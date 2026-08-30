# SPDX-License-Identifier: GPL-2.0-or-later
"""Deterministic local Git operations for O002 synthetic repositories only."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from .persistence import (
    BranchCreateIntent,
    CommitIntent,
    EffectKind,
    EffectRequestAction,
    IntegrationFFIntent,
    SQLiteStateStore,
)
from .policy import ProtectedBranchError, require_ordinary_branch
from .protocols import TaskManifest


MAX_GIT_OUTPUT = 2 * 1024 * 1024
MAX_REVIEW_DIFF = 512 * 1024


@dataclass(frozen=True, slots=True)
class GitManagerError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class SyntheticRepository:
    root: Path
    main_sha: str
    integration_branch: str
    integration_sha: str


@dataclass(frozen=True, slots=True)
class TaskWorktree:
    root: Path
    repository_root: Path
    branch: str
    baseline_sha: str


@dataclass(frozen=True, slots=True)
class CommitResult:
    baseline_sha: str
    head_sha: str
    changed_paths: tuple[str, ...]


class GitManager:
    def __init__(
        self,
        *,
        goodix_root: str | Path,
        store: SQLiteStateStore,
    ) -> None:
        self.goodix_root = Path(goodix_root).resolve(strict=True)
        self.store = store

    def require_synthetic_root(self, root: str | Path) -> Path:
        candidate = Path(root).resolve(strict=False)
        try:
            candidate.relative_to(self.goodix_root)
        except ValueError:
            return candidate
        raise GitManagerError(
            "GOODIX_ROOT_REJECTED_AS_SYNTHETIC_ROOT", str(candidate)
        )

    @staticmethod
    def _git(
        repo: str | Path,
        args: Iterable[str],
        *,
        check: bool = True,
        timeout: float = 30.0,
    ) -> subprocess.CompletedProcess[bytes]:
        command = ["git", "-C", str(repo), *tuple(args)]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitManagerError("GIT_COMMAND_FAILED", type(exc).__name__) from exc
        if len(completed.stdout) > MAX_GIT_OUTPUT or len(completed.stderr) > MAX_GIT_OUTPUT:
            raise GitManagerError("GIT_OUTPUT_TOO_LARGE", "bounded output exceeded")
        if check and completed.returncode != 0:
            raise GitManagerError(
                "GIT_COMMAND_FAILED",
                f"args={tuple(args)!r},exit={completed.returncode}",
            )
        return completed

    @classmethod
    def _text(cls, repo: str | Path, args: Iterable[str]) -> str:
        return cls._git(repo, args).stdout.decode("utf-8", "strict").strip()

    def create_synthetic_repository(
        self,
        root: str | Path,
        *,
        integration_branch: str = "autopilot/integration",
    ) -> SyntheticRepository:
        candidate = self.require_synthetic_root(root)
        try:
            require_ordinary_branch(integration_branch)
        except ProtectedBranchError as exc:
            raise GitManagerError("INTEGRATION_MAIN_DENIED", integration_branch) from exc
        if candidate.exists() and any(candidate.iterdir()):
            raise GitManagerError("SYNTHETIC_ROOT_NOT_EMPTY", str(candidate))
        candidate.mkdir(parents=True, exist_ok=True)
        self._git(candidate, ("init", "-b", "main"))
        self._git(candidate, ("config", "--local", "user.name", "O002 Synthetic"))
        self._git(
            candidate,
            ("config", "--local", "user.email", "o002-synthetic.invalid@example.invalid"),
        )
        (candidate / "requirements.md").write_text(
            "# Synthetic requirements\n\n"
            "The final artifact contains alpha and beta, and the manual documents both.\n",
            encoding="utf-8",
        )
        (candidate / "artifact.txt").write_text("", encoding="utf-8")
        (candidate / "PROJECT_MANUAL.md").write_text(
            "# Synthetic project manual\n\nInitial state.\n", encoding="utf-8"
        )
        (candidate / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n", encoding="utf-8"
        )
        tests = candidate / "tests"
        tests.mkdir()
        (tests / "test_artifact.py").write_text(
            "# SPDX-License-Identifier: GPL-2.0-or-later\n"
            "import unittest\n"
            "from pathlib import Path\n\n"
            "class ArtifactTests(unittest.TestCase):\n"
            "    def test_alpha_beta_and_manual(self):\n"
            "        root = Path(__file__).resolve().parents[1]\n"
            "        artifact = (root / 'artifact.txt').read_text(encoding='utf-8')\n"
            "        manual = (root / 'PROJECT_MANUAL.md').read_text(encoding='utf-8')\n"
            "        self.assertIn('alpha', artifact)\n"
            "        self.assertIn('beta', artifact)\n"
            "        self.assertIn('alpha', manual)\n"
            "        self.assertIn('beta', manual)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
            encoding="utf-8",
        )
        self._git(candidate, ("add", "--", "."))
        self._git(candidate, ("commit", "-m", "O002 synthetic baseline"))
        main_sha = self._text(candidate, ("rev-parse", "HEAD"))
        self._git(candidate, ("branch", integration_branch, main_sha))
        integration_sha = self._text(
            candidate, ("rev-parse", f"refs/heads/{integration_branch}")
        )
        return SyntheticRepository(
            candidate, main_sha, integration_branch, integration_sha
        )

    def create_task_worktree(
        self,
        repository: SyntheticRepository,
        *,
        task_id: str,
        task_branch: str,
        worktree_path: str | Path,
        expected_integration_sha: str,
        effect_id: str,
    ) -> TaskWorktree:
        repo = self.require_synthetic_root(repository.root)
        worktree = self.require_synthetic_root(worktree_path)
        try:
            require_ordinary_branch(task_branch)
        except ProtectedBranchError as exc:
            raise GitManagerError("TASK_MAIN_DENIED", task_branch) from exc
        actual_integration = self._text(
            repo, ("rev-parse", f"refs/heads/{repository.integration_branch}")
        )
        if actual_integration != expected_integration_sha:
            raise GitManagerError(
                "INTEGRATION_BASELINE_MISMATCH",
                f"expected={expected_integration_sha},actual={actual_integration}",
            )
        intent = BranchCreateIntent(
            task_id, task_branch, repository.integration_branch, expected_integration_sha
        )
        request = self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=f"{task_id}:BRANCH_CREATE:{task_branch}",
            kind=EffectKind.BRANCH_CREATE,
            intent=intent,
        )
        if request.action is EffectRequestAction.EXECUTE:
            self.store.begin_effect(effect_id)
            worktree.parent.mkdir(parents=True, exist_ok=True)
            self._git(
                repo,
                (
                    "worktree",
                    "add",
                    "-b",
                    task_branch,
                    str(worktree),
                    expected_integration_sha,
                ),
            )
            self.store.complete_effect(effect_id)
        self._validate_worktree_gitfile(repo, worktree)
        actual_head = self._text(worktree, ("rev-parse", "HEAD"))
        actual_branch = self._text(worktree, ("branch", "--show-current"))
        if actual_head != expected_integration_sha or actual_branch != task_branch:
            raise GitManagerError(
                "TASK_WORKTREE_MISMATCH", f"{actual_branch}@{actual_head}"
            )
        return TaskWorktree(worktree, repo, task_branch, expected_integration_sha)

    @staticmethod
    def _validate_worktree_gitfile(repo: Path, worktree: Path) -> None:
        marker = worktree / ".git"
        if not marker.is_file() or marker.is_symlink():
            raise GitManagerError("GIT_METADATA_CHANGE_DENIED", str(marker))
        content = marker.read_text(encoding="utf-8", errors="strict").strip()
        if not content.startswith("gitdir: "):
            raise GitManagerError("GIT_METADATA_CHANGE_DENIED", "malformed gitfile")
        gitdir = Path(content.removeprefix("gitdir: ")).resolve(strict=True)
        expected_parent = (repo / ".git" / "worktrees").resolve(strict=True)
        try:
            gitdir.relative_to(expected_parent)
        except ValueError as exc:
            raise GitManagerError("GIT_METADATA_CHANGE_DENIED", str(gitdir)) from exc

    @staticmethod
    def _status_paths(worktree: Path) -> tuple[str, ...]:
        completed = GitManager._git(
            worktree, ("status", "--porcelain=v1", "-z", "--untracked-files=all")
        )
        entries = completed.stdout.split(b"\0")
        paths: list[str] = []
        for entry in entries:
            if not entry:
                continue
            if len(entry) < 4:
                raise GitManagerError("GIT_STATUS_MALFORMED", repr(entry[:32]))
            status = entry[:2]
            if b"R" in status or b"C" in status:
                raise GitManagerError("GIT_RENAME_CHANGE_DENIED", status.decode("ascii"))
            try:
                path = entry[3:].decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise GitManagerError("GIT_STATUS_MALFORMED", "non-UTF8 path") from exc
            paths.append(path)
        return tuple(sorted(set(paths)))

    @staticmethod
    def _normalized_scope_path(value: str) -> tuple[str, bool]:
        if not isinstance(value, str) or not value:
            raise GitManagerError("INVALID_SCOPE_PATH", repr(value))
        pure = PurePosixPath(value)
        if pure.is_absolute() or ".." in pure.parts or ".git" in pure.parts:
            raise GitManagerError("INVALID_SCOPE_PATH", value)
        normalized = pure.as_posix().removeprefix("./").rstrip("/")
        if not normalized or normalized == ".":
            raise GitManagerError("INVALID_SCOPE_PATH", value)
        return normalized, value.endswith("/")

    def enforce_scope(
        self, worktree: TaskWorktree, manifest: TaskManifest
    ) -> tuple[str, ...]:
        repo = self.require_synthetic_root(worktree.root)
        self._validate_worktree_gitfile(worktree.repository_root, repo)
        paths = self._status_paths(repo)
        if not paths:
            raise GitManagerError("NO_TASK_CHANGES", manifest.task_id)
        scopes = tuple(self._normalized_scope_path(item) for item in manifest.scope.paths)
        for relative in paths:
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or ".git" in pure.parts:
                raise GitManagerError("GIT_METADATA_CHANGE_DENIED", relative)
            allowed = any(
                relative == scope or (is_directory and relative.startswith(scope + "/"))
                for scope, is_directory in scopes
            )
            if not allowed:
                raise GitManagerError("OUT_OF_SCOPE_CHANGE_DENIED", relative)
            candidate = (repo / relative)
            if candidate.is_symlink():
                raise GitManagerError("SYMLINK_PATH_ESCAPE_DENIED", relative)
            if candidate.exists() and candidate.is_file():
                try:
                    with candidate.open("rb") as stream:
                        for line in stream:
                            content = line.rstrip(b"\r\n")
                            if content.endswith((b" ", b"\t")):
                                raise GitManagerError("DIFF_CHECK_FAILURE_DENIED", relative)
                except OSError as exc:
                    raise GitManagerError("SCOPE_FILE_READ_FAILED", relative) from exc
        diff_check = self._git(repo, ("diff", "--check"), check=False)
        if diff_check.returncode != 0:
            raise GitManagerError("DIFF_CHECK_FAILURE_DENIED", "tracked diff")
        head = self._text(repo, ("rev-parse", "HEAD"))
        if head != worktree.baseline_sha and not self._is_ancestor(
            repo, worktree.baseline_sha, head
        ):
            raise GitManagerError("TASK_BASELINE_ANCESTRY_MISMATCH", head)
        return paths

    @staticmethod
    def _repo_root(worktree: Path) -> Path:
        common = GitManager._text(worktree, ("rev-parse", "--git-common-dir"))
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = (worktree / common_path).resolve(strict=True)
        else:
            common_path = common_path.resolve(strict=True)
        return common_path.parent

    @classmethod
    def _is_ancestor(cls, repo: Path, old: str, new: str) -> bool:
        result = cls._git(repo, ("merge-base", "--is-ancestor", old, new), check=False)
        if result.returncode not in (0, 1):
            raise GitManagerError("GIT_ANCESTRY_AMBIGUOUS", f"exit={result.returncode}")
        return result.returncode == 0

    def commit_task(
        self,
        worktree: TaskWorktree,
        manifest: TaskManifest,
        *,
        expected_parent_sha: str,
        effect_id: str,
    ) -> CommitResult:
        repo = self.require_synthetic_root(worktree.root)
        current_branch = self._text(repo, ("branch", "--show-current"))
        current_head = self._text(repo, ("rev-parse", "HEAD"))
        if current_branch != worktree.branch:
            raise GitManagerError(
                "TASK_HEAD_MISMATCH", f"{current_branch}@{current_head}"
            )
        intent = CommitIntent(manifest.task_id, worktree.branch, expected_parent_sha)
        request = self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=f"{manifest.task_id}:COMMIT:{expected_parent_sha}",
            kind=EffectKind.COMMIT,
            intent=intent,
        )
        if request.action is EffectRequestAction.SKIP_COMPLETED:
            if current_head == expected_parent_sha or not self._is_ancestor(
                repo, expected_parent_sha, current_head
            ):
                raise GitManagerError("TASK_COMMIT_RECONCILIATION_FAILED", current_head)
            changed = tuple(
                line
                for line in self._text(
                    repo, ("diff", "--name-only", expected_parent_sha, current_head)
                ).splitlines()
                if line
            )
            return CommitResult(expected_parent_sha, current_head, tuple(sorted(changed)))
        if current_head != expected_parent_sha:
            raise GitManagerError(
                "TASK_HEAD_MISMATCH", f"{current_branch}@{current_head}"
            )
        paths = self.enforce_scope(worktree, manifest)
        if request.action is EffectRequestAction.EXECUTE:
            self.store.begin_effect(effect_id)
            self._git(repo, ("add", "--", *paths))
            check = self._git(repo, ("diff", "--cached", "--check"), check=False)
            if check.returncode != 0:
                raise GitManagerError("DIFF_CHECK_FAILURE_DENIED", "staged diff")
            safe_title = " ".join(manifest.title.split())[:120]
            self._git(
                repo,
                ("commit", "-m", f"O002 synthetic {manifest.task_id}: {safe_title}"),
            )
            self.store.complete_effect(effect_id)
        head = self._text(repo, ("rev-parse", "HEAD"))
        if head == expected_parent_sha or not self._is_ancestor(repo, expected_parent_sha, head):
            raise GitManagerError("TASK_COMMIT_NOT_CREATED", head)
        changed = tuple(
            line
            for line in self._text(
                repo, ("diff", "--name-only", expected_parent_sha, head)
            ).splitlines()
            if line
        )
        if set(changed) != set(paths):
            raise GitManagerError(
                "COMMIT_CHANGED_PATH_MISMATCH", repr((paths, changed))
            )
        return CommitResult(expected_parent_sha, head, tuple(sorted(changed)))

    def review_diff(self, repo: str | Path, baseline: str, head: str) -> str:
        completed = self._git(repo, ("diff", "--no-ext-diff", baseline, head))
        if len(completed.stdout) > MAX_REVIEW_DIFF:
            raise GitManagerError("REVIEW_DIFF_TOO_LARGE", str(len(completed.stdout)))
        return completed.stdout.decode("utf-8", "strict")

    def fast_forward_integration(
        self,
        repository: SyntheticRepository,
        *,
        task_id: str,
        task_branch: str,
        reviewed_head_sha: str,
        expected_old_sha: str,
        effect_id: str,
    ) -> str:
        repo = self.require_synthetic_root(repository.root)
        target = repository.integration_branch
        try:
            require_ordinary_branch(target)
        except ProtectedBranchError as exc:
            raise GitManagerError("INTEGRATION_MAIN_DENIED", target) from exc
        if target in {"main", "heads/main", "refs/heads/main"}:
            raise GitManagerError("INTEGRATION_MAIN_DENIED", target)
        actual_task_head = self._text(repo, ("rev-parse", f"refs/heads/{task_branch}"))
        if actual_task_head != reviewed_head_sha:
            raise GitManagerError(
                "INTEGRATION_WRONG_REVIEWED_SHA_DENIED",
                f"reviewed={reviewed_head_sha},actual={actual_task_head}",
            )
        intent = IntegrationFFIntent(
            task_id, task_branch, target, expected_old_sha, reviewed_head_sha
        )
        request = self.store.request_effect(
            effect_id=effect_id,
            idempotency_key=f"{task_id}:INTEGRATION_FF:{expected_old_sha}:{reviewed_head_sha}",
            kind=EffectKind.INTEGRATION_FF,
            intent=intent,
        )
        if request.action is EffectRequestAction.SKIP_COMPLETED:
            observed = self._text(repo, ("rev-parse", f"refs/heads/{target}"))
            if observed != reviewed_head_sha:
                raise GitManagerError("INTEGRATION_FF_RECONCILIATION_FAILED", observed)
            main_sha = self._text(repo, ("rev-parse", "refs/heads/main"))
            if main_sha != repository.main_sha:
                raise GitManagerError("MAIN_UPDATE_DENIED", main_sha)
            return observed
        actual_old = self._text(repo, ("rev-parse", f"refs/heads/{target}"))
        if actual_old != expected_old_sha:
            raise GitManagerError(
                "INTEGRATION_WRONG_OLD_SHA_DENIED",
                f"expected={expected_old_sha},actual={actual_old}",
            )
        if not self._is_ancestor(repo, expected_old_sha, reviewed_head_sha):
            raise GitManagerError("INTEGRATION_NON_FF_DENIED", reviewed_head_sha)
        if request.action is EffectRequestAction.EXECUTE:
            self.store.begin_effect(effect_id)
            self._git(
                repo,
                (
                    "update-ref",
                    f"refs/heads/{target}",
                    reviewed_head_sha,
                    expected_old_sha,
                ),
            )
            self.store.complete_effect(effect_id)
        observed = self._text(repo, ("rev-parse", f"refs/heads/{target}"))
        if observed != reviewed_head_sha:
            raise GitManagerError("INTEGRATION_FF_VERIFY_FAILED", observed)
        main_sha = self._text(repo, ("rev-parse", "refs/heads/main"))
        if main_sha != repository.main_sha:
            raise GitManagerError("MAIN_UPDATE_DENIED", main_sha)
        return observed
