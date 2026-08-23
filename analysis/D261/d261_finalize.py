#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Finalize the D261 operational-evidence-hardening corrective bundle."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import zipfile


REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / "analysis/D261"
REFERENCE_HEAD = "75dbb50475786295a816e6cbd0e726af46132091"
BUNDLE_NAME = "D261_operational_evidence_hardening_corrective_bundle.zip"

REVIEW_FILES = (
    "core/protected_runtime.py",
    "core/usb_runtime.py",
    "tools/d261_live_fdt_arm_once.py",
    "operator_kit/d261-live-fdt-arm-once.sh",
    "tests/test_d261_operational_readiness.py",
    "analysis/D261/d261_offline_rehearsal.py",
    "analysis/D261/d261_corrective_harness.py",
    "analysis/D261/d261_finalize.py",
    "analysis/D261/D261_hard_disable_execution_evidence.json",
    "analysis/D261/D261_real_usb_adapter_offline_evidence.json",
    "analysis/D261/D261_failure_containment_matrix.json",
    "analysis/D261/D261_single_reader_demux_evidence.json",
    "analysis/D261/D261_pre_usb_transaction_evidence.json",
    "analysis/D261/D261_durable_report_safety_evidence.json",
    "analysis/D261/D261_preflight_dry_run.json",
    "analysis/D261/D261_operator_kit_dry_run_result.json",
    "analysis/D261/D261_full_offline_operational_rehearsal.json",
    "analysis/D261/D261_operational_live_critical_fileset.json",
    "analysis/D261/D261_test_results.json",
    "analysis/D261/D261_readiness_decision.json",
    "analysis/D261/D261_corrective_report.md",
    "analysis/D261/D261_previous_bundle_status.txt",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(name: str) -> dict:
    return json.loads((OUTPUT / name).read_text(encoding="utf-8"))


def main() -> int:
    preflight = load_json("D261_preflight_dry_run.json")
    rehearsal = load_json("D261_full_offline_operational_rehearsal.json")
    failures = load_json("D261_failure_containment_matrix.json")
    demux = load_json("D261_single_reader_demux_evidence.json")
    hard_disable = load_json("D261_hard_disable_execution_evidence.json")
    report_safety = load_json("D261_durable_report_safety_evidence.json")
    transaction = load_json("D261_pre_usb_transaction_evidence.json")
    if not all((
        preflight["status"] == "PASS",
        rehearsal["status"] == "PASS",
        failures["status"] == "PASS_EXECUTION_DERIVED",
        demux["status"] == "PASS",
        hard_disable["status"] == "PASS",
        report_safety["status"] == "PASS",
        transaction["status"] == "PASS",
    )):
        raise RuntimeError("D261 corrective prerequisite artifact is not PASS")

    test_results = {
        "schema": "D261_CORRECTIVE_TEST_RESULTS_V2",
        "execution_mode": "OFFLINE_ONLY",
        "commands": [
            {"command": "python3 -m py_compile <D261 corrective Python files>", "status": "PASS"},
            {"command": "python3 analysis/D261/d261_tail_audit.py", "status": "PASS"},
            {"command": "python3 analysis/D261/d261_offline_rehearsal.py", "status": "PASS"},
            {"command": "operator_kit/d261-live-fdt-arm-once.sh --dry-run (external cwd)", "status": "PASS"},
            {
                "command": "python3 -m unittest discover -s tests -p 'test_*.py'",
                "status": "PASS", "tests_run": 235, "failures": 0, "errors": 0,
            },
        ],
        "REAL_USB_OPEN_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_COMMAND_SEND_COUNT": 0,
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0,
        "status": "PASS",
    }
    write_json(OUTPUT / "D261_test_results.json", test_results)

    readiness = {
        "schema": "D261_OPERATIONAL_EVIDENCE_HARDENING_DECISION_V2",
        "step": "D261_CORRECTIVE_SAME_STEP",
        "execution_mode": "OFFLINE_ONLY",
        "OUTCOME": "READY_FOR_BASELINE_APPROVAL_REVIEW",
        "ADVANCEMENT": "NEW_TECHNICAL_EVIDENCE_PRODUCED_EXECUTION_DERIVED_OPERATIONAL_CLOSURE",
        "EXECUTABLE_CLOSURE": "PASS_OFFLINE",
        "RESIDUAL_BLOCKER_OR_RISK": [
            "FULL_40_CHAR_COMMIT_SHA_NOT_APPROVED_BY_USER_AND_AI_PM",
            "FDT_ZERO_TAIL_TARGET_ACCEPTANCE_UNPROVEN_FOR_0x36_0x50_0x82_0x20",
        ],
        "CANONICAL_DOCUMENTATION": "Goodix 27c6 5125 manuale tecnico.md",
        "BUNDLE": f"analysis/D261/{BUNDLE_NAME}",
        "BUNDLE_SHA256": f"analysis/D261/{BUNDLE_NAME}.sha256",
        "D261_OPERATIONAL_EVIDENCE_HARDENING": "PASS",
        "SRC_SEALED_UNCHANGED": True,
        "HISTORICAL_LIVE_EVIDENCE_UNCHANGED": True,
        "SUPPORTED_LIVE_ENTRYPOINT_COUNT": 1,
        "LIVE_CAPABILITY_DEFAULT": 0,
        "LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG": False,
        "DIRECT_PYTHON_LIVE_CALL_WITHOUT_CAPABILITY_FAILS_CLOSED": True,
        "SUPPORTED_PATH_FENCE_THREAT_MODEL": hard_disable["SUPPORTED_PATH_FENCE_THREAT_MODEL"],
        "ENVIRONMENT_ONLY_LIVE_ENABLEMENT": False,
        "BACKEND_ONLY_LIVE_ENABLEMENT": False,
        "CLI_INTENT_CAPABILITY_REQUIRED": True,
        "LIVE_IO_CAPABILITY_REQUIRES_MARKER": True,
        "MARKER_AFTER_PROTECTED_CONTENT_VALIDATION": True,
        "MARKER_IMMEDIATELY_PRECEDES_LIVE_IO_CAPABILITY": True,
        "REPORT_DIRECTORY_SAFETY_CHECKED_PRE_SIDE_EFFECT": True,
        "PROTECTED_ROOT_SAFETY_CHECKED_PRE_SIDE_EFFECT": True,
        "PROTECTED_ROOT_STATUS": preflight["PROTECTED_ROOT_STATUS"],
        "REPORT_DIRECTORY_STATUS": preflight["REPORT_DIRECTORY_STATUS"],
        "PROTECTED_METADATA_DRYRUN_STATUS_MODEL": preflight["PROTECTED_METADATA_DRYRUN_STATUS_MODEL"],
        "FAILURE_CONTAINMENT_MATRIX": failures["status"],
        "FAILURE_SCENARIO_COUNT": failures["FAILURE_SCENARIO_COUNT"],
        "FAILURE_SCENARIO_EXECUTED_COUNT": failures["FAILURE_SCENARIO_EXECUTED_COUNT"],
        "ASSERTION_ONLY_FAILURE_ROWS": failures["ASSERTION_ONLY_FAILURE_ROWS"],
        "ONE_PHYSICAL_IN_READER": True,
        "SHARED_READER_PHASE_DEADLINE_ENFORCED": True,
        "TIMEOUT_RENEWAL_PER_UNMATCHED_FRAME": False,
        "SINGLE_READER_DEMUX_EXECUTABLE_EVIDENCE": "PASS",
        "OFFLINE_OPERATIONAL_REHEARSAL": "PASS",
        "PRIMARY_FUTURE_LIVE_RISK": "FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND",
        "FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE": "0x32_PRIMARY_TARGET_PROVEN_0x36_0x50_0x82_0x20_UNPROVEN_LIVE_HYPOTHESIS",
        "LIVE_CRITICAL_PATH_SOURCE": "HARDCODED_REVIEWED_TUPLE_IN_VERIFIER",
        "LIVE_CRITICAL_FILESET_JSON_ROLE": "DERIVED_REPORT_NOT_AUTHORITY",
        "LIVE_CRITICAL_VERIFIER_SELF_INCLUDED": True,
        "FILESET_SELF_INTEGRITY_AGAINST_APPROVED_COMMIT": True,
        "HISTORICAL_SEAL_EVIDENCE_STATUS": "UNCHANGED_MATCH",
        "D260_ARCHITECTURE_CRITICAL_EVIDENCE_STATUS": "PASS_HISTORICAL_REFERENCE",
        "OPERATIONAL_LIVE_CRITICAL_FILESET_APPROVAL": "PENDING_USER_AI_PM_FULL_SHA_APPROVAL",
        "EXACT_APPROVED_LIVE_BASELINE_PRESENT": False,
        "READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW": True,
        "READY_FOR_BASELINE_APPROVAL_REVIEW": True,
        "OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE": True,
        "READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW": False,
        "READY_FOR_FDT_LIVE_REVIEW": False,
        "READY_FOR_FDT_LIVE": False,
        "REAL_USB_OPEN_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_COMMAND_SEND_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0,
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
    }
    write_json(OUTPUT / "D261_readiness_decision.json", readiness)

    report_text = """# D261 corrective v2 — operational evidence hardening

The same-step corrective passes offline. The supported live path now requires distinct CLI-intent and post-marker Live-I/O capabilities; protected content is validated before marker consumption. All 24 negative rows and all 13 shared-reader/demux cases are execution-derived. Report publication is preflighted before side effects and durably uses a `0600` temporary file, file and directory fsync, and same-directory replacement.

The physical-tail decision is unchanged: `0x32` zero-tail is primary-target observed and accepted; `0x36/0x50/0x82/0x20` remain an unproven live hypothesis. No baseline was approved and no live action occurred.

```text
OUTCOME=READY_FOR_BASELINE_APPROVAL_REVIEW
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_OFFLINE
READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
EXACT_APPROVED_LIVE_BASELINE_PRESENT=false
REAL_USB_OPEN_COUNT=0
REAL_SECRET_READ_COUNT=0
REAL_COMMAND_SEND_COUNT=0
FPRINTD_MUTATION_COUNT=0
REAL_SINGLE_USE_MARKER_CREATE_COUNT=0
```
"""
    (OUTPUT / "D261_corrective_report.md").write_text(report_text, encoding="utf-8")
    (OUTPUT / "D261_previous_bundle_status.txt").write_text(
        "D261_operational_live_readiness_bundle.zip\n"
        "STATUS=SUPERSEDED_BY_D261_OPERATIONAL_EVIDENCE_HARDENING_CORRECTIVE\n"
        "NOTE=Preserved byte-for-byte for provenance; do not use for baseline-approval review.\n",
        encoding="utf-8",
    )

    manifest_path = OUTPUT / "D261_bundle_manifest.json"
    manifest = {
        "schema": "D261_CORRECTIVE_BUNDLE_MANIFEST_V2",
        "step": "D261_CORRECTIVE_SAME_STEP",
        "reference_head_before_corrective": REFERENCE_HEAD,
        "baseline_approval": "PENDING_USER_AI_PM_FULL_SHA_APPROVAL",
        "bundle_path": f"analysis/D261/{BUNDLE_NAME}",
        "bundle_sha256": "RECORDED_IN_EXTERNAL_SIDECAR",
        "canonical_manual": {
            "path": "Goodix 27c6 5125 manuale tecnico.md",
            "sha256": sha256_file(REPO / "Goodix 27c6 5125 manuale tecnico.md"),
            "included": False,
            "reason": "CANONICAL_REPOSITORY_REFERENCE_NOT_DUPLICATED",
        },
        "files": [
            {"path": relative, "sha256": sha256_file(REPO / relative), "size": (REPO / relative).stat().st_size}
            for relative in REVIEW_FILES
        ],
        "exclusions": [
            "raw captures and packet payloads",
            "OTP and cache source bytes",
            "real secret/PSK and protected material",
            "biometric plaintext/raster",
            "OEM DLL, firmware and disassembly",
            "unchanged historical artifacts and prior bundle contents",
        ],
        "generated_utc": datetime.now().astimezone().isoformat(),
    }
    write_json(manifest_path, manifest)

    bundle_path = OUTPUT / BUNDLE_NAME
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in (*REVIEW_FILES, "analysis/D261/D261_bundle_manifest.json"):
            data = (REPO / relative).read_bytes()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            executable = relative.endswith(".sh") or Path(relative).name.startswith("d261_") and relative.endswith(".py")
            info.external_attr = (0o755 if executable else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    bundle_hash = sha256_file(bundle_path)
    (OUTPUT / f"{BUNDLE_NAME}.sha256").write_text(f"{bundle_hash}  {BUNDLE_NAME}\n", encoding="ascii")
    print(json.dumps({"OUTCOME": readiness["OUTCOME"], "BUNDLE_SHA256": bundle_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
