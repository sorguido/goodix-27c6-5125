# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from goodix_orchestrator.branch_lifecycle import BranchLifecycle
from goodix_orchestrator.cli import _recover_service_engine, _service_tick
from goodix_orchestrator.codex_adapter import AdapterError
from goodix_orchestrator.coordinator import CoordinatorPhase, ProductionCoordinator
from goodix_orchestrator.engine import DeterministicEngine
from goodix_orchestrator.gate_adapter import GateAction, GitHubIssue, HumanGateAdapter
from goodix_orchestrator.persistence import EffectKind, EffectStatus, SQLiteStateStore
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
        if dispatch_id.endswith("-0001"):
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


class DurableFakeDriver(FakeDriver):
    """File-backed stand-in for durable Codex structured-result reuse."""

    def __init__(self, ledger_path: Path) -> None:
        super().__init__()
        self.ledger_path = ledger_path

    def _ledger(self):
        if not self.ledger_path.exists():
            return {"remote_dispatches": {}}
        return json.loads(self.ledger_path.read_text(encoding="utf-8"))

    def _save(self, data):
        temporary = self.ledger_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.ledger_path)

    def _cached(self, kind, dispatch_id, parser):
        record = self._ledger()["remote_dispatches"].get(dispatch_id)
        if record is None:
            return None
        if record["kind"] != kind:
            raise AssertionError(f"dispatch kind changed: {dispatch_id}")
        return parser(record["payload"])

    def _persist(self, kind, dispatch_id, output):
        data = self._ledger()
        if dispatch_id in data["remote_dispatches"]:
            raise AssertionError(f"duplicate remote project turn: {dispatch_id}")
        data["remote_dispatches"][dispatch_id] = {
            "kind": kind,
            "payload": output.to_dict(),
        }
        self._save(data)
        return output

    def plan(self, facts, planning_class, *, dispatch_id):
        cached = self._cached("plan", dispatch_id, PMPlanningOutput.from_dict)
        if cached is not None:
            return cached
        return self._persist(
            "plan",
            dispatch_id,
            super().plan(facts, planning_class, dispatch_id=dispatch_id),
        )

    def execute(
        self, plan, worktree, execution_class, *, corrective, dispatch_id
    ):
        cached = self._cached("execute", dispatch_id, ExecutorWorkReport.from_dict)
        if cached is not None:
            return cached
        return self._persist(
            "execute",
            dispatch_id,
            super().execute(
                plan,
                worktree,
                execution_class,
                corrective=corrective,
                dispatch_id=dispatch_id,
            ),
        )

    def _new_review(self, evidence, dispatch_id):
        return super().review(evidence, dispatch_id=dispatch_id)

    def review(self, evidence, *, dispatch_id):
        cached = self._cached("review", dispatch_id, PMReviewOutput.from_dict)
        if cached is not None:
            return cached
        return self._persist(
            "review", dispatch_id, self._new_review(evidence, dispatch_id)
        )


class DurableGateDriver(DurableFakeDriver):
    def _new_review(self, evidence, dispatch_id):
        return GateDriver.review(self, evidence, dispatch_id=dispatch_id)


class DurableFailingDriver(DurableFakeDriver):
    failure_method = ""
    failure_code = ""

    def _fail_once(self, method):
        if method != self.failure_method:
            return
        data = self._ledger()
        failures = data.setdefault("injected_failures", [])
        if method in failures:
            return
        failures.append(method)
        self._save(data)
        raise AdapterError(self.failure_code, "synthetic durable availability failure")

    def plan(self, *args, **kwargs):
        self._fail_once("plan")
        return super().plan(*args, **kwargs)

    def execute(self, *args, **kwargs):
        self._fail_once("execute")
        return super().execute(*args, **kwargs)


class DurableRateLimitDriver(DurableFailingDriver):
    failure_method = "plan"
    failure_code = "PAUSED_RATE_LIMIT"


class DurableModelUnavailableDriver(DurableFailingDriver):
    failure_method = "execute"
    failure_code = "PAUSED_MODEL_UNAVAILABLE"


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


