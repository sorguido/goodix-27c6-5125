# SPDX-License-Identifier: GPL-2.0-or-later
"""Trusted data-only verifier for the disposable O002 synthetic project."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .protocols import TestStatus


MAX_SYNTHETIC_FILE_BYTES = 64 * 1024


class VerificationProfile(StrEnum):
    TASK_ONE = "TASK_ONE"
    TASK_TWO = "TASK_TWO"


@dataclass(frozen=True, slots=True)
class SyntheticVerificationError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class SyntheticVerification:
    command: str
    status: TestStatus
    exit_code: int
    summary: str
    files_read: tuple[str, ...]


class SyntheticVerifier:
    """Read only fixed synthetic artifacts; never import or execute project bytes."""

    _PROFILE_FILES = {
        VerificationProfile.TASK_ONE: ("artifact.txt", "PROJECT_MANUAL.md"),
        VerificationProfile.TASK_TWO: (
            "artifact.txt",
            "FINAL_STATUS.md",
            "PROJECT_MANUAL.md",
        ),
    }

    @staticmethod
    def _read_regular_utf8(root: Path, relative: str) -> str:
        candidate = root / relative
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise SyntheticVerificationError(
                "SYNTHETIC_EXPECTED_FILE_UNAVAILABLE", relative
            ) from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise SyntheticVerificationError(
                "SYNTHETIC_EXPECTED_FILE_NOT_REGULAR", relative
            )
        if metadata.st_size > MAX_SYNTHETIC_FILE_BYTES:
            raise SyntheticVerificationError(
                "SYNTHETIC_EXPECTED_FILE_TOO_LARGE", relative
            )
        try:
            payload = candidate.read_bytes()
            return payload.decode("utf-8", "strict")
        except (OSError, UnicodeDecodeError) as exc:
            raise SyntheticVerificationError(
                "SYNTHETIC_EXPECTED_FILE_NOT_UTF8", relative
            ) from exc

    def verify(
        self, worktree: str | Path, profile: VerificationProfile | str
    ) -> SyntheticVerification:
        try:
            selected = (
                profile
                if isinstance(profile, VerificationProfile)
                else VerificationProfile(profile)
            )
        except (TypeError, ValueError) as exc:
            raise SyntheticVerificationError(
                "UNKNOWN_SYNTHETIC_VERIFICATION_PROFILE", repr(profile)
            ) from exc
        root = Path(worktree).resolve(strict=True)
        expected = self._PROFILE_FILES[selected]
        content = {
            relative: self._read_regular_utf8(root, relative)
            for relative in expected
        }
        artifact_ok = content["artifact.txt"].splitlines() == ["alpha", "beta"]
        manual = content["PROJECT_MANUAL.md"].casefold()
        checks = [
            ("artifact_exact_alpha_beta", artifact_ok),
            ("manual_documents_alpha", "alpha" in manual),
            ("manual_documents_beta", "beta" in manual),
        ]
        if selected is VerificationProfile.TASK_TWO:
            checks.extend(
                (
                    (
                        "final_status_exact",
                        content["FINAL_STATUS.md"]
                        == "O002 synthetic cycle complete\n",
                    ),
                    (
                        "manual_documents_completion",
                        "o002 synthetic cycle complete" in manual,
                    ),
                )
            )
        passed = all(value for _, value in checks)
        summary = ";".join(
            f"{name}={'PASS' if value else 'FAIL'}" for name, value in checks
        )
        return SyntheticVerification(
            command=f"trusted-synthetic-verifier:{selected.value}",
            status=TestStatus.PASS if passed else TestStatus.FAIL,
            exit_code=0 if passed else 1,
            summary=summary,
            files_read=expected,
        )
