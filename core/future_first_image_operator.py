# SPDX-License-Identifier: GPL-2.0-or-later
"""Protected future first-image orchestration, disabled for live use in D264/03.

Only injected dependencies can exercise this module in D264/03.  The operator
CLI deliberately has no factory capable of constructing these dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable

from core.persistent_runtime import TerminalBoundary


D265_FUTURE_LIVE_AUTHORIZATION_FLAG = "--i-authorize-one-future-d265-first-image-live-attempt"
D265_FUTURE_APPROVED_BASELINE_ENV = "D265_FUTURE_APPROVED_BASELINE_SHA"
D265_FUTURE_SINGLE_USE_MARKER_PATH = Path("/var/lib/goodix-5125-poc/d265-first-image-single-use.marker")
D261_MARKER_PATH = Path("/var/lib/goodix-5125-poc/d261-live-single-use.marker")
LIVE_CAPABILITY_DEFAULT = 0


class FutureOperatorFailure(RuntimeError):
    pass


class FutureIntentCapability:
    __slots__ = ("_nonce", "_used")

    def __init__(self, nonce: object) -> None:
        self._nonce = nonce
        self._used = False


class FutureLiveIoCapability:
    __slots__ = ("_nonce",)

    def __init__(self, nonce: object) -> None:
        self._nonce = nonce


_INTENT_NONCE = object()
_LIVE_IO_NONCE = object()


def issue_future_intent_for_injected_rehearsal(exact_intent: str) -> FutureIntentCapability:
    """Test seam; the D264/03 CLI never calls this capability issuer."""

    if exact_intent != D265_FUTURE_LIVE_AUTHORIZATION_FLAG:
        raise FutureOperatorFailure("exact_future_operator_intent_required")
    return FutureIntentCapability(_INTENT_NONCE)


def _consume_intent(intent: FutureIntentCapability | None) -> None:
    if not isinstance(intent, FutureIntentCapability) or intent._nonce is not _INTENT_NONCE:
        raise FutureOperatorFailure("future_intent_capability_required")
    if intent._used:
        raise FutureOperatorFailure("future_intent_capability_already_used")
    intent._used = True


def validate_full_sha(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise FutureOperatorFailure("approved_future_baseline_full_sha_required")


def verify_baseline_blobs(repo: Path, sha: str, paths: tuple[str, ...]) -> None:
    """Require an exact commit and byte equality for the authoritative path set."""

    validate_full_sha(sha)
    resolved = subprocess.run(
        ("git", "rev-parse", f"{sha}^{{commit}}"), cwd=repo, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if resolved.returncode or resolved.stdout.strip() != sha:
        raise FutureOperatorFailure("approved_future_baseline_resolution_mismatch")
    for relative in paths:
        blob = subprocess.run(
            ("git", "show", f"{sha}:{relative}"), cwd=repo, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if blob.returncode or blob.stdout != (repo / relative).read_bytes():
            raise FutureOperatorFailure(f"future_live_critical_baseline_stale:{relative}")


def claim_future_marker_fixture(path: Path, baseline_sha: str, *, expected_uid: int | None = None) -> None:
    """Exercise the future schema only in a caller-owned temporary directory."""

    validate_full_sha(baseline_sha)
    if path == D261_MARKER_PATH or path.name == D261_MARKER_PATH.name:
        raise FutureOperatorFailure("D261_marker_namespace_forbidden")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise FutureOperatorFailure(f"future_marker_claim_failed:{exc.errno}") from exc
    try:
        metadata = os.fstat(descriptor)
        uid = os.geteuid() if expected_uid is None else expected_uid
        if metadata.st_uid != uid or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise FutureOperatorFailure("future_marker_owner_mode_invalid")
        payload = json.dumps({
            "schema": "D265_FUTURE_FIRST_IMAGE_SINGLE_USE_MARKER_V1",
            "approved_baseline_sha": baseline_sha,
        }, sort_keys=True).encode() + b"\n"
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass
class FutureOperatorDependencies:
    """Dangerous boundaries; production implementations are intentionally absent."""

    preflight: Callable[[], None]
    stop_fprintd: Callable[[], None]
    restore_fprintd: Callable[[], None]
    block_signals: Callable[[], None]
    restore_signals: Callable[[], None]
    materialize_secret_once: Callable[[], Any]
    claim_marker_once: Callable[[], None]
    construct_coordinator: Callable[[FutureLiveIoCapability, Any], Any]
    publish_report: Callable[[dict[str, Any]], None]


def run_future_first_image_candidate(
    intent: FutureIntentCapability | None,
    dependencies: FutureOperatorDependencies,
    *,
    ts16: int,
) -> dict[str, Any]:
    """Run production-shaped control flow using exclusively injected boundaries."""

    _consume_intent(intent)
    report: dict[str, Any] = {"result": "FAIL_CLOSED", "retry_count": 0}
    secret = None
    coordinator = None
    try:
        dependencies.preflight()
        dependencies.stop_fprintd()
        dependencies.block_signals()
        secret = dependencies.materialize_secret_once()
        dependencies.claim_marker_once()
        capability = FutureLiveIoCapability(_LIVE_IO_NONCE)
        coordinator = dependencies.construct_coordinator(capability, secret)
        result = coordinator.run(
            ts16=ts16,
            terminal_mode=TerminalBoundary.STOP_AFTER_FIRST_IMAGE,
        )
        report.update(
            result="PASS_STOP_AFTER_FIRST_IMAGE",
            phase_reached="STOP_AFTER_FIRST_IMAGE",
            runtime_audit=coordinator.audit(),
            command_trace=[f"0x{x:02x}" for x in result.command_trace],
        )
    except BaseException as exc:
        report["failure_class"] = f"{type(exc).__name__}:{exc}"
    finally:
        # PersistentRuntimeCoordinator.run() owns and independently attempts
        # TLS/secret/transport cleanup in its own finally block.  There is no
        # second runtime session and no invented device-side cleanup here.
        if secret is not None:
            try:
                secret.close()
            except BaseException as exc:
                report["secret_cleanup_failure"] = f"{type(exc).__name__}:{exc}"
        try:
            dependencies.restore_signals()
        except BaseException as exc:
            report["signal_restore_failure"] = f"{type(exc).__name__}:{exc}"
        try:
            dependencies.restore_fprintd()
        except BaseException as exc:
            report["fprintd_restore_failure"] = f"{type(exc).__name__}:{exc}"
        if any(key.endswith("_failure") for key in report):
            report["result"] = "FAIL_CLOSED_CLEANUP_INCOMPLETE"
        try:
            dependencies.publish_report(report)
        except BaseException as exc:
            report["report_publication_failure"] = f"{type(exc).__name__}:{exc}"
            report["result"] = "FAIL_CLOSED_REPORT_UNPUBLISHED"
    return report


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
