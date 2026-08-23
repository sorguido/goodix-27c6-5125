# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Persistent, offline-testable Goodix runtime coordinator.

The coordinator owns one transport session, one validated-secret boundary,
one TLS server engine, mixed A0/B0 routing, and the D259 minimal FDT lifecycle.
It has no USB backend, privilege handling, secret discovery, cache writer,
operator authorization, retry, or recovery command.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from core.fdt_lifecycle import (
    COMMAND_TIMEOUT_MS,
    EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE,
    ExactFreshFdtBootstrapMachine,
    FdtLifecycle,
)
from core.fdt_seed import SeedProviderResult
from core.post_d4 import (
    PLAIN,
    InvalidTransition,
    build_af,
    parse_af_response,
    parse_outer,
    parse_payload,
)
from core.runtime_transport import (
    AF_A0_POLICY,
    B0_TLS_POLICY,
    D1_A0_POLICY,
    D4_A0_POLICY,
    EventSource,
    RuntimeTransport,
    ValidatedSecretBoundary,
    fdt_a0_policy,
)
from core.tls_b0 import (
    B0ApplicationConsumer,
    B0TlsHandshakeBridge,
    Tls12PskServerSession,
    TlsSessionState,
)


D1_CANONICAL_REQUEST = bytes.fromhex("a00600a6d103000000d7")
D4_CANONICAL_REQUEST = bytes.fromhex("a00600a6d403000000d3")
D4_TIMEOUT_MS = 200
AF_TIMEOUT_MS = 500
TLS_HANDSHAKE_MAX_DEVICE_RECORDS = 8


class RuntimeState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED_CLOSED = "FAILED_CLOSED"
    CLOSED = "CLOSED"


class RuntimeFailure(RuntimeError):
    """A bounded runtime phase failed and no retry was attempted."""


@dataclass(frozen=True)
class RuntimeResult:
    command_trace: tuple[int, ...]
    tls_state_before_cleanup: str
    baseline_b0_consumed_before_stage2: bool
    second_native_delta_passed: bool


class _FdtTransportAdapter:
    """Adapt receive-oriented runtime I/O to the bounded FDT machine."""

    _RESPONSE_COUNTS = {0x36: 1, 0x50: 2, 0x82: 2, 0x20: 2, 0x32: 1}

    def __init__(self, transport: RuntimeTransport) -> None:
        self.transport = transport

    def exchange(
        self, request: bytes, *, timeout_ms: int | None = None
    ) -> Iterable[bytes]:
        kind, payload = parse_outer(request)
        if kind != PLAIN:
            raise RuntimeFailure("fdt_request_not_a0")
        control, _data = parse_payload(payload)
        expected_timeout = COMMAND_TIMEOUT_MS.get(control)
        if expected_timeout is None or timeout_ms != expected_timeout:
            raise RuntimeFailure(f"fdt_timeout_policy_mismatch:0x{control:02x}")
        count = self._RESPONSE_COUNTS.get(control)
        if count is None:
            raise RuntimeFailure(f"fdt_response_policy_missing:0x{control:02x}")
        self.transport.submit(request, fdt_a0_policy(control, timeout_ms))
        return tuple(self.transport.receive(timeout_ms) for _ in range(count))


