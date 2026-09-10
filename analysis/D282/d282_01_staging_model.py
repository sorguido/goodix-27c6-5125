#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline-only model of D282-owned staging and storage rollback."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil


OWNED_NAME = ".goodix-d282-01-model"


def manifest(root: Path) -> tuple[tuple[str, str, int, int, int], ...]:
    records: list[tuple[str, str, int, int, int]] = []
    if not root.exists():
        return tuple()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == OWNED_NAME:
            continue
        if path.is_symlink():
            raise RuntimeError(f"symlink refused: {relative}")
        stat = path.stat()
        digest = "DIR"
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append((str(relative), digest, stat.st_mode & 0o7777,
                        stat.st_uid, stat.st_gid))
    return tuple(records)


def stage(runtime_root: Path, unit_root: Path, storage_root: Path,
          fail_after: str | None = None) -> tuple[Path, Path, Path]:
    runtime = runtime_root / OWNED_NAME
    dropin = unit_root / "fprintd.service.d" / "90-goodix-d282-01.conf"
    storage = storage_root / OWNED_NAME
    for path in (runtime, storage):
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    (runtime / "libfprint-2.so.2.0.0").write_bytes(b"D282 synthetic library")
    if fail_after == "runtime":
        raise RuntimeError("injected runtime failure")
    dropin.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    dropin.write_text("[Service]\nExecStart=\nExecStart=/owned/wrapper\n")
    if fail_after == "dropin":
        raise RuntimeError("injected drop-in failure")
    (storage / "owned.fp3").write_bytes(b"FP3 synthetic non-biometric")
    if fail_after == "storage":
        raise RuntimeError("injected storage failure")
    return runtime, dropin, storage


def rollback(runtime_root: Path, unit_root: Path, storage_root: Path) -> None:
    targets = (
        runtime_root / OWNED_NAME,
        unit_root / "fprintd.service.d" / "90-goodix-d282-01.conf",
        storage_root / OWNED_NAME,
    )
    for target in targets:
        resolved_parent = target.parent.resolve()
        if OWNED_NAME not in target.name and target.name != "90-goodix-d282-01.conf":
            raise RuntimeError(f"unowned rollback target: {target}")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
        if target.name == "90-goodix-d282-01.conf":
            try:
                resolved_parent.rmdir()
            except OSError:
                pass


def assert_preserved(before: tuple, storage_root: Path) -> None:
    after = manifest(storage_root)
    if before != after:
        raise AssertionError((before, after))


def seed_preexisting(storage_root: Path) -> None:
    user = storage_root / "preexisting-user"
    user.mkdir(parents=True)
    os.chmod(user, 0o700)
    print_path = user / "right-thumb"
    print_path.write_bytes(b"FP3 preexisting synthetic sentinel")
    os.chmod(print_path, 0o600)
