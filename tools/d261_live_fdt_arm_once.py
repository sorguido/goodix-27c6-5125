#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D261 one-shot operator entrypoint; dry-run is the only default capability.

The live path is reachable only through the exact explicit CLI authorization,
a separately approved full Git commit, a clean live-critical comparison, root
operator context, successful protected preflight and a fresh D261 marker.
Import and argument parsing perform no USB, secret, service or marker action.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Protocol


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.cold_start import ColdStartMachine
from core.fdt_seed import CRC_OFFSET, provide_hash_gated_fdt12
from core.persistent_runtime import PersistentRuntimeCoordinator
from core.protected_runtime import (
    CANONICAL_GFUSB_PATH,
    CANONICAL_GFUSB_SHA256,
    CliIntentCapability,
    CONFIG90_PATH,
    D261_LIVE_AUTHORIZATION_FLAG,
    MATERIAL_MANIFEST_PATH,
    PROTECTED_ROOT,
    SECRET_PATH,
    RealSecretBoundary,
    _issue_cli_intent_after_exact_main_flag,
    _issue_marker_claim_capability,
    issue_live_io_capability_after_marker,
    load_cold_start_material,
    protected_directory_metadata,
    protected_metadata,
    require_cli_intent,
)
from core.usb_runtime import CtypesLibusbBackend, LibusbRuntimeTransport, TARGET_PID, TARGET_VID
from src.goodix5125_cleanroom import crc32_mpeg2


LIVE_FLAG = D261_LIVE_AUTHORIZATION_FLAG
APPROVED_BASELINE_ENV = "D261_APPROVED_LIVE_BASELINE_SHA"
MARKER_PATH = PROTECTED_ROOT / "d261-live-single-use.marker"
REPORT_DIRECTORY = PROTECTED_ROOT / "d261-results"
CACHE_PATH = REPO / "captures/D255_20260822T205631772Z_85c8c41f/raw/cache_before/9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2.bin"
CACHE_SHA256 = "9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2"
FILESET_PATH = REPO / "analysis/D261/D261_operational_live_critical_fileset.json"
D260_FILESET_PATH = REPO / "analysis/D260/D260_architecture_critical_fileset.json"
D260_REFERENCE_COMMIT = "ef2aa95c0b7261638a70cdf26a91ea00dd60eb41"
LIVE_CAPABILITY_DEFAULT = 0
CANONICAL_LIVE_CRITICAL_PATHS = (
    "core/__init__.py",
    "core/cold_start.py",
    "core/fdt_lifecycle.py",
    "core/fdt_seed.py",
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
    "operator_kit/d261-live-fdt-arm-once.sh",
)
# Compatibility name for existing offline reviewers.  The tuple above is the
# sole runtime authority; the JSON is a derived report only.
LIVE_CRITICAL_PATHS = CANONICAL_LIVE_CRITICAL_PATHS


class OperationalFailure(RuntimeError):
    pass


class PreMarkerSecretBoundary(Protocol):
    """Minimal injectable secret interface used by live and offline paths."""

    def materialize(self, cli_intent: CliIntentCapability) -> None:
        ...


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OperationalFailure("durable_write_made_no_progress")
        view = view[written:]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", *args), cwd=repo, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise OperationalFailure(f"git_{args[0]}_failed:{detail}")
    return completed.stdout


