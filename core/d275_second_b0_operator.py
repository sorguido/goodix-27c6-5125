# SPDX-License-Identifier: GPL-2.0-or-later
"""Thin D275/02 authority over the reviewed D268 guards and D275 runtime."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from core.d268_first_image_operator import (
    D268OperatorDependencies, D268ProductionDependencies, claim_d268_marker,
    run_d268_first_image_candidate, validate_full_sha, _git,
)
from core.live_capability import (
    CapabilityFailure, D275IntentCapability, D275MarkerClaimCapability,
    D275LiveIoCapability, _issue_d275_marker_after_durable_claim,
    consume_d275_intent, issue_d275_intent, issue_d275_live_io,
)
from core.persistent_runtime import TerminalBoundary

D275_MARKER_PATH = Path("/var/lib/goodix-5125-poc/d275-second-b0-single-use.marker")
D275_REPORT_PATH = Path("/var/lib/goodix-5125-poc/d261-results/d275-second-b0-final.json")
D275_LIVE_CRITICAL_PATHS = (
    "operator_kit/d275-second-b0-once.sh", "tools/d275_live_second_b0_once.py",
    "core/d275_second_b0_operator.py", "core/d268_first_image_operator.py",
    "core/live_capability.py", "core/persistent_runtime.py", "core/fdt_lifecycle.py",
    "core/runtime_transport.py", "core/usb_runtime.py", "core/tls_b0.py",
    "core/cold_start.py", "core/fdt_seed.py", "core/post_d4.py",
    "core/protected_runtime.py", "src/goodix5125_cleanroom.py",
    "tools/d261_live_fdt_arm_once.py",
)

def verify_d268_authoritative_baseline(repo: Path, sha: str, paths=D275_LIVE_CRITICAL_PATHS) -> None:
    validate_full_sha(sha)
    if tuple(paths) != D275_LIVE_CRITICAL_PATHS or len(paths) != len(set(paths)):
        raise RuntimeError("d275_live_critical_authority_mismatch")
    if _git(repo,"rev-parse","HEAD").stdout.strip() != sha or _git(repo,"status","--porcelain","--untracked-files=all").stdout:
        raise RuntimeError("d275_approved_baseline_or_clean_tree_required")
    for relative in paths:
        blob=_git(repo,"show",f"{sha}:{relative}",text=False)
        if blob.returncode or blob.stdout != (repo/relative).read_bytes():
            raise RuntimeError(f"d275_live_critical_byte_mismatch:{relative}")

def issue_intent(flag: str) -> D275IntentCapability:
    return issue_d275_intent(flag)

def _marker(sha: str, intent: D275IntentCapability) -> D275MarkerClaimCapability:
    # Reuse the durable, O_EXCL, mode-0600 marker implementation; only the
    # D275 namespace and capability authority differ.
    import core.d268_first_image_operator as d268
    original = d268._issue_d268_marker_after_durable_claim
    d268._issue_d268_marker_after_durable_claim = lambda _token: _issue_d275_marker_after_durable_claim(intent)
    try: return claim_d268_marker(D275_MARKER_PATH, sha, intent)  # type: ignore[arg-type]
    finally: d268._issue_d268_marker_after_durable_claim = original

def build_dependencies(repo: Path, intent: D275IntentCapability) -> D268OperatorDependencies:
    deps = D268ProductionDependencies.build(repo, intent)  # type: ignore[arg-type]
    deps.require_marker_absent = lambda: (_ for _ in ()).throw(RuntimeError("d275_single_use_marker_already_exists")) if D275_MARKER_PATH.exists() else None
    deps.claim_marker_once = _marker  # type: ignore[assignment]
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

def run_candidate(intent: D275IntentCapability, dependencies: D268OperatorDependencies, *, repo: Path, sha: str, ts16: int, seed_result: Any = None) -> dict[str, Any]:
    consume_d275_intent(intent)
    import core.d268_first_image_operator as d268
    original_consume = d268._consume_intent
    original_issue = d268.issue_d268_live_io_after_marker
    original_verify = d268.verify_d268_authoritative_baseline
    d268._consume_intent = lambda _token: None
    d268.issue_d268_live_io_after_marker = lambda marker: issue_d275_live_io(marker)
    d268.verify_d268_authoritative_baseline = lambda r, candidate, paths: verify_d268_authoritative_baseline(r, candidate, paths)
    try:
        report = run_d268_first_image_candidate(intent, dependencies, repo=repo,
            approved_baseline_sha=sha, ts16=ts16,
            authoritative_paths=D275_LIVE_CRITICAL_PATHS,
            seed_result_for_offline_rehearsal=seed_result)
        if report.get("result") == "PASS_STOP_AFTER_FIRST_IMAGE":
            report["result"] = "PASS_STOP_AFTER_SECOND_IMAGE"
            report["phase_reached"] = TerminalBoundary.STOP_AFTER_SECOND_IMAGE.value
        return report
    finally:
        d268._consume_intent = original_consume
        d268.issue_d268_live_io_after_marker = original_issue
        d268.verify_d268_authoritative_baseline = original_verify
