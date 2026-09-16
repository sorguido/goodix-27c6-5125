"""Fail-closed integrity gate for D242's behavior-relevant D241 imports."""

from __future__ import annotations

import hashlib
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
D241_BEHAVIOR_DEPENDENCIES = {
    "analysis/D241/d241_operator_dry_run.py": {
        "imported_directly_or_indirectly": "directly_by_d242_operator_dry_run",
        "behavior_relevant": True,
        "sha256": "0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f",
        "pinned": True,
    },
    "analysis/D241/d241_preflight.py": {
        "imported_directly_or_indirectly": (
            "directly_by_d242_preflight_and_indirectly_via_d241_operator_dry_run"
        ),
        "behavior_relevant": True,
        "sha256": "6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7",
        "pinned": True,
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_d241_dependencies() -> dict[str, object]:
    manifest: list[dict[str, object]] = []
    for module_path, declaration in D241_BEHAVIOR_DEPENDENCIES.items():
        actual = sha256(REPOSITORY / module_path)
        expected = str(declaration["sha256"])
        if actual != expected:
            raise RuntimeError(f"D242_D241_DEPENDENCY_HASH_MISMATCH:{module_path}")
        manifest.append({"module_path": module_path, **declaration, "actual_sha256": actual})
    behavior_relevant_count = sum(
        bool(item["behavior_relevant"]) for item in D241_BEHAVIOR_DEPENDENCIES.values()
    )
    pinned_count = sum(
        bool(item["behavior_relevant"] and item["pinned"])
        for item in D241_BEHAVIOR_DEPENDENCIES.values()
    )
    return {
        "modules": manifest,
        "behavior_relevant_dependency_count": behavior_relevant_count,
        "pinned_dependency_count": pinned_count,
        "unpinned_closure_dependency_count": behavior_relevant_count - pinned_count,
        "status": "PASS",
    }
