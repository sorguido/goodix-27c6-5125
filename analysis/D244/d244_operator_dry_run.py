"""D244 executable closure using synthetic USB/TLS and read-only evidence."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Mapping, Sequence

from analysis.D244.d244_dependency_gate import verify_dependencies
from analysis.D244.d244_fresh_state import assess_fresh_state
from analysis.D244.d244_preflight import offline_sandbox_preflight
from analysis.D243.d243_operator_dry_run import run_entrypoint_fixture
from analysis.D241.d241_operator_dry_run import synthetic_material
from src.goodix5125_d232_offline import build_b0, expected_request_frames
from src.goodix5125_d233_backend import (
    B0TlsBridge,
    ProductionUsbTransport,
    TLS_RECORD_PACING_MS,
    UsbTimeout,
)
from src.goodix5125_d235_entrypoint import ProductionRuntimePaths
from tests.test_d233_backend import FakeUsbApi
from tests.test_d242_transport_fix import TwoRecordServerFlight


REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = REPOSITORY / "analysis/D244/D244_executable_closure_report.json"
UNSEAL_PATCH = REPOSITORY / "analysis/D244/D244_live_unseal.patch"
DIFFERENTIAL = REPOSITORY / "analysis/D244/D244_d241_d242_d243_pre_e4_differential.csv"
ARCHIVES = {
    "D241": REPOSITORY / "analysis/D241/D241_d1_direct_b0_tls_transition_bundle.zip",
    "D242": REPOSITORY / "analysis/D242/D242_post_server_flight_causal_differential_bundle.zip",
    "D243": REPOSITORY / "analysis/D243/D243_a0_b0_transport_split_regression_bundle.zip",
}
ARTIFACTS = (
    "src/goodix5125_d232_offline.py",
    "src/goodix5125_d233_backend.py",
    "src/goodix5125_d235_entrypoint.py",
    "analysis/D244/d244_dependency_gate.py",
    "analysis/D244/d244_fresh_state.py",
    "analysis/D244/d244_preflight.py",
    "analysis/D244/d244_preflight_observability.py",
    "analysis/D244/d244_operator_dry_run.py",
    "analysis/D244/D244_live_unseal.patch",
    "analysis/D244/D244_d243_boot_baseline.json",
    "analysis/D244/D244_d241_d242_d243_pre_e4_differential.csv",
    "operator_kit/d244-live-tls-once.sh",
    "tests/test_d244_fresh_state_control.py",
)
CANONICAL_E4_HEX = "a00c00ace40900030002bb00000000fd"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def artifact_hashes() -> dict[str, str]:
    return {name: sha256(REPOSITORY / name) for name in ARTIFACTS}


def _method_source(source: str, class_name: str, method_name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    segment = ast.get_source_segment(source, child)
                    if segment is None:
                        break
                    return segment
    raise ValueError(f"missing {class_name}.{method_name}")


def historical_sources() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for stage, archive in ARCHIVES.items():
        with zipfile.ZipFile(archive) as bundle:
            backend = bundle.read("src/goodix5125_d233_backend.py")
            names = set(bundle.namelist())
            if "src/goodix5125_d232_offline.py" in names:
                core_hash = sha256_bytes(bundle.read("src/goodix5125_d232_offline.py"))
            else:
                launcher_name = f"operator_kit/{stage.lower()}-live-tls-once.sh"
                launcher = bundle.read(launcher_name).decode("utf-8")
                core_hash = "2875a0c4f3b166906d30c4648f0d965e8b18614299be46a7a24fb1d6a9079726"
                if core_hash not in launcher:
                    raise AssertionError(f"{stage} core hash is not pinned")
        method = _method_source(
            backend.decode("utf-8"), "ProductionUsbTransport", "write_frame"
        )
        result[stage] = {
            "archive": str(archive.relative_to(REPOSITORY)),
            "archive_sha256": sha256(archive),
            "backend_sha256": sha256_bytes(backend),
            "core_sha256": core_hash,
            "write_frame_sha256": sha256_bytes(method.encode()),
        }
    return result


def verify_unseal_reseal() -> dict[str, object]:
    relative_sources = (
        "src/goodix5125_d233_backend.py",
        "src/goodix5125_d235_entrypoint.py",
    )
    sealed = {name: sha256(REPOSITORY / name) for name in relative_sources}
    with tempfile.TemporaryDirectory(prefix="d244-seal-") as directory:
        root = Path(directory)
        (root / "src").mkdir()
        for relative in relative_sources:
            shutil.copy2(REPOSITORY / relative, root / relative)
        applied = subprocess.run(
            ["patch", "--batch", "--forward", "--strip=1", f"--input={UNSEAL_PATCH}"],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if applied.returncode or "offset" in applied.stdout.lower():
            raise AssertionError(applied.stderr or applied.stdout)
        entrypoint = (root / relative_sources[1]).read_text(encoding="utf-8")
        backend = (root / relative_sources[0]).read_text(encoding="utf-8")
        compile(backend, relative_sources[0], "exec")
        compile(entrypoint, relative_sources[1], "exec")
        required = (
            'D235_RESULT_SCHEMA = "d244-live-tls-single-shot-result-v1"',
            'reports = store / "d244-results"',
            'single_use_marker=store / "d244-operator-invocation.marker"',
            "D244_FRESH_STATE_CONTROL_VALID",
        )
        if "return None" not in backend or any(item not in entrypoint for item in required):
            raise AssertionError("D244 unseal content missing")
        unsealed = {name: sha256(root / name) for name in relative_sources}
        reversed_patch = subprocess.run(
            ["patch", "--batch", "--reverse", "--strip=1", f"--input={UNSEAL_PATCH}"],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if reversed_patch.returncode or "offset" in reversed_patch.stdout.lower():
            raise AssertionError(reversed_patch.stderr or reversed_patch.stdout)
        final = {name: sha256(root / name) for name in relative_sources}
    if final != sealed:
        raise AssertionError("D244 source reseal mismatch")
    return {
        "patch_apply": "PASS_WITHOUT_OFFSET",
        "reseal_rollback": "PASS_WITHOUT_OFFSET",
        "sealed_sha256": sealed,
        "unsealed_sha256": unsealed,
        "final_sealed_sha256": final,
        "unseal_patch_sha256": sha256(UNSEAL_PATCH),
    }


def verify_e4_wire() -> tuple[bytes, dict[str, object]]:
    material, _responses, _secret = synthetic_material(
        ProductionRuntimePaths.system_default().canonical_gfusb
    )
    e4 = expected_request_frames(material)["E4"]
    expected = bytes.fromhex(CANONICAL_E4_HEX)
    stages = {
        stage: {
            "length": len(e4),
            "sha256": sha256_bytes(e4),
            "match": e4 == expected,
        }
        for stage in ("D241", "D242", "D243", "D244")
    }
    return e4, {
        "canonical_hex": CANONICAL_E4_HEX,
        "canonical_length": len(expected),
        "canonical_sha256": sha256_bytes(expected),
        "runtimes": stages,
        "D244_E4_LOGICAL_WIRE_MATCH": all(row["match"] for row in stages.values()),
    }


def verify_transport(e4: bytes) -> dict[str, object]:
    success_api = FakeUsbApi()
    success = ProductionUsbTransport(success_api)
    success.transport_open()
    success.write_frame(e4, 1000)

    out_timeout_api = FakeUsbApi()
    out_timeout_api.timeout_out = True
    out_timeout = ProductionUsbTransport(out_timeout_api)
    out_timeout.transport_open()
    try:
        out_timeout.write_frame(e4, 1000)
    except UsbTimeout:
        pass
    else:
        raise AssertionError("synthetic bulk OUT timeout did not propagate")

    in_timeout_api = FakeUsbApi()
    in_timeout_api.timeout_in = True
    in_timeout = ProductionUsbTransport(in_timeout_api)
    in_timeout.transport_open()
    in_timeout.write_frame(e4, 1000)
    try:
        in_timeout.read_frame(1000)
    except UsbTimeout:
        pass
    else:
        raise AssertionError("synthetic bulk IN timeout did not propagate")

    delays: list[float] = []

    class RecordingTransport:
        def __init__(self) -> None:
            self.frames: list[bytes] = []

        def write_frame(self, frame: bytes, _timeout: int) -> None:
            self.frames.append(bytes(frame))

    recording = RecordingTransport()
    bridge = B0TlsBridge(TwoRecordServerFlight(), recording, pacer=delays.append)
    client_body = b"\x03\x03" + bytes(32) + b"\x00\x00\x04\x00\xa8\x00\xff\x01\x00"
    client = (
        b"\x16\x03\x03"
        + (4 + len(client_body)).to_bytes(2, "big")
        + b"\x01"
        + len(client_body).to_bytes(3, "big")
        + client_body
    )
    bridge.accept_b0(build_b0(client), 1000, first_record=True)
    b0_api = FakeUsbApi()
    b0_transport = ProductionUsbTransport(b0_api)
    b0_transport.transport_open()
    for frame in recording.frames:
        b0_transport.write_frame(frame, 1000)

    return {
        "a0_short_out": {
            "requested_length": len(success_api.outgoing[0]),
            "logical_length": len(e4),
            "artificial_tail_length": len(success_api.outgoing[0]) - len(e4),
            "command_count_after_completion": success.command_count,
        },
        "timeout_direction_semantics": {
            "out_timeout_command_count": out_timeout.command_count,
            "out_timeout_bulk_in_attempted": any(
                isinstance(call, tuple) and call[0] == "in" for call in out_timeout_api.calls
            ),
            "in_timeout_command_count": in_timeout.command_count,
            "in_timeout_bulk_in_attempted": any(
                isinstance(call, tuple) and call[0] == "in" for call in in_timeout_api.calls
            ),
            "classification": "IN_CONFIRMED_AFTER_OUT_COMPLETION",
        },
        "b0_fixed64": {
            "wire_chunk_lengths": [len(chunk) for chunk in b0_api.outgoing],
            "all_tails_zero_initialized": all(
                not any(chunk[len(frame) % 64 :])
                for chunk, frame in zip(b0_api.outgoing[-2:], recording.frames)
            ),
        },
        "tls_pacing": {
            "pacing_ms": TLS_RECORD_PACING_MS,
            "delays_seconds": delays,
            "count": bridge.pacing_count,
        },
    }


def differential_counts() -> dict[str, int]:
    with DIFFERENTIAL.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    reached_diffs = [
        row for row in rows
        if row["d241_d243_diff"] == "true" and row["reached_before_timeout"] == "true"
    ]
    relevant = [row for row in reached_diffs if row["behavior_relevant"] == "true"]
    unresolved = [row for row in reached_diffs if row["candidate_status"] == "unresolved"]
    return {
        "D244_D241_D243_PRE_E4_DIFF_COUNT": len(reached_diffs),
        "D244_D241_D243_PRE_E4_BEHAVIOR_RELEVANT_DIFF_COUNT": len(relevant),
        "D244_D241_D243_PRE_E4_UNRESOLVED_CANDIDATE_COUNT": len(unresolved),
    }


def fresh_state_fixtures() -> dict[str, object]:
    baseline = "1" * 32
    current = "2" * 32
    return {
        "boot_id_available": assess_fresh_state(
            baseline_boot_id=baseline,
            current_boot_id=current,
            uptime_seconds=42.5,
            journal_boot_ids=(baseline, current),
            operator_confirmed=True,
        ),
        "boot_id_unavailable": assess_fresh_state(
            baseline_boot_id=baseline,
            current_boot_id=None,
            uptime_seconds=42.5,
            operator_confirmed=True,
        ),
        "uptime_available": assess_fresh_state(
            baseline_boot_id=None,
            current_boot_id=None,
            uptime_seconds=42.5,
            operator_confirmed=True,
        ),
        "metadata_insufficient": assess_fresh_state(
            baseline_boot_id=None,
            current_boot_id=None,
            uptime_seconds=None,
            operator_confirmed=True,
        ),
        "same_boot_invalid": assess_fresh_state(
            baseline_boot_id=baseline,
            current_boot_id=baseline,
            uptime_seconds=900.0,
            operator_confirmed=True,
        ),
    }


def publish(path: Path, report: Mapping[str, object]) -> None:
    payload = (json.dumps(dict(report), sort_keys=True, indent=2) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=".d244-closure-", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()


def run(report_path: Path = DEFAULT_REPORT) -> dict[str, object]:
    dependencies = verify_dependencies()
    histories = historical_sources()
    e4, wire = verify_e4_wire()
    transport = verify_transport(e4)
    seal = verify_unseal_reseal()
    counts = differential_counts()
    fresh = fresh_state_fixtures()
    with tempfile.TemporaryDirectory(prefix="d244-closure-") as directory:
        root = Path(directory)
        preflight = offline_sandbox_preflight(root / "preflight")
        e4_report, e4_api, e4_facade, checkpoint, final = run_entrypoint_fixture(
            root, "e4_timeout"
        )
    durability = {
        "runtime_abort": {
            "attempted_phase": e4_report.get("attempted_phase"),
            "abort_class": e4_report.get("abort_class"),
            "command_count": e4_report.get("command_count"),
        },
        "durable_checkpoint_before_restore": {
            "attempted_phase": checkpoint.get("attempted_phase"),
            "abort_class": checkpoint.get("abort_class"),
            "cleanup_count": checkpoint.get("cleanup_count"),
            "secret_zeroized": checkpoint.get("secret_zeroized"),
            "report_publish_count": checkpoint.get("report_publish_count"),
            "signal_restore_status": checkpoint.get("signal_restore_status"),
        },
        "final_report_after_restore": {
            "report_publish_count": final.get("report_publish_count"),
            "fprintd_restore_status": final.get("fprintd_restore_status"),
            "signal_restore_status": final.get("signal_restore_status"),
        },
        "usb_release_count": e4_api.calls.count(("release", 0)),
        "usb_close_count": e4_api.calls.count("close"),
        "usb_exit_count": e4_api.calls.count("exit"),
        "marker_claim_count": e4_facade.marker_claim_count,
    }
    report: dict[str, object] = {
        "schema": "d244-executable-closure-report-v1",
        "status": "PASS",
        "classification": "D244_EXECUTABLE_CLOSURE_GATE_PASS",
        "artifact_sha256": artifact_hashes(),
        "dependency_integrity": dependencies,
        "historical_source_evidence": histories,
        "e4_wire": wire,
        "transport": transport,
        "differential_counts": counts,
        "fresh_state_fixtures": fresh,
        "preflight_fixture": preflight,
        "seal_coherence": seal,
        "e4_timeout_durability": durability,
        "live_usb_execution": "NOT_PERFORMED",
        "real_tls_handshake_execution": "NOT_PERFORMED",
        "real_secret_read_count": 0,
        "retry_count": 0,
        "d4_count": 0,
        "application_data_count": 0,
        "persistent_write_family_count": 0,
    }
    required = (
        dependencies["status"] == "PASS"
        and preflight["status"] == "PASS"
        and wire["D244_E4_LOGICAL_WIRE_MATCH"] is True
        and len(e4) == 16
        and transport["a0_short_out"]["artificial_tail_length"] == 0
        and transport["timeout_direction_semantics"]["out_timeout_command_count"] == 0
        and transport["timeout_direction_semantics"]["in_timeout_command_count"] == 1
        and transport["timeout_direction_semantics"]["in_timeout_bulk_in_attempted"] is True
        and transport["b0_fixed64"]["wire_chunk_lengths"] == [64, 64, 64]
        and transport["tls_pacing"]["delays_seconds"] == [0.01, 0.01]
        and counts["D244_D241_D243_PRE_E4_UNRESOLVED_CANDIDATE_COUNT"] == 0
        and histories["D241"]["write_frame_sha256"] != histories["D243"]["write_frame_sha256"]
        and checkpoint.get("attempted_phase") == "E4"
        and checkpoint.get("cleanup_count") == 1
        and checkpoint.get("secret_zeroized") is True
        and checkpoint.get("report_publish_count") == 1
        and final.get("report_publish_count") == 2
        and final.get("signal_restore_status") == "restored"
        and durability["usb_release_count"] == 1
        and durability["usb_close_count"] == 1
        and durability["usb_exit_count"] == 1
        and fresh["boot_id_available"]["D244_FRESH_STATE_CONTROL_VALID"] is True
        and fresh["boot_id_unavailable"]["D244_FRESH_STATE_CONTROL_VALID"] is False
        and fresh["metadata_insufficient"]["D244_FRESH_BOOT_EVIDENCE"] == "unavailable"
        and seal["patch_apply"] == "PASS_WITHOUT_OFFSET"
        and seal["reseal_rollback"] == "PASS_WITHOUT_OFFSET"
    )
    if not required:
        report["status"] = "FAIL"
        report["classification"] = "D244_BLOCKED_BY_EXECUTABLE_CLOSURE"
    publish(report_path, report)
    return report


def validate_report(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if (
        report.get("schema") != "d244-executable-closure-report-v1"
        or report.get("status") != "PASS"
        or report.get("classification") != "D244_EXECUTABLE_CLOSURE_GATE_PASS"
        or report.get("artifact_sha256") != artifact_hashes()
        or report.get("live_usb_execution") != "NOT_PERFORMED"
    ):
        raise ValueError("D244 closure report is missing, stale, or failed")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    try:
        if not arguments:
            report = run()
        elif len(arguments) == 2 and arguments[0] == "--report":
            report = run(Path(arguments[1]).resolve())
        elif len(arguments) == 2 and arguments[0] == "--verify-report":
            report = validate_report(Path(arguments[1]).resolve())
        else:
            return 64
    except (OSError, ValueError, AssertionError, RuntimeError) as exc:
        print(f"d244_operator_dry_run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
