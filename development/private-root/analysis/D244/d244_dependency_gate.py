"""Fail-closed integrity gate for D244 historical live evidence."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
REPORTS = {
    "analysis/D242/D242_operator_live_stdout.json": (
        "1d9c2c736a2b8939855a184e350ea2ecaa914921536ae2a2d616130a166eb7e7",
        "d242-live-tls-single-shot-result-v1",
    ),
    "analysis/D243/D243_operator_live_stdout.json": (
        "a82c43f4aba5c6f9dcfe072eee7b8b6ab0edc7f621961ea6a322dfe6ac45aa23",
        "d243-live-tls-single-shot-result-v1",
    ),
}
REQUIRED = {
    "execution_mode": "live_single_shot",
    "attempted_phase": "E4",
    "command_count": 1,
    "usb_open_count": 1,
    "runtime_psk_e4_binding_status": "not_reached",
    "tls_handshake_count": 0,
    "retry_count": 0,
    "cleanup_count": 1,
    "secret_zeroized": True,
    "source_seal_state": "sealed",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_dependencies() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for relative, (expected_hash, expected_schema) in REPORTS.items():
        path = REPOSITORY / relative
        status = path.stat()
        if not stat.S_ISREG(status.st_mode):
            raise RuntimeError(f"D244_LIVE_REPORT_NOT_REGULAR:{relative}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise RuntimeError(f"D244_LIVE_REPORT_HASH_MISMATCH:{relative}")
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("schema") != expected_schema or any(
            report.get(key) != value for key, value in REQUIRED.items()
        ):
            raise RuntimeError(f"D244_LIVE_REPORT_SCHEMA_OR_FIELD_MISMATCH:{relative}")
        rows.append(
            {
                "path": relative,
                "sha256": actual_hash,
                "schema": report["schema"],
                "status": "PRIMARY_LOCAL_EVIDENCE_VERIFIED",
            }
        )
    return {
        "status": "PASS",
        "report_count": len(rows),
        "reports": rows,
        "D244_D242_LIVE_REPORT_STATUS": "PRIMARY_LOCAL_EVIDENCE_VERIFIED",
        "D244_D243_LIVE_REPORT_STATUS": "PRIMARY_LOCAL_EVIDENCE_VERIFIED",
    }
