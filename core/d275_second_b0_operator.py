# SPDX-License-Identifier: GPL-2.0-or-later
"""Thin D275/02 authority over the reviewed D268 host transaction."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator, Sequence

from core.d268_first_image_operator import (
    D268OperatorDependencies,
    D268ProductionDependencies,
    run_d268_first_image_candidate,
    _git,
)
from core.live_capability import (
    CapabilityFailure,
    D275IntentCapability,
    D275MarkerClaimCapability,
    _issue_d275_marker_after_durable_claim,
    consume_d275_intent,
    issue_d275_intent,
    issue_d275_live_io,
)
from core.persistent_runtime import TerminalBoundary


D275_MARKER_PATH = Path("/var/lib/goodix-5125-poc/d275-second-b0-single-use.marker")
D275_REPORT_PATH = Path("/var/lib/goodix-5125-poc/d261-results/d275-second-b0-final.json")
D275_MARKER_SCHEMA = "D275_SECOND_B0_SINGLE_USE_MARKER_V1"
D275_LIVE_CRITICAL_PATHS = (
    "operator_kit/d275-second-b0-once.sh",
    "tools/d275_live_second_b0_once.py",
    "core/d275_second_b0_operator.py",
    "core/d268_first_image_operator.py",
    "core/live_capability.py",
    "core/persistent_runtime.py",
    "core/multiframe_validation.py",
    "core/fdt_lifecycle.py",
    "core/runtime_transport.py",
    "core/usb_runtime.py",
    "core/tls_b0.py",
    "core/cold_start.py",
    "core/fdt_seed.py",
    "core/post_d4.py",
    "core/protected_runtime.py",
    "src/goodix5125_cleanroom.py",
    "tools/d261_live_fdt_arm_once.py",
    "poc/goodix5125/tools/binding_reference/__init__.py",
    "poc/goodix5125/tools/binding_reference/runtime.py",
    "poc/goodix5125/tools/binding_reference/crypto_reference.py",
    "poc/goodix5125/tools/binding_reference/pe_parser.py",
)


class D275OperatorFailure(RuntimeError):
    pass


def validate_full_sha(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise D275OperatorFailure("approved_d275_baseline_full_sha_required")


def verify_d275_authoritative_baseline(
    repo: Path,
    sha: str,
    authoritative_paths: Sequence[str] = D275_LIVE_CRITICAL_PATHS,
) -> None:
    validate_full_sha(sha)
    authority = tuple(authoritative_paths)
    if len(authority) != len(set(authority)):
        raise D275OperatorFailure("d275_live_critical_duplicate_path")
    if authority != D275_LIVE_CRITICAL_PATHS:
        raise D275OperatorFailure("d275_live_critical_authoritative_path_set_mismatch")
    resolved = _git(repo, "rev-parse", f"{sha}^{{commit}}")
    if resolved.returncode or resolved.stdout.strip() != sha:
        raise D275OperatorFailure("approved_d275_baseline_resolution_mismatch")
    head = _git(repo, "rev-parse", "HEAD")
    if head.returncode or head.stdout.strip() != sha:
        raise D275OperatorFailure("approved_d275_baseline_head_mismatch")
    dirty = _git(repo, "status", "--porcelain", "--untracked-files=all")
    if dirty.returncode or dirty.stdout:
        raise D275OperatorFailure("approved_d275_baseline_worktree_dirty")
    for relative in authority:
        path = repo / relative
        blob = _git(repo, "show", f"{sha}:{relative}", text=False)
        if blob.returncode or not path.is_file() or blob.stdout != path.read_bytes():
            raise D275OperatorFailure(
                f"approved_d275_live_critical_byte_mismatch:{relative}"
            )


def issue_intent(flag: str) -> D275IntentCapability:
    return issue_d275_intent(flag)


def require_d275_marker_absent() -> None:
    try:
        D275_MARKER_PATH.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise D275OperatorFailure(f"d275_marker_preflight_failed:{exc.errno}") from exc
    raise D275OperatorFailure("d275_single_use_marker_already_exists")


def claim_d275_marker(
    path: Path,
    baseline_sha: str,
    intent: D275IntentCapability,
) -> D275MarkerClaimCapability:
    validate_full_sha(baseline_sha)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise D275OperatorFailure(f"d275_marker_claim_failed:{exc.errno}") from exc
    try:
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise D275OperatorFailure("d275_marker_owner_mode_invalid")
        payload = json.dumps(
            {
                "schema": D275_MARKER_SCHEMA,
                "approved_baseline_sha": baseline_sha,
                "terminal_boundary": TerminalBoundary.STOP_AFTER_SECOND_IMAGE.value,
            },
            sort_keys=True,
        ).encode() + b"\n"
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise D275OperatorFailure("d275_marker_write_made_no_progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        return _issue_d275_marker_after_durable_claim(intent)
    except CapabilityFailure as exc:
        raise D275OperatorFailure(str(exc)) from exc


def _require_d275_safe_directories() -> None:
    from core.protected_runtime import PROTECTED_ROOT
    from tools.d261_live_fdt_arm_once import (
        REPORT_DIRECTORY,
        prepare_report_directory,
        require_safe_report_destination,
    )

    prepare_report_directory(PROTECTED_ROOT, REPORT_DIRECTORY)
    require_safe_report_destination(D275_REPORT_PATH)


def _publish_d275_final_report(report: dict[str, Any]) -> None:
    from tools.d261_live_fdt_arm_once import publish_report

    if not report.get("report_destination_preflight_passed"):
        return
    try:
        publish_report(D275_REPORT_PATH, report)
    except BaseException as exc:
        report["report_publication_failure"] = f"{type(exc).__name__}:{exc}"
        report["result"] = "FAIL_CLOSED_REPORT_UNPUBLISHED"


def _finalize_second_image_report(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("result") == "PASS_STOP_AFTER_FIRST_IMAGE":
        report["result"] = "PASS_STOP_AFTER_SECOND_IMAGE"
        report["phase_reached"] = TerminalBoundary.STOP_AFTER_SECOND_IMAGE.value
    return report


def _issue_d275_live_io_after_marker(marker: object):
    try:
        return issue_d275_live_io(marker)
    except CapabilityFailure as exc:
        raise D275OperatorFailure(str(exc)) from exc


@contextmanager
def _d268_host_adapters() -> Iterator[None]:
    import core.d268_first_image_operator as d268

    original_consume = d268._consume_intent
    original_issue = d268.issue_d268_live_io_after_marker
    original_verify = d268.verify_d268_authoritative_baseline
    d268._consume_intent = lambda _token: None
    d268.issue_d268_live_io_after_marker = _issue_d275_live_io_after_marker
    d268.verify_d268_authoritative_baseline = (
        lambda repo, sha, paths=D275_LIVE_CRITICAL_PATHS: verify_d275_authoritative_baseline(
            repo, sha, paths
        )
    )
    try:
        yield
    finally:
        d268._consume_intent = original_consume
        d268.issue_d268_live_io_after_marker = original_issue
        d268.verify_d268_authoritative_baseline = original_verify


def build_dependencies(
    repo: Path, intent: D275IntentCapability
) -> D268OperatorDependencies:
    deps = D268ProductionDependencies.build(repo, intent)  # type: ignore[arg-type]
    deps.require_marker_absent = require_d275_marker_absent
    deps.claim_marker_once = (  # type: ignore[assignment]
        lambda sha, token: claim_d275_marker(D275_MARKER_PATH, sha, token)
    )
    deps.require_safe_directories = _require_d275_safe_directories
    deps.publish_report = lambda _report: None
    base_construct = D268ProductionDependencies.construct_runtime

    def construct(live_io, secret, target):
        coordinator = base_construct(live_io, secret, target)
        original_run = coordinator.run

        def second_boundary_run(*args, **kwargs):
            kwargs["terminal_mode"] = TerminalBoundary.STOP_AFTER_SECOND_IMAGE
            return original_run(*args, **kwargs)

        coordinator.run = second_boundary_run
        return coordinator

    deps.construct_coordinator = construct
    return deps


def run_candidate(
    intent: D275IntentCapability,
    dependencies: D268OperatorDependencies,
    *,
    repo: Path,
    sha: str,
    ts16: int,
    seed_result: Any = None,
) -> dict[str, Any]:
    consume_d275_intent(intent)
    with _d268_host_adapters():
        report = run_d268_first_image_candidate(
            intent,  # type: ignore[arg-type]
            dependencies,
            repo=repo,
            approved_baseline_sha=sha,
            ts16=ts16,
            authoritative_paths=D275_LIVE_CRITICAL_PATHS,
            seed_result_for_offline_rehearsal=seed_result,
        )
    report = _finalize_second_image_report(report)
    _publish_d275_final_report(report)
    return report
