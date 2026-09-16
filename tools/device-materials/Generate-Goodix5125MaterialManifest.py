#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate the per-reader manifest after validating an offline material bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import struct
import tempfile
from pathlib import Path
from typing import Callable

from _goodix5125_usbpcap import ExtractError, atomic_write_new_0600

SCHEMA = "goodix-5125-device-materials-v1"
RESPONSE_SCHEMA = "goodix-5125-device-response-pins-v1"
RESPONSE_MAX_LENGTH = 4096
DIGEST_KEYS = (
    "a2_response_sha256",
    "chip82_response_sha256",
    "otp_a6_response_sha256",
)
RESPONSE_OPTIONAL_KEYS = (
    "a2_occurrence_count",
    "chip82_occurrence_count",
    "otp_a6_occurrence_count",
)


def read_exact(path: Path, size: int) -> bytes:
    if path is None or not path.is_absolute():
        raise ValueError("all input paths must be absolute")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
        getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode) or status.st_size != size:
            raise ValueError(f"{path.name}: regular {size}-byte file required")
        chunks = bytearray()
        while len(chunks) < size:
            chunk = os.read(descriptor, size - len(chunks))
            if not chunk:
                raise ValueError(f"{path.name}: short or changing file")
            chunks.extend(chunk)
        if os.read(descriptor, 1):
            raise ValueError(f"{path.name}: short or changing file")
        return bytes(chunks)
    finally:
        os.close(descriptor)


def read_bounded(path: Path, maximum: int) -> bytes:
    if path is None or not path.is_absolute():
        raise ValueError("all input paths must be absolute")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
        getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        status = os.fstat(descriptor)
        if (not stat.S_ISREG(status.st_mode) or status.st_size <= 0 or
                status.st_size > maximum):
            raise ValueError(
                f"{path.name}: regular non-empty file up to {maximum} bytes required"
            )
        chunks = bytearray()
        while len(chunks) < status.st_size:
            chunk = os.read(descriptor, status.st_size - len(chunks))
            if not chunk:
                raise ValueError(f"{path.name}: short or changing file")
            chunks.extend(chunk)
        if os.read(descriptor, 1):
            raise ValueError(f"{path.name}: short or changing file")
        return bytes(chunks)
    finally:
        os.close(descriptor)


def crc32_mpeg2(data: bytes) -> int:
    value = 0xffffffff
    for byte in data:
        value ^= byte << 24
        for _ in range(8):
            value = ((value << 1) ^
                     (0x04c11db7 if value & 0x80000000 else 0)) & 0xffffffff
    return value


def finalizer(data: bytes) -> int:
    return (-0xa5a5 - sum(
        int.from_bytes(data[offset:offset + 2], "little")
        for offset in range(0, 222, 2)
    )) & 0xffff


def response_digest(value: str | None, length: int, name: str) -> str:
    if value is None:
        raise ValueError(f"{name}: response is required")
    try:
        body = bytes.fromhex(value)
    except ValueError as error:
        raise ValueError(f"{name}: invalid hex") from error
    if len(body) != length:
        raise ValueError(f"{name}: exactly {length} bytes required")
    return hashlib.sha256(body).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"response pins: duplicate key {key}")
        result[key] = value
    return result


def read_response_pins(path: Path) -> dict[str, str]:
    encoded = read_bounded(path, RESPONSE_MAX_LENGTH)
    if b"\0" in encoded:
        raise ValueError("response pins: embedded NUL rejected")
    try:
        document = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_unique_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"response pins: malformed JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("response pins: JSON object required")
    allowed = {"schema", *DIGEST_KEYS, *RESPONSE_OPTIONAL_KEYS}
    if set(document) - allowed:
        raise ValueError("response pins: unknown key rejected")
    if document.get("schema") != RESPONSE_SCHEMA:
        raise ValueError("response pins: schema rejected")
    result: dict[str, str] = {}
    for key in DIGEST_KEYS:
        value = document.get(key)
        if (not isinstance(value, str) or len(value) != 64 or
                any(character not in "0123456789abcdef" for character in value)):
            raise ValueError(f"response pins: {key} must be 64 lowercase hex digits")
        result[key] = value
    for key in RESPONSE_OPTIONAL_KEYS:
        value = document.get(key)
        if value is not None and (not isinstance(value, int) or
                                  isinstance(value, bool) or value < 1):
            raise ValueError(f"response pins: {key} must be a positive integer")
    return result


def response_pins(arguments: argparse.Namespace) -> dict[str, str]:
    manual = (arguments.a2, arguments.chip82, arguments.otp)
    if arguments.response_pins is not None:
        if any(value is not None for value in manual):
            raise ValueError(
                "--response-pins cannot be combined with manual response arguments"
            )
        return read_response_pins(arguments.response_pins)
    if any(value is None for value in manual):
        raise ValueError(
            "use --response-pins or provide all three manual response arguments"
        )
    return {
        "a2_response_sha256": response_digest(arguments.a2, 3, "A2"),
        "chip82_response_sha256": response_digest(arguments.chip82, 4, "chip82"),
        "otp_a6_response_sha256": response_digest(arguments.otp, 64, "OTP A6"),
    }


def atomic(path: Path, data: bytes,
           *, write_func: Callable[[int, bytes | memoryview], int] = os.write) -> None:
    if path is None or not path.is_absolute():
        raise ValueError("output must be a new absolute path")
    try:
        atomic_write_new_0600(path, data, write_func=write_func)
    except ExtractError as error:
        raise ValueError(str(error)) from error


