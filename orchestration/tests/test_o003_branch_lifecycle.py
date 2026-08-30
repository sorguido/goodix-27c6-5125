# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from goodix_orchestrator.branch_lifecycle import BranchLifecycle, BranchLifecycleError
from goodix_orchestrator.persistence import (
    EffectKind,
    DevelopmentInitIntent,
    IntegrationFFIntent,
    SQLiteStateStore,
    TaskCleanupIntent,
)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.decode("utf-8", "strict").strip()


class O003BranchLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        subprocess.run(("git", "init", "--bare", str(self.remote)), check=True, stdout=subprocess.DEVNULL)
        self.repo = self.root / "repo"
        subprocess.run(("git", "init", "-b", "main", str(self.repo)), check=True, stdout=subprocess.DEVNULL)
        git(self.repo, "config", "user.name", "O003 Test")
        git(self.repo, "config", "user.email", "o003-test@example.invalid")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        git(self.repo, "add", "seed.txt")
        git(self.repo, "commit", "-m", "seed")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-u", "origin", "main")
        self.main = git(self.repo, "rev-parse", "main")
        self.store = SQLiteStateStore(self.root / "state.sqlite")
        self.store.initialize()
        self.lifecycle = BranchLifecycle(self.repo, self.store)

    def init_development(self) -> None:
        self.assertEqual(
            self.lifecycle.initialize_development(self.main, effect_id="EFFECT-DEVELOPMENT-INIT"),
            self.main,
        )

    def create_task(self, task_id: str = "TASK-O003-001") -> tuple[str, Path]:
        branch = self.lifecycle.task_branch(task_id)
        git(self.repo, "branch", branch, "development")
        worktree = self.root / f"worktree-{task_id}"
        git(self.repo, "worktree", "add", str(worktree), branch)
        (worktree / "artifact.txt").write_text("accepted\n", encoding="utf-8")
        git(worktree, "add", "artifact.txt")
        git(worktree, "commit", "-m", task_id)
        git(self.repo, "push", "origin", branch)
        return git(worktree, "rev-parse", "HEAD"), worktree

    def test_development_init_exact_sha_and_replay(self) -> None:
        self.init_development()
        self.assertEqual(git(self.repo, "rev-parse", "development"), self.main)
        self.assertEqual(
            self.lifecycle.initialize_development(self.main, effect_id="EFFECT-DEVELOPMENT-INIT"),
            self.main,
        )
        with self.assertRaises(BranchLifecycleError):
            self.lifecycle.initialize_development("f" * 40, effect_id="EFFECT-OTHER")

    def test_development_init_crash_after_local_ref_resumes_remote_create(self) -> None:
        effect_id = "EFFECT-DEVELOPMENT-INIT-CRASH"
        self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=f"DEVELOPMENT_INIT:{self.main}",
            kind=EffectKind.DEVELOPMENT_INIT,
            intent=DevelopmentInitIntent(self.main),
        )
        self.store.begin_effect(effect_id)
        git(self.repo, "update-ref", "refs/heads/development", self.main, "0" * 40)
        self.assertEqual(
            self.lifecycle.initialize_development(self.main, effect_id=effect_id),
            self.main,
        )
        self.assertEqual(self.lifecycle._remote_sha("development"), self.main)

    def test_verified_ff_and_cleanup_order(self) -> None:
        self.init_development()
        head, worktree = self.create_task()
        observed = self.lifecycle.fast_forward_development(
            task_id="TASK-O003-001",
            reviewed_head_sha=head,
            expected_old_sha=self.main,
            effect_id="EFFECT-DEVELOPMENT-FF",
        )
        self.assertEqual(observed, head)
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.main)
        result = self.lifecycle.cleanup_verified_task(
            task_id="TASK-O003-001",
            accepted_sha=head,
            worktree=worktree,
            remote_branch_exists=True,
        )
        self.assertTrue(all((result.integration_verified, result.worktree_removed, result.local_branch_deleted, result.remote_branch_deleted)))

    def test_reviewed_sha_expected_old_and_non_ff_refuse_preserving_task(self) -> None:
        self.init_development()
        head, worktree = self.create_task()
        for reviewed, old in ((self.main, self.main), (head, "f" * 40)):
            with self.subTest(reviewed=reviewed, old=old), self.assertRaises(BranchLifecycleError):
                self.lifecycle.fast_forward_development(
                    task_id="TASK-O003-001",
                    reviewed_head_sha=reviewed,
                    expected_old_sha=old,
                    effect_id=f"EFFECT-REFUSE-{reviewed[:2]}-{old[:2]}",
                )
        self.assertEqual(git(self.repo, "rev-parse", "task/TASK-O003-001"), head)
        self.assertTrue(worktree.exists())

    def test_cleanup_before_verified_integration_is_denied(self) -> None:
        self.init_development()
        head, worktree = self.create_task()
        with self.assertRaises(BranchLifecycleError) as caught:
            self.lifecycle.cleanup_verified_task(
                task_id="TASK-O003-001",
                accepted_sha=head,
                worktree=worktree,
                remote_branch_exists=True,
            )
        self.assertIn("PRESERVE_TASK", caught.exception.code)
        self.assertTrue(worktree.exists())
        self.assertEqual(git(self.repo, "rev-parse", "task/TASK-O003-001"), head)

    def test_cleanup_wrong_worktree_identity_preserves_task(self) -> None:
        self.init_development()
        head, worktree = self.create_task()
        self.lifecycle.fast_forward_development(
            task_id="TASK-O003-001",
            reviewed_head_sha=head,
            expected_old_sha=self.main,
            effect_id="EFFECT-DEVELOPMENT-FF",
        )
        with self.assertRaises(BranchLifecycleError) as caught:
            self.lifecycle.cleanup_verified_task(
                task_id="TASK-O003-001",
                accepted_sha=head,
                worktree=self.root / "wrong-worktree",
                remote_branch_exists=True,
            )
        self.assertEqual(caught.exception.code, "TASK_WORKTREE_PATH_MISMATCH_PRESERVE_TASK")
        self.assertTrue(worktree.exists())
        self.assertEqual(git(self.repo, "rev-parse", "task/TASK-O003-001"), head)

    def test_max_concurrent_tasks_one(self) -> None:
        self.init_development()
        self.create_task("TASK-O003-001")
        git(self.repo, "branch", "task/TASK-O003-002", "development")
        with self.assertRaises(BranchLifecycleError) as caught:
            self.lifecycle.assert_single_task(allowed_task_id="TASK-O003-001")
        self.assertEqual(caught.exception.code, "MAX_CONCURRENT_TASKS_EXCEEDED")

    def test_cleanup_crash_with_exact_pre_state_retries_once(self) -> None:
        self.init_development()
        head, worktree = self.create_task()
        self.lifecycle.fast_forward_development(
            task_id="TASK-O003-001",
            reviewed_head_sha=head,
            expected_old_sha=self.main,
            effect_id="EFFECT-DEVELOPMENT-FF",
        )
        intent = TaskCleanupIntent("TASK-O003-001", "task/TASK-O003-001", head, head)
        effect_id = "EFFECT-CLEANUP-WORKTREE-TASK-O003-001"
        self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=effect_id,
            kind=EffectKind.TASK_WORKTREE_REMOVE,
            intent=intent,
        )
        self.store.begin_effect(effect_id)
        self.lifecycle.cleanup_verified_task(
            task_id="TASK-O003-001",
            accepted_sha=head,
            worktree=worktree,
            remote_branch_exists=True,
        )
        self.assertFalse(worktree.exists())
        self.assertEqual(self.store.load_git_state().cleanup_status, "PASS")

    def test_crash_after_development_ff_reconciles_without_second_ff(self) -> None:
        self.init_development()
        head, _ = self.create_task()
        effect_id = "EFFECT-DEVELOPMENT-FF-CRASH"
        intent = IntegrationFFIntent(
            "TASK-O003-001", "task/TASK-O003-001", "development", self.main, head
        )
        self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=f"TASK-O003-001:DEVELOPMENT_FF:{self.main}:{head}",
            kind=EffectKind.INTEGRATION_FF,
            intent=intent,
        )
        self.store.begin_effect(effect_id)
        git(self.repo, "update-ref", "refs/heads/development", head, self.main)
        git(self.repo, "push", "origin", "development:development")
        observed = self.lifecycle.fast_forward_development(
            task_id="TASK-O003-001",
            reviewed_head_sha=head,
            expected_old_sha=self.main,
            effect_id=effect_id,
        )
        self.assertEqual(observed, head)
        self.assertEqual(self.store.load_effect(effect_id).status.value, "COMPLETED")

    def test_cleanup_recovery_after_worktree_already_removed(self) -> None:
        self.init_development()
        head, worktree = self.create_task()
        self.lifecycle.fast_forward_development(
            task_id="TASK-O003-001",
            reviewed_head_sha=head,
            expected_old_sha=self.main,
            effect_id="EFFECT-DEVELOPMENT-FF",
        )
        intent = TaskCleanupIntent("TASK-O003-001", "task/TASK-O003-001", head, head)
        effect_id = "EFFECT-CLEANUP-WORKTREE-TASK-O003-001"
        self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=effect_id,
            kind=EffectKind.TASK_WORKTREE_REMOVE,
            intent=intent,
        )
        self.store.begin_effect(effect_id)
        git(self.repo, "worktree", "remove", str(worktree))
        result = self.lifecycle.cleanup_verified_task(
            task_id="TASK-O003-001",
            accepted_sha=head,
            worktree=worktree,
            remote_branch_exists=True,
        )
        self.assertTrue(result.worktree_removed)
        self.assertTrue(result.local_branch_deleted)

    def test_unknown_cleanup_branch_cannot_be_injected(self) -> None:
        self.init_development()
        with self.assertRaises(Exception):
            TaskCleanupIntent("TASK-O003-001", "development", self.main, self.main)
        with self.assertRaises(BranchLifecycleError):
            self.lifecycle.task_branch("main")


if __name__ == "__main__":
    unittest.main()
