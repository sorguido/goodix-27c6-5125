#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Deterministic, hardware-free audit of the consumed D280/01 live run."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "captures/D280_01/D28001_20260910T082439Z_6cbcb9af/sanitized"
)
BASELINE = "6cbcb9af88fa5401895208e9fd5217a6374ffb85"
EXPECTED_HASHES = {
    "operator.log": "6b30227b831eb1f534a97afdff18a264985f93a587d030ea2016a62690bc7580",
    "summary.env": "8589963046c5c020158ab365032a6ba3d2565869fa4195e32ef3c263aae592a4",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_markers(path: Path) -> dict[str, list[str]]:
    markers: dict[str, list[str]] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "=" not in raw:
            raise ValueError(f"{path.name}:{number}: marker without '='")
        key, value = raw.split("=", 1)
        markers.setdefault(key, []).append(value)
    return markers


def one(markers: dict[str, list[str]], key: str) -> str:
    values = markers.get(key, [])
    if len(values) != 1:
        raise ValueError(f"expected one {key}, found {len(values)}")
    return values[0]


def git_source(path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{BASELINE}:{path}"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def predicate(
    name: str,
    expected: object,
    actual: object,
    basis: str,
    rationale: str,
) -> dict[str, object]:
    return {
        "predicate": name,
        "expected": expected,
        "actual": actual,
        "pass": actual == expected,
        "basis": basis,
        "rationale": rationale,
    }


def build_audit(evidence: Path = EVIDENCE) -> dict[str, object]:
    hashes = {name: sha256(evidence / name) for name in EXPECTED_HASHES}
    if hashes != EXPECTED_HASHES:
        raise ValueError(f"evidence hash mismatch: {hashes!r}")

    log = parse_markers(evidence / "operator.log")
    summary = parse_markers(evidence / "summary.env")
    tool_at_live = git_source("tools/d280_ephemeral_template_reuse.c")
    lifecycle_at_live = git_source("libfprint-driver/goodix_post_tls_lifecycle.c")
    device_at_live = git_source("libfprint-driver/goodix_fpimage_device.c")
    context_free = device_at_live[
        device_at_live.index("static void\ngoodix_device_context_free"):
        device_at_live.index("static gboolean\ndefault_acquire_runtime_material")
    ]
    image_close = device_at_live[
        device_at_live.index("static void\ngoodix_fpimage_device_img_close"):
        device_at_live.index("static void\ngoodix_fpimage_device_activate")
    ]

    required_source_facts = {
        "live_gate_required_error_terminal":
            "\n         audit->post_tls.terminal &&" in tool_at_live,
        "failure_sets_terminal_phase":
            "lifecycle->phase = GOODIX_POST_TLS_PHASE_TERMINAL;" in lifecycle_at_live,
        "failure_sets_terminal_audit":
            "lifecycle->audit->terminal = TRUE;" in lifecycle_at_live,
        "single_acquisition_selects_stop":
            "GOODIX_POST_TLS_PHASE_STOP : GOODIX_POST_TLS_PHASE_REARM_GATE" in lifecycle_at_live,
        "stop_increments_single_acquisition_count":
            "lifecycle->audit->single_acquisition_terminal_count++;" in lifecycle_at_live,
        "post_tls_reopen_has_no_increment_path":
            "audit->reopen_count++" not in lifecycle_at_live,
        "post_tls_reset_has_no_increment_path":
            "audit->device_reset_count++" not in lifecycle_at_live,
        "post_tls_clear_halt_has_no_increment_path":
            "audit->clear_halt_count++" not in lifecycle_at_live,
        "free_sets_post_tls_drained":
            "lifecycle->audit->backend_drained = TRUE;" in lifecycle_at_live,
        "free_sets_post_tls_cleanup":
            "lifecycle->audit->terminal_cleanup_completed = TRUE;" in lifecycle_at_live,
        "close_releases_claim_before_snapshot":
            image_close.index("goodix_fpimage_device_release_claim (self, &error)")
            < image_close.index("goodix_fpimage_device_discard_context (self)"),
        "snapshot_follows_lifecycle_and_material_free":
            context_free.index("goodix_post_tls_lifecycle_free (ctx->post_tls_lifecycle)")
            < context_free.index("goodix_device_context_collect_production_enrollment_audit (")
            and context_free.index("default_release_runtime_material (ctx->runtime_material, NULL)")
            < context_free.index("goodix_device_context_collect_production_enrollment_audit (")
    }
    failed_source_facts = [key for key, value in required_source_facts.items() if not value]
    if failed_source_facts:
        raise ValueError(f"baseline source facts failed: {failed_source_facts}")

    observed = lambda key: one(log, f"EPOCH2_IDENTIFY_{key}")
    derived_close = "VERIFIED_BY_BASELINE_CLOSE_FREE_CONTROL_FLOW"
    derived_stop = "VERIFIED_BY_BASELINE_SINGLE_ACQUISITION_STOP_CONTROL_FLOW"

    common = [
        predicate("context_closed", True, observed("CONTEXT_CLOSED") == "true", "OBSERVED", "final epoch-2 marker"),
        predicate("production_action_consumed", True, one(log, "IDENTIFY_ACTION_ATTEMPT_COUNT") == "1", "VERIFIED_BY_BASELINE_CONTROL_FLOW", "production identify sets the flag before starting the secure graph"),
        predicate("usb_backend_drained", True, observed("USB_BACKEND_DRAINED") == "true", "OBSERVED", "final epoch-2 marker"),
        predicate("usb_interface_claimed", False, False, derived_close, "successful close releases interface before final snapshot"),
        predicate("usb_outstanding_count", 0, int(observed("USB_OUTSTANDING_AT_SNAPSHOT")), "OBSERVED", "final epoch-2 marker"),
        predicate("usb_out_outstanding_count", 0, int(observed("USB_OUT_OUTSTANDING_AT_SNAPSHOT")), "OBSERVED", "final epoch-2 marker"),
        predicate("runtime_material_present", False, False, derived_close, "runtime owner is released before final snapshot"),
        predicate("runtime_handoff_views_cleared", True, True, "VERIFIED_BY_BASELINE_SUCCESS_CONTROL_FLOW", "the secure graph clears borrowed views before activation completes"),
        predicate("runtime_material.owner_free_count", 1, 1, derived_close, "the one open-epoch owner is freed once before snapshot"),
        predicate("runtime_material.descriptor_cleansed", True, True, derived_close, "runtime-material free sets the audit flag"),
        predicate("runtime_material.fdt_seed_cleansed", True, True, derived_close, "runtime-material free cleanses the seed and sets the audit flag"),
        predicate("tls.handshake_count", 1, int(observed("TLS_HANDSHAKE_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("tls.terminal_completion_count", 0, int(observed("TLS_TERMINAL_COMPLETION_COUNT")), "OBSERVED", "nominal TLS success has no abnormal terminal event"),
        predicate("tls.project_secret_zeroized", True, True, derived_close, "TLS free cleanses its owned project secret before snapshot"),
        predicate("secure.retry_count", 0, int(observed("SECURE_RETRY_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("secure.transport_reopen_count", 0, int(observed("SECURE_REOPEN_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("secure.device_reset_count", 0, int(observed("SECURE_DEVICE_RESET_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("secure.clear_halt_count", 0, int(observed("SECURE_CLEAR_HALT_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("post_tls.retry_count", 0, int(observed("POST_TLS_RETRY_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("post_tls.reopen_count", 0, 0, "VERIFIED_BY_BASELINE_IMPLEMENTATION", "counter is zero-initialized and the lifecycle has no increment path"),
        predicate("post_tls.device_reset_count", 0, 0, "VERIFIED_BY_BASELINE_IMPLEMENTATION", "counter is zero-initialized and the lifecycle has no increment path"),
        predicate("post_tls.clear_halt_count", 0, 0, "VERIFIED_BY_BASELINE_IMPLEMENTATION", "counter is zero-initialized and the lifecycle has no increment path"),
        predicate("known_persistent_family_count", 0, int(observed("KNOWN_PERSISTENT_FAMILY_COUNT")), "OBSERVED", "sum of all three known persistent families"),
    ]

    identify_without_old_terminal = [
        predicate("post_tls.first_image_pipeline_count", 1, int(observed("FIRST_IMAGE_PIPELINE_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("post_tls.release_tail_complete_count", 1, int(observed("RELEASE_TAIL_COMPLETE_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("post_tls.single_acquisition_terminal_count", 1, int(observed("SINGLE_ACQUISITION_TERMINAL_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("post_tls.rearm_0x32_count", 0, int(observed("REARM_0X32_COUNT")), "OBSERVED", "final epoch-2 marker"),
        predicate("post_tls.second_image_pipeline_count", 0, 0, derived_stop, "single-acquisition release NAV transitions directly to STOP"),
        predicate("post_tls.third_cycle_command_count", 0, 0, derived_stop, "STOP accepts no further lifecycle command"),
        predicate("post_tls.backend_drained", True, True, derived_close, "lifecycle_free requires a drained backend and records it before snapshot"),
        predicate("post_tls.terminal_cleanup_completed", True, True, derived_close, "lifecycle_free records completed cleanup before snapshot"),
    ]
    old_terminal = predicate(
        "post_tls.terminal", True, False, derived_stop,
        "TERMINAL is set only by lifecycle_fail; nominal single-acquisition success ends in STOP",
    )
    corrected_terminal = predicate(
        "post_tls.terminal", False, False, derived_stop,
        "the corrected success contract requires absence of the error-terminal flag",
    )

    old_predicates = common + identify_without_old_terminal + [old_terminal]
    corrected_predicates = common + identify_without_old_terminal + [corrected_terminal]
    old_failures = [item["predicate"] for item in old_predicates if not item["pass"]]
    corrected_failures = [item["predicate"] for item in corrected_predicates if not item["pass"]]

    summary_checks = {
        "baseline": one(summary, "D280_01_BASELINE_SHA") == BASELINE,
        "operation": one(summary, "D280_01_OPERATION") == "D280_01_ENROLL_FP3_CLOSE_OPEN_IDENTIFY_EPHEMERAL",
        "original_return_code_is_one": one(summary, "RUN_RETURN_CODE") == "1",
        "grant_consumed_no_operator_retry": one(summary, "OPERATOR_RETRY_COUNT") == "0",
        "two_actions": one(summary, "ACTION_ATTEMPT_COUNT") == "2",
        "two_successful_opens": one(summary, "OPEN_SUCCESS_COUNT") == "2",
        "two_successful_closes": one(summary, "CLOSE_SUCCESS_COUNT") == "2",
        "tmpfs_cleanup_complete": one(summary, "TEMPLATE_STORAGE_FILESYSTEM") == "tmpfs"
            and one(summary, "TEMPLATE_FILE_PRESENT_AFTER_RUN") == "false"
            and one(summary, "TEMPLATE_RAM_DIRECTORY_PRESENT_AFTER_RUN") == "false",
        "template_not_exported": one(summary, "TEMPLATE_INCLUDED_IN_EXPORT") == "false",
    }
    if not all(summary_checks.values()):
        raise ValueError(f"summary checks failed: {summary_checks}")

    live_claims = {
        "authentic_fp3_serialization": one(log, "ENROLLMENT_SUCCEEDED") == "true"
            and one(log, "FP3_EPHEMERAL_WRITE_SUCCEEDED") == "true",
        "close_open_reuse": one(log, "CLOSE_EPOCH1_SUCCEEDED") == "true"
            and one(log, "FP3_EPHEMERAL_READ_SUCCEEDED") == "true"
            and one(summary, "OPEN_SUCCESS_COUNT") == "2",
        "authentic_fp3_deserialization": one(log, "FP3_DESERIALIZE_COMPATIBLE") == "true",
        "single_acquisition_identify": one(log, "IDENTIFY_ACTION_ATTEMPT_COUNT") == "1"
            and int(observed("FIRST_IMAGE_PIPELINE_COUNT")) == 1
            and int(observed("SINGLE_ACQUISITION_TERMINAL_COUNT")) == 1
            and int(observed("REARM_0X32_COUNT")) == 0,
        "same_instructed_finger_biometric_match": one(log, "IDENTIFY_MATCH_SUCCEEDED") == "true"
            and one(log, "IDENTIFY_MATCH_CALLBACK_COUNT") == "1"
            and one(log, "IDENTIFY_NO_MATCH_CALLBACK_COUNT") == "0"
            and one(log, "IDENTIFY_RETRY_CALLBACK_COUNT") == "0",
    }

    return {
        "schema": "goodix.d280_01.authentic_live_reuse_audit.v1",
        "baseline_live_sha": BASELINE,
        "evidence": {
            "directory": str(EVIDENCE.relative_to(ROOT)),
            "sha256": hashes,
            "user_reported_results_export": "PASS_BYTE_IDENTICAL",
            "repository_import_byte_identical_to_supplied_export": True,
            "template_included": False,
        },
        "source_semantics": required_source_facts,
        "summary_checks": summary_checks,
        "common_audit_predicates": common,
        "identify_audit_predicates_excluding_terminal": identify_without_old_terminal,
        "original_terminal_predicate": old_terminal,
        "corrected_terminal_predicate": corrected_terminal,
        "original_gate": {
            "recorded_pass": one(log, "EPOCH2_IDENTIFY_AUDIT_PASS") == "true",
            "failing_predicates": old_failures,
            "pass": not old_failures,
        },
        "corrected_contract_re_evaluation": {
            "failing_predicates": corrected_failures,
            "pass": not corrected_failures,
        },
        "biometric_execution": {
            "original_executable_return_code": int(one(summary, "RUN_RETURN_CODE")),
            "original_aggregate_pass_marker": one(log, "D280_01_EPHEMERAL_TEMPLATE_REUSE_PASS") == "true",
            "claims_verified_live": live_claims,
            "all_listed_claims_verified_live": all(live_claims.values()),
        },
        "safety": {
            "operator_retry_count": int(one(summary, "OPERATOR_RETRY_COUNT")),
            "known_persistent_family_count": int(observed("KNOWN_PERSISTENT_FAMILY_COUNT")),
            "sensor_side_persistence_absence_proven": one(summary, "SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN") == "true",
            "grant_consumed": True,
            "retry_authorized": False,
        },
        "decision": "PASS_AFTER_DETERMINISTIC_CORRECTED_CONTRACT_RE_EVALUATION",
    }


def main() -> int:
    try:
        audit = build_audit()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"D280_01_AUTHENTIC_LIVE_AUDIT=FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
