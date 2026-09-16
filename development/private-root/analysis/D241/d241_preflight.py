"""D241 root preflight; no libusb call and no sensor traffic."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from src.goodix5125_d232_offline import load_root_target_material
from src.goodix5125_d233_backend import SystemOsFacade
from src.goodix5125_d235_entrypoint import (
    ProductionRuntimePaths,
    SystemUsbTargetSelector,
    TARGET_PID,
    TARGET_VID,
)


REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = REPOSITORY / "analysis/D241/D241_preflight_report.json"
GFUSB_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
CONFIG90_SHA256 = "e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82"
MANIFEST_SHA256 = "1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15"
HISTORICAL_MARKER_NAMES = (
    "d236-live-single-use.marker",
    "d238-live-single-use.marker",
    "d238-operator-invocation.marker",
    "d239-operator-invocation.marker",
)
D241_MARKER_NAME = "d241-operator-invocation.marker"


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
    current = store / D241_MARKER_NAME
    historical = [
        name for name in HISTORICAL_MARKER_NAMES if os.path.lexists(store / name)
    ]
    return {
        "namespace": str(current),
        "d241_marker_absent": not os.path.lexists(current),
        "historical_markers_present_benign": historical,
        "historical_markers_blocking": False,
    }


def report_directory_status(directory: Path, *, owner_uid: int = 0) -> dict[str, object]:
    try:
        status = os.lstat(directory)
    except OSError:
        return {"pass": False, "reason": "missing"}
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


def publish(report: dict[str, object]) -> None:
    payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=".d241-preflight-", dir=OUTPUT.parent)
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


def offline_import_probe() -> int:
    paths = ProductionRuntimePaths.system_default()
    paths.validate()
    report = {
        "schema": "d241-preflight-import-probe-v1",
        "status": "pass",
        "repository": str(REPOSITORY),
        "cwd": str(Path.cwd().resolve()),
        "marker_namespace": str(paths.single_use_marker),
        "report_directory": str(paths.report_directory),
        "libusb_init_count": 0,
        "usb_open_count": 0,
        "goodix_command_count": 0,
        "live_marker_create_count": 0,
    }
    print(json.dumps(report, sort_keys=True))
    return 0


def offline_sandbox_preflight(root: Path) -> dict[str, object]:
    root = root.resolve()
    store = root / "var/lib/goodix-5125-poc"
    reports = store / "d241-results"
    store.mkdir(parents=True, exist_ok=True)
    reports.mkdir(mode=0o700, exist_ok=True)
    reports.chmod(0o700)
    for name in HISTORICAL_MARKER_NAMES:
        marker = store / name
        marker.write_text("historical fixture\n", encoding="ascii")
        marker.chmod(0o600)
    first = marker_namespace_status(store)
    current = store / D241_MARKER_NAME
    current.write_text("consumed fixture\n", encoding="ascii")
    current.chmod(0o600)
    second = marker_namespace_status(store)
    report = {
        "schema": "d241-offline-preflight-fixture-v1",
        "status": "PASS"
        if first["d241_marker_absent"]
        and not second["d241_marker_absent"]
        and report_directory_status(reports, owner_uid=os.getuid())["pass"]
        else "FAIL",
        "historical_markers_case": first,
        "consumed_d241_marker_case": second,
        "report_directory": report_directory_status(reports, owner_uid=os.getuid()),
        "libusb_init_count": 0,
        "usb_open_count": 0,
        "goodix_command_count": 0,
    }
    return report


def live_preflight() -> int:
    report: dict[str, object] = {
        "schema": "d241-preflight-report-v1",
        "operator_risk_acceptance": "granted",
        "status": "fail",
        "phase": "PREFLIGHT",
        "no_libusb_init": True,
        "usb_open_count": 0,
        "contains_secret": False,
        "contains_raw_config90": False,
    }
    failures: list[str] = []
    try:
        report["git_head"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
        report["git_status_short"] = subprocess.run(
            ["git", "status", "--short"], cwd=REPOSITORY, check=True,
            text=True, capture_output=True,
        ).stdout.splitlines()
        paths = ProductionRuntimePaths.system_default()
        paths.validate()
        report["runtime_paths"] = {key: str(value) for key, value in paths.__dict__.items()}

        gfusb_hash = sha256(paths.canonical_gfusb)
        report["canonical_gfusb_sha256"] = gfusb_hash
        if gfusb_hash != GFUSB_SHA256:
            failures.append("canonical_gfusb_hash")

        psk = protected_metadata(paths.psk_store, 88)
        report["psk_store_metadata"] = psk
        if not psk["pass"]:
            failures.append("psk_store_metadata")

        manifest = protected_metadata(
            paths.target_material_manifest, os.lstat(paths.target_material_manifest).st_size
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
            paths.target_material_manifest, paths.config90_store
        )
        if material.config90_sha256 != CONFIG90_SHA256:
            failures.append("config90_semantic_validation")

        facade = SystemOsFacade()
        euid, sudo_uid = facade.euid(), facade.sudo_uid()
        report.update(euid=euid, sudo_uid=sudo_uid)
        if euid != 0 or sudo_uid is None or sudo_uid == 0:
            failures.append("operator_identity")

        markers = marker_namespace_status(paths.psk_store.parent)
        report["marker_namespace_status"] = markers
        if not markers["d241_marker_absent"]:
            failures.append("d241_single_use_marker_consumed")

        report_dir = report_directory_status(paths.report_directory)
        report["report_directory_status"] = report_dir
        if not report_dir["pass"] or not facade.report_path_ready(paths.final_report):
            failures.append("durable_report_path")

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

        report["fprintd_initial_state"] = "active" if facade.fprintd_active() else "inactive"
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

    report["failures"] = failures
    report["failure_class"] = failures[0] if failures else "none"
    report["status"] = "pass" if not failures else "fail"
    publish(report)
    return 0 if not failures else 1


def main(argv: tuple[str, ...] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments == ("--offline-import-probe",):
        return offline_import_probe()
    if len(arguments) == 2 and arguments[0] == "--offline-sandbox-preflight":
        report = offline_sandbox_preflight(Path(arguments[1]))
        print(json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "PASS" else 1
    if arguments:
        print("d241_preflight: unexpected arguments", file=sys.stderr)
        return 64
    return live_preflight()


if __name__ == "__main__":
    raise SystemExit(main())
