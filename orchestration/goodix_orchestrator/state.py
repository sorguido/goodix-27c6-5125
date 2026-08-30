# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit state machine for the O001 deterministic core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class OrchestratorState(StrEnum):
    BOOTSTRAP = "BOOTSTRAP"
    IDLE = "IDLE"
    PM_PLANNING = "PM_PLANNING"
    TASK_READY = "TASK_READY"
    EXECUTOR_RUNNING = "EXECUTOR_RUNNING"
    EXECUTOR_RESULT_READY = "EXECUTOR_RESULT_READY"
    PM_REVIEWING = "PM_REVIEWING"
    HUMAN_GATE_WAIT = "HUMAN_GATE_WAIT"
    PAUSED_RATE_LIMIT = "PAUSED_RATE_LIMIT"
    PAUSED_MODEL_UNAVAILABLE = "PAUSED_MODEL_UNAVAILABLE"
    PAUSED_INFRASTRUCTURE = "PAUSED_INFRASTRUCTURE"
    DONE = "DONE"
    ERROR_LOCKED = "ERROR_LOCKED"


class StateEvent(StrEnum):
    BOOTSTRAP_COMPLETE = "BOOTSTRAP_COMPLETE"
    START_PLANNING = "START_PLANNING"
    TASK_PREPARED = "TASK_PREPARED"
    EXECUTOR_STARTED = "EXECUTOR_STARTED"
    EXECUTOR_COMPLETED = "EXECUTOR_COMPLETED"
    REVIEW_STARTED = "REVIEW_STARTED"
    ACCEPT = "ACCEPT"
    CORRECTIVE = "CORRECTIVE"
    REPLAN = "REPLAN"
    HUMAN_GATE = "HUMAN_GATE"
    PAUSE_RATE_LIMIT = "PAUSE_RATE_LIMIT"
    PAUSE_MODEL_UNAVAILABLE = "PAUSE_MODEL_UNAVAILABLE"
    PAUSE_INFRASTRUCTURE = "PAUSE_INFRASTRUCTURE"
    DONE = "DONE"
    GATE_APPROVE = "GATE_APPROVE"
    GATE_DENY = "GATE_DENY"
    RECONCILE_RESUME = "RECONCILE_RESUME"
    FAIL_CLOSED = "FAIL_CLOSED"


PAUSED_STATES = frozenset(
    {
        OrchestratorState.PAUSED_RATE_LIMIT,
        OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
        OrchestratorState.PAUSED_INFRASTRUCTURE,
    }
)

RECOVERABLE_STATES = frozenset(
    {
        OrchestratorState.IDLE,
        OrchestratorState.PM_PLANNING,
        OrchestratorState.TASK_READY,
        OrchestratorState.EXECUTOR_RUNNING,
        OrchestratorState.EXECUTOR_RESULT_READY,
        OrchestratorState.PM_REVIEWING,
        OrchestratorState.HUMAN_GATE_WAIT,
    }
)

GATE_CONTINUATION_STATES = frozenset(
    {
        OrchestratorState.PM_PLANNING,
        OrchestratorState.TASK_READY,
        OrchestratorState.DONE,
    }
)


@dataclass(frozen=True, slots=True)
class StateTransitionError(Exception):
    code: str
    current_state: str
    event: str
    requested_target: str | None
    allowed_targets: tuple[str, ...]

    def __str__(self) -> str:
        target = f" -> {self.requested_target}" if self.requested_target else ""
        return (
            f"{self.code}: {self.current_state} + {self.event}{target}; "
            f"allowed={self.allowed_targets}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "current_state": self.current_state,
            "event": self.event,
            "requested_target": self.requested_target,
            "allowed_targets": list(self.allowed_targets),
        }


_FIXED_TRANSITIONS: dict[
    tuple[OrchestratorState, StateEvent], OrchestratorState
] = {
    (OrchestratorState.BOOTSTRAP, StateEvent.BOOTSTRAP_COMPLETE): OrchestratorState.IDLE,
    (OrchestratorState.IDLE, StateEvent.START_PLANNING): OrchestratorState.PM_PLANNING,
    (OrchestratorState.PM_PLANNING, StateEvent.TASK_PREPARED): OrchestratorState.TASK_READY,
    (OrchestratorState.TASK_READY, StateEvent.EXECUTOR_STARTED): OrchestratorState.EXECUTOR_RUNNING,
    (OrchestratorState.EXECUTOR_RUNNING, StateEvent.EXECUTOR_COMPLETED): OrchestratorState.EXECUTOR_RESULT_READY,
    (OrchestratorState.EXECUTOR_RESULT_READY, StateEvent.REVIEW_STARTED): OrchestratorState.PM_REVIEWING,
    (OrchestratorState.PM_REVIEWING, StateEvent.CORRECTIVE): OrchestratorState.TASK_READY,
    (OrchestratorState.PM_REVIEWING, StateEvent.REPLAN): OrchestratorState.PM_PLANNING,
    (OrchestratorState.PM_REVIEWING, StateEvent.HUMAN_GATE): OrchestratorState.HUMAN_GATE_WAIT,
    (OrchestratorState.PM_REVIEWING, StateEvent.PAUSE_RATE_LIMIT): OrchestratorState.PAUSED_RATE_LIMIT,
    (OrchestratorState.PM_REVIEWING, StateEvent.PAUSE_MODEL_UNAVAILABLE): OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
    (OrchestratorState.PM_REVIEWING, StateEvent.PAUSE_INFRASTRUCTURE): OrchestratorState.PAUSED_INFRASTRUCTURE,
    (OrchestratorState.PM_REVIEWING, StateEvent.DONE): OrchestratorState.DONE,
}


