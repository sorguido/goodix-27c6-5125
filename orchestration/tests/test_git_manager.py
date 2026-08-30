# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from goodix_orchestrator.git_manager import GitManager, GitManagerError
from goodix_orchestrator.persistence import SQLiteStateStore
from goodix_orchestrator.policy import Capability
from goodix_orchestrator.protocols import ModelPolicy, TaskScope

from tests.common import task_manifest


class GitManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.goodix = self.root / "goodix"
        self.goodix.mkdir()
        self.store = SQLiteStateStore(self.root / "state.sqlite3")
        self.store.initialize()
        self.manager = GitManager(goodix_root=self.goodix, store=self.store)
        self.repository = self.manager.create_synthetic_repository(self.root / "synthetic")

    def manifest(self, task_id="TASK-20260830-100", baseline=None, branch=None):
        original = task_manifest(task_id, baseline=baseline or self.repository.integration_sha)
        return replace(
            original,
            integration_branch=self.repository.integration_branch,
            task_branch=branch or f"ai-executor/{task_id.lower()}",
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
            scope=TaskScope(
                paths=("artifact.txt", "PROJECT_MANUAL.md"),
                non_goals=("No Goodix",),
            ),
        )

    def worktree(self, manifest=None, suffix="one"):
        manifest = manifest or self.manifest()
        return self.manager.create_task_worktree(
            self.repository,
            task_id=manifest.task_id,
            task_branch=manifest.task_branch,
            worktree_path=self.root / "worktrees" / suffix,
            expected_integration_sha=manifest.baseline_sha,
            effect_id=f"EFFECT-BRANCH-{suffix}",
        )

    def test_synthetic_repo_task_branch_and_worktree_exact(self) -> None:
        self.assertEqual(self.repository.main_sha, self.repository.integration_sha)
        manifest = self.manifest()
        worktree = self.worktree(manifest)
        self.assertEqual(worktree.baseline_sha, self.repository.integration_sha)
        self.assertEqual(
            self.manager._text(worktree.root, ("rev-parse", "HEAD")),
            self.repository.integration_sha,
        )

    def test_goodix_root_and_alias_are_rejected(self) -> None:
        for candidate in (self.goodix, self.goodix / "nested"):
            with self.subTest(candidate=candidate), self.assertRaises(GitManagerError) as caught:
                self.manager.require_synthetic_root(candidate)
            self.assertEqual(caught.exception.code, "GOODIX_ROOT_REJECTED_AS_SYNTHETIC_ROOT")

    def test_out_of_scope_symlink_and_diff_check_are_denied(self) -> None:
        manifest = self.manifest()
        worktree = self.worktree(manifest)
        (worktree.root / "outside.txt").write_text("x\n", encoding="utf-8")
        with self.assertRaises(GitManagerError) as caught:
            self.manager.enforce_scope(worktree, manifest)
        self.assertEqual(caught.exception.code, "OUT_OF_SCOPE_CHANGE_DENIED")
        (worktree.root / "outside.txt").unlink()
        (worktree.root / "artifact.txt").unlink()
        (worktree.root / "artifact.txt").symlink_to("PROJECT_MANUAL.md")
        with self.assertRaises(GitManagerError) as caught:
            self.manager.enforce_scope(worktree, manifest)
        self.assertEqual(caught.exception.code, "SYMLINK_PATH_ESCAPE_DENIED")
        (worktree.root / "artifact.txt").unlink()
        (worktree.root / "artifact.txt").write_text("alpha \n", encoding="utf-8")
        with self.assertRaises(GitManagerError) as caught:
            self.manager.enforce_scope(worktree, manifest)
        self.assertEqual(caught.exception.code, "DIFF_CHECK_FAILURE_DENIED")

    def test_git_metadata_change_is_denied(self) -> None:
        manifest = self.manifest()
        worktree = self.worktree(manifest)
        (worktree.root / ".git").write_text("tampered\n", encoding="utf-8")
        (worktree.root / "artifact.txt").write_text("alpha\n", encoding="utf-8")
        with self.assertRaises(GitManagerError) as caught:
            self.manager.enforce_scope(worktree, manifest)
        self.assertEqual(caught.exception.code, "GIT_METADATA_CHANGE_DENIED")

    def _commit(self):
        manifest = self.manifest()
        worktree = self.worktree(manifest)
        (worktree.root / "artifact.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        (worktree.root / "PROJECT_MANUAL.md").write_text(
            "# Manual\n\nalpha and beta.\n", encoding="utf-8"
        )
        commit = self.manager.commit_task(
            worktree,
            manifest,
            expected_parent_sha=manifest.baseline_sha,
            effect_id="EFFECT-COMMIT-ONE",
        )
        return manifest, worktree, commit

    def test_git_manager_creates_commit_and_exact_integration_ff(self) -> None:
        manifest, _, commit = self._commit()
        self.assertNotEqual(commit.head_sha, commit.baseline_sha)
        self.assertEqual(
            commit.changed_paths, ("PROJECT_MANUAL.md", "artifact.txt")
        )
        observed = self.manager.fast_forward_integration(
            self.repository,
            task_id=manifest.task_id,
            task_branch=manifest.task_branch,
            reviewed_head_sha=commit.head_sha,
            expected_old_sha=self.repository.integration_sha,
            effect_id="EFFECT-FF-ONE",
        )
        self.assertEqual(observed, commit.head_sha)
        self.assertEqual(
            self.manager._text(self.repository.root, ("rev-parse", "refs/heads/main")),
            self.repository.main_sha,
        )

    def test_wrong_reviewed_sha_wrong_old_and_main_are_denied(self) -> None:
        manifest, _, commit = self._commit()
        with self.assertRaises(GitManagerError) as caught:
            self.manager.fast_forward_integration(
                self.repository,
                task_id=manifest.task_id,
                task_branch=manifest.task_branch,
                reviewed_head_sha=self.repository.main_sha,
                expected_old_sha=self.repository.integration_sha,
                effect_id="EFFECT-FF-WRONG-HEAD",
            )
        self.assertEqual(caught.exception.code, "INTEGRATION_WRONG_REVIEWED_SHA_DENIED")
        with self.assertRaises(GitManagerError) as caught:
            self.manager.fast_forward_integration(
                self.repository,
                task_id=manifest.task_id,
                task_branch=manifest.task_branch,
                reviewed_head_sha=commit.head_sha,
                expected_old_sha="f" * 40,
                effect_id="EFFECT-FF-WRONG-OLD",
            )
        self.assertEqual(caught.exception.code, "INTEGRATION_WRONG_OLD_SHA_DENIED")
        main_repository = replace(self.repository, integration_branch="main")
        with self.assertRaises(GitManagerError) as caught:
            self.manager.fast_forward_integration(
                main_repository,
                task_id=manifest.task_id,
                task_branch=manifest.task_branch,
                reviewed_head_sha=commit.head_sha,
                expected_old_sha=self.repository.integration_sha,
                effect_id="EFFECT-FF-MAIN",
            )
        self.assertEqual(caught.exception.code, "INTEGRATION_MAIN_DENIED")

    def test_branch_commit_and_ff_effects_are_idempotent(self) -> None:
        manifest, worktree, commit = self._commit()
        replay = self.manager.commit_task(
            worktree,
            manifest,
            expected_parent_sha=manifest.baseline_sha,
            effect_id="EFFECT-COMMIT-ONE",
        )
        self.assertEqual(replay.head_sha, commit.head_sha)
        first = self.manager.fast_forward_integration(
            self.repository,
            task_id=manifest.task_id,
            task_branch=manifest.task_branch,
            reviewed_head_sha=commit.head_sha,
            expected_old_sha=self.repository.integration_sha,
            effect_id="EFFECT-FF-IDEMPOTENT",
        )
        # Replay sees a completed effect but still verifies the exact resulting ref.
        observed = self.manager.fast_forward_integration(
            self.repository,
            task_id=manifest.task_id,
            task_branch=manifest.task_branch,
            reviewed_head_sha=commit.head_sha,
            expected_old_sha=self.repository.integration_sha,
            effect_id="EFFECT-FF-IDEMPOTENT",
        )
        self.assertEqual(observed, first)


if __name__ == "__main__":
    unittest.main()
