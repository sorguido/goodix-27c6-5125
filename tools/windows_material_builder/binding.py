# SPDX-License-Identifier: GPL-2.0-or-later
"""Qualified binding reused from project finalizer at fa98461.

Pure PE/crypto subset; original CLI and staging-record IO are intentionally absent.
See AUDIT.md for provenance and native cross-checks. No DLL execution.
"""
import hashlib
import hmac
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VID = 0x27C6
PID = 0x5125
SECRET_LENGTH = 32

XFR_MAGIC = b"G5125XFR"
XFR_VERSION = 1
XFR_HEADER_LENGTH = 24
XFR_LENGTH = 88
XFR_HEADER = struct.Struct("<8sHHHHHHI")

POC_MAGIC = b"G5125POC"
POC_VERSION = 1
POC_HEADER_LENGTH = 24
POC_LENGTH = 88
POC_HEADER = struct.Struct("<8sHHHHHHHH")

OEM_PE_LENGTH = 5_771_496
OEM_PE_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
FIRST_SEED_RVA = 0x56F030
SECOND_SEED_INSTRUCTION_RVA = 0x69D0

FIXED_AAD = bytes.fromhex("522dc1f099567d07f47f37a32a84427d")


def _zero(value: bytearray | None) -> None:
    if value is not None:
        value[:] = bytes(len(value))


def _sections(data: bytes | bytearray) -> list[tuple[int, int, int, int]]:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("invalid PE DOS header")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe > len(data) - 24 or data[pe : pe + 4] != b"PE\0\0":
        raise ValueError("invalid PE header")
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
            if offset <= len(data) and size <= len(data) - offset:
                return bytes(data[offset : offset + size])
            break
    raise ValueError(f"RVA 0x{rva:x} is outside file-backed PE ranges")


def _extract_seeds(data: bytes | bytearray) -> tuple[bytearray, bytearray]:
    if len(data) != OEM_PE_LENGTH:
        raise ValueError("gfusb.dll length mismatch")
    actual = hashlib.sha256(data).hexdigest()
    if actual != OEM_PE_SHA256:
        raise ValueError("gfusb.dll SHA-256 mismatch")
    sections = _sections(data)
    first = bytearray(_at_rva(data, sections, FIRST_SEED_RVA, 6))
    instruction = _at_rva(data, sections, SECOND_SEED_INSTRUCTION_RVA, 14)
    try:
        pattern = instruction[:12]
        if (
            len(instruction) != 14
            or pattern[:3] != b"\xc7\x45\x9f"
            or pattern[7:10] != b"\xc7\x45\xa3"
            or bytes(data).count(pattern) != 1
        ):
            raise ValueError("producer instruction pattern missing or ambiguous")
        second = bytearray(instruction[3:7] + instruction[10:12])
        if len(first) != 6 or len(second) != 6 or not any(first) or not any(second):
            _zero(second)
            raise ValueError("producer seed rejected")
        return first, second
    except BaseException:
        _zero(first)
        raise


def _ror8(value: int, count: int) -> int:
    return ((value >> count) | (value << (8 - count))) & 0xFF


def _aes(key: bytes, block: bytes, decrypt: bool) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    operation = cipher.decryptor() if decrypt else cipher.encryptor()
    return operation.update(block) + operation.finalize()


def _crc(data: bytes) -> int:
    value = 0xFFFFFFFF
    for byte in data:
        value ^= byte << 24
        for _ in range(8):
            value = ((value << 1) ^ (0x04C11DB7 if value & 0x80000000 else 0)) & 0xFFFFFFFF
    return value


def _half(seed: bytes) -> bytearray:
    expanded = bytes(_ror8(byte, rotation) for rotation in (1, 3, 5, 7) for byte in seed)
    groups = [expanded[offset : offset + 3] for offset in range(0, 24, 3)]
    result = bytearray(hashlib.sha256(groups[0]).digest()[:2])
    for index, group in enumerate(groups[1:5]):
        block = group + b"\xcc" * 13
        if index % 2:
            transformed = _aes(bytes(16 if index == 1 else 24), block, False)
        else:
            transformed = _aes(bytes(16 if index == 0 else 32), block, True)
        result.extend(transformed[:2])
    result.extend(hmac.new(b"123456" + bytes(10), groups[5], hashlib.sha256).digest()[:2])
    result.extend(_crc(groups[6]).to_bytes(4, "big")[:2])
    result.extend(hashlib.sha256(groups[7]).digest()[:2])
    return result


def _bind_validator(secret: bytes | memoryview, seed_a: bytes, seed_b: bytes) -> bytearray:
    if len(secret) != 32 or len(seed_a) != 6 or len(seed_b) != 6:
        raise ValueError("binding requires secret[32] and two seed[6] values")
    half_a = half_b = key = derived = envelope = None
    try:
        half_a, half_b = _half(seed_a), _half(seed_b)
        key = bytearray(half_a + half_b)
        fixed = b"kgoodwixg\0kaelrgnoerlithm" + struct.pack(">I", 384)
        t1 = hmac.new(key, struct.pack(">I", 1) + fixed, hashlib.sha256).digest()
        t2 = hmac.new(key, struct.pack(">I", 2) + fixed, hashlib.sha256).digest()
        derived = bytearray(t1 + t2[:16])
        header = struct.pack("<HI", 0xFF02, 32)
        secret_bytes = bytes(secret)
        inner = hashlib.sha256(header + secret_bytes[:8] + struct.pack("<I", 3) * 16).digest()[:16]
        encrypted = AESGCM(bytes(derived[:32])).encrypt(inner, secret_bytes, FIXED_AAD)
        ciphertext, tag = encrypted[:-16], encrypted[-16:]
        outer = hmac.new(derived[16:48], header + ciphertext + tag, hashlib.sha256).digest()
        envelope = bytearray(outer + header + inner + ciphertext + tag)
        if len(envelope) != 102:
            raise ValueError("binding envelope length mismatch")
        return bytearray(hashlib.sha256(envelope).digest())
    finally:
        for value in (half_a, half_b, key, derived, envelope):
            _zero(value)


def _build_poc(secret: bytearray, validator: bytes | bytearray) -> bytearray:
    if len(secret) != 32 or len(validator) != 32:
        raise ValueError("runtime fields must be exactly 32 bytes")
    result = bytearray(
        POC_HEADER.pack(POC_MAGIC, POC_VERSION, POC_HEADER_LENGTH, VID, PID, 1, 32, 32, 0)
    )
    result.extend(secret)
    result.extend(validator)
    if len(result) != POC_LENGTH:
        raise AssertionError("runtime transport length mismatch")
    return result
