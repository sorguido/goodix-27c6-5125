#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Finalize a Goodix 27c6:5125 Windows transfer record into runtime material.

The input transfer record is produced on Windows by
Export-Goodix5125TransportMaterial.ps1. The finalizer validates that staging
record, reads the two producer seeds from the qualified OEM gfusb.dll without
loading the DLL, derives the runtime validator, and writes G5125POC v1.

No secret, producer seed, derived key, or plaintext material is printed.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
from pathlib import Path
import stat
import struct
import tempfile

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError as exc:  # pragma: no cover - environment dependent
    raise SystemExit(
        "STOP: python3-cryptography is required. On Fedora: "
        "sudo dnf5 install python3-cryptography"
    ) from exc

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


def _read_regular(path: Path, *, exact_size: int | None = None) -> bytearray:
    if not path.is_absolute():
        raise ValueError("input paths must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("regular file required")
        if exact_size is not None and info.st_size != exact_size:
            raise ValueError(f"unexpected file size for {path.name}")
        data = bytearray()
        while len(data) < info.st_size:
            chunk = os.read(fd, info.st_size - len(data))
            if not chunk:
                raise ValueError("short read rejected")
            data.extend(chunk)
        if os.read(fd, 1):
            raise ValueError("file changed while being read")
        return data
    finally:
        os.close(fd)


def _parse_transfer(record: bytes | bytearray) -> bytearray:
    if len(record) != XFR_LENGTH:
        raise ValueError("transfer record length rejected")
    magic, version, flags, vid, pid, secret_len, reserved, payload_len = XFR_HEADER.unpack_from(record)
    if magic != XFR_MAGIC or version != XFR_VERSION:
        raise ValueError("transfer record magic/version rejected")
    if flags != 0 or reserved != 0 or vid != VID or pid != PID:
        raise ValueError("transfer record header rejected")
    if secret_len != SECRET_LENGTH or payload_len != SECRET_LENGTH:
        raise ValueError("transfer record lengths rejected")
    expected = hashlib.sha256(record[: XFR_HEADER_LENGTH + SECRET_LENGTH]).digest()
    if not hmac.compare_digest(expected, record[56:88]):
        raise ValueError("transfer record digest rejected")
    secret = bytearray(record[24:56])
    if not any(secret):
        _zero(secret)
        raise ValueError("zero secret rejected")
    return secret


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


def _write_private_atomic(path: Path, data: bytes | bytearray) -> None:
    if not path.is_absolute():
        raise ValueError("output path must be absolute")
    if path.exists() or path.is_symlink():
        raise FileExistsError("output path already exists")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("output parent must be an existing non-symlink directory")
    fd, tmp_name = tempfile.mkstemp(prefix=".goodix-transport-", dir=parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            view = view[count:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(tmp, path, follow_symlinks=False)
        tmp.unlink()
        parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        check = _read_regular(path, exact_size=POC_LENGTH)
        try:
            if not hmac.compare_digest(check, data):
                raise ValueError("output byte verification failed")
        finally:
            _zero(check)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _build_synthetic_xfr(secret: bytes) -> bytearray:
    prefix = bytearray(XFR_HEADER.pack(XFR_MAGIC, 1, 0, VID, PID, 32, 0, 32))
    prefix.extend(secret)
    prefix.extend(hashlib.sha256(prefix).digest())
    return prefix


def _self_test() -> None:
    secret = bytearray(range(1, 33))
    seed_a = bytearray.fromhex("010203040506")
    seed_b = bytearray.fromhex("a1a2a3a4a5a6")
    record = parsed = validator = runtime = None
    try:
        record = _build_synthetic_xfr(secret)
        if len(record) != XFR_LENGTH:
            raise AssertionError("synthetic transfer length mismatch")
        parsed = _parse_transfer(record)
        if not hmac.compare_digest(parsed, secret):
            raise AssertionError("synthetic transfer parse mismatch")
        validator = _bind_validator(parsed, seed_a, seed_b)
        runtime = _build_poc(parsed, validator)
        if len(runtime) != POC_LENGTH or runtime[:8] != POC_MAGIC:
            raise AssertionError("synthetic runtime material mismatch")
        damaged = bytearray(record)
        damaged[30] ^= 0x01
        rejected = False
        try:
            _parse_transfer(damaged)
        except ValueError:
            rejected = True
        finally:
            _zero(damaged)
        if not rejected:
            raise AssertionError("damaged transfer unexpectedly accepted")
    finally:
        for value in (runtime, validator, parsed, record, seed_a, seed_b, secret):
            _zero(value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finalize Goodix 27c6:5125 G5125XFR staging material into G5125POC runtime material."
    )
    parser.add_argument("--self-test", action="store_true", help="run a secret-free synthetic self-test")
    parser.add_argument("--transfer", type=Path, help="absolute path to transport-material.xfr")
    parser.add_argument("--oem-pe", type=Path, help="absolute path to the qualified gfusb.dll")
    parser.add_argument("--output", type=Path, help="absolute output path for transport-material.bin")
    args = parser.parse_args()

    if args.self_test:
        if any(value is not None for value in (args.transfer, args.oem_pe, args.output)):
            parser.error("--self-test cannot be combined with input/output arguments")
        _self_test()
        print("GOODIX_TRANSPORT_FINALIZER_SELFTEST=PASS")
        return 0

    if None in (args.transfer, args.oem_pe, args.output):
        parser.error("--transfer, --oem-pe and --output are required")

    transfer = pe_data = secret = seed_a = seed_b = validator = runtime = None
    try:
        transfer = _read_regular(args.transfer, exact_size=XFR_LENGTH)
        secret = _parse_transfer(transfer)
        pe_data = _read_regular(args.oem_pe, exact_size=OEM_PE_LENGTH)
        seed_a, seed_b = _extract_seeds(pe_data)
        validator = _bind_validator(secret, seed_a, seed_b)
        runtime = _build_poc(secret, validator)
        _write_private_atomic(args.output, runtime)
        digest = hashlib.sha256(runtime).hexdigest()
    finally:
        for value in (runtime, validator, seed_a, seed_b, secret, pe_data, transfer):
            _zero(value)

    print("GOODIX_TRANSPORT_FINALIZER=PASS")
    print(f"output={args.output}")
    print(f"size={POC_LENGTH}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
