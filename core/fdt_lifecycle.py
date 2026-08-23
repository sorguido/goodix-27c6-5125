# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Offline-only fresh-FDT lifecycle and bootstrap composition.

This module models the target-observed OEM host/bus contract.  Canceling a
wait is a host receive cancellation, session re-entry injects no recovery
command, and terminal stop emits no device command.  Full cold-start is an
explicit external boundary and is never simulated as session re-entry.

There is no USB backend, retry loop, cache writeback, provisioning, firmware,
or persistent-command implementation here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Protocol

from core.fdt_seed import SeedProviderResult
from core.tls_b0 import B0ApplicationConsumer, B0ConsumptionResult
from core.post_d4 import (
    InvalidTransition,
    LengthMismatch,
    UnexpectedAck,
    UnexpectedEvent,
    build_nav_baseline,
    build_read_fdt_delta,
    build_set_image,
    build_fdt_down,
    build_fdt_manual,
    parse_baseline_image_b0_shape,
    parse_ack,
    parse_fdt_delta_response,
    parse_fdt_event,
    parse_image_payload,
    parse_nav_baseline_response,
)


class FdtLifecycleState(str, Enum):
    INITIALIZED_POST_D4 = "INITIALIZED_POST_D4"
    AF_STATE_KNOWN = "AF_STATE_KNOWN"
    FDT_BOOTSTRAP_SAMPLING = "FDT_BOOTSTRAP_SAMPLING"
    FDT_BOOTSTRAP_READY = "FDT_BOOTSTRAP_READY"
    FDT_ARMED_WAIT = "FDT_ARMED_WAIT"
    HOST_WAIT_CANCELED = "HOST_WAIT_CANCELED"
    SESSION_REENTRY = "SESSION_REENTRY"
    TERMINAL_STOPPED = "TERMINAL_STOPPED"
    FIRST_IMAGE_RECEIVED = "FIRST_IMAGE_RECEIVED"
    FULL_COLD_START_REQUIRED = "FULL_COLD_START_REQUIRED"
    FAILED_CLOSED = "FAILED_CLOSED"


SAFE_DEVICE_COMMANDS = frozenset({0x20, 0x22, 0x32, 0x36, 0x50, 0x82})
PERSISTENT_COMMAND_FAMILIES = frozenset({0xE0, 0xA4, 0xF0, 0xF4})
SPECIAL_RECOVERY_COMMANDS = frozenset({0xA2, 0x70})
EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE = (0x36, 0x50, 0x36, 0x82, 0x20, 0x36, 0x32)
COMMAND_TIMEOUT_POLICY = "PER_COMMAND_EVIDENCE_BOUNDED"
COMMAND_TIMEOUT_MS = {
    0x36: 500,
    0x50: 500,
    0x82: 500,
    0x20: 2000,
    0x32: 100,
}
# Compatibility name: end-to-end OEM FDT-base acquisition budget, not the
# 100 ms ACK-only constant inside ChicagoHUSetMode.
FIRST_FDT36_COMMAND_TIMEOUT_MS = COMMAND_TIMEOUT_MS[0x36]


@dataclass(frozen=True)
class LifecycleTransition:
    sequence: int
    session_generation: int
    source: str
    event: str
    target: str
    host_actions: tuple[str, ...]
    device_commands: tuple[int, ...]

    def redacted(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "session_generation": self.session_generation,
            "source": self.source,
            "event": self.event,
            "target": self.target,
            "host_actions": list(self.host_actions),
            "device_commands": [f"0x{value:02x}" for value in self.device_commands],
        }


