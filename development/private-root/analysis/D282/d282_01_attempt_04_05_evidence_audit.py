#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate and classify the sanitized D282/01 attempt-04/05 evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "ed94d33e1cf6a2387135598c58a27d6c1573ba13"
RUNS = {
    "04": {
        "directory": "D28201_ATTEMPT_04_20260910T202549Z_ed94d33e1",
        "operator.log": "b068b91f43211bb3d49eebbae59c2e417c02f20393782864a11c928b55de18a4",
        "summary.env": "3dbe8406f59606c1b46a9fd9275a7b2552bb3d5b3a0f255622acc7f7571c58ea",
        "phase_b_physical_finger": "RIGHT_INDEX_OPERATOR_ATTESTED",
    },
    "05": {
        "directory": "D28201_ATTEMPT_05_20260910T203511Z_ed94d33e1",
        "operator.log": "5ae54ea653e2882bffb4c11ed08b21f53ecb34214f4ea90a6a566bde51968f0c",
        "summary.env": "3dbe8406f59606c1b46a9fd9275a7b2552bb3d5b3a0f255622acc7f7571c58ea",
        "phase_b_physical_finger": "LEFT_INDEX_OPERATOR_ATTESTED",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def multienv(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for line in path.read_text().splitlines():
        key, value = line.split("=", 1)
        result[key].append(value)
    return dict(result)


def require_summary(values: dict[str, list[str]]) -> None:
    expected = {
        "D282_01_RESULT": "PASS_LIVE_PENDING_INDEPENDENT_REVIEW",
        "D282_01_BASELINE_SHA": BASELINE,
        "BIOMETRIC_ACTION_MAX": "3",
        "EXPECTED_PHYSICAL_CONTACT_COUNT_MAX": "10",
        "OPEN_EPOCH_COUNT": "4",
        "ACTION_ATTEMPT_COUNT": "3",
        "CONSUMED_BIOMETRIC_ACTION_COUNT": "3",
        "HOST_ONLY_DELETE_OPEN_EPOCH_COUNT": "1",
        "ENROLL_ACTION_COUNT": "1",
        "VERIFY_ACTION_COUNT": "2",
        "SAME_FINGER_MATCH_COUNT": "1",
        "DIFFERENT_FINGER_NO_MATCH_COUNT": "1",
        "ENROLLMENT_RETRY_CALLBACK_COUNT": "0",
        "EXTRA_ENROLLMENT_CONTACT_REQUESTED": "false",
        "EXTRA_ENROLLMENT_REARM_COUNT": "0",
        "SECOND_SENSOR_REACHING_ACTION_COUNT": "0",
        "OBSERVED_RETRY_COUNT": "0",
        "HIDDEN_REOPEN_COUNT": "0",
        "RESET_COUNT": "0",
        "CLEAR_HALT_COUNT": "0",
        "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT": "0",
        "TEMPLATE_INCLUDED_IN_EXPORT": "false",
        "PAM_IN_SCOPE": "false",
        "SERVICE_STATE_RESTORED": "true",
        "STAGING_REMOVED": "true",
        "SYSTEM_LIBFPRINT_UNCHANGED": "true",
        "RUN_RETURN_CODE": "0",
        "ROLLBACK_COMPLETE": "true",
        "PREEXISTING_STORAGE_UNCHANGED": "true",
        "REAL_USB_ENUMERATION_ATTEMPTED": "true",
        "REAL_SENSOR_ACCESSED": "true",
        "LIVE_EXECUTION_PERFORMED": "true",
        "STAGING_PROBE_EXECUTION_PERFORMED": "false",
    }
    duplicate_expected = {
        "AUTHORIZATION_CREDENTIAL_REQUIRED": ["false", "false"],
        "AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED": ["false", "false"],
    }
    if set(values) != set(expected) | set(duplicate_expected):
        raise ValueError("unexpected summary key set")
    for key, value in expected.items():
        if values[key] != [value]:
            raise ValueError(f"{key}: expected one {value}, got {values[key]}")
    for key, expected_values in duplicate_expected.items():
        if values[key] != expected_values:
            raise ValueError(f"{key}: unexpected historical duplicate values")


def audit_records(text: str) -> list[dict[str, str]]:
    marker = "GOODIX_D282_EPOCH_AUDIT "
    lines = [line.split(marker, 1)[1] for line in text.splitlines()
             if marker in line]
    if len(lines) < 4:
        raise ValueError("missing final audit block")
    records = []
    for line in lines[:4]:
        fields = {}
        for token in line.split():
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


def validate_audit(records: list[dict[str, str]]) -> None:
    if [record.get("action") for record in records] != [
            "FPI_DEVICE_ACTION_ENROLL", "FPI_DEVICE_ACTION_VERIFY",
            "FPI_DEVICE_ACTION_VERIFY", "FPI_DEVICE_ACTION_NONE"]:
        raise ValueError("unexpected final audit action order")
    safety = {
        "secure_retry": "0", "post_retry": "0", "reopen": "0",
        "reset": "0", "clear_halt": "0", "persistent": "0",
        "outstanding": "0", "drained": "1", "context_closed": "1",
    }
    require_fields(records[0], safety | {
        "attempts": "1", "rejected": "0", "consumed": "1", "tls": "1",
        "enroll_stages": "8", "enroll_rearm32": "7",
        "enroll_terminal": "1",
    })
    for record in records[1:3]:
        require_fields(record, safety | {
            "attempts": "1", "rejected": "0", "consumed": "1", "tls": "1",
            "first_image": "1", "rearm32": "0", "enroll_stages": "0",
            "enroll_rearm32": "0", "enroll_terminal": "0",
        })
        pair = (record["release_tail"], record["single_terminal"])
        if pair not in {("0", "0"), ("1", "1")}:
            raise ValueError(f"incoherent verify close pair: {pair}")
    require_fields(records[3], safety | {
        "attempts": "0", "rejected": "0", "consumed": "0", "tls": "0",
        "first_image": "0", "release_tail": "0", "single_terminal": "0",
        "rearm32": "0", "enroll_stages": "0", "enroll_rearm32": "0",
        "enroll_terminal": "0", "real_submit": "0",
    })


def main() -> None:
    result = {"outcome": "PASS_EVIDENCE_CLASSIFICATION", "runs": {}}
    for attempt, metadata in RUNS.items():
        capture = (ROOT / "captures/D282_01" / metadata["directory"] /
                   "sanitized")
        for name in ("operator.log", "summary.env"):
            if sha256(capture / name) != metadata[name]:
                raise SystemExit(f"attempt {attempt} {name} digest mismatch")
        summary = multienv(capture / "summary.env")
        require_summary(summary)
        operator_text = (capture / "operator.log").read_text()
        records = audit_records(operator_text)
        validate_audit(records)
        client_results = Counter(
            line for line in operator_text.splitlines()
            if line.startswith(("Enroll result:", "Verify result:")))
        if client_results != Counter({
                "Enroll result: enroll-stage-passed": 7,
                "Enroll result: enroll-completed": 1,
                "Verify result: verify-match (done)": 1,
                "Verify result: verify-no-match (done)": 1}):
            raise SystemExit(f"attempt {attempt} unexpected client results")
        result["runs"][attempt] = {
            "baseline": BASELINE,
            "phase_b_physical_finger": metadata["phase_b_physical_finger"],
            "audit_actions": [record["action"] for record in records],
            "real_submit_counts": [int(record["real_submit"])
                                   for record in records],
            "summary_duplicate_keys": sorted(
                key for key, values in summary.items() if len(values) > 1),
            "rollback_complete": True,
            "different_finger_claim": (
                "NOT_APPLICABLE" if attempt == "04" else
                "PASS_OPERATOR_ATTESTED_STIMULUS"),
            "same_finger_second_verify_false_non_match_observed": attempt == "04",
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
