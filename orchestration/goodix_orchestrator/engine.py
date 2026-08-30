# SPDX-License-Identifier: GPL-2.0-or-later
"""Pure deterministic loop coordinator; contains no external adapters."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .persistence import (
    EffectStatus,
    PersistenceError,
    ReconciliationOutcome,
    RuntimeRecord,
    SQLiteStateStore,
)
from .policy import CapabilityPolicy
from .protocols import (
    Disposition,
    ExecutorResult,
    GateStatus,
    PMDisposition,
    PauseReason,
    TaskEnvelope,
    TaskManifest,
)
from .state import OrchestratorState, StateEvent, transition


@dataclass(frozen=True, slots=True)
class EngineError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    state: OrchestratorState
    engine: "DeterministicEngine | None"
    error_code: str | None = None
    detail: str | None = None


_ENGINE_CONSTRUCTION_TOKEN = object()


class DeterministicEngine:
    """Persist every state change and reject all implicit interpretations."""

    def __init__(
        self,
        store: SQLiteStateStore,
        policy: CapabilityPolicy,
        runtime: RuntimeRecord,
        *,
        _construction_token: object | None = None,
    ) -> None:
        if _construction_token is not _ENGINE_CONSTRUCTION_TOKEN:
            raise EngineError(
                "DIRECT_CONSTRUCTION_FORBIDDEN",
                "use create() for a fresh store or recover() for persisted state",
            )
        self.store = store
        self.policy = policy
        self.runtime = runtime

    @classmethod
    def create(
        cls,
        store: SQLiteStateStore,
        policy: CapabilityPolicy,
        *,
        run_id: str,
    ) -> "DeterministicEngine":
        store.initialize()
        if store.operational_record_count() != 0:
            raise EngineError(
                "EXISTING_STATE_REQUIRES_RECOVERY",
                "create() is fresh-only; use recover() for an existing store",
            )
        runtime = store.save_runtime(
            RuntimeRecord(current_state=OrchestratorState.BOOTSTRAP, run_id=run_id),
            expected_revision=None,
        )
        return cls(
            store,
            policy,
            runtime,
            _construction_token=_ENGINE_CONSTRUCTION_TOKEN,
        )

    @classmethod
    def recover(
        cls,
        path: str | Path,
        policy: CapabilityPolicy,
        *,
        expected_run_id: str | None = None,
    ) -> RecoveryResult:
        store = SQLiteStateStore(path)
        try:
            store.initialize()
            runtime = store.load_runtime()
            if runtime is None:
                raise EngineError("MISSING_RUNTIME_STATE", "initialized store has no runtime record")
            if expected_run_id is not None and runtime.run_id != expected_run_id:
                raise EngineError(
                    "RUN_ID_MISMATCH",
                    f"persisted {runtime.run_id}, expected {expected_run_id}",
                )
            engine = cls(
                store,
                policy,
                runtime,
                _construction_token=_ENGINE_CONSTRUCTION_TOKEN,
            )

            ambiguous = store.effects_with_statuses((EffectStatus.AMBIGUOUS,))
            in_progress = store.effects_with_statuses((EffectStatus.IN_PROGRESS,))
            unresolved = ambiguous or (
                in_progress if store.load_coordinator_state() is None else ()
            )
            if unresolved:
                engine._advance(StateEvent.FAIL_CLOSED)
                return RecoveryResult(
                    OrchestratorState.ERROR_LOCKED,
                    engine,
                    "AMBIGUOUS_SIDE_EFFECT",
                    ",".join(record.effect_id for record in unresolved),
                )

            if runtime.current_state is OrchestratorState.PM_REVIEWING:
                gates = store.pending_gates_for_task(runtime.task_id or "")
                if len(gates) > 1:
                    engine._advance(StateEvent.FAIL_CLOSED)
                    return RecoveryResult(
                        OrchestratorState.ERROR_LOCKED,
                        engine,
                        "AMBIGUOUS_PENDING_GATES",
                        ",".join(gate.gate_id for gate in gates),
                    )
                if len(gates) == 1:
                    engine._advance(StateEvent.HUMAN_GATE, gate_id=gates[0].gate_id)

            if engine.runtime.current_state is OrchestratorState.HUMAN_GATE_WAIT:
                gate = store.load_gate(engine.runtime.gate_id or "")
                if gate is None:
                    engine._advance(StateEvent.FAIL_CLOSED)
                    return RecoveryResult(
                        OrchestratorState.ERROR_LOCKED,
                        engine,
                        "MISSING_GATE",
                        engine.runtime.gate_id,
                    )
                if gate.status is not GateStatus.PENDING:
                    approved = gate.status is GateStatus.APPROVED
                    engine._advance(
                        StateEvent.GATE_APPROVE if approved else StateEvent.GATE_DENY,
                        target=gate.approval_state if approved else gate.denial_state,
                        gate_id=None,
                    )

            return RecoveryResult(engine.runtime.current_state, engine)
        except (PersistenceError, EngineError) as exc:
            return RecoveryResult(
                OrchestratorState.ERROR_LOCKED,
                None,
                getattr(exc, "code", "RECOVERY_ERROR"),
                str(exc),
            )

    @property
    def state(self) -> OrchestratorState:
        return self.runtime.current_state

    def _save(self, record: RuntimeRecord) -> OrchestratorState:
        self.runtime = self.store.save_runtime(
            record, expected_revision=self.runtime.revision
        )
        return self.runtime.current_state

    def _advance(
        self,
        event: StateEvent,
        *,
        target: OrchestratorState | None = None,
        expected_resume_state: OrchestratorState | None = None,
        **changes: object,
    ) -> OrchestratorState:
        source = self.runtime.current_state
        next_state = transition(
            source,
            event,
            target=target,
            expected_resume_state=expected_resume_state,
        )
        if next_state in {
            OrchestratorState.PAUSED_RATE_LIMIT,
            OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
            OrchestratorState.PAUSED_INFRASTRUCTURE,
        }:
            changes["previous_recoverable_state"] = source
        elif "previous_recoverable_state" not in changes:
            changes["previous_recoverable_state"] = None
        if (
            next_state is not OrchestratorState.HUMAN_GATE_WAIT
            and "gate_id" not in changes
        ):
            changes["gate_id"] = None
        return self._save(replace(self.runtime, current_state=next_state, **changes))

    def fail_closed(self, code: str, detail: str) -> None:
        self._advance(StateEvent.FAIL_CLOSED)
        raise EngineError(code, detail)

    def bootstrap_complete(self) -> OrchestratorState:
        return self._advance(StateEvent.BOOTSTRAP_COMPLETE)

    def start_planning(self) -> OrchestratorState:
        return self._advance(StateEvent.START_PLANNING)

    def task_ready(self, manifest: TaskManifest) -> OrchestratorState:
        if self.runtime.baseline_sha is not None and manifest.baseline_sha != self.runtime.baseline_sha:
            self.fail_closed(
                "BASELINE_MISMATCH",
                f"persisted {self.runtime.baseline_sha}, manifest {manifest.baseline_sha}",
            )
        if (
            self.runtime.expected_next_task_id is not None
            and manifest.task_id != self.runtime.expected_next_task_id
        ):
            self.fail_closed(
                "EXPECTED_NEXT_TASK_MISMATCH",
                f"expected {self.runtime.expected_next_task_id}, manifest {manifest.task_id}",
            )
        proposed_envelope = TaskEnvelope.from_manifest(manifest)
        if (
            self.runtime.task_envelope is not None
            and proposed_envelope != self.runtime.task_envelope
        ):
            self.fail_closed(
                "TASK_ENVELOPE_MISMATCH",
                "replanned manifest changed the immutable delegated envelope",
            )
        self.policy.require(manifest.capabilities_required)
        return self._advance(
            StateEvent.TASK_PREPARED,
            task_id=manifest.task_id,
            baseline_sha=manifest.baseline_sha,
            result_sha=None,
            expected_next_task_id=None,
            task_envelope=proposed_envelope,
            gate_id=None,
        )

    def start_executor(self, *, turn_id: str) -> OrchestratorState:
        if not isinstance(turn_id, str) or not turn_id.strip():
            raise EngineError("INVALID_TURN_ID", repr(turn_id))
        return self._advance(
            StateEvent.EXECUTOR_STARTED, turn_id=turn_id, result_sha=None
        )

    def complete_executor(self, result: ExecutorResult) -> OrchestratorState:
        if result.task_id != self.runtime.task_id:
            self.fail_closed(
                "TASK_ID_MISMATCH",
                f"persisted {self.runtime.task_id}, result {result.task_id}",
            )
        if result.review_set.baseline_sha != self.runtime.baseline_sha:
            self.fail_closed(
                "RESULT_BASELINE_MISMATCH",
                f"persisted {self.runtime.baseline_sha}, result {result.review_set.baseline_sha}",
            )
        assertions = result.policy_assertions
        violations: list[str] = []
        if assertions.usb_open_count != 0:
            violations.append(f"usb_open_count={assertions.usb_open_count}")
        if assertions.sudo_used:
            violations.append("sudo_used=true")
        if assertions.protected_material_accessed:
            violations.append("protected_material_accessed=true")
        if assertions.main_modified:
            violations.append("main_modified=true")
        if violations:
            self.fail_closed(
                "EXECUTOR_POLICY_ASSERTION_VIOLATION", ",".join(violations)
            )
        return self._advance(
            StateEvent.EXECUTOR_COMPLETED,
            result_sha=result.review_set.head_sha,
        )

    def start_review(self, *, turn_id: str) -> OrchestratorState:
        if not isinstance(turn_id, str) or not turn_id.strip():
            raise EngineError("INVALID_TURN_ID", repr(turn_id))
        return self._advance(StateEvent.REVIEW_STARTED, turn_id=turn_id)

    def apply_disposition(self, disposition: PMDisposition) -> OrchestratorState:
        if disposition.task_id != self.runtime.task_id:
            self.fail_closed(
                "TASK_ID_MISMATCH",
                f"persisted {self.runtime.task_id}, disposition {disposition.task_id}",
            )

        primary = disposition.disposition
        if primary is Disposition.ACCEPT:
            if disposition.reviewed_head_sha != self.runtime.result_sha:
                self.fail_closed(
                    "REVIEWED_HEAD_MISMATCH",
                    f"persisted {self.runtime.result_sha}, reviewed {disposition.reviewed_head_sha}",
                )
            return self._advance(
                StateEvent.ACCEPT,
                target=disposition.accept_target,
                baseline_sha=self.runtime.result_sha,
                expected_next_task_id=disposition.next_task_id,
                task_envelope=None,
            )
        if primary is Disposition.CORRECTIVE:
            return self._advance(StateEvent.CORRECTIVE)
        if primary is Disposition.REPLAN:
            return self._advance(StateEvent.REPLAN)
        if primary is Disposition.HUMAN_GATE:
            assert disposition.gate is not None
            self.store.record_gate(disposition.gate)
            return self._advance(StateEvent.HUMAN_GATE, gate_id=disposition.gate.gate_id)
        if primary is Disposition.PAUSE:
            pause_event = {
                PauseReason.RATE_LIMIT: StateEvent.PAUSE_RATE_LIMIT,
                PauseReason.MODEL_UNAVAILABLE: StateEvent.PAUSE_MODEL_UNAVAILABLE,
                PauseReason.INFRASTRUCTURE: StateEvent.PAUSE_INFRASTRUCTURE,
            }[disposition.pause_reason]
            return self._advance(pause_event)
        if primary is Disposition.DONE:
            return self._advance(
                StateEvent.DONE,
                expected_next_task_id=None,
                task_envelope=None,
            )
        self.fail_closed("UNKNOWN_DISPOSITION", repr(primary))

    def pause(self, reason: PauseReason) -> OrchestratorState:
        pause_event = {
            PauseReason.RATE_LIMIT: StateEvent.PAUSE_RATE_LIMIT,
            PauseReason.MODEL_UNAVAILABLE: StateEvent.PAUSE_MODEL_UNAVAILABLE,
            PauseReason.INFRASTRUCTURE: StateEvent.PAUSE_INFRASTRUCTURE,
        }[reason]
        return self._advance(pause_event)

    def resolve_gate(self, *, gate_id: str, approve: bool) -> OrchestratorState:
        if self.runtime.current_state is not OrchestratorState.HUMAN_GATE_WAIT:
            raise EngineError("NO_PENDING_GATE_STATE", self.runtime.current_state.value)
        if gate_id != self.runtime.gate_id:
            self.fail_closed(
                "GATE_ID_MISMATCH",
                f"persisted {self.runtime.gate_id}, decision {gate_id}",
            )
        pending = self.store.load_gate(gate_id)
        if pending is None:
            self.fail_closed("MISSING_GATE", gate_id)
        decision = GateStatus.APPROVED if approve else GateStatus.DENIED
        terminal = self.store.decide_gate(gate_id, decision)
        target = terminal.approval_state if approve else terminal.denial_state
        event = StateEvent.GATE_APPROVE if approve else StateEvent.GATE_DENY
        return self._advance(event, target=target, gate_id=None)

    def resume_pause(self) -> OrchestratorState:
        previous = self.runtime.previous_recoverable_state
        if previous is None:
            self.fail_closed("MISSING_RECOVERABLE_STATE", self.runtime.current_state.value)
        return self._advance(
            StateEvent.RECONCILE_RESUME,
            target=previous,
            expected_resume_state=previous,
        )

    def reconcile_effect(
        self, effect_id: str, outcome: ReconciliationOutcome
    ) -> None:
        record = self.store.reconcile_effect(effect_id, outcome)
        if record.status.value == "AMBIGUOUS":
            self.fail_closed(
                "AMBIGUOUS_SIDE_EFFECT",
                f"external outcome unknown for {effect_id}",
            )