class FdtLifecycle:
    """Fail-closed lifecycle with a monotonically numbered audit trail."""

    def __init__(self) -> None:
        self.state = FdtLifecycleState.INITIALIZED_POST_D4
        self.session_generation = 0
        self.retry_count = 0
        self.persistent_write_family_count = 0
        self.fresh_path: bool | None = None
        self.arm_attempts_by_generation: dict[int, int] = {}
        self.transitions: list[LifecycleTransition] = []

    def _record(
        self,
        event: str,
        target: FdtLifecycleState,
        *,
        host_actions: tuple[str, ...] = (),
        device_commands: tuple[int, ...] = (),
    ) -> LifecycleTransition:
        if any(command not in SAFE_DEVICE_COMMANDS for command in device_commands):
            self.fail_closed(f"non_allowlisted_device_command:{device_commands!r}")
            raise InvalidTransition("lifecycle_device_command_not_allowlisted")
        if set(device_commands) & (PERSISTENT_COMMAND_FAMILIES | SPECIAL_RECOVERY_COMMANDS):
            self.fail_closed("persistent_or_recovery_command_reachable")
            raise InvalidTransition("persistent_or_recovery_command_reachable")
        transition = LifecycleTransition(
            sequence=len(self.transitions) + 1,
            session_generation=self.session_generation,
            source=self.state.value,
            event=event,
            target=target.value,
            host_actions=host_actions,
            device_commands=device_commands,
        )
        self.transitions.append(transition)
        self.state = target
        return transition

    def _require(self, *states: FdtLifecycleState) -> None:
        if self.state in states:
            return
        current = self.state.value
        expected = ",".join(state.value for state in states)
        self.fail_closed(f"invalid_transition:{current}:expected:{expected}")
        raise InvalidTransition(f"lifecycle_state:{current}:expected:{expected}")

    def fail_closed(self, reason: str) -> None:
        if self.state == FdtLifecycleState.FAILED_CLOSED:
            return
        self._record(
            f"FAIL_CLOSED:{reason}",
            FdtLifecycleState.FAILED_CLOSED,
            host_actions=(
                "STOP_NEW_TRAFFIC",
                "CANCEL_PENDING_RECEIVE_IF_ANY",
                "TERMINAL_HOST_CLEANUP",
            ),
        )

    def observe_af_state(self, pov_valid: bool) -> LifecycleTransition:
        self._require(FdtLifecycleState.INITIALIZED_POST_D4)
        self.fresh_path = not pov_valid
        return self._record("AF_STATE_OBSERVED", FdtLifecycleState.AF_STATE_KNOWN)

    def begin_bootstrap(self) -> LifecycleTransition:
        self._require(FdtLifecycleState.AF_STATE_KNOWN)
        if self.fresh_path is not True:
            self.fail_closed("fresh_bootstrap_without_fresh_af_path")
            raise InvalidTransition("fresh_bootstrap_without_fresh_af_path")
        return self._record("BEGIN_FRESH_FDT_BOOTSTRAP", FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING)

    def manual_sample_attempt(self, stage: int) -> LifecycleTransition:
        self._require(FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING)
        return self._record(
            f"FDT_MANUAL_SAMPLE_{stage}_ATTEMPT",
            FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING,
            device_commands=(0x36,),
        )

    def manual_sample_completed(self, stage: int) -> LifecycleTransition:
        self._require(FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING)
        return self._record(
            f"FDT_MANUAL_SAMPLE_{stage}_IRQ100_ACCEPTED",
            FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING,
        )

    def interstage_attempt(self, name: str, command: int) -> LifecycleTransition:
        self._require(FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING)
        return self._record(
            f"INTERSTAGE_{name}_ATTEMPT",
            FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING,
            device_commands=(command,),
        )

    def interstage_completed(self, name: str) -> LifecycleTransition:
        self._require(FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING)
        return self._record(
            f"INTERSTAGE_{name}_GATE_ACCEPTED",
            FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING,
        )

    def bootstrap_completed(self) -> LifecycleTransition:
        self._require(FdtLifecycleState.FDT_BOOTSTRAP_SAMPLING)
        return self._record("FDT_BOOTSTRAP_COMPLETED", FdtLifecycleState.FDT_BOOTSTRAP_READY)

    def arm_fdt(self) -> LifecycleTransition:
        self._require(
            FdtLifecycleState.AF_STATE_KNOWN,
            FdtLifecycleState.FDT_BOOTSTRAP_READY,
            FdtLifecycleState.SESSION_REENTRY,
        )
        if self.fresh_path is not True:
            self.fail_closed("fdt_arm_without_fresh_af_path")
            raise InvalidTransition("fdt_arm_without_fresh_af_path")
        attempts = self.arm_attempts_by_generation.get(self.session_generation, 0)
        if attempts:
            self.fail_closed("implicit_fdt_arm_retry_forbidden")
            raise InvalidTransition("implicit_fdt_arm_retry_forbidden")
        self.arm_attempts_by_generation[self.session_generation] = attempts + 1
        return self._record(
            "FDT_ARM_ATTEMPT",
            FdtLifecycleState.FDT_ARMED_WAIT,
            device_commands=(0x32,),
        )

    def post_irq2_image_command(self) -> LifecycleTransition:
        self._require(FdtLifecycleState.FDT_ARMED_WAIT)
        return self._record(
            "POST_IRQ2_IMAGE_COMMAND_ATTEMPT",
            FdtLifecycleState.FDT_ARMED_WAIT,
            device_commands=(0x22,),
        )

    def first_image_received(self) -> LifecycleTransition:
        self._require(FdtLifecycleState.FDT_ARMED_WAIT)
        return self._record("FIRST_IMAGE_VALIDATED", FdtLifecycleState.FIRST_IMAGE_RECEIVED)

    def cancel_pending_receive(self) -> LifecycleTransition:
        self._require(FdtLifecycleState.FDT_ARMED_WAIT)
        return self._record(
            "HOST_CANCEL_PENDING_RECEIVE",
            FdtLifecycleState.HOST_WAIT_CANCELED,
            host_actions=("CANCEL_PENDING_BULK_IN",),
        )

    def begin_session_reentry(self) -> LifecycleTransition:
        self._require(FdtLifecycleState.HOST_WAIT_CANCELED)
        self.session_generation += 1
        return self._record(
            "BEGIN_SESSION_REENTRY",
            FdtLifecycleState.SESSION_REENTRY,
            host_actions=("OEM_STYLE_REENTRY_STATE_PATH",),
        )

    def terminal_stop(self) -> LifecycleTransition:
        self._require(FdtLifecycleState.HOST_WAIT_CANCELED)
        return self._record(
            "TERMINAL_STOP",
            FdtLifecycleState.TERMINAL_STOPPED,
            host_actions=("STOP_SESSION",),
        )

    def request_full_cold_start(self) -> LifecycleTransition:
        """Expose a distinct boundary without implementing its wire sequence."""
        self._require(FdtLifecycleState.TERMINAL_STOPPED)
        self.session_generation += 1
        return self._record(
            "REQUEST_FULL_COLD_START",
            FdtLifecycleState.FULL_COLD_START_REQUIRED,
            host_actions=("DELEGATE_TO_EXISTING_FULL_COLD_START",),
        )

    @property
    def device_command_trace(self) -> tuple[int, ...]:
        return tuple(command for row in self.transitions for command in row.device_commands)

    def audit(self) -> dict[str, object]:
        trace = self.device_command_trace
        return {
            "state": self.state.value,
            "session_generation": self.session_generation,
            "transition_count": len(self.transitions),
            "transitions": [row.redacted() for row in self.transitions],
            "device_command_trace": [f"0x{value:02x}" for value in trace],
            "retry_count": self.retry_count,
            "persistent_write_family_count": self.persistent_write_family_count,
            "a2_injection_count": trace.count(0xA2),
            "0x70_injection_count": trace.count(0x70),
        }


