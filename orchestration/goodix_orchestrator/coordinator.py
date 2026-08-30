# SPDX-License-Identifier: GPL-2.0-or-later
"""Production-oriented O003 PM -> Executor -> PM service coordinator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .branch_lifecycle import BranchLifecycle, DEVELOPMENT_BRANCH
from .codex_adapter import CodexAppServer, ThreadContext
from .engine import DeterministicEngine
from .gate_adapter import GateAction, HumanGateAdapter
from .git_manager import GitManager, TaskWorktree
from .output_schemas import (
    EXECUTOR_WORK_REPORT_SCHEMA,
    PM_PLANNING_OUTPUT_SCHEMA,
    PM_REVIEW_OUTPUT_SCHEMA,
)
from .persistence import SQLiteStateStore
from .protocols import (
    Disposition,
    ExecutorResult,
    PolicyAssertions,
    ReviewSet,
    TaskManifest,
)
from .state import OrchestratorState
from .structured_output import (
    ExecutionClass,
    ExecutorWorkReport,
    ModelRouter,
    PMPlanningClass,
    PMPlanningOutput,
    PMReviewOutput,
)


@dataclass(frozen=True, slots=True)
class CoordinatorError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


class CoordinatorDriver(Protocol):
    def plan(self, facts: dict[str, Any], planning_class: PMPlanningClass) -> PMPlanningOutput: ...
    def execute(
        self,
        plan: PMPlanningOutput,
        worktree: Path,
        execution_class: ExecutionClass,
        *,
        corrective: bool,
    ) -> ExecutorWorkReport: ...
    def review(self, evidence: dict[str, Any]) -> PMReviewOutput: ...
    def close(self) -> None: ...


class CodexCoordinatorDriver:
    """Three independent App Server contexts with the closed O002 routes."""

    def __init__(
        self,
        store: SQLiteStateStore,
        repository: str | Path,
        *,
        executable: str = "codex",
        timeout: float = 900.0,
    ) -> None:
        self.store = store
        self.repository = Path(repository).resolve(strict=True)
        self.server = CodexAppServer(
            executable,
            process_cwd=self.repository,
            store=store,
            timeout=timeout,
        )
        try:
            self.server.start()
            if self.server.account_mode() != "CHATGPT":
                raise CoordinatorError("AUTH_NOT_CHATGPT", "subscription route required")
        except Exception:
            self.server.close()
            raise
        self._contexts: dict[str, ThreadContext] = {}

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _next_dispatch_id(self, prefix: str) -> str:
        existing = {item.dispatch_id for item in self.store.turn_activities()}
        for attempt in range(1, 10_000):
            candidate = f"{prefix}-{attempt:04d}"
            if candidate not in existing:
                return candidate
        raise CoordinatorError("DISPATCH_ID_SPACE_EXHAUSTED", prefix)

    def _context(self, name: str, route, cwd: Path) -> ThreadContext:
        existing = self._contexts.get(name)
        if existing is not None:
            if existing.cwd != str(cwd.resolve(strict=True)):
                raise CoordinatorError("CONTEXT_CWD_MUTATION_DENIED", name)
            context = self.server.reroute_context(existing, route)
            self._contexts[name] = context
            return context
        persisted = tuple(
            item
            for item in self.store.list_contexts(active_only=True)
            if item.context_class is route.context_class and item.cwd == str(cwd.resolve(strict=True))
        )
        if len(persisted) > 1:
            raise CoordinatorError("CONTEXT_RECONCILIATION_AMBIGUOUS", name)
        context = (
            self.server.resume_thread(persisted[0].thread_id, route, cwd)
            if persisted
            else self.server.start_thread(route, cwd)
        )
        self._contexts[name] = context
        return context

    def plan(self, facts: dict[str, Any], planning_class: PMPlanningClass) -> PMPlanningOutput:
        route = ModelRouter.planning(planning_class)
        context = self._context("plan", route, self.repository)
        prompt = (
            "You are the AI Project Manager. Produce only the bounded host-only task JSON. "
            "Treat CANONICAL_FACTS as authoritative; do not request live, main, sudo, network, "
            "protected material, publication, or history rewrite.\nCANONICAL_FACTS="
            + self._json(facts)
        )
        return self.server.run_structured_turn(
            context,
            prompt,
            output_schema=PM_PLANNING_OUTPUT_SCHEMA,
            validator=PMPlanningOutput.from_dict,
            dispatch_id=self._next_dispatch_id(f"DISPATCH-PM-PLAN-{facts['task_id']}"),
        )

    def execute(
        self,
        plan: PMPlanningOutput,
        worktree: Path,
        execution_class: ExecutionClass,
        *,
        corrective: bool,
    ) -> ExecutorWorkReport:
        route = ModelRouter.execution(execution_class)
        context = self._context(f"executor:{plan.task_manifest.task_id}", route, worktree)
        prompt = (
            "You are the AI Executor. Implement only this exact host-only manifest in the current "
            "task worktree. Do not alter Git refs, commit, push, execute untrusted task-authored "
            "code, access Goodix/USB, sudo, protected material or network. Return only the work "
            "report JSON; deterministic Git facts are supplied by the coordinator.\n"
            f"CORRECTIVE={str(corrective).lower()}\nTASK_MANIFEST="
            + self._json(plan.task_manifest.to_dict())
        )
        return self.server.run_structured_turn(
            context,
            prompt,
            output_schema=EXECUTOR_WORK_REPORT_SCHEMA,
            validator=ExecutorWorkReport.from_dict,
            dispatch_id=self._next_dispatch_id(
                f"DISPATCH-EXEC-{plan.task_manifest.task_id}-{execution_class.value}"
            ),
        )

    def review(self, evidence: dict[str, Any]) -> PMReviewOutput:
        route = ModelRouter.review()
        context = self._context("review", route, self.repository)
        prompt = (
            "You are the independent AI PM reviewer. Decide only from MEASURED_EVIDENCE. "
            "Return one structured disposition; never infer Git facts from Executor prose and "
            "never expand the delegated envelope.\nMEASURED_EVIDENCE="
            + self._json(evidence)
        )
        return self.server.run_structured_turn(
            context,
            prompt,
            output_schema=PM_REVIEW_OUTPUT_SCHEMA,
            validator=PMReviewOutput.from_dict,
            dispatch_id=self._next_dispatch_id(
                f"DISPATCH-PM-REVIEW-{evidence['task_manifest']['task_id']}"
            ),
        )

    def close(self) -> None:
        self.server.close()


class ProductionCoordinator:
    def __init__(
        self,
        *,
        engine: DeterministicEngine,
        lifecycle: BranchLifecycle,
        driver: CoordinatorDriver,
        gate_adapter: HumanGateAdapter,
    ) -> None:
        self.engine = engine
        self.store = engine.store
        self.lifecycle = lifecycle
        self.driver = driver
        self.gate_adapter = gate_adapter

    def _load(self) -> tuple[PMPlanningOutput | None, ExecutorResult | None, ExecutionClass | None, PMPlanningClass]:
        raw = self.store.load_coordinator_state() or {}
        plan = PMPlanningOutput.from_dict(raw["plan"]) if raw.get("plan") else None
        result = ExecutorResult.from_dict(raw["result"]) if raw.get("result") else None
        execution = ExecutionClass(raw["execution_class"]) if raw.get("execution_class") else None
        planning = PMPlanningClass(raw.get("planning_class", PMPlanningClass.STANDARD.value))
        return plan, result, execution, planning

    def _save(
        self,
        *,
        plan: PMPlanningOutput | None,
        result: ExecutorResult | None,
        execution_class: ExecutionClass | None,
        planning_class: PMPlanningClass = PMPlanningClass.STANDARD,
    ) -> None:
        self.store.save_coordinator_state(
            {
                "plan": plan.to_dict() if plan else None,
                "result": result.to_dict() if result else None,
                "execution_class": execution_class.value if execution_class else None,
                "planning_class": planning_class.value,
            }
        )

    def _worktree(self, manifest: TaskManifest) -> TaskWorktree:
        git = self.store.load_git_state()
        if (
            git is None
            or git.task_id != manifest.task_id
            or git.task_branch != manifest.task_branch
            or git.task_worktree is None
        ):
            raise CoordinatorError("TASK_WORKTREE_RECONCILIATION_REQUIRED", manifest.task_id)
        root = Path(git.task_worktree).resolve(strict=True)
        return TaskWorktree(root, self.lifecycle.repository, manifest.task_branch, manifest.baseline_sha)

    def tick(self) -> None:
        operator = self.store.load_operator_state()
        if operator.operator_paused or operator.maintenance_id or operator.emergency_stop_latched:
            return
        state = self.engine.state
        if state is OrchestratorState.BOOTSTRAP:
            self.engine.bootstrap_complete()
            return
        if state is OrchestratorState.IDLE:
            self.engine.start_planning()
            return
        if state in {
            OrchestratorState.HUMAN_GATE_WAIT,
            OrchestratorState.PAUSED_RATE_LIMIT,
            OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
            OrchestratorState.PAUSED_INFRASTRUCTURE,
            OrchestratorState.DONE,
            OrchestratorState.ERROR_LOCKED,
        }:
            return
        plan, result, execution_class, planning_class = self._load()
        if state is OrchestratorState.PM_PLANNING:
            git = self.store.load_git_state()
            if git is None or git.integration_branch != DEVELOPMENT_BRANCH:
                raise CoordinatorError("DEVELOPMENT_STATE_MISSING", state.value)
            task_id = self.engine.runtime.expected_next_task_id or f"TASK-{self.engine.runtime.run_id.removeprefix('ORCH-')}-001"
            facts = {
                "task_id": task_id,
                "parent_task_id": self.engine.runtime.task_id,
                "baseline_sha": git.integration_sha,
                "integration_branch": DEVELOPMENT_BRANCH,
                "task_branch": self.lifecycle.task_branch(task_id),
                "gate_class": "HOST_ONLY",
                "max_concurrent_tasks": 1,
                "required_non_goals": [
                    "Goodix USB/live", "sudo/root", "protected material", "main", "publication", "history rewrite"
                ],
            }
            plan = self.driver.plan(facts, planning_class)
            manifest = plan.task_manifest
            if (
                manifest.task_id != task_id
                or manifest.baseline_sha != git.integration_sha
                or manifest.integration_branch != DEVELOPMENT_BRANCH
                or manifest.task_branch != self.lifecycle.task_branch(task_id)
            ):
                raise CoordinatorError("PLANNER_GIT_BINDING_MISMATCH", manifest.task_id)
            self.engine.task_ready(manifest)
            self.lifecycle.create_task_worktree(
                task_id=task_id,
                expected_development_sha=git.integration_sha,
                effect_id=f"EFFECT-BRANCH-CREATE-{task_id}",
            )
            self._save(plan=plan, result=None, execution_class=plan.execution_class)
            return
        if plan is None:
            raise CoordinatorError("COORDINATOR_PLAN_RECONCILIATION_REQUIRED", state.value)
        manifest = plan.task_manifest
        worktree = self._worktree(manifest)
        if state is OrchestratorState.TASK_READY:
            selected = execution_class or plan.execution_class
            parent = GitManager._text(worktree.root, ("rev-parse", "HEAD"))
            corrective = parent != manifest.baseline_sha
            self.engine.start_executor(
                turn_id=f"TURN-EXEC-{manifest.task_id}-{parent[:12]}"
            )
            report = self.driver.execute(
                plan, worktree.root, selected, corrective=corrective
            )
            if report.task_id != manifest.task_id:
                raise CoordinatorError("EXECUTOR_TASK_ID_MISMATCH", report.task_id)
            if report.policy_assertions != PolicyAssertions(0, False, False, False):
                raise CoordinatorError("EXECUTOR_POLICY_ASSERTION_VIOLATION", manifest.task_id)
            commit = self.lifecycle.commit_task(
                worktree,
                manifest,
                expected_parent_sha=parent,
                effect_id=f"EFFECT-COMMIT-{manifest.task_id}-{parent[:12]}",
            )
            self.lifecycle.push_task(
                task_id=manifest.task_id,
                commit_sha=commit.head_sha,
                expected_remote_sha=(parent if corrective else None),
                effect_id=f"EFFECT-PUSH-{manifest.task_id}-{commit.head_sha[:12]}",
            )
            result = ExecutorResult(
                protocol_version="1.0",
                task_id=manifest.task_id,
                outcome=report.outcome,
                advancement=report.advancement,
                executable_closure=report.executable_closure,
                residual_blocker_or_risk=report.residual_blocker_or_risk,
                canonical_documentation=report.canonical_documentation,
                review_set=ReviewSet(
                    manifest.baseline_sha, commit.head_sha, commit.changed_paths
                ),
                tests=report.tests,
                policy_assertions=report.policy_assertions,
            )
            self.engine.complete_executor(result)
            self._save(plan=plan, result=result, execution_class=selected)
            return
        if state is OrchestratorState.EXECUTOR_RUNNING:
            raise CoordinatorError("EXECUTOR_TURN_RECONCILIATION_REQUIRED", manifest.task_id)
        if state is OrchestratorState.EXECUTOR_RESULT_READY:
            if result is None:
                raise CoordinatorError("EXECUTOR_RESULT_RECONCILIATION_REQUIRED", manifest.task_id)
            self.engine.start_review(turn_id=f"TURN-REVIEW-{manifest.task_id}-{result.review_set.head_sha[:12]}")
            state = self.engine.state
        if state is not OrchestratorState.PM_REVIEWING or result is None:
            raise CoordinatorError("COORDINATOR_STATE_MISMATCH", state.value)
        diff = GitManager._git(
            worktree.root,
            ("diff", "--no-ext-diff", manifest.baseline_sha, result.review_set.head_sha),
        ).stdout
        if len(diff) > 512 * 1024:
            raise CoordinatorError("REVIEW_DIFF_TOO_LARGE", str(len(diff)))
        evidence = {
            "task_manifest": manifest.to_dict(),
            "executor_result": result.to_dict(),
            "actual_baseline_sha": manifest.baseline_sha,
            "actual_head_sha": GitManager._text(worktree.root, ("rev-parse", "HEAD")),
            "changed_paths": list(result.review_set.changed_paths),
            "unified_diff": diff.decode("utf-8", "strict"),
            "current_development_sha": self.store.load_git_state().integration_sha,
        }
        review = self.driver.review(evidence)
        disposition = review.disposition
        if disposition.disposition is Disposition.ACCEPT:
            assert disposition.reviewed_head_sha is not None
            old = manifest.baseline_sha
            accepted = self.lifecycle.fast_forward_development(
                task_id=manifest.task_id,
                reviewed_head_sha=disposition.reviewed_head_sha,
                expected_old_sha=old,
                effect_id=f"EFFECT-DEVELOPMENT-FF-{manifest.task_id}-{disposition.reviewed_head_sha[:12]}",
            )
            self.engine.apply_disposition(disposition)
            self.lifecycle.cleanup_verified_task(
                task_id=manifest.task_id,
                accepted_sha=accepted,
                worktree=worktree.root,
                remote_branch_exists=True,
            )
            self.store.clear_coordinator_state()
            if self.engine.state is OrchestratorState.DONE:
                self.driver.close()
            return
        if disposition.disposition is Disposition.CORRECTIVE:
            assert review.corrective_execution_class is not None
            self.engine.apply_disposition(disposition)
            self._save(
                plan=plan,
                result=None,
                execution_class=review.corrective_execution_class,
            )
            return
        if disposition.disposition is Disposition.REPLAN:
            assert review.replan_planning_class is not None
            self.engine.apply_disposition(disposition)
            self._save(
                plan=plan,
                result=None,
                execution_class=None,
                planning_class=review.replan_planning_class,
            )
            return
        if disposition.disposition is Disposition.HUMAN_GATE:
            assert disposition.gate is not None
            manifest_gate = disposition.gate
            action = GateAction(
                manifest_gate.action_id,
                {
                    "approval_state": manifest_gate.approval_state.value,
                    "denial_state": manifest_gate.denial_state.value,
                },
            )
            if action.digest != manifest_gate.action_digest:
                raise CoordinatorError("GATE_ACTION_BINDING_MISMATCH", manifest_gate.gate_id)
            self.engine.apply_disposition(disposition)
            self.gate_adapter.create_or_reconcile(
                manifest_gate,
                action,
                effect_id=f"EFFECT-GATE-CREATE-{manifest_gate.gate_id}",
            )
            return
        self.engine.apply_disposition(disposition)
        if disposition.disposition is Disposition.DONE:
            self.driver.close()
