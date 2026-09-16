#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate D285/01 Attempt 02 evidence and baseline causal closure."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess


EXPECTED_HASHES = {
    "operator.log": "aeb42ae93bf2e9ad902031a609162c3e394f135554bba3816386df79d9a93995",
    "summary.env": "59577e61a197e855a217192c24fa64ffb213fa16258c624252776ca1bdaf1c33",
    "terminal-transcript.log": "e1935aca82a49bafaee33bf8f20bb3b84f67c491acb44a0e8917931884624e3a",
}
BASELINE = "a9e234e43d2bdf3e81630df143eb7a809a19bff5"
ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = "operator_kit/d285-01-persistent-sudo/run-d285-01.sh"
PAM_PATH = "operator_kit/d285-01-persistent-sudo/goodix-d285-01-sudo.pam"
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
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{BASELINE}:{path}"],
        check=True, capture_output=True, text=True).stdout


def audit_baseline_causality() -> None:
    subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{BASELINE}^{{commit}}"],
        check=True)
    script = git_show(SCRIPT_PATH)
    pam = git_show(PAM_PATH)
    for line in (
            "pam_fprintd.so max-tries=1 timeout=45",
            "pam_unix.so nullok", "pam_deny.so"):
        if line not in pam:
            raise ValueError(f"baseline PAM contract missing {line}")
    if "printf 'Defaults:%s pam_service=goodix-d285-01-sudo\\n'" not in script:
        raise ValueError("baseline per-user sudo PAM selector missing")

    wrapper = script[script.index("d285_write_wrapper ()"):
                     script.index("d285_write_dropin ()")]
    for marker in (
            "D285_01_DAEMON_PROVENANCE_DRIFT=true",
            "D285_01_RUNTIME_INTEGRITY_DRIFT=true",
            "sha256sum -c artifacts.sha256",
            "FP_DRIVERS_ALLOWLIST=goodix_27c6_5125"):
        if marker not in wrapper:
            raise ValueError(f"baseline wrapper contract missing {marker}")
    dropin = script[script.index("d285_write_dropin ()"):
                    script.index("d285_hash_host_config ()")]
    if "ExecStart=/usr/local/sbin/goodix-d285-01-fprintd" not in dropin:
        raise ValueError("baseline fprintd drop-in does not select wrapper")

    install = script[script.index("d285_install ()"):
                     script.index("d285_verify_installed_file ()")]
    ordered = (
        'd285_stage_persistent_runtime "$candidate" "$d285_runtime"',
        'd285_write_wrapper "$d285_runtime" "$daemon_sha" "$d285_wrapper"',
        'd285_write_dropin "$d285_dropin"',
        "authselect disable-feature with-fingerprint",
        "SYSTEM_AUTH_FINGERPRINT_STILL_ENABLED",
        "systemctl start fprintd.service",
        'grep -F "$d285_runtime/libfprint-2.so.2.0.0"',
        "fprintd-enroll -f right-index-finger",
        "d285_template_created=true",
        "systemctl restart fprintd.service",
        'runuser -u "$user" -- sudo -K',
        'runuser -u "$user" -- env -u SUDO_ASKPASS sudo -v',
        "event=outcome result=match",
        'd285_write_state "$baseline" "$user" "$template_relative" "$template_sha"',
        "D285_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW",
        "d285_install_committed=true",
    )
    position = -1
    for snippet in ordered:
        position = install.index(snippet, position + 1)
    for marker in (
            '[[ $action_rc -eq 0 ]]', "$epoch_count -eq 2",
            "$retry_count -eq 0", "$reopen_count -eq 0",
            "$reset_count -eq 0", "$clear_halt_count -eq 0",
            "$persistent_count -eq 0", "$match_count -eq 1",
            "TEMPLATE_INCLUDED_IN_EXPORT=false"):
        if marker not in install:
            raise ValueError(f"baseline final live gate missing {marker}")
    if '>"/etc/pam.d/sudo"' in install:
        raise ValueError("baseline unexpectedly overwrites the system sudo PAM file")


