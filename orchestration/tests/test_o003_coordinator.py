# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from goodix_orchestrator.branch_lifecycle import BranchLifecycle
from goodix_orchestrator.cli import _service_tick
from goodix_orchestrator.codex_adapter import AdapterError
from goodix_orchestrator.coordinator import CoordinatorPhase, ProductionCoordinator
from goodix_orchestrator.engine import DeterministicEngine
from goodix_orchestrator.gate_adapter import GateAction, GitHubIssue, HumanGateAdapter
from goodix_orchestrator.persistence import EffectStatus, SQLiteStateStore
from goodix_orchestrator.policy import Capability, CapabilityPolicy
from goodix_orchestrator.protocols import (
    CanonicalDocumentation,
    Disposition,
    ExecutableClosure,
    ExecutorOutcome,
    GateRequester,
    GateStatus,
    HumanGateManifest,
    ModelPolicy,
    PMDisposition,
    PROTOCOL_VERSION,
    PolicyAssertions,
    TaskScope,
    TestRecord,
    TestStatus,
)
from goodix_orchestrator.state import OrchestratorState
from goodix_orchestrator.service import GitSnapshot
from goodix_orchestrator.structured_output import (
    ExecutionClass,
    ExecutorWorkReport,
    PMPlanningClass,
    PMPlanningOutput,
    PMReviewOutput,
)

from tests.common import task_manifest


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.decode().strip()


class FakeDriver:
    def __init__(self) -> None:
        self.plan_calls = 0
        self.execute_calls = 0
        self.review_calls = 0
        self.closed = False
        self.results = {}

    def plan(self, facts, planning_class, *, dispatch_id):
        if dispatch_id in self.results:
            return self.results[dispatch_id]
        self.plan_calls += 1
        self.assert_planning_class = planning_class
        base = task_manifest(facts["task_id"], baseline=facts["baseline_sha"])
        manifest = replace(
            base,
            integration_branch="development",
            task_branch=facts["task_branch"],
            model_policy=ModelPolicy("gpt-5.6-terra", ("gpt-5.6-terra",)),
            capabilities_required=(
                Capability.HOST_READ,
                Capability.WORKTREE_WRITE,
                Capability.TASK_COMMIT,
                Capability.INTEGRATION_FF,
            ),
            scope=TaskScope(
                ("artifact.txt", "PROJECT_MANUAL.md"),
                ("No Goodix", "No main"),
            ),
        )
        output = PMPlanningOutput(manifest, ExecutionClass.BOUNDED_IMPLEMENTATION)
        self.results[dispatch_id] = output
        return output

    def execute(self, plan, worktree, execution_class, *, corrective, dispatch_id):
        if dispatch_id in self.results:
            return self.results[dispatch_id]
        self.execute_calls += 1
        artifact = worktree / "artifact.txt"
        manual = worktree / "PROJECT_MANUAL.md"
        if corrective:
            artifact.write_text("alpha\nbeta\n", encoding="utf-8")
            manual.write_text("alpha and beta complete\n", encoding="utf-8")
            ready = True
        else:
            artifact.write_text("alpha\n", encoding="utf-8")
            manual.write_text("alpha only\n", encoding="utf-8")
            ready = False
        output = ExecutorWorkReport(
            task_id=plan.task_manifest.task_id,
            outcome=ExecutorOutcome.READY if ready else ExecutorOutcome.BLOCKED,
            advancement="synthetic host-only edit",
            executable_closure=ExecutableClosure.PASS if ready else ExecutableClosure.FAIL,
            residual_blocker_or_risk="none" if ready else "beta missing",
            canonical_documentation=CanonicalDocumentation(True, ("synthetic",)),
            tests=(TestRecord("trusted data check", TestStatus.PASS if ready else TestStatus.FAIL),),
            policy_assertions=PolicyAssertions(0, False, False, False),
        )
        self.results[dispatch_id] = output
        return output

    def review(self, evidence, *, dispatch_id):
        if dispatch_id in self.results:
            return self.results[dispatch_id]
        self.review_calls += 1
        task_id = evidence["task_manifest"]["task_id"]
        if self.review_calls == 1:
            output = PMReviewOutput(
                PMDisposition(
                    PROTOCOL_VERSION,
                    task_id,
                    Disposition.CORRECTIVE,
                    "beta missing",
                ),
                ExecutionClass.LOCAL_CORRECTIVE,
                None,
            )
            self.results[dispatch_id] = output
            return output
        output = PMReviewOutput(
            PMDisposition(
                PROTOCOL_VERSION,
                task_id,
                Disposition.ACCEPT,
                "exact corrected head accepted",
                reviewed_head_sha=evidence["actual_head_sha"],
                accept_target=OrchestratorState.DONE,
            ),
            None,
            None,
        )
        self.results[dispatch_id] = output
        return output

    def close(self):
        self.closed = True


