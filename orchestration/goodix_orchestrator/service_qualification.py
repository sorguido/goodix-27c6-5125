# SPDX-License-Identifier: GPL-2.0-or-later
"""Disposable O003 lifecycle harness for the systemd user sandbox."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .branch_lifecycle import BranchLifecycle
from .coordinator import ProductionCoordinator
from .engine import DeterministicEngine
from .persistence import SQLiteStateStore
from .policy import Capability, CapabilityPolicy
from .protocols import (
    CanonicalDocumentation,
    Disposition,
    ExecutableClosure,
    ExecutorOutcome,
    GateClass,
    ModelPolicy,
    PMDisposition,
    PROTOCOL_VERSION,
    PolicyAssertions,
    TaskManifest,
    TaskScope,
    TestRecord,
    TestStatus,
)
from .state import OrchestratorState
from .structured_output import (
    ExecutionClass,
    ExecutorWorkReport,
    PMPlanningOutput,
    PMReviewOutput,
)


class _Driver:
    def plan(self, facts, planning_class):
        manifest = TaskManifest(
            PROTOCOL_VERSION,
            facts["task_id"],
            facts["parent_task_id"],
            "systemd sandbox lifecycle",
            "Write one inert marker and its manual entry",
            facts["baseline_sha"],
            "development",
            facts["task_branch"],
            ModelPolicy("gpt-5.6-terra", ("gpt-5.6-terra",)),
            GateClass.HOST_ONLY,
            (
                Capability.HOST_READ,
                Capability.WORKTREE_WRITE,
                Capability.TASK_COMMIT,
                Capability.INTEGRATION_FF,
            ),
            TaskScope(("artifact.txt", "PROJECT_MANUAL.md"), ("No Goodix", "No main")),
            ("marker and manual exist",),
            True,
            ("stop on scope drift",),
        )
        return PMPlanningOutput(manifest, ExecutionClass.BOUNDED_IMPLEMENTATION)

    def execute(self, plan, worktree, execution_class, *, corrective):
        (worktree / "artifact.txt").write_text("systemd sandbox pass\n", encoding="utf-8")
        (worktree / "PROJECT_MANUAL.md").write_text("systemd sandbox pass\n", encoding="utf-8")
        return ExecutorWorkReport(
            plan.task_manifest.task_id,
            ExecutorOutcome.READY,
            "disposable systemd lifecycle",
            ExecutableClosure.PASS,
            "none",
            CanonicalDocumentation(True, ("synthetic",)),
            (TestRecord("inert marker check", TestStatus.PASS),),
            PolicyAssertions(0, False, False, False),
        )

    def review(self, evidence):
        return PMReviewOutput(
            PMDisposition(
                PROTOCOL_VERSION,
                evidence["task_manifest"]["task_id"],
                Disposition.ACCEPT,
                "measured inert diff accepted",
                reviewed_head_sha=evidence["actual_head_sha"],
                accept_target=OrchestratorState.DONE,
            ),
            None,
            None,
        )

    def close(self): pass


class _NoGate:
    def create_or_reconcile(self, *args, **kwargs):
        raise RuntimeError("gate unexpectedly requested")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def run(repository: Path, state_dir: Path) -> dict[str, object]:
    repository = repository.resolve(strict=True)
    state_dir = state_dir.resolve(strict=True)
    main_before = _git(repository, "rev-parse", "main")
    store = SQLiteStateStore(state_dir / "state.sqlite")
    engine = DeterministicEngine.create(
        store,
        CapabilityPolicy(
            (
                Capability.HOST_READ,
                Capability.WORKTREE_WRITE,
                Capability.TASK_COMMIT,
                Capability.INTEGRATION_FF,
                Capability.CODEX_APP_SERVER,
            )
        ),
        run_id="ORCH-O003-SYSTEMD",
    )
    lifecycle = BranchLifecycle(
        repository, store, worktree_root=state_dir / "worktrees"
    )
    lifecycle.initialize_development(
        main_before, effect_id="EFFECT-DEVELOPMENT-INIT-SYSTEMD"
    )
    coordinator = ProductionCoordinator(
        engine=engine,
        lifecycle=lifecycle,
        driver=_Driver(),
        gate_adapter=_NoGate(),
    )
    for _ in range(8):
        coordinator.tick()
        if engine.state is OrchestratorState.DONE:
            break
    main_after = _git(repository, "rev-parse", "main")
    git_state = store.load_git_state()
    result = {
        "status": "PASS" if engine.state is OrchestratorState.DONE else "FAIL",
        "state": engine.state.value,
        "main_unchanged": main_before == main_after,
        "cleanup": git_state.cleanup_status if git_state else None,
        "task_branch_absent": not bool(_git(repository, "branch", "--list", "task/*")),
    }
    (state_dir / "qualification.json").write_text(
        json.dumps(result, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run(args.repository, args.state_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
