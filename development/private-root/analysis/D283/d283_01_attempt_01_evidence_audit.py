#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate the hash-pinned, sanitized D283/01 Attempt 01 evidence."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


EXPECTED_HASHES = {
    "operator.log": "bf42acfb2e0ee849ea4554cb9b3ee29c7b2f9cceb4d4ba2bc44ad40736e4597a",
    "summary.env": "6b472c31960051b7562880bfc08abc54eafba4f77d138316a240e8a3079a74c1",
    "terminal-transcript.log": "86e819f4e5221f76805b297704a58162a89aed644ed3685ce05e9b9856481ff1",
}
BASELINE = "2cf82fd1fdb613cc44c997c4f1df74f582dfc376"
EPOCH_MARKER = "GOODIX_D282_EPOCH_AUDIT "
EXTRACT_MARKER = "GOODIX_SIGFM_EXTRACT_AUDIT "
MATCH_MARKER = "GOODIX_SIGFM_MATCH_AUDIT "


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: malformed environment line")
        key, value = line.split("=", 1)
        if not key or key in result:
            raise ValueError(f"{path}:{line_number}: empty or duplicate key {key!r}")
        result[key] = value
    return result


def fields_after(line: str, marker: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in line.split(marker, 1)[1].split():
        if "=" not in token:
            raise ValueError(f"malformed token after {marker!r}: {token!r}")
        key, value = token.split("=", 1)
        if key in result:
            raise ValueError(f"duplicate {marker.strip()} field {key}")
        result[key] = value
    return result


def unique_records(lines: list[str], marker: str) -> list[dict[str, str]]:
    payloads = sorted({line.split(marker, 1)[1] for line in lines if marker in line})
    return [fields_after(marker + payload, marker) for payload in payloads]


def require_fields(actual: dict[str, str], expected: dict[str, str], label: str) -> None:
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ValueError(
                f"{label}: {key} expected {value!r}, got {actual.get(key)!r}")


def audit_capture(capture: Path, enforce_hashes: bool = True) -> None:
    paths = {name: capture / name for name in EXPECTED_HASHES}
    for name, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"{name}: missing, non-file, or symlink")
        if enforce_hashes:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != EXPECTED_HASHES[name]:
                raise ValueError(f"{name}: SHA-256 mismatch")

    summary = read_env(paths["summary.env"])
    require_fields(summary, {
        "D283_01_RESULT": "PASS_LIVE_PENDING_INDEPENDENT_REVIEW",
        "D283_01_BASELINE_SHA": BASELINE,
        "D283_01_PAM_SERVICE": "goodix-d283-01",
        "D283_01_PAM_MAX_TRIES": "1",
        "D283_01_PAM_AUTHENTICATE_RETURN_CODE": "0",
        "D283_01_REAL_LOGIN_IN_SCOPE": "false",
        "D283_01_SUDO_BIOMETRIC_AUTHENTICATION_IN_SCOPE": "false",
        "BIOMETRIC_ACTION_MAX": "2",
        "EXPECTED_PHYSICAL_CONTACT_COUNT_MAX": "9",
        "TARGET_PRECONSUMPTION_MATCH_COUNT": "1",
        "TARGET_POSTSTART_MATCH_COUNT": "1",
        "OPEN_EPOCH_COUNT": "3",
        "CONSUMED_BIOMETRIC_ACTION_COUNT": "2",
        "ENROLL_ACTION_COUNT": "1",
        "VERIFY_ACTION_COUNT": "1",
        "HOST_ONLY_DELETE_OPEN_EPOCH_COUNT": "1",
        "OBSERVED_RETRY_COUNT": "0",
        "HIDDEN_REOPEN_COUNT": "0",
        "RESET_COUNT": "0",
        "CLEAR_HALT_COUNT": "0",
        "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT": "0",
        "SIGFM_EXTRACT_AUDIT_COUNT": "9",
        "SIGFM_MATCH_OUTCOME": "match",
        "SIGFM_MATCH_OBSERVED_MAX_SCORE": "1116",
        "SIGFM_MATCHED_SAMPLE": "1",
        "SIGFM_COMPARISON_COUNT": "1",
        "SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE": "RESIDUAL_RISK",
        "TEMPLATE_INCLUDED_IN_EXPORT": "false",
        "SERVICE_STATE_RESTORED": "true",
        "STAGING_REMOVED": "true",
        "SYSTEM_LIBFPRINT_UNCHANGED": "true",
        "RUN_RETURN_CODE": "0",
        "AUTHORIZATION_CREDENTIAL_REQUIRED": "false",
        "AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED": "false",
        "ROLLBACK_COMPLETE": "true",
        "PREEXISTING_STORAGE_UNCHANGED": "true",
        "REAL_USB_ENUMERATION_ATTEMPTED": "true",
        "REAL_SENSOR_ACCESSED": "true",
        "LIVE_EXECUTION_PERFORMED": "true",
        "STAGING_PROBE_EXECUTION_PERFORMED": "false",
    }, "summary")
    if "D283_01_FAILURE_PHASE" in summary:
        raise ValueError("summary: success result must not retain a failure phase")

    operator_lines = paths["operator.log"].read_text().splitlines()
    if operator_lines.count("D283_01_FAILURE_PHASE=PRE_SENSOR_STAGING") != 1:
        raise ValueError("operator log: expected one legacy initialization marker")
    if any(line.startswith("D283_01_FAILURE_RETURN_CODE=") for line in operator_lines):
        raise ValueError("operator log: failure return code present in successful run")
    for marker in (
            "EXACT_LIBRARY_MAP_VERIFIED=true",
            "POST_RESTART_EXACT_LIBRARY_MAP_VERIFIED=true",
            "ENROLL_PHYSICAL_FINGER=RIGHT_INDEX",
            "ENROLL_OPERATOR_CONFIRMATION=DESTRO",
            "DAEMON_RESTART_COUNT=1",
            "D283_01_PAM_START_CONFDIR_RETURN_CODE=0",
            "D283_01_PAM_AUTHENTICATE_RETURN_CODE=0",
            "D283_01_PAM_END_RETURN_CODE=0"):
        if not any(marker in line for line in operator_lines):
            raise ValueError(f"operator log: missing {marker}")
    if sum(line == "Enroll result: enroll-stage-passed" for line in operator_lines) != 7:
        raise ValueError("operator log: expected seven intermediate enrollment stages")
    if operator_lines.count("Enroll result: enroll-completed") != 1:
        raise ValueError("operator log: expected one enrollment completion")
    if sum("Fingerprints of user <USER> deleted" in line for line in operator_lines) != 1:
        raise ValueError("operator log: isolated-template delete not observed once")

    epochs = unique_records(operator_lines, EPOCH_MARKER)
    if len(epochs) != 3:
        raise ValueError("operator log: expected three distinct open epochs")
    by_action = {epoch.get("action"): epoch for epoch in epochs}
    if set(by_action) != {
            "FPI_DEVICE_ACTION_ENROLL", "FPI_DEVICE_ACTION_VERIFY",
            "FPI_DEVICE_ACTION_NONE"}:
        raise ValueError("operator log: unexpected epoch action set")
    common = {
        "secure_retry": "0", "post_retry": "0", "reopen": "0",
        "reset": "0", "clear_halt": "0", "persistent": "0",
        "outstanding": "0", "drained": "1", "context_closed": "1",
    }
    require_fields(by_action["FPI_DEVICE_ACTION_ENROLL"], {
        **common, "attempts": "1", "rejected": "0", "consumed": "1",
        "tls": "1", "enroll_stages": "8", "enroll_rearm32": "7",
        "enroll_terminal": "1", "real_submit": "203",
    }, "enroll epoch")
    require_fields(by_action["FPI_DEVICE_ACTION_VERIFY"], {
        **common, "attempts": "1", "rejected": "0", "consumed": "1",
        "tls": "1", "first_image": "1", "rearm32": "0",
        "real_submit": "75",
    }, "verify epoch")
    require_fields(by_action["FPI_DEVICE_ACTION_NONE"], {
        **common, "attempts": "0", "rejected": "0", "consumed": "0",
        "tls": "0", "real_submit": "0",
    }, "delete epoch")

    extracts = unique_records(operator_lines, EXTRACT_MARKER)
    if len(extracts) != 9 or any(int(item.get("keypoints", "0")) <= 0 for item in extracts):
        raise ValueError("operator log: expected nine positive SIGFM extractions")
    matcher = unique_records(operator_lines, MATCH_MARKER)
    if len(matcher) != 3:
        raise ValueError("operator log: expected start, comparison, and outcome records")
    events = {record.get("event"): record for record in matcher}
    if set(events) != {"start", "comparison", "outcome"}:
        raise ValueError("operator log: unexpected matcher event set")
    require_fields(events["start"], {"template_samples": "8", "threshold": "40"},
                   "matcher start")
    require_fields(events["comparison"], {
        "sample": "1", "score": "1116", "threshold": "40"},
        "matcher comparison")
    require_fields(events["outcome"], {
        "result": "match", "matched_sample": "1", "comparisons": "1",
        "threshold": "40"}, "matcher outcome")

    transcript = paths["terminal-transcript.log"].read_text()
    for marker in (
            "PHASE_A=Enrollment indice destro",
            "PHASE_B=PAM dedicato",
            "PHASE_C=Delete del solo template D283 isolato.",
            "D283_01_PAM_START_CONFDIR_RETURN_CODE=0",
            "D283_01_PAM_AUTHENTICATE_RETURN_CODE=0",
            "D283_01_PAM_END_RETURN_CODE=0",
            "RISULTATI=/var/tmp/goodix-d283-01-results/"):
        if marker not in transcript:
            raise ValueError(f"terminal transcript: missing {marker}")
    if "D283_01_GATE_REFUSED=true" in transcript or "D283_01_REFUSAL_REASON=" in transcript:
        raise ValueError("terminal transcript: gate refusal present")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    audit_capture(args.capture)
    print("D283_01_ATTEMPT_01_EVIDENCE_AUDIT=PASS_HASH_PINNED")
    print("D283_01_LEGACY_FAILURE_PHASE_MARKER=INITIALIZATION_ONLY_NORMALIZED")


if __name__ == "__main__":
    main()
