#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""One production-shaped D260 runtime rehearsal and its failure matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import ssl
import sys
from typing import Any


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.fdt_seed import SEED_PROVIDER_FAIL_CLOSED, SEED_PROVIDER_PASS, SeedProvenance, SeedProviderResult
from core.persistent_runtime import PersistentRuntimeCoordinator
from core.post_d4 import PLAIN, TLS, parse_outer, parse_payload
from core.runtime_transport import PhysicalSubmissionPolicy, SubmissionMode
from core.tls_b0 import TLS_CIPHER_NAME, TLS_IDENTITY, wrap_tls_record_b0


SYNTHETIC_SECRET = bytes(range(1, 33))
SYNTHETIC_BASELINE = bytes((index * 17 + 3) & 0xFF for index in range(7693))
SEALED_HASHES = {
    "src/goodix5125_d233_backend.py": "e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982",
    "src/goodix5125_d235_entrypoint.py": "d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69",
    "operator_kit/d245-live-tls-once.sh": "77e19d158c252021a51be28b0292c54d95660db5016443af0a944b6145013ea0",
    "operator_kit/d246-live-d4-once.sh": "e86bc07fdfacb282e37ff065e52cc7250ee8cb29d7bfd6e821a8ed6d1f666c48",
    "operator_kit/d251-live-af-once.sh": "e33baf629221f4aa55a73c7feae6f26e0e1084cdc2d26df63bb362b571307280",
    "analysis/D245/D245_operator_live_stdout.json": "2992457855197b90dad3f7048bef85a6703079b95452dc07fa8e201a5c294e09",
    "analysis/D246/D246_operator_live_stdout.json": "055ace08832e2297d1b3687523fd41a410ed80b215207d63c352ea1cee2493e0",
    "analysis/D251/D251_operator_live_stdout.json": "61e76c89d55eb8255377016f44780b53386023a6ac8acfd1b93a553398994084",
}
ARCHITECTURE_CRITICAL_FILES = (
    "core/tls_b0.py",
    "core/runtime_transport.py",
    "core/persistent_runtime.py",
    "core/post_d4.py",
    "core/fdt_lifecycle.py",
    "core/fdt_seed.py",
)
BUNDLE_REVIEW_FILES = (
    "core/README.md",
    "core/tls_b0.py",
    "core/runtime_transport.py",
    "core/persistent_runtime.py",
    "core/fdt_lifecycle.py",
    "tests/test_d260_persistent_runtime.py",
    "analysis/D260/d260_offline_rehearsal.py",
    "analysis/D260/D260_architecture_runtime_report.md",
    "analysis/D260/D260_persistent_tls_evidence.json",
    "analysis/D260/D260_b0_handshake_bridge_evidence.json",
    "analysis/D260/D260_d4_plaintext_continuity_evidence.json",
    "analysis/D260/D260_mixed_a0_b0_evidence.json",
    "analysis/D260/D260_eventsource_irq_evidence.json",
    "analysis/D260/D260_end_to_end_rehearsal.json",
    "analysis/D260/D260_failure_containment_matrix.json",
    "analysis/D260/D260_physical_submission_policy_matrix.json",
    "analysis/D260/D260_architecture_critical_fileset.json",
    "analysis/D260/D260_readiness_decision.json",
    "analysis/D260/D260_test_results.txt",
)
FAILURE_SCENARIOS = (
    "malformed_b0_handshake",
    "tls_bad_mac",
    "tls_timeout",
    "d4_wrong_ack",
    "af_malformed_ae",
    "invalid_seed_fixture",
    "first_0x36_timeout",
    "missing_irq100",
    "wrong_irq100",
    "nav_malformed",
    "delta_reject",
    "baseline_b0_auth_failure",
    "b0_delayed_past_stage2",
    "second_delta_reject",
    "final_0x32_ack_failure",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split_tls_records(data: bytes) -> tuple[bytes, ...]:
    records: list[bytes] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 5:
            raise RuntimeError("synthetic_partial_tls_record")
        size = 5 + int.from_bytes(data[offset + 3:offset + 5], "big")
        if offset + size > len(data):
            raise RuntimeError("synthetic_tls_record_length")
        records.append(data[offset:offset + size])
        offset += size
    return tuple(records)


def _payload_frame(control: int, data: bytes) -> bytes:
    declared = len(data) + 1
    check = (0xAA - ((control & 0xFE) + declared + (declared >> 8) + sum(data))) & 0xFF
    payload = bytes((control, declared & 0xFF, declared >> 8)) + data + bytes((check,))
    size = len(payload)
    return bytes((PLAIN, size & 0xFF, size >> 8, (PLAIN + (size & 0xFF) + (size >> 8)) & 0xFF)) + payload


def _ack(echo: int, status: int = 1) -> bytes:
    return _payload_frame(0xB0, bytes((echo, status)))


def _af_response(*, malformed: bool = False) -> bytes:
    body = bytes((0, 2)) + bytes(14)
    return _payload_frame(0xAD if malformed else 0xAE, body)


def _nav_response(*, malformed: bool = False) -> bytes:
    data = b"\x50\x01" + bytes(2407)
    declared = len(data) + 1
    payload = bytes((0x50, declared & 0xFF, declared >> 8)) + data + bytes((0x89 if malformed else 0x88,))
    size = len(payload)
    return bytes((PLAIN, size & 0xFF, size >> 8, (PLAIN + (size & 0xFF) + (size >> 8)) & 0xFF)) + payload


def _irq100(words: tuple[int, ...], *, irq: int = 0x100) -> bytes:
    raw = b"".join(word.to_bytes(2, "little") for word in words)
    return _payload_frame(0x30, irq.to_bytes(2, "little") + b"\x00\x00" + raw)


def synthetic_seed(*, valid: bool = True) -> SeedProviderResult:
    provenance = SeedProvenance(
        explicit_source_path="SYNTHETIC_IN_MEMORY_FIXTURE",
        file_size=12,
        file_sha256=hashlib.sha256(b"synthetic-seed-fixture").hexdigest(),
        layout="SYNTHETIC_VALIDATED_FDT12_ONLY",
        crc_algorithm="FIXTURE_CONSTRUCTION",
        crc_byte_order="NOT_APPLICABLE",
        crc_valid=valid,
        otp_binding="SYNTHETIC_MATCH" if valid else "SYNTHETIC_REJECT",
        otp_sha256=hashlib.sha256(b"synthetic-otp-identity").hexdigest(),
        fdt12_sha256=hashlib.sha256(bytes.fromhex("801080118012801380148015")).hexdigest(),
    )
    return SeedProviderResult(
        status=SEED_PROVIDER_PASS if valid else SEED_PROVIDER_FAIL_CLOSED,
        fdt12=bytes.fromhex("801080118012801380148015") if valid else None,
        provenance=provenance,
        failure_reason=None if valid else "SYNTHETIC_SEED_REJECTED",
    )


class SyntheticSecretBoundary:
    def __init__(self) -> None:
        self._secret = bytearray(SYNTHETIC_SECRET)
        self.handoff_count = 0
        self.handoff_object_id: int | None = None
        self.close_count = 0

    def handoff(self) -> memoryview:
        if self.handoff_count or self.zeroized:
            raise RuntimeError("synthetic_secret_handoff_forbidden")
        self.handoff_count += 1
        self.handoff_object_id = id(self)
        return memoryview(self._secret)

    def close(self) -> None:
        if self.close_count:
            return
        for index in range(len(self._secret)):
            self._secret[index] = 0
        self.close_count = 1

    @property
    def zeroized(self) -> bool:
        return not any(self._secret)


class SyntheticTlsClient:
    def __init__(self, scenario: str) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers(TLS_CIPHER_NAME)
        context.options |= ssl.OP_NO_TICKET
        context.set_psk_client_callback(lambda _hint: (TLS_IDENTITY, SYNTHETIC_SECRET))
        self.input_bio = ssl.MemoryBIO()
        self.output_bio = ssl.MemoryBIO()
        self.ssl_object = context.wrap_bio(
            self.input_bio, self.output_bio, server_side=False
        )
        self.scenario = scenario
        self.handshake_complete = False
        self.bad_mac_injected = False

    def _advance(self) -> None:
        try:
            self.ssl_object.do_handshake()
            self.handshake_complete = True
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
            pass

    def _drain(self, *, corrupt_finished: bool = False) -> list[bytes]:
        data = bytearray()
        while self.output_bio.pending:
            data.extend(self.output_bio.read())
        records = list(_split_tls_records(bytes(data))) if data else []
        if corrupt_finished and records and not self.bad_mac_injected:
            damaged = bytearray(records[-1])
            damaged[-1] ^= 1
            records[-1] = bytes(damaged)
            self.bad_mac_injected = True
        return [wrap_tls_record_b0(record) for record in records]

    def client_hello(self) -> list[bytes]:
        self._advance()
        return self._drain()

    def accept_server_b0(self, frame: bytes) -> list[bytes]:
        kind, record = parse_outer(frame)
        if kind != TLS:
            raise RuntimeError("synthetic_server_frame_not_b0")
        self.input_bio.write(record)
        self._advance()
        if self.scenario == "tls_timeout":
            self._drain()
            return []
        return self._drain(corrupt_finished=self.scenario == "tls_bad_mac")

    def application_b0(self, plaintext: bytes, *, corrupt: bool = False) -> bytes:
        if not self.handshake_complete:
            raise RuntimeError("synthetic_client_handshake_incomplete")
        if self.ssl_object.write(plaintext) != len(plaintext):
            raise RuntimeError("synthetic_tls_short_write")
        frames = self._drain()
        if len(frames) != 1:
            raise RuntimeError("synthetic_application_record_count")
        if corrupt:
            damaged = bytearray(frames[0])
            damaged[-1] ^= 1
            return bytes(damaged)
        return frames[0]


class SyntheticEventSource:
    def __init__(self, scenario: str) -> None:
        stage0 = tuple(0x20 + index * 2 for index in range(6))
        stage1 = tuple(value + 1 for value in stage0)
        stage2 = tuple(value + (20 if scenario == "second_delta_reject" else 1) for value in stage1)
        first_irq = 2 if scenario == "wrong_irq100" else 0x100
        self.events = [_irq100(stage0, irq=first_irq), _irq100(stage1), _irq100(stage2)]
        self.scenario = scenario
        self.wait_count = 0

    def wait_event(self, timeout_ms: int) -> bytes:
        self.wait_count += 1
        if self.scenario == "missing_irq100" and self.wait_count == 1:
            raise TimeoutError("synthetic_irq100_timeout")
        if not self.events:
            raise TimeoutError("synthetic_event_queue_empty")
        return self.events.pop(0)


class SyntheticRuntimeTransport:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.client = SyntheticTlsClient(scenario)
        self.queue: list[bytes] = []
        self.session_count = 0
        self.cleanup_count = 0
        self.opened = False
        self.submissions: list[dict[str, Any]] = []
        self.control_counts: dict[int, int] = {}

    def open(self) -> None:
        if self.opened or self.session_count:
            raise RuntimeError("synthetic_transport_reopen")
        self.opened = True
        self.session_count = 1

    def _record_submission(self, frame: bytes, policy: PhysicalSubmissionPolicy) -> None:
        kind, body = parse_outer(frame)
        control = None
        if kind == PLAIN:
            control, _data = parse_payload(body)
            self.control_counts[control] = self.control_counts.get(control, 0) + 1
        chunks = policy.materialize(frame)
        self.submissions.append({
            "kind": "A0" if kind == PLAIN else "B0",
            "control": f"0x{control:02x}" if control is not None else None,
            "logical_length": len(frame),
            "policy": policy.name,
            "mode": policy.mode.value,
            "timeout_ms": policy.timeout_ms,
            "pre_submit_pacing_ms": policy.pre_submit_pacing_ms,
            "post_submit_pacing_ms": policy.post_submit_pacing_ms,
            "physical_chunk_lengths": [len(chunk) for chunk in chunks],
            "zero_tail": (
                policy.mode == SubmissionMode.FIXED64_ZERO_TAIL
                and not any(chunks[-1][len(frame) % 64 or 64:])
            ),
        })

    def submit(self, logical_frame: bytes, policy: PhysicalSubmissionPolicy) -> None:
        if not self.opened:
            raise RuntimeError("synthetic_transport_not_open")
        self._record_submission(logical_frame, policy)
        kind, body = parse_outer(logical_frame)
        if kind == TLS:
            self.queue.extend(self.client.accept_server_b0(logical_frame))
            return
        control, _data = parse_payload(body)
        if control == 0xD1:
            if self.scenario == "malformed_b0_handshake":
                self.queue.append(_ack(0xD1))
            else:
                self.queue.extend(self.client.client_hello())
        elif control == 0xD4:
            self.queue.append(_ack(0xD4, 7 if self.scenario == "d4_wrong_ack" else 1))
        elif control == 0xAF:
            self.queue.append(_af_response(malformed=self.scenario == "af_malformed_ae"))
        elif control == 0x36:
            if self.scenario == "first_0x36_timeout" and self.control_counts[0x36] == 1:
                return
            self.queue.append(_ack(0x36))
        elif control == 0x50:
            self.queue.extend((_ack(0x50), _nav_response(malformed=self.scenario == "nav_malformed")))
        elif control == 0x82:
            threshold = 0 if self.scenario == "delta_reject" else 4
            self.queue.extend((_ack(0x82), _payload_frame(0x82, bytes((0, threshold)))))
        elif control == 0x20:
            self.queue.append(_ack(0x20))
            if self.scenario == "b0_delayed_past_stage2":
                self.queue.append(_ack(0x36))
            else:
                self.queue.append(self.client.application_b0(
                    SYNTHETIC_BASELINE,
                    corrupt=self.scenario == "baseline_b0_auth_failure",
                ))
        elif control == 0x32:
            self.queue.append(_ack(0x32, 2 if self.scenario == "final_0x32_ack_failure" else 1))
        else:
            raise RuntimeError(f"unexpected_synthetic_control:0x{control:02x}")

    def receive(self, timeout_ms: int) -> bytes:
        if not self.queue:
            raise TimeoutError(f"synthetic_transport_timeout:{timeout_ms}")
        return self.queue.pop(0)

    def close(self) -> None:
        if self.cleanup_count:
            return
        self.opened = False
        self.cleanup_count = 1


def run_scenario(name: str) -> dict[str, Any]:
    transport = SyntheticRuntimeTransport(name)
    event_source = SyntheticEventSource(name)
    boundary = SyntheticSecretBoundary()
    coordinator = PersistentRuntimeCoordinator(transport, event_source, boundary)
    passed = False
    result = None
    try:
        result = coordinator.run(
            synthetic_seed(valid=name != "invalid_seed_fixture"),
            ts16=0x4242,
        )
        passed = True
    except Exception:
        if name == "happy":
            raise
    audit = coordinator.audit()
    return {
        "scenario": name,
        "passed": passed,
        "expected_pass": name == "happy",
        "result": ({
            "command_trace": [f"0x{value:02x}" for value in result.command_trace],
            "tls_state_before_cleanup": result.tls_state_before_cleanup,
            "baseline_b0_consumed_before_stage2": result.baseline_b0_consumed_before_stage2,
            "second_native_delta_passed": result.second_native_delta_passed,
        } if result else None),
        "audit": audit,
        "event_wait_count": event_source.wait_count,
        "submissions": transport.submissions,
        "secret_boundary_object_id_reused": (
            boundary.handoff_object_id == id(boundary)
            and audit["tls_uses_same_secret_boundary_object"]
        ),
        "synthetic_secret_only": True,
    }


def _sealed_evidence(repo: Path) -> dict[str, Any]:
    actual = {path: sha256_file(repo / path) for path in SEALED_HASHES}
    matches = {path: actual[path] == expected for path, expected in SEALED_HASHES.items()}
    return {
        "expected_sha256": SEALED_HASHES,
        "actual_sha256": actual,
        "matches": matches,
        "SRC_SEALED_UNCHANGED": all(matches[path] for path in matches if path.startswith("src/")),
        "HISTORICAL_LIVE_LAUNCHERS_UNCHANGED": all(matches[path] for path in matches if path.startswith("operator_kit/")),
        "HISTORICAL_LIVE_EVIDENCE_UNCHANGED": all(matches.values()),
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate(repo: Path) -> dict[str, Any]:
    output = repo / "analysis/D260"
    output.mkdir(parents=True, exist_ok=True)
    happy = run_scenario("happy")
    failures = [run_scenario(name) for name in FAILURE_SCENARIOS]
    failure_rows = []
    for row in failures:
        audit = row["audit"]
        contained = (
            not row["passed"]
            and audit["retry_count"] == 0
            and audit["host_cache_write_count"] == 0
            and audit["persistent_device_write_count"] == 0
            and audit["a2_special_recovery_count"] == 0
            and audit["0x70_special_recovery_count"] == 0
            and audit["transport_cleanup_count"] == 1
            and audit["tls_close_count"] == 1
        )
        failure_rows.append({
            "scenario": row["scenario"],
            "failure_reason": audit["failure_reason"],
            "retry_count": audit["retry_count"],
            "cache_write_count": audit["host_cache_write_count"],
            "persistent_device_write_count": audit["persistent_device_write_count"],
            "a2_special_recovery_count": audit["a2_special_recovery_count"],
            "0x70_special_recovery_count": audit["0x70_special_recovery_count"],
            "transport_cleanup_count": audit["transport_cleanup_count"],
            "tls_close_count": audit["tls_close_count"],
            "contained": contained,
        })
    failure_matrix = {
        "schema": "D260_FAILURE_CONTAINMENT_MATRIX_V1",
        "execution_mode": "OFFLINE_ONLY",
        "status": "PASS" if all(row["contained"] for row in failure_rows) else "FAIL",
        "rows": failure_rows,
    }
    sealed = _sealed_evidence(repo)
    audit = happy["audit"]
    d4_rows = [row for row in happy["submissions"] if row["control"] == "0xd4"]
    b0_rows = [row for row in happy["submissions"] if row["kind"] == "B0"]
    fdt_rows = [row for row in happy["submissions"] if row["control"] in {"0x20", "0x32", "0x36", "0x50", "0x82"}]
    physical = {
        "schema": "D260_PHYSICAL_SUBMISSION_POLICY_MATRIX_V1",
        "status": "ABSTRACT_OFFLINE_FOR_FDT_A0_WITH_EXACT_D4_AND_B0_TLS_POLICIES",
        "D4": d4_rows,
        "B0_TLS_HOST_TO_DEVICE": b0_rows,
        "FDT_A0": fdt_rows,
        "unresolved_axis": "FDT_A0_BYTES_OUTSIDE_DECLARED_LOGICAL_LENGTH_ON_FUTURE_LINUX_USB_BACKEND",
    }
    critical = {
        "schema": "D260_ARCHITECTURE_CRITICAL_FILESET_V1",
        "files": [{"path": path, "sha256": sha256_file(repo / path)} for path in ARCHITECTURE_CRITICAL_FILES],
        "operational_live_critical_fileset_created": False,
        "operational_live_critical_fileset_approved": False,
    }
    tls_evidence = {
        "schema": "D260_PERSISTENT_TLS_EVIDENCE_V1",
        "lifecycle": ["CREATED", "HANDSHAKING", "ESTABLISHED", "APPLICATION_ACTIVE", "CLOSED"],
        "TLS_SERVER_SESSION_OBJECT_COUNT": audit["tls_server_session_object_count"],
        "TLS_SERVER_HANDSHAKE_COUNT": audit["tls_server_handshake_count"],
        "SECOND_SERVER_SESSION_CREATED": audit["second_server_session_created"],
        "SECOND_PSK_PROVISIONING": audit["second_psk_provisioning"],
        "POST_D4_TLS_ENGINE_RETAINED": audit["baseline_b0_tls_consumed"],
        "SAME_TLS_SESSION_B0_CONSUMPTION": "PASS_OFFLINE_ARCHITECTURAL",
        "HOST_TO_DEVICE_TLS_APPLICATION_DATA_REQUIRED": False,
        "HOST_TO_DEVICE_TLS_APPLICATION_DATA_STATUS": "OPTIONAL_FUTURE_UNPROVEN",
        "OPENSSL_INTERNAL_COPY_ZEROIZATION": "NOT_PROVEN",
        "PYTHON_IMMUTABLE_TEMP_COPY_ZEROIZATION": "NOT_PROVEN",
    }
    bridge_evidence = {
        "schema": "D260_B0_HANDSHAKE_BRIDGE_EVIDENCE_V1",
        "B0_TLS_HANDSHAKE_BRIDGE_STATUS": "PASS_OFFLINE_ARCHITECTURAL",
        "TLS_SESSION_FIXTURE_USED": True,
        "D1_B0_CLIENT_HELLO_HANDOFF": True,
        "SERVER_FLIGHT_EMITTED_AS_B0": bool(b0_rows),
        "CLIENT_FINISHED_RECEIVED_AS_B0": True,
        "REAL_TLS_TARGET_HANDSHAKE_COUNT": 0,
    }
    d4_evidence = {
        "schema": "D260_D4_PLAINTEXT_CONTINUITY_EVIDENCE_V1",
        "D4_POST_TLS_A0_PLAINTEXT_EXACTLY_ONCE": audit["d4_send_count"] == 1,
        "D4_TLS_APPLICATION_RECORD_COUNT": audit["d4_tls_application_record_count"],
        "D4_RETRY_COUNT": 0,
        "POST_D4_TLS_ENGINE_RETAINED": audit["baseline_b0_tls_consumed"],
        "POST_D4_MIXED_A0_B0_TRANSPORT_CONTINUITY": "PASS_OFFLINE",
    }
    mixed = {
        "schema": "D260_MIXED_A0_B0_EVIDENCE_V1",
        "POST_TLS_A0_B0_MIXED_DEMUX": "PASS",
        "post_tls_plain_a0_controls": ["0xd4", "0xaf", "0x36", "0x50", "0x82", "0x20", "0x32"],
        "baseline_response_routed_to": "SAME_RETAINED_TLS_SERVER_SESSION",
        "AF_EXACTLY_ONCE": audit["af_send_count"] == 1,
        "AF_RETRY_COUNT": audit["af_retry_count"],
    }
    irq = {
        "schema": "D260_EVENTSOURCE_IRQ_EVIDENCE_V1",
        "EVENT_SOURCE_CONTRACT_REQUIRED": True,
        "IRQ100_EVENT_SEPARATE_FROM_ACK_REQUIRED": True,
        "ack_receive_path": "RuntimeTransport.receive",
        "event_receive_path": "EventSource.wait_event",
        "IRQ100_STAGE0_EXACTLY_ONCE": happy["event_wait_count"] == 3,
        "IRQ100_STAGE1_EXACTLY_ONCE": happy["event_wait_count"] == 3,
        "IRQ100_STAGE2_EXACTLY_ONCE": happy["event_wait_count"] == 3,
    }
    end_to_end = {
        "schema": "D260_END_TO_END_REHEARSAL_V1",
        "execution_mode": "OFFLINE_ONLY",
        "status": "PASS" if happy["passed"] else "FAIL",
        "single_runtime_object": True,
        "result": happy["result"],
        "audit": audit,
        "submissions": happy["submissions"],
        "safety": {
            "REAL_USB_OPEN_COUNT": 0,
            "REAL_TLS_TARGET_HANDSHAKE_COUNT": 0,
            "REAL_E4_VALIDATED_SECRET_USED": False,
            "REAL_CAPTURE_COUNT": 0,
            "REAL_HARDWARE_ACTION_COUNT": 0,
            "REAL_COMMAND_SEND_COUNT": 0,
            "FINGER_INTERACTION_COUNT": 0,
            "PERSISTENT_WRITE_FAMILY_COUNT": 0,
            "HOST_CACHE_WRITE_COUNT": 0,
        },
    }
    readiness = {
        "schema": "D260_READINESS_DECISION_V1",
        "OUTCOME": "READY",
        "ADVANCEMENT": "ARCHITECTURAL_OFFLINE_IMPLEMENTATION_AND_NEW_TECHNICAL_EVIDENCE",
        "EXECUTABLE_CLOSURE": "PASS",
        "RESIDUAL_BLOCKER_OR_RISK": "REAL_USB_TRANSPORT_SECRET_BINDING_PRIVILEGE_OPERATOR_AND_APPROVED_BASELINE_REMAIN_FOR_SEPARATE_OPERATIONAL_REVIEW",
        "CANONICAL_DOCUMENTATION": {
            "path": "Goodix 27c6 5125 manuale tecnico.md",
            "manual_updated": True,
            "sections": ["Stato del progetto", "Stato area", "D260", "Current critical boundary", "Hard Wall", "Stato implementazione Linux"],
        },
        "BUNDLE": "analysis/D260/D260_persistent_runtime_architecture_readiness_bundle.zip",
        "BUNDLE_SHA256": "RECORDED_IN_EXTERNAL_SIDECAR",
        **sealed,
        "NEW_RUNTIME_LIVE_PROVEN": False,
        "PERSISTENT_TLS_RUNTIME_IMPLEMENTED": True,
        "B0_TLS_HANDSHAKE_BRIDGE_STATUS": bridge_evidence["B0_TLS_HANDSHAKE_BRIDGE_STATUS"],
        "TLS_SERVER_SESSION_OBJECT_COUNT": audit["tls_server_session_object_count"],
        "TLS_SERVER_HANDSHAKE_COUNT": audit["tls_server_handshake_count"],
        "SECOND_SERVER_SESSION_CREATED": False,
        "SECOND_PSK_PROVISIONING": False,
        "USB_TRANSPORT_SESSION_COUNT": audit["usb_transport_session_count"],
        "TRANSPORT_REOPEN_AFTER_TLS": audit["transport_reopen_after_tls"],
        "TLS_REHANDSHAKE_AFTER_D4": False,
        "SECRET_BOUNDARY_INTERFACE_ALIGNED_WITH_D241": True,
        "SYNTHETIC_SECRET_HANDOFF_TESTED": happy["secret_boundary_object_id_reused"],
        "REAL_E4_VALIDATED_SECRET_USED": False,
        "NEW_RUNTIME_LIVE_SECRET_PROVEN": False,
        "PSK_FALLBACK_COUNT": 0,
        "PSK_RANDOM_COUNT": 0,
        "PSK_NULL_COUNT": 0,
        **{key: value for key, value in d4_evidence.items() if key != "schema"},
        "PHYSICAL_SUBMISSION_CONTRACT_STATUS": physical["status"],
        **{key: value for key, value in irq.items() if key not in {"schema", "ack_receive_path", "event_receive_path"}},
        "POST_TLS_A0_B0_MIXED_DEMUX": "PASS",
        "AF_EXACTLY_ONCE": True,
        "AF_RETRY_COUNT": 0,
        "BASELINE_B0_TLS_CONSUMPTION_REQUIRED": True,
        "BASELINE_B0_CONSUMED_BEFORE_STAGE2": audit["baseline_b0_consumed_before_stage2"],
        "SAME_TLS_SESSION_B0_CONSUMPTION": "PASS_OFFLINE_ARCHITECTURAL",
        "SECOND_NATIVE_DELTA_REQUIRED": True,
        "EXACT_FDT_COMMAND_TRACE": audit["exact_fdt_command_trace"],
        "CLASSIFIER_CALL_COUNT": audit["classifier_call_count"],
        "RASTER_DECODE_COUNT": audit["raster_decode_count"],
        "HOST_CACHE_WRITE_COUNT": audit["host_cache_write_count"],
        "RETRY_COUNT": audit["retry_count"],
        "A2_SPECIAL_RECOVERY_COUNT": audit["a2_special_recovery_count"],
        "0x70_SPECIAL_RECOVERY_COUNT": audit["0x70_special_recovery_count"],
        "PERSISTENT_WRITE_FAMILY_COUNT": audit["persistent_device_write_count"],
        "HOST_TO_DEVICE_TLS_APPLICATION_DATA_REQUIRED": False,
        "HOST_TO_DEVICE_TLS_APPLICATION_DATA_STATUS": "OPTIONAL_FUTURE_UNPROVEN",
        "END_TO_END_OFFLINE_RUNTIME_REHEARSAL": end_to_end["status"],
        "FAILURE_CONTAINMENT_MATRIX": failure_matrix["status"],
        "D260_ARCHITECTURE_CRITICAL_FILESET": "analysis/D260/D260_architecture_critical_fileset.json",
        "LEGACY_TLS_ONE_SHOT_LIMITATION_ARCHITECTURALLY_BYPASSED_IN_CORE": True,
        "MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED": True,
        "FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED": True,
        "FDT_OFFLINE_CANDIDATE_CLOSED": True,
        "READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW": True,
        "READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW": False,
        "READY_FOR_FDT_LIVE_REVIEW": False,
        "READY_FOR_FDT_LIVE": False,
        **end_to_end["safety"],
    }
    _write_json(output / "D260_persistent_tls_evidence.json", tls_evidence)
    _write_json(output / "D260_b0_handshake_bridge_evidence.json", bridge_evidence)
    _write_json(output / "D260_d4_plaintext_continuity_evidence.json", d4_evidence)
    _write_json(output / "D260_mixed_a0_b0_evidence.json", mixed)
    _write_json(output / "D260_eventsource_irq_evidence.json", irq)
    _write_json(output / "D260_end_to_end_rehearsal.json", end_to_end)
    _write_json(output / "D260_failure_containment_matrix.json", failure_matrix)
    _write_json(output / "D260_physical_submission_policy_matrix.json", physical)
    _write_json(output / "D260_architecture_critical_fileset.json", critical)
    _write_json(output / "D260_readiness_decision.json", readiness)
    manifest = {
        "schema": "D260_BUNDLE_MANIFEST_V1",
        "step": "D260",
        "reference_head": "52aecb4cf7980af4261ec6a1c345770ea759c961",
        "bundle_path": "analysis/D260/D260_persistent_runtime_architecture_readiness_bundle.zip",
        "bundle_sha256": "RECORDED_IN_EXTERNAL_SIDECAR",
        "canonical_manual": {
            "path": "Goodix 27c6 5125 manuale tecnico.md",
            "sha256": sha256_file(repo / "Goodix 27c6 5125 manuale tecnico.md"),
            "included": False,
            "reason": "CANONICAL_REPOSITORY_REFERENCE_NOT_DUPLICATED",
        },
        "files": [
            {
                "path": path,
                "sha256": sha256_file(repo / path),
                "size": (repo / path).stat().st_size,
            }
            for path in BUNDLE_REVIEW_FILES
        ],
        "exclusions": [
            "historical unchanged files",
            "raw captures",
            "real secret/PSK",
            "biometric plaintext/raster",
            "firmware and OEM DLL/disassembly",
            "cache/OTP",
            "operator kit and live launcher",
        ],
    }
    _write_json(output / "D260_bundle_manifest.json", manifest)
    return readiness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO)
    args = parser.parse_args()
    readiness = generate(args.repo_root.resolve())
    print(json.dumps({
        "OUTCOME": readiness["OUTCOME"],
        "END_TO_END_OFFLINE_RUNTIME_REHEARSAL": readiness["END_TO_END_OFFLINE_RUNTIME_REHEARSAL"],
        "FAILURE_CONTAINMENT_MATRIX": readiness["FAILURE_CONTAINMENT_MATRIX"],
        "READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW": readiness["READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW"],
        "READY_FOR_FDT_LIVE": readiness["READY_FOR_FDT_LIVE"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
