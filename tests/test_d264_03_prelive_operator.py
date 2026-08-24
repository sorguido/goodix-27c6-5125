# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from core.future_first_image_operator import (
    D261_MARKER_PATH,
    D265_FUTURE_LIVE_AUTHORIZATION_FLAG,
    FutureOperatorDependencies,
    FutureOperatorFailure,
    claim_future_marker_fixture,
    issue_future_intent_for_injected_rehearsal,
    run_future_first_image_candidate,
    validate_full_sha,
)
from core.persistent_runtime import TerminalBoundary


REPO = Path(__file__).resolve().parents[1]
SHA = "a" * 40


class Secret:
    def __init__(self, events, failure=False):
        self.events, self.failure = events, failure

    def close(self):
        self.events.append("secret_close")
        if self.failure:
            raise RuntimeError("secret close")


class Coordinator:
    def __init__(self, events, run_failure=None):
        self.events, self.run_failure = events, run_failure

    def run(self, *, ts16, terminal_mode):
        self.events.append(("run", ts16, terminal_mode))
        assert terminal_mode is TerminalBoundary.STOP_AFTER_FIRST_IMAGE
        if self.run_failure:
            raise self.run_failure
        return SimpleNamespace(command_trace=(0x36, 0x50, 0x36, 0x82, 0x20, 0x36, 0x32, 0x22))

    def audit(self):
        return {
            "usb_open_count": 1, "transport_session_count": 1,
            "tls_server_session_object_count": 1, "tls_handshake_count": 1,
            "secret_handoff_count": 1, "command_22_attempt_count": 1,
            "command_22_ack_validation_count": 1, "first_image_b0_receive_count": 1,
            "retry_count": 0, "reopen_count": 0,
        }

def dependencies(events, *, run_failure=None, cleanup_failures=()):
    def action(name):
        def invoke():
            events.append(name)
            if name in cleanup_failures:
                raise RuntimeError(name)
        return invoke

    return FutureOperatorDependencies(
        preflight=action("preflight"), stop_fprintd=action("fprintd_stop"),
        restore_fprintd=action("fprintd_restore"), block_signals=action("signals_block"),
        restore_signals=action("signals_restore"),
        materialize_secret_once=lambda: (events.append("secret_materialize") or Secret(events, "secret_close" in cleanup_failures)),
        claim_marker_once=action("marker_claim"),
        construct_coordinator=lambda capability, secret: (events.append("backend_construct") or Coordinator(events, run_failure)),
        publish_report=lambda report: (events.append("report_publish") or (_ for _ in ()).throw(RuntimeError("report"))) if "report_publish" in cleanup_failures else events.append("report_publish"),
    )


def test_production_shaped_success_and_exact_boundary():
    events = []
    intent = issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG)
    report = run_future_first_image_candidate(intent, dependencies(events), ts16=0x4242)
    assert report["result"] == "PASS_STOP_AFTER_FIRST_IMAGE"
    assert events[:7] == ["preflight", "fprintd_stop", "signals_block", "secret_materialize", "marker_claim", "backend_construct", ("run", 0x4242, TerminalBoundary.STOP_AFTER_FIRST_IMAGE)]
    assert events[-4:] == ["secret_close", "signals_restore", "fprintd_restore", "report_publish"]
    assert report["runtime_audit"]["command_22_attempt_count"] == 1
    assert report["command_trace"][-1] == "0x22"
    assert not {"0x34", "0xa2", "0x70"} & set(report["command_trace"])


@pytest.mark.parametrize("value", ["", "abc", "HEAD", "main", "a" * 39, "A" * 40])
def test_baseline_requires_lowercase_full_sha(value):
    with pytest.raises(FutureOperatorFailure, match="full_sha_required"):
        validate_full_sha(value)


