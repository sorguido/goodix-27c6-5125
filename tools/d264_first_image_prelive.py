#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D264/03 offline-only inspection of the future protected operator path."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))
sys.path.insert(0, str(REPO)) if str(REPO) not in sys.path else None

from core.future_first_image_operator import (  # noqa: E402
    D265_FUTURE_APPROVED_BASELINE_ENV,
    D265_FUTURE_SINGLE_USE_MARKER_PATH,
    LIVE_CAPABILITY_DEFAULT,
    sha256_file,
)
MANIFEST = REPO / "analysis/D264/D264_03_live_critical_manifest.json"


def marker_metadata_only(path: Path) -> dict[str, object]:
    """Inspect the future marker without importing or reading secret code."""
    try:
        value = path.lstat()
    except OSError as exc:
        return {"path": os.fspath(path), "exists": False, "content_read": False, "errno": exc.errno}
    return {
        "path": os.fspath(path), "exists": True, "content_read": False,
        "regular": stat.S_ISREG(value.st_mode), "symlink": stat.S_ISLNK(value.st_mode),
        "uid": value.st_uid, "mode": oct(stat.S_IMODE(value.st_mode)),
    }


def dry_run() -> dict[str, object]:
    failures: list[str] = []
    try:
        manifest = json.loads(MANIFEST.read_text())
        if manifest.get("schema") != "D264_03_LIVE_CRITICAL_MANIFEST_V4_CORRECTIVE2":
            failures.append("manifest_schema")
        rows = manifest.get("future_live_critical_files", []) + manifest.get("d264_03_offline_gate_files", [])
        paths = [row.get("path") for row in rows]
        if len(paths) != len(set(paths)) or not paths:
            failures.append("manifest_path_set")
        for row in rows:
            path = REPO / row["path"]
            if not path.is_file() or sha256_file(path) != row["sha256"]:
                failures.append(f"worktree_hash:{row['path']}")
    except (OSError, ValueError, KeyError) as exc:
        failures.append(f"manifest_unavailable:{type(exc).__name__}")
        rows = []
    launcher = REPO / "operator_kit/d264-first-image-prelive.sh"
    syntax = subprocess.run(("bash", "-n", str(launcher)), check=False).returncode == 0
    if not syntax:
        failures.append("launcher_syntax")
    candidate_sha = ""  # Never consume an environment approval during D264/03.
    baseline_model = {
        "environment_name": D265_FUTURE_APPROVED_BASELINE_ENV,
        "value_consumed_during_D264_03": False,
        "full_40_char_sha_required": True,
        "candidate_is_full_sha": bool(re.fullmatch(r"[0-9a-f]{40}", candidate_sha)),
        "approved": False,
    }
    return {
        "schema": "D264_03_FIRST_IMAGE_PRELIVE_DRY_RUN_V1",
        "status": "PASS_OFFLINE" if not failures else "FAIL_CLOSED",
        "execution_mode": "OFFLINE_ONLY",
        "repository_root": str(REPO),
        "cwd_independent": True,
        "FIRST_IMAGE_PRELIVE_OPERATOR_WIRING": "IMPLEMENTED_OFFLINE",
        "LIVE_CAPABILITY_DEFAULT": LIVE_CAPABILITY_DEFAULT,
        "LIVE_PATH_REACHABLE_DURING_D264_03": False,
        "future_marker_path": str(D265_FUTURE_SINGLE_USE_MARKER_PATH),
        "future_marker_metadata_only": marker_metadata_only(D265_FUTURE_SINGLE_USE_MARKER_PATH),
        "baseline_model": baseline_model,
        "manifest_file_count": len(rows),
        "launcher_syntax": "PASS" if syntax else "FAIL",
        "failures": failures,
        "REAL_USB_OPEN_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0,
        "REAL_SENSOR_COMMAND_COUNT": 0,
        "D264_03_LIVE_TLS_HANDSHAKE_COUNT": 0,
        "READY_FOR_LIVE": False,
        "BASELINE_APPROVED": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run:
        print(json.dumps({
            "status": "HARD_DISABLED_D264_03",
            "LIVE_PATH_REACHABLE_DURING_D264_03": False,
            "REAL_USB_OPEN_COUNT": 0,
            "REAL_SECRET_READ_COUNT": 0,
            "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
            "FPRINTD_MUTATION_COUNT": 0,
            "REAL_SENSOR_COMMAND_COUNT": 0,
        }, sort_keys=True))
        return 2
    report = dry_run()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS_OFFLINE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
