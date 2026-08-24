# SPDX-License-Identifier: GPL-2.0-or-later
"""Future protected first-image path; its D264/03 shell gate is offline-only.

The candidate spells out every guard, capability transition, and ownership
transition.  :class:`FutureProductionDependencies` is the concrete future call
graph, but D264/03's CLI never constructs it.  Tests replace only dangerous
external dependencies while retaining this orchestration and the real public
``PersistentRuntimeCoordinator.run`` path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable, Sequence

from core.persistent_runtime import PersistentRuntimeCoordinator, TerminalBoundary
from core.live_capability import (
    CapabilityFailure,
    D265_FUTURE_LIVE_AUTHORIZATION_FLAG,
    FutureIntentCapability,
    FutureLiveIoCapability,
    FutureMarkerClaimCapability,
    consume_future_intent,
    issue_future_intent,
    issue_future_live_io,
    _issue_future_marker_after_durable_claim,
    require_known_live_io_capability,
)


D265_FUTURE_APPROVED_BASELINE_ENV = "D265_FUTURE_APPROVED_BASELINE_SHA"
D265_FUTURE_SINGLE_USE_MARKER_PATH = Path("/var/lib/goodix-5125-poc/d265-first-image-single-use.marker")
D261_MARKER_PATH = Path("/var/lib/goodix-5125-poc/d261-live-single-use.marker")
D265_FUTURE_REPORT_PATH = Path("/var/lib/goodix-5125-poc/d261-results/d265-first-image-final.json")
LIVE_CAPABILITY_DEFAULT = 0

FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS = (
    "core/__init__.py",
    "core/cold_start.py",
    "core/fdt_lifecycle.py",
    "core/fdt_seed.py",
    "core/future_first_image_operator.py",
    "core/live_capability.py",
    "core/persistent_runtime.py",
    "core/post_d4.py",
    "core/protected_runtime.py",
    "core/runtime_transport.py",
    "core/tls_b0.py",
    "core/usb_runtime.py",
    "src/goodix5125_cleanroom.py",
    "poc/goodix5125/tools/binding_reference/__init__.py",
    "poc/goodix5125/tools/binding_reference/runtime.py",
    "poc/goodix5125/tools/binding_reference/crypto_reference.py",
    "poc/goodix5125/tools/binding_reference/pe_parser.py",
    "tools/d261_live_fdt_arm_once.py",
)
D264_03_OFFLINE_GATE_PATHS = (
    "operator_kit/d264-first-image-prelive.sh",
    "tools/d264_first_image_prelive.py",
)


class FutureOperatorFailure(RuntimeError):
    pass


def issue_future_intent_for_injected_rehearsal(exact_intent: str) -> FutureIntentCapability:
    """Test/future-main seam; the D264/03 CLI never calls this issuer."""
    try:
        return issue_future_intent(exact_intent)
    except CapabilityFailure as exc:
        raise FutureOperatorFailure(str(exc)) from exc


def _consume_intent(intent: FutureIntentCapability | None) -> None:
    try:
        consume_future_intent(intent)
    except CapabilityFailure as exc:
        raise FutureOperatorFailure(str(exc)) from exc


def issue_live_io_after_marker_claim(marker: FutureMarkerClaimCapability | None) -> FutureLiveIoCapability:
    try:
        return issue_future_live_io(marker)
    except CapabilityFailure as exc:
        raise FutureOperatorFailure(str(exc)) from exc


def require_future_live_io(capability: FutureLiveIoCapability | None) -> None:
    try:
        require_known_live_io_capability(capability)
    except CapabilityFailure as exc:
        raise FutureOperatorFailure(str(exc)) from exc


def validate_full_sha(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise FutureOperatorFailure("approved_future_baseline_full_sha_required")


def verify_authoritative_baseline(
    repo: Path,
    sha: str,
    authoritative_paths: Sequence[str],
) -> None:
    """Verify exact path authority and commit/worktree byte identity."""
    validate_full_sha(sha)
    authority = tuple(authoritative_paths)
    if len(authority) != len(set(authority)):
        raise FutureOperatorFailure("future_live_critical_duplicate_path")
    if authority != FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS:
        raise FutureOperatorFailure("future_live_critical_authoritative_path_set_mismatch")
    resolved = subprocess.run(
        ("git", "rev-parse", f"{sha}^{{commit}}"), cwd=repo, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if resolved.returncode or resolved.stdout.strip() != sha:
        raise FutureOperatorFailure("approved_future_baseline_resolution_mismatch")
    for relative in authority:
        path = repo / relative
        blob = subprocess.run(
            ("git", "show", f"{sha}:{relative}"), cwd=repo, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if blob.returncode or not path.is_file() or blob.stdout != path.read_bytes():
            raise FutureOperatorFailure(f"future_live_critical_baseline_stale:{relative}")


def claim_future_marker_fixture(path: Path, baseline_sha: str, intent: FutureIntentCapability) -> FutureMarkerClaimCapability:
    """Durable claim primitive, used only with temp paths in D264/03 tests."""
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
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise FutureOperatorFailure("future_marker_owner_mode_invalid")
        payload = json.dumps({
            "schema": "D265_FUTURE_FIRST_IMAGE_SINGLE_USE_MARKER_V1",
            "approved_baseline_sha": baseline_sha,
        }, sort_keys=True).encode() + b"\n"
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _issue_future_marker_after_durable_claim(intent)


def require_future_marker_absent_at(path: Path) -> None:
    """Non-mutating absence check; production always passes the fixed future path."""
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise FutureOperatorFailure(f"future_marker_preflight_failed:{exc.errno}") from exc
    raise FutureOperatorFailure("future_single_use_marker_already_exists")


def require_bound_future_report_destination(checker: Callable[[Path], None]) -> None:
    """Apply the reviewed destination checker to the fixed future report path."""
    checker(D265_FUTURE_REPORT_PATH)


@dataclass
class FutureOperatorDependencies:
    observe_baseline_verified: Callable[[], None]
    require_operator_context: Callable[[], None]
    require_safe_directories: Callable[[], None]
    verify_protected_metadata: Callable[[], None]
    verify_gfusb_hash: Callable[[], None]
    resolve_exact_target: Callable[[], Any]
    stop_fprintd: Callable[[], None]
    block_signals: Callable[[], None]
    require_no_holders: Callable[[Any], None]
    validate_non_secret_material: Callable[[], None]
    require_future_marker_absent: Callable[[], None]
    materialize_secret_once: Callable[[], Any]
    claim_marker_once: Callable[[str, FutureIntentCapability], FutureMarkerClaimCapability]
    observe_live_io_issue: Callable[[], None]
    construct_coordinator: Callable[[FutureLiveIoCapability, Any, Any], PersistentRuntimeCoordinator]
    restore_signals: Callable[[], None]
    restore_fprintd: Callable[[], None]
    publish_report: Callable[[dict[str, Any]], None]


class FutureProductionDependencies:
    """Concrete future adapter, deliberately unreachable from the D264/03 CLI.

    Imports are lazy so importing the offline gate performs no protected reads.
    This adapter names the real D261-reviewed guards, real backend, cold start,
    FDT seed provider, and coordinator instead of hiding them behind a nominal
    callback.  Transactions and the dedicated report destination are bound by
    ``build()`` rather than supplied by a future caller.
    """
    @staticmethod
    def construct_runtime(live_io: FutureLiveIoCapability, secret: Any, target: Any) -> PersistentRuntimeCoordinator:
        require_known_live_io_capability(live_io)
        from core.cold_start import ColdStartMachine
        from core.fdt_seed import provide_hash_gated_fdt12
        from core.usb_runtime import CtypesLibusbBackend, LibusbRuntimeTransport
        from tools.d261_live_fdt_arm_once import CACHE_PATH, CACHE_SHA256
        backend = CtypesLibusbBackend(live_io)
        transport = LibusbRuntimeTransport(backend)
        cold_start = ColdStartMachine(transport, secret)
        return PersistentRuntimeCoordinator(
            transport, transport.event_source, secret,
            cold_start_machine=cold_start,
            cold_start_material=target["material"],
            seed_provider_from_live_otp=lambda otp: provide_hash_gated_fdt12(CACHE_PATH, otp, CACHE_SHA256),
            operational_physical_policy=True,
        )

    @staticmethod
    def build(repo: Path, intent: FutureIntentCapability) -> FutureOperatorDependencies:
        """Bind the future candidate to the reviewed real guard/runtime graph.

        This function is intentionally never referenced by the D264/03 CLI.
        Calling it is not authorization; the orchestration still requires all
        baseline, intent, marker, and capability gates.
        """
        from core.protected_runtime import (CANONICAL_GFUSB_PATH, CANONICAL_GFUSB_SHA256,
            CONFIG90_PATH, MATERIAL_MANIFEST_PATH, PROTECTED_ROOT, SECRET_PATH,
            RealSecretBoundary, load_cold_start_material, protected_metadata)
        from tools.d261_live_fdt_arm_once import (CACHE_PATH, CACHE_SHA256, REPORT_DIRECTORY,
            FprintdTransaction, SignalTransaction, cache_preflight, exact_target_sysfs,
            external_holders, prepare_report_directory, publish_report,
            require_no_external_holders, require_safe_report_destination, sha256_file)
        state: dict[str, Any] = {}
        fprintd, signals = FprintdTransaction(), SignalTransaction()
        def operator_context():
            if os.geteuid() != 0 or not os.environ.get("SUDO_UID", "").isdigit():
                raise FutureOperatorFailure("future_operator_context_required")
        def safe_directories():
            prepare_report_directory(PROTECTED_ROOT, REPORT_DIRECTORY)
            require_bound_future_report_destination(require_safe_report_destination)
        def metadata():
            if not all(protected_metadata(path, size)["metadata_pass"] for path, size in (
                (SECRET_PATH, 88), (MATERIAL_MANIFEST_PATH, None), (CONFIG90_PATH, 224))):
                raise FutureOperatorFailure("future_protected_metadata_failed")
        def gfusb():
            if sha256_file(repo / CANONICAL_GFUSB_PATH) != CANONICAL_GFUSB_SHA256:
                raise FutureOperatorFailure("future_gfusb_hash_failed")
        def target():
            state["target"] = {"identity": exact_target_sysfs()}; return state["target"]
        def holders(value):
            require_no_external_holders(external_holders(value["identity"][1]), own_pid=os.getpid())
        def non_secret():
            cache = cache_preflight(CACHE_PATH, CACHE_SHA256)
            if cache["status"] != "PASS": raise FutureOperatorFailure("future_cache_failed")
            state["target"]["material"] = load_cold_start_material(
                MATERIAL_MANIFEST_PATH, CONFIG90_PATH, intent)
        def marker_absent():
            require_future_marker_absent_at(D265_FUTURE_SINGLE_USE_MARKER_PATH)
        def secret():
            boundary = RealSecretBoundary(SECRET_PATH, repo / CANONICAL_GFUSB_PATH)
            boundary.materialize(intent); return boundary
        return FutureOperatorDependencies(
            observe_baseline_verified=lambda: None, require_operator_context=operator_context,
            require_safe_directories=safe_directories, verify_protected_metadata=metadata,
            verify_gfusb_hash=gfusb, resolve_exact_target=target, stop_fprintd=fprintd.prepare,
            block_signals=signals.block, require_no_holders=holders, validate_non_secret_material=non_secret,
            require_future_marker_absent=marker_absent, materialize_secret_once=secret,
            claim_marker_once=lambda sha, token: claim_future_marker_fixture(D265_FUTURE_SINGLE_USE_MARKER_PATH, sha, token),
            observe_live_io_issue=lambda: None, construct_coordinator=FutureProductionDependencies.construct_runtime,
            restore_signals=signals.restore, restore_fprintd=fprintd.restore,
            publish_report=lambda report: publish_report(D265_FUTURE_REPORT_PATH, report),
        )


def run_future_first_image_candidate(
    intent: FutureIntentCapability | None,
    dependencies: FutureOperatorDependencies,
    *, repo: Path, approved_baseline_sha: str,
    authoritative_paths: Sequence[str],
    ts16: int, seed_result_for_offline_rehearsal: Any = None,
) -> dict[str, Any]:
    """Execute the explicit guard→capability→ownership→coordinator chain."""
    _consume_intent(intent)
    report: dict[str, Any] = {"result": "FAIL_CLOSED", "retry_count": 0}
    secret = None
    secret_owned_by_outer = False
    ownership_transferred = False
    try:
        verify_authoritative_baseline(repo, approved_baseline_sha, authoritative_paths)
        dependencies.observe_baseline_verified()
        dependencies.require_operator_context()
        dependencies.require_safe_directories()
        dependencies.verify_protected_metadata()
        dependencies.verify_gfusb_hash()
        target = dependencies.resolve_exact_target()
        dependencies.stop_fprintd()
        dependencies.block_signals()
        dependencies.require_no_holders(target)
        dependencies.validate_non_secret_material()
        dependencies.require_future_marker_absent()
        secret = dependencies.materialize_secret_once()
        secret_owned_by_outer = True
        marker_claim = dependencies.claim_marker_once(approved_baseline_sha, intent)
        live_io = issue_live_io_after_marker_claim(marker_claim)
        dependencies.observe_live_io_issue()
        coordinator = dependencies.construct_coordinator(live_io, secret, target)
        ownership_transferred = True
        secret_owned_by_outer = False
        run_kwargs = {"ts16": ts16, "terminal_mode": TerminalBoundary.STOP_AFTER_FIRST_IMAGE}
        if seed_result_for_offline_rehearsal is not None:
            run_kwargs["seed_result"] = seed_result_for_offline_rehearsal
        result = coordinator.run(**run_kwargs)
        report.update(
            result="PASS_STOP_AFTER_FIRST_IMAGE", phase_reached="STOP_AFTER_FIRST_IMAGE",
            runtime_audit=coordinator.audit(), command_trace=[f"0x{x:02x}" for x in result.command_trace],
            first_image_raster_shape=(list(result.first_image_raster_shape)
                                      if getattr(result, "first_image_raster_shape", None) else None),
        )
    except BaseException as exc:
        report["failure_class"] = f"{type(exc).__name__}:{exc}"
    finally:
        if secret_owned_by_outer and secret is not None:
            try:
                secret.close()
            except BaseException as exc:
                report["secret_cleanup_failure"] = f"{type(exc).__name__}:{exc}"
        report["secret_ownership_transferred_to_coordinator"] = ownership_transferred
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