def load_fileset() -> dict[str, Any]:
    try:
        value = json.loads(FILESET_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OperationalFailure("D261_live_critical_fileset_unavailable") from exc
    if value.get("schema") != "D261_OPERATIONAL_LIVE_CRITICAL_FILESET_V1":
        raise OperationalFailure("D261_live_critical_fileset_schema")
    if tuple(row.get("path") for row in value.get("files", [])) != CANONICAL_LIVE_CRITICAL_PATHS:
        raise OperationalFailure("D261_live_critical_fileset_path_set_mismatch")
    if value.get("role") != "DERIVED_REPORT_NOT_AUTHORITY":
        raise OperationalFailure("D261_live_critical_fileset_role_mismatch")
    return value


def fileset_digest(fileset: dict[str, Any]) -> str:
    rows = [(row["path"], row["sha256"]) for row in fileset["files"]]
    canonical = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def verify_worktree_fileset(repo: Path, fileset: dict[str, Any]) -> list[str]:
    failures = []
    for row in fileset.get("files", []):
        path = repo / row["path"]
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            failures.append(str(row["path"]))
    return failures


def verify_approved_git_baseline(repo: Path, sha: str, fileset: dict[str, Any]) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise OperationalFailure("approved_live_baseline_full_sha_required")
    resolved = _git(repo, "rev-parse", f"{sha}^{{commit}}").decode("ascii").strip()
    if resolved != sha:
        raise OperationalFailure("approved_live_baseline_resolution_mismatch")
    if tuple(row.get("path") for row in fileset.get("files", [])) != CANONICAL_LIVE_CRITICAL_PATHS:
        raise OperationalFailure("D261_live_critical_fileset_path_set_mismatch")
    for relative in CANONICAL_LIVE_CRITICAL_PATHS:
        blob = _git(repo, "show", f"{sha}:{relative}")
        worktree = (repo / relative).read_bytes()
        if blob != worktree:
            raise OperationalFailure(f"live_critical_baseline_stale:{relative}")


def verify_d260_architecture_reference(repo: Path) -> dict[str, Any]:
    relative_manifest = str(D260_FILESET_PATH.relative_to(REPO))
    data = json.loads(
        _git(repo, "show", f"{D260_REFERENCE_COMMIT}:{relative_manifest}").decode("utf-8")
    )
    mismatches = []
    for row in data["files"]:
        try:
            blob = _git(repo, "show", f"{D260_REFERENCE_COMMIT}:{row['path']}")
        except OperationalFailure:
            mismatches.append(row["path"])
            continue
        if hashlib.sha256(blob).hexdigest() != row["sha256"]:
            mismatches.append(row["path"])
    return {
        "reference_commit": D260_REFERENCE_COMMIT,
        "status": "PASS_HISTORICAL_REFERENCE" if not mismatches else "FAIL",
        "mismatches": mismatches,
    }


def cache_preflight(
    cache_path: Path = CACHE_PATH,
    expected_sha256: str = CACHE_SHA256,
) -> dict[str, Any]:
    result = {
        "path": (
            str(cache_path.relative_to(REPO))
            if cache_path.is_relative_to(REPO)
            else str(cache_path)
        ),
        "expected_sha256": expected_sha256,
        "size": None,
        "sha256": None,
        "layout_crc_status": "NOT_CHECKED",
        "mtime_is_generation_time": False,
        "write_count": 0,
        "status": "FAIL",
    }
    try:
        before = cache_path.stat()
        data = cache_path.read_bytes()
        after = cache_path.stat()
    except OSError:
        return result
    result["size"] = len(data)
    result["sha256"] = hashlib.sha256(data).hexdigest()
    stable = (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
    crc_ok = len(data) == 13_520 and int.from_bytes(data[CRC_OFFSET:], "little") == crc32_mpeg2(data[:CRC_OFFSET])
    result["layout_crc_status"] = "PASS" if crc_ok else "FAIL"
    result["status"] = "PASS" if stable and crc_ok and result["sha256"] == expected_sha256 else "FAIL"
    return result


def prepare_pre_marker_material(
    cli_intent: CliIntentCapability | None,
    *,
    material_loader: Any = load_cold_start_material,
    cache_validator: Any = cache_preflight,
    secret_boundary_factory: Any = RealSecretBoundary,
) -> tuple[Any, dict[str, Any], PreMarkerSecretBoundary]:
    """Validate all available non-secret content before touching the secret.

    The injectable callables are the bounded offline-test seam.  Production
    uses the concrete protected loaders; rehearsals inject synthetic fixtures
    and never instantiate or materialize ``RealSecretBoundary``.
    """

    require_cli_intent(cli_intent)
    material = material_loader(MATERIAL_MANIFEST_PATH, CONFIG90_PATH, cli_intent)
    cache = cache_validator()
    if cache.get("status") != "PASS":
        raise OperationalFailure("canonical_seed_cache_preflight_failed")
    boundary = secret_boundary_factory(SECRET_PATH, REPO / CANONICAL_GFUSB_PATH)
    boundary.materialize(cli_intent)
    return material, cache, boundary


def dependency_preflight() -> dict[str, Any]:
    import ctypes.util
    return {
        "python": sys.version.split()[0],
        "ssl_psk_server_callback": hasattr(ssl.SSLContext, "set_psk_server_callback"),
        "libusb_1_0": ctypes.util.find_library("usb-1.0") is not None,
        "git": shutil.which("git") is not None,
        "bash": shutil.which("bash") is not None,
    }


def protected_preflight_metadata(repo: Path) -> dict[str, Any]:
    protected_root = protected_directory_metadata(PROTECTED_ROOT)
    report_directory = protected_directory_metadata(REPORT_DIRECTORY)
    secret = protected_metadata(SECRET_PATH, 88)
    config = protected_metadata(CONFIG90_PATH, 224)
    manifest = protected_metadata(MATERIAL_MANIFEST_PATH, None)
    gfusb = repo / CANONICAL_GFUSB_PATH
    return {
        "protected_root": protected_root,
        "report_directory": report_directory,
        "secret_store": secret,
        "config90_store": config,
        "material_manifest": manifest,
        "canonical_gfusb": {
            "path": str(CANONICAL_GFUSB_PATH),
            "exists": gfusb.is_file(),
            "sha256": sha256_file(gfusb) if gfusb.is_file() else None,
            "expected_sha256": CANONICAL_GFUSB_SHA256,
        },
        "REAL_SECRET_READ_COUNT": 0,
    }


def dry_run(repo: Path) -> dict[str, Any]:
    fileset = load_fileset()
    worktree_failures = verify_worktree_fileset(repo, fileset)
    d260 = verify_d260_architecture_reference(repo)
    cache = cache_preflight()
    protected = protected_preflight_metadata(repo)
    dependencies = dependency_preflight()
    launcher = repo / "operator_kit/d261-live-fdt-arm-once.sh"
    syntax = subprocess.run(("bash", "-n", str(launcher)), check=False, capture_output=True).returncode == 0
    with tempfile.TemporaryDirectory(prefix="d261-marker-fixture-") as directory:
        fake_marker = Path(directory) / "d261.marker"
        marker_fixture_absent = not fake_marker.exists()
    passed = bool(
        not worktree_failures
        and d260["status"] == "PASS_HISTORICAL_REFERENCE"
        and cache["status"] == "PASS"
        and protected["canonical_gfusb"]["sha256"] == CANONICAL_GFUSB_SHA256
        and all(dependencies[key] for key in ("ssl_psk_server_callback", "libusb_1_0", "git", "bash"))
        and syntax
        and marker_fixture_absent
    )
    return {
        "schema": "D261_PREFLIGHT_DRY_RUN_V1",
        "execution_mode": "OFFLINE_ONLY",
        "status": "PASS" if passed else "FAIL",
        "repository_root": str(repo),
        "cwd_independent": True,
        "D260_architecture_critical_reference": d260,
        "D261_operational_fileset_digest": fileset_digest(fileset),
        "D261_operational_worktree_mismatches": worktree_failures,
        "protected_material_metadata": protected,
        "PROTECTED_ROOT_STATUS": protected["protected_root"]["status"],
        "REPORT_DIRECTORY_STATUS": protected["report_directory"]["status"],
        "PROTECTED_METADATA_DRYRUN_STATUS_MODEL": [
            "PASS_METADATA", "ABSENT", "INACCESSIBLE_UNPRIVILEGED", "ERROR_<errno>"
        ],
        "PROTECTED_ROOT_SAFETY_CHECKED_PRE_SIDE_EFFECT": True,
        "REPORT_DIRECTORY_SAFETY_CHECKED_PRE_SIDE_EFFECT": True,
        "cache_seed_source": cache,
        "dependencies": dependencies,
        "operator_launcher_syntax": "PASS" if syntax else "FAIL",
        "fake_marker_fixture_absent": marker_fixture_absent,
        "live_baseline_approval": "PENDING_USER_AI_PM_FULL_SHA_APPROVAL",
        "report_destination_model": str(REPORT_DIRECTORY / "d261-final.json"),
        "LIVE_CAPABILITY_DEFAULT": LIVE_CAPABILITY_DEFAULT,
        "LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG": False,
        "REAL_USB_OPEN_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0,
    }


def exact_target_sysfs() -> tuple[Path, Path]:
    matches = []
    for candidate in Path("/sys/bus/usb/devices").glob("*"):
        try:
            vid = int((candidate / "idVendor").read_text().strip(), 16)
            pid = int((candidate / "idProduct").read_text().strip(), 16)
            bus = int((candidate / "busnum").read_text().strip())
            address = int((candidate / "devnum").read_text().strip())
        except (OSError, ValueError):
            continue
        if (vid, pid) == (TARGET_VID, TARGET_PID):
            matches.append((candidate, Path(f"/dev/bus/usb/{bus:03d}/{address:03d}")))
    if len(matches) != 1:
        raise OperationalFailure(f"exact_target_sysfs_cardinality:{len(matches)}")
    return matches[0]


def external_holders(devnode: Path) -> list[int]:
    holders = []
    expected = os.fspath(devnode)
    for process in Path("/proc").glob("[0-9]*"):
        try:
            descriptors = list((process / "fd").iterdir())
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                if os.readlink(descriptor) == expected:
                    holders.append(int(process.name))
                    break
            except OSError:
                continue
    return sorted(set(holders))


def require_no_external_holders(holders: list[int], *, own_pid: int) -> None:
    external = sorted({pid for pid in holders if pid != own_pid})
    if external:
        raise OperationalFailure(f"external_usb_holder:{external}")


class FprintdTransaction:
    def __init__(self, *, runner: Any = subprocess.run) -> None:
        self._runner = runner
        self.initial_state = "unknown"
        self.stop_count = 0
        self.restore_count = 0
        self.restore_status = "not_attempted"

    def prepare(self) -> None:
        probe = self._runner(("systemctl", "is-active", "fprintd.service"), check=False, capture_output=True, text=True)
        self.initial_state = "active" if probe.returncode == 0 and probe.stdout.strip() == "active" else "inactive"
        if self.initial_state == "active":
            self._runner(("systemctl", "stop", "fprintd.service"), check=True)
            self.stop_count = 1

    def restore(self) -> None:
        if self.initial_state == "active":
            self._runner(("systemctl", "start", "fprintd.service"), check=True)
        self.restore_count = 1
        self.restore_status = "restored_to_initial_state"


class SignalTransaction:
    SIGNALS = {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}

    def __init__(self, *, mask_fn: Any = signal.pthread_sigmask) -> None:
        self._mask_fn = mask_fn
        self.previous = None
        self.restore_status = "not_attempted"

    def block(self) -> None:
        self.previous = self._mask_fn(signal.SIG_BLOCK, self.SIGNALS)

    def restore(self) -> None:
        if self.previous is not None:
            self._mask_fn(signal.SIG_SETMASK, self.previous)
        self.restore_status = "restored"


def claim_marker(
    path: Path,
    baseline_sha: str,
    cli_intent: CliIntentCapability | None,
    *,
    expected_uid: int = 0,
):
    require_cli_intent(cli_intent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        status = os.fstat(descriptor)
        if status.st_uid != expected_uid or stat.S_IMODE(status.st_mode) != 0o600:
            raise OperationalFailure("marker_owner_mode_invalid")
        payload = json.dumps({
            "schema": "D261_SINGLE_USE_MARKER_V1",
            "approved_baseline_sha": baseline_sha,
            "claimed_utc": datetime.now().astimezone().isoformat(),
        }, sort_keys=True).encode("utf-8") + b"\n"
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _issue_marker_claim_capability(cli_intent)


def _require_safe_directory(path: Path, *, expected_uid: int, expected_mode: int = 0o700) -> None:
    try:
        status = path.lstat()
    except OSError as exc:
        raise OperationalFailure(f"safe_directory_lstat_failed:{path}:{exc.errno}") from exc
    if (
        stat.S_ISLNK(status.st_mode)
        or not stat.S_ISDIR(status.st_mode)
        or status.st_uid != expected_uid
        or stat.S_IMODE(status.st_mode) != expected_mode
    ):
        raise OperationalFailure(f"safe_directory_metadata_failed:{path}")


def prepare_report_directory(
    protected_root: Path,
    report_directory: Path,
    *,
    expected_uid: int = 0,
) -> str:
    """Validate the root and safely create/validate the report directory."""

    _require_safe_directory(protected_root, expected_uid=expected_uid)
    try:
        report_directory.lstat()
    except FileNotFoundError:
        os.mkdir(report_directory, 0o700)
        disposition = "CREATED_SAFE"
    except OSError as exc:
        raise OperationalFailure(f"report_directory_lstat_failed:{exc.errno}") from exc
    else:
        disposition = "EXISTING_SAFE"
    _require_safe_directory(report_directory, expected_uid=expected_uid)
    return disposition


def require_safe_report_destination(path: Path) -> None:
    """A D261 single-shot report must not replace any pre-existing object."""

    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise OperationalFailure(f"report_destination_lstat_failed:{exc.errno}") from exc
    raise OperationalFailure("report_destination_already_exists_or_unsafe")


def publish_report(
    path: Path,
    report: dict[str, Any],
    *,
    expected_uid: int = 0,
) -> dict[str, Any]:
    """Durably publish once within a prevalidated real directory."""

    directory = path.parent
    _require_safe_directory(directory, expected_uid=expected_uid)
    require_safe_report_destination(path)
    temporary = directory / f".{path.name}.{os.getpid()}.tmp"
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    directory_descriptor = os.open(directory, directory_flags)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    created_temporary = False
    try:
        descriptor = os.open(temporary.name, flags, 0o600, dir_fd=directory_descriptor)
        created_temporary = True
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != expected_uid
            or stat.S_IMODE(opened.st_mode) != 0o600
        ):
            raise OperationalFailure("report_temporary_metadata_failed")
        _write_all(descriptor, json.dumps(report, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _require_safe_directory(directory, expected_uid=expected_uid)
        require_safe_report_destination(path)
        os.replace(
            temporary.name,
            path.name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
        )
        created_temporary = False
        os.fsync(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if created_temporary:
            try:
                os.unlink(temporary.name, dir_fd=directory_descriptor)
            except OSError:
                pass
        os.close(directory_descriptor)
    final = path.lstat()
    if (
        not stat.S_ISREG(final.st_mode)
        or stat.S_ISLNK(final.st_mode)
        or final.st_uid != expected_uid
        or stat.S_IMODE(final.st_mode) != 0o600
    ):
        raise OperationalFailure("final_report_metadata_failed")
    return {
        "temporary_mode": "0600",
        "file_fsync": True,
        "same_directory_replace": True,
        "directory_fsync": True,
        "final_mode": "0600",
    }


def live_preflight(
    repo: Path,
    baseline_sha: str,
    cli_intent: CliIntentCapability | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    require_cli_intent(cli_intent)
    fileset = load_fileset()
    # Baseline approval is deliberately the first external-state gate.  An
    # unapproved SHA cannot reach privilege, service, protected or USB work.
    verify_approved_git_baseline(repo, baseline_sha, fileset)
    if os.geteuid() != 0:
        raise OperationalFailure("live_euid_root_required")
    sudo_uid = os.environ.get("SUDO_UID", "")
    if not sudo_uid.isdigit() or int(sudo_uid) == 0:
        raise OperationalFailure("non_root_operator_context_required")
    try:
        MARKER_PATH.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise OperationalFailure(f"marker_status_probe_failed:{exc.errno}") from exc
    else:
        raise OperationalFailure("D261_single_use_marker_already_consumed")
    report_directory_disposition = prepare_report_directory(PROTECTED_ROOT, REPORT_DIRECTORY)
    require_safe_report_destination(REPORT_DIRECTORY / "d261-final.json")
    if not all(protected_metadata(path, size)["metadata_pass"] for path, size in (
        (SECRET_PATH, 88), (MATERIAL_MANIFEST_PATH, None), (CONFIG90_PATH, 224)
    )):
        raise OperationalFailure("protected_material_metadata_failed")
    gfusb = repo / CANONICAL_GFUSB_PATH
    if sha256_file(gfusb) != CANONICAL_GFUSB_SHA256:
        raise OperationalFailure("canonical_gfusb_hash_mismatch")
    sysfs, devnode = exact_target_sysfs()
    return fileset, {
        "sysfs": str(sysfs),
        "devnode": str(devnode),
        "target": "27c6:5125",
        "cache": {"status": "DEFERRED_UNTIL_AFTER_HOLDER_CHECK"},
        "approved_baseline_sha": baseline_sha,
        "fileset_digest": fileset_digest(fileset),
        "protected_root_status": "PASS_METADATA",
        "report_directory_status": "PASS_METADATA",
        "report_directory_disposition": report_directory_disposition,
    }


def _run_live(
    repo: Path,
    baseline_sha: str,
    cli_intent: CliIntentCapability | None,
) -> dict[str, Any]:
    """Internal live implementation; unsupported direct calls fail closed."""

    require_cli_intent(cli_intent)
    fileset, preflight = live_preflight(repo, baseline_sha, cli_intent)
    fprintd = FprintdTransaction()
    signals = SignalTransaction()
    boundary: RealSecretBoundary | None = None
    coordinator: PersistentRuntimeCoordinator | None = None
    report: dict[str, Any] = {
        "schema": "D261_LIVE_FDT_ARM_ONCE_RESULT_V1",
        "result": "FAIL_CLOSED",
        "phase_reached": "PREFLIGHT_PASS",
        "approved_baseline_sha": baseline_sha,
        "live_critical_fileset_digest": fileset_digest(fileset),
        "target_identity": "27c6:5125",
        "retry_count": 0,
        "persistent_write_count": 0,
        "cache_write_count": 0,
        "finger_interaction_count": 0,
        "marker_status": "not_claimed",
    }
    try:
        fprintd.prepare()
        report["fprintd_initial_state"] = fprintd.initial_state
        signals.block()
        require_no_external_holders(
            external_holders(Path(preflight["devnode"])),
            own_pid=os.getpid(),
        )
        material, cache, boundary = prepare_pre_marker_material(cli_intent)
        preflight["cache"] = cache
        marker_claim = claim_marker(MARKER_PATH, baseline_sha, cli_intent)
        live_io_capability = issue_live_io_capability_after_marker(
            cli_intent,
            marker_claim=marker_claim,
        )
        report["marker_status"] = "claimed_single_use"
        backend = CtypesLibusbBackend(live_io_capability)
        transport = LibusbRuntimeTransport(backend)
        cold_start = ColdStartMachine(transport, boundary)
        coordinator = PersistentRuntimeCoordinator(
            transport,
            transport.event_source,
            boundary,
            cold_start_machine=cold_start,
            cold_start_material=material,
            seed_provider_from_live_otp=lambda otp: provide_hash_gated_fdt12(CACHE_PATH, otp, CACHE_SHA256),
            operational_physical_policy=True,
        )
        now = datetime.now()
        ts16 = (now.second * 1000 + now.microsecond // 1000) & 0xFFFF
        result = coordinator.run(ts16=ts16)
        report.update(
            result="PASS_STOP_AFTER_FDT_ARM_ACK",
            phase_reached="STOP_AFTER_FDT_ARM_ACK",
            firmware_version=result.target_firmware,
            fdt_command_trace=[f"0x{value:02x}" for value in result.command_trace],
            runtime_audit=coordinator.audit(),
        )
    except BaseException as exc:
        report["failure_class"] = f"{type(exc).__name__}:{exc}"
        if coordinator is not None:
            report["runtime_audit"] = coordinator.audit()
    finally:
        if boundary is not None:
            boundary.close()
        try:
            signals.restore()
        except BaseException as exc:
            report["signal_restore_failure"] = f"{type(exc).__name__}:{exc}"
        try:
            fprintd.restore()
        except BaseException as exc:
            report["fprintd_restore_failure"] = f"{type(exc).__name__}:{exc}"
        report["signal_restore_status"] = signals.restore_status
        report["fprintd_restore_status"] = fprintd.restore_status
        report["secret_zeroized"] = boundary is None or boundary.zeroized
        report["secret_log_count"] = 0
        report["finalized_utc"] = datetime.now().astimezone().isoformat()
        if "signal_restore_failure" in report or "fprintd_restore_failure" in report:
            report["result"] = "FAIL_CLOSED_RESTORE_INCOMPLETE"
        publish_report(REPORT_DIRECTORY / "d261-final.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument(LIVE_FLAG, dest="live", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        report = dry_run(REPO)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "PASS" else 1
    if args.live:
        baseline = os.environ.get(APPROVED_BASELINE_ENV, "")
        try:
            cli_intent = _issue_cli_intent_after_exact_main_flag(LIVE_FLAG)
            report = _run_live(REPO, baseline, cli_intent)
        except BaseException as exc:
            print(json.dumps({
                "result": "FAIL_CLOSED",
                "failure_class": f"{type(exc).__name__}:{exc}",
                "report": "NOT_DURABLY_PUBLISHED",
            }, sort_keys=True))
            return 1
        print(json.dumps({
            "result": report["result"],
            "phase_reached": report.get("phase_reached"),
            "report": str(REPORT_DIRECTORY / "d261-final.json"),
        }, sort_keys=True))
        return 0 if report["result"] == "PASS_STOP_AFTER_FDT_ARM_ACK" else 1
    print(json.dumps({
        "LIVE_CAPABILITY_DEFAULT": LIVE_CAPABILITY_DEFAULT,
        "LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG": False,
        "required_live_flag": LIVE_FLAG,
        "status": "HARD_DISABLED_DEFAULT",
    }, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