class OfflineTransport(Protocol):
    def exchange(self, request: bytes, *, timeout_ms: int | None = None) -> Iterable[bytes]:
        ...


def table_from_irq100_payload(payload: bytes) -> bytes:
    """Derive the six-word FDT table using the D252 target-observed transform."""
    event = parse_fdt_event(payload)
    if event.irq != 0x100 or event.touch_flags != 0 or event.raw_base is None:
        raise UnexpectedEvent("manual_sample_requires_irq100_touch_zero_raw12")
    if len(event.raw_base) != 12:
        raise LengthMismatch("manual_sample_raw_base_length")
    learned = bytearray()
    for offset in range(0, 12, 2):
        word = int.from_bytes(event.raw_base[offset:offset + 2], "little")
        component = (word >> 1) & 0xFF
        if component in (0, 0xFF):
            raise UnexpectedEvent("manual_sample_baseline_validator_rejected_word")
        learned += bytes((0x80, component))
    return bytes(learned)


def raw_words_from_irq100_payload(payload: bytes) -> tuple[int, ...]:
    """Return the six unsigned OEM FDT-base words from an IRQ 0x0100."""
    event = parse_fdt_event(payload)
    if event.irq != 0x100 or event.touch_flags != 0 or event.raw_base is None:
        raise UnexpectedEvent("manual_sample_requires_irq100_touch_zero_raw12")
    if len(event.raw_base) != 12:
        raise LengthMismatch("manual_sample_raw_base_length")
    return tuple(
        int.from_bytes(event.raw_base[offset:offset + 2], "little")
        for offset in range(0, 12, 2)
    )


