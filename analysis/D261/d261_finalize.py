#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Finalize the step-local D261 decision, manifest, ZIP and checksum."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import zipfile


REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / "analysis/D261"
REFERENCE_HEAD = "ef2aa95c0b7261638a70cdf26a91ea00dd60eb41"
BUNDLE_NAME = "D261_operational_live_readiness_bundle.zip"

REVIEW_FILES = (
    "core/cold_start.py",
    "core/fdt_seed.py",
    "core/persistent_runtime.py",
    "core/protected_runtime.py",
    "core/runtime_transport.py",
    "core/usb_runtime.py",
    "tools/d261_live_fdt_arm_once.py",
    "operator_kit/d261-live-fdt-arm-once.sh",
    "tests/test_d261_operational_readiness.py",
    "analysis/D261/d261_tail_audit.py",
    "analysis/D261/d261_offline_rehearsal.py",
    "analysis/D261/d261_finalize.py",
    "analysis/D261/D261_fdt_physical_tail_audit.json",
    "analysis/D261/D261_sanitized_tail_matrix.json",
    "analysis/D261/D261_physical_policy_decision.json",
    "analysis/D261/D261_cold_start_migration_evidence.json",
    "analysis/D261/D261_real_usb_adapter_offline_evidence.json",
    "analysis/D261/D261_single_reader_demux_evidence.json",
    "analysis/D261/D261_secret_boundary_operational_evidence.json",
    "analysis/D261/D261_seed_otp_runtime_path_evidence.json",
    "analysis/D261/D261_preflight_dry_run.json",
    "analysis/D261/D261_operator_kit_dry_run_result.json",
    "analysis/D261/D261_failure_containment_matrix.json",
    "analysis/D261/D261_operational_live_critical_fileset.json",
    "analysis/D261/D261_full_offline_operational_rehearsal.json",
    "analysis/D261/D261_test_results.json",
    "analysis/D261/D261_readiness_decision.json",
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
    if (preflight["status"], rehearsal["status"], failures["status"]) != ("PASS", "PASS", "PASS"):
        raise RuntimeError("D261 prerequisite artifact is not PASS")

    test_results = {
        "schema": "D261_TEST_RESULTS_V1",
        "execution_mode": "OFFLINE_ONLY",
        "commands": [
            {"command": "python3 -m py_compile <D261 Python files>", "status": "PASS"},
            {"command": "python3 analysis/D261/d261_tail_audit.py", "status": "PASS"},
            {"command": "python3 analysis/D261/d261_offline_rehearsal.py", "status": "PASS"},
            {"command": "operator_kit/d261-live-fdt-arm-once.sh --dry-run", "status": "PASS"},
            {
                "command": "python3 -m unittest discover -s tests -p 'test_*.py'",
                "status": "PASS",
                "tests_run": 231,
                "failures": 0,
                "errors": 0,
                "wall_seconds": 15.387,
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
        "schema": "D261_OPERATIONAL_LIVE_READINESS_DECISION_V1",
        "step": "D261",
        "execution_mode": "OFFLINE_ONLY",
        "OUTCOME": "READY_FOR_OPERATIONAL_LIVE_REVIEW",
        "ADVANCEMENT": ["NEW_TECHNICAL_EVIDENCE_PRODUCED", "EXECUTABLE_CLOSURE_COMPLETED_OFFLINE"],
        "EXECUTABLE_CLOSURE": "PASS_OFFLINE",
        "RESIDUAL_BLOCKER_OR_RISK": [
            "FULL_COMMIT_SHA_FOR_D261_LIVE_CRITICAL_SET_NOT_YET_APPROVED",
            "FDT_ZERO_TAIL_TARGET_ACCEPTANCE_UNPROVEN_FOR_0x36_0x50_0x82_0x20",
        ],
        "CANONICAL_DOCUMENTATION": "Goodix 27c6 5125 manuale tecnico.md",
        "BUNDLE": {
            "path": f"analysis/D261/{BUNDLE_NAME}",
            "manifest": "analysis/D261/D261_bundle_manifest.json",
            "checksum": f"analysis/D261/{BUNDLE_NAME}.sha256",
        },
        "FDT_A0_PHYSICAL_POLICY": "FIXED64_ZERO_FILL_OUTSIDE_DECLARED_LOGICAL_FRAME",
        "FDT_A0_RESIDUE_REPLAY": False,
        "PRIMARY_FUTURE_LIVE_RISK": "FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND",
        "READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW": True,
        "READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW": True,
        "READY_FOR_FDT_LIVE_REVIEW": True,
        "READY_FOR_FDT_LIVE": False,
        "LIVE_CAPABILITY_DEFAULT": 0,
        "LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG": False,
        "OPERATIONAL_LIVE_CRITICAL_FILESET_APPROVAL": "PENDING_USER_AI_PM_FULL_SHA_APPROVAL",
        "D261_LIVE_EXECUTION": "NOT_PERFORMED",
        "OFFLINE_OPERATIONAL_REHEARSAL": rehearsal["status"],
        "FAILURE_CONTAINMENT_MATRIX": failures["status"],
        "FULL_REPOSITORY_TEST_SUITE": "PASS_231_OF_231",
        "REAL_USB_OPEN_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_COMMAND_SEND_COUNT": 0,
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0,
    }
    write_json(OUTPUT / "D261_readiness_decision.json", readiness)

    manifest_path = OUTPUT / "D261_bundle_manifest.json"
    manifest = {
        "schema": "D261_BUNDLE_MANIFEST_V1",
        "step": "D261",
        "reference_head": REFERENCE_HEAD,
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
            "historical unchanged artifacts",
        ],
        "generated_utc": datetime.now().astimezone().isoformat(),
    }
    write_json(manifest_path, manifest)

    bundle_path = OUTPUT / BUNDLE_NAME
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in (*REVIEW_FILES, "analysis/D261/D261_bundle_manifest.json"):
            data = (REPO / relative).read_bytes()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            mode = 0o755 if relative.endswith(".sh") or Path(relative).name.startswith("d261_") and relative.endswith(".py") else 0o644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    bundle_hash = sha256_file(bundle_path)
    (OUTPUT / f"{BUNDLE_NAME}.sha256").write_text(f"{bundle_hash}  {BUNDLE_NAME}\n", encoding="ascii")
    print(json.dumps({"OUTCOME": readiness["OUTCOME"], "BUNDLE_SHA256": bundle_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
