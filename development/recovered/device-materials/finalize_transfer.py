#!/usr/bin/env python3
"""D192 root-only transfer -> v1 finalizer with a closed production CLI."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
from typing import Callable

from tools.binding_reference.crypto_reference import bind
from tools.binding_reference.pe_parser import extract_seeds_from_bytes
from tools.transfer_record import RECORD_LENGTH, parse

V1_MAGIC = b"G5125POC"
V1_LENGTH = 88
PE_MIN_SIZE = 65536
PE_MAX_SIZE = 32 * 1024 * 1024
CANONICAL_STORE = Path("/var/lib/goodix-5125-poc")
STORE_FILE = "transport-material.bin"
CANONICAL_IMPORTER = Path(__file__).resolve().parents[1] / "build" / "goodix5125-import"


@dataclass(frozen=True)
class _Policy:
    importer: Path
    store: Path
    owner: int
    require_root: bool = True
    test_root_arg: bool = False


def _zero(value: bytearray | None) -> None:
    if value is not None:
        value[:] = bytes(len(value))


def _absolute(path: Path, label: str) -> Path:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise ValueError(f"{label} must be a normalized absolute path")
    return path


def _open_regular(path: Path, *, owner: int | None = None, mode: int | None = None,
                  exact_size: int | None = None, min_size: int | None = None,
                  max_size: int | None = None, executable: bool = False) -> tuple[int, os.stat_result]:
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
             getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError("regular file required")
        if owner is not None and info.st_uid != owner:
            raise PermissionError("file owner rejected")
        if mode is not None and stat.S_IMODE(info.st_mode) != mode:
            raise PermissionError("file mode rejected")
        if exact_size is not None and info.st_size != exact_size:
            raise ValueError("file size rejected")
        if min_size is not None and info.st_size < min_size:
            raise ValueError("file below size bound")
        if max_size is not None and info.st_size > max_size:
            raise ValueError("file above size bound")
        if executable:
            permissions = stat.S_IMODE(info.st_mode)
            if permissions & 0o022 or not permissions & stat.S_IXUSR:
                raise PermissionError("importer permissions rejected")
        return fd, info
    except BaseException:
        os.close(fd)
        raise


def _read_fd(fd: int, size: int) -> bytearray:
    os.lseek(fd, 0, os.SEEK_SET)
    data = bytearray()
    while len(data) < size:
        chunk = os.read(fd, size - len(data))
        if not chunk:
            raise ValueError("short file rejected")
        data.extend(chunk)
    if os.read(fd, 1):
        raise ValueError("trailing bytes rejected")
    return data


def _read_transfer(path: Path, owner: int) -> bytearray:
    fd, _ = _open_regular(path, owner=owner, mode=0o600, exact_size=RECORD_LENGTH)
    try:
        return _read_fd(fd, RECORD_LENGTH)
    finally:
        os.close(fd)


def _read_pe_once(path: Path, after_open: Callable[[], None] | None = None) -> bytearray:
    fd, info = _open_regular(path, min_size=PE_MIN_SIZE, max_size=PE_MAX_SIZE)
    try:
        if after_open is not None:
            after_open()
        return _read_fd(fd, info.st_size)
    finally:
        os.close(fd)


def _v1(secret: bytearray, validator: bytes) -> bytearray:
    if len(secret) != 32 or len(validator) != 32:
        raise ValueError("v1 fields must be exactly 32 bytes")
    return bytearray(struct.pack("<8sHHHHHHHH", V1_MAGIC, 1, 24, 0x27C6,
                                 0x5125, 1, 32, 32, 0) + secret + validator)


def _execute_fd(fd: int, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    executable = f"/proc/self/fd/{fd}"
    if not Path("/proc/self/fd").is_dir():
        raise RuntimeError("open-fd execution requires Linux procfs")
    return subprocess.run([executable, *arguments], pass_fds=(fd,), check=True,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True)


def _verify_store(expected: bytearray, policy: _Policy, importer_fd: int) -> None:
    directory_fd = os.open(policy.store, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                           getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        directory_info = os.fstat(directory_fd)
        if (not stat.S_ISDIR(directory_info.st_mode) or directory_info.st_uid != policy.owner or
                stat.S_IMODE(directory_info.st_mode) != 0o700):
            raise PermissionError("store directory metadata rejected")
        fd = os.open(STORE_FILE, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
                     getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                     dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != policy.owner or
                    stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != V1_LENGTH):
                raise PermissionError("store file metadata rejected")
            actual = _read_fd(fd, V1_LENGTH)
            try:
                if not hmac.compare_digest(actual, expected):
                    raise ValueError("store bytes differ from in-memory v1")
                if hashlib.sha256(actual).digest() != hashlib.sha256(expected).digest():
                    raise ValueError("store v1 hash mismatch")
            finally:
                _zero(actual)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    verify_args = ["--verify-store"]
    if policy.test_root_arg:
        verify_args += ["--test-root", str(policy.store)]
    _execute_fd(importer_fd, verify_args)


def _finalize(transfer_path: Path, pe_bytes: bytearray, remove_after: bool,
              policy: _Policy, after_import: Callable[[], None] | None = None,
              seed_extractor: Callable[[bytes | bytearray], tuple[bytearray, bytearray]] = extract_seeds_from_bytes) -> tuple[str, str]:
    if policy.require_root and os.geteuid() != 0:
        raise PermissionError("finalizer requires root")
    transfer_path = _absolute(transfer_path, "transfer")
    importer_path = _absolute(policy.importer, "canonical importer")
    importer_fd, _ = _open_regular(importer_path, owner=policy.owner, executable=True)
    record = secret = v1 = validator = envelope = None
    staging_name: str | None = None
    completed = False
    transfer_acquired = False
    try:
        record = _read_transfer(transfer_path, policy.owner)
        transfer_acquired = True
        transfer_hash = hashlib.sha256(record).hexdigest()
        secret = parse(record)
        seeds = seed_extractor(pe_bytes)
        try:
            result = bind(bytes(secret), bytes(seeds[0]), bytes(seeds[1]))
        finally:
            _zero(seeds[0]); _zero(seeds[1])
        validator = bytearray(result["validator"])
        envelope = bytearray(result["envelope"])
        v1 = _v1(secret, validator)
        v1_hash = hashlib.sha256(v1).hexdigest()
        fd, staging_name = tempfile.mkstemp(prefix=".goodix5125-v1-", dir=transfer_path.parent)
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(v1)
            while view:
                count = os.write(fd, view)
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        import_args = []
        if policy.test_root_arg:
            import_args += ["--test-root", str(policy.store)]
        import_args.append(staging_name)
        _execute_fd(importer_fd, import_args)
        if after_import is not None:
            after_import()
        _verify_store(v1, policy, importer_fd)
        completed = True
        if remove_after:
            os.unlink(transfer_path)
            parent_fd = os.open(transfer_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        return transfer_hash, v1_hash
    finally:
        os.close(importer_fd)
        if staging_name is not None:
            try:
                os.unlink(staging_name)
            except FileNotFoundError:
                pass
        _zero(envelope); _zero(validator); _zero(v1); _zero(secret); _zero(record)
        if transfer_acquired and not completed and not transfer_path.exists():
            raise RuntimeError("fail-closed invariant violated: transfer removed before verified success")


def main() -> int:
    parser = argparse.ArgumentParser(prog="goodix5125-finalize-transfer")
    parser.add_argument("--transfer", required=True, type=Path)
    parser.add_argument("--oem-pe", required=True, type=Path)
    parser.add_argument("--import", dest="do_import", action="store_true", required=True)
    parser.add_argument("--remove-transfer-after-success", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("STOP: finalizer requires root")
    transfer = _absolute(args.transfer, "transfer")
    pe_path = _absolute(args.oem_pe, "oem-pe")
    pe_data = _read_pe_once(pe_path)
    try:
        transfer_hash, v1_hash = _finalize(
            transfer, pe_data, args.remove_transfer_after_success,
            _Policy(CANONICAL_IMPORTER, CANONICAL_STORE, 0),
        )
    finally:
        _zero(pe_data)
    print(f"finalization completed: transfer_sha256={transfer_hash} v1_sha256={v1_hash}")
    if args.remove_transfer_after_success:
        print("transfer staging removed after exact store verification; SSD physical erasure is not guaranteed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
