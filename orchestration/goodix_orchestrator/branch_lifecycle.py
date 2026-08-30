# SPDX-License-Identifier: GPL-2.0-or-later
"""O003 exact-SHA development/task branch lifecycle."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .git_manager import CommitResult, GitManager, TaskWorktree
from .persistence import (
    BranchCreateIntent,
    CommitIntent,
    DevelopmentInitIntent,
    EffectKind,
    EffectRequestAction,
    EffectStatus,
    GitStateRecord,
    IntegrationFFIntent,
    PushIntent,
    ReconciliationOutcome,
    SQLiteStateStore,
    TaskCleanupIntent,
)
from .protocols import TaskManifest


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
        worktree_root: str | Path | None = None,
    ) -> None:
        self.repository = Path(repository).resolve(strict=True)
        self.store = store
        self.remote = remote
        proposed_root = Path(worktree_root or (self.store.path.parent / "worktrees"))
        if not proposed_root.is_absolute():
            raise BranchLifecycleError("WORKTREE_ROOT_NOT_ABSOLUTE", str(proposed_root))
        if proposed_root.exists() and proposed_root.is_symlink():
            raise BranchLifecycleError("WORKTREE_ROOT_SYMLINK_DENIED", str(proposed_root))
        proposed_root.mkdir(parents=True, exist_ok=True)
        self.worktree_root = proposed_root.resolve(strict=True)
        try:
            self.worktree_root.relative_to(self.repository)
        except ValueError:
            pass
        else:
            raise BranchLifecycleError(
                "WORKTREE_ROOT_INSIDE_REPOSITORY_DENIED", str(self.worktree_root)
            )
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

    def create_task_worktree(
        self,
        *,
        task_id: str,
        expected_development_sha: str,
        effect_id: str,
    ) -> TaskWorktree:
        branch = self.task_branch(task_id)
        if _SHA_RE.fullmatch(expected_development_sha) is None:
            raise BranchLifecycleError("INVALID_DEVELOPMENT_SHA", expected_development_sha)
        local_development = self._sha(f"refs/heads/{DEVELOPMENT_BRANCH}")
        remote_development = self._remote_sha(DEVELOPMENT_BRANCH)
        if local_development != expected_development_sha or remote_development != expected_development_sha:
            raise BranchLifecycleError(
                "DEVELOPMENT_BASELINE_MISMATCH",
                repr((local_development, remote_development)),
            )
        self.assert_single_task(allowed_task_id=task_id)
        worktree = self.worktree_root / task_id
        if worktree.parent.resolve(strict=True) != self.worktree_root:
            raise BranchLifecycleError("WORKTREE_PATH_ESCAPE_DENIED", str(worktree))
        if worktree.exists() and worktree.is_symlink():
            raise BranchLifecycleError("WORKTREE_SYMLINK_DENIED", str(worktree))
        branch_head = self._sha(f"refs/heads/{branch}", optional=True)
        bound_worktree = self._worktree_for_branch(branch)
        existing = self.store.load_effect(effect_id)
        if existing is not None and existing.status is EffectStatus.IN_PROGRESS:
            if (
                branch_head == expected_development_sha
                and bound_worktree == worktree
                and worktree.is_dir()
            ):
                self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
            else:
                raise BranchLifecycleError(
                    "TASK_CREATE_OUTCOME_AMBIGUOUS_PRESERVE_TASK",
                    repr((branch_head, bound_worktree)),
                )
        else:
            request = self.store.request_effect(
                effect_id=effect_id,
                idempotency_key=f"{task_id}:BRANCH_CREATE:{branch}:{expected_development_sha}",
                kind=EffectKind.BRANCH_CREATE,
                intent=BranchCreateIntent(
                    task_id, branch, DEVELOPMENT_BRANCH, expected_development_sha
                ),
            )
            if request.action is EffectRequestAction.EXECUTE:
                if branch_head is not None or bound_worktree is not None or worktree.exists():
                    raise BranchLifecycleError(
                        "TASK_ALREADY_EXISTS_PRESERVE_TASK",
                        repr((branch_head, bound_worktree, worktree.exists())),
                    )
                self.store.begin_effect(effect_id)
                self._git(
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(worktree),
                    expected_development_sha,
                )
                self.store.complete_effect(effect_id)
        GitManager._validate_worktree_gitfile(self.repository, worktree)
        actual_head = GitManager._text(worktree, ("rev-parse", "HEAD"))
        actual_branch = GitManager._text(worktree, ("branch", "--show-current"))
        if actual_head != expected_development_sha or actual_branch != branch:
            raise BranchLifecycleError(
                "TASK_WORKTREE_MISMATCH_PRESERVE_TASK",
                f"{actual_branch}@{actual_head}",
            )
        self.store.save_git_state(
            GitStateRecord(
                DEVELOPMENT_BRANCH,
                expected_development_sha,
                str(worktree),
                main_sha=self._sha("refs/heads/main"),
                task_id=task_id,
                task_branch=branch,
            )
        )
        return TaskWorktree(worktree, self.repository, branch, expected_development_sha)

    @staticmethod
    def _scope_paths(worktree: TaskWorktree, manifest: TaskManifest) -> tuple[str, ...]:
        GitManager._validate_worktree_gitfile(worktree.repository_root, worktree.root)
        paths = GitManager._status_paths(worktree.root)
        if not paths:
            raise BranchLifecycleError("NO_TASK_CHANGES", manifest.task_id)
        scopes = tuple(GitManager._normalized_scope_path(item) for item in manifest.scope.paths)
        for relative in paths:
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or ".git" in pure.parts:
                raise BranchLifecycleError("GIT_METADATA_CHANGE_DENIED", relative)
            allowed = any(
                relative == scope or (directory and relative.startswith(scope + "/"))
                for scope, directory in scopes
            )
            if not allowed:
                raise BranchLifecycleError("OUT_OF_SCOPE_CHANGE_DENIED", relative)
            candidate = worktree.root / relative
            if candidate.is_symlink():
                raise BranchLifecycleError("SYMLINK_PATH_ESCAPE_DENIED", relative)
        if GitManager._git(worktree.root, ("diff", "--check"), check=False).returncode != 0:
            raise BranchLifecycleError("DIFF_CHECK_FAILURE_DENIED", "tracked diff")
        return paths

    def commit_task(
        self,
        worktree: TaskWorktree,
        manifest: TaskManifest,
        *,
        expected_parent_sha: str,
        effect_id: str,
    ) -> CommitResult:
        branch = self.task_branch(manifest.task_id)
        if worktree.branch != branch or worktree.repository_root != self.repository:
            raise BranchLifecycleError("TASK_WORKTREE_BINDING_MISMATCH", branch)
        current_branch = GitManager._text(worktree.root, ("branch", "--show-current"))
        current_head = GitManager._text(worktree.root, ("rev-parse", "HEAD"))
        if current_branch != branch:
            raise BranchLifecycleError("TASK_HEAD_MISMATCH", current_branch)
        intent = CommitIntent(manifest.task_id, branch, expected_parent_sha)
        existing = self.store.load_effect(effect_id)
        if existing is not None and existing.status is EffectStatus.IN_PROGRESS:
            if current_head != expected_parent_sha and GitManager._is_ancestor(
                worktree.root, expected_parent_sha, current_head
            ):
                self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
            else:
                raise BranchLifecycleError(
                    "TASK_COMMIT_OUTCOME_AMBIGUOUS_PRESERVE_TASK", current_head
                )
        else:
            request = self.store.request_effect(
                effect_id=effect_id,
                idempotency_key=f"{manifest.task_id}:COMMIT:{expected_parent_sha}",
                kind=EffectKind.COMMIT,
                intent=intent,
            )
            if request.action is EffectRequestAction.EXECUTE:
                if current_head != expected_parent_sha:
                    raise BranchLifecycleError("TASK_HEAD_MISMATCH", current_head)
                paths = self._scope_paths(worktree, manifest)
                self.store.begin_effect(effect_id)
                GitManager._git(worktree.root, ("add", "--", *paths))
                if GitManager._git(
                    worktree.root, ("diff", "--cached", "--check"), check=False
                ).returncode != 0:
                    raise BranchLifecycleError("DIFF_CHECK_FAILURE_DENIED", "staged")
                title = " ".join(manifest.title.split())[:120]
                GitManager._git(
                    worktree.root,
                    ("commit", "-m", f"{manifest.task_id}: {title}"),
                )
                self.store.complete_effect(effect_id)
        head = GitManager._text(worktree.root, ("rev-parse", "HEAD"))
        if head == expected_parent_sha or not GitManager._is_ancestor(
            worktree.root, expected_parent_sha, head
        ):
            raise BranchLifecycleError("TASK_COMMIT_NOT_CREATED", head)
        changed = tuple(
            line
            for line in GitManager._text(
                worktree.root, ("diff", "--name-only", expected_parent_sha, head)
            ).splitlines()
            if line
        )
        return CommitResult(expected_parent_sha, head, tuple(sorted(changed)))

    def push_task(
        self,
        *,
        task_id: str,
        commit_sha: str,
        expected_remote_sha: str | None,
        effect_id: str,
    ) -> str:
        branch = self.task_branch(task_id)
        if self._sha(f"refs/heads/{branch}") != commit_sha:
            raise BranchLifecycleError("TASK_PUSH_HEAD_MISMATCH", commit_sha)
        intent = PushIntent(task_id, branch, commit_sha, expected_remote_sha)
        existing = self.store.load_effect(effect_id)
        remote = self._remote_sha(branch)
        if existing is not None and existing.status is EffectStatus.IN_PROGRESS:
            if remote == commit_sha:
                self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
            else:
                raise BranchLifecycleError(
                    "TASK_PUSH_OUTCOME_AMBIGUOUS_PRESERVE_TASK", repr(remote)
                )
        else:
            request = self.store.request_effect(
                effect_id=effect_id,
                idempotency_key=f"{task_id}:PUSH:{branch}:{commit_sha}",
                kind=EffectKind.PUSH,
                intent=intent,
            )
            if request.action is EffectRequestAction.EXECUTE:
                if remote != expected_remote_sha:
                    raise BranchLifecycleError("REMOTE_TASK_DRIFT_PRESERVE_TASK", remote)
                self.store.begin_effect(effect_id)
                if expected_remote_sha is not None and not self._is_ancestor(
                    expected_remote_sha, commit_sha
                ):
                    raise BranchLifecycleError(
                        "REMOTE_TASK_NON_FF_PRESERVE_TASK", commit_sha
                    )
                self._git("push", self.remote, f"{commit_sha}:refs/heads/{branch}")
                self.store.complete_effect(effect_id)
        if self._remote_sha(branch) != commit_sha:
            raise BranchLifecycleError("TASK_PUSH_VERIFY_FAILED", branch)
        return commit_sha

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
