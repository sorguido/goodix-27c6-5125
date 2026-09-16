#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Authorized one-shot ATTEMPT02 aggregate evaluator.

This entrypoint is intentionally fixed to one capture and one production
transport-material location. It has no USB code and writes only aggregate NBIS
metrics. The surrounding launcher validates and consumes the one-shot grant
before invoking it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path


OPERATION = "D279_35_ONE_OFFLINE_PROTECTED_EVALUATION"
TRANSPORT_DIRECTORY = Path("/var/lib/goodix-5125-poc")
TRANSPORT_NAME = "transport-material.bin"
TRANSPORT_LENGTH = 88
TRANSPORT_SHA256 = "eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75"
PSK_OFFSET = 24
PSK_LENGTH = 32
CAPTURE_SHA256 = "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"


class ProtectedEvaluationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtectedEvaluationError(message)


def cleanse(buffer: bytearray | None) -> None:
    if buffer is not None:
        buffer[:] = b"\x00" * len(buffer)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"{name}_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_transport_psk(
    directory: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_hash: str,
) -> tuple[bytearray, bytearray]:
    """Read one exact transport file using openat and return owned buffers."""

    directory_fd = file_fd = -1
    transport = bytearray(TRANSPORT_LENGTH)
    psk = None
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        directory_status = os.fstat(directory_fd)
        require(stat.S_ISDIR(directory_status.st_mode), "TRANSPORT_DIRECTORY_TYPE")
        require(directory_status.st_uid == expected_uid and
                directory_status.st_gid == expected_gid,
                "TRANSPORT_DIRECTORY_OWNER")
        require(stat.S_IMODE(directory_status.st_mode) == 0o700,
                "TRANSPORT_DIRECTORY_MODE")

        file_fd = os.open(
            TRANSPORT_NAME,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        file_status = os.fstat(file_fd)
        require(stat.S_ISREG(file_status.st_mode), "TRANSPORT_FILE_TYPE")
        require(file_status.st_uid == expected_uid and file_status.st_gid == expected_gid,
                "TRANSPORT_FILE_OWNER")
        require(stat.S_IMODE(file_status.st_mode) == 0o600,
                "TRANSPORT_FILE_MODE")
        require(file_status.st_size == TRANSPORT_LENGTH, "TRANSPORT_FILE_LENGTH")

        with os.fdopen(file_fd, "rb", buffering=0, closefd=False) as stream:
            require(stream.readinto(transport) == TRANSPORT_LENGTH,
                    "TRANSPORT_FILE_SHORT_READ")
            require(stream.read(1) == b"", "TRANSPORT_FILE_LONG_READ")
        require(hashlib.sha256(transport).hexdigest() == expected_hash,
                "TRANSPORT_FILE_HASH")
        after = os.fstat(file_fd)
        require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) ==
                (file_status.st_dev, file_status.st_ino, file_status.st_size,
                 file_status.st_mtime_ns),
                "TRANSPORT_FILE_CHANGED")
        psk = bytearray(transport[PSK_OFFSET:PSK_OFFSET + PSK_LENGTH])
        require(len(psk) == PSK_LENGTH, "PSK_LENGTH")
        return transport, psk
    except Exception:
        cleanse(transport)
        cleanse(psk)
        raise
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def write_aggregate(path: Path, result: dict) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def evaluate(args) -> None:
    require(os.geteuid() == 0, "ROOT_REQUIRED_FOR_PROTECTED_READ")
    require(os.environ.get("D279_35_AUTHORIZED_OPERATION") == OPERATION,
            "AUTHORIZED_OPERATION_ENV_MISSING")
    require(os.environ.get("D279_35_AUTHORIZED_SHA") == args.baseline,
            "AUTHORIZED_SHA_ENV_MISMATCH")
    require(len(args.baseline) == 40 and
            all(character in "0123456789abcdef" for character in args.baseline),
            "BASELINE_SHA")
    require(args.capture.is_file() and not args.capture.is_symlink(), "CAPTURE_FILE")
    require(hashlib.sha256(args.capture.read_bytes()).hexdigest() == CAPTURE_SHA256,
            "CAPTURE_HASH")
    require(args.nbis_helper.is_file() and not args.nbis_helper.is_symlink(),
            "NBIS_HELPER_FILE")
    require(not args.output.exists(), "OUTPUT_COLLISION")

    snapshot_root = Path(__file__).resolve().parents[2]
    d33 = load_module(
        "d279_35_d33",
        snapshot_root / "analysis/D279/d279_33_attempt02_in_memory_composer.py",
    )
    d34 = load_module(
        "d279_35_d34",
        snapshot_root / "analysis/D279/d279_34_exact_nbis_variant_evaluator.py",
    )
    transport = psk = None
    try:
        transport, psk = read_transport_psk(
            TRANSPORT_DIRECTORY,
            expected_uid=0,
            expected_gid=0,
            expected_hash=TRANSPORT_SHA256,
        )
        cleanse(transport)
        with d33.decrypt_target_attempt(psk, args.capture) as attempt:
            with d34.ExactNbisPipe(args.nbis_helper) as runner:
                aggregate = d34.evaluate_target_attempt(attempt.rasters, runner)
        output = {
            "schema": "D279_35_ONE_OFFLINE_PROTECTED_EVALUATION_V1",
            "outcome": "AUTHENTIC_AGGREGATE_READY",
            "baseline_sha": args.baseline,
            "operation": OPERATION,
            "capture_sha256": CAPTURE_SHA256,
            "transport_input_verified": True,
            "transport_or_psk_exported": False,
            "plaintext_or_raster_exported": False,
            "template_exported": False,
            "live_or_usb_action_count": 0,
            "aggregate": aggregate,
        }
        write_aggregate(args.output, output)
    finally:
        cleanse(psk)
        cleanse(transport)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--nbis-helper", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        evaluate(args)
        print("OUTCOME=AUTHENTIC_AGGREGATE_READY")
        print("TARGET_PSK_ACCESSED=true")
        print("PSK_EXPORTED=false")
        print("RASTER_OR_TEMPLATE_EXPORTED=false")
        print("LIVE_OR_USB_ACTION_COUNT=0")
        return 0
    except (ProtectedEvaluationError, OSError, ValueError, RuntimeError) as error:
        print("OUTCOME=FAIL_CLOSED")
        print(f"FAILURE_CLASS={type(error).__name__}:{error}")
        print("LIVE_OR_USB_ACTION_COUNT=0")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

