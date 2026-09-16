"""D241 executable-closure fixture: full launcher path without real USB."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

from poc.goodix5125.tools.binding_reference.known_answers import VECTORS
from poc.goodix5125.tools.binding_reference.runtime import derive_validator_from_canonical_pe
from src.goodix5125_d232_offline import (
    ContractError,
    DurableReportPublisher,
    SecretBuffer,
    SyntheticResponseBodies,
    TargetMaterial,
    _config90_finalizer,
    build_b0,
    happy_synthetic_script,
    parse_b0,
)
from src.goodix5125_d233_backend import (
    TLS_CIPHER_NAME,
    Tls12PskServer,
    UsbIdentity,
    UsbTimeout,
)
from src.goodix5125_d235_entrypoint import (
    ProductionRuntimePaths,
    ResolvedUsbTarget,
    run_injected_offline_entrypoint_review,
)
from analysis.D241.d241_preflight import offline_sandbox_preflight


REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = REPOSITORY / "analysis/D241/D241_executable_closure_report.json"
UNSEAL_PATCH = REPOSITORY / "analysis/D241/D241_live_unseal.patch"
ARTIFACTS = (
    "src/goodix5125_d232_offline.py",
    "src/goodix5125_d233_backend.py",
    "src/goodix5125_d235_entrypoint.py",
    "analysis/D241/d241_preflight.py",
    "analysis/D241/d241_operator_dry_run.py",
    "analysis/D241/D241_live_unseal.patch",
    "operator_kit/d241-live-tls-once.sh",
    "tests/test_d241_transition.py",
    "tests/test_d241_operator_kit.py",
    "tests/test_d239_operator_kit.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_hashes() -> dict[str, str]:
    return {name: sha256(REPOSITORY / name) for name in ARTIFACTS}


class OfflineFacade:
    offline_only = True

    def __init__(self):
        self.calls: list[object] = []
        self.marker_claim_count = 0

    def euid(self): return 0
    def sudo_uid(self): return 1000
    def process_count(self): return 1
    def thread_count(self): return 1
    def external_holders(self, _path): return ()
    def fprintd_active(self): self.calls.append("capture"); return False
    def stop_fprintd(self): raise AssertionError("inactive fprintd must not stop")
    def start_fprintd(self): raise AssertionError("inactive fprintd must not start")
    def block_signals(self, _signals): self.calls.append("block"); return "old-mask"
    def restore_signals(self, previous): self.calls.append(("restore", previous))

    def claim_single_use_marker(self, path):
        if os.path.lexists(path):
            raise ContractError("D241 fixture marker already consumed")
        path.write_text("D241 synthetic claim\n", encoding="ascii")
        path.chmod(0o600)
        self.marker_claim_count += 1

    def report_path_ready(self, path):
        if os.path.lexists(path):
            return False
        status = os.lstat(path.parent)
        return (
            stat.S_ISDIR(status.st_mode)
            and not stat.S_ISLNK(status.st_mode)
            and stat.S_IMODE(status.st_mode) == 0o700
        )


class SyntheticInputs:
    offline_only = True

    def __init__(self, material: TargetMaterial, secret: bytes):
        self.material = material
        self.secret = secret
        self.material_load_count = 0
        self.secret_load_count = 0

    def load_material(self):
        self.material_load_count += 1
        if self.material_load_count != 1:
            raise ContractError("fixture material loaded twice")
        return self.material

    def load_secret(self):
        self.secret_load_count += 1
        if self.secret_load_count != 1:
            raise ContractError("fixture secret loaded twice")
        return SecretBuffer.synthetic(self.secret)


class FixtureUsbApi:
    offline_only = True

    def __init__(self, incoming: Sequence[bytes], identity: UsbIdentity, *, timeout_when_empty=False):
        self.incoming = [bytearray(item) for item in incoming]
        self.current_identity = identity
        self.timeout_when_empty = timeout_when_empty
        self.calls: list[object] = []
        self.outgoing: list[bytes] = []

    def init(self): self.calls.append("init"); return object()
    def open_exact(self, _context, vid, pid): self.calls.append(("open", vid, pid)); return object()
    def identity(self, _handle): self.calls.append("identity"); return self.current_identity
    def claim_interface(self, _handle, interface): self.calls.append(("claim", interface))

    def bulk_out(self, _handle, endpoint, data, timeout_ms):
        self.calls.append(("out", endpoint, timeout_ms))
        self.outgoing.append(bytes(data))
        return len(data)

    def bulk_in(self, _handle, endpoint, maximum, timeout_ms):
        self.calls.append(("in", endpoint, timeout_ms))
        if not self.incoming:
            if self.timeout_when_empty:
                raise UsbTimeout("D241 synthetic handshake stall")
            return b""
        item = self.incoming[0]
        result = bytes(item[:maximum])
        del item[:maximum]
        if not item:
            self.incoming.pop(0)
        return result

    def release_interface(self, _handle, interface): self.calls.append(("release", interface))
    def close(self, _handle): self.calls.append("close")
    def exit(self, _context): self.calls.append("exit")


class LoopbackTlsUsbApi(FixtureUsbApi):
    """Synthetic USB device driven by a real OpenSSL TLS 1.2 PSK client."""

    def __init__(self, incoming: Sequence[bytes], identity: UsbIdentity, secret: bytes):
        super().__init__(incoming, identity)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers(TLS_CIPHER_NAME)
        context.options |= ssl.OP_NO_TICKET
        context.set_psk_client_callback(lambda _hint: ("Client_identity", secret))
        self._client_in = ssl.MemoryBIO()
        self._client_out = ssl.MemoryBIO()
        self._client = context.wrap_bio(
            self._client_in, self._client_out, server_side=False
        )
        self._outgoing_stream = bytearray()
        self.client_complete = False

    @staticmethod
    def _records(stream: bytes) -> tuple[bytes, ...]:
        records = []
        cursor = 0
        while cursor < len(stream):
            if len(stream) - cursor < 5:
                raise AssertionError("partial loopback TLS record")
            end = cursor + 5 + int.from_bytes(stream[cursor + 3:cursor + 5], "big")
            if end > len(stream):
                raise AssertionError("partial loopback TLS record")
            records.append(stream[cursor:end])
            cursor = end
        return tuple(records)

    def _advance_client(self) -> None:
        try:
            self._client.do_handshake()
            self.client_complete = True
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
            pass
        wire = self._client_out.read()
        for record in self._records(wire) if wire else ():
            self.incoming.append(bytearray(build_b0(record)))

    def _handle_outgoing_frame(self, frame: bytes) -> None:
        if frame[0] == 0xA0 and len(frame) >= 5 and frame[4] == 0xD1:
            self._advance_client()
        elif frame[0] == 0xB0:
            self._client_in.write(parse_b0(frame))
            self._advance_client()

    def bulk_out(self, handle, endpoint, data, timeout_ms):
        result = super().bulk_out(handle, endpoint, data, timeout_ms)
        self._outgoing_stream.extend(data)
        while len(self._outgoing_stream) >= 4:
            total = 4 + int.from_bytes(self._outgoing_stream[1:3], "little")
            if len(self._outgoing_stream) < total:
                break
            frame = bytes(self._outgoing_stream[:total])
            del self._outgoing_stream[:total]
            self._handle_outgoing_frame(frame)
        return result


class SuccessTlsEngine:
    def __init__(self, secret: SecretBuffer):
        self.bound_secret = secret
        self.complete = False
        self.closed = False
        self.handshake_count = 0
        self.feed_count = 0

    def feed(self, _payload): self.feed_count += 1
    def advance(self): self.handshake_count = 1; self.complete = True
    def drain(self): return ()
    def close(self): self.closed = True


class StalledTlsEngine(SuccessTlsEngine):
    def __init__(self, secret: SecretBuffer):
        super().__init__(secret)
        self._drained = False

    def advance(self): self.handshake_count = 1

    def drain(self):
        if self._drained:
            return ()
        self._drained = True
        return (b"\x16\x03\x03\x00\x01\x02",)


def synthetic_material(canonical_pe: Path) -> tuple[TargetMaterial, SyntheticResponseBodies, bytes]:
    secret = VECTORS["V2"]
    expected = derive_validator_from_canonical_pe(canonical_pe, secret)
    try:
        validator = bytes(expected)
    finally:
        expected[:] = bytes(len(expected))
    config = bytearray((17 * index + 3) & 0xFF for index in range(224))
    dac = []
    for register, value, offset in (
        (0x0220, b"\xd8\x0b", 117),
        (0x0236, b"\xbe\x00", 121),
        (0x0238, b"\xbd\x00", 125),
        (0x023A, b"\xbc\x00", 129),
    ):
        config[offset:offset + 4] = register.to_bytes(2, "little") + value
        dac.append((register, value, offset))
    config[-2:] = _config90_finalizer(bytes(config))
    random = bytes((13 * index + 1) & 0xFF for index in range(32))
    body = b"\x03\x03" + random + b"\x00\x00\x02\x00\xa8\x01\x00"
    handshake = b"\x01" + len(body).to_bytes(3, "big") + body
    client_hello = b"\x16\x03\x01" + len(handshake).to_bytes(2, "big") + handshake
    responses = SyntheticResponseBodies(
        e4_validator=validator,
        a2_irq=b"\x12\x34\x56",
        chip82=b"\x01\x25\x09\x41",
        otp_a6=bytes((9 * index + 11) & 0xFF for index in range(64)),
        tls_client_hello_record=client_hello,
    )
    material = TargetMaterial(
        e4_validator_sha256=hashlib.sha256(validator).hexdigest(),
        a2_response_sha256=hashlib.sha256(responses.a2_irq).hexdigest(),
        chip82_response_sha256=hashlib.sha256(responses.chip82).hexdigest(),
        otp_a6_response_sha256=hashlib.sha256(responses.otp_a6).hexdigest(),
        dac=tuple(dac),
        config90=bytes(config),
        config90_sha256=hashlib.sha256(config).hexdigest(),
    )
    return material, responses, secret


def fixture_incoming(
    material, responses, *, fragment_first_b0: bool, include_d1: bool = True
) -> list[bytes]:
    incoming: list[bytes] = []
    for step in happy_synthetic_script(material, responses, ack_status=0x07):
        for frame in step.responses:
            if step.phase_id == "D1" and not include_d1:
                continue
            if fragment_first_b0 and step.phase_id == "D1":
                split = len(frame) // 2
                incoming.extend((frame[:split], frame[split:]))
            else:
                incoming.append(frame)
    return incoming


def run_entrypoint_fixture(root: Path, *, timeout: bool) -> tuple[dict[str, object], FixtureUsbApi, OfflineFacade]:
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
        checkpoint_report=reports / "checkpoint.json",
        final_report=reports / "final.json",
        single_use_marker=store / "d241-operator-invocation.marker",
    )
    identity = UsbIdentity(0x27C6, 0x5125, 1, 4, (7,))
    target = ResolvedUsbTarget(identity, Path("/dev/bus/usb/001/004"))
    facade = OfflineFacade()
    if timeout:
        api = FixtureUsbApi(
            fixture_incoming(material, responses, fragment_first_b0=True),
            identity,
            timeout_when_empty=True,
        )
        tls_factory = StalledTlsEngine
    else:
        api = LoopbackTlsUsbApi(
            fixture_incoming(
                material, responses, fragment_first_b0=False, include_d1=False
            ),
            identity,
            secret,
        )
        tls_factory = Tls12PskServer
    report = run_injected_offline_entrypoint_review(
        offline_root=case,
        paths=paths,
        os_facade=facade,
        operator_uid=1000,
        target=target,
        inputs=SyntheticInputs(material, secret),
        usb_api=api,
        tls_factory=tls_factory,
        checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
        final_delegate=DurableReportPublisher(paths.final_report),
    )
    return report, api, facade


def verify_unseal_reseal() -> dict[str, object]:
    sealed = {
        "src/goodix5125_d233_backend.py": sha256(REPOSITORY / "src/goodix5125_d233_backend.py"),
        "src/goodix5125_d235_entrypoint.py": sha256(REPOSITORY / "src/goodix5125_d235_entrypoint.py"),
    }
    patch_hash = sha256(UNSEAL_PATCH)
    with tempfile.TemporaryDirectory(prefix="d241-seal-") as directory:
        root = Path(directory)
        (root / "src").mkdir()
        for relative in sealed:
            shutil.copy2(REPOSITORY / relative, root / relative)
        applied = subprocess.run(
            ["patch", "--batch", "--forward", "--strip=1", f"--input={UNSEAL_PATCH}"],
            cwd=root, text=True, capture_output=True,
        )
        if applied.returncode != 0:
            raise AssertionError(f"D241 unseal patch failed: {applied.stderr}")
        backend = (root / "src/goodix5125_d233_backend.py").read_text(encoding="utf-8")
        entrypoint = (root / "src/goodix5125_d235_entrypoint.py").read_text(encoding="utf-8")
        if "def _d233_usb_source_seal()" not in backend or "return None" not in backend:
            raise AssertionError("backend unseal content missing")
        if 'D235_RESULT_SCHEMA = "d241-live-tls-single-shot-result-v1"' not in entrypoint:
            raise AssertionError("entrypoint D241 unseal content missing")
        unsealed = {relative: sha256(root / relative) for relative in sealed}
        rolled_back = subprocess.run(
            ["patch", "--batch", "--reverse", "--strip=1", f"--input={UNSEAL_PATCH}"],
            cwd=root, text=True, capture_output=True,
        )
        if rolled_back.returncode != 0:
            raise AssertionError(f"D241 reseal patch failed: {rolled_back.stderr}")
        final = {relative: sha256(root / relative) for relative in sealed}
    if final != sealed:
        raise AssertionError("D241 reseal hashes differ from sealed baseline")
    return {
        "sealed_sha256": sealed,
        "unsealed_sha256": unsealed,
        "unseal_patch_sha256": patch_hash,
        "patch_apply": "PASS",
        "reseal_rollback": "PASS",
        "final_sealed_sha256": final,
        "d239_hash_used_as_gate": False,
    }


def publish(path: Path, report: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(dict(report), sort_keys=True, indent=2) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=".d241-closure-", dir=path.parent)
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
    with tempfile.TemporaryDirectory(prefix="d241-closure-") as directory:
        root = Path(directory)
        preflight = offline_sandbox_preflight(root / "preflight")
        success, success_api, success_facade = run_entrypoint_fixture(root, timeout=False)
        timeout, timeout_api, timeout_facade = run_entrypoint_fixture(root, timeout=True)
        seal = verify_unseal_reseal()
        report = {
            "schema": "d241-executable-closure-report-v1",
            "status": "PASS",
            "classification": "D241_EXECUTABLE_CLOSURE_GATE_PASS",
            "repository": str(REPOSITORY),
            "cwd": str(Path.cwd().resolve()),
            "artifact_sha256": artifact_hashes(),
            "preflight_fixture": preflight,
            "seal_coherence": seal,
            "direct_b0_success": {
                "result": success.get("result"),
                "unexpected_data": success.get("unexpected_data"),
                "first_tls_record_handoff_count": success.get("first_tls_record_handoff_count"),
                "same_validated_psk_used_by_tls": success.get("same_validated_psk_used_by_tls"),
                "d241_result": success.get("d241_result"),
                "tls_trace_redacted": success.get("tls_trace_redacted"),
                "cleanup_count": success.get("cleanup_count"),
                "release_count": success_api.calls.count(("release", 0)),
                "close_count": success_api.calls.count("close"),
                "marker_claim_count": success_facade.marker_claim_count,
                "real_openssl_client_complete": getattr(
                    success_api, "client_complete", False
                ),
            },
            "handshake_timeout": {
                "abort_class": timeout.get("abort_class"),
                "failure_class": timeout.get("tls_failure_class"),
                "first_tls_record_handoff_count": timeout.get("first_tls_record_handoff_count"),
                "retry_count": timeout.get("retry_count"),
                "cleanup_count": timeout.get("cleanup_count"),
                "release_count": timeout_api.calls.count(("release", 0)),
                "close_count": timeout_api.calls.count("close"),
                "marker_claim_count": timeout_facade.marker_claim_count,
                "tls_trace_redacted": timeout.get("tls_trace_redacted"),
            },
            "live_usb_execution": "NOT_PERFORMED",
            "real_secret_read_count": 0,
            "d4_count": 0,
            "application_data_count": 0,
            "persistent_write_family_count": 0,
            "retry_count": 0,
        }
        required = (
            preflight.get("status") == "PASS"
            and success.get("result") == "pass"
            and success.get("first_tls_record_handoff_count") == 1
            and success.get("same_validated_psk_used_by_tls") is True
            and getattr(success_api, "client_complete", False)
            and timeout.get("abort_class") == "tls_timeout"
            and timeout.get("tls_failure_class") == "TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT"
            and timeout.get("retry_count") == 0
            and success.get("cleanup_count") == timeout.get("cleanup_count") == 1
            and success_api.calls.count(("release", 0)) == 1
            and timeout_api.calls.count(("release", 0)) == 1
            and seal.get("patch_apply") == seal.get("reseal_rollback") == "PASS"
        )
        if not required:
            report["status"] = "FAIL"
            report["classification"] = "D241_BLOCKED_BY_EXECUTABLE_CLOSURE"
        serialized = json.dumps(report, sort_keys=True).encode()
        material, _responses, secret = synthetic_material(
            ProductionRuntimePaths.system_default().canonical_gfusb
        )
        del material
        if secret in serialized or b"payload" in serialized:
            report["status"] = "FAIL"
            report["classification"] = "D241_BLOCKED_BY_REDACTION_FAILURE"
        publish(report_path, report)
        return report


def validate_report(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if (
        report.get("schema") != "d241-executable-closure-report-v1"
        or report.get("status") != "PASS"
        or report.get("classification") != "D241_EXECUTABLE_CLOSURE_GATE_PASS"
        or report.get("artifact_sha256") != artifact_hashes()
        or report.get("live_usb_execution") != "NOT_PERFORMED"
    ):
        raise ValueError("D241 closure report is missing, stale, or failed")
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
            print("d241_operator_dry_run: invalid arguments", file=sys.stderr)
            return 64
    except (OSError, ValueError, AssertionError, ContractError) as exc:
        print(f"d241_operator_dry_run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
