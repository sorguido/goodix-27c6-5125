"""Narrow, read-only parser for the two producer seeds in canonical gfusb.dll.

This is the D190 parser recovered from a local Codex session transcript, with
the bounded-parser hardening made in D191 and an explicit uniqueness check for
the target instruction pattern.  The DLL is parsed as bytes and never loaded.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct

EXPECTED_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
_FIRST_SEED_RVA = 0x56F030
_SECOND_SEED_INSTRUCTION_RVA = 0x69D0


def _sections(data: bytes | bytearray) -> list[tuple[int, int, int, int]]:
    if len(data) < 0x40:
        raise ValueError("truncated DOS header")
    if data[:2] != b"MZ":
        raise ValueError("not a PE image")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe > len(data) - 24:
        raise ValueError("PE header outside bounded image")
    if data[pe : pe + 4] != b"PE\0\0":
        raise ValueError("invalid PE signature")
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    if count == 0 or count > 96:
        raise ValueError("PE section count rejected")
    table = pe + 24 + optional
    if table > len(data) or count > (len(data) - table) // 40:
        raise ValueError("truncated PE section table")
    return [
        struct.unpack_from("<IIII", data, table + 40 * index + 8)
        for index in range(count)
    ]


def _at_rva(
    data: bytes | bytearray,
    sections: list[tuple[int, int, int, int]],
    rva: int,
    size: int,
) -> bytes:
    for virtual_size, virtual_address, raw_size, raw_offset in sections:
        backed = min(virtual_size, raw_size)
        if virtual_address <= rva and rva + size <= virtual_address + backed:
            offset = raw_offset + rva - virtual_address
            if offset > len(data) or size > len(data) - offset:
                break
            return bytes(data[offset : offset + size])
    raise ValueError(f"RVA 0x{rva:x} is outside file-backed canonical ranges")


def _require_unique_instruction_pattern(data: bytes | bytearray, instruction: bytes) -> None:
    """Reject drift and ambiguity without exposing the embedded immediates."""
    pattern = instruction[:12]
    if (
        len(instruction) != 14
        or pattern[:3] != b"\xc7\x45\x9f"
        or pattern[7:10] != b"\xc7\x45\xa3"
        or bytes(data).count(pattern) != 1
    ):
        raise ValueError("canonical producer instruction pattern missing or ambiguous")


def extract_seeds_from_bytes(data: bytes | bytearray) -> tuple[bytearray, bytearray]:
    actual = hashlib.sha256(data).hexdigest()
    if actual != EXPECTED_SHA256:
        raise ValueError("PE hash mismatch")
    sections = _sections(data)
    first = bytearray(_at_rva(data, sections, _FIRST_SEED_RVA, 6))
    instruction = _at_rva(data, sections, _SECOND_SEED_INSTRUCTION_RVA, 14)
    try:
        _require_unique_instruction_pattern(data, instruction)
        second = bytearray(instruction[3:7] + instruction[10:12])
        if len(first) != 6 or len(second) != 6:
            raise ValueError("producer seed length mismatch")
        return first, second
    except BaseException:
        first[:] = bytes(len(first))
        raise


def extract_seeds(path: Path) -> tuple[bytearray, bytearray]:
    return extract_seeds_from_bytes(path.read_bytes())
