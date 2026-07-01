"""PM970 image encoder + BLE sender CLI."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import deque
from pathlib import Path

from . import constants as c
from .ble_client import Pm970BleClient
from .card_sdk_agent import get_refresh_data
from .image_utils import load_argb_pixels, resolve_lcd_type
from .native_bridge import (
    NativeLibraryError,
    PassthroughBleCallback,
    create_native_encoder,
    load_packets_file,
    save_packets_file,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("pm970")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Encode image(s) and send to pm970 e-paper badge over BLE.",
    )
    parser.add_argument("--address", help="BLE MAC address (AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--scan-timeout", type=float, default=12.0, help="BLE scan timeout, seconds")
    parser.add_argument("--apk", help="Path to TableCard APK (for native JniUtils bridge)")
    parser.add_argument("--screen-code", type=int, default=0, help="Device screenCode from scan data")
    parser.add_argument("--width", type=int, default=c.DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=c.DEFAULT_HEIGHT)
    parser.add_argument("--image-a", help="Image file for side A")
    parser.add_argument("--image-b", help="Image file for side B (double-sided)")
    parser.add_argument(
        "--packets-file",
        help="Skip encoding; send pre-encoded packets (.bin/.hex/.json)",
    )
    parser.add_argument(
        "--dump-packets",
        help="Encode only and save packets to file (.bin/.hex/.json), no BLE",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def prepare_packets(args: argparse.Namespace) -> deque[bytes]:
    if args.packets_file:
        packets = load_packets_file(args.packets_file)
        logger.info("Loaded %d packets from %s", len(packets), args.packets_file)
        return deque(packets)

    if not args.image_a and not args.image_b:
        raise SystemExit("Provide --image-a/--image-b or --packets-file")

    native = _create_native(args)
    pixels_a = load_argb_pixels(args.image_a, args.width, args.height) if args.image_a else None
    pixels_b = load_argb_pixels(args.image_b, args.width, args.height) if args.image_b else None

    same_image = bool(
        args.image_a
        and args.image_b
        and Path(args.image_a).read_bytes() == Path(args.image_b).read_bytes()
    )
    lcd_type = resolve_lcd_type(args.image_a, args.image_b, same_image)

    info = get_refresh_data(
        native=native,
        pixels_a=pixels_a,
        pixels_b=pixels_b,
        width=args.width,
        height=args.height,
        lcd_type=lcd_type,
        screen_code=args.screen_code,
    )
    if not info.success or not info.queue_packet:
        raise SystemExit(f"Encoding failed: {info.tips} (code={info.error_code})")

    packets = info.queue_packet
    logger.info("Encoded %d BLE packets (lcd_type=%s)", len(packets), lcd_type)
    return packets


def _create_native(args: argparse.Namespace):
    if args.apk:
        return create_native_encoder(args.apk)
    try:
        return create_native_encoder()
    except NativeLibraryError:
        return PassthroughBleCallback()


async def run_async(args: argparse.Namespace) -> None:
    packets = prepare_packets(args)

    if args.dump_packets:
        save_packets_file(args.dump_packets, packets)
        logger.info("Saved %d packets to %s", len(packets), args.dump_packets)
        return

    native = _create_native(args)
    client = Pm970BleClient(native=native, address=args.address)
    device = await client.scan(timeout=args.scan_timeout)
    await client.connect(device)
    try:
        logger.info("Sending %d packets...", len(packets))
        await client.send_packets(packets)
        logger.info("Refresh completed successfully")
    finally:
        await client.disconnect()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        asyncio.run(run_async(args))
        return 0
    except KeyboardInterrupt:
        logger.warning("Interrupted")
        return 130
    except (NativeLibraryError, RuntimeError, SystemExit) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    # Allow: python pm970_send.py (from scripts/pm970 directory)
    if __package__ is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from pm970.pm970_send import main as _main  # type: ignore[import]

        sys.exit(_main())
    sys.exit(main())
