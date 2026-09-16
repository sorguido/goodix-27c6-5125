#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate and classify the sanitized D282/01 attempt-03 evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "captures/D282_01/D28201_ATTEMPT_03_42903b70/sanitized"
EXPECTED_HASHES = {
    "operator.log": "f9751a16cd6985adad69e4013b40a9a02c5df212d16375a08c0e0feeab81e291",
    "summary.env": "84edc196d617ced362eff4b3bd7ae598bbd42e3002efb9dfdfc896a80d8cc459",
    "phase-a-audit.raw": "36cb1223a8a0de4b6491933929a1ce239da9f40862b8b0b395bbf2c8d420c12a",
}


def env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, value = line.split("=", 1)
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def audit_records(path: Path) -> list[dict[str, str]]:
    records = []
    for line in path.read_text().splitlines():
        marker = "GOODIX_D282_EPOCH_AUDIT "
        if line.count(marker) != 1:
            raise ValueError("invalid audit marker cardinality")
        fields = {}
        for token in line.split(marker, 1)[1].split():
            key, value = token.split("=", 1)
            if key in fields:
                raise ValueError(f"duplicate audit field: {key}")
            fields[key] = value
        records.append(fields)
    return records


def require_fields(record: dict[str, str], expected: dict[str, str]) -> None:
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError(f"{key}: expected {value}, got {record.get(key)}")


def main() -> None:
    observed_hashes = {
        name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
        for name in EXPECTED_HASHES
    }
    if observed_hashes != EXPECTED_HASHES:
        raise SystemExit("capture digest mismatch")

    summary = env(CAPTURE / "summary.env")
    require_fields(summary, {
        "D282_01_RESULT": "FAIL_ACTION_OR_AUDIT",
        "D282_01_BASELINE_SHA": "42903b70c89b2399bef35f4a4c7eb8c9dc5d04e5",
        "TARGET_PRECONSUMPTION_MATCH_COUNT": "1",
        "SERVICE_STATE_RESTORED": "true",
        "STAGING_REMOVED": "true",
        "SYSTEM_LIBFPRINT_UNCHANGED": "true",
        "RUN_RETURN_CODE": "1",
        "ROLLBACK_COMPLETE": "true",
        "PREEXISTING_STORAGE_UNCHANGED": "true",
        "REAL_SENSOR_ACCESSED": "true",
        "LIVE_EXECUTION_PERFORMED": "true",
        "RETRY_AUTHORIZED": "false",
    })

    if (CAPTURE / "operator.log").read_text().splitlines() != [
        "EXACT_LIBRARY_MAP_VERIFIED=true",
        "DAEMON_RESTART_COUNT=1",
    ]:
        raise SystemExit("unexpected operator.log")

    records = audit_records(CAPTURE / "phase-a-audit.raw")
    if len(records) != 2:
        raise SystemExit("expected exactly two Phase-A epochs")
    enroll, verify = records
    common = {
        "attempts": "1", "rejected": "0", "consumed": "1", "tls": "1",
        "secure_retry": "0", "post_retry": "0", "reopen": "0",
        "reset": "0", "clear_halt": "0", "persistent": "0",
        "outstanding": "0", "drained": "1", "context_closed": "1",
    }
    require_fields(enroll, common | {
        "action": "FPI_DEVICE_ACTION_ENROLL", "first_image": "0",
        "release_tail": "0", "single_terminal": "0", "rearm32": "0",
        "enroll_stages": "8", "enroll_rearm32": "7",
        "enroll_terminal": "1", "real_submit": "203",
    })
    require_fields(verify, common | {
        "action": "FPI_DEVICE_ACTION_VERIFY", "first_image": "1",
        "release_tail": "0", "single_terminal": "0", "rearm32": "0",
        "enroll_stages": "0", "enroll_rearm32": "0",
        "enroll_terminal": "0", "real_submit": "76",
    })

    result = {
        "outcome": "PASS_EVIDENCE_CLASSIFICATION",
        "baseline": summary["D282_01_BASELINE_SHA"],
        "phase_a_epoch_count": len(records),
        "enroll_epoch": enroll,
        "verify_epoch": verify,
        "total_real_submit_count": sum(int(r["real_submit"]) for r in records),
        "exact_failed_assert":
            "VERIFY_RELEASE_TAIL_1_SINGLE_TERMINAL_1_EXPECTED_ACTUAL_0_0",
        "phase_b_started": False,
        "different_finger_sensor_acquisition_count": 0,
        "rollback_complete": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
