"""D242 executable closure using only synthetic USB and TLS peers."""

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

from analysis.D242.d242_dependency_gate import verify_d241_dependencies

verify_d241_dependencies()

from analysis.D241.d241_operator_dry_run import (
    FixtureUsbApi,
    LoopbackTlsUsbApi,
    OfflineFacade,
    SyntheticInputs,
    fixture_incoming,
    synthetic_material,
)
from analysis.D242.d242_preflight import offline_sandbox_preflight
from src.goodix5125_d232_offline import ContractError, DurableReportPublisher
from src.goodix5125_d233_backend import TLS_RECORD_PACING_MS, Tls12PskServer, UsbIdentity
from src.goodix5125_d235_entrypoint import (
    ProductionRuntimePaths,
    ResolvedUsbTarget,
    run_injected_offline_entrypoint_review,
)


REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = REPOSITORY / "analysis/D242/D242_executable_closure_report.json"
UNSEAL_PATCH = REPOSITORY / "analysis/D242/D242_live_unseal.patch"
ARTIFACTS = (
    "src/goodix5125_d232_offline.py",
    "src/goodix5125_d233_backend.py",
    "src/goodix5125_d235_entrypoint.py",
    "analysis/D242/d242_capture_forensics.py",
    "analysis/D242/d242_dependency_gate.py",
    "analysis/D242/d242_preflight_observability.py",
    "analysis/D242/d242_preflight.py",
    "analysis/D242/d242_operator_dry_run.py",
    "analysis/D242/D242_live_unseal.patch",
    "operator_kit/d242-live-tls-once.sh",
    "tests/test_d242_operator_kit.py",
    "tests/test_d242_transport_fix.py",
)


class D242LoopbackTlsUsbApi(LoopbackTlsUsbApi):
    """D242-local adapter: discard non-semantic fixed-64 staging tails."""

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
    root: Path, *, timeout: bool
) -> tuple[dict[str, object], FixtureUsbApi, OfflineFacade]:
    production = ProductionRuntimePaths.system_default()
    material, responses, secret = synthetic_material(production.canonical_gfusb)
    case = root / ("timeout" if timeout else "success")
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
        checkpoint_report=reports / "d242-checkpoint.json",
        final_report=reports / "d242-final.json",
        single_use_marker=store / "d242-operator-invocation.marker",
    )
    identity = UsbIdentity(0x27C6, 0x5125, 1, 4, (7,))
    target = ResolvedUsbTarget(identity, Path("/dev/bus/usb/001/004"))
    facade = OfflineFacade()
    incoming = fixture_incoming(
        material,
        responses,
        fragment_first_b0=timeout,
        include_d1=timeout,
    )
    if timeout:
        api = FixtureUsbApi(incoming, identity, timeout_when_empty=True)
    else:
        api = D242LoopbackTlsUsbApi(incoming, identity, secret)
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
    return report, api, facade


