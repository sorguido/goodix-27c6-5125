# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from unittest import mock

import pytest

import tools.d265_live_first_image_once as tool
from core.future_first_image_operator import (
    D261_MARKER_PATH, D265_FUTURE_SINGLE_USE_MARKER_PATH,
    FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS,
    FutureOperatorFailure, claim_future_marker_fixture,
    issue_future_intent_for_injected_rehearsal, verify_authoritative_baseline,
)
from core.live_capability import D265_FUTURE_LIVE_AUTHORIZATION_FLAG as INTERNAL_INTENT_FLAG, consume_future_intent

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "operator_kit/d265-first-image-once.sh"
D265_FUTURE_LIVE_AUTHORIZATION_FLAG = tool.LIVE_FLAG
D265_FUTURE_APPROVED_BASELINE_ENV = tool.APPROVED_BASELINE_ENV
D265_PATHS = tool.D265_FIRST_IMAGE_LIVE_CRITICAL_PATHS


def run_launcher(*args: str, cwd: Path | None = None):
    return subprocess.run((str(LAUNCHER), *args), cwd=cwd or REPO, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_launcher_dry_run_passes_from_foreign_cwd(tmp_path):
    result = run_launcher("--dry-run", cwd=tmp_path)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["OUTCOME"] == "PASS_OFFLINE_OPERATOR_KIT"
    assert all(report[key] == 0 for key in (
        "REAL_USB_OPEN_COUNT", "REAL_SECRET_READ_COUNT", "REAL_SENSOR_COMMAND_COUNT",
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT", "FPRINTD_MUTATION_COUNT", "LIVE_TLS_HANDSHAKE_COUNT"))


@pytest.mark.parametrize("args", [(), ("wrong",), ("--dry-run", "extra"),
                                    (D265_FUTURE_LIVE_AUTHORIZATION_FLAG, "extra")])
def test_default_and_wrong_combinations_are_hard_disabled(args):
    result = run_launcher(*args)
    assert result.returncode == 2
    assert "HARD_DISABLED_DEFAULT" in result.stderr


def test_exact_live_flag_is_wired_but_test_cannot_build_production(monkeypatch):
    monkeypatch.setenv(D265_FUTURE_APPROVED_BASELINE_ENV, "a" * 40)
    build = mock.Mock(side_effect=RuntimeError("offline double stopped path"))
    monkeypatch.setattr(tool.FutureProductionDependencies, "build", build)
    monkeypatch.setattr(tool, "verify_d265_approved_baseline", mock.Mock())
    with pytest.raises(RuntimeError, match="offline double"):
        tool.main([D265_FUTURE_LIVE_AUTHORIZATION_FLAG])
    build.assert_called_once()


@pytest.mark.parametrize("sha", ["", "a" * 39, "A" * 40, "g" * 40, "HEAD", "main"])
def test_live_requires_full_lowercase_sha_before_production_adapter(monkeypatch, sha):
    monkeypatch.setenv(D265_FUTURE_APPROVED_BASELINE_ENV, sha)
    build = mock.Mock()
    monkeypatch.setattr(tool.FutureProductionDependencies, "build", build)
    assert tool.main([D265_FUTURE_LIVE_AUTHORIZATION_FLAG]) == 1
    build.assert_not_called()


def _git_fixture(tmp_path: Path):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.email", "offline@example.invalid"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "Offline"), cwd=repo, check=True)
    for relative in D265_PATHS:
        path = repo / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(relative)
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-qm", "approved"), cwd=repo, check=True)
    sha = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=repo, text=True).strip()
    return repo, sha


def test_head_mismatch_and_dirty_fail_closed(tmp_path):
    repo, approved = _git_fixture(tmp_path)
    (repo / "other").write_text("next")
    subprocess.run(("git", "add", "other"), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-qm", "next"), cwd=repo, check=True)
    with pytest.raises(RuntimeError, match="head_mismatch"):
        tool.verify_d265_approved_baseline(repo, approved)
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=repo, text=True).strip()
    (repo / D265_PATHS[0]).write_text("stale")
    with pytest.raises(RuntimeError, match="worktree_dirty"):
        tool.verify_d265_approved_baseline(repo, head)


def test_authority_manifest_exact_and_namespace_distinct():
    doc = json.loads(tool.MANIFEST.read_text())
    assert tuple(row["path"] for row in doc["future_live_critical_files"]) == D265_PATHS
    assert D265_FUTURE_SINGLE_USE_MARKER_PATH != D261_MARKER_PATH


def test_marker_write_all_and_zero_progress(tmp_path, monkeypatch):
    intent = issue_future_intent_for_injected_rehearsal(INTERNAL_INTENT_FLAG)
    consume_future_intent(intent)
    real_write = os.write
    monkeypatch.setattr(os, "write", lambda fd, data: real_write(fd, data[:max(1, len(data)//2)]))
    claim_future_marker_fixture(tmp_path / "short.marker", "a" * 40, intent)
    intent = issue_future_intent_for_injected_rehearsal(INTERNAL_INTENT_FLAG)
    consume_future_intent(intent)
    monkeypatch.setattr(os, "write", lambda fd, data: 0)
    with pytest.raises(FutureOperatorFailure, match="no_progress"):
        claim_future_marker_fixture(tmp_path / "zero.marker", "a" * 40, intent)


def test_summary_contains_no_biometric_content():
    summary = tool._summary("a" * 40, {"result": "PASS_STOP_AFTER_FIRST_IMAGE",
        "first_image_raster_shape": [80, 64], "runtime_audit": {"secret_zeroized": True}})
    assert summary["FIRST_IMAGE_RASTER_SHAPE"] == [80, 64]
    forbidden = {"secret", "psk", "raster_bytes", "image_hash", "pixel_samples", "biometric_payload"}
    assert forbidden.isdisjoint({key.lower() for key in summary})
    assert summary["RETRY_COUNT"] == summary["RECOVERY_COUNT"] == 0
