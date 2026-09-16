# SPDX-License-Identifier: GPL-2.0-or-later
"""Minimal D250 root preflight; it never initializes libusb or sends commands."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import sys
import tempfile
from pathlib import Path

from analysis.D250.d250_live_critical import baseline_state
from src.goodix5125_d232_offline import load_root_target_material
from src.goodix5125_d233_backend import SystemOsFacade
from src.goodix5125_d235_entrypoint import (
    ProductionRuntimePaths,
    SystemUsbTargetSelector,
    TARGET_PID,
    TARGET_VID,
)


REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = REPOSITORY / "analysis/D250/D250_preflight_report.json"
GFUSB_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
CONFIG90_SHA256 = "e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82"
MANIFEST_SHA256 = "1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15"
D250_MARKER_NAME = "d250-operator-invocation.marker"
HISTORICAL_MARKER_NAMES = (
    "d245-operator-invocation.marker",
    "d246-operator-invocation.marker",
)
BACKEND_SOURCE = REPOSITORY / "src/goodix5125_d233_backend.py"
ENTRYPOINT_SOURCE = REPOSITORY / "src/goodix5125_d235_entrypoint.py"


def d250_runtime_paths() -> ProductionRuntimePaths:
    sealed = ProductionRuntimePaths.system_default()
    store = sealed.psk_store.parent
    reports = store / "d250-results"
    return ProductionRuntimePaths(
        psk_store=sealed.psk_store,
        target_material_manifest=sealed.target_material_manifest,
        config90_store=sealed.config90_store,
        canonical_gfusb=sealed.canonical_gfusb,
        report_directory=reports,
        checkpoint_report=reports / "d250-live-pre-restore.json",
        final_report=reports / "d250-live-result.json",
        single_use_marker=store / D250_MARKER_NAME,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def protected_metadata(path: Path, expected_size: int) -> dict[str, object]:
    status = os.lstat(path)
    return {
        "regular": stat.S_ISREG(status.st_mode),
        "symlink": stat.S_ISLNK(status.st_mode),
        "owner_uid": status.st_uid,
        "mode": f"{stat.S_IMODE(status.st_mode):04o}",
        "size": status.st_size,
        "pass": (
            stat.S_ISREG(status.st_mode)
            and not stat.S_ISLNK(status.st_mode)
            and status.st_uid == 0
            and stat.S_IMODE(status.st_mode) == 0o600
            and status.st_size == expected_size
        ),
    }


def marker_namespace_status(store: Path) -> dict[str, object]:
    current = store / D250_MARKER_NAME
    return {
        "namespace": str(current),
        "d250_marker_absent": not os.path.lexists(current),
        "historical_markers_present_benign": [
            name for name in HISTORICAL_MARKER_NAMES if os.path.lexists(store / name)
        ],
        "historical_markers_blocking": False,
    }


def report_directory_status(directory: Path, *, owner_uid: int = 0) -> dict[str, object]:
    try:
        status = os.lstat(directory)
    except OSError:
        return {"pass": False, "reason": "missing", "directory": str(directory)}
    passed = (
        stat.S_ISDIR(status.st_mode)
        and not stat.S_ISLNK(status.st_mode)
        and status.st_uid == owner_uid
        and stat.S_IMODE(status.st_mode) == 0o700
        and os.access(directory, os.W_OK)
    )
    return {
        "pass": passed,
        "directory": str(directory),
        "owner_uid": status.st_uid,
        "mode": f"{stat.S_IMODE(status.st_mode):04o}",
        "symlink": stat.S_ISLNK(status.st_mode),
    }


def source_seal_status() -> dict[str, object]:
    backend = BACKEND_SOURCE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT_SOURCE.read_text(encoding="utf-8")
    backend_sealed = 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' in backend
    entrypoint_sealed = (
        'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")'
        in entrypoint
    )
    return {
        "backend_sealed": backend_sealed,
        "entrypoint_sealed": entrypoint_sealed,
        "pass": backend_sealed and entrypoint_sealed,
    }


def publish(report: dict[str, object]) -> None:
    payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=".d250-preflight-", dir=OUTPUT.parent)
    temporary = Path(name)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, OUTPUT)
        operator = os.environ.get("SUDO_UID")
        if operator is not None and operator.isdecimal():
            os.chown(OUTPUT, int(operator), -1)
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()


def _initial_report() -> dict[str, object]:
    return {
        "schema": "d250-preflight-report-v1",
        "status": "fail",
        "phase": "PREFLIGHT",
        "no_libusb_init": True,
        "libusb_init_count": 0,
        "usb_open_count": 0,
        "goodix_command_count": 0,
        "tls_handshake_count": 0,
        "d4_send_count": 0,
        "af_attempt_count": 0,
        "af_send_count": 0,
        "real_secret_read_count": 0,
        "fprintd_mutation_count": 0,
        "live_marker_create_count": 0,
        "contains_secret": False,
        "contains_raw_config90": False,
        "durable_preflight_report": str(OUTPUT),
    }


def _finish(report: dict[str, object], failures: list[str]) -> int:
    report["failures"] = failures
    report["failure_class"] = failures[0] if failures else "none"
    report["status"] = "pass" if not failures else "fail"
    publish(report)
    return 0 if not failures else 1


def offline_sandbox_preflight(root: Path) -> dict[str, object]:
    store = root.resolve() / "var/lib/goodix-5125-poc"
    reports = store / "d250-results"
    reports.mkdir(parents=True, mode=0o700, exist_ok=True)
    reports.chmod(0o700)
    historical_before: dict[str, bytes] = {}
    for name in HISTORICAL_MARKER_NAMES:
        marker = store / name
        marker.write_text("historical fixture\n", encoding="ascii")
        marker.chmod(0o600)
        historical_before[name] = marker.read_bytes()
    absent_case = marker_namespace_status(store)
    current = store / D250_MARKER_NAME
    current.write_text("consumed fixture\n", encoding="ascii")
    current.chmod(0o600)
    present_case = marker_namespace_status(store)
    directory = report_directory_status(reports, owner_uid=os.getuid())
    historical_untouched = all(
        (store / name).read_bytes() == content
        for name, content in historical_before.items()
    )
    passed = bool(
        absent_case["d250_marker_absent"]
        and set(absent_case["historical_markers_present_benign"])
        == set(HISTORICAL_MARKER_NAMES)
        and not absent_case["historical_markers_blocking"]
        and not present_case["d250_marker_absent"]
        and directory["pass"]
        and historical_untouched
    )
    return {
        **_initial_report(),
        "schema": "d250-offline-preflight-fixture-v1",
        "status": "PASS" if passed else "FAIL",
        "marker_absent_case": absent_case,
        "marker_present_case": present_case,
        "report_directory": directory,
        "historical_markers_touched": not historical_untouched,
    }


def live_preflight() -> int:
    report = _initial_report()
    failures: list[str] = []
    try:
        paths = d250_runtime_paths()
        paths.validate()
        report["runtime_paths"] = {
            key: str(value) for key, value in paths.__dict__.items()
        }

        facade = SystemOsFacade()
        euid, sudo_uid = facade.euid(), facade.sudo_uid()
        report.update(euid=euid, sudo_uid=sudo_uid)
        if euid != 0 or sudo_uid is None or sudo_uid == 0:
            failures.append("operator_identity")

        markers = marker_namespace_status(paths.psk_store.parent)
        report["marker_namespace_status"] = markers
        if not markers["d250_marker_absent"]:
            failures.append("d250_single_use_marker_consumed")

        report_dir = report_directory_status(paths.report_directory)
        report["report_directory_status"] = report_dir
        if not report_dir["pass"] or not facade.report_path_ready(paths.final_report):
            failures.append("durable_report_path")

        seal = source_seal_status()
        report["source_seal"] = seal
        if not seal["pass"]:
            failures.append("source_not_sealed")

        approved_sha = os.environ.get("D250_APPROVED_LIVE_BASELINE_SHA", "")
        approved_state = baseline_state(REPOSITORY, approved_sha)
        report["approved_baseline_sha"] = approved_sha if len(approved_sha) == 40 else "UNAVAILABLE"
        report["live_critical_set_status"] = approved_state
        if approved_state == "UNAPPROVED":
            failures.append("live_baseline_not_approved")
        elif approved_state != "APPROVED":
            failures.append("live_critical_baseline_stale")

        # Outer gates fail before protected input inspection or USB enumeration.
        if failures:
            return _finish(report, failures)

        gfusb_hash = sha256(paths.canonical_gfusb)
        report["canonical_gfusb_sha256"] = gfusb_hash
        if gfusb_hash != GFUSB_SHA256:
            failures.append("canonical_gfusb_hash")

        psk = protected_metadata(paths.psk_store, 88)
        report["psk_store_metadata"] = psk
        if not psk["pass"]:
            failures.append("psk_store_metadata")

        manifest = protected_metadata(
            paths.target_material_manifest,
            os.lstat(paths.target_material_manifest).st_size,
        )
        manifest_hash = sha256(paths.target_material_manifest)
        manifest["sha256"] = manifest_hash
        manifest["pass"] = bool(manifest["pass"] and manifest_hash == MANIFEST_SHA256)
        report["target_material_manifest"] = manifest
        if not manifest["pass"]:
            failures.append("target_material_manifest")

        config = protected_metadata(paths.config90_store, 224)
        config_hash = sha256(paths.config90_store)
        config["sha256"] = config_hash
        config["pass"] = bool(config["pass"] and config_hash == CONFIG90_SHA256)
        report["config90_store_metadata"] = config
        if not config["pass"]:
            failures.append("config90_store_metadata")
        material = load_root_target_material(
            paths.target_material_manifest,
            paths.config90_store,
        )
        if material.config90_sha256 != CONFIG90_SHA256:
            failures.append("config90_semantic_validation")

        report["process_count"] = facade.process_count()
        report["thread_count"] = facade.thread_count()
        if report["process_count"] != 1 or report["thread_count"] != 1:
            failures.append("process_thread_topology")

        target = SystemUsbTargetSelector().resolve_exact(TARGET_VID, TARGET_PID)
        holders = facade.external_holders(target.device_path)
        report["external_holders"] = list(holders)
        if holders:
            failures.append("unexpected_external_holders")
        report["target"] = {
            "vid": f"{target.identity.vid:04x}",
            "pid": f"{target.identity.pid:04x}",
            "bus": target.identity.bus,
            "address": target.identity.address,
            "port_path": list(target.identity.port_path),
            "device_path": str(target.device_path),
        }

        report["fprintd_initial_state"] = (
            "active" if facade.fprintd_active() else "inactive"
        )
        previous = facade.block_signals(
            frozenset((signal.SIGINT, signal.SIGTERM, signal.SIGHUP))
        )
        facade.restore_signals(previous)
        report["signal_mask_prepare_restore"] = "pass"
        udev = Path("/etc/udev/rules.d/70-goodix-5125.rules")
        report["udev_rule_absent"] = not os.path.lexists(udev)
        if not report["udev_rule_absent"]:
            failures.append("udev_rule_present")
    except Exception as exc:
        report["preflight_exception"] = type(exc).__name__
        report["preflight_exception_message"] = str(exc)
        failures.append("preflight_exception")
    return _finish(report, failures)


def main(argv: tuple[str, ...] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if len(arguments) == 2 and arguments[0] == "--offline-sandbox-preflight":
        report = offline_sandbox_preflight(Path(arguments[1]))
        print(json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "PASS" else 1
    if arguments:
        print("d250_preflight: unexpected arguments", file=sys.stderr)
        return 64
    return live_preflight()


if __name__ == "__main__":
    raise SystemExit(main())
