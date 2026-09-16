# SPDX-License-Identifier: GPL-2.0-or-later
"""Protected D268 first-image candidate with independent one-shot authority.

The module is inert at import time.  Real dependencies are constructed only
after the caller verifies an explicitly approved full-SHA baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable, Sequence

from core.live_capability import (
    CapabilityFailure,
    D268IntentCapability,
    D268LiveIoCapability,
    D268MarkerClaimCapability,
    _issue_d268_marker_after_durable_claim,
    consume_d268_intent,
    issue_d268_intent,
    issue_d268_live_io,
    require_known_live_io_capability,
    require_root_with_nonroot_operator,
)
from core.persistent_runtime import PersistentRuntimeCoordinator, TerminalBoundary


D268_APPROVED_BASELINE_ENV = "D268_APPROVED_LIVE_BASELINE_SHA"
D268_SINGLE_USE_MARKER_PATH = Path(
    "/var/lib/goodix-5125-poc/d268-first-image-single-use.marker"
)
D268_REPORT_PATH = Path(
    "/var/lib/goodix-5125-poc/d261-results/d268-first-image-final.json"
)
HISTORICAL_MARKER_PATHS = frozenset(
    {
        Path("/var/lib/goodix-5125-poc/d261-live-single-use.marker"),
        Path("/var/lib/goodix-5125-poc/d265-first-image-single-use.marker"),
        Path("/var/lib/goodix-5125-poc/d267-first-image-single-use.marker"),
    }
)

D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS = (
    "operator_kit/d268-first-image-once.sh",
    "tools/d268_live_first_image_once.py",
    "core/__init__.py",
    "core/cold_start.py",
    "core/d268_first_image_operator.py",
    "core/fdt_lifecycle.py",
    "core/fdt_seed.py",
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


class D268OperatorFailure(RuntimeError):
    pass


def validate_full_sha(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise D268OperatorFailure("approved_d268_baseline_full_sha_required")


def _git(
    repo: Path, *args: str, text: bool = True
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ("git", *args),
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )


def verify_d268_authoritative_baseline(
    repo: Path,
    sha: str,
    authoritative_paths: Sequence[str] = D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS,
) -> None:
    """Require exact authority, approved HEAD, clean tree and byte identity."""
    validate_full_sha(sha)
    authority = tuple(authoritative_paths)
    if len(authority) != len(set(authority)):
        raise D268OperatorFailure("d268_live_critical_duplicate_path")
    if authority != D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS:
        raise D268OperatorFailure("d268_live_critical_authoritative_path_set_mismatch")

    resolved = _git(repo, "rev-parse", f"{sha}^{{commit}}")
    if resolved.returncode or resolved.stdout.strip() != sha:
        raise D268OperatorFailure("approved_d268_baseline_resolution_mismatch")
    head = _git(repo, "rev-parse", "HEAD")
    if head.returncode or head.stdout.strip() != sha:
        raise D268OperatorFailure("approved_d268_baseline_head_mismatch")
    dirty = _git(repo, "status", "--porcelain", "--untracked-files=all")
    if dirty.returncode or dirty.stdout:
        raise D268OperatorFailure("approved_d268_baseline_worktree_dirty")

    for relative in authority:
        path = repo / relative
        blob = _git(repo, "show", f"{sha}:{relative}", text=False)
        if blob.returncode or not path.is_file() or blob.stdout != path.read_bytes():
            raise D268OperatorFailure(
                f"approved_d268_live_critical_byte_mismatch:{relative}"
            )


def issue_d268_intent_for_operator(exact_intent: str) -> D268IntentCapability:
    try:
        return issue_d268_intent(exact_intent)
    except CapabilityFailure as exc:
        raise D268OperatorFailure(str(exc)) from exc


def _consume_intent(intent: D268IntentCapability | None) -> None:
    try:
        consume_d268_intent(intent)
    except CapabilityFailure as exc:
        raise D268OperatorFailure(str(exc)) from exc


def issue_d268_live_io_after_marker(
    marker: D268MarkerClaimCapability | None,
) -> D268LiveIoCapability:
    try:
        return issue_d268_live_io(marker)
    except CapabilityFailure as exc:
        raise D268OperatorFailure(str(exc)) from exc


def claim_d268_marker(
    path: Path,
    baseline_sha: str,
    intent: D268IntentCapability,
) -> D268MarkerClaimCapability:
    """Durably claim the D268 marker before minting live-I/O authority."""
    validate_full_sha(baseline_sha)
    if path in HISTORICAL_MARKER_PATHS or path.name in {
        item.name for item in HISTORICAL_MARKER_PATHS
    }:
        raise D268OperatorFailure("historical_marker_namespace_forbidden")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise D268OperatorFailure(f"d268_marker_claim_failed:{exc.errno}") from exc
    try:
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise D268OperatorFailure("d268_marker_owner_mode_invalid")
        payload = json.dumps(
            {
                "schema": "D268_FIRST_IMAGE_SINGLE_USE_MARKER_V1",
                "approved_baseline_sha": baseline_sha,
            },
            sort_keys=True,
        ).encode() + b"\n"
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise D268OperatorFailure("d268_marker_write_made_no_progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        return _issue_d268_marker_after_durable_claim(intent)
    except CapabilityFailure as exc:
        raise D268OperatorFailure(str(exc)) from exc


def require_d268_marker_absent() -> None:
    try:
        D268_SINGLE_USE_MARKER_PATH.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise D268OperatorFailure(f"d268_marker_preflight_failed:{exc.errno}") from exc
    raise D268OperatorFailure("d268_single_use_marker_already_exists")


@dataclass
class D268OperatorDependencies:
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
    require_marker_absent: Callable[[], None]
    materialize_secret_once: Callable[[], Any]
    claim_marker_once: Callable[
        [str, D268IntentCapability], D268MarkerClaimCapability
    ]
    observe_live_io_issue: Callable[[], None]
    construct_coordinator: Callable[
        [D268LiveIoCapability, Any, Any], PersistentRuntimeCoordinator
    ]
    restore_signals: Callable[[], None]
    restore_fprintd: Callable[[], None]
    publish_report: Callable[[dict[str, Any]], None]


class D268ProductionDependencies:
    """Bind D268 to the reviewed guards and concrete runtime graph."""

    @staticmethod
    def construct_runtime(
        live_io: D268LiveIoCapability,
        secret: Any,
        target: Any,
    ) -> PersistentRuntimeCoordinator:
        require_known_live_io_capability(live_io)
        from core.cold_start import ColdStartMachine
        from core.fdt_seed import provide_hash_gated_fdt12
        from core.usb_runtime import CtypesLibusbBackend, LibusbRuntimeTransport
        from tools.d261_live_fdt_arm_once import CACHE_PATH, CACHE_SHA256

        backend = CtypesLibusbBackend(live_io)
        transport = LibusbRuntimeTransport(backend)
        cold_start = ColdStartMachine(transport, secret)
        return PersistentRuntimeCoordinator(
            transport,
            transport.event_source,
            secret,
            cold_start_machine=cold_start,
            cold_start_material=target["material"],
            seed_provider_from_live_otp=lambda otp: provide_hash_gated_fdt12(
                CACHE_PATH, otp, CACHE_SHA256
            ),
            operational_physical_policy=True,
        )

    @staticmethod
    def build(repo: Path, intent: D268IntentCapability) -> D268OperatorDependencies:
        from core.protected_runtime import (
            CANONICAL_GFUSB_PATH,
            CANONICAL_GFUSB_SHA256,
            CONFIG90_PATH,
            MATERIAL_MANIFEST_PATH,
            PROTECTED_ROOT,
            SECRET_PATH,
            RealSecretBoundary,
            load_cold_start_material,
            protected_metadata,
        )
        from tools.d261_live_fdt_arm_once import (
            CACHE_PATH,
            CACHE_SHA256,
            REPORT_DIRECTORY,
            FprintdTransaction,
            SignalTransaction,
            cache_preflight,
            exact_target_sysfs,
            external_holders,
            prepare_report_directory,
            publish_report,
            require_no_external_holders,
            require_safe_report_destination,
            sha256_file,
        )

        state: dict[str, Any] = {}
        fprintd = FprintdTransaction()
        signals = SignalTransaction()

        def operator_context() -> None:
            try:
                require_root_with_nonroot_operator(
                    os.geteuid(), os.environ.get("SUDO_UID", "")
                )
            except CapabilityFailure as exc:
                raise D268OperatorFailure(str(exc)) from exc

        def safe_directories() -> None:
            prepare_report_directory(PROTECTED_ROOT, REPORT_DIRECTORY)
            require_safe_report_destination(D268_REPORT_PATH)

        def metadata() -> None:
            checks = (
                (SECRET_PATH, 88),
                (MATERIAL_MANIFEST_PATH, None),
                (CONFIG90_PATH, 224),
            )
            if not all(
                protected_metadata(path, size)["metadata_pass"]
                for path, size in checks
            ):
                raise D268OperatorFailure("d268_protected_metadata_failed")

        def gfusb() -> None:
            if sha256_file(repo / CANONICAL_GFUSB_PATH) != CANONICAL_GFUSB_SHA256:
                raise D268OperatorFailure("d268_gfusb_hash_failed")

        def target() -> dict[str, Any]:
            state["target"] = {"identity": exact_target_sysfs()}
            return state["target"]

        def holders(value: dict[str, Any]) -> None:
            require_no_external_holders(
                external_holders(value["identity"][1]), own_pid=os.getpid()
            )

        def non_secret() -> None:
            cache = cache_preflight(CACHE_PATH, CACHE_SHA256)
            if cache["status"] != "PASS":
                raise D268OperatorFailure("d268_cache_failed")
            state["target"]["material"] = load_cold_start_material(
                MATERIAL_MANIFEST_PATH, CONFIG90_PATH, intent
            )

        def secret() -> Any:
            boundary = RealSecretBoundary(SECRET_PATH, repo / CANONICAL_GFUSB_PATH)
            boundary.materialize(intent)
            return boundary

        return D268OperatorDependencies(
            observe_baseline_verified=lambda: None,
            require_operator_context=operator_context,
            require_safe_directories=safe_directories,
            verify_protected_metadata=metadata,
            verify_gfusb_hash=gfusb,
            resolve_exact_target=target,
            stop_fprintd=fprintd.prepare,
            block_signals=signals.block,
            require_no_holders=holders,
            validate_non_secret_material=non_secret,
            require_marker_absent=require_d268_marker_absent,
            materialize_secret_once=secret,
            claim_marker_once=lambda sha, token: claim_d268_marker(
                D268_SINGLE_USE_MARKER_PATH, sha, token
            ),
            observe_live_io_issue=lambda: None,
            construct_coordinator=D268ProductionDependencies.construct_runtime,
            restore_signals=signals.restore,
            restore_fprintd=fprintd.restore,
            publish_report=lambda report: publish_report(D268_REPORT_PATH, report),
        )


def run_d268_first_image_candidate(
    intent: D268IntentCapability | None,
    dependencies: D268OperatorDependencies,
    *,
    repo: Path,
    approved_baseline_sha: str,
    ts16: int,
    authoritative_paths: Sequence[str] = D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS,
    seed_result_for_offline_rehearsal: Any = None,
) -> dict[str, Any]:
    """Run the guarded one-shot chain and always perform host cleanup."""
    _consume_intent(intent)
    report: dict[str, Any] = {"result": "FAIL_CLOSED", "retry_count": 0}
    secret = None
    coordinator: PersistentRuntimeCoordinator | None = None
    secret_owned_by_outer = False
    ownership_transferred = False
    report_destination_preflight_passed = False
    fprintd_transaction_started = False
    signals_transaction_started = False
    try:
        verify_d268_authoritative_baseline(
            repo, approved_baseline_sha, authoritative_paths
        )
        dependencies.observe_baseline_verified()
        dependencies.require_operator_context()
        dependencies.require_safe_directories()
        report_destination_preflight_passed = True
        dependencies.verify_protected_metadata()
        dependencies.verify_gfusb_hash()
        target = dependencies.resolve_exact_target()
        dependencies.stop_fprintd()
        fprintd_transaction_started = True
        dependencies.block_signals()
        signals_transaction_started = True
        dependencies.require_no_holders(target)
        dependencies.validate_non_secret_material()
        dependencies.require_marker_absent()
        secret = dependencies.materialize_secret_once()
        secret_owned_by_outer = True
        marker_claim = dependencies.claim_marker_once(approved_baseline_sha, intent)
        live_io = issue_d268_live_io_after_marker(marker_claim)
        dependencies.observe_live_io_issue()
        coordinator = dependencies.construct_coordinator(live_io, secret, target)
        ownership_transferred = True
        secret_owned_by_outer = False
        run_kwargs = {
            "ts16": ts16,
            "terminal_mode": TerminalBoundary.STOP_AFTER_FIRST_IMAGE,
        }
        if seed_result_for_offline_rehearsal is not None:
            run_kwargs["seed_result"] = seed_result_for_offline_rehearsal
        result = coordinator.run(**run_kwargs)
        report.update(
            result="PASS_STOP_AFTER_FIRST_IMAGE",
            phase_reached="STOP_AFTER_FIRST_IMAGE",
            runtime_audit=coordinator.audit(),
            command_trace=[f"0x{x:02x}" for x in result.command_trace],
            first_image_raster_shape=(
                list(result.first_image_raster_shape)
                if getattr(result, "first_image_raster_shape", None)
                else None
            ),
        )
    except BaseException as exc:
        report["failure_class"] = f"{type(exc).__name__}:{exc}"
        if coordinator is not None:
            report["runtime_audit"] = coordinator.audit()
    finally:
        if secret_owned_by_outer and secret is not None:
            try:
                secret.close()
            except BaseException as exc:
                report["secret_cleanup_failure"] = f"{type(exc).__name__}:{exc}"
        report["secret_ownership_transferred_to_coordinator"] = ownership_transferred
        if signals_transaction_started:
            try:
                dependencies.restore_signals()
            except BaseException as exc:
                report["signal_restore_failure"] = f"{type(exc).__name__}:{exc}"
        if fprintd_transaction_started:
            try:
                dependencies.restore_fprintd()
            except BaseException as exc:
                report["fprintd_restore_failure"] = f"{type(exc).__name__}:{exc}"
        if any(key.endswith("_failure") for key in report):
            report["result"] = "FAIL_CLOSED_CLEANUP_INCOMPLETE"
        report["report_destination_preflight_passed"] = (
            report_destination_preflight_passed
        )
        if report_destination_preflight_passed:
            try:
                dependencies.publish_report(report)
            except BaseException as exc:
                report["report_publication_failure"] = (
                    f"{type(exc).__name__}:{exc}"
                )
                report["result"] = "FAIL_CLOSED_REPORT_UNPUBLISHED"
    return report
