#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Deterministic audit of the consumed D282/01 privileged staging probe."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "3d42daec016d1a2c3292ac35374ae117ef8d1611"
OPERATION = "D282_01_PRIVILEGED_SYSTEMD_SELINUX_STAGING_PROBE"
EVIDENCE = (
    ROOT
    / "captures/D282_01"
    / "D28201_STAGING_PROBE_20260910T143838Z_3d42daec"
    / "sanitized/summary.env"
)
EXPECTED_SUMMARY_SHA256 = (
    "988f992039b6cee1d0dcc64aef4bc53775f6fb5617ec1ec6ce7a93ac558e49ef"
)
EXPECTED_MARKERS = {
    "D282_01_RESULT": "PASS_STAGING_PROBE",
    "D282_01_STAGING_PROBE_BASELINE_SHA": BASELINE,
    "D282_01_OPERATION": OPERATION,
    "FPRINTD_SYSTEMD_STAGING_START": "PASS",
    "SELINUX_ENFORCING": "true",
    "SELINUX_EXEC_DENIAL": "false",
    "EXEC_MAIN_STATUS": "0",
    "DAEMON_EXE": "/usr/libexec/fprintd",
    "EXACT_LIBRARY_MAP_VERIFIED": "true",
    "CUSTOM_LIBFPRINT_LOADED": "true",
    "EXACT_STATE_DIRECTORY_VERIFIED": "true",
    "D282_01_STAGING_PROBE_DRIVER": "virtual_image",
    "D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED": "true",
    "D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT": "false",
    "PRIVATE_DEVICES": "true",
    "DEVICE_POLICY": "closed",
    "USB_DEVICE_FD_COUNT": "0",
    "REAL_USB_ENUMERATION_ATTEMPTED": "false",
    "REAL_SENSOR_ACCESSED": "false",
    "BIOMETRIC_ACTION_COUNT": "0",
    "FINGER_CONTACT_COUNT": "0",
    "LIVE_EXECUTION_PERFORMED": "false",
    "PAM_IN_SCOPE": "false",
    "SERVICE_CLEANUP_COMMANDS_SUCCEEDED": "true",
    "SERVICE_STATE_RESTORED": "true",
    "SERVICE_INITIAL_STATE": "active",
    "SERVICE_FINAL_STATE": "active",
    "STAGING_REMOVED": "true",
    "SYSTEM_LIBFPRINT_UNCHANGED": "true",
    "RUN_RETURN_CODE": "0",
    "GRANT_CONSUMED": "true",
    "RETRY_AUTHORIZED": "false",
    "ROLLBACK_COMPLETE": "true",
    "PREEXISTING_STORAGE_UNCHANGED": "true",
    "STAGING_PROBE_EXECUTION_PERFORMED": "true",
    "RECOVERY_REQUIRED": "false",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_summary(path: Path) -> dict[str, str]:
    markers: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw:
            continue
        if "=" not in raw:
            raise ValueError(f"{path.name}:{number}: marker without '='")
        key, value = raw.split("=", 1)
        if key in markers:
            raise ValueError(f"{path.name}:{number}: duplicate marker {key}")
        markers[key] = value
    return markers


def git_source(path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{BASELINE}:{path}"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def function_slice(text: str, name: str, next_name: str) -> str:
    start = text.index(name)
    end = text.index(next_name, start + len(name))
    return text[start:end]


def build_audit(evidence: Path = EVIDENCE) -> dict[str, object]:
    evidence_hash = sha256(evidence)
    if evidence_hash != EXPECTED_SUMMARY_SHA256:
        raise ValueError(f"evidence hash mismatch: {evidence_hash}")
    markers = parse_summary(evidence)
    if markers != EXPECTED_MARKERS:
        missing = sorted(set(EXPECTED_MARKERS) - set(markers))
        unexpected = sorted(set(markers) - set(EXPECTED_MARKERS))
        differing = sorted(
            key
            for key in set(markers) & set(EXPECTED_MARKERS)
            if markers[key] != EXPECTED_MARKERS[key]
        )
        raise ValueError(
            "summary mismatch: "
            f"missing={missing}, unexpected={unexpected}, differing={differing}"
        )

    launcher = git_source(
        "operator_kit/d282-01-fprintd-target/run-d282-01.sh"
    )
    probe = function_slice(
        launcher, "run_authorized_staging_probe ()", "run_authorized_live ()"
    )
    cleanup = function_slice(launcher, "cleanup_live ()", "verify_baseline ()")
    manager = git_source("reference/fprintd-fedora44-1.94.5/source/src/manager.c")
    main = git_source("reference/fprintd-fedora44-1.94.5/source/src/main.c")

    source_facts = {
        "operation_binding": f"staging_probe_operation={OPERATION}" in launcher,
        "probe_uses_direct_system_fprintd":
            "ExecStart=/usr/libexec/fprintd" in launcher,
        "probe_allowlists_only_virtual_image":
            "FP_DRIVERS_ALLOWLIST=virtual_image" in probe,
        "probe_usb_context_compile_disabled_gate":
            "STAGING_PROBE_USB_CONTEXT_SYMBOL_PRESENT" in launcher,
        "probe_goodix_absence_gate": "STAGING_PROBE_GOODIX_PRESENT" in launcher,
        "probe_has_no_biometric_client": all(
            name not in probe
            for name in ("fprintd-enroll", "fprintd-verify", "fprintd-delete")
        ),
        "probe_requires_zero_usb_fds":
            "STAGING_PROBE_USB_FD_OBSERVED" in probe,
        "probe_checks_exact_daemon_exe":
            "[[ $daemon_exe == /usr/libexec/fprintd ]]" in probe,
        "probe_checks_exact_candidate_map":
            "DAEMON_LIBRARY_MAP_NOT_EXACT" in probe,
        "cleanup_compares_final_and_initial_service_state":
            '[[ $service_final_state == "$live_service_before" ]]' in cleanup,
        "fprintd_idle_timeout_exits_successfully": "exit (0);" in manager,
        "fprintd_no_timeout_option_exists":
            '{"no-timeout"' in main and "Do not exit after unused for a while" in main,
    }
    failed_source_facts = sorted(
        name for name, passed in source_facts.items() if not passed
    )
    if failed_source_facts:
        raise ValueError(f"baseline source facts failed: {failed_source_facts}")

    return {
        "schema": "goodix.d282_01.privileged_staging_probe_audit.v1",
        "baseline_sha": BASELINE,
        "operation": OPERATION,
        "evidence": {
            "path": str(EVIDENCE.relative_to(ROOT)),
            "sha256": evidence_hash,
            "provenance": "OPERATOR_SUPPLIED_VERBATIM_SUMMARY_TRANSCRIPT",
            "raw_export_byte_identity_claimed": False,
            "private_material_imported": False,
        },
        "source_facts": source_facts,
        "runtime": {
            "systemd_selinux_staging": "VERIFIED_PRIVILEGED_HOST",
            "selinux_wrapper_failure": "RESOLVED",
            "systemd_start": "VERIFIED_PRIVILEGED_HOST",
            "selinux_exec_denial": False,
            "exact_library_map_verified": True,
            "custom_libfprint_loaded": True,
        },
        "safety": {
            "real_usb_enumeration_attempted": False,
            "real_sensor_accessed": False,
            "biometric_action_count": 0,
            "finger_contact_count": 0,
            "pam_in_scope": False,
        },
        "rollback": {
            "complete": True,
            "service_initial_state": "active",
            "service_final_state": "active",
            "service_state_restored": True,
            "preexisting_storage_unchanged": True,
            "system_libfprint_unchanged": True,
            "recovery_required": False,
        },
        "post_probe_inactive_dead": {
            "classification": "NORMAL_FPRINTD_IDLE_TIMEOUT_NON_BLOCKING",
            "invalidates_recorded_rollback": False,
        },
        "grant_consumed": True,
        "retry_authorized": False,
        "decision": "ACCEPTED_CLOSED",
    }


def main() -> int:
    try:
        audit = build_audit()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"D282_01_STAGING_PROBE_EVIDENCE_AUDIT=FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