def verify_unseal_reseal() -> dict[str, object]:
    sealed = {
        name: sha256(REPOSITORY / name)
        for name in (
            "src/goodix5125_d233_backend.py",
            "src/goodix5125_d235_entrypoint.py",
        )
    }
    with tempfile.TemporaryDirectory(prefix="d242-seal-") as directory:
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
        if applied.returncode:
            raise AssertionError(applied.stderr or applied.stdout)
        backend = (root / "src/goodix5125_d233_backend.py").read_text()
        entrypoint = (root / "src/goodix5125_d235_entrypoint.py").read_text()
        if "return None" not in backend or 'D235_RESULT_SCHEMA = "d242-live-tls-single-shot-result-v1"' not in entrypoint:
            raise AssertionError("D242 unseal content missing")
        unsealed = {name: sha256(root / name) for name in sealed}
        reversed_patch = subprocess.run(
            ["patch", "--batch", "--reverse", "--strip=1", f"--input={UNSEAL_PATCH}"],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if reversed_patch.returncode:
            raise AssertionError(reversed_patch.stderr or reversed_patch.stdout)
        final = {name: sha256(root / name) for name in sealed}
    if final != sealed:
        raise AssertionError("D242 source reseal mismatch")
    return {
        "patch_apply": "PASS",
        "reseal_rollback": "PASS",
        "sealed_sha256": sealed,
        "unsealed_sha256": unsealed,
        "final_sealed_sha256": final,
        "unseal_patch_sha256": sha256(UNSEAL_PATCH),
    }


def publish(path: Path, report: Mapping[str, object]) -> None:
    payload = (json.dumps(dict(report), sort_keys=True, indent=2) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=".d242-closure-", dir=path.parent)
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
    with tempfile.TemporaryDirectory(prefix="d242-closure-") as directory:
        root = Path(directory)
        preflight = offline_sandbox_preflight(root / "preflight")
        success, success_api, success_facade = run_entrypoint_fixture(root, timeout=False)
        timeout, timeout_api, timeout_facade = run_entrypoint_fixture(root, timeout=True)
        seal = verify_unseal_reseal()
        report: dict[str, object] = {
            "schema": "d242-executable-closure-report-v1",
            "status": "PASS",
            "classification": "D242_EXECUTABLE_CLOSURE_GATE_PASS",
            "repository": str(REPOSITORY),
            "artifact_sha256": artifact_hashes(),
            "d241_dependency_integrity": verify_d241_dependencies(),
            "preflight_fixture": preflight,
            "seal_coherence": seal,
            "success": {
                "result": success.get("result"),
                "first_tls_record_handoff_count": success.get("first_tls_record_handoff_count"),
                "same_validated_psk_used_by_tls": success.get("same_validated_psk_used_by_tls"),
                "client_complete": getattr(success_api, "client_complete", False),
                "cleanup_count": success.get("cleanup_count"),
                "marker_claim_count": success_facade.marker_claim_count,
            },
            "server_flight_timeout": {
                "abort_class": timeout.get("abort_class"),
                "failure_class": timeout.get("tls_failure_class"),
                "server_flight_b0_frame_count": timeout.get("server_flight_b0_frame_count"),
                "server_flight_tls_record_count": timeout.get("server_flight_tls_record_count"),
                "server_flight_usb_bulk_out_count": timeout.get("server_flight_usb_bulk_out_count"),
                "server_flight_chunk_size_buckets": timeout.get("server_flight_chunk_size_buckets"),
                "server_flight_pacing_ms": timeout.get("server_flight_pacing_ms"),
                "server_flight_pacing_count": timeout.get("server_flight_pacing_count"),
                "post_server_flight_bulk_in_call_count": timeout.get("post_server_flight_bulk_in_call_count"),
                "post_server_flight_bulk_in_timeout_count": timeout.get("post_server_flight_bulk_in_timeout_count"),
                "post_server_flight_bulk_in_error_count": timeout.get("post_server_flight_bulk_in_error_count"),
                "post_server_flight_nonzero_rx_count": timeout.get("post_server_flight_nonzero_rx_count"),
                "post_server_flight_first_rx_class": timeout.get("post_server_flight_first_rx_class"),
                "openssl_fatal_error_observed": timeout.get("openssl_fatal_error_observed"),
                "cleanup_count": timeout.get("cleanup_count"),
                "marker_claim_count": timeout_facade.marker_claim_count,
            },
            "live_usb_execution": "NOT_PERFORMED",
            "real_secret_read_count": 0,
            "d4_count": 0,
            "application_data_count": 0,
            "persistent_write_family_count": 0,
            "retry_count": 0,
        }
        closure = report["server_flight_timeout"]
        required = (
            preflight.get("status") == "PASS"
            and success.get("result") == "pass"
            and report["d241_dependency_integrity"]["unpinned_closure_dependency_count"] == 0
            and success.get("first_tls_record_handoff_count") == 1
            and success.get("same_validated_psk_used_by_tls") is True
            and getattr(success_api, "client_complete", False)
            and timeout.get("tls_failure_class") == "TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT"
            and closure["server_flight_b0_frame_count"] == 2
            and closure["server_flight_tls_record_count"] == 2
            and closure["server_flight_usb_bulk_out_count"] == 3
            and closure["server_flight_chunk_size_buckets"] == {"64": 3}
            and closure["server_flight_pacing_ms"] == TLS_RECORD_PACING_MS
            and closure["server_flight_pacing_count"] == 2
            and closure["post_server_flight_bulk_in_call_count"] >= 1
            and closure["post_server_flight_bulk_in_timeout_count"] == 1
            and closure["post_server_flight_bulk_in_error_count"] == 0
            and closure["post_server_flight_nonzero_rx_count"] == 0
            and success.get("cleanup_count") == timeout.get("cleanup_count") == 1
            and success_api.calls.count(("release", 0)) == 1
            and timeout_api.calls.count(("release", 0)) == 1
            and seal["patch_apply"] == seal["reseal_rollback"] == "PASS"
        )
        if not required:
            report["status"] = "FAIL"
            report["classification"] = "D242_BLOCKED_BY_EXECUTABLE_CLOSURE"
        serialized = json.dumps(report, sort_keys=True).encode()
        _material, _responses, secret = synthetic_material(
            ProductionRuntimePaths.system_default().canonical_gfusb
        )
        if secret in serialized or b'"payload"' in serialized:
            report["status"] = "FAIL"
            report["classification"] = "D242_BLOCKED_BY_REDACTION_FAILURE"
        publish(report_path, report)
        return report


def validate_report(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if (
        report.get("schema") != "d242-executable-closure-report-v1"
        or report.get("status") != "PASS"
        or report.get("classification") != "D242_EXECUTABLE_CLOSURE_GATE_PASS"
        or report.get("artifact_sha256") != artifact_hashes()
        or report.get("live_usb_execution") != "NOT_PERFORMED"
    ):
        raise ValueError("D242 closure report is missing, stale, or failed")
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
    except (OSError, ValueError, AssertionError, ContractError) as exc:
        print(f"d242_operator_dry_run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
