"""Fail-closed integrity gate for D243's historical runtime dependencies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
DEPENDENCIES = {
    "analysis/D241/d241_operator_dry_run.py": (
        "0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f",
        "synthetic USB/TLS fixtures",
    ),
    "analysis/D241/d241_preflight.py": (
        "6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7",
        "reviewed protected-input and OS preflight",
    ),
    "analysis/D242/D242_operator_live_stdout.json": (
        "1d9c2c736a2b8939855a184e350ea2ecaa914921536ae2a2d616130a166eb7e7",
        "primary local D242 live evidence",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_dependencies() -> dict[str, object]:
    rows = []
    for relative, (expected, purpose) in DEPENDENCIES.items():
        path = REPOSITORY / relative
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"D243_DEPENDENCY_HASH_MISMATCH:{relative}")
        rows.append(
            {
                "path": relative,
                "purpose": purpose,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "status": "MATCH",
            }
        )
    live = json.loads(
        (REPOSITORY / "analysis/D242/D242_operator_live_stdout.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "schema": "d242-live-tls-single-shot-result-v1",
        "execution_mode": "live_single_shot",
        "attempted_phase": "E4",
        "command_count": 1,
        "usb_open_count": 1,
        "cleanup_count": 1,
        "secret_zeroized": True,
        "source_seal_state": "sealed",
    }
    if any(live.get(key) != value for key, value in required.items()):
        raise RuntimeError("D243_D242_LIVE_REPORT_SCHEMA_OR_FIELD_MISMATCH")
    return {
        "status": "PASS",
        "dependency_count": len(rows),
        "unpinned_dependency_count": 0,
        "dependencies": rows,
        "d242_live_report_status": "PRIMARY_LOCAL_EVIDENCE_VERIFIED",
    }

