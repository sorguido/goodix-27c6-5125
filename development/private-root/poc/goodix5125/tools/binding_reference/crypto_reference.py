"""Recovered D190 local volatile binding reference.

No OEM-derived producer half, key or SP800-108 output is printed or persisted.
"""

from __future__ import annotations

import hashlib
import hmac
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FIXED_AAD = bytes.fromhex("522dc1f099567d07f47f37a32a84427d")


def _zero(value: bytearray | None) -> None:
    if value is not None:
        value[:] = bytes(len(value))


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
            value = (
                (value << 1) ^ (0x04C11DB7 if value & 0x80000000 else 0)
            ) & 0xFFFFFFFF
    return value


def _half(seed: bytes) -> bytearray:
    expanded = bytes(
        _ror8(byte, rotation) for rotation in (1, 3, 5, 7) for byte in seed
    )
    groups = [expanded[offset : offset + 3] for offset in range(0, 24, 3)]
    result = bytearray(hashlib.sha256(groups[0]).digest()[:2])
    for index, group in enumerate(groups[1:5]):
        # D190 correction: each AES scratch block starts cleared; blocks are
        # independent and are not chained across iterations.
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


def bind_validator(secret: bytes | memoryview, seed_a: bytes, seed_b: bytes) -> bytearray:
    """Return only validator[32], zeroing mutable intermediate key material."""
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
        # D190 correction: inner is the nonce and FIXED_AAD is the AAD.
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
