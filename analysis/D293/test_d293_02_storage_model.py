#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Content-free executable model of fprintd's user/driver/device/finger tree."""

from pathlib import Path
from tempfile import TemporaryDirectory


DRIVER = "goodix_27c6_5125"
DEVICE = "0"


def finger_path(root: Path, user: str, finger: str) -> Path:
    assert user and "/" not in user and finger in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "a"}
    return root / user / DRIVER / DEVICE / finger


def store(root: Path, user: str, finger: str, token: bytes) -> None:
    path = finger_path(root, user, finger)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(token)


def load(root: Path, user: str) -> dict[str, bytes]:
    base = root / user / DRIVER / DEVICE
    if not base.is_dir():
        return {}
    return {entry.name: entry.read_bytes() for entry in base.iterdir() if entry.is_file()}


def main() -> None:
    with TemporaryDirectory(prefix="d293-storage-model-") as temp:
        root = Path(temp)
        store(root, "alice", "2", b"alice-left-index-v1")
        store(root, "alice", "7", b"alice-right-index")
        store(root, "bob", "2", b"bob-left-index")

        # Restart is represented by reconstructing state only from the tree.
        assert set(load(root, "alice")) == {"2", "7"}
        assert set(load(root, "bob")) == {"2"}
        assert load(root, "alice")["2"] != load(root, "bob")["2"]

        # Same user/finger replaces exactly that leaf; other principals/fingers survive.
        store(root, "alice", "2", b"alice-left-index-v2")
        assert load(root, "alice") == {
            "2": b"alice-left-index-v2",
            "7": b"alice-right-index",
        }
        assert load(root, "bob") == {"2": b"bob-left-index"}

        finger_path(root, "alice", "7").unlink()
        assert set(load(root, "alice")) == {"2"}

        # fprintd has no account-delete hook: stale data would bind to name reuse.
        assert load(root, "bob") == {"2": b"bob-left-index"}
        for leaf in list((root / "bob" / DRIVER / DEVICE).iterdir()):
            leaf.unlink()
        assert load(root, "bob") == {}
        store(root, "bob", "2", b"new-account-new-print")
        assert load(root, "bob") == {"2": b"new-account-new-print"}

    print("D293_02_STORAGE_MODEL=PASS")
    print("PRINCIPAL_COUNT=2")
    print("MULTI_FINGER_COUNT=2")
    print("RESTART_RELOAD=PASS")
    print("REPLACE_DELETE_NAME_REUSE=PASS")
    print("REAL_BIOMETRIC_CONTENT=0")


if __name__ == "__main__":
    main()
