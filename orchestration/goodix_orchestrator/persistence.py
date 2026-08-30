# SPDX-License-Identifier: GPL-2.0-or-later
"""Single-file SQLite persistence and typed idempotency ledger for O001."""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator

from .policy import ProtectedBranchError, require_ordinary_branch

from .protocols import (
    GateStatus,
    HumanGateManifest,
    PROTOCOL_VERSION,
    ProtocolValidationError,
    TaskEnvelope,
)
from .state import OrchestratorState, PAUSED_STATES
from .structured_output import ContextClass, RoutingClass


SCHEMA_VERSION = 5
_RUN_ID_RE = re.compile(r"^ORCH-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_TASK_ID_RE = re.compile(r"^TASK-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_TURN_ID_RE = re.compile(r"^TURN-[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_GATE_ID_RE = re.compile(r"^HG-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REF_FORBIDDEN_RE = re.compile(r"[\s~^:?*\[\\]")


class PersistenceError(Exception):
    code = "PERSISTENCE_ERROR"


class StoreCorruptionError(PersistenceError):
    code = "STORE_CORRUPT"


class StoreIncompatibleError(PersistenceError):
    code = "STORE_INCOMPATIBLE"


class ConcurrentStateError(PersistenceError):
    code = "CONCURRENT_STATE_UPDATE"


class IdempotencyIntentMismatchError(PersistenceError):
    code = "IDEMPOTENCY_INTENT_MISMATCH"


class AmbiguousEffectError(PersistenceError):
    code = "AMBIGUOUS_EFFECT"


class GateReplayError(PersistenceError):
    code = "TERMINAL_GATE_REPLAY"


class UnsafePersistenceDataError(PersistenceError):
    code = "UNSAFE_PERSISTENCE_DATA"


class EffectKind(StrEnum):
    BRANCH_CREATE = "BRANCH_CREATE"
    COMMIT = "COMMIT"
    PUSH = "PUSH"
    INTEGRATION_FF = "INTEGRATION_FF"
    GATE_CREATE = "GATE_CREATE"
    GATE_DECISION_CONSUME = "GATE_DECISION_CONSUME"
    DEVELOPMENT_INIT = "DEVELOPMENT_INIT"
    TASK_WORKTREE_REMOVE = "TASK_WORKTREE_REMOVE"
    TASK_LOCAL_BRANCH_DELETE = "TASK_LOCAL_BRANCH_DELETE"
    TASK_REMOTE_BRANCH_DELETE = "TASK_REMOTE_BRANCH_DELETE"
    STATE_BACKUP = "STATE_BACKUP"


class EffectStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    AMBIGUOUS = "AMBIGUOUS"


class EffectRequestAction(StrEnum):
    EXECUTE = "EXECUTE"
    SKIP_COMPLETED = "SKIP_COMPLETED"


class ReconciliationOutcome(StrEnum):
    NO_EFFECT = "NO_EFFECT"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"


class TurnActivityStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class RuntimeRecord:
    current_state: OrchestratorState
    run_id: str
    previous_recoverable_state: OrchestratorState | None = None
    task_id: str | None = None
    turn_id: str | None = None
    gate_id: str | None = None
    baseline_sha: str | None = None
    result_sha: str | None = None
    expected_next_task_id: str | None = None
    task_envelope: TaskEnvelope | None = None
    protocol_version: str = PROTOCOL_VERSION
    revision: int = 0

    def __post_init__(self) -> None:
        try:
            state = self.current_state if isinstance(self.current_state, OrchestratorState) else OrchestratorState(self.current_state)
            previous = (
                self.previous_recoverable_state
                if isinstance(self.previous_recoverable_state, OrchestratorState)
                else OrchestratorState(self.previous_recoverable_state)
                if self.previous_recoverable_state is not None
                else None
            )
        except (TypeError, ValueError) as exc:
            raise StoreCorruptionError(f"unknown persisted state: {exc}") from exc
        if not isinstance(self.run_id, str) or _RUN_ID_RE.fullmatch(self.run_id) is None:
            raise StoreCorruptionError(f"invalid RUN_ID: {self.run_id!r}")
        if self.protocol_version != PROTOCOL_VERSION:
            raise StoreIncompatibleError(f"runtime protocol version {self.protocol_version!r}")
        if not isinstance(self.revision, int) or self.revision < 0:
            raise StoreCorruptionError(f"invalid revision: {self.revision!r}")
        for field_name, pattern in (
            ("task_id", _TASK_ID_RE),
            ("expected_next_task_id", _TASK_ID_RE),
            ("turn_id", _TURN_ID_RE),
            ("gate_id", _GATE_ID_RE),
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or pattern.fullmatch(value) is None
            ):
                raise StoreCorruptionError(f"invalid {field_name}: {value!r}")
        for field_name in ("baseline_sha", "result_sha"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or _SHA_RE.fullmatch(value) is None):
                raise StoreCorruptionError(f"invalid {field_name}: {value!r}")
        if state in PAUSED_STATES and previous is None:
            raise StoreCorruptionError("paused state is missing previous recoverable state")
        if state not in PAUSED_STATES and previous is not None:
            raise StoreCorruptionError("non-paused state unexpectedly has previous recoverable state")
        if state is OrchestratorState.HUMAN_GATE_WAIT and self.gate_id is None:
            raise StoreCorruptionError("HUMAN_GATE_WAIT is missing GATE_ID")
        if state is not OrchestratorState.HUMAN_GATE_WAIT and self.gate_id is not None:
            raise StoreCorruptionError("GATE_ID is present outside HUMAN_GATE_WAIT")
        if self.expected_next_task_id is not None:
            if state not in {
                OrchestratorState.PM_PLANNING,
                OrchestratorState.ERROR_LOCKED,
            }:
                raise StoreCorruptionError(
                    "expected next TASK_ID exists outside PM_PLANNING/ERROR_LOCKED"
                )
            if self.task_envelope is not None:
                raise StoreCorruptionError(
                    "expected next TASK_ID conflicts with retained task envelope"
                )
        if self.task_envelope is not None:
            if not isinstance(self.task_envelope, TaskEnvelope):
                raise StoreCorruptionError("invalid task envelope object")
            if self.task_envelope.task_id != self.task_id:
                raise StoreCorruptionError("task envelope TASK_ID mismatch")
        if state is OrchestratorState.DONE and self.expected_next_task_id is not None:
            raise StoreCorruptionError("DONE retains an expected next TASK_ID")
        object.__setattr__(self, "current_state", state)
        object.__setattr__(self, "previous_recoverable_state", previous)


@dataclass(frozen=True, slots=True)
class ContextRecord:
    thread_id: str
    context_class: ContextClass
    role: str
    effective_model_id: str
    effective_reasoning_effort: str
    routing_class: RoutingClass
    cwd: str
    codex_version: str
    active: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "thread_id",
            "role",
            "effective_model_id",
            "effective_reasoning_effort",
            "cwd",
            "codex_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or len(value) > 1024:
                raise UnsafePersistenceDataError(f"invalid {field_name}: {value!r}")
        try:
            context = (
                self.context_class
                if isinstance(self.context_class, ContextClass)
                else ContextClass(self.context_class)
            )
            routing = (
                self.routing_class
                if isinstance(self.routing_class, RoutingClass)
                else RoutingClass(self.routing_class)
            )
        except (TypeError, ValueError) as exc:
            raise UnsafePersistenceDataError(f"invalid context routing: {exc}") from exc
        if not isinstance(self.active, bool):
            raise UnsafePersistenceDataError(f"invalid active flag: {self.active!r}")
        object.__setattr__(self, "context_class", context)
        object.__setattr__(self, "routing_class", routing)


@dataclass(frozen=True, slots=True)
class DispatchRecord:
    dispatch_id: str
    thread_id: str
    turn_id: str
    context_class: ContextClass
    routing_class: RoutingClass
    effective_model_id: str
    effective_reasoning_effort: str
    codex_version: str
    schema_repair: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "dispatch_id",
            "thread_id",
            "turn_id",
            "effective_model_id",
            "effective_reasoning_effort",
            "codex_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or len(value) > 1024:
                raise UnsafePersistenceDataError(f"invalid {field_name}: {value!r}")
        try:
            object.__setattr__(
                self,
                "context_class",
                self.context_class
                if isinstance(self.context_class, ContextClass)
                else ContextClass(self.context_class),
            )
            object.__setattr__(
                self,
                "routing_class",
                self.routing_class
                if isinstance(self.routing_class, RoutingClass)
                else RoutingClass(self.routing_class),
            )
        except (TypeError, ValueError) as exc:
            raise UnsafePersistenceDataError(f"invalid dispatch routing: {exc}") from exc
        if not isinstance(self.schema_repair, bool):
            raise UnsafePersistenceDataError(
                f"invalid schema_repair flag: {self.schema_repair!r}"
            )


@dataclass(frozen=True, slots=True)
class TurnActivityRecord:
    activity_id: str
    dispatch_id: str
    thread_id: str
    context_class: ContextClass
    routing_class: RoutingClass
    requested_model_id: str
    requested_reasoning_effort: str
    status: TurnActivityStatus
    turn_id: str | None = None
    error_class: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "activity_id",
            "dispatch_id",
            "thread_id",
            "requested_model_id",
            "requested_reasoning_effort",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 1024:
                raise UnsafePersistenceDataError(f"invalid turn activity {name}: {value!r}")
        try:
            object.__setattr__(
                self,
                "context_class",
                self.context_class
                if isinstance(self.context_class, ContextClass)
                else ContextClass(self.context_class),
            )
            object.__setattr__(
                self,
                "routing_class",
                self.routing_class
                if isinstance(self.routing_class, RoutingClass)
                else RoutingClass(self.routing_class),
            )
            object.__setattr__(
                self,
                "status",
                self.status
                if isinstance(self.status, TurnActivityStatus)
                else TurnActivityStatus(self.status),
            )
        except (TypeError, ValueError) as exc:
            raise UnsafePersistenceDataError(f"invalid turn activity enum: {exc}") from exc
        for name in ("turn_id", "error_class"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not value.strip() or len(value) > 1024
            ):
                raise UnsafePersistenceDataError(f"invalid turn activity {name}: {value!r}")
        if self.status is TurnActivityStatus.COMPLETED and self.turn_id is None:
            raise UnsafePersistenceDataError("completed turn activity lacks turn_id")


@dataclass(frozen=True, slots=True)
class GitStateRecord:
    integration_branch: str
    integration_sha: str
    task_worktree: str | None = None
    main_sha: str | None = None
    task_id: str | None = None
    task_branch: str | None = None
    reviewed_head_sha: str | None = None
    integration_verified: bool = False
    cleanup_status: str = "NOT_STARTED"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "integration_branch",
            _validated_ref(self.integration_branch, target=True),
        )
        object.__setattr__(self, "integration_sha", _validated_sha(self.integration_sha))
        if self.task_worktree is not None and (
            not isinstance(self.task_worktree, str)
            or not self.task_worktree.strip()
            or len(self.task_worktree) > 4096
        ):
            raise UnsafePersistenceDataError(
                f"invalid task_worktree: {self.task_worktree!r}"
            )
        object.__setattr__(self, "main_sha", _validated_sha(self.main_sha, optional=True))
        object.__setattr__(
            self, "reviewed_head_sha", _validated_sha(self.reviewed_head_sha, optional=True)
        )
        if self.task_id is not None:
            object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        if self.task_branch is not None:
            object.__setattr__(self, "task_branch", _validated_ref(self.task_branch, target=True))
        if (self.task_id is None) != (self.task_branch is None):
            raise UnsafePersistenceDataError("task_id/task_branch must be present together")
        if not isinstance(self.integration_verified, bool):
            raise UnsafePersistenceDataError("invalid integration_verified")
        if self.cleanup_status not in {
            "NOT_STARTED",
            "IN_PROGRESS",
            "PASS",
            "PRESERVED",
        }:
            raise UnsafePersistenceDataError(f"invalid cleanup_status: {self.cleanup_status!r}")


@dataclass(frozen=True, slots=True)
class GateExternalRecord:
    gate_id: str
    task_id: str
    repository: str
    issue_number: int
    issue_node_id: str
    issue_body_digest: str
    action_id: str
    action_digest: str
    commit_sha: str | None
    authorized_user_id: int
    authorized_login: str
    decision_comment_id: int | None = None
    decision_author_id: int | None = None
    decision: GateStatus = GateStatus.PENDING

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", _validated_gate_id(self.gate_id))
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise UnsafePersistenceDataError(f"invalid repository: {self.repository!r}")
        if not isinstance(self.issue_number, int) or self.issue_number <= 0:
            raise UnsafePersistenceDataError(f"invalid issue_number: {self.issue_number!r}")
        for name in (
            "issue_node_id",
            "action_id",
            "authorized_login",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise UnsafePersistenceDataError(f"invalid {name}: {value!r}")
        for name in ("issue_body_digest", "action_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise UnsafePersistenceDataError(f"invalid {name}: {value!r}")
        object.__setattr__(self, "commit_sha", _validated_sha(self.commit_sha, optional=True))
        if not isinstance(self.authorized_user_id, int) or self.authorized_user_id <= 0:
            raise UnsafePersistenceDataError(
                f"invalid authorized_user_id: {self.authorized_user_id!r}"
            )
        for name in ("decision_comment_id", "decision_author_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value <= 0):
                raise UnsafePersistenceDataError(f"invalid {name}: {value!r}")
        try:
            decision = self.decision if isinstance(self.decision, GateStatus) else GateStatus(self.decision)
        except (TypeError, ValueError) as exc:
            raise UnsafePersistenceDataError(f"invalid decision: {self.decision!r}") from exc
        if decision is GateStatus.PENDING and any(
            value is not None for value in (self.decision_comment_id, self.decision_author_id)
        ):
            raise UnsafePersistenceDataError("pending gate has terminal decision provenance")
        if decision is not GateStatus.PENDING and (
            self.decision_comment_id is None or self.decision_author_id is None
        ):
            raise UnsafePersistenceDataError("terminal gate lacks decision provenance")
        object.__setattr__(self, "decision", decision)


@dataclass(frozen=True, slots=True)
class OperatorStateRecord:
    operator_paused: bool = False
    emergency_stop_latched: bool = False
    maintenance_id: str | None = None
    last_event: str = "UNINITIALIZED"
    last_error_class: str | None = None
    reprobe_due_at: str | None = None
    availability_class: str = "UNKNOWN"

    def __post_init__(self) -> None:
        for name in ("operator_paused", "emergency_stop_latched"):
            if not isinstance(getattr(self, name), bool):
                raise UnsafePersistenceDataError(f"invalid {name}")
        if self.maintenance_id is not None and re.fullmatch(
            r"MAINT-[A-Za-z0-9][A-Za-z0-9._-]{0,119}", self.maintenance_id
        ) is None:
            raise UnsafePersistenceDataError(f"invalid maintenance_id: {self.maintenance_id!r}")
        for name in ("last_event", "availability_class"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise UnsafePersistenceDataError(f"invalid {name}: {value!r}")
        for name in ("last_error_class", "reprobe_due_at"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or len(value) > 256):
                raise UnsafePersistenceDataError(f"invalid {name}: {value!r}")


@dataclass(frozen=True, slots=True)
class MaintenanceEpochRecord:
    maintenance_id: str
    entered_at: str
    main_sha: str
    development_sha: str | None
    task_id: str | None
    task_branch: str | None
    orchestrator_state: str
    integration_baseline: str | None
    exited_at: str | None = None
    reconciliation: str | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"MAINT-[A-Za-z0-9][A-Za-z0-9._-]{0,119}", self.maintenance_id) is None:
            raise UnsafePersistenceDataError(f"invalid maintenance_id: {self.maintenance_id!r}")
        object.__setattr__(self, "main_sha", _validated_sha(self.main_sha))
        object.__setattr__(self, "development_sha", _validated_sha(self.development_sha, optional=True))
        object.__setattr__(self, "integration_baseline", _validated_sha(self.integration_baseline, optional=True))
        if self.task_id is not None:
            object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        if self.task_branch is not None:
            object.__setattr__(self, "task_branch", _validated_ref(self.task_branch, target=True))
        for name in ("entered_at", "orchestrator_state"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise UnsafePersistenceDataError(f"invalid {name}: {value!r}")
        for name in ("exited_at", "reconciliation"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or len(value) > 512):
                raise UnsafePersistenceDataError(f"invalid {name}: {value!r}")


@dataclass(frozen=True, slots=True)
class _EffectIntentMixin:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validated_task_id(value: str) -> str:
    if not isinstance(value, str) or _TASK_ID_RE.fullmatch(value) is None:
        raise UnsafePersistenceDataError(f"invalid task_id: {value!r}")
    return value


def _validated_gate_id(value: str) -> str:
    if not isinstance(value, str) or _GATE_ID_RE.fullmatch(value) is None:
        raise UnsafePersistenceDataError(f"invalid gate_id: {value!r}")
    return value


def _validated_sha(value: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise UnsafePersistenceDataError(f"invalid SHA: {value!r}")
    return value


def _validated_ref(value: str, *, target: bool) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or value.endswith("/")
        or value.endswith(".")
        or ".." in value
        or "//" in value
        or "@{" in value
        or _REF_FORBIDDEN_RE.search(value)
    ):
        raise UnsafePersistenceDataError(f"invalid ref: {value!r}")
    if target:
        try:
            require_ordinary_branch(value)
        except ProtectedBranchError as exc:
            raise UnsafePersistenceDataError(str(exc)) from exc
    return value


@dataclass(frozen=True, slots=True)
class BranchCreateIntent(_EffectIntentMixin):
    task_id: str
    branch: str
    source_ref: str
    baseline_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "branch", _validated_ref(self.branch, target=True))
        object.__setattr__(self, "source_ref", _validated_ref(self.source_ref, target=False))
        object.__setattr__(self, "baseline_sha", _validated_sha(self.baseline_sha))


@dataclass(frozen=True, slots=True)
class CommitIntent(_EffectIntentMixin):
    task_id: str
    branch: str
    baseline_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "branch", _validated_ref(self.branch, target=True))
        object.__setattr__(self, "baseline_sha", _validated_sha(self.baseline_sha))


@dataclass(frozen=True, slots=True)
class PushIntent(_EffectIntentMixin):
    task_id: str
    branch: str
    commit_sha: str
    expected_remote_sha: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "branch", _validated_ref(self.branch, target=True))
        object.__setattr__(self, "commit_sha", _validated_sha(self.commit_sha))
        object.__setattr__(
            self,
            "expected_remote_sha",
            _validated_sha(self.expected_remote_sha, optional=True),
        )


@dataclass(frozen=True, slots=True)
class IntegrationFFIntent(_EffectIntentMixin):
    task_id: str
    source_ref: str
    target_ref: str
    baseline_sha: str
    commit_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "source_ref", _validated_ref(self.source_ref, target=False))
        object.__setattr__(self, "target_ref", _validated_ref(self.target_ref, target=True))
        object.__setattr__(self, "baseline_sha", _validated_sha(self.baseline_sha))
        object.__setattr__(self, "commit_sha", _validated_sha(self.commit_sha))


@dataclass(frozen=True, slots=True)
class GateCreateIntent(_EffectIntentMixin):
    task_id: str
    gate_id: str
    commit_sha: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "gate_id", _validated_gate_id(self.gate_id))
        object.__setattr__(
            self, "commit_sha", _validated_sha(self.commit_sha, optional=True)
        )


