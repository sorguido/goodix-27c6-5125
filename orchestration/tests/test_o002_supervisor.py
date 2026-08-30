# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from goodix_orchestrator.engine import DeterministicEngine
from goodix_orchestrator.git_manager import GitManager
from goodix_orchestrator.persistence import SQLiteStateStore
from goodix_orchestrator.policy import Capability, CapabilityPolicy
from goodix_orchestrator.protocols import (
    CanonicalDocumentation,
    Disposition,
    ExecutableClosure,
    ExecutorOutcome,
    ModelPolicy,
    PMDisposition,
    PROTOCOL_VERSION,
    PolicyAssertions,
    TaskScope,
    TestRecord,
    TestStatus,
)
from goodix_orchestrator.state import OrchestratorState
from goodix_orchestrator.structured_output import (
    ExecutionClass,
    ExecutorWorkReport,
    PMPlanningOutput,
    PMReviewOutput,
)
from goodix_orchestrator.supervisor import O002Supervisor

from tests.common import task_manifest


class O002SupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.goodix = self.root / "goodix"
        self.goodix.mkdir()
        self.store = SQLiteStateStore(self.root / "state.sqlite3")
        policy = CapabilityPolicy(
            (
                Capability.HOST_READ,
                Capability.WORKTREE_WRITE,
                Capability.TASK_COMMIT,
                Capability.INTEGRATION_FF,
                Capability.CODEX_APP_SERVER,
            )
        )
        engine = DeterministicEngine.create(
            self.store, policy, run_id="ORCH-20260830-O002"
        )
        manager = GitManager(goodix_root=self.goodix, store=self.store)
        repository = manager.create_synthetic_repository(self.root / "synthetic")
        self.supervisor = O002Supervisor(
            engine=engine, git_manager=manager, repository=repository
        )
        self.supervisor.bootstrap()

    def plan(self, task_id, baseline, branch, paths, parent=None):
        original = task_manifest(task_id, baseline=baseline, parent_task_id=parent)
        manifest = replace(
            original,
            integration_branch=self.supervisor.repository.integration_branch,
            task_branch=branch,
            model_policy=ModelPolicy(
                preferred="gpt-5.6-terra",
                allowed=("gpt-5.6-terra",),
            ),
            capabilities_required=(
                Capability.HOST_READ,
                Capability.WORKTREE_WRITE,
                Capability.TASK_COMMIT,
                Capability.INTEGRATION_FF,
            ),
            scope=TaskScope(paths=paths, non_goals=("No Goodix", "No main")),
            acceptance_criteria=("Measured synthetic criteria pass",),
        )
        return PMPlanningOutput(manifest, ExecutionClass.BOUNDED_IMPLEMENTATION)

    @staticmethod
    def work_report(task_id, *, complete):
        return ExecutorWorkReport(
            task_id=task_id,
            outcome=ExecutorOutcome.READY if complete else ExecutorOutcome.BLOCKED,
            advancement="Synthetic host-only implementation",
            executable_closure=ExecutableClosure.PASS if complete else ExecutableClosure.FAIL,
            residual_blocker_or_risk="None" if complete else "beta remains unmet",
            canonical_documentation=CanonicalDocumentation(
                manual_updated=True, sections=("Synthetic project state",)
            ),
            tests=(
                TestRecord(
                    "python -m unittest discover -s tests -v",
                    TestStatus.PASS if complete else TestStatus.FAIL,
                ),
            ),
            policy_assertions=PolicyAssertions(0, False, False, False),
        )

    def test_fake_corrective_accept_next_done_uses_o001_engine(self) -> None:
        initial_main = self.supervisor.repository.main_sha
        first_plan = self.plan(
            "TASK-20260830-201",
            self.supervisor.repository.integration_sha,
            "ai-executor/o002-first",
            ("artifact.txt", "PROJECT_MANUAL.md"),
        )
        worktree = self.supervisor.accept_plan(
            first_plan,
            worktree_path=self.root / "worktrees" / "first",
            branch_effect_id="EFFECT-FIRST-BRANCH",
        )
        self.supervisor.start_executor("TURN-FIRST-EXEC")
        (worktree.root / "artifact.txt").write_text("alpha\n", encoding="utf-8")
        (worktree.root / "PROJECT_MANUAL.md").write_text(
            "# Synthetic project manual\n\nalpha implemented; beta missing.\n",
            encoding="utf-8",
        )
        first_result = self.supervisor.materialize_executor_result(
            self.work_report(first_plan.task_manifest.task_id, complete=False),
            expected_parent_sha=first_plan.task_manifest.baseline_sha,
            commit_effect_id="EFFECT-FIRST-COMMIT",
        )
        evidence = self.supervisor.start_review(
            "TURN-FIRST-REVIEW", execution_class=ExecutionClass.BOUNDED_IMPLEMENTATION
        )
        payload = evidence.to_dict()
        self.assertNotIn("planner_history", payload)
        self.assertNotIn("planner_prompt", payload)
        self.assertEqual(payload["measured_test"]["status"], "FAIL")
        corrective = PMReviewOutput(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id=first_plan.task_manifest.task_id,
                disposition=Disposition.CORRECTIVE,
                reason="beta and its manual coverage are absent",
            ),
            ExecutionClass.LOCAL_CORRECTIVE,
            None,
        )
        self.assertEqual(
            self.supervisor.apply_review(corrective), OrchestratorState.TASK_READY
        )

        self.supervisor.start_executor("TURN-CORRECTIVE-EXEC")
        (worktree.root / "artifact.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        (worktree.root / "PROJECT_MANUAL.md").write_text(
            "# Synthetic project manual\n\nalpha and beta implemented.\n",
            encoding="utf-8",
        )
        corrected = self.supervisor.materialize_executor_result(
            self.work_report(first_plan.task_manifest.task_id, complete=True),
            expected_parent_sha=first_result.review_set.head_sha,
            commit_effect_id="EFFECT-CORRECTIVE-COMMIT",
        )
        evidence = self.supervisor.start_review(
            "TURN-CORRECTIVE-REVIEW",
            execution_class=ExecutionClass.LOCAL_CORRECTIVE,
        )
        self.assertEqual(evidence.measured_test["status"], "PASS")
        accepted = PMReviewOutput(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id=first_plan.task_manifest.task_id,
                disposition=Disposition.ACCEPT,
                reason="Exact corrected head and measured evidence pass",
                reviewed_head_sha=corrected.review_set.head_sha,
                accept_target=OrchestratorState.PM_PLANNING,
                next_task_id="TASK-20260830-202",
            ),
            None,
            None,
        )
        self.assertEqual(
            self.supervisor.apply_review(
                accepted, integration_effect_id="EFFECT-FIRST-FF"
            ),
            OrchestratorState.PM_PLANNING,
        )

        second_plan = self.plan(
            "TASK-20260830-202",
            self.supervisor.repository.integration_sha,
            "ai-executor/o002-second",
            ("FINAL_STATUS.md", "PROJECT_MANUAL.md"),
            parent=first_plan.task_manifest.task_id,
        )
        second_worktree = self.supervisor.accept_plan(
            second_plan,
            worktree_path=self.root / "worktrees" / "second",
            branch_effect_id="EFFECT-SECOND-BRANCH",
        )
        self.supervisor.start_executor("TURN-SECOND-EXEC")
        (second_worktree.root / "FINAL_STATUS.md").write_text(
            "O002 synthetic completion marker\n", encoding="utf-8"
        )
        with (second_worktree.root / "PROJECT_MANUAL.md").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write("\nSynthetic cycle complete.\n")
        second_result = self.supervisor.materialize_executor_result(
            self.work_report(second_plan.task_manifest.task_id, complete=True),
            expected_parent_sha=second_plan.task_manifest.baseline_sha,
            commit_effect_id="EFFECT-SECOND-COMMIT",
        )
        self.supervisor.start_review(
            "TURN-SECOND-REVIEW", execution_class=ExecutionClass.BOUNDED_IMPLEMENTATION
        )
        done = PMReviewOutput(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id=second_plan.task_manifest.task_id,
                disposition=Disposition.DONE,
                reason=f"Second harmless task reviewed at {second_result.review_set.head_sha}",
            ),
            None,
            None,
        )
        self.assertEqual(self.supervisor.apply_review(done), OrchestratorState.DONE)
        self.assertEqual(
            self.supervisor.git_manager._text(
                self.supervisor.repository.root, ("rev-parse", "refs/heads/main")
            ),
            initial_main,
        )


if __name__ == "__main__":
    unittest.main()
