#!/usr/bin/env python3
"""Fail-closed audit of the sanitized D279/57 stage-8 live evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = (
    ROOT
    / "captures/D279_57/D27957_20260910T055810Z_38962cc/sanitized"
)
OPERATOR_LOG = EVIDENCE_DIR / "operator.log"
SUMMARY = EVIDENCE_DIR / "summary.env"
OPERATOR_LOG_SHA256 = (
    "49c28b34d18cbad98a7711972a336c18a57cfd705fc40d2add77a65f39bacc18"
)
SUMMARY_SHA256 = (
    "a79fa72b1969358723582a8718939266c453d19e16e3f7259609cdaa02929211"
)
BASELINE = "38962cc00b7707dc1bf56bc38cd4457d7d11b5e1"
GRANT_ID = f"d27957-{BASELINE}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_values(path: Path) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and all(character.isupper() or character.isdigit() or character == "_"
                       for character in key):
            values.setdefault(key, []).append(value)
    return values


def require_value(values: dict[str, list[str]], key: str, expected: str) -> None:
    actual = values.get(key)
    if not actual or any(value != expected for value in actual):
        raise ValueError(f"{key}: expected only {expected!r}, found {actual!r}")


def require_int(values: dict[str, list[str]], key: str, expected: int) -> None:
    require_value(values, key, str(expected))


def only_int(values: dict[str, list[str]], key: str) -> int:
    actual = values.get(key)
    if not actual or len(set(actual)) != 1:
        raise ValueError(f"{key}: missing or inconsistent values {actual!r}")
    try:
        return int(actual[0], 10)
    except ValueError as error:
        raise ValueError(f"{key}: not a decimal integer: {actual[0]!r}") from error


def audit(operator_log: Path = OPERATOR_LOG, summary: Path = SUMMARY) -> dict:
    operator_digest = sha256(operator_log)
    summary_digest = sha256(summary)
    if operator_digest != OPERATOR_LOG_SHA256:
        raise ValueError(f"operator.log SHA-256 mismatch: {operator_digest}")
    if summary_digest != SUMMARY_SHA256:
        raise ValueError(f"summary.env SHA-256 mismatch: {summary_digest}")

    log = parse_values(operator_log)
    summary_values = parse_values(summary)

    expected_log = {
        "LIVE_RUN_STARTED": "true",
        "ACTION_ALLOWLIST": "ENROLL_ONLY",
        "REAL_USB_ENUMERATION_ATTEMPTED": "true",
        "TARGET_DRIVER_MATCH_COUNT": "1",
        "OPEN_ATTEMPT_COUNT": "1",
        "OPEN_SUCCEEDED": "true",
        "ACTION_ATTEMPT_COUNT": "1",
        "ENROLLMENT_SUCCEEDED": "true",
        "BIOMETRIC_TEMPLATE_SAVED": "false",
        "CLOSE_ATTEMPT_COUNT": "1",
        "CLOSE_SUCCEEDED": "true",
        "PRODUCTION_AUDIT_AVAILABLE": "true",
        "AUDIT_CONTEXT_CLOSED": "true",
        "AUDIT_ACTION_CONSUMED": "true",
        "AUDIT_USB_BACKEND_DRAINED": "true",
        "AUDIT_USB_INTERFACE_CLAIMED_AT_SNAPSHOT": "false",
        "AUDIT_RUNTIME_MATERIAL_PRESENT_AT_SNAPSHOT": "false",
        "AUDIT_RUNTIME_OWNER_FREE_COUNT": "1",
        "AUDIT_RUNTIME_DESCRIPTOR_CLEANSED": "true",
        "AUDIT_RUNTIME_FDT_SEED_CLEANSED": "true",
        "AUDIT_RUNTIME_HANDOFF_VIEWS_CLEARED": "true",
        "AUDIT_TLS_HANDSHAKE_COUNT": "1",
        "AUDIT_TLS_SECRET_ZEROIZED": "true",
        "AUDIT_ENROLL_CONFIGURED_STAGE_COUNT": "8",
        "AUDIT_ENROLL_INTERMEDIATE_DELIVERY_DEFERRED_UNTIL_RELEASE_READY": "true",
        "AUDIT_ENROLL_TERMINAL_DELIVERY_DEFERRED_UNTIL_RELEASE_READY": "true",
        "AUDIT_ENROLL_TERMINAL_COMPLETION_HOLD_COUNT": "1",
        "AUDIT_ENROLL_TERMINAL_COMPLETION_RELEASE_COUNT": "1",
        "AUDIT_ENROLL_TERMINAL_COMPLETION_ABORT_COUNT": "0",
        "AUDIT_ENROLL_TERMINAL_COMPLETION_HELD_AT_SNAPSHOT": "false",
        "AUDIT_ENROLL_OBSERVED_PRIMARY_STAGE_COUNT": "8",
        "AUDIT_ENROLL_COMPLETED_STAGE_COUNT": "8",
        "AUDIT_ENROLL_TERMINAL_TRANSITION_COUNT": "1",
        "AUDIT_ENROLL_INTER_STAGE_REARM_COUNT": "7",
        "AUDIT_ENROLL_COMMAND_32_COUNT": "8",
        "AUDIT_ENROLL_REJECTED_INBOUND_COUNT": "0",
        "AUDIT_ENROLL_LAST_MISMATCH_EXPECTED_EVENT": "NONE",
        "AUDIT_ENROLL_LAST_MISMATCH_IRQ_CLASSIFIED": "false",
        "AUDIT_KNOWN_PERSISTENT_FAMILY_OBSERVED_COUNT": "0",
        "SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN": "false",
        "D279_57_STAGE8_TERMINAL_AUDIT_PASS": "true",
        "D279_57_REUSABILITY_PROVEN": "false",
        "COMPLETED_STAGE_COUNT": "8",
        "PROGRESS_ERROR_COUNT": "0",
        "RELEASE_READY_PROMPT_COUNT": "8",
        "REPOSITION_PROMPT_COUNT": "7",
        "PHYSICAL_INSTRUCTION_SOURCE": "LIBFPRINT_FINGER_STATUS",
        "OPERATOR_RETRY_COUNT": "0",
        "SECOND_ACTION_COUNT": "0",
        "REOPEN_COUNT": "0",
        "HOST_DEADLINE_EXPIRED": "false",
        "OPERATOR_SIGNAL_RECEIVED": "false",
        "DEVICE_SIDE_TIMEOUT_OR_QUIESCENCE_INFERRED": "false",
    }
    for key, expected in expected_log.items():
        require_value(log, key, expected)

    zero_counters = (
        "AUDIT_USB_OUTSTANDING_AT_SNAPSHOT",
        "AUDIT_USB_OUT_OUTSTANDING_AT_SNAPSHOT",
        "AUDIT_SECURE_RETRY_COUNT",
        "AUDIT_SECURE_REOPEN_COUNT",
        "AUDIT_SECURE_DEVICE_RESET_COUNT",
        "AUDIT_SECURE_CLEAR_HALT_COUNT",
        "AUDIT_POST_TLS_RETRY_COUNT",
        "AUDIT_POST_TLS_REOPEN_COUNT",
        "AUDIT_POST_TLS_DEVICE_RESET_COUNT",
        "AUDIT_POST_TLS_CLEAR_HALT_COUNT",
        "AUDIT_ENROLL_EVENT_RETRY_COUNT",
        "AUDIT_ENROLL_BINDING_CANCELLATION_COUNT",
        "AUDIT_ENROLL_BINDING_RETRY_COUNT",
    )
    for key in zero_counters:
        require_int(log, key, 0)

    require_int(log, "AUDIT_USB_MAX_IN_OUTSTANDING", 1)
    require_int(log, "AUDIT_USB_MAX_OUT_OUTSTANDING", 1)
    require_int(log, "AUDIT_ENROLL_EVENT_ACK_COUNT", 47)
    require_int(log, "AUDIT_ENROLL_EVENT_PRIMARY_B0_COUNT", 8)
    require_int(log, "AUDIT_ENROLL_EVENT_AUXILIARY_B0_COUNT", 8)
    require_int(log, "AUDIT_ENROLL_BINDING_BACKEND_SUBMIT_ATTEMPT_COUNT", 47)
    require_int(log, "AUDIT_ENROLL_BINDING_BACKEND_COMPLETION_COUNT", 47)

    real_submit = only_int(log, "AUDIT_USB_REAL_SUBMIT_COUNT")
    out_submit = only_int(log, "AUDIT_USB_OUT_SUBMIT_COUNT")
    in_completion = only_int(log, "AUDIT_USB_IN_COMPLETION_COUNT")
    out_completion = only_int(log, "AUDIT_USB_OUT_COMPLETION_COUNT")
    if real_submit != in_completion + out_submit or out_submit != out_completion:
        raise ValueError("USB submit/completion accounting is inconsistent")

    if log.get("RILASCIO_FISICO_PRONTO") != [str(index) for index in range(1, 9)]:
        raise ValueError("release-ready prompt sequence is not exactly 1..8")
    if log.get("RIPOSIZIONAMENTO_RICHIESTO") != [str(index) for index in range(1, 8)]:
        raise ValueError("reposition prompt sequence is not exactly 1..7")
    if log.get("STAGE_COMPLETATO") != [f"{index}/8" for index in range(1, 9)]:
        raise ValueError("completed-stage sequence is not exactly 1/8..8/8")

    expected_summary = {
        "D279_57_BASELINE_SHA": BASELINE,
        "D279_57_OPERATION": "D279_57_STAGE8_EARLY_TERMINAL_ENROLLMENT",
        "D279_57_GRANT_ID": GRANT_ID,
        "RUN_RETURN_CODE": "0",
        "ACTION_ATTEMPT_MAX": "1",
        "OPERATOR_RETRY_COUNT": "0",
        "SECOND_ACTION_COUNT": "0",
        "REOPEN_COUNT": "0",
        "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT": "0",
        "EXPECTED_ENROLLMENT_STAGE_COUNT": "8",
        "REUSABILITY_PROVEN": "false",
        "SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN": "false",
        "DEVICE_SIDE_TIMEOUT_OR_QUIESCENCE_INFERRED": "false",
    }
    if set(summary_values) != set(expected_summary):
        raise ValueError("summary.env key set is not exact")
    for key, expected in expected_summary.items():
        require_value(summary_values, key, expected)

    return {
        "schema": "D279_57_STAGE8_SUCCESS_AUDIT_V1",
        "baseline_sha": BASELINE,
        "evidence": {
            "operator_log_path": str(operator_log.relative_to(ROOT)),
            "operator_log_sha256": operator_digest,
            "summary_path": str(summary.relative_to(ROOT)),
            "summary_sha256": summary_digest,
            "export_byte_identical": True,
        },
        "result": "PASS_STAGE8_EARLY_TERMINAL",
        "live_authorization_consumed": True,
        "rerun_authorized": False,
        "production_path": {
            "target_driver_match_count": 1,
            "open_succeeded": True,
            "action_attempt_count": 1,
            "tls_handshake_count": 1,
            "configured_stage_count": 8,
            "observed_primary_stage_count": 8,
            "completed_stage_count": 8,
            "primary_b0_count": 8,
            "auxiliary_b0_count": 8,
            "inter_stage_rearm_count": 7,
            "command_32_count": 8,
            "terminal_transition_count": 1,
            "rejected_inbound_count": 0,
            "close_succeeded": True,
        },
        "safety": {
            "real_usb_submit_count": real_submit,
            "usb_out_submit_count": out_submit,
            "usb_in_completion_count": in_completion,
            "usb_out_completion_count": out_completion,
            "max_in_outstanding": 1,
            "max_out_outstanding": 1,
            "usb_backend_drained": True,
            "runtime_owner_free_count": 1,
            "tls_secret_zeroized": True,
            "operator_retry_count": 0,
            "second_action_count": 0,
            "reopen_count": 0,
            "device_reset_count": 0,
            "clear_halt_count": 0,
            "known_persistent_family_observed_count": 0,
        },
        "non_claims": {
            "biometric_template_saved": False,
            "post_close_reusability_proven": False,
            "sensor_side_persistence_absence_proven": False,
            "fprintd_end_user_integration_proven": False,
            "production_identify_live_proven": False,
        },
        "decision": "ACCEPT_LIVE_EVIDENCE_AND_CLOSE_D279",
        "next_boundary": (
            "D280_01_OFFLINE_POST_CLOSE_SERIALIZED_TEMPLATE_REUSE_"
            "AND_PRODUCTION_IDENTIFY_OPERATOR_BOUNDARY"
        ),
        "live_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    rendered = json.dumps(audit(), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