@dataclass(frozen=True, slots=True)
class GateDecisionIntent(_EffectIntentMixin):
    task_id: str
    gate_id: str
    decision: str
    comment_id: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "gate_id", _validated_gate_id(self.gate_id))
        if self.decision not in {GateStatus.APPROVED.value, GateStatus.DENIED.value}:
            raise UnsafePersistenceDataError(f"invalid gate decision: {self.decision!r}")
        if not isinstance(self.comment_id, int) or self.comment_id <= 0:
            raise UnsafePersistenceDataError(f"invalid comment_id: {self.comment_id!r}")


@dataclass(frozen=True, slots=True)
class DevelopmentInitIntent(_EffectIntentMixin):
    commit_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "commit_sha", _validated_sha(self.commit_sha))


@dataclass(frozen=True, slots=True)
class TaskCleanupIntent(_EffectIntentMixin):
    task_id: str
    branch: str
    accepted_sha: str
    integration_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "branch", _validated_ref(self.branch, target=True))
        if not self.branch.startswith("task/"):
            raise UnsafePersistenceDataError(f"cleanup branch outside task namespace: {self.branch!r}")
        object.__setattr__(self, "accepted_sha", _validated_sha(self.accepted_sha))
        object.__setattr__(self, "integration_sha", _validated_sha(self.integration_sha))


