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
from typing import Callable, Iterable

from core.cold_start import ColdStartMachine, ColdStartMaterial, ColdStartResult

from core.fdt_lifecycle import (
    COMMAND_TIMEOUT_MS,
    EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE,
    ExactFreshFdtBootstrapMachine,
    FdtLifecycle,
)
from core.fdt_seed import SeedProviderResult
from core.post_d4 import (
    PLAIN,
    TLS,
    InvalidTransition,
    UnexpectedAck,
    build_af,
    build_finger_image,
    parse_ack,
    parse_af_response,
    parse_fdt_event,
    parse_image_payload,
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
    operational_fdt_a0_policy,
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
FIRST_IMAGE_IRQ2_TIMEOUT_MS = 5000
FIRST_IMAGE_B0_TIMEOUT_MS = 5000


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
    cold_start_completed: bool = False
    target_firmware: str | None = None
    irq2_observed: bool = False
    image_command_attempt_count: int = 0
    image_ack: str = "NONE"
    first_image_received: bool = False
    first_image_validation: str = "NOT_ATTEMPTED"
    first_image_raster_shape: tuple[int, int] | None = None
    first_image_bytes_persisted: bool = False
    terminal_cleanup_completed: bool = False


class _FdtTransportAdapter:
    """Adapt receive-oriented runtime I/O to the bounded FDT machine."""

    _RESPONSE_COUNTS = {0x36: 1, 0x50: 2, 0x82: 2, 0x20: 2, 0x32: 1}

    def __init__(self, transport: RuntimeTransport, *, operational_physical_policy: bool = False) -> None:
        self.transport = transport
        self.operational_physical_policy = operational_physical_policy

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
        policy_factory = operational_fdt_a0_policy if self.operational_physical_policy else fdt_a0_policy
        self.transport.submit(request, policy_factory(control, timeout_ms))
        return tuple(self.transport.receive(timeout_ms) for _ in range(count))


class PersistentRuntimeCoordinator:
    """Run D1→TLS→D4→AF→minimal-FDT on one retained runtime object."""

    def __init__(
        self,
        transport: RuntimeTransport,
        event_source: EventSource,
        secret_boundary: ValidatedSecretBoundary,
        *,
        cold_start_machine: ColdStartMachine | None = None,
        cold_start_material: ColdStartMaterial | None = None,
        seed_provider_from_live_otp: Callable[[bytes], SeedProviderResult] | None = None,
        operational_physical_policy: bool = False,
    ) -> None:
        self.transport = transport
        self.event_source = event_source
        self.secret_boundary = secret_boundary
        self.cold_start_machine = cold_start_machine
        self.cold_start_material = cold_start_material
        self.seed_provider_from_live_otp = seed_provider_from_live_otp
        self.operational_physical_policy = operational_physical_policy
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
        self.cold_start_result: ColdStartResult | None = None

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

    def run(self, seed_result: SeedProviderResult | None = None, *, ts16: int) -> RuntimeResult:
        if self.state != RuntimeState.CREATED:
            raise RuntimeFailure("runtime_single_use")
        self.state = RuntimeState.RUNNING
        try:
            self.transport.open()
            if self.cold_start_machine is not None:
                if self.cold_start_material is None or self.seed_provider_from_live_otp is None:
                    raise RuntimeFailure("cold_start_operational_inputs_missing")
                self.cold_start_result = self.cold_start_machine.run(self.cold_start_material)
                seed_result = self.seed_provider_from_live_otp(self.cold_start_result.otp64)
                if not seed_result.ok:
                    raise RuntimeFailure("live_otp_seed_binding_failed_before_first_0x36")
            elif seed_result is None:
                raise RuntimeFailure("seed_result_missing")
            self.tls_session = Tls12PskServerSession.from_boundary(self.secret_boundary)
            if not self.tls_session.uses_secret_boundary(self.secret_boundary):
                raise RuntimeFailure("tls_secret_boundary_identity_mismatch")
            self._handshake()
            self._d4()
            self._af(ts16)
            adapter = _FdtTransportAdapter(
                self.transport,
                operational_physical_policy=self.operational_physical_policy,
            )
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
            first_image = self._run_first_image_terminal()
            terminal_queue_gate = getattr(self.transport, "assert_no_buffered_frames", None)
            if callable(terminal_queue_gate):
                terminal_queue_gate()
            trace = tuple(self.lifecycle.device_command_trace)
            if trace[: len(EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE)] != EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE:
                raise RuntimeFailure("exact_fdt_command_trace_prefix_mismatch")
            extra = trace[len(EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE):]
            if any(command in {0x34, 0xA2, 0x70, 0x20} for command in extra):
                raise RuntimeFailure("forbidden_post_arm_command_in_trace")
            if extra != (0x22,):
                raise RuntimeFailure(f"unexpected_post_arm_commands:{extra!r}")
            result = RuntimeResult(
                command_trace=self.lifecycle.device_command_trace,
                tls_state_before_cleanup=self.tls_session.state.value,
                baseline_b0_consumed_before_stage2=(
                    self.machine.baseline_b0_consumed_at_manual_stage == 2
                ),
                second_native_delta_passed=self.machine.second_delta_gate_passed,
                cold_start_completed=self.cold_start_result is not None,
                target_firmware=(
                    self.cold_start_result.firmware if self.cold_start_result is not None else None
                ),
                irq2_observed=bool(first_image["irq2_observed"]),
                image_command_attempt_count=int(first_image["image_command_attempt_count"]),
                image_ack=str(first_image["image_ack"]),
                first_image_received=first_image["first_image_validation"] == "SUCCESS",
                first_image_validation=str(first_image["first_image_validation"]),
                first_image_raster_shape=first_image["first_image_raster_shape"],
                first_image_bytes_persisted=bool(first_image["first_image_bytes_persisted"]),
                terminal_cleanup_completed=bool(first_image["terminal_cleanup_completed"]),
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

    def _run_first_image_terminal(self) -> dict[str, object]:
        """Bounded offline candidate after FDT arm: one first image then stop.

        D262 arm complete -> bounded IRQ2 wait -> exactly-one 0x22 -> retained
        TLS first-image B0 -> canonical parser/codec -> FIRST_IMAGE_RECEIVED
        -> bounded host/TLS/USB cleanup -> stop. No 0x34, no post-image 0x20,
        no re-arm, no A2/0x70, no retry, no persistent write. The first-image
        plaintext is wiped after decode and never persisted.
        """

        outcome: dict[str, object] = {
            "irq2_observed": False,
            "image_command_attempt_count": 0,
            "image_ack": "NONE",
            "first_image_validation": "NOT_ATTEMPTED",
            "first_image_raster_shape": None,
            "first_image_bytes_persisted": False,
            "terminal_cleanup_completed": False,
        }
        # 1) bounded wait for finger-down IRQ 0x0002
        irq_frame = self.event_source.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS)
        kind, payload = parse_outer(irq_frame)
        if kind != PLAIN:
            raise RuntimeFailure("irq2_event_not_a0")
        event = parse_fdt_event(payload)
        if event.irq != 2:
            raise RuntimeFailure(f"expected_irq2_finger_down:0x{event.irq:x}")
        outcome["irq2_observed"] = True
        # 2) exactly one 0x22 image command on the same retained TLS session
        self.lifecycle.post_irq2_image_command()
        outcome["image_command_attempt_count"] = self.lifecycle.image_command_attempt_count
        self.transport.submit(
            build_finger_image(), fdt_a0_policy(0x22, COMMAND_TIMEOUT_MS[0x22])
        )
        ack_frame = self.transport.receive(COMMAND_TIMEOUT_MS[0x22])
        try:
            parse_ack(ack_frame, 0x22)
            outcome["image_ack"] = "ACK01_OR_07"
        except UnexpectedAck:
            raise RuntimeFailure("0x22_ack_invalid")
        # 3) retained TLS receives the first-image B0 and the canonical codec decodes it
        image_frame = self.transport.receive(FIRST_IMAGE_B0_TIMEOUT_MS)
        b0_kind, b0_body = parse_outer(image_frame)
        if b0_kind != TLS:
            raise RuntimeFailure("first_image_not_b0")
        try:
            plaintext = self.tls_session.application_session.consume_application_record(b0_body)
        except Exception:
            raise RuntimeFailure("first_image_b0_consumption_failed")
        try:
            raster = parse_image_payload(bytes(plaintext))
            outcome["first_image_validation"] = "SUCCESS"
            outcome["first_image_raster_shape"] = (len(raster) // 64, 64)
        except Exception:
            for index in range(len(plaintext)):
                plaintext[index] = 0
            raise RuntimeFailure("first_image_decode_failed")
        for index in range(len(plaintext)):
            plaintext[index] = 0
        # 4) transition + bounded host-only terminal cleanup (no device command)
        self.lifecycle.first_image_received()
        self.lifecycle.cancel_pending_receive()
        self.lifecycle.terminal_stop()
        outcome["terminal_cleanup_completed"] = True
        return outcome

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
            "cold_start_gpl_runtime_completed": self.cold_start_result is not None,
            "cold_start_phase_trace": (
                list(self.cold_start_result.phase_trace) if self.cold_start_result else []
            ),
            "cold_start_command_trace": (
                [f"0x{value:02x}" for value in self.cold_start_result.command_trace]
                if self.cold_start_result else []
            ),
            "target_firmware": self.cold_start_result.firmware if self.cold_start_result else None,
            "e4_validation_count": (
                self.cold_start_machine.e4_validation_count if self.cold_start_machine else 0
            ),
            "operational_fdt_physical_policy": self.operational_physical_policy,
            "classifier_call_count": machine.semantic_classifier_call_count if machine else 0,
            "raster_decode_count": machine.raster_decode_count if machine else 0,
            "host_cache_write_count": machine.host_cache_write_count if machine else 0,
            "persistent_device_write_count": self.lifecycle.persistent_write_family_count,
            "a2_special_recovery_count": self.lifecycle.device_command_trace.count(0xA2),
            "0x70_special_recovery_count": self.lifecycle.device_command_trace.count(0x70),
            "exact_fdt_command_trace": [
                f"0x{control:02x}" for control in self.lifecycle.device_command_trace
            ],
            "first_image_received": self.lifecycle.state.value == "FIRST_IMAGE_RECEIVED"
            or self.lifecycle.state.value == "TERMINAL_STOPPED",
            "image_command_attempt_count": getattr(
                self.lifecycle, "image_command_attempt_count", 0
            ),
            "first_image_validation": "INTEGRATED_IN_RUNTIME_RESULT",
            "first_image_bytes_persisted": False,
            "terminal_cleanup_completed": self.lifecycle.state.value == "TERMINAL_STOPPED",
        }
