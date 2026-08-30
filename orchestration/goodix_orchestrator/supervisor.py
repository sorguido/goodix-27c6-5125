# SPDX-License-Identifier: GPL-2.0-or-later
"""O002 coordinator around the authoritative O001 deterministic engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .engine import DeterministicEngine, EngineError
from .git_manager import (
    CommitResult,
    GitManager,
    GitManagerError,
    SyntheticRepository,
    TaskWorktree,
)
from .persistence import DispatchRecord, GitStateRecord, PersistenceError
from .protocols import (
    ExecutorResult,
    PolicyAssertions,
    ReviewSet,
    TestRecord,
    TestStatus,
)
from .state import OrchestratorState
from .structured_output import (
    ExecutionClass,
    ExecutorWorkReport,
    ModelRouter,
    PMPlanningOutput,
    PMReviewOutput,
)
from .synthetic_verifier import (
    SyntheticVerification,
    SyntheticVerificationError,
    SyntheticVerifier,
    VerificationProfile,
)


MAX_REVIEW_PAYLOAD_BYTES = 768 * 1024
MAX_MANUAL_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class SupervisorError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ReviewEvidence:
    task_manifest: dict[str, Any]
    executor_result: dict[str, Any]
    actual_baseline_sha: str
    actual_head_sha: str
    changed_paths: tuple[str, ...]
    unified_diff: str
    measured_test: dict[str, Any]
    project_manual: str
    policy_assertions_verified: bool
    current_integration_sha: str
    executor_routing: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        # Deliberately no planner prompt, free-form conversation, or history.
        return {
            "task_manifest": self.task_manifest,
            "executor_result": self.executor_result,
            "actual_baseline_sha": self.actual_baseline_sha,
            "actual_head_sha": self.actual_head_sha,
            "changed_paths": list(self.changed_paths),
            "unified_diff": self.unified_diff,
            "measured_test": self.measured_test,
            "project_manual": self.project_manual,
            "policy_assertions_verified": self.policy_assertions_verified,
            "current_integration_sha": self.current_integration_sha,
            "executor_routing": self.executor_routing,
        }


class O002Supervisor:
    def __init__(
        self,
        *,
        engine: DeterministicEngine,
        git_manager: GitManager,
        repository: SyntheticRepository,
        synthetic_verifier: SyntheticVerifier | None = None,
    ) -> None:
        self.engine = engine
        self.git_manager = git_manager
        self.repository = repository
        self.synthetic_verifier = synthetic_verifier or SyntheticVerifier()
        self.current_plan: PMPlanningOutput | None = None
        self.current_worktree: TaskWorktree | None = None
        self.current_result: ExecutorResult | None = None
        self.current_test: SyntheticVerification | None = None
        self.current_executor_dispatch_id: str | None = None

    def bootstrap(self) -> OrchestratorState:
        if self.engine.state is OrchestratorState.BOOTSTRAP:
            self.engine.bootstrap_complete()
        if self.engine.state is OrchestratorState.IDLE:
            self.engine.start_planning()
        if self.engine.state is not OrchestratorState.PM_PLANNING:
            raise SupervisorError("SUPERVISOR_STATE_MISMATCH", self.engine.state.value)
        self.engine.store.save_git_state(
            GitStateRecord(
                self.repository.integration_branch,
                self.repository.integration_sha,
                None,
            )
        )
        return self.engine.state

    def accept_plan(
        self,
        planning: PMPlanningOutput,
        *,
        worktree_path: str | Path,
        branch_effect_id: str,
    ) -> TaskWorktree:
        if self.engine.state is not OrchestratorState.PM_PLANNING:
            raise SupervisorError("PLAN_STATE_MISMATCH", self.engine.state.value)
        manifest = planning.task_manifest
        route = ModelRouter.execution(planning.execution_class)
        if route.model_id not in manifest.model_policy.allowed:
            raise SupervisorError("ROUTE_OUTSIDE_TASK_MODEL_POLICY", route.model_id)
        actual_integration = self.git_manager._text(
            self.repository.root,
            ("rev-parse", f"refs/heads/{self.repository.integration_branch}"),
        )
        if manifest.baseline_sha != actual_integration:
            raise SupervisorError(
                "PLAN_BASELINE_MISMATCH",
                f"manifest={manifest.baseline_sha},integration={actual_integration}",
            )
        self.engine.task_ready(manifest)
        worktree = self.git_manager.create_task_worktree(
            self.repository,
            task_id=manifest.task_id,
            task_branch=manifest.task_branch,
            worktree_path=worktree_path,
            expected_integration_sha=actual_integration,
            effect_id=branch_effect_id,
        )
        self.current_plan = planning
        self.current_worktree = worktree
        self.current_result = None
        self.current_test = None
        self.current_executor_dispatch_id = None
        self.engine.store.save_git_state(
            GitStateRecord(
                self.repository.integration_branch,
                actual_integration,
                str(worktree.root),
            )
        )
        return worktree

    def start_executor(self, turn_id: str) -> None:
        if self.current_plan is None or self.current_worktree is None:
            raise SupervisorError("NO_CURRENT_TASK", turn_id)
        self.engine.start_executor(turn_id=turn_id)

    def _verified_executor_dispatch(
        self,
        dispatch_id: str,
        expected_execution_class: ExecutionClass,
    ) -> DispatchRecord:
        try:
            dispatch = self.engine.store.load_dispatch(dispatch_id)
            context = self.engine.store.load_context(dispatch.thread_id)
        except PersistenceError as exc:
            raise SupervisorError(
                "EXECUTOR_DISPATCH_EVIDENCE_UNAVAILABLE", dispatch_id
            ) from exc
        expected_routing = ModelRouter.execution(expected_execution_class).routing_class
        if (
            dispatch.context_class.value != "AI_EXECUTOR"
            or dispatch.routing_class is not expected_routing
            or context.context_class is not dispatch.context_class
            or context.thread_id != dispatch.thread_id
            or context.routing_class is not dispatch.routing_class
            or context.effective_model_id != dispatch.effective_model_id
            or context.effective_reasoning_effort
            != dispatch.effective_reasoning_effort
            or context.codex_version != dispatch.codex_version
            or not context.active
        ):
            raise SupervisorError(
                "EXECUTOR_DISPATCH_EVIDENCE_MISMATCH", dispatch_id
            )
        return dispatch

    def materialize_executor_result(
        self,
        work_report: ExecutorWorkReport,
        *,
        expected_parent_sha: str,
        commit_effect_id: str,
        executor_dispatch_id: str,
        expected_execution_class: ExecutionClass,
        verification_profile: VerificationProfile,
    ) -> ExecutorResult:
        if self.engine.state is not OrchestratorState.EXECUTOR_RUNNING:
            raise SupervisorError("EXECUTOR_STATE_MISMATCH", self.engine.state.value)
        if self.current_plan is None or self.current_worktree is None:
            raise SupervisorError("NO_CURRENT_TASK", work_report.task_id)
        manifest = self.current_plan.task_manifest
        if work_report.task_id != manifest.task_id:
            self.engine.fail_closed(
                "TASK_ID_MISMATCH",
                f"manifest={manifest.task_id},work={work_report.task_id}",
            )
        assertions = work_report.policy_assertions
        if assertions != PolicyAssertions(0, False, False, False):
            self.engine.fail_closed(
                "EXECUTOR_POLICY_ASSERTION_VIOLATION", repr(assertions.to_dict())
            )
        dispatch = self._verified_executor_dispatch(
            executor_dispatch_id, expected_execution_class
        )
        commit = self.git_manager.commit_task(
            self.current_worktree,
            manifest,
            expected_parent_sha=expected_parent_sha,
            effect_id=commit_effect_id,
        )
        try:
            measured = self.synthetic_verifier.verify(
                self.current_worktree.root, verification_profile
            )
        except SyntheticVerificationError as exc:
            raise SupervisorError(exc.code, exc.detail) from exc
        changed_from_task_baseline = tuple(
            path
            for path in self.git_manager._text(
                self.current_worktree.root,
                ("diff", "--name-only", manifest.baseline_sha, commit.head_sha),
            ).splitlines()
            if path
        )
        result = ExecutorResult(
            protocol_version="1.0",
            task_id=manifest.task_id,
            outcome=work_report.outcome,
            advancement=work_report.advancement,
            executable_closure=work_report.executable_closure,
            residual_blocker_or_risk=work_report.residual_blocker_or_risk,
            canonical_documentation=work_report.canonical_documentation,
            review_set=ReviewSet(
                manifest.baseline_sha,
                commit.head_sha,
                tuple(sorted(changed_from_task_baseline)),
            ),
            tests=(TestRecord(measured.command, measured.status),),
            policy_assertions=assertions,
        )
        self.engine.complete_executor(result)
        self.current_result = result
        self.current_test = measured
        self.current_executor_dispatch_id = dispatch.dispatch_id
        return result

    def start_review(self, turn_id: str) -> ReviewEvidence:
        if self.current_result is None or self.current_plan is None or self.current_worktree is None:
            raise SupervisorError("NO_EXECUTOR_RESULT", turn_id)
        self.engine.start_review(turn_id=turn_id)
        manifest = self.current_plan.task_manifest
        result = self.current_result
        measured = self.current_test
        assert measured is not None
        if self.current_executor_dispatch_id is None:
            raise SupervisorError("EXECUTOR_DISPATCH_EVIDENCE_UNAVAILABLE", turn_id)
        try:
            dispatch = self.engine.store.load_dispatch(
                self.current_executor_dispatch_id
            )
            context = self.engine.store.load_context(dispatch.thread_id)
        except PersistenceError as exc:
            raise SupervisorError(
                "EXECUTOR_DISPATCH_EVIDENCE_UNAVAILABLE",
                self.current_executor_dispatch_id,
            ) from exc
        if (
            dispatch.context_class.value != "AI_EXECUTOR"
            or context.context_class is not dispatch.context_class
            or context.routing_class is not dispatch.routing_class
            or context.effective_model_id != dispatch.effective_model_id
            or context.effective_reasoning_effort
            != dispatch.effective_reasoning_effort
            or context.codex_version != dispatch.codex_version
        ):
            raise SupervisorError(
                "EXECUTOR_DISPATCH_EVIDENCE_MISMATCH", dispatch.dispatch_id
            )
        manual_path = self.current_worktree.root / "PROJECT_MANUAL.md"
        manual = manual_path.read_text(encoding="utf-8")
        if len(manual.encode("utf-8")) > MAX_MANUAL_BYTES:
            raise SupervisorError("REVIEW_MANUAL_TOO_LARGE", str(len(manual)))
        diff = self.git_manager.review_diff(
            self.current_worktree.root,
            manifest.baseline_sha,
            result.review_set.head_sha,
        )
        evidence = ReviewEvidence(
            task_manifest=manifest.to_dict(),
            executor_result=result.to_dict(),
            actual_baseline_sha=manifest.baseline_sha,
            actual_head_sha=result.review_set.head_sha,
            changed_paths=result.review_set.changed_paths,
            unified_diff=diff,
            measured_test={
                "command": measured.command,
                "status": measured.status.value,
                "exit_code": measured.exit_code,
                "summary": measured.summary,
            },
            project_manual=manual,
            policy_assertions_verified=True,
            current_integration_sha=self.repository.integration_sha,
            executor_routing={
                "dispatch_id": dispatch.dispatch_id,
                "routing_class": dispatch.routing_class.value,
                "effective_model_id": dispatch.effective_model_id,
                "effective_reasoning_effort": dispatch.effective_reasoning_effort,
                "codex_version": dispatch.codex_version,
                "schema_repair": dispatch.schema_repair,
            },
        )
        encoded = json.dumps(evidence.to_dict(), ensure_ascii=True).encode("utf-8")
        if len(encoded) > MAX_REVIEW_PAYLOAD_BYTES:
            raise SupervisorError("REVIEW_PAYLOAD_TOO_LARGE", str(len(encoded)))
        return evidence

    def apply_review(
        self,
        review: PMReviewOutput,
        *,
        integration_effect_id: str | None = None,
    ) -> OrchestratorState:
        if self.engine.state is not OrchestratorState.PM_REVIEWING:
            raise SupervisorError("REVIEW_STATE_MISMATCH", self.engine.state.value)
        if self.current_plan is None or self.current_result is None:
            raise SupervisorError("NO_CURRENT_REVIEW", review.disposition.task_id)
        disposition = review.disposition
        if disposition.task_id != self.current_plan.task_manifest.task_id:
            self.engine.fail_closed(
                "TASK_ID_MISMATCH",
                f"plan={self.current_plan.task_manifest.task_id},review={disposition.task_id}",
            )
        if disposition.disposition.value == "CORRECTIVE":
            assert review.corrective_execution_class is not None
            route = ModelRouter.execution(review.corrective_execution_class)
            if route.model_id not in self.current_plan.task_manifest.model_policy.allowed:
                raise SupervisorError(
                    "CORRECTIVE_DISPATCH_DENIED", route.model_id
                )
            return self.engine.apply_disposition(disposition)
        if disposition.disposition.value == "ACCEPT":
            if not integration_effect_id:
                raise SupervisorError("INTEGRATION_EFFECT_ID_REQUIRED", disposition.task_id)
            assert disposition.reviewed_head_sha is not None
            old_sha = self.repository.integration_sha
            new_sha = self.git_manager.fast_forward_integration(
                self.repository,
                task_id=disposition.task_id,
                task_branch=self.current_plan.task_manifest.task_branch,
                reviewed_head_sha=disposition.reviewed_head_sha,
                expected_old_sha=old_sha,
                effect_id=integration_effect_id,
            )
            self.repository = replace(self.repository, integration_sha=new_sha)
            self.engine.store.save_git_state(
                GitStateRecord(self.repository.integration_branch, new_sha, None)
            )
            state = self.engine.apply_disposition(disposition)
            if state is OrchestratorState.PM_PLANNING:
                self.current_plan = None
                self.current_worktree = None
                self.current_result = None
                self.current_test = None
                self.current_executor_dispatch_id = None
            return state
        state = self.engine.apply_disposition(disposition)
        if state in {OrchestratorState.PM_PLANNING, OrchestratorState.DONE}:
            self.current_plan = None
            self.current_worktree = None
            self.current_result = None
            self.current_test = None
            self.current_executor_dispatch_id = None
        return state
