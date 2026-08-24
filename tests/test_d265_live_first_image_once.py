# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
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
    assert "modalità D265 esatta richiesta" in result.stderr


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
    audit = {"usb_transport_session_count": 1, "transport_cleanup_count": 1,
        "tls_server_session_object_count": 1, "tls_server_handshake_count": 1,
        "retry_count": 0, "persistent_device_write_count": 0,
        "secret_boundary_zeroized": True, "a2_special_recovery_count": 0,
        "0x70_special_recovery_count": 0, "exact_fdt_command_trace":
        ["0x36","0x50","0x36","0x82","0x20","0x36","0x32","0x22"],
        "first_image_irq2_observed_count": 1, "image_command_attempt_count": 1,
        "first_image_ack_validation_count": 1, "first_image_b0_count": 1,
        "first_image_received": True, "cleanup_failures": []}
    coordinator = SimpleNamespace(audit=lambda: audit,
        transport=SimpleNamespace(backend=SimpleNamespace(open_count=1)))
    tracker = tool.PhaseTracker(1, 1, 1, 1, 1, coordinator)
    summary = tool._summary("a" * 40, {"result": "PASS_STOP_AFTER_FIRST_IMAGE",
        "first_image_raster_shape": [80, 64]}, tracker)
    assert summary["FIRST_IMAGE_RASTER_SHAPE"] == [80, 64]
    forbidden = {"secret", "psk", "raster_bytes", "image_hash", "pixel_samples", "biometric_payload"}
    assert forbidden.isdisjoint({key.lower() for key in summary})
    assert summary["RETRY_COUNT"] == summary["RECOVERY_COUNT"] == 0
    assert summary["USB_OPEN_COUNT"] == summary["TRANSPORT_SESSION_COUNT"] == 1
    assert summary["TLS_OBJECT_COUNT"] == summary["TLS_HANDSHAKE_COUNT"] == 1
    assert summary["COMMAND_22_ATTEMPT_COUNT"] == summary["COMMAND_22_ACK_VALIDATION_COUNT"] == 1
    assert summary["FIRST_B0_COUNT"] == 1 and summary["SECRET_ZEROIZED"] is True
    assert summary["LIVE_RESULT"] == "PASS_STOP_AFTER_FIRST_IMAGE"


def test_italian_operator_text_and_sudo_env_contract():
    source = Path(tool.__file__).read_text()
    assert "APPOGGIA_UN_DITO_ORA" in source
    for english in ("first-image live is starting", "Keep your finger off",
                    "When prompted, place ONE finger", "Do not retry"):
        assert english not in source
    assert tool.CANONICAL_LIVE_COMMAND_TEMPLATE.startswith(
        "sudo env D265_APPROVED_LIVE_BASELINE_SHA=<FULL_APPROVED_SHA>")
    assert "sudo -S" not in source and "getpass" not in source and "stdin.write" not in source


def test_prompt_occurs_only_at_irq2_wait_and_once(capsys):
    events = []
    class Delegate:
        def wait_event(self, timeout): events.append(("wait", timeout)); return b"frame"
    tracker = tool.PhaseTracker(); wrapped = tool.PromptingEventSource(Delegate(), tracker)
    wrapped.wait_event(500); assert "APPOGGIA" not in capsys.readouterr().out
    events.append(("final_arm_completed", None))
    wrapped.wait_event(15000); output = capsys.readouterr().out
    wrapped.wait_event(15000); second = capsys.readouterr().out
    assert output.count("D265_OPERATOR_ACTION = APPOGGIA_UN_DITO_ORA") == 1
    assert "APPOGGIA" not in second and tracker.operator_prompt_count == 1
    assert events == [("wait",500),("final_arm_completed",None),("wait",15000),("wait",15000)]


def test_truthful_summary_before_secret_and_after_marker_before_usb():
    before = tool._summary("a"*40, {"result":"FAIL_CLOSED"}, tool.PhaseTracker())
    assert before["SECRET_MATERIALIZATION_COUNT"] == 0
    assert before["D265_MARKER_CLAIMED"] is False and before["USB_OPEN_COUNT"] == "NOT_REACHED"
    after = tool._summary("a"*40, {"result":"FAIL_CLOSED"}, tool.PhaseTracker(1,1))
    assert after["SECRET_MATERIALIZATION_COUNT"] == 1
    assert after["D265_MARKER_CLAIMED"] is True and after["USB_OPEN_COUNT"] == "NOT_REACHED"


@pytest.mark.parametrize("irq,ack,b0", [(0,0,0),(1,0,0),(1,1,0),(1,1,1)])
def test_partial_first_image_progress_is_preserved(irq, ack, b0):
    audit={"usb_transport_session_count":1,"first_image_irq2_observed_count":irq,
        "image_command_attempt_count":irq,"first_image_ack_validation_count":ack,
        "first_image_b0_count":b0,"exact_fdt_command_trace":[],"retry_count":0,
        "persistent_device_write_count":0,"a2_special_recovery_count":0,"0x70_special_recovery_count":0}
    coordinator=SimpleNamespace(audit=lambda:audit,transport=SimpleNamespace(backend=SimpleNamespace(open_count=1)))
    summary=tool._summary("a"*40,{"result":"FAIL_CLOSED"},tool.PhaseTracker(coordinator=coordinator))
    assert (summary["IRQ2_FINGER_DOWN_COUNT"],summary["COMMAND_22_ACK_VALIDATION_COUNT"],summary["FIRST_B0_COUNT"]) == (irq,ack,b0)
