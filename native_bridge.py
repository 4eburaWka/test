"""
Bridge to libbluetoothhelper.so (com.bupin.blesdk.jni.JniUtils).

The Android app loads native methods via JNI. On desktop Python we call the
same library through a tiny Java helper (EncodeBridge) when available, or
directly when exported symbols exist.

Extract the library from APK:
  lib/arm64-v8a/libbluetoothhelper.so
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from .card_sdk_agent import NativeCardSdk
from .image_utils import to_java_int32


class NativeLibraryError(RuntimeError):
    pass


def extract_lib_from_apk(apk_path: str | Path, arch: str = "arm64-v8a", dest_dir: str | Path | None = None) -> Path:
    apk = Path(apk_path)
    member = f"lib/{arch}/libbluetoothhelper.so"
    out_dir = Path(dest_dir) if dest_dir else Path(tempfile.gettempdir()) / "pm970_native"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "libbluetoothhelper.so"

    with zipfile.ZipFile(apk, "r") as zf:
        if member not in zf.namelist():
            available = sorted({n.split("/")[1] for n in zf.namelist() if n.startswith("lib/")})
            raise NativeLibraryError(
                f"{member} not found in APK. Available arches: {', '.join(available)}"
            )
        out_file.write_bytes(zf.read(member))
    return out_file


class JavaBridgeEncoder(NativeCardSdk):
    """
    Calls JniUtils through a small Java helper.

    Requires:
      - java on PATH
      - tablecard APK or classes.dex + libbluetoothhelper.so for target arch
    """

    def __init__(self, apk_path: str | Path, java_home: str | Path | None = None):
        self.apk_path = Path(apk_path)
        self.java = Path(java_home) / "bin/java" if java_home else Path("java")
        self._bridge_dir = Path(__file__).resolve().parent / "java"
        self._bridge_jar = self._bridge_dir / "pm970-encoder.jar"

    def _run(self, command: str, payload: dict) -> bytes:
        if not self._bridge_jar.is_file():
            raise NativeLibraryError(
                f"Java bridge jar not found: {self._bridge_jar}\n"
                "Build it: cd scripts/pm970/java && build.bat <path-to-tablecard.apk>"
            )

        native_dir = self._bridge_dir / "native"
        if not (native_dir / "libbluetoothhelper.so").is_file() and self.apk_path.is_file():
            extract_lib_from_apk(self.apk_path, dest_dir=native_dir)

        stdin_bytes = self._encode_stdin(command, payload)
        proc = subprocess.run(
            [
                str(self.java),
                f"-Djava.library.path={native_dir}",
                "-cp",
                str(self._bridge_jar),
                "com.bupin.pm970.EncodeBridge",
                command,
            ],
            input=stdin_bytes,
            capture_output=True,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            stdout = proc.stdout.decode("utf-8", errors="replace").strip()
            raise NativeLibraryError(stderr or stdout or "Java bridge failed")

        return self._decode_stdout(proc.stdout.decode("utf-8", errors="replace"))

    @staticmethod
    def _encode_stdin(command: str, payload: dict) -> bytes:
        if command == "create_image":
            pixels_a = [to_java_int32(v) for v in (payload.get("pixels_a") or [])]
            pixels_b = [to_java_int32(v) for v in (payload.get("pixels_b") or [])]
            buf = bytearray()
            buf.extend(struct.pack(">ii", int(payload["lcd_type"]), int(payload["screen_code"])))
            buf.extend(struct.pack(">i", len(pixels_a)))
            if pixels_a:
                buf.extend(struct.pack(f">{len(pixels_a)}i", *pixels_a))
            buf.extend(struct.pack(">i", len(pixels_b)))
            if pixels_b:
                buf.extend(struct.pack(f">{len(pixels_b)}i", *pixels_b))
            return bytes(buf)

        data = bytes.fromhex(payload["data_hex"])
        return struct.pack(">i", len(data)) + data

    @staticmethod
    def _decode_stdout(stdout: str) -> bytes:
        lines = stdout.replace("\r\n", "\n").strip().split("\n")
        if len(lines) < 2:
            raise NativeLibraryError(f"Unexpected bridge output: {stdout!r}")
        status = lines[0].strip()
        if status == "ERR":
            raise NativeLibraryError(lines[1].strip())
        if status == "OK_TEXT":
            return lines[1].encode("utf-8")
        if status == "OK":
            return bytes.fromhex(lines[1].strip())
        raise NativeLibraryError(f"Unknown bridge status: {status}")

    def create_image(
        self,
        pixels_a: list[int],
        pixels_b: list[int],
        lcd_type: int,
        screen_code: int,
    ) -> bytes:
        return self._run(
            "create_image",
            {
                "apk": str(self.apk_path.resolve()),
                "pixels_a": pixels_a,
                "pixels_b": pixels_b,
                "lcd_type": lcd_type,
                "screen_code": screen_code,
            },
        )

    def ble_callback(self, data: bytes) -> bytes:
        return self._run("ble_callback", {"data_hex": data.hex()})

    def scan_callback(self, scan_record: bytes) -> str:
        raw = self._run("scan_callback", {"data_hex": scan_record.hex()})
        return raw.decode("utf-8")


class PassthroughBleCallback(NativeCardSdk):
    """
    Fallback when Java/native bridge is unavailable for BleCallBack only.

    WARNING: may not work on real devices if native transform is non-trivial.
    """

    def __init__(self, inner: NativeCardSdk | None = None):
        self._inner = inner

    def create_image(
        self,
        pixels_a: list[int],
        pixels_b: list[int],
        lcd_type: int,
        screen_code: int,
    ) -> bytes:
        if self._inner is None:
            raise NativeLibraryError(
                "CreateImage requires libbluetoothhelper.so via Java bridge. "
                "Use --apk path/to/tablecard.apk or --packets-file."
            )
        return self._inner.create_image(pixels_a, pixels_b, lcd_type, screen_code)

    def ble_callback(self, data: bytes) -> bytes:
        if self._inner is not None:
            return self._inner.ble_callback(data)
        return data

    def scan_callback(self, scan_record: bytes) -> str:
        if self._inner is not None:
            return self._inner.scan_callback(scan_record)
        raise NativeLibraryError("ScanCallBack requires native bridge")


def load_packets_file(path: str | Path) -> list[bytes]:
    """
    Load pre-encoded BLE packets.

    Supported formats:
      - .bin  : [uint32_be length][payload] repeated
      - .hex  : one packet per line (hex)
      - .json : {"packets": ["aabbcc...", ...]}
    """
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return [bytes.fromhex(item) for item in data["packets"]]

    if suffix == ".hex":
        packets = []
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip().replace(" ", "")
            if line:
                packets.append(bytes.fromhex(line))
        return packets

    raw = file_path.read_bytes()
    packets: list[bytes] = []
    offset = 0
    while offset + 4 <= len(raw):
        length = int.from_bytes(raw[offset : offset + 4], "big")
        offset += 4
        packets.append(raw[offset : offset + length])
        offset += length
    return packets


def save_packets_file(path: str | Path, packets: Iterable[bytes]) -> None:
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".json":
        payload = {"packets": [packet.hex() for packet in packets]}
        file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return

    if suffix == ".hex":
        file_path.write_text("\n".join(packet.hex() for packet in packets) + "\n", encoding="utf-8")
        return

    blob = bytearray()
    for packet in packets:
        blob.extend(len(packet).to_bytes(4, "big"))
        blob.extend(packet)
    file_path.write_bytes(blob)


def create_native_encoder(apk_path: str | Path | None = None) -> NativeCardSdk:
    apk = apk_path or os.environ.get("TABLECARD_APK")
    if apk:
        return JavaBridgeEncoder(apk)
    raise NativeLibraryError(
        "Native encoder not configured. Pass --apk /path/to/tablecard.apk "
        "or set TABLECARD_APK environment variable."
    )
