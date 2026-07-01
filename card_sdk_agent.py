"""Python port of com.bupin.data.CardSdkAgent (+ CardResponseInfo)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Protocol

from . import constants as c
from .packet_utils import read_int_be, slice_bytes, split_packets


@dataclass
class CardResponseInfo:
    end: bool
    success: bool
    error_code: int
    tips: str
    queue_packet: Deque[bytes] | None = None

    @property
    def packets(self) -> list[bytes]:
        if not self.queue_packet:
            return []
        return list(self.queue_packet)


class NativeCardSdk(Protocol):
    def create_image(
        self,
        pixels_a: list[int],
        pixels_b: list[int],
        lcd_type: int,
        screen_code: int,
    ) -> bytes: ...

    def ble_callback(self, data: bytes) -> bytes: ...

    def scan_callback(self, scan_record: bytes) -> str: ...


def _parse_native_result(raw: bytes, split_payload: bool) -> CardResponseInfo:
    if len(raw) < 2:
        return CardResponseInfo(False, False, 0, "response too short", None)

    result_type = raw[0]
    status = raw[1]

    if status == c.RESULT_STATE_ERROR:
        error_code = raw[2] & 0xFF if len(raw) > 2 else 0
        return CardResponseInfo(
            False,
            False,
            error_code,
            f"type: {result_type & 0xFF}",
            None,
        )

    if status != c.RESULT_STATE_SUCCESS:
        return CardResponseInfo(False, False, 0, "not match resultStatus", None)

    if split_payload:
        if len(raw) < 6:
            return CardResponseInfo(False, False, 0, "success payload too short", None)
        payload_len = read_int_be(raw, 2)
        payload = slice_bytes(raw, 6, payload_len)
        return CardResponseInfo(
            False,
            True,
            0,
            "success",
            split_packets(payload, c.BLE_PACKET_MTU),
        )

    return CardResponseInfo(False, True, 0, "success", None)


def get_refresh_data(
    native: NativeCardSdk,
    pixels_a: list[int] | None,
    pixels_b: list[int] | None,
    width: int,
    height: int,
    lcd_type: int,
    screen_code: int,
) -> CardResponseInfo:
    """
    Port of CardSdkAgent.getRefreshData().

    pixels arrays must match width * height when provided.
    """
    expected = width * height

    if lcd_type not in (
        c.LCD_TYPE_ONLY_A,
        c.LCD_TYPE_ONLY_B,
        c.LCD_TYPE_EQUAL_AB,
        c.LCD_TYPE_DIFFERENT_AB,
    ):
        return CardResponseInfo(False, False, 0, f"invalid lcd_type: {lcd_type}", None)

    arr_a: list[int] = []
    arr_b: list[int] = []

    if lcd_type in (c.LCD_TYPE_ONLY_A, c.LCD_TYPE_ONLY_B, c.LCD_TYPE_EQUAL_AB, c.LCD_TYPE_DIFFERENT_AB):
        if pixels_a is None:
            return CardResponseInfo(False, False, 0, "bitmap1 is null", None)
        if len(pixels_a) != expected:
            return CardResponseInfo(
                False,
                False,
                0,
                f"bitmap1 size mismatch: expected {expected}, got {len(pixels_a)}",
                None,
            )
        arr_a = pixels_a

    if lcd_type == c.LCD_TYPE_DIFFERENT_AB:
        if pixels_b is None:
            return CardResponseInfo(False, False, 0, "bitmap2 is null", None)
        if len(pixels_b) != expected:
            return CardResponseInfo(
                False,
                False,
                0,
                f"bitmap2 size mismatch: expected {expected}, got {len(pixels_b)}",
                None,
            )
        arr_b = pixels_b

    raw = native.create_image(arr_a, arr_b, lcd_type, screen_code)
    return _parse_native_result(raw, split_payload=True)


def refresh_callback(native: NativeCardSdk, notification: bytes) -> CardResponseInfo:
    """Port of CardSdkAgent.refreshCallback()."""
    raw = native.ble_callback(notification)
    if len(raw) < 2:
        return CardResponseInfo(False, False, 0, "callback response too short", None)

    result_type = raw[0]
    status = raw[1]

    if status == c.RESULT_STATE_ERROR:
        error_code = raw[2] & 0xFF if len(raw) > 2 else 0
        return CardResponseInfo(
            False,
            False,
            error_code,
            f"type: {result_type & 0xFF}",
            None,
        )

    if status != c.RESULT_STATE_SUCCESS:
        return CardResponseInfo(False, False, 0, "not match resultStatus", None)

    if result_type == c.RESULT_TYPE_REQUEST_FILE:
        if len(raw) < 6:
            return CardResponseInfo(False, False, 0, "request_file payload too short", None)
        payload_len = read_int_be(raw, 2)
        payload = slice_bytes(raw, 6, payload_len)
        return CardResponseInfo(
            False,
            True,
            0,
            "success",
            split_packets(payload, c.BLE_PACKET_MTU),
        )

    if result_type == c.RESULT_TYPE_WRITE_FILE:
        if len(raw) < 6:
            return CardResponseInfo(False, False, 0, "write_file header too short", None)
        packet_count = read_int_be(raw, 2)
        queue: Deque[bytes] = deque()
        offset = 6
        for _ in range(packet_count):
            if offset + 4 > len(raw):
                break
            packet_len = read_int_be(raw, offset)
            offset += 4
            queue.append(slice_bytes(raw, offset, packet_len))
            offset += packet_len
        return CardResponseInfo(False, True, 0, "success", queue)

    if result_type == c.RESULT_TYPE_REFRESH_END:
        return CardResponseInfo(True, True, 0, "end", None)

    return CardResponseInfo(False, False, 0, "not match resultType", None)
