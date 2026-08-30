# SPDX-License-Identifier: GPL-2.0-or-later
"""Strict O002 control wrappers and deterministic model routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .protocols import (
    CanonicalDocumentation,
    Disposition,
    ExecutableClosure,
    ExecutorOutcome,
    PMDisposition,
    PolicyAssertions,
    ProtocolMixin,
    ProtocolValidationError,
    TaskManifest,
    TestRecord,
)


class ContextClass(StrEnum):
    AI_PM_PLAN = "AI_PM_PLAN"
    AI_PM_REVIEW = "AI_PM_REVIEW"
    AI_EXECUTOR = "AI_EXECUTOR"


class PMPlanningClass(StrEnum):
    STANDARD = "STANDARD"
    ESCALATED = "ESCALATED"


class ExecutionClass(StrEnum):
    MECHANICAL = "MECHANICAL"
    LOCAL_CORRECTIVE = "LOCAL_CORRECTIVE"
    BOUNDED_IMPLEMENTATION = "BOUNDED_IMPLEMENTATION"
    ARCHITECTURAL_OR_HIGH_RISK = "ARCHITECTURAL_OR_HIGH_RISK"


class RoutingClass(StrEnum):
    AI_PM_PLAN_STANDARD = "AI_PM_PLAN_STANDARD"
    AI_PM_PLAN_ESCALATED = "AI_PM_PLAN_ESCALATED"
    AI_PM_REVIEW = "AI_PM_REVIEW"
    EXEC_MECHANICAL = "EXEC_MECHANICAL"
    EXEC_LOCAL_CORRECTIVE = "EXEC_LOCAL_CORRECTIVE"
    EXEC_BOUNDED_IMPLEMENTATION = "EXEC_BOUNDED_IMPLEMENTATION"
    EXEC_ARCHITECTURAL_OR_HIGH_RISK = "EXEC_ARCHITECTURAL_OR_HIGH_RISK"


@dataclass(frozen=True, slots=True)
class ModelRoute(ProtocolMixin):
    routing_class: RoutingClass
    context_class: ContextClass
    model_id: str
    reasoning_effort: str


_ROUTES: dict[RoutingClass, ModelRoute] = {
    RoutingClass.AI_PM_PLAN_STANDARD: ModelRoute(
        RoutingClass.AI_PM_PLAN_STANDARD,
        ContextClass.AI_PM_PLAN,
        "gpt-5.6-sol",
        "medium",
    ),
    RoutingClass.AI_PM_PLAN_ESCALATED: ModelRoute(
        RoutingClass.AI_PM_PLAN_ESCALATED,
        ContextClass.AI_PM_PLAN,
        "gpt-5.6-sol",
        "high",
    ),
    RoutingClass.AI_PM_REVIEW: ModelRoute(
        RoutingClass.AI_PM_REVIEW,
        ContextClass.AI_PM_REVIEW,
        "gpt-5.6-sol",
        "high",
    ),
    RoutingClass.EXEC_MECHANICAL: ModelRoute(
        RoutingClass.EXEC_MECHANICAL,
        ContextClass.AI_EXECUTOR,
        "gpt-5.6-luna",
        "medium",
    ),
    RoutingClass.EXEC_LOCAL_CORRECTIVE: ModelRoute(
        RoutingClass.EXEC_LOCAL_CORRECTIVE,
        ContextClass.AI_EXECUTOR,
        "gpt-5.6-terra",
        "medium",
    ),
    RoutingClass.EXEC_BOUNDED_IMPLEMENTATION: ModelRoute(
        RoutingClass.EXEC_BOUNDED_IMPLEMENTATION,
        ContextClass.AI_EXECUTOR,
        "gpt-5.6-terra",
        "high",
    ),
    RoutingClass.EXEC_ARCHITECTURAL_OR_HIGH_RISK: ModelRoute(
        RoutingClass.EXEC_ARCHITECTURAL_OR_HIGH_RISK,
        ContextClass.AI_EXECUTOR,
        "gpt-5.6-sol",
        "high",
    ),
}


_EXECUTION_TO_ROUTING = {
    ExecutionClass.MECHANICAL: RoutingClass.EXEC_MECHANICAL,
    ExecutionClass.LOCAL_CORRECTIVE: RoutingClass.EXEC_LOCAL_CORRECTIVE,
    ExecutionClass.BOUNDED_IMPLEMENTATION: RoutingClass.EXEC_BOUNDED_IMPLEMENTATION,
    ExecutionClass.ARCHITECTURAL_OR_HIGH_RISK: RoutingClass.EXEC_ARCHITECTURAL_OR_HIGH_RISK,
}

_PLANNING_TO_ROUTING = {
    PMPlanningClass.STANDARD: RoutingClass.AI_PM_PLAN_STANDARD,
    PMPlanningClass.ESCALATED: RoutingClass.AI_PM_PLAN_ESCALATED,
}


def _strict_keys(data: Mapping[str, Any], expected: set[str], contract: str) -> None:
    unknown = set(data) - expected
    missing = expected - set(data)
    if unknown:
        raw_override = unknown & {"model", "model_id", "effort", "reasoning_effort"}
        code = "RAW_ROUTING_OVERRIDE_DENIED" if raw_override else "UNKNOWN_CONTROL_FIELD"
        raise ProtocolValidationError(code, contract, ",".join(sorted(unknown)))
    if missing:
        raise ProtocolValidationError(
            "MISSING_CONTROL_FIELD", contract, ",".join(sorted(missing))
        )


def _optional_enum(enum_type: type[StrEnum], value: Any, field: str) -> StrEnum | None:
    if value is None:
        return None
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolValidationError("UNKNOWN_ROUTING_CLASS", field, repr(value)) from exc


class ModelRouter:
    """Closed, auditable O002 routing table. No aliases or fallback exist."""

    @staticmethod
    def planning(planning_class: PMPlanningClass | str) -> ModelRoute:
        try:
            parsed = (
                planning_class
                if isinstance(planning_class, PMPlanningClass)
                else PMPlanningClass(planning_class)
            )
        except (TypeError, ValueError) as exc:
            raise ProtocolValidationError(
                "UNKNOWN_ROUTING_CLASS", "planning_class", repr(planning_class)
            ) from exc
        return _ROUTES[_PLANNING_TO_ROUTING[parsed]]

    @staticmethod
    def review() -> ModelRoute:
        return _ROUTES[RoutingClass.AI_PM_REVIEW]

    @staticmethod
    def execution(execution_class: ExecutionClass | str) -> ModelRoute:
        try:
            parsed = (
                execution_class
                if isinstance(execution_class, ExecutionClass)
                else ExecutionClass(execution_class)
            )
        except (TypeError, ValueError) as exc:
            raise ProtocolValidationError(
                "UNKNOWN_ROUTING_CLASS", "execution_class", repr(execution_class)
            ) from exc
        return _ROUTES[_EXECUTION_TO_ROUTING[parsed]]

    @staticmethod
    def require_catalog(route: ModelRoute, models: Mapping[str, set[str]]) -> None:
        if route.reasoning_effort in {"none", "low", "xhigh", "max"}:
            raise ProtocolValidationError(
                "AUTONOMOUS_EFFORT_DENIED", "reasoning_effort", route.reasoning_effort
            )
        efforts = models.get(route.model_id)
        if efforts is None or route.reasoning_effort not in efforts:
            raise ProtocolValidationError(
                "MODEL_UNAVAILABLE",
                "model/list",
                f"{route.model_id}/{route.reasoning_effort}",
            )

    @staticmethod
    def verify_effective(
        route: ModelRoute, effective_model: Any, effective_effort: Any
    ) -> None:
        if effective_model != route.model_id:
            raise ProtocolValidationError(
                "MODEL_ROUTING_MISMATCH",
                "effective_model_id",
                f"requested={route.model_id},effective={effective_model!r}",
            )
        if effective_effort != route.reasoning_effort:
            raise ProtocolValidationError(
                "MODEL_ROUTING_MISMATCH",
                "effective_reasoning_effort",
                f"requested={route.reasoning_effort},effective={effective_effort!r}",
            )


@dataclass(frozen=True, slots=True)
class PMPlanningOutput(ProtocolMixin):
    task_manifest: TaskManifest
    execution_class: ExecutionClass

    def __post_init__(self) -> None:
        if not isinstance(self.task_manifest, TaskManifest):
            raise ProtocolValidationError(
                "INVALID_OBJECT", "task_manifest", repr(self.task_manifest)
            )
        try:
            parsed = (
                self.execution_class
                if isinstance(self.execution_class, ExecutionClass)
                else ExecutionClass(self.execution_class)
            )
        except (TypeError, ValueError) as exc:
            raise ProtocolValidationError(
                "UNKNOWN_ROUTING_CLASS", "execution_class", repr(self.execution_class)
            ) from exc
        route = ModelRouter.execution(parsed)
        policy = self.task_manifest.model_policy
        if route.model_id not in policy.allowed or policy.preferred != route.model_id:
            raise ProtocolValidationError(
                "ROUTE_OUTSIDE_TASK_MODEL_POLICY",
                "task_manifest.model_policy",
                f"{route.model_id}/{route.reasoning_effort}",
            )
        object.__setattr__(self, "execution_class", parsed)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PMPlanningOutput":
        _strict_keys(data, {"task_manifest", "execution_class"}, "PMPlanningOutput")
        manifest_data = data["task_manifest"]
        if not isinstance(manifest_data, Mapping):
            raise ProtocolValidationError(
                "INVALID_OBJECT", "task_manifest", repr(manifest_data)
            )
        return cls(TaskManifest.from_dict(manifest_data), data["execution_class"])


@dataclass(frozen=True, slots=True)
class PMReviewOutput(ProtocolMixin):
    disposition: PMDisposition
    corrective_execution_class: ExecutionClass | None
    replan_planning_class: PMPlanningClass | None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, PMDisposition):
            raise ProtocolValidationError(
                "INVALID_OBJECT", "disposition", repr(self.disposition)
            )
        corrective = _optional_enum(
            ExecutionClass, self.corrective_execution_class, "corrective_execution_class"
        )
        replan = _optional_enum(
            PMPlanningClass, self.replan_planning_class, "replan_planning_class"
        )
        if self.disposition.disposition is Disposition.CORRECTIVE:
            if corrective is None or replan is not None:
                raise ProtocolValidationError(
                    "CORRECTIVE_ROUTING_FIELDS_INVALID",
                    "corrective_execution_class",
                    repr((corrective, replan)),
                )
        elif self.disposition.disposition is Disposition.REPLAN:
            if replan is None or corrective is not None:
                raise ProtocolValidationError(
                    "REPLAN_ROUTING_FIELDS_INVALID",
                    "replan_planning_class",
                    repr((corrective, replan)),
                )
        elif corrective is not None or replan is not None:
            raise ProtocolValidationError(
                "UNEXPECTED_ROUTING_OVERRIDE",
                "corrective_execution_class/replan_planning_class",
                self.disposition.disposition.value,
            )
        object.__setattr__(self, "corrective_execution_class", corrective)
        object.__setattr__(self, "replan_planning_class", replan)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PMReviewOutput":
        _strict_keys(
            data,
            {
                "disposition",
                "corrective_execution_class",
                "replan_planning_class",
            },
            "PMReviewOutput",
        )
        disposition_data = data["disposition"]
        if not isinstance(disposition_data, Mapping):
            raise ProtocolValidationError(
                "INVALID_OBJECT", "disposition", repr(disposition_data)
            )
        return cls(
            PMDisposition.from_dict(disposition_data),
            data["corrective_execution_class"],
            data["replan_planning_class"],
        )


@dataclass(frozen=True, slots=True)
class ExecutorWorkReport(ProtocolMixin):
    task_id: str
    outcome: ExecutorOutcome
    advancement: str
    executable_closure: ExecutableClosure
    residual_blocker_or_risk: str
    canonical_documentation: CanonicalDocumentation
    tests: tuple[TestRecord, ...]
    policy_assertions: PolicyAssertions

    def __post_init__(self) -> None:
        # Reuse the canonical validators without inventing Git facts.
        if not isinstance(self.task_id, str) or not self.task_id.startswith("TASK-"):
            raise ProtocolValidationError("MALFORMED_TASK_ID", "task_id", repr(self.task_id))
        try:
            outcome = (
                self.outcome
                if isinstance(self.outcome, ExecutorOutcome)
                else ExecutorOutcome(self.outcome)
            )
            closure = (
                self.executable_closure
                if isinstance(self.executable_closure, ExecutableClosure)
                else ExecutableClosure(self.executable_closure)
            )
        except (TypeError, ValueError) as exc:
            raise ProtocolValidationError(
                "UNKNOWN_ENUM_VALUE", "outcome/executable_closure", str(exc)
            ) from exc
        if not isinstance(self.advancement, str) or not self.advancement.strip():
            raise ProtocolValidationError("EMPTY_CRITICAL_FIELD", "advancement", repr(self.advancement))
        if not isinstance(self.residual_blocker_or_risk, str) or not self.residual_blocker_or_risk.strip():
            raise ProtocolValidationError(
                "EMPTY_CRITICAL_FIELD",
                "residual_blocker_or_risk",
                repr(self.residual_blocker_or_risk),
            )
        if not isinstance(self.canonical_documentation, CanonicalDocumentation):
            raise ProtocolValidationError(
                "INVALID_OBJECT", "canonical_documentation", repr(self.canonical_documentation)
            )
        if not self.tests or any(not isinstance(item, TestRecord) for item in self.tests):
            raise ProtocolValidationError("INVALID_TESTS", "tests", "validated tests required")
        if not isinstance(self.policy_assertions, PolicyAssertions):
            raise ProtocolValidationError(
                "INVALID_OBJECT", "policy_assertions", repr(self.policy_assertions)
            )
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "executable_closure", closure)
        object.__setattr__(self, "tests", tuple(self.tests))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutorWorkReport":
        expected = {
            "task_id",
            "outcome",
            "advancement",
            "executable_closure",
            "residual_blocker_or_risk",
            "canonical_documentation",
            "tests",
            "policy_assertions",
        }
        _strict_keys(data, expected, "ExecutorWorkReport")
        for forbidden in (
            "baseline_sha",
            "head_sha",
            "changed_paths",
            "integration_sha",
            "effective_model_id",
            "effective_reasoning_effort",
        ):
            if forbidden in data:
                raise ProtocolValidationError(
                    "MODEL_GIT_FACT_DENIED", forbidden, "deterministic fact"
                )
        return cls(
            task_id=data["task_id"],
            outcome=data["outcome"],
            advancement=data["advancement"],
            executable_closure=data["executable_closure"],
            residual_blocker_or_risk=data["residual_blocker_or_risk"],
            canonical_documentation=CanonicalDocumentation.from_dict(
                data["canonical_documentation"]
            ),
            tests=tuple(TestRecord.from_dict(item) for item in data["tests"]),
            policy_assertions=PolicyAssertions.from_dict(data["policy_assertions"]),
        )
