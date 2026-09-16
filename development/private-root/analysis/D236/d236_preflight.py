"""D236 root preflight. It performs no libusb call and sends no device traffic."""

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
OUTPUT = REPOSITORY / "analysis/D236/D236_preflight_report.json"
GFUSB_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
CONFIG90_SHA256 = "e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82"
MANIFEST_SHA256 = "1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15"


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


def publish(report: dict[str, object]) -> None:
    payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=".d236-preflight-", dir=OUTPUT.parent)
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


def d239_offline_import_probe() -> int:
    """Exercise imports and production path construction without system access."""
    paths = ProductionRuntimePaths.system_default()
    paths.validate()
    report = {
        "schema": "d239-preflight-import-probe-v1",
        "status": "pass",
        "repository": str(REPOSITORY),
        "cwd": str(Path.cwd().resolve()),
        "modules_loaded": [
            "src.goodix5125_d232_offline",
            "src.goodix5125_d233_backend",
            "src.goodix5125_d235_entrypoint",
        ],
        "runtime_paths": {
            key: str(value) for key, value in paths.__dict__.items()
        },
        "protected_input_read_count": 0,
        "libusb_init_count": 0,
        "usb_open_count": 0,
        "goodix_command_count": 0,
        "live_marker_create_count": 0,
        "live_usb_execution": "NOT_PERFORMED",
    }
    print(json.dumps(report, sort_keys=True))
    return 0


def main(argv: tuple[str, ...] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments == ("--d239-offline-import-probe",):
        return d239_offline_import_probe()
    if arguments:
        print("d236_preflight: unexpected arguments", file=sys.stderr)
        return 64
    report: dict[str, object] = {
        "schema": "d236-preflight-report-v1",
        "operator_risk_acceptance": "granted",
        "status": "fail",
        "no_libusb_init": True,
        "usb_open_count": 0,
        "contains_secret": False,
        "contains_raw_config90": False,
    }
    failures: list[str] = []
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
        status_lines = subprocess.run(
            ["git", "status", "--short"], cwd=REPOSITORY, check=True,
            text=True, capture_output=True,
        ).stdout.splitlines()
        report.update(git_head=head, git_status_short=status_lines)

        paths = ProductionRuntimePaths.system_default()
        paths.validate()
        report["runtime_paths"] = {key: str(value) for key, value in paths.__dict__.items()}

        gfusb_hash = sha256(paths.canonical_gfusb)
        report["canonical_gfusb_sha256"] = gfusb_hash
        report["canonical_gfusb_status"] = "pass" if gfusb_hash == GFUSB_SHA256 else "fail"
        if gfusb_hash != GFUSB_SHA256:
            failures.append("canonical_gfusb_hash")

        psk = protected_metadata(paths.psk_store, 88)
        report["psk_store_metadata"] = psk
        if not psk["pass"]:
            failures.append("psk_store_metadata")

        manifest = protected_metadata(paths.target_material_manifest, os.lstat(paths.target_material_manifest).st_size)
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
        try:
            material = load_root_target_material(
                paths.target_material_manifest, paths.config90_store
            )
            report["config90_semantic_validation"] = (
                "pass" if material.config90_sha256 == CONFIG90_SHA256 else "fail"
            )
        except Exception as exc:
            report["config90_semantic_validation"] = "fail"
            report["config90_semantic_error"] = type(exc).__name__
            failures.append("config90_semantic_validation")

        facade = SystemOsFacade()
        euid = facade.euid()
        sudo_uid = facade.sudo_uid()
        report.update(euid=euid, sudo_uid=sudo_uid)
        if euid != 0 or sudo_uid is None or sudo_uid == 0:
            failures.append("operator_identity")

        report["single_use_marker_absent"] = not os.path.lexists(paths.single_use_marker)
        if not report["single_use_marker_absent"]:
            failures.append("single_use_marker")

        report["process_count"] = facade.process_count()
        report["thread_count"] = facade.thread_count()
        if report["process_count"] != 1 or report["thread_count"] != 1:
            failures.append("process_thread_topology")

        target = SystemUsbTargetSelector().resolve_exact(TARGET_VID, TARGET_PID)
        report["target"] = {
            "vid": f"{target.identity.vid:04x}",
            "pid": f"{target.identity.pid:04x}",
            "bus": target.identity.bus,
            "address": target.identity.address,
            "port_path": list(target.identity.port_path),
            "device_path": str(target.device_path),
            "candidate_count": 1,
        }
        holders = facade.external_holders(target.device_path)
        report["external_holders"] = list(holders)
        if holders:
            failures.append("unexpected_external_holders")

        report["fprintd_initial_state"] = "active" if facade.fprintd_active() else "inactive"
        report["durable_report_path_ready"] = facade.report_path_ready(paths.final_report)
        if not report["durable_report_path_ready"]:
            failures.append("durable_report_path")

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
    report["status"] = "pass" if not failures else "fail"
    publish(report)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