def generate(arguments: argparse.Namespace) -> dict[str, str]:
    transport = read_exact(arguments.transport, 88)
    config90 = read_exact(arguments.config90, 224)
    fdt_cache = read_exact(arguments.fdt_cache, 13520)
    header = struct.unpack_from("<8sHHHHHHHH", transport)
    if header != (b"G5125POC", 1, 24, 0x27c6, 0x5125, 1, 32, 32, 0):
        raise ValueError("transport header rejected")
    if int.from_bytes(config90[-2:], "little") != finalizer(config90):
        raise ValueError("CONFIG90 finalizer rejected")
    if int.from_bytes(fdt_cache[-4:], "little") != crc32_mpeg2(fdt_cache[:-4]):
        raise ValueError("FDT cache CRC rejected")
    pins = response_pins(arguments)
    manifest = {
        "schema": SCHEMA,
        "vid": "27c6",
        "pid": "5125",
        "app": "GF_ST411SEC_APP_12509",
        "transport_sha256": hashlib.sha256(transport).hexdigest(),
        "config90_sha256": hashlib.sha256(config90).hexdigest(),
        "fdt_cache_sha256": hashlib.sha256(fdt_cache).hexdigest(),
        **pins,
    }
    if manifest["otp_a6_response_sha256"] != hashlib.sha256(fdt_cache[:64]).hexdigest():
        raise ValueError("OTP A6 response does not match FDT cache OTP")
    atomic(
        arguments.output,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("ascii"),
    )
    return manifest


def _arguments(root: Path, output: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "transport": (root / "transport").absolute(),
        "config90": (root / "config90").absolute(),
        "fdt_cache": (root / "fdt-cache").absolute(),
        "response_pins": None,
        "a2": "010203",
        "chip82": "01020304",
        "otp": bytes(range(64)).hex(),
        "output": output.absolute(),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def selftest() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        transport = struct.pack(
            "<8sHHHHHHHH", b"G5125POC", 1, 24, 0x27c6, 0x5125, 1, 32, 32, 0
        ) + bytes(range(64))
        config90 = bytearray(224)
        config90[-2:] = finalizer(config90).to_bytes(2, "little")
        fdt_cache = bytearray(13520)
        fdt_cache[:64] = bytes(range(64))
        fdt_cache[64:76] = b"nonzero-seed"
        fdt_cache[-4:] = crc32_mpeg2(fdt_cache[:-4]).to_bytes(4, "little")
        for name, data in (
            ("transport", transport),
            ("config90", config90),
            ("fdt-cache", fdt_cache),
        ):
            (root / name).write_bytes(data)

        manual_output = root / "manual-manifest"
        manual = generate(_arguments(root, manual_output))
        assert json.loads(manual_output.read_text())["schema"] == SCHEMA

        pin_document = {
            "schema": RESPONSE_SCHEMA,
            "a2_response_sha256": hashlib.sha256(b"\x01\x02\x03").hexdigest(),
            "chip82_response_sha256": hashlib.sha256(b"\x01\x02\x03\x04").hexdigest(),
            "otp_a6_response_sha256": hashlib.sha256(bytes(range(64))).hexdigest(),
            "a2_occurrence_count": 2,
            "chip82_occurrence_count": 1,
            "otp_a6_occurrence_count": 1,
        }
        pin_path = (root / "device-response-pins.json").absolute()
        pin_path.write_text(json.dumps(pin_document), encoding="ascii")
        pin_output = root / "pins-manifest"
        from_pins = generate(_arguments(
            root, pin_output, response_pins=pin_path, a2=None, chip82=None, otp=None
        ))
        assert from_pins == manual

        try:
            response_pins(_arguments(root, root / "unused", response_pins=pin_path))
        except ValueError as error:
            assert "cannot be combined" in str(error)
        else:
            raise AssertionError("mixed response-pin input was accepted")

        duplicate_pin_path = (root / "duplicate-response-pins.json").absolute()
        duplicate_pin_path.write_text(
            '{"schema":"' + RESPONSE_SCHEMA + '","schema":"' +
            RESPONSE_SCHEMA + '"}', encoding="ascii"
        )
        try:
            read_response_pins(duplicate_pin_path)
        except ValueError as error:
            assert "duplicate key schema" in str(error)
        else:
            raise AssertionError("duplicate response-pin key was accepted")

        short_output = (root / "short-write-output").absolute()

        def short_write(descriptor: int, data: bytes | memoryview) -> int:
            return os.write(descriptor, data[:7])

        payload = b"short-write-safe" * 19
        atomic(short_output, payload, write_func=short_write)
        assert short_output.read_bytes() == payload
        assert short_output.stat().st_mode & 0o777 == 0o600
        assert not any(path.suffix == ".tmp" for path in root.iterdir())

    print("GOODIX_MATERIAL_MANIFEST_SELFTEST=PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--transport", type=Path)
    parser.add_argument("--config90", type=Path)
    parser.add_argument("--fdt-cache", type=Path)
    parser.add_argument("--response-pins", type=Path)
    parser.add_argument("--a2-response-hex", dest="a2")
    parser.add_argument("--chip82-response-hex", dest="chip82")
    parser.add_argument("--otp-a6-response-hex", dest="otp")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.self_test:
        selftest()
        return 0
    try:
        generate(arguments)
    except (OSError, ValueError, TypeError) as error:
        print(f"GOODIX_MATERIAL_MANIFEST=FAIL: {error}")
        return 1
    print("GOODIX_MATERIAL_MANIFEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