class FailingDriver(FakeDriver):
    def __init__(self, method, code):
        super().__init__()
        self.method = method
        self.code = code
        self.failed = False

    def _fail(self, method):
        if self.method == method and not self.failed:
            self.failed = True
            raise AdapterError(self.code, "synthetic bounded failure")

    def plan(self, *args, **kwargs):
        self._fail("plan")
        return super().plan(*args, **kwargs)

    def execute(self, *args, **kwargs):
        self._fail("execute")
        return super().execute(*args, **kwargs)

    def review(self, *args, **kwargs):
        self._fail("review")
        return super().review(*args, **kwargs)


class GateDriver(FakeDriver):
    def review(self, evidence, *, dispatch_id):
        if dispatch_id in self.results:
            return self.results[dispatch_id]
        self.review_calls += 1
        task_id = evidence["task_manifest"]["task_id"]
        action = GateAction(
            "SYNTHETIC_CONTINUE",
            {"approval_state": "PM_PLANNING", "denial_state": "DONE"},
        )
        gate = HumanGateManifest(
            protocol_version=PROTOCOL_VERSION,
            gate_id="HG-O003-COORD-001",
            task_id=task_id,
            decision_required="Approve synthetic continuation",
            reason="exercise coordinator gate crash recovery",
            commit_sha=evidence["actual_head_sha"],
            action_id=action.action_id,
            action_digest=action.digest,
            action_to_unlock="return to planning",
            residual_risks=("synthetic only",),
            still_forbidden=("USB_GOODIX", "MAIN_MERGE"),
            requested_by=GateRequester.AI_PM,
            status=GateStatus.PENDING,
            approval_state=OrchestratorState.PM_PLANNING,
            denial_state=OrchestratorState.DONE,
        )
        output = PMReviewOutput(
            PMDisposition(
                PROTOCOL_VERSION,
                task_id,
                Disposition.HUMAN_GATE,
                "human authority required",
                gate=gate,
            ),
            None,
            None,
        )
        self.results[dispatch_id] = output
        return output


class FakeGateTransport:
    def __init__(self):
        self.issue = None
        self.create_count = 0

    def find_gate_issue(self, repository, marker):
        return self.issue if self.issue is not None and marker in self.issue.body else None

    def create_issue(self, repository, title, body):
        self.create_count += 1
        self.issue = GitHubIssue(repository, 1, "ISSUE_NODE_1", title, body)
        return self.issue

    def read_issue(self, repository, number):
        return self.issue

    def list_comments(self, repository, number):
        return ()


class UnusedGateAdapter:
    def create_or_reconcile(self, *args, **kwargs):
        raise AssertionError("gate adapter unexpectedly used")