class PersistentRuntimeCoordinator:
    """Run D1→TLS→D4→AF→minimal-FDT on one retained runtime object."""

    def __init__(
        self,
        transport: RuntimeTransport,
        event_source: EventSource,
        secret_boundary: ValidatedSecretBoundary,
    ) -> None:
        self.transport = transport
        self.event_source = event_source
        self.secret_boundary = secret_boundary
        self.state = RuntimeState.CREATED
        self.tls_session: Tls12PskServerSession | None = None
        self.tls_close_count = 0
        self.retry_count = 0
        self.d4_attempt_count = 0
        self.d4_send_count = 0
        self.d4_tls_application_record_count = 0
        self.af_attempt_count = 0
        self.af_send_count = 0
        self.af_retry_count = 0
        self.handshake_device_record_count = 0
        self.failure_reason: str | None = None
        self.lifecycle = FdtLifecycle()
        self.machine: ExactFreshFdtBootstrapMachine | None = None

    def _handshake(self) -> None:
        if self.tls_session is None:
            raise RuntimeFailure("tls_session_missing")
        bridge = B0TlsHandshakeBridge(self.tls_session)
        self.transport.submit(D1_CANONICAL_REQUEST, D1_A0_POLICY)
        while not self.tls_session.handshake_complete:
            if self.handshake_device_record_count >= TLS_HANDSHAKE_MAX_DEVICE_RECORDS:
                raise RuntimeFailure("tls_handshake_record_bound")
            incoming = self.transport.receive(D1_A0_POLICY.timeout_ms)
            self.handshake_device_record_count += 1
            for outgoing in bridge.accept_handshake_b0(incoming):
                self.transport.submit(outgoing, B0_TLS_POLICY)
        if self.tls_session.handshake_count != 1:
            raise RuntimeFailure("tls_handshake_count_not_one")

    def _d4(self) -> None:
        if self.tls_session is None or not self.tls_session.handshake_complete:
            raise RuntimeFailure("d4_without_established_tls")
        self.d4_attempt_count += 1
        if self.d4_attempt_count != 1:
            raise RuntimeFailure("d4_retry_forbidden")
        chunks = D4_A0_POLICY.materialize(D4_CANONICAL_REQUEST)
        if len(chunks) != 1 or len(chunks[0]) != 64 or any(chunks[0][10:]):
            raise RuntimeFailure("d4_physical_policy_invalid")
        self.transport.submit(D4_CANONICAL_REQUEST, D4_A0_POLICY)
        self.d4_send_count += 1
        d4_ack = self.transport.receive(D4_TIMEOUT_MS)
        kind, payload = parse_outer(d4_ack)
        control, data = parse_payload(payload)
        if kind != PLAIN or control != 0xB0 or data != b"\xD4\x01":
            raise RuntimeFailure("d4_exact_ack_required")
        self.d4_tls_application_record_count = self.tls_session.application_record_count
        if self.d4_tls_application_record_count != 0:
            raise RuntimeFailure("d4_must_not_be_tls_application_data")

    def _af(self, ts16: int) -> None:
        self.af_attempt_count += 1
        if self.af_attempt_count != 1:
            raise RuntimeFailure("af_retry_forbidden")
        self.transport.submit(build_af(ts16), AF_A0_POLICY)
        self.af_send_count += 1
        state = parse_af_response(self.transport.receive(AF_TIMEOUT_MS))
        if state.pov_valid:
            raise RuntimeFailure("d260_requires_fresh_fdt_path")
        self.lifecycle.observe_af_state(state.pov_valid)

    def run(self, seed_result: SeedProviderResult, *, ts16: int) -> RuntimeResult:
        if self.state != RuntimeState.CREATED:
            raise RuntimeFailure("runtime_single_use")
        self.state = RuntimeState.RUNNING
        try:
            self.transport.open()
            self.tls_session = Tls12PskServerSession.from_boundary(self.secret_boundary)
            if not self.tls_session.uses_secret_boundary(self.secret_boundary):
                raise RuntimeFailure("tls_secret_boundary_identity_mismatch")
            self._handshake()
            self._d4()
            self._af(ts16)
            adapter = _FdtTransportAdapter(self.transport)
            self.machine = ExactFreshFdtBootstrapMachine(
                adapter,
                self.lifecycle,
                event_source=self.event_source,
            )
            self.machine.begin(seed_result)
            self.machine.manual_sample()
            self.machine.nav_interstage()
            self.machine.manual_sample()
            consumer = B0ApplicationConsumer(self.tls_session.application_session)
            self.machine.delta_and_baseline_interstage(consumer)
            if self.tls_session.state != TlsSessionState.APPLICATION_ACTIVE:
                raise RuntimeFailure("baseline_b0_not_consumed_by_retained_tls")
            self.machine.manual_sample()
            self.machine.finalize_minimal_device_contract()
            self.machine.arm(ts16)
            if tuple(self.lifecycle.device_command_trace) != EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE:
                raise RuntimeFailure("exact_fdt_command_trace_mismatch")
            result = RuntimeResult(
                command_trace=self.lifecycle.device_command_trace,
                tls_state_before_cleanup=self.tls_session.state.value,
                baseline_b0_consumed_before_stage2=(
                    self.machine.baseline_b0_consumed_at_manual_stage == 2
                ),
                second_native_delta_passed=self.machine.second_delta_gate_passed,
            )
            self.state = RuntimeState.COMPLETED
            return result
        except Exception as error:
            self.failure_reason = f"{type(error).__name__}:{error}"
            self.state = RuntimeState.FAILED_CLOSED
            try:
                self.lifecycle.fail_closed("persistent_runtime_failure")
            except Exception:
                pass
            raise
        finally:
            if self.tls_session is not None:
                self.tls_session.close()
                self.tls_close_count = 1
            self.secret_boundary.close()
            self.transport.close()
            if self.state == RuntimeState.COMPLETED:
                self.state = RuntimeState.CLOSED

    def audit(self) -> dict[str, object]:
        session = self.tls_session
        machine = self.machine
        return {
            "runtime_state": self.state.value,
            "failure_reason": self.failure_reason,
            "usb_transport_session_count": self.transport.session_count,
            "transport_cleanup_count": self.transport.cleanup_count,
            "transport_reopen_after_tls": self.transport.session_count != 1,
            "tls_server_session_object_count": (
                session.server_session_object_count if session is not None else 0
            ),
            "tls_server_handshake_count": session.handshake_count if session is not None else 0,
            "tls_close_count": self.tls_close_count,
            "second_server_session_created": False,
            "second_psk_provisioning": (
                session.psk_context_provisioning_count != 1 if session is not None else False
            ),
            "secret_boundary_handoff_count": self.secret_boundary.handoff_count,
            "tls_uses_same_secret_boundary_object": bool(
                session and session.uses_secret_boundary(self.secret_boundary)
            ),
            "secret_boundary_zeroized": self.secret_boundary.zeroized,
            "d4_attempt_count": self.d4_attempt_count,
            "d4_send_count": self.d4_send_count,
            "d4_tls_application_record_count": self.d4_tls_application_record_count,
            "af_attempt_count": self.af_attempt_count,
            "af_send_count": self.af_send_count,
            "af_retry_count": self.af_retry_count,
            "retry_count": self.retry_count,
            "baseline_b0_tls_consumed": bool(machine and machine.baseline_b0_tls_consumed),
            "baseline_b0_consumed_before_stage2": bool(
                machine and machine.baseline_b0_consumed_at_manual_stage == 2
            ),
            "second_native_delta_passed": bool(machine and machine.second_delta_gate_passed),
            "classifier_call_count": machine.semantic_classifier_call_count if machine else 0,
            "raster_decode_count": machine.raster_decode_count if machine else 0,
            "host_cache_write_count": machine.host_cache_write_count if machine else 0,
            "persistent_device_write_count": self.lifecycle.persistent_write_family_count,
            "a2_special_recovery_count": self.lifecycle.device_command_trace.count(0xA2),
            "0x70_special_recovery_count": self.lifecycle.device_command_trace.count(0x70),
            "exact_fdt_command_trace": [
                f"0x{control:02x}" for control in self.lifecycle.device_command_trace
            ],
        }