class PersistentGateTransport:
    def __init__(self, state_path: Path):
        self.state_path = state_path

    def _load(self):
        if not self.state_path.exists():
            return {"create_count": 0, "issue": None}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save(self, value):
        self.state_path.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    @staticmethod
    def _issue(value):
        return None if value is None else GitHubIssue(**value)

    @property
    def create_count(self):
        return int(self._load()["create_count"])

    def find_gate_issue(self, repository, marker):
        issue = self._issue(self._load()["issue"])
        return issue if issue is not None and marker in issue.body else None

    def create_issue(self, repository, title, body):
        data = self._load()
        data["create_count"] += 1
        issue = GitHubIssue(repository, 1, "ISSUE_NODE_1", title, body)
        data["issue"] = {
            "repository": issue.repository,
            "number": issue.number,
            "node_id": issue.node_id,
            "title": issue.title,
            "body": issue.body,
        }
        self._save(data)
        return issue

    def read_issue(self, repository, number):
        return self._issue(self._load()["issue"])

    def list_comments(self, repository, number):
        return ()


class CrashBeforeGateEffect:
    def create_or_reconcile(self, *args, **kwargs):
        raise RuntimeError("synthetic crash before GitHub issue effect")


class UnusedGateAdapter:
    def create_or_reconcile(self, *args, **kwargs):
        raise AssertionError("gate adapter unexpectedly used")