class O003CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote = root / "remote.git"
        subprocess.run(("git", "init", "--bare", str(self.remote)), check=True, stdout=subprocess.DEVNULL)
        self.repo = root / "repo"
        subprocess.run(("git", "init", "-b", "main", str(self.repo)), check=True, stdout=subprocess.DEVNULL)
        git(self.repo, "config", "user.name", "O003 Coordinator")
        git(self.repo, "config", "user.email", "o003@example.invalid")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        git(self.repo, "add", "seed.txt")
        git(self.repo, "commit", "-m", "seed")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-u", "origin", "main")
        self.main = git(self.repo, "rev-parse", "main")
        self.store = SQLiteStateStore(root / "state" / "state.sqlite")
        self.engine = DeterministicEngine.create(
            self.store,
            CapabilityPolicy(
                (
                    Capability.HOST_READ,
                    Capability.WORKTREE_WRITE,
                    Capability.TASK_COMMIT,
                    Capability.INTEGRATION_FF,
                    Capability.CODEX_APP_SERVER,
                )
            ),
            run_id="ORCH-O003-COORD",
        )
        self.lifecycle = BranchLifecycle(
            self.repo, self.store, worktree_root=root / "xdg-worktrees"
        )
        self.lifecycle.initialize_development(
            self.main, effect_id="EFFECT-DEVELOPMENT-INIT"
        )
        self.driver = FakeDriver()
        self.coordinator = ProductionCoordinator(
            engine=self.engine,
            lifecycle=self.lifecycle,
            driver=self.driver,
            gate_adapter=UnusedGateAdapter(),
        )

    def test_service_loop_corrective_accept_ff_cleanup_done(self):
        for _ in range(64):
            self.coordinator.tick()
            if self.engine.state is OrchestratorState.DONE:
                break
        self.assertEqual(self.engine.state, OrchestratorState.DONE)
        self.assertTrue(self.driver.closed)
        self.assertEqual(self.driver.execute_calls, 2)
        self.assertEqual(self.driver.review_calls, 2)
        development = git(self.repo, "rev-parse", "development")
        self.assertNotEqual(development, self.main)
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.main)
        self.assertEqual(git(self.repo, "branch", "--list", "task/*"), "")
        self.assertIsNone(self.lifecycle._remote_sha("task/TASK-O003-COORD-001"))
        state = self.store.load_git_state()
        self.assertEqual(state.cleanup_status, "PASS")
        self.assertIsNone(state.task_id)

    def test_crash_recovery_has_stable_dispatch_and_no_duplicate_effects(self):
        crash_targets = {
            CoordinatorPhase.PLAN_COMPLETED,
            CoordinatorPhase.EXECUTOR_REPORT_PERSISTED,
            CoordinatorPhase.REVIEW_COMPLETED,
            CoordinatorPhase.ACCEPT_FF_VERIFIED,
            CoordinatorPhase.CLEANUP_VERIFIED,
        }
        crashed = set()

        def crash_once(phase, checkpoint):
            if phase in crash_targets and phase not in crashed:
                crashed.add(phase)
                raise RuntimeError(f"synthetic crash before {phase.value}")

        coordinator = ProductionCoordinator(
            engine=self.engine,
            lifecycle=self.lifecycle,
            driver=self.driver,
            gate_adapter=UnusedGateAdapter(),
            before_checkpoint=crash_once,
        )
        for _ in range(128):
            try:
                coordinator.tick()
            except RuntimeError:
                coordinator = ProductionCoordinator(
                    engine=self.engine,
                    lifecycle=self.lifecycle,
                    driver=self.driver,
                    gate_adapter=UnusedGateAdapter(),
                    before_checkpoint=crash_once,
                )
            if self.engine.state is OrchestratorState.DONE:
                break
        self.assertEqual(crashed, crash_targets)
        self.assertEqual(self.engine.state, OrchestratorState.DONE)
        self.assertEqual(self.driver.plan_calls, 1)
        self.assertEqual(self.driver.execute_calls, 2)
        self.assertEqual(self.driver.review_calls, 2)
        effects = self.store.effects_with_statuses(tuple(EffectStatus))
        self.assertEqual(len({item.effect_id for item in effects}), len(effects))

    def _availability_failure(self, method, code, paused_state, failure_class):
        driver = FailingDriver(method, code)
        coordinator = ProductionCoordinator(
            engine=self.engine,
            lifecycle=self.lifecycle,
            driver=driver,
            gate_adapter=UnusedGateAdapter(),
        )
        for _ in range(48):
            coordinator.tick()
            if self.engine.state is paused_state:
                break
        self.assertEqual(self.engine.state, paused_state)
        checkpoint = self.store.load_coordinator_state()
        self.assertEqual(checkpoint["phase"], CoordinatorPhase.PAUSED.value)
        self.assertEqual(checkpoint["failure_class"], failure_class)
        self.assertIn("model_id", checkpoint["failed_route"])
        self.assertFalse(self.store.load_operator_state().operator_paused)
        self.engine.resume_pause()
        for _ in range(128):
            coordinator.tick()
            if self.engine.state is OrchestratorState.DONE:
                break
        self.assertEqual(self.engine.state, OrchestratorState.DONE)

    def test_planning_rate_limit_uses_normative_pause_and_safe_resume(self):
        self._availability_failure("plan", "PAUSED_RATE_LIMIT", OrchestratorState.PAUSED_RATE_LIMIT, "RATE_LIMIT")

    def test_executor_model_unavailable_uses_normative_pause_and_safe_resume(self):
        self._availability_failure("execute", "PAUSED_MODEL_UNAVAILABLE", OrchestratorState.PAUSED_MODEL_UNAVAILABLE, "MODEL_UNAVAILABLE")

    def test_review_transport_ambiguity_uses_infrastructure_pause(self):
        self._availability_failure("review", "TURN_TIMEOUT_AMBIGUOUS", OrchestratorState.PAUSED_INFRASTRUCTURE, "AMBIGUOUS_TRANSPORT_OR_TURN")

    def test_human_gate_issue_crash_reconciles_without_duplicate(self):
        driver = GateDriver()
        transport = FakeGateTransport()
        adapter = HumanGateAdapter(
            self.store,
            transport,
            repository="owner/private",
            authorized_user_id=1,
            authorized_login="authority",
        )
        crashed = False

        def crash_after_issue(phase, checkpoint):
            nonlocal crashed
            if phase is CoordinatorPhase.GATE_BOUND and not crashed:
                crashed = True
                raise RuntimeError("synthetic crash after gate issue")

        coordinator = ProductionCoordinator(
            engine=self.engine,
            lifecycle=self.lifecycle,
            driver=driver,
            gate_adapter=adapter,
            before_checkpoint=crash_after_issue,
        )
        for _ in range(64):
            try:
                coordinator.tick()
            except RuntimeError:
                coordinator = ProductionCoordinator(
                    engine=self.engine,
                    lifecycle=self.lifecycle,
                    driver=driver,
                    gate_adapter=adapter,
                )
            if (self.store.load_coordinator_state() or {}).get("phase") == CoordinatorPhase.GATE_BOUND.value:
                break
        self.assertTrue(crashed)
        self.assertEqual(self.engine.state, OrchestratorState.HUMAN_GATE_WAIT)
        self.assertEqual(transport.create_count, 1)

    def test_real_creation_enforces_single_task_and_xdg_root(self):
        self.engine.bootstrap_complete()
        self.engine.start_planning()
        worktree = self.lifecycle.create_task_worktree(
            task_id="TASK-O003-ONE",
            expected_development_sha=self.main,
            effect_id="EFFECT-BRANCH-ONE",
        )
        self.assertEqual(worktree.root.parent, self.lifecycle.worktree_root)
        with self.assertRaises(Exception):
            self.lifecycle.create_task_worktree(
                task_id="TASK-O003-TWO",
                expected_development_sha=self.main,
                effect_id="EFFECT-BRANCH-TWO",
            )

    def test_fresh_normal_service_path_runs_coordinator_to_done(self):
        fresh = SQLiteStateStore(Path(self.temp.name) / "fresh" / "state.sqlite")
        fresh.initialize()
        driver = FakeDriver()
        with patch(
            "goodix_orchestrator.cli.CodexCoordinatorDriver", return_value=driver
        ):
            tick, close, engine = _service_tick(
                fresh,
                {
                    "github_repository": "owner/private",
                    "authorized_github_user_id": 1,
                    "authorized_github_login": "authority",
                    "reprobe_seconds": 900,
                },
                self.repo,
            )
            self.assertIsNotNone(engine)
            self.assertEqual(engine.state, OrchestratorState.BOOTSTRAP)
            for _ in range(64):
                tick()
                if engine.state is OrchestratorState.DONE:
                    break
            self.assertEqual(engine.state, OrchestratorState.DONE)
            self.assertEqual(fresh.load_git_state().cleanup_status, "PASS")
            self.assertEqual(git(self.repo, "rev-parse", "main"), self.main)
            close()

    def test_fresh_service_without_accepted_development_pauses_cleanly(self):
        fresh = SQLiteStateStore(Path(self.temp.name) / "preactivation" / "state.sqlite")
        fresh.initialize()
        with patch(
            "goodix_orchestrator.cli.git_snapshot",
            return_value=GitSnapshot(self.main, None),
        ):
            tick, close, engine = _service_tick(fresh, {}, self.repo)
        self.assertIsNone(engine)
        self.assertTrue(fresh.load_operator_state().operator_paused)
        self.assertEqual(
            fresh.load_operator_state().last_error_class,
            "DEVELOPMENT_NOT_ACTIVATED",
        )
        tick()
        close()


if __name__ == "__main__":
    unittest.main()
