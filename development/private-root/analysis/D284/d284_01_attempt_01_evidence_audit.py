#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate the hash-pinned D284/01 Attempt 01 evidence and live causality."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess


EXPECTED_HASHES = {
    "operator.log": "9c0cbe489f83a5a5ddd1bfaeb76249e884fab7f36056e8592d1b7913ff5c2b19",
    "summary.env": "66a2a3416b7b90d0e78e343b6a602bd9496020cf14393cf592cb2d181029200d",
    "terminal-transcript.log": "476549872552d132d2abc535af8ad7f774778612f80c63eff8ea742efc3f27ff",
}
BASELINE = "bc478f480be822c04ffc44ec9e7cd46420712f72"
ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = "operator_kit/d284-01-transient-sudo-pilot/run-d284-01.sh"
PAM_PATH = "operator_kit/d284-01-transient-sudo-pilot/goodix-d284-01-sudo.pam"
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


def git_show(path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{BASELINE}:{path}"],
        check=True, capture_output=True, text=True)
    return result.stdout


def audit_baseline_causality() -> None:
    subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{BASELINE}^{{commit}}"],
        check=True)
    script = git_show(SCRIPT_PATH)
    pam = git_show(PAM_PATH)
    required_pam = (
        "auth        sufficient                                   "
        "pam_fprintd.so max-tries=1 timeout=45",
        "auth        sufficient                                   pam_unix.so nullok",
        "auth        required                                     pam_deny.so",
    )
    if not all(line in pam for line in required_pam):
        raise ValueError("baseline PAM: fingerprint/fallback/deny contract drift")
    writer = "printf 'Defaults:%s pam_service=goodix-d284-01-sudo\\n'"
    if writer not in script:
        raise ValueError("baseline script: per-user sudo PAM selector missing")

    live = script[script.index("run_d284_live ()"):
                  script.index("export_d284_results ()")]
    ordered = (
        'install_d284_overrides "$user"',
        'runuser -u "$user" -- sudo -K',
        'runuser -u "$user" -- env -u SUDO_ASKPASS sudo -v',
        'grep GOODIX_SIGFM_MATCH_AUDIT "$live_private/pre-delete-journal.raw"',
        'runuser -u "$user" -- sudo -K',
        "remove_d284_overrides",
        'fprintd-delete "$user"',
    )
    position = -1
    for snippet in ordered:
        position = live.index(snippet, position + 1)
    for condition in (
            '[[ $action_rc -ne 0 ]]',
            "event=outcome result=match",
            "D284_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW"):
        if condition not in live:
            raise ValueError(f"baseline script: missing causal condition {condition}")

    operator = script[script.index("operator_d284_run ()"):
                      script.index("offline_cleanup_regression ()")]
    first_live = operator.index('--run-live "$prepared_candidate"')
    export_call = operator.index('--export-results "$result"')
    if first_live >= export_call or operator.count("sudo \"") < 2:
        raise ValueError("baseline script: live/export sudo invocation topology drift")