def fdt_delta_threshold(response_data: bytes) -> int:
    """Decode the OEM threshold from a two-byte register-0x0082 read."""
    if len(response_data) != 2:
        raise LengthMismatch(f"fdt_delta_response_length:{len(response_data)}")
    return response_data[1]


def fdt_raw_delta_within_threshold(
    first: tuple[int, ...],
    second: tuple[int, ...],
    threshold: int,
) -> bool:
    """Apply the OEM unsigned absolute-delta test to two raw FDT bases."""
    if len(first) != len(second) or not first:
        raise LengthMismatch("fdt_delta_word_count")
    if not 0 <= threshold <= 0xFF:
        raise ValueError("fdt_delta_threshold_range")
    if any(not 0 <= value <= 0xFFFF for value in (*first, *second)):
        raise ValueError("fdt_delta_word_range")
    return all(abs(left - right) <= threshold for left, right in zip(first, second))


class FreshFdtBootstrapMachine:
    """Exactly-three-stage FDT bootstrap plus cancel/re-entry/stop projection.

    The three stages are named successful OEM stages, not retries.  Inter-stage
    NAV/base-image work remains outside this FDT-only composition and is not
    claimed to be causally optional.
    """

    MANUAL_STAGE_COUNT = 3

    def __init__(self, transport: OfflineTransport, lifecycle: FdtLifecycle) -> None:
        self.transport = transport
        self.lifecycle = lifecycle
        self.table12: bytes | None = None
        self.manual_stage = 0
        self.manual_attempt_count = 0
        self.arm_attempt_count = 0

    @staticmethod
    def _exchange_optional_ack(transport: OfflineTransport, request: bytes, echo: int) -> None:
        frames = list(transport.exchange(request))
        if len(frames) > 1:
            raise UnexpectedAck(f"ack_frame_count:{len(frames)}")
        if frames:
            parse_ack(frames[0], echo)

    def begin(self, seed_result: SeedProviderResult) -> None:
        if not seed_result.ok:
            self.lifecycle.fail_closed(seed_result.failure_reason or "seed_provider_fail_closed")
            raise InvalidTransition("seed_provider_fail_closed")
        self.lifecycle.begin_bootstrap()
        self.table12 = seed_result.require_seed()

    def manual_sample(self, event_payload: bytes) -> bytes:
        if self.table12 is None or self.manual_stage >= self.MANUAL_STAGE_COUNT:
            self.lifecycle.fail_closed("manual_sample_invalid_stage")
            raise InvalidTransition("manual_sample_invalid_stage")
        stage = self.manual_stage
        self.lifecycle.manual_sample_attempt(stage)
        self.manual_attempt_count += 1
        try:
            self._exchange_optional_ack(self.transport, build_fdt_manual(self.table12), 0x36)
            learned = table_from_irq100_payload(event_payload)
        except Exception:
            self.lifecycle.fail_closed(f"manual_sample_{stage}_failed")
            raise
        self.table12 = learned
        self.manual_stage += 1
        self.lifecycle.manual_sample_completed(stage)
        if self.manual_stage == self.MANUAL_STAGE_COUNT:
            self.lifecycle.bootstrap_completed()
        return learned

    def arm(self, ts16: int) -> None:
        if self.table12 is None or self.manual_stage != self.MANUAL_STAGE_COUNT:
            self.lifecycle.fail_closed("arm_before_bootstrap_complete")
            raise InvalidTransition("arm_before_bootstrap_complete")
        self.lifecycle.arm_fdt()
        self.arm_attempt_count += 1
        try:
            self._exchange_optional_ack(self.transport, build_fdt_down(self.table12, ts16), 0x32)
        except Exception:
            self.lifecycle.fail_closed("fdt_arm_exchange_failed")
            raise

    def cancel_pending_receive(self) -> None:
        self.lifecycle.cancel_pending_receive()

    def reenter_and_arm(self, ts16: int) -> None:
        self.lifecycle.begin_session_reentry()
        if self.table12 is None:
            self.lifecycle.fail_closed("reentry_table_missing")
            raise InvalidTransition("reentry_table_missing")
        self.lifecycle.arm_fdt()
        self.arm_attempt_count += 1
        try:
            self._exchange_optional_ack(self.transport, build_fdt_down(self.table12, ts16), 0x32)
        except Exception:
            self.lifecycle.fail_closed("reentry_arm_exchange_failed")
            raise

    def terminal_cancel_and_stop(self) -> None:
        self.lifecycle.cancel_pending_receive()
        self.lifecycle.terminal_stop()


