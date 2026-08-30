# SPDX-License-Identifier: GPL-2.0-or-later
"""O003 exact-SHA development/task branch lifecycle."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .persistence import (
    DevelopmentInitIntent,
    EffectKind,
    EffectRequestAction,
    EffectStatus,
    GitStateRecord,
    IntegrationFFIntent,
    ReconciliationOutcome,
    SQLiteStateStore,
    TaskCleanupIntent,
)


DEVELOPMENT_BRANCH = "development"
MAIN_BRANCH = "main"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TASK_ID_RE = re.compile(r"^TASK-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")


@dataclass(frozen=True, slots=True)
class BranchLifecycleError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class CleanupResult:
    integration_verified: bool
    worktree_removed: bool
    local_branch_deleted: bool
    remote_branch_deleted: bool


class BranchLifecycle:
    def __init__(
        self,
        repository: str | Path,
        store: SQLiteStateStore,
        *,
        remote: str = "origin",
    ) -> None:
        self.repository = Path(repository).resolve(strict=True)
        self.store = store
        self.remote = remote
        root = self._text("rev-parse", "--show-toplevel")
        if Path(root).resolve(strict=True) != self.repository:
            raise BranchLifecycleError("REPOSITORY_ROOT_MISMATCH", root)

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        completed = subprocess.run(
            ("git", "-C", str(self.repository), *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        if check and completed.returncode != 0:
            raise BranchLifecycleError(
                "GIT_COMMAND_FAILED", f"git {args[0]} exit={completed.returncode}"
            )
        return completed

    def _text(self, *args: str) -> str:
        return self._git(*args).stdout.decode("utf-8", "strict").strip()

    @staticmethod
    def task_branch(task_id: str) -> str:
        if _TASK_ID_RE.fullmatch(task_id) is None:
            raise BranchLifecycleError("INVALID_TASK_ID", task_id)
        return f"task/{task_id}"

    def _sha(self, ref: str, *, optional: bool = False) -> str | None:
        completed = self._git("rev-parse", "--verify", ref, check=False)
        if completed.returncode != 0:
            if optional:
                return None
            raise BranchLifecycleError("MISSING_REF", ref)
        value = completed.stdout.decode("ascii", "strict").strip()
        if _SHA_RE.fullmatch(value) is None:
            raise BranchLifecycleError("INVALID_REF_SHA", ref)
        return value

    def _is_ancestor(self, old: str, new: str) -> bool:
        result = self._git("merge-base", "--is-ancestor", old, new, check=False)
        if result.returncode not in (0, 1):
            raise BranchLifecycleError("ANCESTRY_AMBIGUOUS", f"{old}->{new}")
        return result.returncode == 0

    def _remote_sha(self, branch: str) -> str | None:
        result = self._git("ls-remote", "--heads", self.remote, branch)
        lines = [line for line in result.stdout.decode("ascii", "strict").splitlines() if line]
        if not lines:
            return None
        if len(lines) != 1:
            raise BranchLifecycleError("REMOTE_REF_AMBIGUOUS", branch)
        sha, ref = lines[0].split("\t", 1)
        if ref != f"refs/heads/{branch}" or _SHA_RE.fullmatch(sha) is None:
            raise BranchLifecycleError("REMOTE_REF_INVALID", lines[0])
        return sha

    def _worktree_for_branch(self, branch: str) -> Path | None:
        output = self._text("worktree", "list", "--porcelain")
        matches: list[Path] = []
        current_path: Path | None = None
        for line in output.splitlines():
            if line.startswith("worktree "):
                current_path = Path(line.removeprefix("worktree ")).resolve()
            elif line == f"branch refs/heads/{branch}" and current_path is not None:
                matches.append(current_path)
        if len(matches) > 1:
            raise BranchLifecycleError("TASK_WORKTREE_AMBIGUOUS", branch)
        return matches[0] if matches else None

    def initialize_development(self, accepted_sha: str, *, effect_id: str) -> str:
        if _SHA_RE.fullmatch(accepted_sha) is None:
            raise BranchLifecycleError("INVALID_ACCEPTED_SHA", accepted_sha)
        self._sha(accepted_sha)
        intent = DevelopmentInitIntent(accepted_sha)
        effect = self.store.load_effect(effect_id)
        local = self._sha(f"refs/heads/{DEVELOPMENT_BRANCH}", optional=True)
        remote = self._remote_sha(DEVELOPMENT_BRANCH)
        if effect is not None and effect.status is EffectStatus.IN_PROGRESS:
            if local == remote == accepted_sha:
                self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
                self.store.save_git_state(
                    GitStateRecord(DEVELOPMENT_BRANCH, accepted_sha, main_sha=self._sha("refs/heads/main"))
                )
                return accepted_sha
            if local == accepted_sha and remote is None:
                self._git("push", self.remote, f"{accepted_sha}:refs/heads/{DEVELOPMENT_BRANCH}")
                if self._remote_sha(DEVELOPMENT_BRANCH) != accepted_sha:
                    raise BranchLifecycleError("DEVELOPMENT_INIT_VERIFY_FAILED", "remote")
                self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
                self.store.save_git_state(
                    GitStateRecord(DEVELOPMENT_BRANCH, accepted_sha, main_sha=self._sha("refs/heads/main"))
                )
                return accepted_sha
            if local is None and remote == accepted_sha:
                self._git("update-ref", f"refs/heads/{DEVELOPMENT_BRANCH}", accepted_sha, "0" * 40)
                self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
                self.store.save_git_state(
                    GitStateRecord(DEVELOPMENT_BRANCH, accepted_sha, main_sha=self._sha("refs/heads/main"))
                )
                return accepted_sha
            raise BranchLifecycleError("DEVELOPMENT_INIT_AMBIGUOUS", repr((local, remote)))
        request = self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=f"DEVELOPMENT_INIT:{accepted_sha}",
            kind=EffectKind.DEVELOPMENT_INIT,
            intent=intent,
        )
        if request.action is EffectRequestAction.SKIP_COMPLETED:
            if local != accepted_sha or remote != accepted_sha:
                raise BranchLifecycleError("DEVELOPMENT_INIT_RECONCILIATION_FAILED", repr((local, remote)))
            self.store.save_git_state(
                GitStateRecord(DEVELOPMENT_BRANCH, accepted_sha, main_sha=self._sha("refs/heads/main"))
            )
            return accepted_sha
        if local is not None or remote is not None:
            raise BranchLifecycleError("DEVELOPMENT_ALREADY_EXISTS", repr((local, remote)))
        self.store.begin_effect(effect_id)
        self._git("update-ref", f"refs/heads/{DEVELOPMENT_BRANCH}", accepted_sha, "0" * 40)
        self._git("push", self.remote, f"{accepted_sha}:refs/heads/{DEVELOPMENT_BRANCH}")
        local = self._sha(f"refs/heads/{DEVELOPMENT_BRANCH}")
        remote = self._remote_sha(DEVELOPMENT_BRANCH)
        if local != accepted_sha or remote != accepted_sha:
            raise BranchLifecycleError("DEVELOPMENT_INIT_VERIFY_FAILED", repr((local, remote)))
        self.store.complete_effect(effect_id)
        self.store.save_git_state(
            GitStateRecord(DEVELOPMENT_BRANCH, accepted_sha, main_sha=self._sha("refs/heads/main"))
        )
        return accepted_sha

    def assert_single_task(self, *, allowed_task_id: str | None = None) -> None:
        allowed = self.task_branch(allowed_task_id) if allowed_task_id else None
        refs = tuple(
            line
            for line in self._text("for-each-ref", "--format=%(refname:short)", "refs/heads/task/").splitlines()
            if line
        )
        unexpected = tuple(ref for ref in refs if ref != allowed)
        if unexpected or (allowed is None and refs):
            raise BranchLifecycleError("MAX_CONCURRENT_TASKS_EXCEEDED", repr(refs))

    def fast_forward_development(
        self,
        *,
        task_id: str,
        reviewed_head_sha: str,
        expected_old_sha: str,
        effect_id: str,
    ) -> str:
        branch = self.task_branch(task_id)
        task_head = self._sha(f"refs/heads/{branch}")
        if task_head != reviewed_head_sha:
            raise BranchLifecycleError("REVIEWED_SHA_MISMATCH", repr((reviewed_head_sha, task_head)))
        existing_effect = self.store.load_effect(effect_id)
        if existing_effect is not None and existing_effect.status in {
            EffectStatus.IN_PROGRESS,
            EffectStatus.COMPLETED,
        }:
            observed_local = self._sha(f"refs/heads/{DEVELOPMENT_BRANCH}")
            observed_remote = self._remote_sha(DEVELOPMENT_BRANCH)
            if observed_local == observed_remote == reviewed_head_sha and self._is_ancestor(
                expected_old_sha, reviewed_head_sha
            ):
                if existing_effect.status is EffectStatus.IN_PROGRESS:
                    self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
                self.store.save_git_state(
                    GitStateRecord(
                        DEVELOPMENT_BRANCH,
                        reviewed_head_sha,
                        main_sha=self._sha("refs/heads/main"),
                        task_id=task_id,
                        task_branch=branch,
                        reviewed_head_sha=reviewed_head_sha,
                        integration_verified=True,
                    )
                )
                return reviewed_head_sha
            if existing_effect.status is EffectStatus.IN_PROGRESS:
                raise BranchLifecycleError(
                    "INTEGRATION_OUTCOME_AMBIGUOUS_PRESERVE_TASK",
                    repr((observed_local, observed_remote)),
                )
        local_old = self._sha(f"refs/heads/{DEVELOPMENT_BRANCH}")
        remote_old = self._remote_sha(DEVELOPMENT_BRANCH)
        main_before = self._sha(f"refs/heads/{MAIN_BRANCH}")
        if local_old != expected_old_sha or remote_old != expected_old_sha:
            raise BranchLifecycleError("DEVELOPMENT_EXPECTED_OLD_MISMATCH", repr((local_old, remote_old)))
        if not self._is_ancestor(expected_old_sha, reviewed_head_sha):
            raise BranchLifecycleError("DEVELOPMENT_NON_FF_DENIED", reviewed_head_sha)
        intent = IntegrationFFIntent(
            task_id, branch, DEVELOPMENT_BRANCH, expected_old_sha, reviewed_head_sha
        )
        request = self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=f"{task_id}:DEVELOPMENT_FF:{expected_old_sha}:{reviewed_head_sha}",
            kind=EffectKind.INTEGRATION_FF,
            intent=intent,
        )
        if request.action is EffectRequestAction.EXECUTE:
            self.store.begin_effect(effect_id)
            self._git(
                "update-ref",
                f"refs/heads/{DEVELOPMENT_BRANCH}",
                reviewed_head_sha,
                expected_old_sha,
            )
            self._git(
                "push",
                self.remote,
                f"refs/heads/{DEVELOPMENT_BRANCH}:refs/heads/{DEVELOPMENT_BRANCH}",
            )
            self.store.complete_effect(effect_id)
        local = self._sha(f"refs/heads/{DEVELOPMENT_BRANCH}")
        remote = self._remote_sha(DEVELOPMENT_BRANCH)
        main = self._sha(f"refs/heads/{MAIN_BRANCH}")
        if local != reviewed_head_sha or remote != reviewed_head_sha:
            raise BranchLifecycleError("DEVELOPMENT_FF_VERIFY_FAILED", repr((local, remote)))
        if not self._is_ancestor(reviewed_head_sha, local):
            raise BranchLifecycleError("ACCEPTED_HEAD_NOT_REACHABLE", reviewed_head_sha)
        if main != main_before:
            raise BranchLifecycleError("MAIN_UPDATE_DENIED", repr((main_before, main)))
        previous = self.store.load_git_state()
        self.store.save_git_state(
            GitStateRecord(
                DEVELOPMENT_BRANCH,
                reviewed_head_sha,
                previous.task_worktree if previous else None,
                main_sha=main,
                task_id=task_id,
                task_branch=branch,
                reviewed_head_sha=reviewed_head_sha,
                integration_verified=True,
                cleanup_status="NOT_STARTED",
            )
        )
        return reviewed_head_sha

    def cleanup_verified_task(
        self,
        *,
        task_id: str,
        accepted_sha: str,
        worktree: str | Path,
        remote_branch_exists: bool,
    ) -> CleanupResult:
        branch = self.task_branch(task_id)
        worktree_path = Path(worktree).resolve()
        development = self._sha(f"refs/heads/{DEVELOPMENT_BRANCH}")
        remote_development = self._remote_sha(DEVELOPMENT_BRANCH)
        if development != accepted_sha or remote_development != accepted_sha:
            raise BranchLifecycleError("INTEGRATION_NOT_VERIFIED_PRESERVE_TASK", repr((development, remote_development)))
        if not self._is_ancestor(accepted_sha, development):
            raise BranchLifecycleError("ACCEPTED_HEAD_NOT_REACHABLE_PRESERVE_TASK", accepted_sha)
        task_head = self._sha(f"refs/heads/{branch}", optional=True)
        if task_head is not None and task_head != accepted_sha:
            raise BranchLifecycleError("TASK_HEAD_CHANGED_PRESERVE_TASK", task_head)
        bound_worktree = self._worktree_for_branch(branch)
        if worktree_path.exists() and bound_worktree != worktree_path:
            raise BranchLifecycleError(
                "TASK_WORKTREE_BINDING_MISMATCH_PRESERVE_TASK",
                repr((worktree_path, bound_worktree)),
            )
        if not worktree_path.exists() and bound_worktree is not None:
            raise BranchLifecycleError(
                "TASK_WORKTREE_PATH_MISMATCH_PRESERVE_TASK",
                repr((worktree_path, bound_worktree)),
            )
        intent = TaskCleanupIntent(task_id, branch, accepted_sha, development)

        worktree_removed = not worktree_path.exists()
        worktree_effect = f"EFFECT-CLEANUP-WORKTREE-{task_id}"
        request = self._cleanup_request(worktree_effect, EffectKind.TASK_WORKTREE_REMOVE, intent, worktree_removed)
        if request and not worktree_removed:
            self.store.begin_effect(worktree_effect)
            self._git("worktree", "remove", str(worktree_path))
            worktree_removed = not worktree_path.exists() and self._worktree_for_branch(branch) is None
            if not worktree_removed:
                raise BranchLifecycleError("WORKTREE_REMOVE_VERIFY_FAILED", str(worktree_path))
            self.store.complete_effect(worktree_effect)

        local_deleted = self._sha(f"refs/heads/{branch}", optional=True) is None
        local_effect = f"EFFECT-CLEANUP-LOCAL-{task_id}"
        request = self._cleanup_request(local_effect, EffectKind.TASK_LOCAL_BRANCH_DELETE, intent, local_deleted)
        if request and not local_deleted:
            self.store.begin_effect(local_effect)
            self._git("update-ref", "-d", f"refs/heads/{branch}", accepted_sha)
            local_deleted = self._sha(f"refs/heads/{branch}", optional=True) is None
            if not local_deleted:
                raise BranchLifecycleError("LOCAL_BRANCH_DELETE_VERIFY_FAILED", branch)
            self.store.complete_effect(local_effect)

        remote_deleted = self._remote_sha(branch) is None
        if not remote_branch_exists and not remote_deleted:
            raise BranchLifecycleError("UNEXPECTED_REMOTE_TASK_BRANCH_PRESERVE_TASK", branch)
        remote_effect = f"EFFECT-CLEANUP-REMOTE-{task_id}"
        request = self._cleanup_request(remote_effect, EffectKind.TASK_REMOTE_BRANCH_DELETE, intent, remote_deleted)
        if request and remote_branch_exists and not remote_deleted:
            self.store.begin_effect(remote_effect)
            self._git("push", self.remote, "--delete", branch)
            remote_deleted = self._remote_sha(branch) is None
            if not remote_deleted:
                raise BranchLifecycleError("REMOTE_BRANCH_DELETE_VERIFY_FAILED", branch)
            self.store.complete_effect(remote_effect)
        elif request and remote_deleted:
            self.store.begin_effect(remote_effect)
            self.store.complete_effect(remote_effect)

        result = CleanupResult(True, worktree_removed, local_deleted, remote_deleted)
        self.store.save_git_state(
            GitStateRecord(
                DEVELOPMENT_BRANCH,
                accepted_sha,
                main_sha=self._sha("refs/heads/main"),
                reviewed_head_sha=accepted_sha,
                integration_verified=True,
                cleanup_status="PASS" if all((worktree_removed, local_deleted, remote_deleted)) else "IN_PROGRESS",
            )
        )
        return result

    def _cleanup_request(
        self,
        effect_id: str,
        kind: EffectKind,
        intent: TaskCleanupIntent,
        already_done: bool,
    ) -> bool:
        effect = self.store.load_effect(effect_id)
        if effect is not None and effect.status is EffectStatus.IN_PROGRESS:
            if not already_done:
                raise BranchLifecycleError("CLEANUP_OUTCOME_AMBIGUOUS_PRESERVE_TASK", effect_id)
            self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
            return False
        request = self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=effect_id,
            kind=kind,
            intent=intent,
        )
        return request.action is EffectRequestAction.EXECUTE