def test_authorization_exact_one_shot_and_direct_call_blocked():
    with pytest.raises(FutureOperatorFailure):
        issue_future_intent_for_injected_rehearsal("wrong")
    with pytest.raises(FutureOperatorFailure):
        run_future_first_image_candidate(None, dependencies([]), ts16=0)
    intent = issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG)
    run_future_first_image_candidate(intent, dependencies([]), ts16=0)
    with pytest.raises(FutureOperatorFailure, match="already_used"):
        run_future_first_image_candidate(intent, dependencies([]), ts16=0)


def test_dedicated_marker_schema_second_claim_symlink_and_d261_rejected(tmp_path):
    marker = tmp_path / "future.marker"
    claim_future_marker_fixture(marker, SHA)
    assert json.loads(marker.read_text())["schema"] == "D265_FUTURE_FIRST_IMAGE_SINGLE_USE_MARKER_V1"
    with pytest.raises(FutureOperatorFailure):
        claim_future_marker_fixture(marker, SHA)
    link = tmp_path / "link.marker"
    link.symlink_to(tmp_path / "missing")
    with pytest.raises(FutureOperatorFailure):
        claim_future_marker_fixture(link, SHA)
    with pytest.raises(FutureOperatorFailure, match="D261_marker"):
        claim_future_marker_fixture(tmp_path / D261_MARKER_PATH.name, SHA)


@pytest.mark.parametrize("failure", [
    TimeoutError("irq2 timeout"), RuntimeError("unexpected irq"), RuntimeError("invalid 0x22 ack"),
    RuntimeError("malformed B0"), RuntimeError("TLS consume"), RuntimeError("CRC"),
    RuntimeError("decode"), RuntimeError("buffered frame"), RuntimeError("second 0x22 blocked"),
    RuntimeError("usb open"), RuntimeError("submit"), RuntimeError("receive"),
])
def test_runtime_failures_have_no_retry_and_restore(failure):
    events = []
    report = run_future_first_image_candidate(
        issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG),
        dependencies(events, run_failure=failure), ts16=1,
    )
    assert report["result"] == "FAIL_CLOSED"
    assert report["retry_count"] == 0
    assert events.count("backend_construct") == 1
    assert events[-3:] == ["signals_restore", "fprintd_restore", "report_publish"]


def test_all_cleanup_and_restore_attempted_despite_independent_failures():
    events = []
    report = run_future_first_image_candidate(
        issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG),
        dependencies(events, cleanup_failures={"secret_close", "signals_restore", "fprintd_restore", "report_publish"}),
        ts16=1,
    )
    assert events[-4:] == ["secret_close", "signals_restore", "fprintd_restore", "report_publish"]
    assert report["result"] == "FAIL_CLOSED_REPORT_UNPUBLISHED"


def test_cli_is_offline_only_from_foreign_cwd(tmp_path):
    launcher = REPO / "operator_kit/d264-first-image-prelive.sh"
    completed = subprocess.run((str(launcher), "--dry-run"), cwd=tmp_path, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["LIVE_PATH_REACHABLE_DURING_D264_03"] is False
    assert all(report[key] == 0 for key in (
        "REAL_USB_OPEN_COUNT", "REAL_SECRET_READ_COUNT", "REAL_SINGLE_USE_MARKER_CREATE_COUNT",
        "FPRINTD_MUTATION_COUNT", "REAL_SENSOR_COMMAND_COUNT", "D264_03_LIVE_TLS_HANDSHAKE_COUNT",
    ))
    blocked = subprocess.run((str(launcher), D265_FUTURE_LIVE_AUTHORIZATION_FLAG), cwd=tmp_path, text=True, capture_output=True)
    assert blocked.returncode == 2
    assert "HARD_DISABLED_D264_03" in blocked.stderr


def test_d261_source_keeps_default_arm_only():
    source = (REPO / "tools/d261_live_fdt_arm_once.py").read_text()
    assert "result = coordinator.run(ts16=ts16)" in source
    assert "terminal_mode=TerminalBoundary.STOP_AFTER_FIRST_IMAGE" not in source