def audit_capture(capture: Path, enforce_hashes: bool = True) -> None:
    expected_names = set(EXPECTED_HASHES)
    actual_names = {item.name for item in capture.iterdir()}
    if actual_names != expected_names:
        raise ValueError(f"capture file set mismatch: {sorted(actual_names)}")
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
        "D284_01_RESULT": "PASS_LIVE_PENDING_INDEPENDENT_REVIEW",
        "D284_01_BASELINE_SHA": BASELINE,
        "D284_01_CONSUMER": "SUDO_VALIDATE",
        "D284_01_PAM_SERVICE": "goodix-d284-01-sudo",
        "D284_01_PAM_MAX_TRIES": "1",
        "D284_01_SUDO_VALIDATE_RETURN_CODE": "0",
        "D284_01_PASSWORD_FALLBACK_PRESENT": "true",
        "D284_01_AUTHSELECT_WRITE_COUNT": "0",
        "D284_01_EXISTING_PAM_FILE_WRITE_COUNT": "0",
        "D284_01_REAL_LOGIN_IN_SCOPE": "false",
        "D284_01_KDE_LOCK_SCREEN_IN_SCOPE": "false",
        "BIOMETRIC_ACTION_MAX": "2",
        "EXPECTED_PHYSICAL_CONTACT_COUNT_MAX": "9",
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
        "SIGFM_MATCH_OBSERVED_MAX_SCORE": "14858",
        "SIGFM_MATCHED_SAMPLE": "1",
        "SIGFM_COMPARISON_COUNT": "1",
        "TEMPLATE_INCLUDED_IN_EXPORT": "false",
        "SERVICE_CLEANUP_COMMANDS_SUCCEEDED": "true",
        "SERVICE_STATE_RESTORED": "true",
        "SERVICE_INITIAL_STATE": "active",
        "SERVICE_FINAL_STATE": "active",
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
        "RECOVERY_REQUIRED": "false",
        "D284_01_PAM_SUDOERS_ROLLBACK": "true",
        "D284_01_SUDO_TIMESTAMP_INVALIDATED": "true",
    }, "summary")
    if any(key.startswith("D284_01_FAILURE_") for key in summary):
        raise ValueError("summary: successful run contains a failure field")

    operator_lines = paths["operator.log"].read_text().splitlines()
    for marker in (
            "D284_01_PROGRESS_PHASE=PRE_SENSOR_STAGING",
            "ENROLL_OPERATOR_CONFIRMATION=DESTRO",
            "SUDO_OPERATOR_CONFIRMATION=INDICE_DESTRO",
            "D284_01_PAM_SUDOERS_REMOVED_BEFORE_DELETE=true"):
        if operator_lines.count(marker) != 1:
            raise ValueError(f"operator log: expected one {marker}")
    if any("D284_01_FAILURE_" in line for line in operator_lines):
        raise ValueError("operator log: failure marker present")
    if sum(line == "Enroll result: enroll-stage-passed" for line in operator_lines) != 7:
        raise ValueError("operator log: expected seven intermediate enrollment stages")
    if operator_lines.count("Enroll result: enroll-completed") != 1:
        raise ValueError("operator log: expected one enrollment completion")
    if sum("Fingerprints of user <USER> deleted" in line for line in operator_lines) != 1:
        raise ValueError("operator log: isolated template delete not observed once")

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
        "enroll_terminal": "1", "real_submit": "204",
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

    extract_lines = sorted({line for line in operator_lines if EXTRACT_MARKER in line})
    extracts = [fields_after(line, EXTRACT_MARKER) for line in extract_lines]
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
        "sample": "1", "score": "14858", "threshold": "40"},
        "matcher comparison")
    require_fields(events["outcome"], {
        "result": "match", "matched_sample": "1", "comparisons": "1",
        "threshold": "40"}, "matcher outcome")

    transcript = paths["terminal-transcript.log"].read_text()
    for marker in (
            "PHASE_A=Enrollment isolato indice destro: otto contatti.",
            "PHASE_B=Un solo sudo -v con impronta; non digitare password.",
            "PHASE_C=Delete del solo template isolato e rollback.",
            "RISULTATI=/var/tmp/goodix-d284-01-results/"):
        if marker not in transcript:
            raise ValueError(f"terminal transcript: missing {marker}")
    if transcript.count(": OK") != 6:
        raise ValueError("terminal transcript: expected six verified candidate artifacts")
    if transcript.count("Enroll result: enroll-stage-passed") != 7 or \
            transcript.count("Enroll result: enroll-completed") != 1:
        raise ValueError("terminal transcript: enrollment sequence mismatch")
    if "D284_01_GATE_REFUSED=true" in transcript or "D284_01_REFUSAL_REASON=" in transcript:
        raise ValueError("terminal transcript: gate refusal present")

    audit_baseline_causality()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    audit_capture(args.capture)
    print("D284_01_ATTEMPT_01_EVIDENCE_AUDIT=PASS_HASH_PINNED")
    print("D284_01_SUDO_BIOMETRIC_CAUSALITY=VERIFIED_BASELINE_AND_LIVE_MATCH")
    print("D284_01_POST_PHASE_C_PASSWORD=USER_OPERATOR_ATTESTED_EXPORT_ONLY")


if __name__ == "__main__":
    main()
