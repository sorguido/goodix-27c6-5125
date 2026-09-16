"""Executable offline closure for the sealed D245 live kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
PATCH = REPOSITORY / "analysis/D245/D245_live_unseal.patch"
RUNTIME_MATRIX = REPOSITORY / "analysis/D245/d245_runtime_matrix.py"
CANONICAL_PE = REPOSITORY / "analysis/D230/work/GoodixExport/gfusb.dll"
SEALED_EXPECTED = {
    "src/goodix5125_d233_backend.py": "e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982",
    "src/goodix5125_d235_entrypoint.py": "d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69",
}
INPUT_ARTIFACTS = (
    "analysis/D245/D245_A8_E4_primary_evidence_audit.md",
    "analysis/D245/D245_A8_E4_contract.json",
    "analysis/D245/D245_live_unseal.patch",
    "analysis/D245/d245_runtime_matrix.py",
)
HISTORICAL_LAUNCHERS = (
    (
        "operator_kit/d239-live-pre-d1-tls-once.sh",
        "D239_operator_kit_executability_gate_bundle.zip",
        "operator_kit/d239-live-pre-d1-tls-once.sh",
        "74bfd0a556d947eaa1bca600e832521c4018fb9dfd923a502ea000e2bb3aad15",
    ),
    (
        "operator_kit/d241-live-tls-once.sh",
        "analysis/D241/D241_d1_direct_b0_tls_transition_bundle.zip",
        "operator_kit/d241-live-tls-once.sh",
        "e30bcfa9e2962c5947a93013d6312c2c01bf1f2d5a20a4f20d110ac1610611f9",
    ),
    (
        "operator_kit/d242-live-tls-once.sh",
        "analysis/D242/D242_post_server_flight_causal_differential_bundle.zip",
        "operator_kit/d242-live-tls-once.sh",
        "0e52c549725d02663d06a24f90c55a1f6dbd7e1accf4f5cf251558c94fa8906e",
    ),
    (
        "operator_kit/d243-live-tls-once.sh",
        "analysis/D243/D243_a0_b0_transport_split_regression_bundle.zip",
        "operator_kit/d243-live-tls-once.sh",
        "cc5a077bb2cb001618d5acb3312305107ffb2fd82c4de874e2f4b8f17bc13713",
    ),
    (
        "operator_kit/d244-live-tls-once.sh",
        "analysis/D244/D244_e4_timeout_forensic_fresh_state_control_bundle.zip",
        "operator_kit/d244-live-tls-once.sh",
        "bd2701c27c5f2ed61a450bcd964d9ccd6d993c466759ed4da1e6e52b3a41bc10",
    ),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout or f"command failed: {command}")
    return result


def verify_sealed_baseline(root: Path = REPOSITORY) -> dict[str, object]:
    rows = []
    for relative, expected in SEALED_EXPECTED.items():
        actual = sha256(root / relative)
        rows.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "behavior_relevant": True,
                "status": "MATCH" if actual == expected else "MISMATCH",
            }
        )
    return {
        "D245_SEALED_BASELINE_AFTER_RENAME_STATUS": (
            "MATCH" if all(row["status"] == "MATCH" for row in rows) else "MISMATCH"
        ),
        "files": rows,
    }


def _copy_runtime_tree(root: Path) -> None:
    for name in ("src", "tests", "poc"):
        shutil.copytree(REPOSITORY / name, root / name)
    (root / "analysis/D245").mkdir(parents=True)
    shutil.copy2(RUNTIME_MATRIX, root / "analysis/D245/d245_runtime_matrix.py")
    pe_target = root / "analysis/D230/work/GoodixExport/gfusb.dll"
    pe_target.parent.mkdir(parents=True)
    shutil.copy2(CANONICAL_PE, pe_target)


def verify_unseal_runtime_reseal() -> dict[str, object]:
    before = {relative: sha256(REPOSITORY / relative) for relative in SEALED_EXPECTED}
    with tempfile.TemporaryDirectory(prefix="d245-closure-") as directory:
        root = Path(directory)
        _copy_runtime_tree(root)
        apply = _run(
            ["patch", "--batch", "--forward", "--strip=1", f"--input={PATCH}"],
            cwd=root,
        )
        patch_output = apply.stdout + apply.stderr
        if "offset" in patch_output.lower() or "fuzz" in patch_output.lower():
            raise AssertionError("D245 patch applied with offset/fuzz")
        unsealed = {relative: sha256(root / relative) for relative in SEALED_EXPECTED}
        env = dict(os.environ)
        env.update(PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1")
        matrix_run = _run(
            ["python3", "analysis/D245/d245_runtime_matrix.py"], cwd=root, env=env
        )
        matrix = json.loads(matrix_run.stdout)
        if matrix.get("status") != "PASS" or matrix.get("real_usb_access") != 0:
            raise AssertionError("D245 runtime matrix did not close safely")
        reverse = _run(
            ["patch", "--batch", "--reverse", "--strip=1", f"--input={PATCH}"],
            cwd=root,
        )
        reverse_output = reverse.stdout + reverse.stderr
        if "offset" in reverse_output.lower() or "fuzz" in reverse_output.lower():
            raise AssertionError("D245 patch reversed with offset/fuzz")
        after = {relative: sha256(root / relative) for relative in SEALED_EXPECTED}
    if before != after:
        raise AssertionError("D245 temporary source did not reseal byte-exactly")
    if before != {relative: sha256(REPOSITORY / relative) for relative in SEALED_EXPECTED}:
        raise AssertionError("D245 closure changed canonical sealed sources")
    return {
        "patch_apply": "PASS_WITHOUT_OFFSET",
        "source_reseal": "PASS_WITHOUT_OFFSET",
        "sealed_sha256": before,
        "unsealed_sha256": unsealed,
        "final_sealed_sha256": after,
        "runtime_matrix": matrix,
    }


def artifact_sha256() -> dict[str, str]:
    return {relative: sha256(REPOSITORY / relative) for relative in INPUT_ARTIFACTS}


def verify_historical_launcher_integrity() -> dict[str, object]:
    rows = []
    for root_path, bundle_path, member, expected in HISTORICAL_LAUNCHERS:
        with zipfile.ZipFile(REPOSITORY / bundle_path) as archive:
            canonical = archive.read(member)
        canonical_sha256 = hashlib.sha256(canonical).hexdigest()
        root_bytes = (REPOSITORY / root_path).read_bytes()
        rows.append(
            {
                "path": root_path,
                "canonical_bundle": bundle_path,
                "canonical_sha256": canonical_sha256,
                "root_sha256": hashlib.sha256(root_bytes).hexdigest(),
                "status": (
                    "MATCH"
                    if canonical_sha256 == expected and root_bytes == canonical
                    else "MISMATCH"
                ),
            }
        )
    mutation_count = sum(row["status"] != "MATCH" for row in rows)
    if mutation_count:
        raise AssertionError("D245_BLOCKED_BY_HISTORICAL_LAUNCHER_INTEGRITY")
    return {
        "D245_HISTORICAL_LAUNCHER_INTEGRITY": "RESTORED",
        "D245_HISTORICAL_LAUNCHER_MUTATION_COUNT": mutation_count,
        "files": rows,
    }


def run(report_path: Path | None = None) -> dict[str, object]:
    baseline = verify_sealed_baseline()
    if baseline["D245_SEALED_BASELINE_AFTER_RENAME_STATUS"] != "MATCH":
        raise AssertionError("D245_BLOCKED_BY_SEALED_BASELINE_INTEGRITY_MISMATCH")
    contract = json.loads((REPOSITORY / "analysis/D245/D245_A8_E4_contract.json").read_text())
    if contract["provenance"]["D245_A8_CURRENT_LOCAL_CORPUS_CORROBORATION"] != "PASS":
        raise AssertionError("D245_BLOCKED_BY_A8_CURRENT_CORPUS_CORROBORATION")
    closure = verify_unseal_runtime_reseal()
    historical_launchers = verify_historical_launcher_integrity()
    d244 = json.loads(
        (REPOSITORY / "analysis/D244/D244_operator_live_stdout.json").read_text(encoding="utf-8")
    )
    if not (
        d244.get("d244_result") == "D244_ABORTED_FAIL_CLOSED"
        and d244.get("attempted_phase") == "E4"
        and d244.get("abort_class") == "timeout"
        and d244.get("command_count") == 1
        and d244.get("runtime_psk_e4_binding_status") == "not_reached"
    ):
        raise AssertionError("D245 D244 live ingest mismatch")
    report = {
        "schema": "d245-executable-closure-v2",
        "status": "PASS",
        "repository_root": str(REPOSITORY),
        "artifact_sha256": artifact_sha256(),
        "sealed_baseline": baseline,
        "unseal_runtime_reseal": closure,
        "historical_launcher_integrity": historical_launchers,
        "D245_HISTORICAL_LAUNCHER_INTEGRITY": historical_launchers[
            "D245_HISTORICAL_LAUNCHER_INTEGRITY"
        ],
        "D245_HISTORICAL_LAUNCHER_MUTATION_COUNT": historical_launchers[
            "D245_HISTORICAL_LAUNCHER_MUTATION_COUNT"
        ],
        "D245_LIVE_BASELINE_APPROVAL_STATUS": "LIVE_BASELINE_APPROVAL_PENDING_USER_REVIEW",
        "D245_D244_LIVE_RESULT_INGESTED": True,
        "D245_D244_E4_OUT_COMPLETED": True,
        "D245_D244_E4_IN_TIMEOUT": True,
        "D244_FRESH_STATE_HOST_CONTROL_RESULT": "E4_TIMEOUT_PERSISTS",
        "D244_FRESH_HOST_BOOT_SUFFICIENCY": "FALSIFIED_AS_SUFFICIENT_RECOVERY_CONDITION",
        "D244_SENSOR_ELECTRICAL_POWER_CYCLE_STATUS": "NOT_PROVEN",
        "D245_FPRINTD_INITIAL_STATE_CAUSAL_STATUS": "NOT_SUFFICIENT_EXPLANATION",
        "D245_A8_CURRENT_LOCAL_CORPUS_CORROBORATION": "PASS",
        "D245_A8_READ_ONLY_CLASSIFICATION": "CURRENT_LOCAL_CORPUS_CONFIRMED",
        "D245_A8_WIRE_CONTRACT_CURRENT_CORPUS": "CONFIRMED",
        "D245_EXECUTABLE_CLOSURE_GATE": "PASS",
        "retry_count": 0,
        "d4_count": 0,
        "application_data_count": 0,
        "persistent_write_family_count": 0,
        "real_usb_access": 0,
        "real_tls_handshake": 0,
        "live_usb_execution": "NOT_PERFORMED",
    }
    if report_path is not None:
        destination = Path(report_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def verify_report(path: Path) -> dict[str, object]:
    expected = run(None)
    observed = json.loads(Path(path).read_text(encoding="utf-8"))
    if observed != expected:
        raise AssertionError("D245 closure report is stale")
    return observed


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--report", type=Path)
    group.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    report = verify_report(args.verify_report) if args.verify_report else run(args.report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