@dataclass(frozen=True, slots=True)
class StateBackupIntent(_EffectIntentMixin):
    run_id: str
    source_revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or _RUN_ID_RE.fullmatch(self.run_id) is None:
            raise UnsafePersistenceDataError(f"invalid run_id: {self.run_id!r}")
        if not isinstance(self.source_revision, int) or self.source_revision < 0:
            raise UnsafePersistenceDataError(
                f"invalid source_revision: {self.source_revision!r}"
            )


EffectIntent = (
    BranchCreateIntent
    | CommitIntent
    | PushIntent
    | IntegrationFFIntent
    | GateCreateIntent
    | GateDecisionIntent
    | DevelopmentInitIntent
    | TaskCleanupIntent
    | StateBackupIntent
)

_EFFECT_INTENT_TYPES: dict[EffectKind, type[_EffectIntentMixin]] = {
    EffectKind.BRANCH_CREATE: BranchCreateIntent,
    EffectKind.COMMIT: CommitIntent,
    EffectKind.PUSH: PushIntent,
    EffectKind.INTEGRATION_FF: IntegrationFFIntent,
    EffectKind.GATE_CREATE: GateCreateIntent,
    EffectKind.GATE_DECISION_CONSUME: GateDecisionIntent,
    EffectKind.DEVELOPMENT_INIT: DevelopmentInitIntent,
    EffectKind.TASK_WORKTREE_REMOVE: TaskCleanupIntent,
    EffectKind.TASK_LOCAL_BRANCH_DELETE: TaskCleanupIntent,
    EffectKind.TASK_REMOTE_BRANCH_DELETE: TaskCleanupIntent,
    EffectKind.STATE_BACKUP: StateBackupIntent,
}


@dataclass(frozen=True, slots=True)
class EffectRecord:
    effect_id: str
    idempotency_key: str
    kind: EffectKind
    status: EffectStatus
    intent: EffectIntent


