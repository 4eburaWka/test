"""Packet helpers ported from a.a and a.b (Card SDK helpers)."""

from __future__ import annotations

from collections import deque
from typing import Deque


def read_int_be(data: bytes, offset: int = 0) -> int:
    """Port of a.b.a(byte[]) — big-endian int32."""
    if offset + 4 > len(data):
        raise ValueError(f"Not enough bytes for int32 at offset {offset}")
    return (
        ((data[offset] & 0xFF) << 24)
        | ((data[offset + 1] & 0xFF) << 16)
        | ((data[offset + 2] & 0xFF) << 8)
        | (data[offset + 3] & 0xFF)
    )


def slice_bytes(data: bytes, offset: int, length: int) -> bytes:
    """Port of a.b.a(byte[], int, int)."""
    return data[offset : offset + length]


def split_packets(data: bytes, chunk_size: int = 242) -> Deque[bytes]:
    """
    Port of a.a.a(byte[]) — split payload into BLE packets.

    Mirrors CardSdkAgent.BLE_PACKET_MTU = 242.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")

    packets: Deque[bytes] = deque()
    if not data:
        return packets

    total = len(data) // chunk_size
    if len(data) % chunk_size != 0:
        total += 1

    for index in range(total):
        start = index * chunk_size
        if index == total - 1:
            end = len(data)
        else:
            end = start + chunk_size
        packets.append(data[start:end])

    return packets