def audit_capture(capture: Path, enforce_hashes: bool = True) -> None:
    if {item.name for item in capture.iterdir()} != set(EXPECTED_HASHES):
        raise ValueError("capture file set mismatch")
    paths = {name: capture / name for name in EXPECTED_HASHES}
    for name, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"{name}: missing, non-file, or symlink")
        if enforce_hashes and hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED_HASHES[name]:
            raise ValueError(f"{name}: SHA-256 mismatch")

    summary = read_env(paths["summary.env"])
    expected_summary = {
        "D285_01_RESULT": "PASS_LIVE_PENDING_INDEPENDENT_REVIEW",
        "D285_01_BASELINE_SHA": BASELINE,
        "D285_01_INSTALL_STATUS": "ACTIVE",
        "D285_01_CONSUMER": "SUDO_VALIDATE_PERSISTENT",
        "D285_01_PAM_SERVICE": "goodix-d285-01-sudo",
        "D285_01_PAM_MAX_TRIES": "1",
        "D285_01_PASSWORD_FALLBACK_PRESENT": "true",
        "D285_01_GLOBAL_AUTHSELECT_FINGERPRINT_DISABLED": "true",
        "D285_01_SYSTEM_AUTH_PAM_FPRINTD_COUNT": "0",
        "D285_01_ENROLL_ACTION_COUNT": "1",
        "D285_01_VERIFY_ACTION_COUNT": "1",
        "D285_01_DAEMON_RESTART_COUNT": "1",
        "D285_01_OBSERVED_RETRY_COUNT": "0",
        "D285_01_HIDDEN_REOPEN_COUNT": "0",
        "D285_01_RESET_COUNT": "0",
        "D285_01_CLEAR_HALT_COUNT": "0",
        "D285_01_KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT": "0",
        "D285_01_SIGFM_MATCH_OUTCOME": "match",
        "D285_01_SUDO_VALIDATE_RETURN_CODE": "0",
        "D285_01_RUNTIME_INTEGRITY_WRAPPER_ACTIVE": "true",
        "D285_01_DAEMON_PROVENANCE_WRAPPER_ACTIVE": "true",
        "D285_01_UNINSTALL_TEMPLATE_OWNERSHIP_PINNED": "true",
        "TEMPLATE_INCLUDED_IN_EXPORT": "false",
        "REAL_USB_ENUMERATION_ATTEMPTED": "true",
        "REAL_SENSOR_ACCESSED": "true",
        "LIVE_EXECUTION_PERFORMED": "true",
        "AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED": "false",
    }
    if summary != expected_summary:
        require_fields(summary, expected_summary, "summary")
        raise ValueError("summary: unexpected key set")

    lines = paths["operator.log"].read_text().splitlines()
    for marker in (
            "ENROLL_OPERATOR_CONFIRMATION=DESTRO",
            "SUDO_OPERATOR_CONFIRMATION=INDICE_DESTRO"):
        if lines.count(marker) != 1:
            raise ValueError(f"operator log: expected one {marker}")
    epochs = unique_records(lines, EPOCH_MARKER)
    if len(epochs) != 2:
        raise ValueError("operator log: expected exactly two epochs")
    by_action = {epoch.get("action"): epoch for epoch in epochs}
    if set(by_action) != {"FPI_DEVICE_ACTION_ENROLL", "FPI_DEVICE_ACTION_VERIFY"}:
        raise ValueError("operator log: unexpected action set")
    common = {
        "attempts": "1", "rejected": "0", "consumed": "1", "tls": "1",
        "secure_retry": "0", "post_retry": "0", "reopen": "0",
        "reset": "0", "clear_halt": "0", "persistent": "0",
        "outstanding": "0", "drained": "1", "context_closed": "1",
    }
    require_fields(by_action["FPI_DEVICE_ACTION_ENROLL"], {
        **common, "first_image": "0", "enroll_stages": "8",
        "enroll_rearm32": "7", "enroll_terminal": "1", "real_submit": "203",
    }, "enroll epoch")
    require_fields(by_action["FPI_DEVICE_ACTION_VERIFY"], {
        **common, "first_image": "1", "enroll_stages": "0",
        "enroll_rearm32": "0", "enroll_terminal": "0", "real_submit": "75",
    }, "verify epoch")

    extracts = unique_records(lines, EXTRACT_MARKER)
    if len(extracts) != 9 or any(int(record.get("keypoints", "0")) <= 0 for record in extracts):
        raise ValueError("operator log: expected nine positive SIGFM extractions")
    matcher = unique_records(lines, MATCH_MARKER)
    events = {record.get("event"): record for record in matcher}
    if len(matcher) != 3 or set(events) != {"start", "comparison", "outcome"}:
        raise ValueError("operator log: incomplete matcher event set")
    require_fields(events["start"], {"template_samples": "8", "threshold": "40"},
                   "matcher start")
    require_fields(events["comparison"], {
        "sample": "1", "score": "584", "threshold": "40"},
        "matcher comparison")
    require_fields(events["outcome"], {
        "result": "match", "matched_sample": "1", "comparisons": "1",
        "threshold": "40"}, "matcher outcome")

    transcript = paths["terminal-transcript.log"].read_text()
    for marker in (
            "PHASE_A=Enrollment persistente indice destro: otto contatti.",
            "PHASE_B=Un solo sudo -v persistente con impronta; non digitare password.",
            "D285_01_INSTALL=PASS_LIVE_PENDING_INDEPENDENT_REVIEW",
            "TEMPLATE_INCLUDED_IN_EXPORT=false"):
        if marker not in transcript:
            raise ValueError(f"terminal transcript: missing {marker}")
    if transcript.count("Enroll result: enroll-stage-passed") != 7 or \
            transcript.count("Enroll result: enroll-completed") != 1:
        raise ValueError("terminal transcript: enrollment sequence mismatch")
    backup = re.search(r"d285-01-\d{8}T\d{6}Z-a9e234e43d2b", transcript)
    if not backup:
        raise ValueError("terminal transcript: baseline-pinned authselect backup missing")
    for forbidden in ("D285_01_GATE_REFUSED=true", "D285_01_REFUSAL_REASON=", "Password:"):
        if forbidden in transcript:
            raise ValueError(f"terminal transcript: forbidden marker {forbidden}")

    audit_baseline_causality()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    audit_capture(args.capture)
    print("D285_01_ATTEMPT_02_EVIDENCE_AUDIT=PASS_HASH_PINNED")
    print("D285_01_SUDO_BIOMETRIC_CAUSALITY=VERIFIED_BASELINE_AND_LIVE_MATCH")


if __name__ == "__main__":
    main()
