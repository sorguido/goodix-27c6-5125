"""D243 executable closure using only synthetic USB and TLS peers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

from analysis.D243.d243_dependency_gate import verify_dependencies

verify_dependencies()

from analysis.D241.d241_operator_dry_run import (
    FixtureUsbApi,
    LoopbackTlsUsbApi,
    OfflineFacade,
    SyntheticInputs,
    fixture_incoming,
    synthetic_material,
)
from analysis.D243.d243_preflight import offline_sandbox_preflight
from src.goodix5125_d232_offline import ContractError, DurableReportPublisher
from src.goodix5125_d233_backend import TLS_RECORD_PACING_MS, Tls12PskServer, UsbIdentity
from src.goodix5125_d235_entrypoint import (
    ProductionRuntimePaths,
    ResolvedUsbTarget,
    run_injected_offline_entrypoint_review,
)


REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = REPOSITORY / "analysis/D243/D243_executable_closure_report.json"
UNSEAL_PATCH = REPOSITORY / "analysis/D243/D243_live_unseal.patch"
ARTIFACTS = (
    "src/goodix5125_d232_offline.py",
    "src/goodix5125_d233_backend.py",
    "src/goodix5125_d235_entrypoint.py",
    "analysis/D243/d243_dependency_gate.py",
    "analysis/D243/d243_preflight.py",
    "analysis/D243/d243_preflight_observability.py",
    "analysis/D243/d243_operator_dry_run.py",
    "analysis/D243/D243_live_unseal.patch",
    "operator_kit/d243-live-tls-once.sh",
    "tests/test_d243_transport_split.py",
    "tests/test_d243_operator_kit.py",
)


class D243LoopbackTlsUsbApi(LoopbackTlsUsbApi):
    """Synthetic device that ignores only B0 fixed-64 zero staging tails."""

    def bulk_out(self, handle, endpoint, data, timeout_ms):
        result = FixtureUsbApi.bulk_out(self, handle, endpoint, data, timeout_ms)
        self._outgoing_stream.extend(data)
        while len(self._outgoing_stream) >= 4:
            total = 4 + int.from_bytes(self._outgoing_stream[1:3], "little")
            if len(self._outgoing_stream) < total:
                break
            frame = bytes(self._outgoing_stream[:total])
            del self._outgoing_stream[:total]
            self._handle_outgoing_frame(frame)
            if self._outgoing_stream and not any(self._outgoing_stream):
                self._outgoing_stream.clear()
        return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hashes() -> dict[str, str]:
    return {name: sha256(REPOSITORY / name) for name in ARTIFACTS}


def run_entrypoint_fixture(
    root: Path, scenario: str
) -> tuple[dict[str, object], FixtureUsbApi, OfflineFacade, dict[str, object], dict[str, object]]:
    production = ProductionRuntimePaths.system_default()
    material, responses, secret = synthetic_material(production.canonical_gfusb)
    case = root / scenario
    store, reports = case / "store", case / "reports"
    store.mkdir(parents=True)
    reports.mkdir(mode=0o700)
    reports.chmod(0o700)
    paths = ProductionRuntimePaths(
        psk_store=store / "synthetic-transport-material.bin",
        target_material_manifest=store / "synthetic-material-manifest.json",
        config90_store=store / "synthetic-config90.bin",
        canonical_gfusb=production.canonical_gfusb,
        report_directory=reports,
        checkpoint_report=reports / "d243-live-pre-restore.json",
        final_report=reports / "d243-live-result.json",
        single_use_marker=store / "d243-operator-invocation.marker",
    )
    identity = UsbIdentity(0x27C6, 0x5125, 1, 4, (7,))
    target = ResolvedUsbTarget(identity, Path("/dev/bus/usb/001/004"))
    facade = OfflineFacade()
    if scenario == "e4_timeout":
        api: FixtureUsbApi = FixtureUsbApi((), identity, timeout_when_empty=True)
    else:
        incoming = fixture_incoming(
            material,
            responses,
            fragment_first_b0=scenario == "server_flight_timeout",
            include_d1=scenario == "server_flight_timeout",
        )
        if scenario == "server_flight_timeout":
            api = FixtureUsbApi(incoming, identity, timeout_when_empty=True)
        elif scenario == "success":
            api = D243LoopbackTlsUsbApi(incoming, identity, secret)
        else:
            raise ValueError(f"unknown fixture scenario: {scenario}")
    report = run_injected_offline_entrypoint_review(
        offline_root=case,
        paths=paths,
        os_facade=facade,
        operator_uid=1000,
        target=target,
        inputs=SyntheticInputs(material, secret),
        usb_api=api,
        tls_factory=Tls12PskServer,
        checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
        final_delegate=DurableReportPublisher(paths.final_report),
    )
    checkpoint = json.loads(paths.checkpoint_report.read_text(encoding="utf-8"))
    final = json.loads(paths.final_report.read_text(encoding="utf-8"))
    if (paths.checkpoint_report.stat().st_mode & 0o777) != 0o600:
        raise AssertionError("checkpoint report mode is not 0600")
    if (paths.final_report.stat().st_mode & 0o777) != 0o600:
        raise AssertionError("final report mode is not 0600")
    return report, api, facade, checkpoint, final


def verify_unseal_reseal() -> dict[str, object]:
    sealed = {
        name: sha256(REPOSITORY / name)
        for name in (
            "src/goodix5125_d233_backend.py",
            "src/goodix5125_d235_entrypoint.py",
        )
    }
    with tempfile.TemporaryDirectory(prefix="d243-seal-") as directory:
        root = Path(directory)
        (root / "src").mkdir()
        for relative in sealed:
            shutil.copy2(REPOSITORY / relative, root / relative)
        applied = subprocess.run(
            ["patch", "--batch", "--forward", "--strip=1", f"--input={UNSEAL_PATCH}"],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if applied.returncode or "offset" in applied.stdout.lower():
            raise AssertionError(applied.stderr or applied.stdout or "patch offset detected")
        backend = (root / "src/goodix5125_d233_backend.py").read_text()
        entrypoint = (root / "src/goodix5125_d235_entrypoint.py").read_text()
        if (
            "return None" not in backend
            or 'D235_RESULT_SCHEMA = "d243-live-tls-single-shot-result-v1"'
            not in entrypoint
        ):
            raise AssertionError("D243 unseal content missing")
        unsealed = {name: sha256(root / name) for name in sealed}
        reversed_patch = subprocess.run(
            ["patch", "--batch", "--reverse", "--strip=1", f"--input={UNSEAL_PATCH}"],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if reversed_patch.returncode or "offset" in reversed_patch.stdout.lower():
            raise AssertionError(reversed_patch.stderr or reversed_patch.stdout)
        final = {name: sha256(root / name) for name in sealed}
    if final != sealed:
        raise AssertionError("D243 source reseal mismatch")
    return {
        "patch_apply": "PASS_WITHOUT_OFFSET",
        "reseal_rollback": "PASS_WITHOUT_OFFSET",
        "sealed_sha256": sealed,
        "unsealed_sha256": unsealed,
        "final_sealed_sha256": final,
        "unseal_patch_sha256": sha256(UNSEAL_PATCH),
    }


def publish(path: Path, report: Mapping[str, object]) -> None:
    payload = (json.dumps(dict(report), sort_keys=True, indent=2) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=".d243-closure-", dir=path.parent)
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


def _durability_view(report: Mapping[str, object]) -> dict[str, object]:
    return {
        key: report.get(key)
        for key in (
            "schema",
            "result",
            "terminal_state",
            "attempted_phase",
            "abort_class",
            "command_count",
            "usb_open_count",
            "cleanup_count",
            "secret_zeroized",
            "fprintd_restore_status",
            "signal_restore_status",
            "report_publish_count",
            "source_seal_state",
            "retry_count",
            "d4_count",
            "application_data_count",
            "persistent_write_family_count",
        )
    }


def run(report_path: Path = DEFAULT_REPORT) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="d243-closure-") as directory:
        root = Path(directory)
        preflight = offline_sandbox_preflight(root / "preflight")
        success, success_api, success_facade, _success_checkpoint, _success_final = (
            run_entrypoint_fixture(root, "success")
        )
        server_timeout, timeout_api, timeout_facade, _timeout_checkpoint, _timeout_final = (
            run_entrypoint_fixture(root, "server_flight_timeout")
        )
        e4, e4_api, e4_facade, e4_checkpoint, e4_final = run_entrypoint_fixture(
            root, "e4_timeout"
        )
        seal = verify_unseal_reseal()
        dependencies = verify_dependencies()
        closure = {
            "schema": "d243-executable-closure-report-v1",
            "status": "PASS",
            "classification": "D243_EXECUTABLE_CLOSURE_GATE_PASS",
            "repository": str(REPOSITORY),
            "artifact_sha256": artifact_hashes(),
            "dependency_integrity": dependencies,
            "preflight_fixture": preflight,
            "seal_coherence": seal,
            "success": {
                "result": success.get("result"),
                "first_tls_record_handoff_count": success.get(
                    "first_tls_record_handoff_count"
                ),
                "same_validated_psk_used_by_tls": success.get(
                    "same_validated_psk_used_by_tls"
                ),
                "client_complete": getattr(success_api, "client_complete", False),
                "cleanup_count": success.get("cleanup_count"),
                "marker_claim_count": success_facade.marker_claim_count,
            },
            "server_flight_timeout": {
                "abort_class": server_timeout.get("abort_class"),
                "failure_class": server_timeout.get("tls_failure_class"),
                "server_flight_b0_frame_count": server_timeout.get(
                    "server_flight_b0_frame_count"
                ),
                "server_flight_usb_bulk_out_count": server_timeout.get(
                    "server_flight_usb_bulk_out_count"
                ),
                "server_flight_chunk_size_buckets": server_timeout.get(
                    "server_flight_chunk_size_buckets"
                ),
                "server_flight_pacing_ms": server_timeout.get(
                    "server_flight_pacing_ms"
                ),
                "server_flight_pacing_count": server_timeout.get(
                    "server_flight_pacing_count"
                ),
                "post_server_flight_bulk_in_timeout_count": server_timeout.get(
                    "post_server_flight_bulk_in_timeout_count"
                ),
                "cleanup_count": server_timeout.get("cleanup_count"),
                "marker_claim_count": timeout_facade.marker_claim_count,
            },
            "e4_timeout_durability": {
                "runtime_abort": _durability_view(e4),
                "durable_checkpoint_before_restore": _durability_view(e4_checkpoint),
                "final_report_after_restore": _durability_view(e4_final),
                "checkpoint_precedes_restore": (
                    e4_checkpoint.get("fprintd_restore_status") in {"pending", "not_required"}
                    and e4_checkpoint.get("signal_restore_status") == "pending"
                    and e4_final.get("signal_restore_status") == "restored"
                ),
                "usb_release_count": e4_api.calls.count(("release", 0)),
                "usb_close_count": e4_api.calls.count("close"),
                "usb_exit_count": e4_api.calls.count("exit"),
                "marker_claim_count": e4_facade.marker_claim_count,
            },
            "live_usb_execution": "NOT_PERFORMED",
            "real_tls_handshake_execution": "SYNTHETIC_ONLY",
            "real_secret_read_count": 0,
            "d4_count": 0,
            "application_data_count": 0,
            "persistent_write_family_count": 0,
            "retry_count": 0,
        }
        timeout_view = closure["server_flight_timeout"]
        durability = closure["e4_timeout_durability"]
        checkpoint = durability["durable_checkpoint_before_restore"]
        final = durability["final_report_after_restore"]
        required = (
            preflight.get("status") == "PASS"
            and dependencies["status"] == "PASS"
            and dependencies["unpinned_dependency_count"] == 0
            and success.get("result") == "pass"
            and success.get("first_tls_record_handoff_count") == 1
            and success.get("same_validated_psk_used_by_tls") is True
            and getattr(success_api, "client_complete", False)
            and timeout_view["failure_class"]
            == "TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT"
            and timeout_view["server_flight_b0_frame_count"] == 2
            and timeout_view["server_flight_usb_bulk_out_count"] == 3
            and timeout_view["server_flight_chunk_size_buckets"] == {"64": 3}
            and timeout_view["server_flight_pacing_ms"] == TLS_RECORD_PACING_MS
            and timeout_view["server_flight_pacing_count"] == 2
            and timeout_view["post_server_flight_bulk_in_timeout_count"] == 1
            and e4.get("attempted_phase") == "E4"
            and e4.get("abort_class") == "timeout"
            and e4.get("command_count") == 1
            and e4.get("usb_open_count") == 1
            and e4.get("cleanup_count") == 1
            and e4.get("secret_zeroized") is True
            and checkpoint.get("terminal_state") == "STOP"
            and checkpoint.get("attempted_phase") == "E4"
            and checkpoint.get("cleanup_count") == 1
            and checkpoint.get("secret_zeroized") is True
            and checkpoint.get("report_publish_count") == 1
            and final.get("report_publish_count") == 2
            and final.get("fprintd_restore_status") == "not_required"
            and final.get("signal_restore_status") == "restored"
            and durability["checkpoint_precedes_restore"] is True
            and durability["usb_release_count"] == 1
            and durability["usb_close_count"] == 1
            and durability["usb_exit_count"] == 1
            and durability["marker_claim_count"] == 1
            and seal["patch_apply"] == "PASS_WITHOUT_OFFSET"
            and seal["reseal_rollback"] == "PASS_WITHOUT_OFFSET"
        )
        if not required:
            closure["status"] = "FAIL"
            closure["classification"] = "D243_BLOCKED_BY_EXECUTABLE_CLOSURE"
        serialized = json.dumps(closure, sort_keys=True).encode()
        _material, _responses, secret = synthetic_material(
            ProductionRuntimePaths.system_default().canonical_gfusb
        )
        if secret in serialized or b'"payload"' in serialized:
            closure["status"] = "FAIL"
            closure["classification"] = "D243_BLOCKED_BY_REDACTION_FAILURE"
        publish(report_path, closure)
        return closure


def validate_report(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if (
        report.get("schema") != "d243-executable-closure-report-v1"
        or report.get("status") != "PASS"
        or report.get("classification") != "D243_EXECUTABLE_CLOSURE_GATE_PASS"
        or report.get("artifact_sha256") != artifact_hashes()
        or report.get("live_usb_execution") != "NOT_PERFORMED"
    ):
        raise ValueError("D243 closure report is missing, stale, or failed")
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
    except (OSError, ValueError, AssertionError, RuntimeError, ContractError) as exc:
        print(f"d243_operator_dry_run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
