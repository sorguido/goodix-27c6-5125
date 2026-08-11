"""Synthetic-only Goodix 27c6:5125 image-record helpers.

This module implements a clean-room data-format contract.  It has no USB,
firmware, TLS, secret, replay, enrollment, verification, or hardware API.
"""

from __future__ import annotations


PACKED_BYTES = 7680
RECORD_BYTES = 7684
SAMPLE_COUNT = 5120
WIDTH = 80
HEIGHT = 64


def crc32_mpeg2(data: bytes) -> int:
    """Return non-reflected CRC-32/MPEG-2 (poly 0x04c11db7)."""
    value = 0xFFFFFFFF
    for byte in data:
        value ^= byte << 24
        for _ in range(8):
            value = ((value << 1) ^ (0x04C11DB7 if value & 0x80000000 else 0)) & 0xFFFFFFFF
    return value


def encode_crc_trailer(value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("CRC outside uint32")
    return bytes(((value >> 8) & 0xFF, value & 0xFF, (value >> 24) & 0xFF, (value >> 16) & 0xFF))


def decode_crc_trailer(trailer: bytes) -> int:
    if len(trailer) != 4:
        raise ValueError("CRC trailer must be four bytes")
    t0, t1, t2, t3 = trailer
    return (t2 << 24) | (t3 << 16) | (t0 << 8) | t1


def decode_group(block: bytes) -> tuple[int, int, int, int]:
    if len(block) != 6:
        raise ValueError("packed group must be six bytes")
    b0, b1, b2, b3, b4, b5 = block
    return (
        ((b0 & 0x0F) << 8) | b1,
        (b3 << 4) | (b0 >> 4),
        ((b5 & 0x0F) << 8) | b2,
        (b4 << 4) | (b5 >> 4),
    )


def encode_group(samples: tuple[int, int, int, int]) -> bytes:
    if len(samples) != 4 or any(value < 0 or value > 0xFFF for value in samples):
        raise ValueError("four 12-bit samples required")
    p0, p1, p2, p3 = samples
    return bytes((
        ((p1 & 0x0F) << 4) | ((p0 >> 8) & 0x0F),
        p0 & 0xFF,
        p2 & 0xFF,
        (p1 >> 4) & 0xFF,
        (p3 >> 4) & 0xFF,
        ((p3 & 0x0F) << 4) | ((p2 >> 8) & 0x0F),
    ))


def raster_index(wire_index: int) -> int:
    if not 0 <= wire_index < SAMPLE_COUNT:
        raise ValueError("wire index outside frame")
    return (wire_index % HEIGHT) * WIDTH + wire_index // HEIGHT


def decode_record(record: bytes) -> tuple[int, ...]:
    """Validate and decode one exact record into an owned 80x64 u16 tuple."""
    if len(record) != RECORD_BYTES:
        raise ValueError("record must be exactly 7684 bytes")
    packed = record[:PACKED_BYTES]
    if crc32_mpeg2(packed) != decode_crc_trailer(record[PACKED_BYTES:]):
        raise ValueError("CRC mismatch")
    raster = [0] * SAMPLE_COUNT
    wire_index = 0
    for offset in range(0, PACKED_BYTES, 6):
        for value in decode_group(packed[offset:offset + 6]):
            raster[raster_index(wire_index)] = value
            wire_index += 1
    return tuple(raster)


def encode_synthetic_record(raster: tuple[int, ...]) -> bytes:
    """Encode synthetic test values; this is not a device command or replay."""
    if len(raster) != SAMPLE_COUNT or any(value < 0 or value > 0xFFF for value in raster):
        raise ValueError("5120 12-bit samples required")
    wire = tuple(raster[raster_index(index)] for index in range(SAMPLE_COUNT))
    packed = b"".join(encode_group(wire[index:index + 4]) for index in range(0, SAMPLE_COUNT, 4))
    return packed + encode_crc_trailer(crc32_mpeg2(packed))

