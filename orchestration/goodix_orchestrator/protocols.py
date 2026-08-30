# SPDX-License-Identifier: GPL-2.0-or-later
"""Validated structured contracts for the O001 orchestration boundary."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any, Mapping

from .policy import (
    Capability,
    PROTECTED_CAPABILITIES,
    ProtectedBranchError,
    require_ordinary_branch,
)
from .state import GATE_CONTINUATION_STATES, OrchestratorState


PROTOCOL_VERSION = "1.0"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TASK_ID_RE = re.compile(r"^TASK-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_GATE_ID_RE = re.compile(r"^HG-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_BRANCH_FORBIDDEN_RE = re.compile(r"[\s~^:?*\[\\]")


@dataclass(frozen=True, slots=True)
class ProtocolValidationError(Exception):
    code: str
    field: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code} ({self.field}): {self.detail}"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "detail": self.detail}


class GateClass(StrEnum):
    HOST_ONLY = "HOST_ONLY"


class ExecutorOutcome(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class ExecutableClosure(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TestStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class Disposition(StrEnum):
    ACCEPT = "ACCEPT"
    CORRECTIVE = "CORRECTIVE"
    REPLAN = "REPLAN"
    HUMAN_GATE = "HUMAN_GATE"
    PAUSE = "PAUSE"
    DONE = "DONE"


class PauseReason(StrEnum):
    RATE_LIMIT = "RATE_LIMIT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class GateStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class GateRequester(StrEnum):
    AI_PM = "AI_PM"


def _enum(enum_type: type[StrEnum], value: Any, field: str) -> StrEnum:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolValidationError("UNKNOWN_ENUM_VALUE", field, repr(value)) from exc


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolValidationError("EMPTY_CRITICAL_FIELD", field, repr(value))
    return value


def _string_tuple(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, str) or value is None:
        raise ProtocolValidationError("INVALID_SEQUENCE", field, repr(value))
    try:
        result = tuple(_nonempty(item, field) for item in value)
    except TypeError as exc:
        raise ProtocolValidationError("INVALID_SEQUENCE", field, repr(value)) from exc
    if not result and not allow_empty:
        raise ProtocolValidationError("EMPTY_CRITICAL_FIELD", field, "at least one item required")
    return result


def _protocol_version(value: Any) -> str:
    if value != PROTOCOL_VERSION:
        raise ProtocolValidationError("UNSUPPORTED_PROTOCOL_VERSION", "protocol_version", repr(value))
    return value


def _sha(value: Any, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise ProtocolValidationError("MALFORMED_SHA", field, repr(value))
    return value


def _task_id(value: Any, field: str = "task_id", *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _TASK_ID_RE.fullmatch(value) is None:
        raise ProtocolValidationError("MALFORMED_TASK_ID", field, repr(value))
    return value


def _gate_id(value: Any) -> str:
    if not isinstance(value, str) or _GATE_ID_RE.fullmatch(value) is None:
        raise ProtocolValidationError("MALFORMED_GATE_ID", "gate_id", repr(value))
    return value


def _branch(value: Any, field: str) -> str:
    branch = _nonempty(value, field)
    if (
        branch.startswith("/")
        or branch.endswith("/")
        or branch.endswith(".")
        or ".." in branch
        or "//" in branch
        or "@{" in branch
        or _BRANCH_FORBIDDEN_RE.search(branch)
    ):
        raise ProtocolValidationError("MALFORMED_BRANCH", field, repr(value))
    try:
        return require_ordinary_branch(branch)
    except ProtectedBranchError as exc:
        raise ProtocolValidationError(
            "PROTECTED_MAIN_BRANCH", field, branch
        ) from exc


def _json_ready(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


class ProtocolMixin:
    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True, slots=True)
class ModelPolicy(ProtocolMixin):
    preferred: str
    allowed: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "preferred", _nonempty(self.preferred, "model_policy.preferred"))
        allowed = _string_tuple(self.allowed, "model_policy.allowed")
        if self.preferred not in allowed:
            raise ProtocolValidationError(
                "PREFERRED_MODEL_NOT_ALLOWED", "model_policy", self.preferred
            )
        object.__setattr__(self, "allowed", allowed)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModelPolicy":
        return cls(preferred=data.get("preferred"), allowed=tuple(data.get("allowed", ())))


@dataclass(frozen=True, slots=True)
class TaskScope(ProtocolMixin):
    paths: tuple[str, ...]
    non_goals: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "paths", _string_tuple(self.paths, "scope.paths"))
        object.__setattr__(self, "non_goals", _string_tuple(self.non_goals, "scope.non_goals"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskScope":
        return cls(paths=tuple(data.get("paths", ())), non_goals=tuple(data.get("non_goals", ())))


@dataclass(frozen=True, slots=True)
class TaskManifest(ProtocolMixin):
    protocol_version: str
    task_id: str
    parent_task_id: str | None
    title: str
    objective: str
    baseline_sha: str
    integration_branch: str
    task_branch: str
    model_policy: ModelPolicy
    gate_class: GateClass
    capabilities_required: tuple[Capability, ...]
    scope: TaskScope
    acceptance_criteria: tuple[str, ...]
    manual_update_required: bool
    stop_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "protocol_version", _protocol_version(self.protocol_version))
        object.__setattr__(self, "task_id", _task_id(self.task_id))
        object.__setattr__(self, "parent_task_id", _task_id(self.parent_task_id, "parent_task_id", optional=True))
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "objective", _nonempty(self.objective, "objective"))
        object.__setattr__(self, "baseline_sha", _sha(self.baseline_sha, "baseline_sha"))
        object.__setattr__(self, "integration_branch", _branch(self.integration_branch, "integration_branch"))
        object.__setattr__(self, "task_branch", _branch(self.task_branch, "task_branch"))
        if not isinstance(self.model_policy, ModelPolicy):
            raise ProtocolValidationError("INVALID_OBJECT", "model_policy", repr(self.model_policy))
        gate_class = _enum(GateClass, self.gate_class, "gate_class")
        object.__setattr__(self, "gate_class", gate_class)
        if not isinstance(self.scope, TaskScope):
            raise ProtocolValidationError("INVALID_OBJECT", "scope", repr(self.scope))
        if not isinstance(self.manual_update_required, bool):
            raise ProtocolValidationError("INVALID_BOOLEAN", "manual_update_required", repr(self.manual_update_required))

        capabilities: list[Capability] = []
        for raw in self.capabilities_required:
            try:
                capability = raw if isinstance(raw, Capability) else Capability(raw)
            except (TypeError, ValueError) as exc:
                raise ProtocolValidationError("UNKNOWN_CAPABILITY", "capabilities_required", repr(raw)) from exc
            if capability in PROTECTED_CAPABILITIES:
                raise ProtocolValidationError(
                    "PROTECTED_CAPABILITY_REQUEST", "capabilities_required", capability.value
                )
            capabilities.append(capability)
        if not capabilities:
            raise ProtocolValidationError(
                "EMPTY_CRITICAL_FIELD", "capabilities_required", "at least one capability required"
            )
        object.__setattr__(self, "capabilities_required", tuple(capabilities))
        object.__setattr__(self, "acceptance_criteria", _string_tuple(self.acceptance_criteria, "acceptance_criteria"))
        object.__setattr__(self, "stop_conditions", _string_tuple(self.stop_conditions, "stop_conditions"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskManifest":
        return cls(
            protocol_version=data.get("protocol_version"),
            task_id=data.get("task_id"),
            parent_task_id=data.get("parent_task_id"),
            title=data.get("title"),
            objective=data.get("objective"),
            baseline_sha=data.get("baseline_sha"),
            integration_branch=data.get("integration_branch"),
            task_branch=data.get("task_branch"),
            model_policy=ModelPolicy.from_dict(data.get("model_policy", {})),
            gate_class=data.get("gate_class"),
            capabilities_required=tuple(data.get("capabilities_required", ())),
            scope=TaskScope.from_dict(data.get("scope", {})),
            acceptance_criteria=tuple(data.get("acceptance_criteria", ())),
            manual_update_required=data.get("manual_update_required"),
            stop_conditions=tuple(data.get("stop_conditions", ())),
        )


@dataclass(frozen=True, slots=True)
class TaskEnvelope(ProtocolMixin):
    """Immutable delegation envelope retained across a REPLAN."""

    task_id: str
    parent_task_id: str | None
    baseline_sha: str
    integration_branch: str
    task_branch: str
    model_preferred: str
    model_allowed: tuple[str, ...]
    gate_class: GateClass
    capabilities_required: tuple[Capability, ...]
    scope_paths: tuple[str, ...]
    scope_non_goals: tuple[str, ...]
    manual_update_required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _task_id(self.task_id))
        object.__setattr__(
            self,
            "parent_task_id",
            _task_id(self.parent_task_id, "parent_task_id", optional=True),
        )
        object.__setattr__(self, "baseline_sha", _sha(self.baseline_sha, "baseline_sha"))
        object.__setattr__(
            self,
            "integration_branch",
            _branch(self.integration_branch, "integration_branch"),
        )
        object.__setattr__(
            self, "task_branch", _branch(self.task_branch, "task_branch")
        )
        object.__setattr__(
            self, "model_preferred", _nonempty(self.model_preferred, "model_preferred")
        )
        allowed = _string_tuple(self.model_allowed, "model_allowed")
        if self.model_preferred not in allowed:
            raise ProtocolValidationError(
                "PREFERRED_MODEL_NOT_ALLOWED", "model_allowed", self.model_preferred
            )
        object.__setattr__(self, "model_allowed", allowed)
        object.__setattr__(self, "gate_class", _enum(GateClass, self.gate_class, "gate_class"))

        capabilities: list[Capability] = []
        for raw in self.capabilities_required:
            try:
                capability = raw if isinstance(raw, Capability) else Capability(raw)
            except (TypeError, ValueError) as exc:
                raise ProtocolValidationError(
                    "UNKNOWN_CAPABILITY", "capabilities_required", repr(raw)
                ) from exc
            if capability in PROTECTED_CAPABILITIES:
                raise ProtocolValidationError(
                    "PROTECTED_CAPABILITY_REQUEST",
                    "capabilities_required",
                    capability.value,
                )
            capabilities.append(capability)
        if not capabilities:
            raise ProtocolValidationError(
                "EMPTY_CRITICAL_FIELD",
                "capabilities_required",
                "at least one capability required",
            )
        object.__setattr__(
            self,
            "capabilities_required",
            tuple(sorted(set(capabilities), key=lambda item: item.value)),
        )
        object.__setattr__(
            self, "scope_paths", _string_tuple(self.scope_paths, "scope_paths")
        )
        object.__setattr__(
            self,
            "scope_non_goals",
            _string_tuple(self.scope_non_goals, "scope_non_goals"),
        )
        if not isinstance(self.manual_update_required, bool):
            raise ProtocolValidationError(
                "INVALID_BOOLEAN",
                "manual_update_required",
                repr(self.manual_update_required),
            )

    @classmethod
    def from_manifest(cls, manifest: TaskManifest) -> "TaskEnvelope":
        return cls(
            task_id=manifest.task_id,
            parent_task_id=manifest.parent_task_id,
            baseline_sha=manifest.baseline_sha,
            integration_branch=manifest.integration_branch,
            task_branch=manifest.task_branch,
            model_preferred=manifest.model_policy.preferred,
            model_allowed=manifest.model_policy.allowed,
            gate_class=manifest.gate_class,
            capabilities_required=manifest.capabilities_required,
            scope_paths=manifest.scope.paths,
            scope_non_goals=manifest.scope.non_goals,
            manual_update_required=manifest.manual_update_required,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskEnvelope":
        return cls(
            task_id=data.get("task_id"),
            parent_task_id=data.get("parent_task_id"),
            baseline_sha=data.get("baseline_sha"),
            integration_branch=data.get("integration_branch"),
            task_branch=data.get("task_branch"),
            model_preferred=data.get("model_preferred"),
            model_allowed=tuple(data.get("model_allowed", ())),
            gate_class=data.get("gate_class"),
            capabilities_required=tuple(data.get("capabilities_required", ())),
            scope_paths=tuple(data.get("scope_paths", ())),
            scope_non_goals=tuple(data.get("scope_non_goals", ())),
            manual_update_required=data.get("manual_update_required"),
        )


@dataclass(frozen=True, slots=True)
class CanonicalDocumentation(ProtocolMixin):
    manual_updated: bool
    sections: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.manual_updated, bool):
            raise ProtocolValidationError("INVALID_BOOLEAN", "canonical_documentation.manual_updated", repr(self.manual_updated))
        sections = _string_tuple(
            self.sections, "canonical_documentation.sections", allow_empty=not self.manual_updated
        )
        if self.manual_updated and not sections:
            raise ProtocolValidationError(
                "MISSING_MANUAL_SECTIONS", "canonical_documentation.sections", "manual_updated is true"
            )
        object.__setattr__(self, "sections", sections)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CanonicalDocumentation":
        return cls(manual_updated=data.get("manual_updated"), sections=tuple(data.get("sections", ())))


@dataclass(frozen=True, slots=True)
class ReviewSet(ProtocolMixin):
    baseline_sha: str
    head_sha: str
    changed_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_sha", _sha(self.baseline_sha, "review_set.baseline_sha"))
        object.__setattr__(self, "head_sha", _sha(self.head_sha, "review_set.head_sha"))
        object.__setattr__(self, "changed_paths", _string_tuple(self.changed_paths, "review_set.changed_paths"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReviewSet":
        return cls(
            baseline_sha=data.get("baseline_sha"),
            head_sha=data.get("head_sha"),
            changed_paths=tuple(data.get("changed_paths", ())),
        )


@dataclass(frozen=True, slots=True)
class TestRecord(ProtocolMixin):
    command: str
    status: TestStatus

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _nonempty(self.command, "tests.command"))
        object.__setattr__(self, "status", _enum(TestStatus, self.status, "tests.status"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TestRecord":
        return cls(command=data.get("command"), status=data.get("status"))


@dataclass(frozen=True, slots=True)
class PolicyAssertions(ProtocolMixin):
    usb_open_count: int
    sudo_used: bool
    protected_material_accessed: bool
    main_modified: bool

    def __post_init__(self) -> None:
        if not isinstance(self.usb_open_count, int) or isinstance(self.usb_open_count, bool) or self.usb_open_count < 0:
            raise ProtocolValidationError("INVALID_COUNT", "policy_assertions.usb_open_count", repr(self.usb_open_count))
        for field_name in ("sudo_used", "protected_material_accessed", "main_modified"):
            if not isinstance(getattr(self, field_name), bool):
                raise ProtocolValidationError("INVALID_BOOLEAN", f"policy_assertions.{field_name}", repr(getattr(self, field_name)))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PolicyAssertions":
        return cls(
            usb_open_count=data.get("usb_open_count"),
            sudo_used=data.get("sudo_used"),
            protected_material_accessed=data.get("protected_material_accessed"),
            main_modified=data.get("main_modified"),
        )


@dataclass(frozen=True, slots=True)
class ExecutorResult(ProtocolMixin):
    protocol_version: str
    task_id: str
    outcome: ExecutorOutcome
    advancement: str
    executable_closure: ExecutableClosure
    residual_blocker_or_risk: str
    canonical_documentation: CanonicalDocumentation
    review_set: ReviewSet
    tests: tuple[TestRecord, ...]
    policy_assertions: PolicyAssertions

    def __post_init__(self) -> None:
        object.__setattr__(self, "protocol_version", _protocol_version(self.protocol_version))
        object.__setattr__(self, "task_id", _task_id(self.task_id))
        object.__setattr__(self, "outcome", _enum(ExecutorOutcome, self.outcome, "outcome"))
        object.__setattr__(self, "advancement", _nonempty(self.advancement, "advancement"))
        object.__setattr__(self, "executable_closure", _enum(ExecutableClosure, self.executable_closure, "executable_closure"))
        object.__setattr__(self, "residual_blocker_or_risk", _nonempty(self.residual_blocker_or_risk, "residual_blocker_or_risk"))
        if not isinstance(self.canonical_documentation, CanonicalDocumentation):
            raise ProtocolValidationError("INVALID_OBJECT", "canonical_documentation", repr(self.canonical_documentation))
        if not isinstance(self.review_set, ReviewSet):
            raise ProtocolValidationError("INVALID_OBJECT", "review_set", repr(self.review_set))
        if not self.tests or any(not isinstance(item, TestRecord) for item in self.tests):
            raise ProtocolValidationError("INVALID_TESTS", "tests", "at least one validated test record required")
        if not isinstance(self.policy_assertions, PolicyAssertions):
            raise ProtocolValidationError("INVALID_OBJECT", "policy_assertions", repr(self.policy_assertions))
        object.__setattr__(self, "tests", tuple(self.tests))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutorResult":
        return cls(
            protocol_version=data.get("protocol_version"),
            task_id=data.get("task_id"),
            outcome=data.get("outcome"),
            advancement=data.get("advancement"),
            executable_closure=data.get("executable_closure"),
            residual_blocker_or_risk=data.get("residual_blocker_or_risk"),
            canonical_documentation=CanonicalDocumentation.from_dict(data.get("canonical_documentation", {})),
            review_set=ReviewSet.from_dict(data.get("review_set", {})),
            tests=tuple(TestRecord.from_dict(item) for item in data.get("tests", ())),
            policy_assertions=PolicyAssertions.from_dict(data.get("policy_assertions", {})),
        )


@dataclass(frozen=True, slots=True)
class HumanGateManifest(ProtocolMixin):
    protocol_version: str
    gate_id: str
    task_id: str
    decision_required: str
    reason: str
    commit_sha: str | None
    action_to_unlock: str
    residual_risks: tuple[str, ...]
    still_forbidden: tuple[str, ...]
    requested_by: GateRequester
    status: GateStatus
    approval_state: OrchestratorState
    denial_state: OrchestratorState

    def __post_init__(self) -> None:
        object.__setattr__(self, "protocol_version", _protocol_version(self.protocol_version))
        object.__setattr__(self, "gate_id", _gate_id(self.gate_id))
        object.__setattr__(self, "task_id", _task_id(self.task_id))
        object.__setattr__(self, "decision_required", _nonempty(self.decision_required, "decision_required"))
        object.__setattr__(self, "reason", _nonempty(self.reason, "reason"))
        object.__setattr__(self, "commit_sha", _sha(self.commit_sha, "commit_sha", optional=True))
        object.__setattr__(self, "action_to_unlock", _nonempty(self.action_to_unlock, "action_to_unlock"))
        object.__setattr__(self, "residual_risks", _string_tuple(self.residual_risks, "residual_risks"))
        object.__setattr__(self, "still_forbidden", _string_tuple(self.still_forbidden, "still_forbidden"))
        object.__setattr__(self, "requested_by", _enum(GateRequester, self.requested_by, "requested_by"))
        object.__setattr__(self, "status", _enum(GateStatus, self.status, "status"))
        try:
            approval_state = self.approval_state if isinstance(self.approval_state, OrchestratorState) else OrchestratorState(self.approval_state)
            denial_state = self.denial_state if isinstance(self.denial_state, OrchestratorState) else OrchestratorState(self.denial_state)
        except (TypeError, ValueError) as exc:
            raise ProtocolValidationError("UNKNOWN_GATE_CONTINUATION", "approval_state/denial_state", str(exc)) from exc
        if approval_state not in GATE_CONTINUATION_STATES or denial_state not in {
            OrchestratorState.PM_PLANNING,
            OrchestratorState.DONE,
        }:
            raise ProtocolValidationError(
                "INVALID_GATE_CONTINUATION", "approval_state/denial_state", f"{approval_state}/{denial_state}"
            )
        object.__setattr__(self, "approval_state", approval_state)
        object.__setattr__(self, "denial_state", denial_state)

    def terminal(self, status: GateStatus) -> "HumanGateManifest":
        parsed = _enum(GateStatus, status, "status")
        if self.status is not GateStatus.PENDING:
            raise ProtocolValidationError("TERMINAL_GATE_REPLAY", "status", self.status.value)
        if parsed is GateStatus.PENDING:
            raise ProtocolValidationError("INVALID_GATE_DECISION", "status", parsed.value)
        return replace(self, status=parsed)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HumanGateManifest":
        return cls(
            protocol_version=data.get("protocol_version"),
            gate_id=data.get("gate_id"),
            task_id=data.get("task_id"),
            decision_required=data.get("decision_required"),
            reason=data.get("reason"),
            commit_sha=data.get("commit_sha"),
            action_to_unlock=data.get("action_to_unlock"),
            residual_risks=tuple(data.get("residual_risks", ())),
            still_forbidden=tuple(data.get("still_forbidden", ())),
            requested_by=data.get("requested_by"),
            status=data.get("status"),
            approval_state=data.get("approval_state"),
            denial_state=data.get("denial_state"),
        )


@dataclass(frozen=True, slots=True)
class PMDisposition(ProtocolMixin):
    protocol_version: str
    task_id: str
    disposition: Disposition
    reason: str
    reviewed_head_sha: str | None = None
    findings: tuple[str, ...] = ()
    accept_target: OrchestratorState | None = None
    gate: HumanGateManifest | None = None
    pause_reason: PauseReason | None = None
    next_task_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "protocol_version", _protocol_version(self.protocol_version))
        object.__setattr__(self, "task_id", _task_id(self.task_id))
        disposition = _enum(Disposition, self.disposition, "disposition")
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "reason", _nonempty(self.reason, "reason"))
        object.__setattr__(self, "reviewed_head_sha", _sha(self.reviewed_head_sha, "reviewed_head_sha", optional=True))
        object.__setattr__(self, "findings", _string_tuple(self.findings, "findings", allow_empty=True))
        object.__setattr__(self, "next_task_id", _task_id(self.next_task_id, "next_task_id", optional=True))

        accept_target = self.accept_target
        if accept_target is not None:
            try:
                accept_target = accept_target if isinstance(accept_target, OrchestratorState) else OrchestratorState(accept_target)
            except (TypeError, ValueError) as exc:
                raise ProtocolValidationError("UNKNOWN_ACCEPT_TARGET", "accept_target", repr(self.accept_target)) from exc
        object.__setattr__(self, "accept_target", accept_target)

        pause_reason = self.pause_reason
        if pause_reason is not None:
            pause_reason = _enum(PauseReason, pause_reason, "pause_reason")
        object.__setattr__(self, "pause_reason", pause_reason)

        if disposition is Disposition.ACCEPT:
            if self.reviewed_head_sha is None:
                raise ProtocolValidationError("ACCEPT_REQUIRES_REVIEWED_SHA", "reviewed_head_sha", "missing")
            if accept_target not in {OrchestratorState.PM_PLANNING, OrchestratorState.DONE}:
                raise ProtocolValidationError("ACCEPT_REQUIRES_TARGET", "accept_target", repr(accept_target))
            if accept_target is OrchestratorState.PM_PLANNING and self.next_task_id is None:
                raise ProtocolValidationError("ACCEPT_NEXT_REQUIRES_TASK", "next_task_id", "missing")
            if accept_target is OrchestratorState.DONE and self.next_task_id is not None:
                raise ProtocolValidationError("DONE_TARGET_FORBIDS_NEXT_TASK", "next_task_id", self.next_task_id)
        elif self.reviewed_head_sha is not None or accept_target is not None:
            raise ProtocolValidationError("UNEXPECTED_ACCEPT_FIELDS", "reviewed_head_sha/accept_target", disposition.value)

        if disposition is Disposition.HUMAN_GATE:
            if not isinstance(self.gate, HumanGateManifest) or self.gate.status is not GateStatus.PENDING:
                raise ProtocolValidationError("HUMAN_GATE_REQUIRES_PENDING_MANIFEST", "gate", repr(self.gate))
            if self.gate.task_id != self.task_id:
                raise ProtocolValidationError("TASK_ID_MISMATCH", "gate.task_id", self.gate.task_id)
        elif self.gate is not None:
            raise ProtocolValidationError("UNEXPECTED_GATE", "gate", disposition.value)

        if disposition is Disposition.PAUSE:
            if pause_reason is None:
                raise ProtocolValidationError("PAUSE_REQUIRES_CLASSIFICATION", "pause_reason", "missing")
        elif pause_reason is not None:
            raise ProtocolValidationError("UNEXPECTED_PAUSE_REASON", "pause_reason", disposition.value)

        if disposition is Disposition.DONE and self.next_task_id is not None:
            raise ProtocolValidationError("DONE_FORBIDS_NEXT_TASK", "next_task_id", self.next_task_id)
        if disposition not in {Disposition.ACCEPT, Disposition.DONE} and self.next_task_id is not None:
            raise ProtocolValidationError("UNEXPECTED_NEXT_TASK", "next_task_id", disposition.value)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PMDisposition":
        gate_data = data.get("gate")
        return cls(
            protocol_version=data.get("protocol_version"),
            task_id=data.get("task_id"),
            disposition=data.get("disposition"),
            reason=data.get("reason"),
            reviewed_head_sha=data.get("reviewed_head_sha"),
            findings=tuple(data.get("findings", ())),
            accept_target=data.get("accept_target"),
            gate=HumanGateManifest.from_dict(gate_data) if gate_data else None,
            pause_reason=data.get("pause_reason"),
            next_task_id=data.get("next_task_id"),
        )
