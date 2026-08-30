# SPDX-License-Identifier: GPL-2.0-or-later
"""Real Codex/App-Server O002 qualification on a disposable synthetic repo."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .codex_adapter import AdapterError, CodexAppServer
from .engine import DeterministicEngine, EngineError
from .git_manager import GitManager, GitManagerError
from .output_schemas import (
    EXECUTOR_WORK_REPORT_SCHEMA,
    PM_PLANNING_OUTPUT_SCHEMA,
    PM_REVIEW_OUTPUT_SCHEMA,
)
from .persistence import SCHEMA_VERSION, SQLiteStateStore
from .policy import Capability, CapabilityPolicy
from .state import OrchestratorState
from .structured_output import (
    ExecutionClass,
    ExecutorWorkReport,
    ModelRouter,
    PMPlanningClass,
    PMPlanningOutput,
    PMReviewOutput,
)
from .supervisor import O002Supervisor, SupervisorError
from .synthetic_verifier import VerificationProfile


def _default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / "goodix-orchestrator"
    return Path.home() / ".local" / "state" / "goodix-orchestrator"


def _role_prompt(name: str) -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / name
    return path.read_text(encoding="utf-8")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _planner_prompt(
    *,
    task_id: str,
    parent_task_id: str | None,
    baseline: str,
    integration_branch: str,
    task_branch: str,
    second: bool,
) -> str:
    if second:
        objective = (
            "Create FINAL_STATUS.md with the exact line 'O002 synthetic cycle complete' "
            "and append a matching completion statement to PROJECT_MANUAL.md."
        )
        paths = ["FINAL_STATUS.md", "PROJECT_MANUAL.md"]
        criteria = [
            "FINAL_STATUS.md contains the exact completion line",
            "PROJECT_MANUAL.md documents completion",
            "trusted data-only synthetic verifier passes",
        ]
    else:
        objective = (
            "Make artifact.txt contain alpha and beta on separate lines and document both "
            "in PROJECT_MANUAL.md."
        )
        paths = ["artifact.txt", "PROJECT_MANUAL.md"]
        criteria = [
            "artifact.txt contains alpha and beta",
            "PROJECT_MANUAL.md documents alpha and beta",
            "trusted data-only synthetic verifier passes",
        ]
    facts = {
        "required_task_id": task_id,
        "required_parent_task_id": parent_task_id,
        "exact_baseline_sha": baseline,
        "integration_branch": integration_branch,
        "task_branch": task_branch,
        "objective": objective,
        "scope_paths": paths,
        "acceptance_criteria": criteria,
        "required_execution_class": "BOUNDED_IMPLEMENTATION",
        "model_policy": {
            "preferred": "gpt-5.6-terra",
            "allowed": ["gpt-5.6-terra"],
        },
        "gate_class": "HOST_ONLY",
        "capabilities_required": [
            "HOST_READ",
            "WORKTREE_WRITE",
            "TASK_COMMIT",
            "INTEGRATION_FF",
        ],
        "manual_update_required": True,
        "non_goals": [
            "No Goodix code, USB, protected material, network, sudo, main, or Git refs",
        ],
        "stop_conditions": ["Any requested action exceeds the supplied host-only envelope"],
    }
    return _role_prompt("pm_planner.md") + "\nCANONICAL_PLANNING_FACTS=" + _json(facts)


def _executor_prompt(plan: PMPlanningOutput, *, phase: str) -> str:
    phase_instruction = {
        "initial": (
            "SYNTHETIC_CORRECTIVE_DRILL=true. Implement only alpha and document alpha. "
            "Do not implement or document beta. Do not execute project code; perform only "
            "a data-content self-check, report the unmet beta criterion honestly, use "
            "outcome BLOCKED and executable_closure FAIL."
        ),
        "corrective": (
            "Implement the missing beta requirement, preserve alpha, document both, and do "
            "not execute project code. Report the data-content self-check honestly."
        ),
        "second": (
            "Implement the harmless completion marker exactly, update PROJECT_MANUAL.md, "
            "and do not execute project code. Report a data-content self-check."
        ),
    }[phase]
    return (
        _role_prompt("executor.md")
        + "\nTASK_MANIFEST="
        + _json(plan.task_manifest.to_dict())
        + "\nPHASE_INSTRUCTION="
        + phase_instruction
    )


def _review_prompt(evidence: dict[str, Any], *, phase: str, next_task_id: str | None) -> str:
    state = {
        "phase_id": phase,
        "current_state": "PM_REVIEWING",
        "continuation_task_id": next_task_id,
    }
    return (
        _role_prompt("pm_reviewer.md")
        + "\nORCHESTRATION_STATE="
        + _json(state)
        + "\nMEASURED_REVIEW_EVIDENCE="
        + _json(evidence)
    )


def _review_disposition_hint_count(prompt: str) -> int:
    lowered = prompt.casefold()
    forbidden = (
        "choose corrective",
        "choose accept",
        "choose done",
        "should produce corrective",
        "if all measured criteria pass, accept",
        "if measured evidence passes, return done",
        "expected disposition",
    )
    return sum(lowered.count(item) for item in forbidden)


def _report_base() -> dict[str, Any]:
    return {
        "O002_REAL_CODEX_SYNTHETIC_CYCLE": "FAIL",
        "APP_SERVER_HANDSHAKE": "NOT_EXECUTED",
        "AUTH_MODE": "UNKNOWN",
        "REAL_MODEL_ROUTING_PINNED": "NOT_EXECUTED",
        "REAL_EFFECTIVE_MODEL_EFFORT_VERIFIED": "NOT_EXECUTED",
        "REAL_PM_CORRECTIVE": "NOT_OBSERVED",
        "REAL_PM_ACCEPT": "NOT_OBSERVED",
        "REAL_SECOND_TASK_DONE": "NOT_OBSERVED",
        "REAL_INTEGRATION_FF": "NOT_EXECUTED",
        "MAIN_UNCHANGED": False,
        "HUMAN_RELAY_COUNT": 0,
        "PAID_API_FALLBACK_COUNT": 0,
        "GOODIX_USB_OPEN_COUNT": 0,
        "SUDO_USE_COUNT": 0,
        "PROTECTED_MATERIAL_ACCESS_COUNT": 0,
        "XHIGH_MAX_AUTONOMOUS_USE_COUNT": 0,
        "UNSANDBOXED_TASK_CODE_EXECUTION_COUNT": 0,
        "PM_REVIEW_DISPOSITION_HINT_COUNT": 0,
        "OS_NEGATIVE_CAPABILITY_ISOLATION_PROVEN": False,
        "NEGATIVE_CAPABILITY_EVIDENCE_CLASS": "QUALIFICATION_PATH_NOT_OS_PROOF",
    }


def run_real(state_dir: Path, report_path: Path, codex: str) -> tuple[int, dict[str, Any]]:
    report = _report_base()
    goodix_root = Path(__file__).resolve().parents[2]
    state_dir = state_dir.resolve(strict=False)
    report_path = report_path.resolve(strict=False)
    manager_probe_store = SQLiteStateStore(state_dir / "state.sqlite3")
    manager = GitManager(goodix_root=goodix_root, store=manager_probe_store)
    manager.require_synthetic_root(state_dir)
    manager.require_synthetic_root(report_path)
    state_dir.mkdir(parents=True, exist_ok=False)
    store = manager_probe_store
    store.initialize()
    repository = manager.create_synthetic_repository(state_dir / "synthetic-repository")
    policy = CapabilityPolicy(
        (
            Capability.HOST_READ,
            Capability.WORKTREE_WRITE,
            Capability.TASK_COMMIT,
            Capability.INTEGRATION_FF,
            Capability.CODEX_APP_SERVER,
        )
    )
    engine = DeterministicEngine.create(store, policy, run_id="ORCH-O002-REAL-001")
    supervisor = O002Supervisor(engine=engine, git_manager=manager, repository=repository)
    supervisor.bootstrap()
    adapter = CodexAppServer(
        codex,
        process_cwd=repository.root,
        store=store,
        timeout=900.0,
    )
    try:
        with adapter:
            report["APP_SERVER_HANDSHAKE"] = "PASS"
            report["CODEX_VERSION"] = adapter.codex_version
            report["AUTH_MODE"] = adapter.account_mode()
            report["RATE_LIMIT_TELEMETRY"] = adapter.rate_limit_telemetry()
            for route in (
                ModelRouter.planning(PMPlanningClass.STANDARD),
                ModelRouter.review(),
                ModelRouter.execution(ExecutionClass.BOUNDED_IMPLEMENTATION),
                ModelRouter.execution(ExecutionClass.LOCAL_CORRECTIVE),
            ):
                adapter.require_route(route)

            plan_context = adapter.start_thread(
                ModelRouter.planning(PMPlanningClass.STANDARD), repository.root
            )
            review_context = adapter.start_thread(ModelRouter.review(), repository.root)
            first_id = "TASK-O002-REAL-001"
            second_id = "TASK-O002-REAL-002"
            first_plan = adapter.run_structured_turn(
                plan_context,
                _planner_prompt(
                    task_id=first_id,
                    parent_task_id=None,
                    baseline=repository.integration_sha,
                    integration_branch=repository.integration_branch,
                    task_branch="ai-executor/o002-real-first",
                    second=False,
                ),
                output_schema=PM_PLANNING_OUTPUT_SCHEMA,
                validator=PMPlanningOutput.from_dict,
                dispatch_id="DISPATCH-PM-PLAN-1",
            )
            first_plan_dispatch = store.latest_dispatch_for_thread(plan_context.thread_id)
            if first_plan.execution_class is not ExecutionClass.BOUNDED_IMPLEMENTATION:
                raise SupervisorError("REAL_PLAN_ROUTING_MISMATCH", first_plan.execution_class.value)
            first_worktree = supervisor.accept_plan(
                first_plan,
                worktree_path=state_dir / "worktrees" / "first",
                branch_effect_id="EFFECT-REAL-FIRST-BRANCH",
            )
            exec_context = adapter.start_thread(
                ModelRouter.execution(ExecutionClass.BOUNDED_IMPLEMENTATION),
                first_worktree.root,
            )
            supervisor.start_executor("TURN-REAL-FIRST-EXEC")
            first_work = adapter.run_structured_turn(
                exec_context,
                _executor_prompt(first_plan, phase="initial"),
                output_schema=EXECUTOR_WORK_REPORT_SCHEMA,
                validator=ExecutorWorkReport.from_dict,
                dispatch_id="DISPATCH-EXEC-INITIAL",
            )
            first_work_dispatch = store.latest_dispatch_for_thread(exec_context.thread_id)
            first_result = supervisor.materialize_executor_result(
                first_work,
                expected_parent_sha=first_plan.task_manifest.baseline_sha,
                commit_effect_id="EFFECT-REAL-FIRST-COMMIT",
                executor_dispatch_id=first_work_dispatch.dispatch_id,
                expected_execution_class=ExecutionClass.BOUNDED_IMPLEMENTATION,
                verification_profile=VerificationProfile.TASK_ONE,
            )
            evidence = supervisor.start_review("TURN-REAL-FIRST-REVIEW")
            first_review_prompt = _review_prompt(
                evidence.to_dict(), phase="DRILL-1A", next_task_id=None
            )
            if _review_disposition_hint_count(first_review_prompt):
                raise SupervisorError("REVIEW_DISPOSITION_HINT_DETECTED", "DRILL-1A")
            first_review = adapter.run_structured_turn(
                review_context,
                first_review_prompt,
                output_schema=PM_REVIEW_OUTPUT_SCHEMA,
                validator=PMReviewOutput.from_dict,
                dispatch_id="DISPATCH-PM-REVIEW-1",
            )
            first_review_dispatch = store.latest_dispatch_for_thread(review_context.thread_id)
            if first_review.disposition.disposition.value != "CORRECTIVE":
                raise SupervisorError(
                    "REAL_CORRECTIVE_NOT_OBSERVED",
                    first_review.disposition.disposition.value,
                )
            report["REAL_PM_CORRECTIVE"] = "OBSERVED"
            report["REAL_PM_CORRECTIVE_INDEPENDENT"] = "PASS"
            supervisor.apply_review(first_review)

            corrective_route = ModelRouter.execution(ExecutionClass.LOCAL_CORRECTIVE)
            exec_context = adapter.reroute_context(exec_context, corrective_route)
            supervisor.start_executor("TURN-REAL-CORRECTIVE-EXEC")
            corrective_work = adapter.run_structured_turn(
                exec_context,
                _executor_prompt(first_plan, phase="corrective"),
                output_schema=EXECUTOR_WORK_REPORT_SCHEMA,
                validator=ExecutorWorkReport.from_dict,
                dispatch_id="DISPATCH-EXEC-CORRECTIVE",
            )
            corrective_dispatch = store.latest_dispatch_for_thread(exec_context.thread_id)
            corrected_result = supervisor.materialize_executor_result(
                corrective_work,
                expected_parent_sha=first_result.review_set.head_sha,
                commit_effect_id="EFFECT-REAL-CORRECTIVE-COMMIT",
                executor_dispatch_id=corrective_dispatch.dispatch_id,
                expected_execution_class=ExecutionClass.LOCAL_CORRECTIVE,
                verification_profile=VerificationProfile.TASK_ONE,
            )
            evidence = supervisor.start_review("TURN-REAL-CORRECTIVE-REVIEW")
            corrected_review_prompt = _review_prompt(
                evidence.to_dict(), phase="DRILL-1B", next_task_id=second_id
            )
            if _review_disposition_hint_count(corrected_review_prompt):
                raise SupervisorError("REVIEW_DISPOSITION_HINT_DETECTED", "DRILL-1B")
            accepted = adapter.run_structured_turn(
                review_context,
                corrected_review_prompt,
                output_schema=PM_REVIEW_OUTPUT_SCHEMA,
                validator=PMReviewOutput.from_dict,
                dispatch_id="DISPATCH-PM-REVIEW-2",
            )
            accepted_review_dispatch = store.latest_dispatch_for_thread(
                review_context.thread_id
            )
            if accepted.disposition.disposition.value != "ACCEPT":
                raise SupervisorError(
                    "REAL_ACCEPT_NOT_OBSERVED", accepted.disposition.disposition.value
                )
            if accepted.disposition.reviewed_head_sha != corrected_result.review_set.head_sha:
                raise SupervisorError("REAL_ACCEPT_SHA_MISMATCH", "reviewed head")
            supervisor.apply_review(
                accepted, integration_effect_id="EFFECT-REAL-FIRST-FF"
            )
            report["REAL_PM_ACCEPT"] = "OBSERVED"
            report["REAL_PM_ACCEPT_INDEPENDENT"] = "PASS"
            report["REAL_INTEGRATION_FF"] = "PASS"

            second_plan = adapter.run_structured_turn(
                plan_context,
                _planner_prompt(
                    task_id=second_id,
                    parent_task_id=first_id,
                    baseline=supervisor.repository.integration_sha,
                    integration_branch=supervisor.repository.integration_branch,
                    task_branch="ai-executor/o002-real-second",
                    second=True,
                ),
                output_schema=PM_PLANNING_OUTPUT_SCHEMA,
                validator=PMPlanningOutput.from_dict,
                dispatch_id="DISPATCH-PM-PLAN-2",
            )
            second_plan_dispatch = store.latest_dispatch_for_thread(plan_context.thread_id)
            if second_plan.execution_class is not ExecutionClass.BOUNDED_IMPLEMENTATION:
                raise SupervisorError("REAL_PLAN_ROUTING_MISMATCH", second_plan.execution_class.value)
            second_worktree = supervisor.accept_plan(
                second_plan,
                worktree_path=state_dir / "worktrees" / "second",
                branch_effect_id="EFFECT-REAL-SECOND-BRANCH",
            )
            store.retire_context(exec_context.thread_id)
            second_exec = adapter.start_thread(
                ModelRouter.execution(ExecutionClass.BOUNDED_IMPLEMENTATION),
                second_worktree.root,
            )
            supervisor.start_executor("TURN-REAL-SECOND-EXEC")
            second_work = adapter.run_structured_turn(
                second_exec,
                _executor_prompt(second_plan, phase="second"),
                output_schema=EXECUTOR_WORK_REPORT_SCHEMA,
                validator=ExecutorWorkReport.from_dict,
                dispatch_id="DISPATCH-EXEC-SECOND",
            )
            second_work_dispatch = store.latest_dispatch_for_thread(second_exec.thread_id)
            second_result = supervisor.materialize_executor_result(
                second_work,
                expected_parent_sha=second_plan.task_manifest.baseline_sha,
                commit_effect_id="EFFECT-REAL-SECOND-COMMIT",
                executor_dispatch_id=second_work_dispatch.dispatch_id,
                expected_execution_class=ExecutionClass.BOUNDED_IMPLEMENTATION,
                verification_profile=VerificationProfile.TASK_TWO,
            )
            evidence = supervisor.start_review("TURN-REAL-SECOND-REVIEW")
            final_review_prompt = _review_prompt(
                evidence.to_dict(), phase="DRILL-2", next_task_id=None
            )
            if _review_disposition_hint_count(final_review_prompt):
                raise SupervisorError("REVIEW_DISPOSITION_HINT_DETECTED", "DRILL-2")
            done = adapter.run_structured_turn(
                review_context,
                final_review_prompt,
                output_schema=PM_REVIEW_OUTPUT_SCHEMA,
                validator=PMReviewOutput.from_dict,
                dispatch_id="DISPATCH-PM-REVIEW-3",
            )
            done_review_dispatch = store.latest_dispatch_for_thread(review_context.thread_id)
            if done.disposition.disposition.value != "DONE":
                raise SupervisorError(
                    "REAL_DONE_NOT_OBSERVED", done.disposition.disposition.value
                )
            supervisor.apply_review(done)
            report["REAL_SECOND_TASK_DONE"] = "OBSERVED"
            report["REAL_PM_DONE_INDEPENDENT"] = "PASS"
            report["REAL_PM_TASK_MANIFEST"] = "VALID"
            report["REAL_EXECUTOR_WORK_REPORT"] = "VALID"
            report["REAL_MODEL_ROUTING_PINNED"] = "PASS"
            report["REAL_EFFECTIVE_MODEL_EFFORT_VERIFIED"] = "PASS"
            report["PM_PLAN_MODEL_ID"] = first_plan_dispatch.effective_model_id
            report["PM_PLAN_REASONING"] = first_plan_dispatch.effective_reasoning_effort
            report["PM_REVIEW_MODEL_ID"] = first_review_dispatch.effective_model_id
            report["PM_REVIEW_REASONING"] = first_review_dispatch.effective_reasoning_effort
            report["EXECUTOR_INITIAL_MODEL_ID"] = first_work_dispatch.effective_model_id
            report["EXECUTOR_INITIAL_REASONING"] = first_work_dispatch.effective_reasoning_effort
            report["EXECUTOR_CORRECTIVE_MODEL_ID"] = corrective_dispatch.effective_model_id
            report["EXECUTOR_CORRECTIVE_REASONING"] = corrective_dispatch.effective_reasoning_effort
            report["EXECUTOR_SECOND_MODEL_ID"] = second_work_dispatch.effective_model_id
            report["EXECUTOR_SECOND_REASONING"] = second_work_dispatch.effective_reasoning_effort
            report["PM_PLAN_THREAD_ID_CREATED"] = True
            report["PM_REVIEW_THREAD_ID_CREATED"] = True
            report["EXECUTOR_THREAD_ID_CREATED"] = True
            report["PM_PLAN_REVIEW_THREAD_IDS_DISTINCT"] = plan_context.thread_id != review_context.thread_id
            report["PM_EXECUTOR_THREAD_IDS_DISTINCT"] = len(
                {plan_context.thread_id, review_context.thread_id, exec_context.thread_id}
            ) == 3
            report["ROUTING_TURN_COUNTS"] = store.routing_counts()
            report["PERSISTED_VERIFIED_DISPATCH_IDS"] = [
                dispatch.dispatch_id
                for dispatch in (
                    first_plan_dispatch,
                    first_work_dispatch,
                    first_review_dispatch,
                    corrective_dispatch,
                    accepted_review_dispatch,
                    second_plan_dispatch,
                    second_work_dispatch,
                    done_review_dispatch,
                )
            ]
            report["REVIEW_ROUTING_EVIDENCE_SOURCE"] = "PERSISTED_VERIFIED_DISPATCH"
            report["REAL_REPORT_ROUTING_FIELDS_DERIVED"] = True
            report["O002_EFFECTIVE_ROUTE_VERIFIED_PER_DISPATCH"] = "PASS"
            report["PM_SECOND_TURN_EFFECTIVE_ROUTE_REVERIFIED"] = "PASS"
            report["REVIEW_SECOND_TURN_EFFECTIVE_ROUTE_REVERIFIED"] = "PASS"
            report["EXECUTOR_SAME_ROUTE_REVERIFIED"] = "PASS"
            report["CORRECTIVE_REROUTE_REVERIFIED"] = "PASS"
            report["PM_REVIEW_DISPOSITION_HINT_COUNT"] = sum(
                _review_disposition_hint_count(prompt)
                for prompt in (
                    first_review_prompt,
                    corrected_review_prompt,
                    final_review_prompt,
                )
            )
            report["SYNTHETIC_TRUSTED_VERIFIER"] = "PASS"
            report["SCHEMA_REPAIR_ECHOES_INVALID_CONTENT"] = False
            report["MAIN_UNCHANGED"] = (
                manager._text(repository.root, ("rev-parse", "refs/heads/main"))
                == repository.main_sha
            )
            report["O002_REAL_CODEX_SYNTHETIC_CYCLE"] = "PASS"
            report["TASK_BRANCH_REAL"] = "PASS"
            report["WORKTREE_REAL"] = "PASS"
            report["DETERMINISTIC_TASK_COMMITS"] = "PASS"
            report["INTEGRATION_FF_REAL"] = "PASS"
            report["SYNTHETIC_MAIN_SHA"] = repository.main_sha
            report["FIRST_TASK_HEAD_SHA"] = corrected_result.review_set.head_sha
            report["SECOND_TASK_HEAD_SHA"] = second_result.review_set.head_sha
            report["SYNTHETIC_INTEGRATION_SHA"] = supervisor.repository.integration_sha
            report["STATE_SCHEMA_VERSION"] = SCHEMA_VERSION
            return 0, report
    except (AdapterError, GitManagerError, SupervisorError, EngineError) as exc:
        report["ERROR_CLASS"] = getattr(exc, "code", type(exc).__name__)
        report["ERROR_DETAIL"] = str(exc)[:512]
        if report["ERROR_CLASS"] in {
            "CODEX_NOT_FOUND",
            "AUTH_NOT_CHATGPT",
            "PAUSED_MODEL_UNAVAILABLE",
        }:
            report["O002_REAL_CODEX_SYNTHETIC_CYCLE"] = "NOT_EXECUTED_ENVIRONMENT"
        return 2, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-codex", action="store_true", required=True)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--codex", default="codex")
    args = parser.parse_args(argv)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = args.state_dir or (_default_state_dir() / f"qualification-{timestamp}")
    report_path = args.report or (base.parent / f"qualification-{timestamp}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        code, report = run_real(base, report_path, args.codex)
    except (AdapterError, GitManagerError, SupervisorError, EngineError, OSError) as exc:
        code = 2
        report = _report_base()
        report["ERROR_CLASS"] = getattr(exc, "code", type(exc).__name__)
        report["ERROR_DETAIL"] = str(exc)[:512]
        if report["ERROR_CLASS"] in {
            "CODEX_NOT_FOUND",
            "AUTH_NOT_CHATGPT",
            "PAUSED_MODEL_UNAVAILABLE",
        }:
            report["O002_REAL_CODEX_SYNTHETIC_CYCLE"] = "NOT_EXECUTED_ENVIRONMENT"
    report_path.write_text(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"O002_REAL_CODEX_SYNTHETIC_CYCLE={report['O002_REAL_CODEX_SYNTHETIC_CYCLE']}")
    print(f"REPORT={report_path}")
    if "ERROR_CLASS" in report:
        print(f"ERROR_CLASS={report['ERROR_CLASS']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
