#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D265 one-shot operator entrypoint.  Dry-run is strictly metadata-only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.future_first_image_operator import (  # noqa: E402
    D265_FUTURE_REPORT_PATH,
    D265_FUTURE_SINGLE_USE_MARKER_PATH,
    FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS,
    FutureProductionDependencies,
    issue_future_intent_for_injected_rehearsal,
    run_future_first_image_candidate,
    sha256_file,
)
from core.live_capability import D265_FUTURE_LIVE_AUTHORIZATION_FLAG as INTERNAL_INTENT_FLAG  # noqa: E402

DRY_FLAG = "--dry-run"
LIVE_FLAG = "--i-authorize-one-d265-first-image-live-attempt"
APPROVED_BASELINE_ENV = "D265_APPROVED_LIVE_BASELINE_SHA"
D265_FIRST_IMAGE_LIVE_CRITICAL_PATHS = (
    "operator_kit/d265-first-image-once.sh", "tools/d265_live_first_image_once.py",
    *FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS,
)
MANIFEST = REPO / "analysis/D265/D265_01_live_critical_manifest.json"


def _zero_side_effects() -> dict[str, int]:
    return {
        "REAL_USB_OPEN_COUNT": 0, "REAL_SECRET_READ_COUNT": 0,
        "REAL_SENSOR_COMMAND_COUNT": 0, "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0, "LIVE_TLS_HANDSHAKE_COUNT": 0,
    }


