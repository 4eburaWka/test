"""BLE transport for pm970 devices (Nordic UART + Card SDK protocol)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from typing import Deque

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import constants as c
from .card_sdk_agent import CardResponseInfo, NativeCardSdk, refresh_callback

logger = logging.getLogger(__name__)


class Pm970BleClient:
    def __init__(
        self,
        native: NativeCardSdk,
        address: str | None = None,
        name_filter: str = c.BLE_FILTER_NAME,
        write_delay_ms: float = c.WRITE_DELAY_MS,
    ):
        self.native = native
        self.address = address
        self.name_filter = name_filter
        self.write_delay_ms = write_delay_ms
        self._client: BleakClient | None = None
        self._notify_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._done = asyncio.Event()
        self._failed = asyncio.Event()
        self._last_error: str | None = None
        self._pending: Deque[bytes] = deque()
        self._pending_lock = asyncio.Lock()
        self._pending_changed = asyncio.Event()

    async def scan(self, timeout: float = 10.0) -> BLEDevice:
        logger.info("Scanning for BLE devices (%ss)...", timeout)

        def match(device: BLEDevice, _adv_data) -> bool:
            name = device.name or ""
            if self.address and device.address.lower() == self.address.lower():
                return True
            return self.name_filter.lower() in name.lower()

        device = await BleakScanner.find_device_by_filter(match, timeout=timeout)
        if device is None:
            raise RuntimeError(
                f"Device not found (filter='{self.name_filter}', address={self.address})"
            )
        logger.info("Found %s (%s)", device.name, device.address)
        return device

    async def connect(self, device: BLEDevice) -> None:
        self._client = BleakClient(device)
        await self._client.connect()
        await asyncio.sleep(c.CONNECT_NOTIFY_DELAY_MS / 1000.0)
        await self._client.start_notify(c.UUID_NOTIFY, self._on_notify)
        logger.info("Connected and notifications enabled")

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None

    def _on_notify(self, _handle: int, data: bytearray) -> None:
        self._notify_queue.put_nowait(bytes(data))

    async def send_packets(self, initial_packets: Deque[bytes] | list[bytes]) -> None:
        if self._client is None or not self._client.is_connected:
            raise RuntimeError("Not connected")

        self._done.clear()
        self._failed.clear()
        self._last_error = None
        self._pending = deque(initial_packets)
        self._pending_changed.set()

        notify_task = asyncio.create_task(self._consume_notifications())
        sender_task = asyncio.create_task(self._sender_loop())
        try:
            await asyncio.wait_for(self._done.wait(), timeout=180.0)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Timed out waiting for REFRESH_END from device") from exc
        finally:
            notify_task.cancel()
            sender_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(notify_task, sender_task)

        if self._failed.is_set():
            raise RuntimeError(self._last_error or "Device reported failure")

    async def _sender_loop(self) -> None:
        while not self._done.is_set():
            await self._pending_changed.wait()
            self._pending_changed.clear()

            while self._pending and not self._done.is_set():
                async with self._pending_lock:
                    if not self._pending:
                        break
                    packet = self._pending.popleft()
                await self._write(packet)
                await asyncio.sleep(self.write_delay_ms / 1000.0)

    async def _consume_notifications(self) -> None:
        while not self._done.is_set():
            data = await self._notify_queue.get()
            response = refresh_callback(self.native, data)
            await self._handle_response(response)

    async def _handle_response(self, response: CardResponseInfo) -> None:
        logger.debug(
            "Device response: end=%s success=%s tips=%s extra_packets=%s",
            response.end,
            response.success,
            response.tips,
            0 if not response.queue_packet else len(response.queue_packet),
        )

        if response.end:
            self._done.set()
            return

        if not response.success:
            self._last_error = response.tips
            self._failed.set()
            self._done.set()
            return

        if response.queue_packet:
            async with self._pending_lock:
                self._pending.extend(response.queue_packet)
            self._pending_changed.set()

    async def _write(self, packet: bytes) -> None:
        assert self._client is not None
        logger.debug("Writing %d bytes: %s", len(packet), packet.hex())
        await self._client.write_gatt_char(c.UUID_WRITE, packet, response=False)
