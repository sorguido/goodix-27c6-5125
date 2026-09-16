#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Private, read-only fprint storage inventory for D282/01."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


def selinux_label(path: Path) -> str:
    try:
        return os.getxattr(path, "security.selinux", follow_symlinks=False).decode(
            "ascii", "strict").rstrip("\0")
    except OSError:
        return "UNAVAILABLE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--exclude-name")
    args = parser.parse_args()
    root = args.root
    records = []
    if root.is_symlink():
        raise SystemExit("REFUSED_SYMLINK_ROOT")
    if root.exists() and not root.is_dir():
        raise SystemExit("REFUSED_NON_DIRECTORY_ROOT")
    if root.exists():
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            directories[:] = sorted(
                item for item in directories
                if not (current_path == root and item == args.exclude_name))
            for name in directories + sorted(files):
                path = current_path / name
                relative = str(path.relative_to(root))
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise SystemExit(f"REFUSED_SYMLINK:{relative}")
                kind = "directory" if stat.S_ISDIR(info.st_mode) else "file"
                digest = None
                size = info.st_size
                if kind == "file":
                    hasher = hashlib.sha256()
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            hasher.update(chunk)
                    digest = hasher.hexdigest()
                records.append({
                    "path": relative,
                    "kind": kind,
                    "mode": oct(stat.S_IMODE(info.st_mode)),
                    "uid": info.st_uid,
                    "gid": info.st_gid,
                    "size": size,
                    "sha256": digest,
                    "selinux": selinux_label(path),
                })
    payload = {
        "schema": "goodix-d282-storage-inventory-v1",
        "root_existed": root.exists(),
        "root_mode": oct(stat.S_IMODE(root.stat().st_mode)) if root.exists() else None,
        "root_uid": root.stat().st_uid if root.exists() else None,
        "root_gid": root.stat().st_gid if root.exists() else None,
        "root_selinux": selinux_label(root) if root.exists() else None,
        "file_count": sum(item["kind"] == "file" for item in records),
        "top_level_entries": sorted({item["path"].split("/", 1)[0]
                                     for item in records}),
        "records": sorted(records, key=lambda item: item["path"]),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.write_text(encoded)
    os.chmod(args.output, 0o600)
    print(f"STORAGE_FILE_COUNT={payload['file_count']}")
    print(f"STORAGE_TOP_LEVEL_ENTRY_COUNT={len(payload['top_level_entries'])}")
    print(f"STORAGE_MANIFEST_SHA256={hashlib.sha256(encoded.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