def dry_run() -> dict[str, Any]:
    failures: list[str] = []
    try:
        doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
        rows = doc["future_live_critical_files"]
        paths = tuple(row["path"] for row in rows)
        if doc.get("schema") != "D265_01_LIVE_CRITICAL_MANIFEST_V1": failures.append("schema")
        if doc.get("baseline_approved") is not False: failures.append("baseline_model")
        if paths != D265_FIRST_IMAGE_LIVE_CRITICAL_PATHS: failures.append("path_authority")
        for row in rows:
            path = REPO / row["path"]
            if not path.is_file() or sha256_file(path) != row["sha256"]:
                failures.append(f"byte_identity:{row['path']}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append(f"manifest:{type(exc).__name__}")
        rows = []
    syntax = subprocess.run(
        ("bash", "-n", str(REPO / "operator_kit/d265-first-image-once.sh")),
        check=False,
    ).returncode == 0
    if not syntax: failures.append("launcher_syntax")
    return {
        "schema": "D265_01_OPERATOR_DRY_RUN_V1",
        "OUTCOME": "PASS_OFFLINE_OPERATOR_KIT" if not failures else "FAIL_CLOSED",
        "execution_mode": "OFFLINE_ONLY", "cwd_independent": True,
        "approved_baseline_environment": APPROVED_BASELINE_ENV,
        "approved_baseline_value_consumed": False,
        "full_40_lowercase_sha_required": True,
        "future_live_critical_file_count": len(rows),
        "future_live_critical_path_authority_exact": not any("authority" in x for x in failures),
        "launcher_syntax": "PASS" if syntax else "FAIL",
        "marker_path_metadata_model": str(D265_FUTURE_SINGLE_USE_MARKER_PATH),
        "report_path_metadata_model": str(D265_FUTURE_REPORT_PATH),
        "protected_content_reads": 0, "service_mutations": 0,
        "live_capability_reachable": False, "failures": failures,
        "READY_FOR_LIVE": False, "LIVE_AUTHORIZED": False, "BASELINE_APPROVED": False,
        **_zero_side_effects(),
    }


def _summary(sha: str, report: dict[str, Any]) -> dict[str, Any]:
    audit = report.get("runtime_audit", {})
    shape = report.get("first_image_raster_shape")
    passed = report.get("result") == "PASS_STOP_AFTER_FIRST_IMAGE"
    return {
        "OUTCOME": report.get("result", "FAIL_CLOSED"), "APPROVED_BASELINE_SHA": sha,
        "LIVE_ATTEMPT_INVOCATION_COUNT": 1, "D265_MARKER_CLAIMED": True,
        "USB_OPEN_COUNT": audit.get("usb_open_count", 0), "TRANSPORT_SESSION_COUNT": audit.get("transport_session_count", 0),
        "TLS_OBJECT_COUNT": audit.get("tls_object_count", 0), "TLS_HANDSHAKE_COUNT": audit.get("tls_handshake_count", 0),
        "SECRET_MATERIALIZATION_COUNT": 1, "FINAL_FDT_ARM_COUNT": audit.get("final_fdt_arm_count", 0),
        "IRQ2_FINGER_DOWN_COUNT": audit.get("irq2_finger_down_count", 0), "COMMAND_22_ATTEMPT_COUNT": audit.get("command_22_attempt_count", 0),
        "COMMAND_22_ACK_VALIDATION_COUNT": audit.get("command_22_ack_validation_count", 0), "FIRST_B0_COUNT": audit.get("first_b0_count", 0),
        "FIRST_IMAGE_DECODE_STATUS": "PASS" if shape else "NOT_COMPLETED", "FIRST_IMAGE_RASTER_SHAPE": shape,
        "RETRY_COUNT": 0, "RECOVERY_COUNT": 0, "REOPEN_COUNT": 0,
        "PERSISTENT_DEVICE_WRITE_COUNT": 0, "FORBIDDEN_POST_IMAGE_COMMAND_COUNT": 0,
        "TERMINAL_BOUNDARY": "STOP_AFTER_FIRST_IMAGE", "LIVE_RESULT": "PASS" if passed else "FAIL_CLOSED",
        "HOST_CLEANUP_STATUS": "COMPLETED" if passed else "SEE_FAILURE_REPORT",
        "FPRINTD_RESTORE_STATUS": "COMPLETED" if passed else "SEE_FAILURE_REPORT",
        "SECRET_ZEROIZED": bool(audit.get("secret_zeroized", passed)),
    }


def verify_d265_approved_baseline(repo: Path, sha: str) -> None:
    """Fail before protected/service/device effects on anything but exact approved bytes."""
    if not re.fullmatch(r"[0-9a-f]{40}", sha): raise RuntimeError("baseline_full_sha_required")
    def git(*args: str, text: bool = True):
        return subprocess.run(("git", *args), cwd=repo, check=False, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=text)
    resolved = git("rev-parse", f"{sha}^{{commit}}")
    if resolved.returncode or resolved.stdout.strip() != sha: raise RuntimeError("baseline_resolution_mismatch")
    head = git("rev-parse", "HEAD")
    if head.returncode or head.stdout.strip() != sha: raise RuntimeError("baseline_head_mismatch")
    dirty = git("status", "--porcelain", "--untracked-files=all")
    if dirty.returncode or dirty.stdout: raise RuntimeError("baseline_worktree_dirty")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paths = tuple(row["path"] for row in manifest["future_live_critical_files"])
    if paths != D265_FIRST_IMAGE_LIVE_CRITICAL_PATHS: raise RuntimeError("live_critical_path_set_mismatch")
    for relative in paths:
        blob = git("show", f"{sha}:{relative}", text=False)
        if blob.returncode or blob.stdout != (repo / relative).read_bytes():
            raise RuntimeError(f"live_critical_byte_mismatch:{relative}")


def live_once() -> int:
    sha = os.environ.get(APPROVED_BASELINE_ENV, "")
    # Format is rejected before intent construction or any production adapter.
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        print(json.dumps({"OUTCOME": "FAIL_BASELINE_FULL_SHA_REQUIRED", **_zero_side_effects()}, sort_keys=True))
        return 1
    try:
        verify_d265_approved_baseline(REPO, sha)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"OUTCOME": f"FAIL_{exc}", **_zero_side_effects()}, sort_keys=True))
        return 1
    intent = issue_future_intent_for_injected_rehearsal(INTERNAL_INTENT_FLAG)
    dependencies = FutureProductionDependencies.build(REPO, intent)
    print("D265 one-shot first-image live is starting.")
    print("Keep your finger off the sensor until prompted.")
    print("When prompted, place ONE finger ONCE and keep it still until completion.")
    print("Do not retry if this run fails or times out.")
    print("D265_OPERATOR_ACTION = PLACE_ONE_FINGER_NOW")
    try:
        report = run_future_first_image_candidate(
            intent, dependencies, repo=REPO, approved_baseline_sha=sha,
            authoritative_paths=FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS,
            ts16=int(time.time()) & 0xffff,
        )
    finally:
        print("D265_OPERATOR_ACTION_WINDOW = CLOSED")
    summary = _summary(sha, report)
    print(json.dumps(summary, sort_keys=True))
    for key, value in summary.items(): print(f"{key} = {value}")
    return 0 if summary["LIVE_RESULT"] == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == [DRY_FLAG]:
        report = dry_run(); print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["OUTCOME"] == "PASS_OFFLINE_OPERATOR_KIT" else 1
    if args == [LIVE_FLAG]: return live_once()
    print("HARD_DISABLED_DEFAULT")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