class ExactFreshFdtBootstrapMachine:
    """Bounded exact-order OEM bootstrap candidate.

    Unlike ``FreshFdtBootstrapMachine`` (the historical projected
    subsequence), this machine enforces the target-observed 0x50, 0x82 and
    0x20 inter-stage work.  NAV and baseline data are acquired before the third
    manual sample but consumed by the OEM classifier only after it.  The native
    0x82 predicate is enforced immediately; unresolved post-sample classifiers
    remain injected fail-closed boundaries.  Capture bytes are never truth
    predicates.
    """

    MANUAL_STAGE_COUNT = 3

    def __init__(
        self,
        transport: OfflineTransport,
        lifecycle: FdtLifecycle,
        *,
        nav_semantic_gate: Callable[[bytes], bool] | None = None,
        decrypt_baseline_b0: Callable[[bytes], bytes] | None = None,
        baseline_semantic_gate: Callable[[tuple[int, ...]], bool] | None = None,
    ) -> None:
        self.transport = transport
        self.lifecycle = lifecycle
        self.nav_semantic_gate = nav_semantic_gate
        self.decrypt_baseline_b0 = decrypt_baseline_b0
        self.baseline_semantic_gate = baseline_semantic_gate
        self.table12: bytes | None = None
        self.manual_stage = 0
        self.manual_attempt_count = 0
        self.first_0x36_attempt_count = 0
        self.first_0x36_timeout_ms = FIRST_FDT36_COMMAND_TIMEOUT_MS
        self.arm_attempt_count = 0
        self.nav_gate_passed = False
        self.delta_gate_passed = False
        self.second_delta_gate_passed = False
        self.baseline_gate_passed = False
        self.nav_dynamic_state: bytes | None = None
        self.baseline_b0: bytes | None = None
        self.raw_fdt_samples: list[tuple[int, ...]] = []
        self.delta_threshold: int | None = None
        self.host_decisions_finalized = False
        self.baseline_b0_tls_consumed = False
        self.baseline_b0_consumed_at_manual_stage: int | None = None
        self.semantic_classifier_call_count = 0
        self.raster_decode_count = 0
        self.host_cache_write_count = 0

    def _fail(self, reason: str) -> None:
        self.lifecycle.fail_closed(reason)

    def _required_exchange(self, request: bytes, echo: int, response_count: int) -> list[bytes]:
        timeout_ms = COMMAND_TIMEOUT_MS.get(echo)
        if timeout_ms is None:
            raise InvalidTransition(f"missing_command_timeout:0x{echo:02x}")
        frames = list(self.transport.exchange(request, timeout_ms=timeout_ms))
        if len(frames) != response_count + 1:
            raise UnexpectedAck(
                f"required_ack_response_count:0x{echo:02x}:{len(frames)}"
            )
        parse_ack(frames[0], echo)
        return frames[1:]

    def begin(self, seed_result: SeedProviderResult) -> None:
        if not seed_result.ok:
            self._fail(seed_result.failure_reason or "seed_provider_fail_closed")
            raise InvalidTransition("seed_provider_fail_closed")
        self.lifecycle.begin_bootstrap()
        self.table12 = seed_result.require_seed()

    def manual_sample(self, event_payload: bytes) -> bytes:
        if self.table12 is None or self.manual_stage >= self.MANUAL_STAGE_COUNT:
            self._fail("manual_sample_invalid_stage")
            raise InvalidTransition("manual_sample_invalid_stage")
        if self.manual_stage == 1 and self.nav_dynamic_state is None:
            self._fail("second_manual_stage_before_nav_acquisition")
            raise InvalidTransition("second_manual_stage_before_nav_acquisition")
        if self.manual_stage == 2 and not (
            self.delta_gate_passed
            and (self.baseline_b0 is not None or self.baseline_b0_tls_consumed)
        ):
            self._fail("third_manual_stage_before_delta_and_baseline_acquisition")
            raise InvalidTransition("third_manual_stage_before_delta_and_baseline_acquisition")
        stage = self.manual_stage
        self.lifecycle.manual_sample_attempt(stage)
        self.manual_attempt_count += 1
        if stage == 0:
            self.first_0x36_attempt_count += 1
        try:
            self._required_exchange(build_fdt_manual(self.table12), 0x36, 0)
            raw_words = raw_words_from_irq100_payload(event_payload)
            learned = table_from_irq100_payload(event_payload)
        except Exception:
            self._fail(f"manual_sample_{stage}_failed")
            raise
        self.table12 = learned
        self.raw_fdt_samples.append(raw_words)
        self.manual_stage += 1
        self.lifecycle.manual_sample_completed(stage)
        if self.manual_stage == self.MANUAL_STAGE_COUNT:
            self.lifecycle.bootstrap_completed()
        return learned

    def nav_interstage(self) -> None:
        if self.manual_stage != 1 or self.nav_dynamic_state is not None:
            self._fail("nav_interstage_wrong_order")
            raise InvalidTransition("nav_interstage_wrong_order")
        self.lifecycle.interstage_attempt("0x50_NAV", 0x50)
        try:
            response = self._required_exchange(build_nav_baseline(), 0x50, 1)[0]
            nav = parse_nav_baseline_response(response)
            self.nav_dynamic_state = bytes(nav)
        except Exception:
            self._fail("nav_interstage_failed")
            raise
        self.lifecycle.interstage_completed("0x50_NAV_STORED")

    def delta_and_baseline_interstage(
        self, consumer: B0ApplicationConsumer | None = None
    ) -> None:
        if self.manual_stage != 2 or self.delta_gate_passed or self.baseline_gate_passed:
            self._fail("delta_baseline_interstage_wrong_order")
            raise InvalidTransition("delta_baseline_interstage_wrong_order")
        self.lifecycle.interstage_attempt("0x82_FDT_DELTA", 0x82)
        try:
            response = self._required_exchange(build_read_fdt_delta(), 0x82, 1)[0]
            delta = parse_fdt_delta_response(response)
            if len(self.raw_fdt_samples) != 2:
                raise InvalidTransition("delta_requires_two_raw_fdt_samples")
            threshold = fdt_delta_threshold(delta)
            if not fdt_raw_delta_within_threshold(
                self.raw_fdt_samples[0], self.raw_fdt_samples[1], threshold
            ):
                raise UnexpectedEvent("fdt_delta_threshold_rejected")
            self.delta_threshold = threshold
        except Exception:
            self._fail("delta_interstage_failed")
            raise
        self.delta_gate_passed = True
        self.lifecycle.interstage_completed("0x82_FDT_DELTA")

        self.lifecycle.interstage_attempt("0x20_BASELINE_IMAGE", 0x20)
        try:
            response = self._required_exchange(build_set_image(), 0x20, 1)[0]
            parse_baseline_image_b0_shape(response)
            self.baseline_b0 = bytes(response)
            if consumer is not None:
                result = consumer.consume(self.baseline_b0)
                if not isinstance(result, B0ConsumptionResult) or not result.accepted:
                    raise InvalidTransition("baseline_b0_tls_consumption_unproven")
                self.baseline_b0_tls_consumed = True
                self.baseline_b0_consumed_at_manual_stage = self.manual_stage
                self.baseline_b0 = None
        except Exception:
            self._fail("baseline_interstage_failed")
            raise
        self.lifecycle.interstage_completed(
            "0x20_BASELINE_B0_TLS_CONSUMED"
            if self.baseline_b0_tls_consumed
            else "0x20_BASELINE_IMAGE_ACQUIRED"
        )

    def finalize_host_base_decisions(self) -> None:
        """Run post-stage2 NAV/image decisions, failing closed while unknown."""
        if self.manual_stage != self.MANUAL_STAGE_COUNT or self.host_decisions_finalized:
            self._fail("host_base_decisions_wrong_order")
            raise InvalidTransition("host_base_decisions_wrong_order")
        if self.nav_dynamic_state is None or self.baseline_b0 is None:
            self._fail("host_base_decision_inputs_missing")
            raise InvalidTransition("host_base_decision_inputs_missing")
        try:
            if len(self.raw_fdt_samples) != 3 or self.delta_threshold is None:
                raise InvalidTransition("second_delta_requires_three_raw_fdt_samples")
            if not fdt_raw_delta_within_threshold(
                self.raw_fdt_samples[1], self.raw_fdt_samples[2], self.delta_threshold
            ):
                raise UnexpectedEvent("second_fdt_delta_threshold_rejected")
            self.second_delta_gate_passed = True
            if self.nav_semantic_gate is None:
                raise InvalidTransition("nav_post_sample_classifier_unavailable")
            if not self.nav_semantic_gate(self.nav_dynamic_state):
                raise UnexpectedEvent("nav_post_sample_classifier_rejected")
            if self.decrypt_baseline_b0 is None:
                raise InvalidTransition("baseline_b0_decryptor_unavailable")
            pixels = parse_image_payload(self.decrypt_baseline_b0(self.baseline_b0))
            if self.baseline_semantic_gate is None:
                raise InvalidTransition("baseline_post_sample_classifier_unavailable")
            if not self.baseline_semantic_gate(pixels):
                raise UnexpectedEvent("baseline_post_sample_classifier_rejected")
        except Exception:
            self._fail("post_sample_host_base_decisions_failed")
            raise
        self.nav_gate_passed = True
        self.baseline_gate_passed = True
        self.host_decisions_finalized = True

    def finalize_minimal_device_contract(self) -> None:
        """Close only device-visible post-stage2 work.

        D259 proves that OEM classifier returns affect host base/cache fidelity,
        not the final FDT table, payload, command sequence, or reachability.
        The second native delta predicate remains mandatory.  The encrypted
        baseline B0 must already have been consumed by the active TLS session
        immediately after ``0x20`` and before stage2.  No plaintext is decoded,
        classified, persisted, or retained here.
        """
        if self.manual_stage != self.MANUAL_STAGE_COUNT or self.host_decisions_finalized:
            self._fail("minimal_device_contract_wrong_order")
            raise InvalidTransition("minimal_device_contract_wrong_order")
        if self.nav_dynamic_state is None or not self.baseline_b0_tls_consumed:
            self._fail("minimal_device_contract_inputs_missing")
            raise InvalidTransition("minimal_device_contract_inputs_missing")
        try:
            if len(self.raw_fdt_samples) != 3 or self.delta_threshold is None:
                raise InvalidTransition("second_delta_requires_three_raw_fdt_samples")
            if not fdt_raw_delta_within_threshold(
                self.raw_fdt_samples[1], self.raw_fdt_samples[2], self.delta_threshold
            ):
                raise UnexpectedEvent("second_fdt_delta_threshold_rejected")
            self.second_delta_gate_passed = True
            if self.baseline_b0_consumed_at_manual_stage != 2:
                raise InvalidTransition("baseline_b0_not_consumed_before_stage2")
        except Exception:
            self._fail("minimal_device_contract_finalization_failed")
            raise
        self.host_decisions_finalized = True

    def arm(self, ts16: int) -> None:
        if (
            self.table12 is None
            or self.manual_stage != self.MANUAL_STAGE_COUNT
            or not self.host_decisions_finalized
        ):
            self._fail("arm_before_exact_bootstrap_complete")
            raise InvalidTransition("arm_before_exact_bootstrap_complete")
        self.lifecycle.arm_fdt()
        self.arm_attempt_count += 1
        try:
            self._required_exchange(build_fdt_down(self.table12, ts16), 0x32, 0)
        except Exception:
            self._fail("fdt_arm_exchange_failed")
            raise