class O003CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.root = root
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
        self.state_path = root / "state" / "state.sqlite"
        self.worktree_root = root / "xdg-worktrees"
        self.ledger_path = root / "durable-driver.json"
        self.gate_transport_path = root / "gate-transport.json"
        self.store = SQLiteStateStore(self.state_path)
        self.policy = CapabilityPolicy(
            (
                Capability.HOST_READ,
                Capability.WORKTREE_WRITE,
                Capability.TASK_COMMIT,
                Capability.INTEGRATION_FF,
                Capability.CODEX_APP_SERVER,
            )
        )
        self.engine = DeterministicEngine.create(
            self.store,
            self.policy,
            run_id="ORCH-O003-COORD",
        )
        self.lifecycle = BranchLifecycle(
            self.repo, self.store, worktree_root=self.worktree_root
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

    def _gate_adapter(self, store, transport=None):
        return HumanGateAdapter(
            store,
            transport or PersistentGateTransport(self.gate_transport_path),
            repository="owner/private",
            authorized_user_id=1,
            authorized_login="authority",
        )

    def _restart_runtime(
        self,
        driver_class=DurableFakeDriver,
        *,
        before_checkpoint=None,
        transport=None,
    ):
        try:
            self.coordinator.driver.close()
        except Exception:
            pass
        old_objects = (
            self.store,
            self.engine,
            self.lifecycle,
            self.coordinator.driver,
            self.coordinator,
        )
        self.coordinator = None
        self.lifecycle = None
        self.engine = None
        self.store = None
        reopened = SQLiteStateStore(self.state_path)
        reopened.initialize()
        adapter = self._gate_adapter(reopened, transport)
        engine = _recover_service_engine(reopened, adapter, self.policy)
        self.store = engine.store
        self.engine = engine
        self.lifecycle = BranchLifecycle(
            self.repo, self.store, worktree_root=self.worktree_root
        )
        self.driver = driver_class(self.ledger_path)
        self.coordinator = ProductionCoordinator(
            engine=self.engine,
            lifecycle=self.lifecycle,
            driver=self.driver,
            gate_adapter=adapter,
            before_checkpoint=before_checkpoint,
        )
        new_objects = (
            self.store,
            self.engine,
            self.lifecycle,
            self.driver,
            self.coordinator,
        )
        self.assertTrue(
            all(old is not new for old, new in zip(old_objects, new_objects))
        )
        return self.coordinator

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
            CoordinatorPhase.COMMITTED,
            CoordinatorPhase.PUSHED,
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

    def test_true_store_engine_restart_covers_durable_phase_boundaries(self):
        crash_targets = {
            CoordinatorPhase.PLAN_COMPLETED,
            CoordinatorPhase.TASK_PREPARED,
            CoordinatorPhase.WORKTREE_READY,
            CoordinatorPhase.EXECUTOR_REPORT_PERSISTED,
            CoordinatorPhase.COMMIT_PENDING,
            CoordinatorPhase.COMMITTED,
            CoordinatorPhase.PUSH_PENDING,
            CoordinatorPhase.PUSHED,
            CoordinatorPhase.EXECUTOR_RESULT_PERSISTED,
            CoordinatorPhase.REVIEW_COMPLETED,
            CoordinatorPhase.ACCEPT_FF_PENDING,
            CoordinatorPhase.ACCEPT_FF_VERIFIED,
            CoordinatorPhase.CLEANUP_PENDING,
            CoordinatorPhase.CLEANUP_VERIFIED,
        }
        crashed = set()

        def crash_once(phase, checkpoint):
            if phase in crash_targets and phase not in crashed:
                crashed.add(phase)
                raise RuntimeError(f"synthetic process crash before {phase.value}")

        self.driver = DurableFakeDriver(self.ledger_path)
        self.coordinator = ProductionCoordinator(
            engine=self.engine,
            lifecycle=self.lifecycle,
            driver=self.driver,
            gate_adapter=self._gate_adapter(self.store),
            before_checkpoint=crash_once,
        )
        for _ in range(512):
            try:
                self.coordinator.tick()
            except RuntimeError:
                local_tasks = tuple(
                    line
                    for line in git(
                        self.repo, "branch", "--list", "task/*"
                    ).splitlines()
                    if line.strip()
                )
                self.assertLessEqual(len(local_tasks), 1)
                self._restart_runtime(
                    DurableFakeDriver, before_checkpoint=crash_once
                )
            if self.engine.state is OrchestratorState.DONE:
                break

        self.assertEqual(crashed, crash_targets)
        self.assertEqual(self.engine.state, OrchestratorState.DONE)
        self.assertEqual(self.engine.runtime.run_id, "ORCH-O003-COORD")
        self.assertEqual(self.engine.runtime.task_id, "TASK-O003-COORD-001")
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.main)
        self.assertEqual(git(self.repo, "branch", "--list", "task/*"), "")
        self.assertEqual(self.store.load_git_state().cleanup_status, "PASS")

        remote_dispatches = self.ledger_path.exists() and json.loads(
            self.ledger_path.read_text(encoding="utf-8")
        )["remote_dispatches"]
        kinds = [item["kind"] for item in remote_dispatches.values()]
        self.assertEqual(kinds.count("plan"), 1)
        self.assertEqual(kinds.count("execute"), 2)
        self.assertEqual(kinds.count("review"), 2)
        self.assertEqual(len(remote_dispatches), 5)

        effects = self.store.effects_with_statuses(tuple(EffectStatus))
        self.assertEqual(len({item.effect_id for item in effects}), len(effects))
        kind_counts = {
            kind: sum(item.kind is kind for item in effects) for kind in EffectKind
        }
        self.assertEqual(kind_counts[EffectKind.BRANCH_CREATE], 1)
        self.assertEqual(kind_counts[EffectKind.COMMIT], 2)
        self.assertEqual(kind_counts[EffectKind.PUSH], 2)
        self.assertEqual(kind_counts[EffectKind.INTEGRATION_FF], 1)
        self.assertEqual(kind_counts[EffectKind.TASK_WORKTREE_REMOVE], 1)
        self.assertEqual(kind_counts[EffectKind.TASK_LOCAL_BRANCH_DELETE], 1)
        self.assertEqual(kind_counts[EffectKind.TASK_REMOTE_BRANCH_DELETE], 1)

    def test_subprocess_service_restart_uses_production_startup_path(self):
        state_path = self.root / "subprocess-state" / "state.sqlite"
        worker = Path(__file__).parent / "fixtures" / "service_restart_worker.py"
        observed = []
        for _ in range(96):
            completed = subprocess.run(
                (sys.executable, str(worker), str(self.repo), str(state_path)),
                cwd=Path(__file__).parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"stdout={completed.stdout}\nstderr={completed.stderr}",
            )
            result = json.loads(completed.stdout)
            observed.append(result)
            local_tasks = tuple(
                line
                for line in git(self.repo, "branch", "--list", "task/*").splitlines()
                if line.strip()
            )
            self.assertLessEqual(len(local_tasks), 1)
            if result["state"] == OrchestratorState.DONE.value:
                break

        self.assertEqual(observed[-1]["state"], OrchestratorState.DONE.value)
        self.assertGreater(len({item["pid"] for item in observed}), 1)
        self.assertEqual(len({item["run_id"] for item in observed}), 1)
        restarted = SQLiteStateStore(state_path)
        restarted.initialize()
        self.assertEqual(restarted.load_git_state().cleanup_status, "PASS")
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.main)
        self.assertEqual(git(self.repo, "branch", "--list", "task/*"), "")

    def test_gate_prebinding_restart_recovers_one_local_and_external_gate(self):
        transport = PersistentGateTransport(self.gate_transport_path)
        self.driver = DurableGateDriver(self.ledger_path)
        self.coordinator = ProductionCoordinator(
            engine=self.engine,
            lifecycle=self.lifecycle,
            driver=self.driver,
            gate_adapter=self._gate_adapter(self.store, transport),
        )
        for _ in range(64):
            self.coordinator.tick()
            checkpoint = self.store.load_coordinator_state() or {}
            if checkpoint.get("phase") == CoordinatorPhase.REVIEW_COMPLETED.value:
                break
        self.assertEqual(
            self.store.load_coordinator_state()["phase"],
            CoordinatorPhase.REVIEW_COMPLETED.value,
        )
        self.coordinator.tick()
        self.assertEqual(
            self.store.load_coordinator_state()["phase"],
            CoordinatorPhase.GATE_BINDING_PENDING.value,
        )
        self.assertEqual(self.engine.state, OrchestratorState.PM_REVIEWING)

        dispatches_before = len(
            json.loads(self.ledger_path.read_text(encoding="utf-8"))[
                "remote_dispatches"
            ]
        )
        self.coordinator.gate_adapter = CrashBeforeGateEffect()
        with self.assertRaisesRegex(RuntimeError, "before GitHub issue"):
            self.coordinator.tick()
        self.assertEqual(self.engine.state, OrchestratorState.HUMAN_GATE_WAIT)
        self.assertEqual(
            self.store.load_coordinator_state()["phase"],
            CoordinatorPhase.GATE_BINDING_PENDING.value,
        )
        self.assertEqual(transport.create_count, 0)

        self._restart_runtime(DurableGateDriver, transport=transport)
        self.assertEqual(self.engine.state, OrchestratorState.HUMAN_GATE_WAIT)
        self.coordinator.tick()
        self.assertEqual(
            self.store.load_coordinator_state()["phase"],
            CoordinatorPhase.GATE_BOUND.value,
        )
        self.assertEqual(transport.create_count, 1)
        self.assertEqual(
            len(self.store.pending_gates_for_task("TASK-O003-COORD-001")), 1
        )
        self.assertIsNotNone(
            self.store.load_gate_external("HG-O003-COORD-001")
        )
        dispatches_after = len(
            json.loads(self.ledger_path.read_text(encoding="utf-8"))[
                "remote_dispatches"
            ]
        )
        self.assertEqual(dispatches_after - dispatches_before, 0)
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.main)

    def _availability_restart(self, driver_class, paused_state):
        self.driver = driver_class(self.ledger_path)
        self.coordinator = ProductionCoordinator(
            engine=self.engine,
            lifecycle=self.lifecycle,
            driver=self.driver,
            gate_adapter=self._gate_adapter(self.store),
        )
        for _ in range(64):
            self.coordinator.tick()
            if self.engine.state is paused_state:
                break
        self.assertEqual(self.engine.state, paused_state)
        self._restart_runtime(driver_class)
        self.assertEqual(self.engine.state, paused_state)
        self.engine.resume_pause()
        for _ in range(160):
            self.coordinator.tick()
            if self.engine.state is OrchestratorState.DONE:
                break
        self.assertEqual(self.engine.state, OrchestratorState.DONE)
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.main)

    def test_rate_limit_pause_survives_true_store_engine_restart(self):
        self._availability_restart(
            DurableRateLimitDriver, OrchestratorState.PAUSED_RATE_LIMIT
        )

    def test_model_unavailable_pause_survives_true_store_engine_restart(self):
        self._availability_restart(
            DurableModelUnavailableDriver,
            OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
        )

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
