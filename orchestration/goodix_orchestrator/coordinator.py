# SPDX-License-Identifier: GPL-2.0-or-later
"""Crash-consistent O003 PM -> Executor -> PM production coordinator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Protocol

from .branch_lifecycle import BranchLifecycle, DEVELOPMENT_BRANCH
from .codex_adapter import AdapterError, CodexAppServer, ThreadContext
from .engine import DeterministicEngine
from .gate_adapter import GateAction, HumanGateAdapter
from .git_manager import GitManager, TaskWorktree
from .output_schemas import EXECUTOR_WORK_REPORT_SCHEMA, PM_PLANNING_OUTPUT_SCHEMA, PM_REVIEW_OUTPUT_SCHEMA
from .persistence import SQLiteStateStore, TurnActivityRecord
from .protocols import Disposition, ExecutorResult, PauseReason, PolicyAssertions, ReviewSet, TaskManifest
from .state import OrchestratorState, PAUSED_STATES
from .structured_output import ExecutionClass, ExecutorWorkReport, ModelRouter, PMPlanningClass, PMPlanningOutput, PMReviewOutput

CHECKPOINT_VERSION = 2


class CoordinatorPhase(StrEnum):
    PLAN_DISPATCH_REQUIRED = "PLAN_DISPATCH_REQUIRED"
    PLAN_COMPLETED = "PLAN_COMPLETED"
    TASK_PREPARED = "TASK_PREPARED"
    WORKTREE_READY = "WORKTREE_READY"
    EXECUTOR_START_PENDING = "EXECUTOR_START_PENDING"
    EXECUTOR_DISPATCH_REQUIRED = "EXECUTOR_DISPATCH_REQUIRED"
    EXECUTOR_REPORT_PERSISTED = "EXECUTOR_REPORT_PERSISTED"
    COMMIT_PENDING = "COMMIT_PENDING"
    COMMITTED = "COMMITTED"
    PUSH_PENDING = "PUSH_PENDING"
    PUSHED = "PUSHED"
    EXECUTOR_RESULT_PERSISTED = "EXECUTOR_RESULT_PERSISTED"
    REVIEW_START_PENDING = "REVIEW_START_PENDING"
    REVIEW_DISPATCH_REQUIRED = "REVIEW_DISPATCH_REQUIRED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    ACCEPT_FF_PENDING = "ACCEPT_FF_PENDING"
    ACCEPT_FF_VERIFIED = "ACCEPT_FF_VERIFIED"
    CLEANUP_PENDING = "CLEANUP_PENDING"
    CLEANUP_VERIFIED = "CLEANUP_VERIFIED"
    GATE_BINDING_PENDING = "GATE_BINDING_PENDING"
    GATE_BOUND = "GATE_BOUND"
    PAUSED = "PAUSED"
    DONE = "DONE"


@dataclass(frozen=True, slots=True)
class CoordinatorError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


class CoordinatorDriver(Protocol):
    def plan(self, facts: dict[str, Any], planning_class: PMPlanningClass, *, dispatch_id: str) -> PMPlanningOutput: ...
    def execute(self, plan: PMPlanningOutput, worktree: Path, execution_class: ExecutionClass, *, corrective: bool, dispatch_id: str) -> ExecutorWorkReport: ...
    def review(self, evidence: dict[str, Any], *, dispatch_id: str) -> PMReviewOutput: ...
    def close(self) -> None: ...


class CodexCoordinatorDriver:
    """Three independent App Server contexts with durable structured results."""

    def __init__(self, store: SQLiteStateStore, repository: str | Path, *, executable: str = "codex", timeout: float = 900.0) -> None:
        self.store = store
        self.repository = Path(repository).resolve(strict=True)
        self.server = CodexAppServer(executable, process_cwd=self.repository, store=store, timeout=timeout)
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

    def _context(self, name: str, route, cwd: Path) -> ThreadContext:
        existing = self._contexts.get(name)
        if existing is not None:
            if existing.cwd != str(cwd.resolve(strict=True)):
                raise CoordinatorError("CONTEXT_CWD_MUTATION_DENIED", name)
            context = self.server.reroute_context(existing, route)
            self._contexts[name] = context
            return context
        persisted = tuple(item for item in self.store.list_contexts(active_only=True) if item.context_class is route.context_class and item.cwd == str(cwd.resolve(strict=True)))
        if len(persisted) > 1:
            raise CoordinatorError("CONTEXT_RECONCILIATION_AMBIGUOUS", name)
        context = self.server.resume_thread(persisted[0].thread_id, route, cwd) if persisted else self.server.start_thread(route, cwd)
        self._contexts[name] = context
        return context

    def _cached(self, dispatch_id: str, validator):
        cached = self.store.load_logical_turn_result(dispatch_id)
        return validator(cached[1]) if cached is not None else None

    def plan(self, facts: dict[str, Any], planning_class: PMPlanningClass, *, dispatch_id: str) -> PMPlanningOutput:
        cached = self._cached(dispatch_id, PMPlanningOutput.from_dict)
        if cached is not None:
            return cached
        route = ModelRouter.planning(planning_class)
        context = self._context("plan", route, self.repository)
        prompt = "You are the AI Project Manager. Produce only the bounded host-only task JSON. Copy every identity, Git binding, objective, scope, model policy, execution class, capability, criterion and stop condition supplied in CANONICAL_FACTS exactly; use protocol_version 1.0 and non-empty title/non-goals. Treat CANONICAL_FACTS as authoritative; do not request live, main, sudo, network, protected material, publication, or history rewrite.\nCANONICAL_FACTS=" + self._json(facts)
        return self.server.run_structured_turn(context, prompt, output_schema=PM_PLANNING_OUTPUT_SCHEMA, validator=PMPlanningOutput.from_dict, dispatch_id=dispatch_id)

    def execute(self, plan: PMPlanningOutput, worktree: Path, execution_class: ExecutionClass, *, corrective: bool, dispatch_id: str) -> ExecutorWorkReport:
        cached = self._cached(dispatch_id, ExecutorWorkReport.from_dict)
        if cached is not None:
            return cached
        route = ModelRouter.execution(execution_class)
        context = self._context(f"executor:{plan.task_manifest.task_id}", route, worktree)
        prompt = "You are the AI Executor. Implement only this exact host-only manifest in the current task worktree. Do not alter Git refs, commit, push, execute untrusted task-authored code, access Goodix/USB, sudo, protected material or network. Return only the work report JSON. Copy task_id exactly; after satisfying the criteria use outcome READY and executable_closure PASS, include at least one PASS test, set canonical_documentation.manual_updated true with non-empty sections, and set usb_open_count=0 plus every policy boolean false. Never include deterministic Git facts in the report; they are supplied by the coordinator.\n" + f"CORRECTIVE={str(corrective).lower()}\nTASK_MANIFEST=" + self._json(plan.task_manifest.to_dict())
        return self.server.run_structured_turn(context, prompt, output_schema=EXECUTOR_WORK_REPORT_SCHEMA, validator=ExecutorWorkReport.from_dict, dispatch_id=dispatch_id)

    def review(self, evidence: dict[str, Any], *, dispatch_id: str) -> PMReviewOutput:
        cached = self._cached(dispatch_id, PMReviewOutput.from_dict)
        if cached is not None:
            return cached
        route = ModelRouter.review()
        context = self._context("review", route, self.repository)
        prompt = "You are the independent AI PM reviewer. Decide only from MEASURED_EVIDENCE. Return one structured disposition; never infer Git facts from Executor prose and never expand the delegated envelope. If every criterion and test is satisfied, use ACCEPT with reviewed_head_sha equal to actual_head_sha, accept_target DONE, next_task_id null, and every unrelated disposition field null; otherwise choose the exact applicable non-accept disposition and keep unrelated fields null.\nMEASURED_EVIDENCE=" + self._json(evidence)
        return self.server.run_structured_turn(context, prompt, output_schema=PM_REVIEW_OUTPUT_SCHEMA, validator=PMReviewOutput.from_dict, dispatch_id=dispatch_id)

    def close(self) -> None:
        self.server.close()


def persist_unresolved_turn_pause(
    store: SQLiteStateStore,
    engine: DeterministicEngine,
    activities: tuple[TurnActivityRecord, ...],
) -> None:
    """Crash-safe startup wiring for a previously ambiguous Codex turn."""
    raw = store.load_coordinator_state()
    if not raw or raw.get("version") != CHECKPOINT_VERSION or not activities:
        raise CoordinatorError("TURN_CHECKPOINT_MISSING", repr(tuple(item.activity_id for item in activities)))
    item = activities[-1]
    paused = dict(raw)
    paused.update({
        "phase": CoordinatorPhase.PAUSED.value,
        "resume_phase": raw.get("phase"),
        "pause_applied": False,
        "pause_reason": PauseReason.INFRASTRUCTURE.value,
        "failure_class": "AMBIGUOUS_TRANSPORT_OR_TURN",
        "failed_route": {
            "logical_dispatch_id": raw.get("dispatch_id"),
            "activity_id": item.activity_id,
            "turn_id": item.turn_id,
            "context_class": item.context_class.value,
            "routing_class": item.routing_class.value,
            "model_id": item.requested_model_id,
            "reasoning_effort": item.requested_reasoning_effort,
            "failure_class": "AMBIGUOUS_TRANSPORT_OR_TURN",
        },
    })
    store.save_coordinator_state(paused)
    engine.pause(PauseReason.INFRASTRUCTURE)
    paused["pause_applied"] = True
    store.save_coordinator_state(paused)


class ProductionCoordinator:
    """Advance one durable phase per tick; every external effect has a pre-checkpoint."""

    def __init__(self, *, engine: DeterministicEngine, lifecycle: BranchLifecycle, driver: CoordinatorDriver, gate_adapter: HumanGateAdapter, before_checkpoint: Callable[[CoordinatorPhase, dict[str, Any]], None] | None = None, planning_directive: dict[str, Any] | None = None) -> None:
        self.engine = engine
        self.store = engine.store
        self.lifecycle = lifecycle
        self.driver = driver
        self.gate_adapter = gate_adapter
        self.before_checkpoint = before_checkpoint
        self.planning_directive = dict(planning_directive or {})

    def _load(self) -> dict[str, Any]:
        raw = self.store.load_coordinator_state()
        if raw is None:
            return {}
        if raw.get("version") != CHECKPOINT_VERSION:
            raise CoordinatorError("COORDINATOR_CHECKPOINT_VERSION_MISMATCH", repr(raw.get("version")))
        try:
            CoordinatorPhase(raw["phase"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CoordinatorError("COORDINATOR_CHECKPOINT_INVALID", repr(raw)) from exc
        return raw

    def _save_phase(self, raw: dict[str, Any], phase: CoordinatorPhase, **changes: Any) -> dict[str, Any]:
        updated = dict(raw)
        updated.update(changes)
        updated.update({"version": CHECKPOINT_VERSION, "phase": phase.value})
        if self.before_checkpoint is not None:
            self.before_checkpoint(phase, updated)
        self.store.save_coordinator_state(updated)
        return updated

    def _new_dispatch(self, prefix: str) -> str:
        return self.store.next_logical_dispatch_id(prefix)

    @staticmethod
    def _pause_reason(code: str) -> tuple[PauseReason, str]:
        if code in {"PAUSED_RATE_LIMIT", "USAGE_LIMIT_REACHED"}:
            return PauseReason.RATE_LIMIT, "RATE_LIMIT"
        if code in {"PAUSED_MODEL_UNAVAILABLE", "MODEL_UNAVAILABLE", "MODEL_ROUTING_MISMATCH"}:
            return PauseReason.MODEL_UNAVAILABLE, "MODEL_UNAVAILABLE"
        if code in {"TRANSPORT_LOST_AMBIGUOUS", "TURN_TIMEOUT_AMBIGUOUS", "APP_SERVER_TIMEOUT", "RECONCILIATION_REQUIRED"}:
            return PauseReason.INFRASTRUCTURE, "AMBIGUOUS_TRANSPORT_OR_TURN"
        return PauseReason.INFRASTRUCTURE, "INFRASTRUCTURE"

    def _failed_route(self, raw: dict[str, Any], dispatch_id: str, failure_class: str) -> dict[str, Any]:
        activities = self.store.activities_for_logical_dispatch(dispatch_id)
        if not activities:
            phase = CoordinatorPhase(raw["phase"])
            if phase is CoordinatorPhase.PLAN_DISPATCH_REQUIRED:
                route = ModelRouter.planning(PMPlanningClass(raw["planning_class"]))
            elif phase is CoordinatorPhase.EXECUTOR_DISPATCH_REQUIRED:
                route = ModelRouter.execution(ExecutionClass(raw["execution_class"]))
            elif phase is CoordinatorPhase.REVIEW_DISPATCH_REQUIRED:
                route = ModelRouter.review()
            else:
                return {"logical_dispatch_id": dispatch_id, "failure_class": failure_class}
            return {"logical_dispatch_id": dispatch_id, "context_class": route.context_class.value, "routing_class": route.routing_class.value, "model_id": route.model_id, "reasoning_effort": route.reasoning_effort, "failure_class": failure_class}
        item = activities[-1]
        return {"logical_dispatch_id": dispatch_id, "activity_id": item.activity_id, "turn_id": item.turn_id, "context_class": item.context_class.value, "routing_class": item.routing_class.value, "model_id": item.requested_model_id, "reasoning_effort": item.requested_reasoning_effort, "failure_class": failure_class}

    def _persist_pause(self, raw: dict[str, Any], exc: Exception) -> None:
        code = str(getattr(exc, "code", type(exc).__name__))
        reason, failure_class = self._pause_reason(code)
        dispatch_id = str(raw.get("dispatch_id", "UNKNOWN"))
        paused = self._save_phase(raw, CoordinatorPhase.PAUSED, resume_phase=raw.get("phase"), pause_applied=False, pause_reason=reason.value, failure_class=failure_class, failed_route=self._failed_route(raw, dispatch_id, failure_class))
        self.engine.pause(reason)
        self._save_phase(paused, CoordinatorPhase.PAUSED, pause_applied=True)

    @staticmethod
    def _plan(raw: dict[str, Any]) -> PMPlanningOutput:
        return PMPlanningOutput.from_dict(raw["plan"])

    @staticmethod
    def _report(raw: dict[str, Any]) -> ExecutorWorkReport:
        return ExecutorWorkReport.from_dict(raw["report"])

    @staticmethod
    def _result(raw: dict[str, Any]) -> ExecutorResult:
        return ExecutorResult.from_dict(raw["result"])

    @staticmethod
    def _review(raw: dict[str, Any]) -> PMReviewOutput:
        return PMReviewOutput.from_dict(raw["review"])

    def _worktree(self, manifest: TaskManifest) -> TaskWorktree:
        git = self.store.load_git_state()
        if git is None or git.task_id != manifest.task_id or git.task_branch != manifest.task_branch or git.task_worktree is None:
            raise CoordinatorError("TASK_WORKTREE_RECONCILIATION_REQUIRED", manifest.task_id)
        root = Path(git.task_worktree).resolve(strict=True)
        return TaskWorktree(root, self.lifecycle.repository, manifest.task_branch, manifest.baseline_sha)

    def _planning_checkpoint(self) -> None:
        git = self.store.load_git_state()
        if git is None or git.integration_branch != DEVELOPMENT_BRANCH:
            raise CoordinatorError("DEVELOPMENT_STATE_MISSING", self.engine.state.value)
        task_id = self.engine.runtime.expected_next_task_id or f"TASK-{self.engine.runtime.run_id.removeprefix('ORCH-')}-001"
        facts = {"task_id": task_id, "parent_task_id": self.engine.runtime.task_id, "baseline_sha": git.integration_sha, "integration_branch": DEVELOPMENT_BRANCH, "task_branch": self.lifecycle.task_branch(task_id), "gate_class": "HOST_ONLY", "max_concurrent_tasks": 1, "required_non_goals": ["Goodix USB/live", "sudo/root", "protected material", "main", "publication", "history rewrite"]}
        facts.update(self.planning_directive)
        self._save_phase({}, CoordinatorPhase.PLAN_DISPATCH_REQUIRED, planning_class=PMPlanningClass.STANDARD.value, execution_class=None, facts=facts, plan_attempt=1, executor_attempt=0, review_attempt=0, dispatch_id=f"DISPATCH-PM-PLAN-{task_id}-0001")

    def _review_evidence(self, plan: PMPlanningOutput, result: ExecutorResult, worktree: TaskWorktree) -> dict[str, Any]:
        manifest = plan.task_manifest
        diff = GitManager._git(worktree.root, ("diff", "--no-ext-diff", manifest.baseline_sha, result.review_set.head_sha)).stdout
        if len(diff) > 512 * 1024:
            raise CoordinatorError("REVIEW_DIFF_TOO_LARGE", str(len(diff)))
        git = self.store.load_git_state()
        return {"task_manifest": manifest.to_dict(), "executor_result": result.to_dict(), "actual_baseline_sha": manifest.baseline_sha, "actual_head_sha": GitManager._text(worktree.root, ("rev-parse", "HEAD")), "changed_paths": list(result.review_set.changed_paths), "unified_diff": diff.decode("utf-8", "strict"), "current_development_sha": git.integration_sha if git else None}

    def _tick_phase(self, raw: dict[str, Any]) -> None:
        phase = CoordinatorPhase(raw["phase"])
        if phase is CoordinatorPhase.PAUSED:
            if not raw.get("pause_applied"):
                self.engine.pause(PauseReason(raw["pause_reason"]))
                self._save_phase(raw, phase, pause_applied=True)
                return
            if self.engine.state in PAUSED_STATES:
                return
            resume = CoordinatorPhase(raw["resume_phase"])
            changes: dict[str, Any] = {"pause_applied": None, "pause_reason": None, "failure_class": None, "failed_route": None, "resume_phase": None}
            if resume in {CoordinatorPhase.PLAN_DISPATCH_REQUIRED, CoordinatorPhase.EXECUTOR_DISPATCH_REQUIRED, CoordinatorPhase.REVIEW_DISPATCH_REQUIRED}:
                changes["dispatch_id"] = self._new_dispatch(str(raw["dispatch_id"]).rsplit("-", 1)[0])
            self._save_phase(raw, resume, **changes)
            return
        if phase in {CoordinatorPhase.DONE, CoordinatorPhase.GATE_BOUND}:
            if phase is CoordinatorPhase.GATE_BOUND and self.engine.state is not OrchestratorState.HUMAN_GATE_WAIT:
                self.store.clear_coordinator_state()
            return
        if phase is CoordinatorPhase.PLAN_DISPATCH_REQUIRED:
            plan = self.driver.plan(raw["facts"], PMPlanningClass(raw["planning_class"]), dispatch_id=raw["dispatch_id"])
            manifest, facts = plan.task_manifest, raw["facts"]
            if manifest.task_id != facts["task_id"] or manifest.baseline_sha != facts["baseline_sha"] or manifest.integration_branch != DEVELOPMENT_BRANCH or manifest.task_branch != facts["task_branch"]:
                raise CoordinatorError("PLANNER_GIT_BINDING_MISMATCH", manifest.task_id)
            self._save_phase(raw, CoordinatorPhase.PLAN_COMPLETED, plan=plan.to_dict(), execution_class=plan.execution_class.value)
            return
        plan = self._plan(raw)
        manifest = plan.task_manifest
        if phase is CoordinatorPhase.PLAN_COMPLETED:
            if self.engine.state is OrchestratorState.PM_PLANNING:
                self.engine.task_ready(manifest)
            elif self.engine.state is not OrchestratorState.TASK_READY:
                raise CoordinatorError("PLAN_ENGINE_STATE_MISMATCH", self.engine.state.value)
            self._save_phase(raw, CoordinatorPhase.TASK_PREPARED)
            return
        if phase is CoordinatorPhase.TASK_PREPARED:
            created = self.lifecycle.create_task_worktree(task_id=manifest.task_id, expected_development_sha=manifest.baseline_sha, effect_id=f"EFFECT-BRANCH-CREATE-{manifest.task_id}")
            self._save_phase(raw, CoordinatorPhase.WORKTREE_READY, worktree_path=str(created.root))
            return
        if phase is CoordinatorPhase.CLEANUP_PENDING:
            self.lifecycle.cleanup_verified_task(task_id=manifest.task_id, accepted_sha=raw["accepted_sha"], worktree=Path(raw["worktree_path"]), remote_branch_exists=True)
            self._save_phase(raw, CoordinatorPhase.CLEANUP_VERIFIED)
            return
        if phase is CoordinatorPhase.CLEANUP_VERIFIED:
            disposition = self._review(raw).disposition
            if self.engine.state is OrchestratorState.PM_REVIEWING:
                self.engine.apply_disposition(disposition)
            if self.engine.state is OrchestratorState.DONE:
                self._save_phase(raw, CoordinatorPhase.DONE)
                self.driver.close()
            elif self.engine.state is OrchestratorState.PM_PLANNING:
                self.store.clear_coordinator_state()
            else:
                raise CoordinatorError("POST_ACCEPT_STATE_MISMATCH", self.engine.state.value)
            return
        worktree = self._worktree(manifest)
        if phase is CoordinatorPhase.WORKTREE_READY:
            parent = GitManager._text(worktree.root, ("rev-parse", "HEAD"))
            execution = ExecutionClass(raw["execution_class"])
            attempt = int(raw.get("executor_attempt", 0)) + 1
            self._save_phase(raw, CoordinatorPhase.EXECUTOR_START_PENDING, parent_sha=parent, corrective=parent != manifest.baseline_sha, executor_attempt=attempt, dispatch_id=f"DISPATCH-EXEC-{manifest.task_id}-{execution.value}-{attempt:04d}")
            return
        if phase is CoordinatorPhase.EXECUTOR_START_PENDING:
            if self.engine.state is OrchestratorState.TASK_READY:
                self.engine.start_executor(turn_id=f"TURN-EXEC-{manifest.task_id}-{raw['parent_sha'][:12]}")
            elif self.engine.state is not OrchestratorState.EXECUTOR_RUNNING:
                raise CoordinatorError("EXECUTOR_START_STATE_MISMATCH", self.engine.state.value)
            self._save_phase(raw, CoordinatorPhase.EXECUTOR_DISPATCH_REQUIRED)
            return
        if phase is CoordinatorPhase.EXECUTOR_DISPATCH_REQUIRED:
            report = self.driver.execute(plan, worktree.root, ExecutionClass(raw["execution_class"]), corrective=bool(raw["corrective"]), dispatch_id=raw["dispatch_id"])
            if report.task_id != manifest.task_id:
                raise CoordinatorError("EXECUTOR_TASK_ID_MISMATCH", report.task_id)
            if report.policy_assertions != PolicyAssertions(0, False, False, False):
                raise CoordinatorError("EXECUTOR_POLICY_ASSERTION_VIOLATION", manifest.task_id)
            self._save_phase(raw, CoordinatorPhase.EXECUTOR_REPORT_PERSISTED, report=report.to_dict())
            return
        if phase is CoordinatorPhase.EXECUTOR_REPORT_PERSISTED:
            paths, digest = self.lifecycle.measure_task_changes(worktree, manifest)
            self._save_phase(raw, CoordinatorPhase.COMMIT_PENDING, changed_paths=list(paths), content_digest=digest)
            return
        if phase is CoordinatorPhase.COMMIT_PENDING:
            commit = self.lifecycle.commit_task(worktree, manifest, expected_parent_sha=raw["parent_sha"], effect_id=f"EFFECT-COMMIT-{manifest.task_id}-{raw['parent_sha'][:12]}", expected_changed_paths=tuple(raw["changed_paths"]), expected_content_digest=raw["content_digest"])
            self._save_phase(raw, CoordinatorPhase.COMMITTED, commit_sha=commit.head_sha, changed_paths=list(commit.changed_paths))
            return
        if phase is CoordinatorPhase.COMMITTED:
            self._save_phase(raw, CoordinatorPhase.PUSH_PENDING)
            return
        if phase is CoordinatorPhase.PUSH_PENDING:
            self.lifecycle.push_task(task_id=manifest.task_id, commit_sha=raw["commit_sha"], expected_remote_sha=(raw["parent_sha"] if raw["corrective"] else None), effect_id=f"EFFECT-PUSH-{manifest.task_id}-{raw['commit_sha'][:12]}")
            self._save_phase(raw, CoordinatorPhase.PUSHED)
            return
        if phase is CoordinatorPhase.PUSHED:
            report = self._report(raw)
            result = ExecutorResult(protocol_version="1.0", task_id=manifest.task_id, outcome=report.outcome, advancement=report.advancement, executable_closure=report.executable_closure, residual_blocker_or_risk=report.residual_blocker_or_risk, canonical_documentation=report.canonical_documentation, review_set=ReviewSet(manifest.baseline_sha, raw["commit_sha"], tuple(raw["changed_paths"])), tests=report.tests, policy_assertions=report.policy_assertions)
            self._save_phase(raw, CoordinatorPhase.EXECUTOR_RESULT_PERSISTED, result=result.to_dict())
            return
        if phase is CoordinatorPhase.EXECUTOR_RESULT_PERSISTED:
            result = self._result(raw)
            if self.engine.state is OrchestratorState.EXECUTOR_RUNNING:
                self.engine.complete_executor(result)
            elif self.engine.state is not OrchestratorState.EXECUTOR_RESULT_READY:
                raise CoordinatorError("EXECUTOR_RESULT_STATE_MISMATCH", self.engine.state.value)
            attempt = int(raw.get("review_attempt", 0)) + 1
            self._save_phase(raw, CoordinatorPhase.REVIEW_START_PENDING, review_attempt=attempt, dispatch_id=f"DISPATCH-PM-REVIEW-{manifest.task_id}-{attempt:04d}")
            return
        if phase is CoordinatorPhase.REVIEW_START_PENDING:
            result = self._result(raw)
            if self.engine.state is OrchestratorState.EXECUTOR_RESULT_READY:
                self.engine.start_review(turn_id=f"TURN-REVIEW-{manifest.task_id}-{result.review_set.head_sha[:12]}")
            elif self.engine.state is not OrchestratorState.PM_REVIEWING:
                raise CoordinatorError("REVIEW_START_STATE_MISMATCH", self.engine.state.value)
            self._save_phase(raw, CoordinatorPhase.REVIEW_DISPATCH_REQUIRED)
            return
        if phase is CoordinatorPhase.REVIEW_DISPATCH_REQUIRED:
            review = self.driver.review(self._review_evidence(plan, self._result(raw), worktree), dispatch_id=raw["dispatch_id"])
            self._save_phase(raw, CoordinatorPhase.REVIEW_COMPLETED, review=review.to_dict())
            return
        if phase is CoordinatorPhase.REVIEW_COMPLETED:
            review = self._review(raw)
            disposition = review.disposition
            if disposition.disposition is Disposition.ACCEPT:
                self._save_phase(raw, CoordinatorPhase.ACCEPT_FF_PENDING)
            elif disposition.disposition is Disposition.CORRECTIVE:
                assert review.corrective_execution_class is not None
                if self.engine.state is OrchestratorState.PM_REVIEWING:
                    self.engine.apply_disposition(disposition)
                self._save_phase(raw, CoordinatorPhase.WORKTREE_READY, execution_class=review.corrective_execution_class.value, report=None, result=None, review=None)
            elif disposition.disposition is Disposition.REPLAN:
                assert review.replan_planning_class is not None
                if self.engine.state is OrchestratorState.PM_REVIEWING:
                    self.engine.apply_disposition(disposition)
                attempt = int(raw.get("plan_attempt", 0)) + 1
                self._save_phase(raw, CoordinatorPhase.PLAN_DISPATCH_REQUIRED, planning_class=review.replan_planning_class.value, execution_class=None, plan=None, report=None, result=None, review=None, plan_attempt=attempt, dispatch_id=f"DISPATCH-PM-PLAN-{manifest.task_id}-{attempt:04d}")
            elif disposition.disposition is Disposition.HUMAN_GATE:
                self._save_phase(raw, CoordinatorPhase.GATE_BINDING_PENDING)
            elif disposition.disposition is Disposition.DONE:
                if self.engine.state is OrchestratorState.PM_REVIEWING:
                    self.engine.apply_disposition(disposition)
                self._save_phase(raw, CoordinatorPhase.DONE)
                self.driver.close()
            else:
                if self.engine.state is OrchestratorState.PM_REVIEWING:
                    self.engine.apply_disposition(disposition)
                self._save_phase(raw, CoordinatorPhase.PAUSED, resume_phase=CoordinatorPhase.REVIEW_COMPLETED.value, pause_applied=True, pause_reason=disposition.pause_reason.value)
            return
        if phase is CoordinatorPhase.ACCEPT_FF_PENDING:
            disposition = self._review(raw).disposition
            assert disposition.reviewed_head_sha is not None
            accepted = self.lifecycle.fast_forward_development(task_id=manifest.task_id, reviewed_head_sha=disposition.reviewed_head_sha, expected_old_sha=manifest.baseline_sha, effect_id=f"EFFECT-DEVELOPMENT-FF-{manifest.task_id}-{disposition.reviewed_head_sha[:12]}")
            self._save_phase(raw, CoordinatorPhase.ACCEPT_FF_VERIFIED, accepted_sha=accepted)
            return
        if phase is CoordinatorPhase.ACCEPT_FF_VERIFIED:
            self._save_phase(raw, CoordinatorPhase.CLEANUP_PENDING)
            return
        if phase is CoordinatorPhase.GATE_BINDING_PENDING:
            disposition = self._review(raw).disposition
            assert disposition.gate is not None
            gate = disposition.gate
            if self.engine.state is OrchestratorState.PM_REVIEWING:
                self.engine.apply_disposition(disposition)
            elif self.engine.state is not OrchestratorState.HUMAN_GATE_WAIT:
                raise CoordinatorError(
                    "GATE_BINDING_ENGINE_STATE_MISMATCH", self.engine.state.value
                )
            action = GateAction(gate.action_id, {"approval_state": gate.approval_state.value, "denial_state": gate.denial_state.value})
            if action.digest != gate.action_digest:
                raise CoordinatorError("GATE_ACTION_BINDING_MISMATCH", gate.gate_id)
            self.gate_adapter.create_or_reconcile(gate, action, effect_id=f"EFFECT-GATE-CREATE-{gate.gate_id}")
            self._save_phase(raw, CoordinatorPhase.GATE_BOUND)
            return
        raise CoordinatorError("UNKNOWN_COORDINATOR_PHASE", phase.value)

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
        if state in {OrchestratorState.DONE, OrchestratorState.ERROR_LOCKED}:
            return
        raw = self._load()
        if not raw:
            if state is OrchestratorState.PM_PLANNING:
                self._planning_checkpoint()
            return
        try:
            self._tick_phase(raw)
        except AdapterError as exc:
            self._persist_pause(raw, exc)