@dataclass(frozen=True, slots=True)
class EffectRequest:
    action: EffectRequestAction
    record: EffectRecord


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class SQLiteStateStore:
    """Inspectable transactional store; never replaces incompatible data."""

    _REQUIRED_TABLES = frozenset(
        {
            "metadata",
            "runtime_state",
            "effects",
            "gates",
            "contexts",
            "dispatches",
            "turn_activity",
            "coordinator_state",
            "git_state",
            "gate_external",
            "operator_state",
            "maintenance_epochs",
        }
    )

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                if not tables:
                    self._create_schema(connection)
                elif "metadata" in tables:
                    # Version mismatch is incompatibility, not corruption. Check it
                    # before comparing the richer v5 table set so legacy files stay
                    # byte-for-byte untouched and receive the correct classification.
                    schema_version = self._read_schema_version(connection)
                    if schema_version != SCHEMA_VERSION:
                        raise StoreIncompatibleError(
                            f"schema version {schema_version}, expected {SCHEMA_VERSION}"
                        )
                if tables and tables != self._REQUIRED_TABLES:
                    raise StoreCorruptionError(
                        f"unexpected schema tables: expected {sorted(self._REQUIRED_TABLES)}, got {sorted(tables)}"
                    )
                self._validate_schema(connection)
                for row in connection.execute("SELECT * FROM effects"):
                    self._effect_from_row(row)
                connection.commit()
        except (StoreCorruptionError, StoreIncompatibleError):
            raise
        except sqlite3.DatabaseError as exc:
            raise StoreCorruptionError(str(exc)) from exc

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        statements = (
            """CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""",
            """CREATE TABLE runtime_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                current_state TEXT NOT NULL,
                previous_recoverable_state TEXT,
                run_id TEXT NOT NULL,
                task_id TEXT,
                turn_id TEXT,
                gate_id TEXT,
                baseline_sha TEXT,
                result_sha TEXT,
                expected_next_task_id TEXT,
                task_envelope_json TEXT,
                protocol_version TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision >= 0)
            )""",
            """CREATE TABLE effects (
                effect_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                intent_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE gates (
                gate_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE contexts (
                thread_id TEXT PRIMARY KEY,
                context_class TEXT NOT NULL,
                role TEXT NOT NULL,
                effective_model_id TEXT NOT NULL,
                effective_reasoning_effort TEXT NOT NULL,
                routing_class TEXT NOT NULL,
                cwd TEXT NOT NULL,
                codex_version TEXT NOT NULL,
                active INTEGER NOT NULL CHECK (active IN (0, 1)),
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE dispatches (
                dispatch_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                context_class TEXT NOT NULL,
                routing_class TEXT NOT NULL,
                effective_model_id TEXT NOT NULL,
                effective_reasoning_effort TEXT NOT NULL,
                codex_version TEXT NOT NULL,
                schema_repair INTEGER NOT NULL CHECK (schema_repair IN (0, 1)),
                created_at TEXT NOT NULL,
                FOREIGN KEY(thread_id) REFERENCES contexts(thread_id)
            )""",
            """CREATE TABLE turn_activity (
                activity_id TEXT PRIMARY KEY,
                dispatch_id TEXT NOT NULL UNIQUE,
                thread_id TEXT NOT NULL,
                context_class TEXT NOT NULL,
                routing_class TEXT NOT NULL,
                requested_model_id TEXT NOT NULL,
                requested_reasoning_effort TEXT NOT NULL,
                status TEXT NOT NULL,
                turn_id TEXT,
                error_class TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(thread_id) REFERENCES contexts(thread_id)
            )""",
            """CREATE TABLE coordinator_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                record_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE git_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                integration_branch TEXT NOT NULL,
                integration_sha TEXT NOT NULL,
                task_worktree TEXT,
                main_sha TEXT,
                task_id TEXT,
                task_branch TEXT,
                reviewed_head_sha TEXT,
                integration_verified INTEGER NOT NULL CHECK (integration_verified IN (0, 1)),
                cleanup_status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE gate_external (
                gate_id TEXT PRIMARY KEY,
                record_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE operator_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                record_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE maintenance_epochs (
                maintenance_id TEXT PRIMARY KEY,
                record_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
        )
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('protocol_version', ?)",
            (PROTOCOL_VERSION,),
        )

    @staticmethod
    def _read_schema_version(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        try:
            return int(row[0])
        except (TypeError, ValueError, IndexError) as exc:
            raise StoreCorruptionError("missing or malformed schema_version") from exc

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        schema_version = self._read_schema_version(connection)
        if schema_version != SCHEMA_VERSION:
            raise StoreIncompatibleError(
                f"schema version {schema_version}, expected {SCHEMA_VERSION}"
            )
        if metadata.get("protocol_version") != PROTOCOL_VERSION:
            raise StoreIncompatibleError(
                f"protocol version {metadata.get('protocol_version')!r}, expected {PROTOCOL_VERSION}"
            )

    @contextmanager
    def _checked_connection(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            try:
                self._validate_schema(connection)
                yield connection
            except PersistenceError:
                raise
            except sqlite3.DatabaseError as exc:
                raise StoreCorruptionError(str(exc)) from exc

    def load_runtime(self) -> RuntimeRecord | None:
        try:
            with self._checked_connection() as connection:
                row = connection.execute("SELECT * FROM runtime_state WHERE singleton = 1").fetchone()
        except (PersistenceError, sqlite3.DatabaseError) as exc:
            if isinstance(exc, PersistenceError):
                raise
            raise StoreCorruptionError(str(exc)) from exc
        if row is None:
            return None
        envelope = None
        if row["task_envelope_json"] is not None:
            try:
                payload = json.loads(row["task_envelope_json"])
                if not isinstance(payload, dict):
                    raise TypeError("task envelope is not an object")
                envelope = TaskEnvelope.from_dict(payload)
            except (
                json.JSONDecodeError,
                ProtocolValidationError,
                TypeError,
                ValueError,
            ) as exc:
                raise StoreCorruptionError(f"malformed task envelope: {exc}") from exc
        return RuntimeRecord(
            current_state=row["current_state"],
            previous_recoverable_state=row["previous_recoverable_state"],
            run_id=row["run_id"],
            task_id=row["task_id"],
            turn_id=row["turn_id"],
            gate_id=row["gate_id"],
            baseline_sha=row["baseline_sha"],
            result_sha=row["result_sha"],
            expected_next_task_id=row["expected_next_task_id"],
            task_envelope=envelope,
            protocol_version=row["protocol_version"],
            revision=row["revision"],
        )

    def save_runtime(
        self, record: RuntimeRecord, *, expected_revision: int | None
    ) -> RuntimeRecord:
        next_revision = 0 if expected_revision is None else expected_revision + 1
        persisted = replace(record, revision=next_revision)
        values = (
            persisted.current_state.value,
            persisted.previous_recoverable_state.value if persisted.previous_recoverable_state else None,
            persisted.run_id,
            persisted.task_id,
            persisted.turn_id,
            persisted.gate_id,
            persisted.baseline_sha,
            persisted.result_sha,
            persisted.expected_next_task_id,
            _canonical_json(persisted.task_envelope.to_dict())
            if persisted.task_envelope is not None
            else None,
            persisted.protocol_version,
            persisted.revision,
        )
        try:
            with self._checked_connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if expected_revision is None:
                    try:
                        connection.execute(
                            """INSERT INTO runtime_state(
                                   singleton, current_state, previous_recoverable_state,
                                   run_id, task_id, turn_id, gate_id, baseline_sha,
                                   result_sha, expected_next_task_id,
                                   task_envelope_json, protocol_version, revision
                               ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            values,
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ConcurrentStateError("runtime state already exists") from exc
                else:
                    cursor = connection.execute(
                        """UPDATE runtime_state
                           SET current_state = ?, previous_recoverable_state = ?,
                               run_id = ?, task_id = ?, turn_id = ?, gate_id = ?,
                               baseline_sha = ?, result_sha = ?,
                               expected_next_task_id = ?, task_envelope_json = ?,
                               protocol_version = ?, revision = ?
                           WHERE singleton = 1 AND revision = ?""",
                        values + (expected_revision,),
                    )
                    if cursor.rowcount != 1:
                        raise ConcurrentStateError(
                            f"expected runtime revision {expected_revision}"
                        )
                connection.commit()
        except PersistenceError:
            raise
        except sqlite3.DatabaseError as exc:
            raise StoreCorruptionError(str(exc)) from exc
        return persisted

    def operational_record_count(self) -> int:
        with self._checked_connection() as connection:
            counts = (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "runtime_state",
                    "effects",
                    "gates",
                    "contexts",
                    "dispatches",
                    "turn_activity",
                    "coordinator_state",
                    "git_state",
                    "gate_external",
                    "operator_state",
                    "maintenance_epochs",
                )
            )
            return sum(int(count) for count in counts)

    def request_effect(
        self,
        *,
        effect_id: str,
        idempotency_key: str,
        kind: EffectKind | str,
        intent: EffectIntent,
    ) -> EffectRequest:
        if not effect_id or not idempotency_key:
            raise IdempotencyIntentMismatchError("effect_id and idempotency_key must be non-empty")
        try:
            parsed_kind = kind if isinstance(kind, EffectKind) else EffectKind(kind)
        except (TypeError, ValueError) as exc:
            raise IdempotencyIntentMismatchError(f"unknown effect kind: {kind!r}") from exc
        expected_intent_type = _EFFECT_INTENT_TYPES[parsed_kind]
        if type(intent) is not expected_intent_type:
            raise UnsafePersistenceDataError(
                f"{parsed_kind.value} requires {expected_intent_type.__name__}"
            )
        intent_data = intent.to_dict()
        intent_json = _canonical_json(intent_data)
        now = _utc_now()

        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            by_id = connection.execute(
                "SELECT * FROM effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
            by_key = connection.execute(
                "SELECT * FROM effects WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            existing = by_id or by_key
            if existing is None:
                connection.execute(
                    """INSERT INTO effects(
                           effect_id, idempotency_key, kind, status, intent_json,
                           created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        effect_id,
                        idempotency_key,
                        parsed_kind.value,
                        EffectStatus.NOT_STARTED.value,
                        intent_json,
                        now,
                        now,
                    ),
                )
                connection.commit()
                record = EffectRecord(
                    effect_id, idempotency_key, parsed_kind, EffectStatus.NOT_STARTED, intent
                )
                return EffectRequest(EffectRequestAction.EXECUTE, record)

            if (
                existing["effect_id"] != effect_id
                or existing["idempotency_key"] != idempotency_key
                or existing["kind"] != parsed_kind.value
                or existing["intent_json"] != intent_json
            ):
                raise IdempotencyIntentMismatchError(
                    "same effect identity used with different immutable intent"
                )
            record = self._effect_from_row(existing)
            if record.status is EffectStatus.COMPLETED:
                connection.commit()
                return EffectRequest(EffectRequestAction.SKIP_COMPLETED, record)
            if record.status in {EffectStatus.IN_PROGRESS, EffectStatus.AMBIGUOUS}:
                raise AmbiguousEffectError(
                    f"effect {effect_id} requires deterministic reconciliation"
                )
            connection.commit()
            return EffectRequest(EffectRequestAction.EXECUTE, record)

    def load_effect(self, effect_id: str) -> EffectRecord | None:
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT * FROM effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
        return self._effect_from_row(row) if row is not None else None

    @staticmethod
    def _effect_from_row(row: sqlite3.Row) -> EffectRecord:
        try:
            kind = EffectKind(row["kind"])
            intent_data = json.loads(row["intent_json"])
            if not isinstance(intent_data, dict):
                raise TypeError("effect intent is not an object")
            intent_type = _EFFECT_INTENT_TYPES[kind]
            intent = intent_type(**intent_data)
            return EffectRecord(
                effect_id=row["effect_id"],
                idempotency_key=row["idempotency_key"],
                kind=kind,
                status=EffectStatus(row["status"]),
                intent=intent,
            )
        except (
            ValueError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            UnsafePersistenceDataError,
        ) as exc:
            raise StoreCorruptionError(f"malformed effect record: {exc}") from exc

    def effects_with_statuses(
        self, statuses: tuple[EffectStatus, ...]
    ) -> tuple[EffectRecord, ...]:
        if not statuses:
            return ()
        placeholders = ",".join("?" for _ in statuses)
        with self._checked_connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM effects WHERE status IN ({placeholders}) ORDER BY effect_id",
                tuple(status.value for status in statuses),
            ).fetchall()
        return tuple(self._effect_from_row(row) for row in rows)

    def begin_effect(self, effect_id: str) -> EffectRecord:
        return self._advance_effect(effect_id, EffectStatus.NOT_STARTED, EffectStatus.IN_PROGRESS)

    def complete_effect(self, effect_id: str) -> EffectRecord:
        current = self.load_effect(effect_id)
        if current is not None and current.status is EffectStatus.COMPLETED:
            return current
        return self._advance_effect(effect_id, EffectStatus.IN_PROGRESS, EffectStatus.COMPLETED)

    def _advance_effect(
        self, effect_id: str, expected: EffectStatus, target: EffectStatus
    ) -> EffectRecord:
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE effects SET status = ?, updated_at = ? WHERE effect_id = ? AND status = ?",
                (target.value, _utc_now(), effect_id, expected.value),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    "SELECT status FROM effects WHERE effect_id = ?", (effect_id,)
                ).fetchone()
                observed = row["status"] if row is not None else "MISSING"
                raise AmbiguousEffectError(
                    f"effect {effect_id}: expected {expected.value}, observed {observed}"
                )
            connection.commit()
        record = self.load_effect(effect_id)
        if record is None:
            raise StoreCorruptionError(f"effect disappeared after update: {effect_id}")
        return record

    def reconcile_effect(
        self, effect_id: str, outcome: ReconciliationOutcome | str
    ) -> EffectRecord:
        try:
            parsed = outcome if isinstance(outcome, ReconciliationOutcome) else ReconciliationOutcome(outcome)
        except (TypeError, ValueError) as exc:
            raise AmbiguousEffectError(f"unknown reconciliation outcome: {outcome!r}") from exc
        target = {
            ReconciliationOutcome.NO_EFFECT: EffectStatus.NOT_STARTED,
            ReconciliationOutcome.COMPLETED: EffectStatus.COMPLETED,
            ReconciliationOutcome.UNKNOWN: EffectStatus.AMBIGUOUS,
        }[parsed]
        return self._advance_effect(effect_id, EffectStatus.IN_PROGRESS, target)

    def record_gate(self, manifest: HumanGateManifest) -> HumanGateManifest:
        payload = _canonical_json(manifest.to_dict())
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM gates WHERE gate_id = ?", (manifest.gate_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO gates(gate_id, task_id, status, manifest_json, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (manifest.gate_id, manifest.task_id, manifest.status.value, payload, _utc_now()),
                )
            elif row["manifest_json"] != payload:
                raise GateReplayError(f"gate ID collision: {manifest.gate_id}")
            connection.commit()
        return manifest

    def load_gate(self, gate_id: str) -> HumanGateManifest | None:
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM gates WHERE gate_id = ?", (gate_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return HumanGateManifest.from_dict(json.loads(row["manifest_json"]))
        except (json.JSONDecodeError, ProtocolValidationError, TypeError, ValueError) as exc:
            raise StoreCorruptionError(f"malformed gate record {gate_id}: {exc}") from exc

    def pending_gates_for_task(self, task_id: str) -> tuple[HumanGateManifest, ...]:
        with self._checked_connection() as connection:
            rows = connection.execute(
                "SELECT manifest_json FROM gates WHERE task_id = ? AND status = ? ORDER BY gate_id",
                (task_id, GateStatus.PENDING.value),
            ).fetchall()
        manifests: list[HumanGateManifest] = []
        for row in rows:
            try:
                manifests.append(
                    HumanGateManifest.from_dict(json.loads(row["manifest_json"]))
                )
            except (
                json.JSONDecodeError,
                ProtocolValidationError,
                TypeError,
                ValueError,
            ) as exc:
                raise StoreCorruptionError(
                    f"malformed pending gate record for {task_id}: {exc}"
                ) from exc
        return tuple(manifests)

    def decide_gate(self, gate_id: str, decision: GateStatus | str) -> HumanGateManifest:
        try:
            parsed = decision if isinstance(decision, GateStatus) else GateStatus(decision)
        except (TypeError, ValueError) as exc:
            raise GateReplayError(f"unknown gate decision: {decision!r}") from exc
        if parsed is GateStatus.PENDING:
            raise GateReplayError("PENDING is not a terminal decision")

        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT manifest_json, status FROM gates WHERE gate_id = ?", (gate_id,)
            ).fetchone()
            if row is None:
                raise GateReplayError(f"unknown gate: {gate_id}")
            if row["status"] != GateStatus.PENDING.value:
                raise GateReplayError(f"terminal gate replay: {gate_id}")
            try:
                manifest = HumanGateManifest.from_dict(json.loads(row["manifest_json"]))
            except (json.JSONDecodeError, ProtocolValidationError, TypeError, ValueError) as exc:
                raise StoreCorruptionError(f"malformed gate record {gate_id}: {exc}") from exc
            terminal = manifest.terminal(parsed)
            connection.execute(
                "UPDATE gates SET status = ?, manifest_json = ?, updated_at = ? WHERE gate_id = ?",
                (parsed.value, _canonical_json(terminal.to_dict()), _utc_now(), gate_id),
            )
            connection.commit()
        return terminal

    def raw_metadata(self) -> dict[str, str]:
        """Small inspection helper used by compatibility tests."""
        with self._checked_connection() as connection:
            return dict(connection.execute("SELECT key, value FROM metadata"))

    def record_context(self, record: ContextRecord) -> ContextRecord:
        """Persist a bounded context identity and enforce active-thread separation."""
        if not isinstance(record, ContextRecord):
            raise UnsafePersistenceDataError("record_context requires ContextRecord")
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM contexts WHERE thread_id = ?", (record.thread_id,)
            ).fetchone()
            if existing is not None:
                observed = self._context_from_row(existing)
                if (
                    observed.thread_id != record.thread_id
                    or observed.context_class is not record.context_class
                    or observed.role != record.role
                    or observed.cwd != record.cwd
                    or observed.codex_version != record.codex_version
                ):
                    raise UnsafePersistenceDataError(
                        f"thread identity collision: {record.thread_id}"
                    )
                if observed != record:
                    connection.execute(
                        """UPDATE contexts SET
                               effective_model_id = ?,
                               effective_reasoning_effort = ?,
                               routing_class = ?, active = ?, updated_at = ?
                           WHERE thread_id = ?""",
                        (
                            record.effective_model_id,
                            record.effective_reasoning_effort,
                            record.routing_class.value,
                            int(record.active),
                            _utc_now(),
                            record.thread_id,
                        ),
                    )
                connection.commit()
                return record
            if record.active:
                collision = connection.execute(
                    """SELECT thread_id FROM contexts
                       WHERE active = 1 AND thread_id = ?""",
                    (record.thread_id,),
                ).fetchone()
                if collision is not None:
                    raise UnsafePersistenceDataError(
                        f"active context thread collision: {record.thread_id}"
                    )
            connection.execute(
                """INSERT INTO contexts(
                       thread_id, context_class, role, effective_model_id,
                       effective_reasoning_effort, routing_class, cwd,
                       codex_version, active, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.thread_id,
                    record.context_class.value,
                    record.role,
                    record.effective_model_id,
                    record.effective_reasoning_effort,
                    record.routing_class.value,
                    record.cwd,
                    record.codex_version,
                    int(record.active),
                    _utc_now(),
                ),
            )
            connection.commit()
        return record

    @staticmethod
    def _context_from_row(row: sqlite3.Row) -> ContextRecord:
        try:
            return ContextRecord(
                thread_id=row["thread_id"],
                context_class=row["context_class"],
                role=row["role"],
                effective_model_id=row["effective_model_id"],
                effective_reasoning_effort=row["effective_reasoning_effort"],
                routing_class=row["routing_class"],
                cwd=row["cwd"],
                codex_version=row["codex_version"],
                active=bool(row["active"]),
            )
        except (ValueError, TypeError, UnsafePersistenceDataError) as exc:
            raise StoreCorruptionError(f"malformed context record: {exc}") from exc

    def list_contexts(self, *, active_only: bool = False) -> tuple[ContextRecord, ...]:
        query = "SELECT * FROM contexts"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY updated_at, thread_id"
        with self._checked_connection() as connection:
            rows = connection.execute(query).fetchall()
        return tuple(self._context_from_row(row) for row in rows)

    def load_context(self, thread_id: str) -> ContextRecord:
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise UnsafePersistenceDataError(f"invalid thread_id: {thread_id!r}")
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT * FROM contexts WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        if row is None:
            raise StoreCorruptionError(f"unknown context thread: {thread_id}")
        return self._context_from_row(row)

    def retire_context(self, thread_id: str) -> None:
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise UnsafePersistenceDataError(f"invalid thread_id: {thread_id!r}")
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE contexts SET active = 0, updated_at = ? WHERE thread_id = ?",
                (_utc_now(), thread_id),
            )
            if cursor.rowcount != 1:
                raise StoreCorruptionError(f"unknown context thread: {thread_id}")
            connection.commit()

    def record_dispatch(self, record: DispatchRecord) -> DispatchRecord:
        if not isinstance(record, DispatchRecord):
            raise UnsafePersistenceDataError("record_dispatch requires DispatchRecord")
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            context = connection.execute(
                "SELECT * FROM contexts WHERE thread_id = ?", (record.thread_id,)
            ).fetchone()
            if context is None:
                raise UnsafePersistenceDataError(
                    f"dispatch references unknown thread: {record.thread_id}"
                )
            observed_context = self._context_from_row(context)
            if (
                observed_context.context_class is not record.context_class
                or observed_context.codex_version != record.codex_version
                or observed_context.routing_class is not record.routing_class
                or observed_context.effective_model_id != record.effective_model_id
                or observed_context.effective_reasoning_effort
                != record.effective_reasoning_effort
                or not observed_context.active
            ):
                raise UnsafePersistenceDataError(
                    f"dispatch/context routing mismatch: {record.dispatch_id}"
                )
            try:
                connection.execute(
                    """INSERT INTO dispatches(
                           dispatch_id, thread_id, turn_id, context_class,
                           routing_class, effective_model_id,
                           effective_reasoning_effort, codex_version,
                           schema_repair, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.dispatch_id,
                        record.thread_id,
                        record.turn_id,
                        record.context_class.value,
                        record.routing_class.value,
                        record.effective_model_id,
                        record.effective_reasoning_effort,
                        record.codex_version,
                        int(record.schema_repair),
                        _utc_now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                row = connection.execute(
                    "SELECT * FROM dispatches WHERE dispatch_id = ?",
                    (record.dispatch_id,),
                ).fetchone()
                if row is None or self._dispatch_from_row(row) != record:
                    raise UnsafePersistenceDataError(
                        f"dispatch identity collision: {record.dispatch_id}"
                    ) from exc
            connection.commit()
        return record

    @staticmethod
    def _dispatch_from_row(row: sqlite3.Row) -> DispatchRecord:
        try:
            return DispatchRecord(
                dispatch_id=row["dispatch_id"],
                thread_id=row["thread_id"],
                turn_id=row["turn_id"],
                context_class=row["context_class"],
                routing_class=row["routing_class"],
                effective_model_id=row["effective_model_id"],
                effective_reasoning_effort=row["effective_reasoning_effort"],
                codex_version=row["codex_version"],
                schema_repair=bool(row["schema_repair"]),
            )
        except (ValueError, TypeError, UnsafePersistenceDataError) as exc:
            raise StoreCorruptionError(f"malformed dispatch record: {exc}") from exc

    def list_dispatches(self) -> tuple[DispatchRecord, ...]:
        with self._checked_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM dispatches ORDER BY created_at, dispatch_id"
            ).fetchall()
        return tuple(self._dispatch_from_row(row) for row in rows)

    def start_turn_activity(self, record: TurnActivityRecord) -> TurnActivityRecord:
        if record.status is not TurnActivityStatus.IN_PROGRESS:
            raise UnsafePersistenceDataError("new turn activity must be IN_PROGRESS")
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            context = connection.execute(
                "SELECT thread_id FROM contexts WHERE thread_id = ? AND active = 1",
                (record.thread_id,),
            ).fetchone()
            if context is None:
                raise UnsafePersistenceDataError(
                    f"turn activity references inactive context: {record.thread_id}"
                )
            try:
                connection.execute(
                    """INSERT INTO turn_activity(
                           activity_id, dispatch_id, thread_id, context_class,
                           routing_class, requested_model_id,
                           requested_reasoning_effort, status, turn_id,
                           error_class, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.activity_id,
                        record.dispatch_id,
                        record.thread_id,
                        record.context_class.value,
                        record.routing_class.value,
                        record.requested_model_id,
                        record.requested_reasoning_effort,
                        record.status.value,
                        record.turn_id,
                        record.error_class,
                        _utc_now(),
                        _utc_now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                existing = connection.execute(
                    "SELECT * FROM turn_activity WHERE activity_id = ? OR dispatch_id = ?",
                    (record.activity_id, record.dispatch_id),
                ).fetchone()
                if existing is None or self._turn_activity_from_row(existing) != record:
                    raise UnsafePersistenceDataError(
                        f"turn activity identity collision: {record.activity_id}"
                    ) from exc
            connection.commit()
        return record

    @staticmethod
    def _turn_activity_from_row(row: sqlite3.Row) -> TurnActivityRecord:
        try:
            return TurnActivityRecord(
                activity_id=row["activity_id"],
                dispatch_id=row["dispatch_id"],
                thread_id=row["thread_id"],
                context_class=row["context_class"],
                routing_class=row["routing_class"],
                requested_model_id=row["requested_model_id"],
                requested_reasoning_effort=row["requested_reasoning_effort"],
                status=row["status"],
                turn_id=row["turn_id"],
                error_class=row["error_class"],
            )
        except (TypeError, ValueError, UnsafePersistenceDataError) as exc:
            raise StoreCorruptionError(f"malformed turn activity: {exc}") from exc

    def update_turn_activity(
        self,
        activity_id: str,
        *,
        status: TurnActivityStatus,
        turn_id: str | None = None,
        error_class: str | None = None,
    ) -> TurnActivityRecord:
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM turn_activity WHERE activity_id = ?", (activity_id,)
            ).fetchone()
            if row is None:
                raise StoreCorruptionError(f"unknown turn activity: {activity_id}")
            current = self._turn_activity_from_row(row)
            if current.status is not TurnActivityStatus.IN_PROGRESS:
                candidate = replace(
                    current, status=status, turn_id=turn_id or current.turn_id,
                    error_class=error_class,
                )
                if candidate != current:
                    raise ConcurrentStateError(
                        f"terminal turn activity replay: {activity_id}"
                    )
                connection.commit()
                return current
            updated = replace(
                current,
                status=status,
                turn_id=turn_id or current.turn_id,
                error_class=error_class,
            )
            connection.execute(
                """UPDATE turn_activity SET status = ?, turn_id = ?,
                   error_class = ?, updated_at = ? WHERE activity_id = ?""",
                (
                    updated.status.value,
                    updated.turn_id,
                    updated.error_class,
                    _utc_now(),
                    activity_id,
                ),
            )
            connection.commit()
        return updated

    def turn_activities(
        self, statuses: tuple[TurnActivityStatus, ...] | None = None
    ) -> tuple[TurnActivityRecord, ...]:
        query = "SELECT * FROM turn_activity"
        parameters: tuple[str, ...] = ()
        if statuses:
            query += " WHERE status IN (" + ",".join("?" for _ in statuses) + ")"
            parameters = tuple(status.value for status in statuses)
        query += " ORDER BY created_at, activity_id"
        with self._checked_connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._turn_activity_from_row(row) for row in rows)

    def save_coordinator_state(self, record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise UnsafePersistenceDataError("coordinator state must be an object")
        encoded = _canonical_json(record)
        if len(encoded.encode("utf-8")) > 1024 * 1024:
            raise UnsafePersistenceDataError("coordinator state exceeds bounded size")
        lowered = encoded.casefold()
        if any(marker in lowered for marker in ('"token"', '"password"', '"secret"', '"email"')):
            raise UnsafePersistenceDataError("coordinator state contains forbidden key")
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO coordinator_state(singleton, record_json, updated_at)
                   VALUES (1, ?, ?)
                   ON CONFLICT(singleton) DO UPDATE SET
                       record_json = excluded.record_json,
                       updated_at = excluded.updated_at""",
                (encoded, _utc_now()),
            )
            connection.commit()
        return record

    def load_coordinator_state(self) -> dict[str, Any] | None:
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT record_json FROM coordinator_state WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row[0])
        except json.JSONDecodeError as exc:
            raise StoreCorruptionError(f"malformed coordinator state: {exc}") from exc
        if not isinstance(value, dict):
            raise StoreCorruptionError("coordinator state is not an object")
        return value

    def clear_coordinator_state(self) -> None:
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM coordinator_state WHERE singleton = 1")
            connection.commit()

    def load_dispatch(self, dispatch_id: str) -> DispatchRecord:
        if not isinstance(dispatch_id, str) or not dispatch_id.strip():
            raise UnsafePersistenceDataError(f"invalid dispatch_id: {dispatch_id!r}")
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT * FROM dispatches WHERE dispatch_id = ?", (dispatch_id,)
            ).fetchone()
        if row is None:
            raise StoreCorruptionError(f"unknown dispatch: {dispatch_id}")
        return self._dispatch_from_row(row)

    def latest_dispatch_for_thread(self, thread_id: str) -> DispatchRecord:
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise UnsafePersistenceDataError(f"invalid thread_id: {thread_id!r}")
        with self._checked_connection() as connection:
            row = connection.execute(
                """SELECT * FROM dispatches WHERE thread_id = ?
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (thread_id,),
            ).fetchone()
        if row is None:
            raise StoreCorruptionError(f"thread has no dispatch: {thread_id}")
        return self._dispatch_from_row(row)

    def routing_counts(self) -> dict[str, int]:
        with self._checked_connection() as connection:
            rows = connection.execute(
                "SELECT routing_class, COUNT(*) FROM dispatches GROUP BY routing_class"
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def save_git_state(self, record: GitStateRecord) -> GitStateRecord:
        if not isinstance(record, GitStateRecord):
            raise UnsafePersistenceDataError("save_git_state requires GitStateRecord")
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO git_state(
                       singleton, integration_branch, integration_sha,
                       task_worktree, main_sha, task_id, task_branch,
                       reviewed_head_sha, integration_verified, cleanup_status,
                       updated_at
                   ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(singleton) DO UPDATE SET
                       integration_branch = excluded.integration_branch,
                       integration_sha = excluded.integration_sha,
                       task_worktree = excluded.task_worktree,
                       main_sha = excluded.main_sha,
                       task_id = excluded.task_id,
                       task_branch = excluded.task_branch,
                       reviewed_head_sha = excluded.reviewed_head_sha,
                       integration_verified = excluded.integration_verified,
                       cleanup_status = excluded.cleanup_status,
                       updated_at = excluded.updated_at""",
                (
                    record.integration_branch,
                    record.integration_sha,
                    record.task_worktree,
                    record.main_sha,
                    record.task_id,
                    record.task_branch,
                    record.reviewed_head_sha,
                    int(record.integration_verified),
                    record.cleanup_status,
                    _utc_now(),
                ),
            )
            connection.commit()
        return record

    def load_git_state(self) -> GitStateRecord | None:
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT * FROM git_state WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return None
        try:
            return GitStateRecord(
                integration_branch=row["integration_branch"],
                integration_sha=row["integration_sha"],
                task_worktree=row["task_worktree"],
                main_sha=row["main_sha"],
                task_id=row["task_id"],
                task_branch=row["task_branch"],
                reviewed_head_sha=row["reviewed_head_sha"],
                integration_verified=bool(row["integration_verified"]),
                cleanup_status=row["cleanup_status"],
            )
        except UnsafePersistenceDataError as exc:
            raise StoreCorruptionError(f"malformed git state: {exc}") from exc

    def save_gate_external(self, record: GateExternalRecord) -> GateExternalRecord:
        if not isinstance(record, GateExternalRecord):
            raise UnsafePersistenceDataError("save_gate_external requires GateExternalRecord")
        payload = _canonical_json(asdict(record))
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT record_json FROM gate_external WHERE gate_id = ?",
                (record.gate_id,),
            ).fetchone()
            if existing is not None:
                old = self._gate_external_from_json(existing[0])
                immutable_old = replace(
                    old,
                    decision_comment_id=None,
                    decision_author_id=None,
                    decision=GateStatus.PENDING,
                )
                immutable_new = replace(
                    record,
                    decision_comment_id=None,
                    decision_author_id=None,
                    decision=GateStatus.PENDING,
                )
                if immutable_old != immutable_new:
                    raise GateReplayError(f"external gate binding mutation: {record.gate_id}")
                if old.decision is not GateStatus.PENDING and record != old:
                    raise GateReplayError(f"external terminal gate replay: {record.gate_id}")
            connection.execute(
                """INSERT INTO gate_external(gate_id, record_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(gate_id) DO UPDATE SET
                       record_json = excluded.record_json,
                       updated_at = excluded.updated_at""",
                (record.gate_id, payload, _utc_now()),
            )
            connection.commit()
        return record

    @staticmethod
    def _gate_external_from_json(payload: str) -> GateExternalRecord:
        try:
            data = json.loads(payload)
            return GateExternalRecord(**data)
        except (json.JSONDecodeError, TypeError, ValueError, UnsafePersistenceDataError) as exc:
            raise StoreCorruptionError(f"malformed external gate record: {exc}") from exc

    def load_gate_external(self, gate_id: str) -> GateExternalRecord | None:
        _validated_gate_id(gate_id)
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT record_json FROM gate_external WHERE gate_id = ?", (gate_id,)
            ).fetchone()
        return None if row is None else self._gate_external_from_json(row[0])

    def save_operator_state(self, record: OperatorStateRecord) -> OperatorStateRecord:
        if not isinstance(record, OperatorStateRecord):
            raise UnsafePersistenceDataError("save_operator_state requires OperatorStateRecord")
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO operator_state(singleton, record_json, updated_at)
                   VALUES (1, ?, ?)
                   ON CONFLICT(singleton) DO UPDATE SET
                       record_json = excluded.record_json,
                       updated_at = excluded.updated_at""",
                (_canonical_json(asdict(record)), _utc_now()),
            )
            connection.commit()
        return record

    def load_operator_state(self) -> OperatorStateRecord:
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT record_json FROM operator_state WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return OperatorStateRecord()
        try:
            return OperatorStateRecord(**json.loads(row[0]))
        except (json.JSONDecodeError, TypeError, ValueError, UnsafePersistenceDataError) as exc:
            raise StoreCorruptionError(f"malformed operator state: {exc}") from exc

    def save_maintenance_epoch(
        self, record: MaintenanceEpochRecord
    ) -> MaintenanceEpochRecord:
        if not isinstance(record, MaintenanceEpochRecord):
            raise UnsafePersistenceDataError(
                "save_maintenance_epoch requires MaintenanceEpochRecord"
            )
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT record_json FROM maintenance_epochs WHERE maintenance_id = ?",
                (record.maintenance_id,),
            ).fetchone()
            if existing is not None:
                old = self._maintenance_from_json(existing[0])
                if replace(old, exited_at=None, reconciliation=None) != replace(
                    record, exited_at=None, reconciliation=None
                ):
                    raise ConcurrentStateError("maintenance entry snapshot mutation")
                if old.exited_at is not None and record != old:
                    raise ConcurrentStateError("terminal maintenance epoch replay")
            connection.execute(
                """INSERT INTO maintenance_epochs(maintenance_id, record_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(maintenance_id) DO UPDATE SET
                       record_json = excluded.record_json,
                       updated_at = excluded.updated_at""",
                (record.maintenance_id, _canonical_json(asdict(record)), _utc_now()),
            )
            connection.commit()
        return record

    @staticmethod
    def _maintenance_from_json(payload: str) -> MaintenanceEpochRecord:
        try:
            return MaintenanceEpochRecord(**json.loads(payload))
        except (json.JSONDecodeError, TypeError, ValueError, UnsafePersistenceDataError) as exc:
            raise StoreCorruptionError(f"malformed maintenance epoch: {exc}") from exc

    def load_maintenance_epoch(self, maintenance_id: str) -> MaintenanceEpochRecord | None:
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT record_json FROM maintenance_epochs WHERE maintenance_id = ?",
                (maintenance_id,),
            ).fetchone()
        return None if row is None else self._maintenance_from_json(row[0])

    def consistent_backup(self, backup_dir: str | Path, *, retain: int = 5) -> Path:
        if not isinstance(retain, int) or retain < 1 or retain > 20:
            raise UnsafePersistenceDataError(f"invalid backup retention: {retain!r}")
        directory = Path(backup_dir)
        directory.mkdir(parents=True, exist_ok=True)
        if directory.resolve() == self.path.parent.resolve():
            raise UnsafePersistenceDataError("backup directory must be a state subdirectory")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = directory / f"state-{stamp}.sqlite"
        with self._checked_connection() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
        backups = sorted(directory.glob("state-*.sqlite"), reverse=True)
        for obsolete in backups[retain:]:
            obsolete.unlink()
        return destination

    def backup_with_effect(
        self,
        backup_dir: str | Path,
        *,
        effect_id: str,
        retain: int = 5,
    ) -> Path:
        """Create/reconcile one consistent backup as an allow-listed effect."""
        runtime = self.load_runtime()
        run_id = runtime.run_id if runtime is not None else "ORCH-OPERATOR"
        revision = runtime.revision if runtime is not None else 0
        intent = StateBackupIntent(run_id, revision)
        suffix = hashlib.sha256(effect_id.encode("utf-8")).hexdigest()[:24]
        directory = Path(backup_dir)
        destination = directory / f"state-effect-{suffix}.sqlite"
        effect = self.load_effect(effect_id)
        if effect is not None and effect.status is EffectStatus.IN_PROGRESS:
            if not destination.is_file():
                raise AmbiguousEffectError(
                    f"backup effect {effect_id} has no verifiable destination"
                )
            probe = SQLiteStateStore(destination)
            probe.initialize()
            self.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
            backup_effect = probe.load_effect(effect_id)
            if backup_effect is not None and backup_effect.status is EffectStatus.IN_PROGRESS:
                probe.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
            return destination
        request = self.request_effect(
            effect_id=effect_id,
            idempotency_key=f"STATE_BACKUP:{run_id}:{revision}:{suffix}",
            kind=EffectKind.STATE_BACKUP,
            intent=intent,
        )
        if request.action is EffectRequestAction.SKIP_COMPLETED:
            if not destination.is_file():
                raise StoreCorruptionError("completed backup effect has no destination")
            probe = SQLiteStateStore(destination)
            probe.initialize()
            backup_effect = probe.load_effect(effect_id)
            if backup_effect is not None and backup_effect.status is EffectStatus.IN_PROGRESS:
                probe.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
            return destination
        directory.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise AmbiguousEffectError("backup destination pre-exists before effect")
        self.begin_effect(effect_id)
        with self._checked_connection() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
        SQLiteStateStore(destination).initialize()
        self.complete_effect(effect_id)
        SQLiteStateStore(destination).complete_effect(effect_id)
        backups = sorted(directory.glob("state-*.sqlite"), reverse=True)
        for obsolete in backups[retain:]:
            if obsolete != destination:
                obsolete.unlink()
        return destination
