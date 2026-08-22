#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Finalize an already acquired D255 run without hardware or raw-file writes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from d255_postprocess_windows_evidence import EvidenceError, iter_usbpcap, load_markers


RUN_NAME = "D255_20260822T205631772Z_85c8c41f"
WIRE_RELATIVE = "raw/wire.pcapng"
REQUIRED_MARKERS = (
    "CAPTURE_PROCESS_STARTED",
    "CAPTURE_STARTED",
    "VM_USB_ATTACH_BEGIN",
    "VM_USB_ATTACH_END",
    "GUEST_27C6_5125_PRESENT",
    "CAPTURE_OUTPUT_MATERIALIZED",
    "PASSIVE_BOOTSTRAP_SETTLED",
    "HELLO_SETUP_UI_CHECK_BEGIN",
    "HELLO_SETUP_UI_READY",
    "OEM_SESSION_BEGIN",
    "OEM_WAITING_NO_FINGER",
    "CANCEL_NO_FINGER_BEGIN",
    "CANCEL_NO_FINGER_END",
    "REENTRY_BEGIN",
    "REENTRY_WAITING_NO_FINGER",
    "REENTRY_CANCEL_BEGIN",
    "REENTRY_CANCEL_END",
    "REENTRY_END",
    "OPERATOR_PHASES_COMPLETE",
)
EXPECTED_ORIGINAL_ARTIFACTS = {
    "run_clock_end.json": "NOT_RECOVERABLE",
    "guest_topology_after_capture.json": "NOT_RECOVERABLE",
    "cache_after_metadata.json": "NOT_RECOVERABLE",
    "oem_logs_after_metadata.json": "NOT_RECOVERABLE",
    "input_manifest.json": "NOT_RECOVERABLE",
    "input_manifest.json.sha256": "NOT_RECOVERABLE",
}
ROLE_BY_PATH = {
    WIRE_RELATIVE: "wire",
    "operator_markers.tsv": "markers",
    "run_clock.json": "clock_anchor",
    "run_clock_end.json": "clock_end",
    "guest_topology_before_attach.json": "guest_topology_before",
    "guest_topology_after_attach.json": "guest_topology_after_attach",
    "guest_topology_after_capture.json": "guest_topology_after_capture",
}
RECOVERY_FILENAMES = {
    "recovery_manifest.json",
    "recovery_manifest.json.sha256",
    "recovery_report.json",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def role_for(relative: str) -> str:
    if relative in ROLE_BY_PATH:
        return ROLE_BY_PATH[relative]
    if relative.startswith("raw/cache_before/"):
        return "cache_before"
    if relative.startswith("raw/cache_after/"):
        return "cache_after"
    if relative.startswith("raw/oem_logs_before/"):
        return "oem_log_before"
    if relative.startswith("raw/oem_logs_after/"):
        return "oem_log_after"
    return "metadata"


def original_files(run_dir: Path) -> list[Path]:
    return sorted(
        path for path in run_dir.rglob("*")
        if path.is_file() and path.name not in RECOVERY_FILENAMES
    )


def recover(run_dir: Path) -> dict:
    run_dir = run_dir.resolve()
    require(run_dir.is_dir(), "run directory is missing")
    require(run_dir.name == RUN_NAME, f"unexpected run directory; expected {RUN_NAME}")
    manifest_path = run_dir / "recovery_manifest.json"
    manifest_sidecar = run_dir / "recovery_manifest.json.sha256"
    report_path = run_dir / "recovery_report.json"
    require(not any(path.exists() for path in (manifest_path, manifest_sidecar, report_path)),
            "recovery output collision")

    wire = run_dir / WIRE_RELATIVE
    markers_path = run_dir / "operator_markers.tsv"
    require(wire.is_file(), "raw wire capture is missing")
    require(markers_path.is_file(), "operator marker file is missing")
    wire_stat_before = wire.stat()
    wire_hash_before = sha256_file(wire)
    require(wire_stat_before.st_size > 0, "raw wire capture is empty")

    packets = list(iter_usbpcap(wire))
    require(packets, "raw wire capture contains no readable USBPcap frames")
    markers = load_markers(markers_path)
    positions: list[int] = []
    events = [row["event"] for row in markers]
    for name in REQUIRED_MARKERS:
        matches = [index for index, event in enumerate(events) if event == name]
        require(len(matches) == 1, f"required marker {name} missing or duplicated")
        positions.append(matches[0])
    require(positions == sorted(positions), "required D255 markers are out of order")
    forbidden_finger_events = {
        "FINGER_TOUCHED", "FINGER_DOWN", "FINGER_INTERACTION",
        "ENROLLMENT_CAPTURED", "RECOGNITION_CAPTURED",
    }
    require(not forbidden_finger_events.intersection(events),
            "unexpected finger-interaction marker in zero-finger run")

    artifacts = {}
    for relative, missing_status in EXPECTED_ORIGINAL_ARTIFACTS.items():
        artifacts[relative] = "ORIGINAL_ARTIFACT" if (run_dir / relative).is_file() else missing_status

    files = []
    for path in original_files(run_dir):
        relative = path.relative_to(run_dir).as_posix()
        files.append({
            "path": relative,
            "role": role_for(relative),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
            "artifact_origin": "ORIGINAL_ARTIFACT",
        })

    wire_stat_after = wire.stat()
    wire_hash_after = sha256_file(wire)
    raw_unchanged = (
        wire_hash_before == wire_hash_after
        and wire_stat_before.st_size == wire_stat_after.st_size
        and wire_stat_before.st_mtime_ns == wire_stat_after.st_mtime_ns
    )
    require(raw_unchanged, "raw pcap changed during offline recovery")

    manifest = {
        "schema": "D255_WINDOWS_EVIDENCE_INPUT_MANIFEST_V3",
        "created_by": "D255_OFFLINE_RECOVERY_V1",
        "target": "27c6:5125",
        "expected_firmware": "GF_ST411SEC_APP_12509",
        "recovery": {
            "offline_recovery": True,
            "original_run_finalization": "FAILED_HOST_SIDE_EXITCODE_UNAVAILABLE",
            "original_artifact_default": "ORIGINAL_ARTIFACT",
            "recovered_artifact": "recovery_manifest.json",
            "artifact_status": artifacts,
            "post_capture_state_snapshot": "NOT_RECOVERABLE_RETROACTIVELY",
        },
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_hash = sha256_file(manifest_path)
    manifest_sidecar.write_text(f"{manifest_hash}  recovery_manifest.json\n", encoding="ascii")

    report = {
        "schema": "D255_OFFLINE_RECOVERY_REPORT_V1",
        "result": "PASS_RECOVERED_READY_FOR_OFFLINE_POSTPROCESSING",
        "run": run_dir.name,
        "capture_acquisition": "SUCCEEDED",
        "operator_phases": "COMPLETED_ZERO_FINGER",
        "process_state": "EXITED",
        "tshark_exit_code": "UNAVAILABLE",
        "pcap": {
            "path": WIRE_RELATIVE,
            "bytes": wire_stat_before.st_size,
            "sha256_before": wire_hash_before,
            "sha256_after": wire_hash_after,
            "readable": True,
            "first_frame": 1,
            "frame_count": len(packets),
            "modified": False,
        },
        "markers": {
            "required": list(REQUIRED_MARKERS),
            "present_once_and_ordered": True,
            "zero_finger_phases_complete": True,
        },
        "artifact_status": {
            **artifacts,
            "recovery_manifest.json": "RECOVERED_ARTIFACT",
            "recovery_report.json": "RECOVERED_ARTIFACT",
        },
        "post_capture_state_snapshot": "NOT_RECOVERABLE_RETROACTIVELY",
        "postprocess": {
            "manifest": "recovery_manifest.json",
            "manifest_sha256": manifest_hash,
            "status": "READY",
        },
        "safety": {
            "offline": True,
            "usb_access": False,
            "windows_hello_access": False,
            "sensor_required": False,
            "real_usb_open_count": 0,
            "real_capture_count": 0,
            "real_hardware_action_count": 0,
            "raw_pcap_modified": False,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    result = recover(args.run_dir)
    print(json.dumps({
        "result": result["result"],
        "pcap_bytes": result["pcap"]["bytes"],
        "frame_count": result["pcap"]["frame_count"],
        "manifest_sha256": result["postprocess"]["manifest_sha256"],
        "raw_pcap_modified": result["pcap"]["modified"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        raise SystemExit(f"D255_RECOVERY_FAIL_CLOSED: {exc}")