def parse_state(value: OrchestratorState | str) -> OrchestratorState:
    try:
        return value if isinstance(value, OrchestratorState) else OrchestratorState(value)
    except (TypeError, ValueError) as exc:
        raise StateTransitionError(
            "UNKNOWN_STATE", str(value), "NONE", None, tuple(state.value for state in OrchestratorState)
        ) from exc


def parse_event(value: StateEvent | str) -> StateEvent:
    try:
        return value if isinstance(value, StateEvent) else StateEvent(value)
    except (TypeError, ValueError) as exc:
        raise StateTransitionError(
            "UNKNOWN_EVENT", "UNKNOWN", str(value), None, tuple(event.value for event in StateEvent)
        ) from exc


def transition(
    current: OrchestratorState | str,
    event: StateEvent | str,
    *,
    target: OrchestratorState | str | None = None,
    expected_resume_state: OrchestratorState | str | None = None,
) -> OrchestratorState:
    """Return the next state or raise a structured transition error.

    Dynamic targets are accepted only where the SPEC explicitly requires an
    exact continuation to be encoded by a disposition, gate, or persisted pause.
    """

    source = parse_state(current)
    parsed_event = parse_event(event)
    parsed_target = parse_state(target) if target is not None else None

    if parsed_event is StateEvent.FAIL_CLOSED:
        if source is OrchestratorState.ERROR_LOCKED:
            return source
        return OrchestratorState.ERROR_LOCKED

    fixed = _FIXED_TRANSITIONS.get((source, parsed_event))
    if fixed is not None:
        if parsed_target is not None and parsed_target is not fixed:
            raise StateTransitionError(
                "TARGET_MISMATCH", source.value, parsed_event.value, parsed_target.value, (fixed.value,)
            )
        return fixed

    availability_pause_targets = {
        StateEvent.PAUSE_RATE_LIMIT: OrchestratorState.PAUSED_RATE_LIMIT,
        StateEvent.PAUSE_MODEL_UNAVAILABLE: OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
        StateEvent.PAUSE_INFRASTRUCTURE: OrchestratorState.PAUSED_INFRASTRUCTURE,
    }
    if (
        source
        in {
            OrchestratorState.PM_PLANNING,
            OrchestratorState.EXECUTOR_RUNNING,
            OrchestratorState.PM_REVIEWING,
        }
        and parsed_event in availability_pause_targets
    ):
        paused = availability_pause_targets[parsed_event]
        if parsed_target is not None and parsed_target is not paused:
            raise StateTransitionError(
                "TARGET_MISMATCH",
                source.value,
                parsed_event.value,
                parsed_target.value,
                (paused.value,),
            )
        return paused

    if source is OrchestratorState.PM_REVIEWING and parsed_event is StateEvent.ACCEPT:
        allowed = (OrchestratorState.PM_PLANNING, OrchestratorState.DONE)
        if parsed_target not in allowed:
            raise StateTransitionError(
                "EXPLICIT_TARGET_REQUIRED",
                source.value,
                parsed_event.value,
                parsed_target.value if parsed_target else None,
                tuple(item.value for item in allowed),
            )
        return parsed_target

    if source is OrchestratorState.HUMAN_GATE_WAIT and parsed_event is StateEvent.GATE_APPROVE:
        if parsed_target not in GATE_CONTINUATION_STATES:
            raise StateTransitionError(
                "INVALID_GATE_CONTINUATION",
                source.value,
                parsed_event.value,
                parsed_target.value if parsed_target else None,
                tuple(sorted(item.value for item in GATE_CONTINUATION_STATES)),
            )
        return parsed_target

    if source is OrchestratorState.HUMAN_GATE_WAIT and parsed_event is StateEvent.GATE_DENY:
        allowed = {OrchestratorState.PM_PLANNING, OrchestratorState.DONE}
        if parsed_target not in allowed:
            raise StateTransitionError(
                "INVALID_GATE_DENIAL_CONTINUATION",
                source.value,
                parsed_event.value,
                parsed_target.value if parsed_target else None,
                tuple(sorted(item.value for item in allowed)),
            )
        return parsed_target

    if source in PAUSED_STATES and parsed_event is StateEvent.RECONCILE_RESUME:
        expected = parse_state(expected_resume_state) if expected_resume_state is not None else None
        if expected not in RECOVERABLE_STATES or parsed_target is not expected:
            allowed = (expected.value,) if expected in RECOVERABLE_STATES else ()
            raise StateTransitionError(
                "PAUSE_RECONCILIATION_MISMATCH",
                source.value,
                parsed_event.value,
                parsed_target.value if parsed_target else None,
                allowed,
            )
        return expected

    raise StateTransitionError(
        "INVALID_TRANSITION", source.value, parsed_event.value,
        parsed_target.value if parsed_target else None, ()
    )
