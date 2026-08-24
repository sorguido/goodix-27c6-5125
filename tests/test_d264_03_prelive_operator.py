# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from core.future_first_image_operator import (
    D261_MARKER_PATH, D265_FUTURE_LIVE_AUTHORIZATION_FLAG,
    FutureIntentCapability, FutureLiveIoCapability, FutureMarkerClaimCapability,
    FutureOperatorDependencies, FutureOperatorFailure,
    claim_future_marker_fixture, issue_future_intent_for_injected_rehearsal,
    issue_live_io_after_marker_claim, issue_marker_claim_after_durable_claim,
    require_future_live_io, run_future_first_image_candidate,
    verify_authoritative_baseline,
)
from core.persistent_runtime import TerminalBoundary


REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def git_authority(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.email", "offline@example.invalid"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "Offline Test"), cwd=repo, check=True)
    (repo / "critical.py").write_text("safe = True\n")
    (repo / "guard.py").write_text("guard = True\n")
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=repo, check=True)
    sha = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=repo, text=True).strip()
    return repo, sha, ("critical.py", "guard.py")


class Secret:
    def __init__(self, events): self.events, self.close_count = events, 0
    def close(self): self.close_count += 1; self.events.append("secret_close")


class Coordinator:
    def __init__(self, events, secret, failure=None): self.events, self.secret, self.failure = events, secret, failure
    def run(self, **kwargs):
        self.events.append("coordinator_run")
        assert kwargs["terminal_mode"] is TerminalBoundary.STOP_AFTER_FIRST_IMAGE
        try:
            if self.failure: raise self.failure
            return SimpleNamespace(command_trace=(0x36,0x50,0x36,0x82,0x20,0x36,0x32,0x22))
        finally:
            self.secret.close()  # models real coordinator ownership/finally
    def audit(self): return {"retry_count": 0, "command_22_attempt_count": 1}


def deps(events, *, fail_at=None, runtime_failure=None, construction_failure=False):
    def guard(name, value=None):
        def call(*args):
            events.append(name)
            if fail_at == name: raise FutureOperatorFailure(name)
            return value
        return call
    def marker(baseline, intent):
        events.append("marker_claim")
        if fail_at == "marker_claim": raise FutureOperatorFailure("marker")
        return issue_marker_claim_after_durable_claim(intent)
    def construct(capability, secret, target):
        events.append("backend_construct"); require_future_live_io(capability)
        if construction_failure or fail_at == "backend_construct": raise FutureOperatorFailure("backend")
        return Coordinator(events, secret, runtime_failure)
    return FutureOperatorDependencies(
        observe_baseline_verified=guard("baseline_verify"), require_operator_context=guard("operator_context"),
        require_safe_directories=guard("safe_directories"),
        verify_protected_metadata=guard("protected_metadata"),
        verify_gfusb_hash=guard("gfusb_hash"), resolve_exact_target=guard("target_identity", {"target":"synthetic"}),
        stop_fprintd=guard("fprintd_stop"), block_signals=guard("signals_block"),
        require_no_holders=guard("holder_check"), validate_non_secret_material=guard("non_secret_material"),
        materialize_secret_once=lambda: (events.append("secret_materialize") or Secret(events)),
        claim_marker_once=marker, observe_live_io_issue=guard("live_io_capability_issue"),
        construct_coordinator=construct, restore_signals=guard("signals_restore"),
        restore_fprintd=guard("fprintd_restore"), publish_report=guard("report_publish"),
    )


def run(git_authority, dependencies, events, **kwargs):
    repo, sha, paths = git_authority
    return run_future_first_image_candidate(
        issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG), dependencies,
        repo=repo, approved_baseline_sha=sha, authoritative_paths=paths, expected_paths=paths, ts16=0x4242, **kwargs,
    )


def test_explicit_guard_order_and_ownership_success(git_authority):
    events=[]; report=run(git_authority, deps(events), events)
    assert report["result"] == "PASS_STOP_AFTER_FIRST_IMAGE"
    assert events == ["baseline_verify","operator_context","safe_directories","protected_metadata","gfusb_hash","target_identity",
        "fprintd_stop","signals_block","holder_check","non_secret_material","secret_materialize","marker_claim",
        "live_io_capability_issue","backend_construct","coordinator_run","secret_close","signals_restore","fprintd_restore","report_publish"]
    assert events.count("secret_close") == 1
    assert report["secret_ownership_transferred_to_coordinator"] is True


@pytest.mark.parametrize("sha", ["", "abc", "HEAD", "main", "a"*39])
def test_baseline_format_fails_before_side_effects(git_authority, sha):
    repo, _, paths=git_authority; events=[]
    report=run_future_first_image_candidate(issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG), deps(events),
        repo=repo, approved_baseline_sha=sha, authoritative_paths=paths, expected_paths=paths, ts16=1)
    assert events == ["signals_restore","fprintd_restore","report_publish"]
    assert "full_sha_required" in report["failure_class"]


def test_baseline_unresolved_stale_duplicate_omitted_extra(git_authority):
    repo, sha, paths=git_authority
    with pytest.raises(FutureOperatorFailure, match="resolution"):
        verify_authoritative_baseline(repo, "f"*40, paths, paths)
    (repo/paths[0]).write_text("dirty = True\n")
    with pytest.raises(FutureOperatorFailure, match="stale"):
        verify_authoritative_baseline(repo, sha, paths, paths)
    (repo/paths[0]).write_text("safe = True\n")
    for authority in ((paths[0],paths[0]), (paths[0],), paths+("extra.py",)):
        with pytest.raises(FutureOperatorFailure, match="duplicate|path_set"):
            verify_authoritative_baseline(repo, sha, authority, paths)


@pytest.mark.parametrize("guard", ["operator_context","safe_directories","protected_metadata","gfusb_hash",
    "target_identity","fprintd_stop","signals_block","holder_check","non_secret_material"])
def test_each_guard_fails_closed_before_later_phases(git_authority, guard):
    events=[]; report=run(git_authority, deps(events, fail_at=guard), events)
    assert report["result"] == "FAIL_CLOSED"
    assert "secret_materialize" not in events and "marker_claim" not in events and "backend_construct" not in events
    assert events[-3:] == ["signals_restore","fprintd_restore","report_publish"]


def test_capability_chain_wrong_type_nonce_and_reuse():
    with pytest.raises(FutureOperatorFailure):
        issue_future_intent_for_injected_rehearsal("wrong")
    intent=issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG)
    with pytest.raises(FutureOperatorFailure): issue_marker_claim_after_durable_claim(intent)
    intent._used=True; marker=issue_marker_claim_after_durable_claim(intent)
    live=issue_live_io_after_marker_claim(marker); require_future_live_io(live)
    with pytest.raises(FutureOperatorFailure, match="already_used"): issue_live_io_after_marker_claim(marker)
    with pytest.raises(FutureOperatorFailure): issue_live_io_after_marker_claim(None)
    with pytest.raises(FutureOperatorFailure): require_future_live_io(FutureLiveIoCapability(object()))
    with pytest.raises(FutureOperatorFailure): require_future_live_io(FutureMarkerClaimCapability(object()))


def test_intent_reuse_fails_before_baseline(git_authority):
    repo,sha,paths=git_authority; events=[]
    intent=issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG)
    run_future_first_image_candidate(intent,deps(events),repo=repo,approved_baseline_sha=sha,
        authoritative_paths=paths,expected_paths=paths,ts16=1)
    with pytest.raises(FutureOperatorFailure,match="already_used"):
        run_future_first_image_candidate(intent,deps([]),repo=repo,approved_baseline_sha=sha,
            authoritative_paths=paths,expected_paths=paths,ts16=1)


def test_marker_existing_symlink_owner_mode_second_claim_and_d261(tmp_path, monkeypatch):
    def intent():
        value=issue_future_intent_for_injected_rehearsal(D265_FUTURE_LIVE_AUTHORIZATION_FLAG); value._used=True; return value
    marker=tmp_path/"future.marker"; claim=claim_future_marker_fixture(marker,"a"*40,intent())
    assert issue_live_io_after_marker_claim(claim)
    with pytest.raises(FutureOperatorFailure): claim_future_marker_fixture(marker,"a"*40,intent())
    link=tmp_path/"link"; link.symlink_to(tmp_path/"missing")
    with pytest.raises(FutureOperatorFailure): claim_future_marker_fixture(link,"a"*40,intent())
    with pytest.raises(FutureOperatorFailure, match="D261"): claim_future_marker_fixture(tmp_path/D261_MARKER_PATH.name,"a"*40,intent())
    original=os.fstat
    monkeypatch.setattr(os,"fstat",lambda fd: SimpleNamespace(st_uid=os.geteuid()+1,st_mode=0o100600))
    with pytest.raises(FutureOperatorFailure, match="owner_mode"): claim_future_marker_fixture(tmp_path/"owner","a"*40,intent())
    monkeypatch.setattr(os,"fstat",lambda fd: SimpleNamespace(st_uid=os.geteuid(),st_mode=0o100644))
    with pytest.raises(FutureOperatorFailure, match="owner_mode"): claim_future_marker_fixture(tmp_path/"mode","a"*40,intent())
    monkeypatch.setattr(os,"fstat",original)


@pytest.mark.parametrize("fail_at", ["target_identity","holder_check","backend_construct"])
def test_target_holder_backend_failures_are_distinct_and_zero_retry(git_authority, fail_at):
    events=[]; report=run(git_authority,deps(events,fail_at=fail_at),events)
    assert report["retry_count"] == 0 and events.count("backend_construct") <= 1


@pytest.mark.parametrize("cardinality", [0, 2])
def test_exact_target_absent_and_duplicate_fail_before_secret(git_authority, cardinality):
    events=[]; dependencies=deps(events)
    dependencies.resolve_exact_target=lambda: (events.append(f"target_cardinality_{cardinality}") or
        (_ for _ in ()).throw(FutureOperatorFailure(f"exact_target_sysfs_cardinality:{cardinality}")))
    report=run(git_authority,dependencies,events)
    assert f"cardinality:{cardinality}" in report["failure_class"]
    assert "secret_materialize" not in events and "backend_construct" not in events


@pytest.mark.parametrize("failure", [RuntimeError("usb open"),RuntimeError("submit"),RuntimeError("receive")])
def test_runtime_backend_failures_no_retry_one_secret_close(git_authority, failure):
    events=[]; report=run(git_authority,deps(events,runtime_failure=failure),events)
    assert report["retry_count"] == 0 and events.count("coordinator_run") == 1 and events.count("secret_close") == 1


def test_secret_owned_by_outer_before_transfer(git_authority):
    for failure in ("marker_claim","backend_construct"):
        events=[]; run(git_authority,deps(events,fail_at=failure),events)
        assert events.count("secret_close") == 1 and "coordinator_run" not in events


def test_real_persistent_coordinator_integration(git_authority):
    from tests.test_d263_phase2_public_run import (Tls12PskServerSession, _build_event_frames,
        _build_receive_frames, _fake_tls_factory, _make_coordinator, synthetic_seed)
    events=[]; holder={}
    dependencies=deps(events)
    def materialize():
        events.append("secret_materialize")
        coord,transport,event_source=_make_coordinator(operational_physical_policy=True,record_submissions=True)
        transport._receive=_build_receive_frames(first_image=True); event_source._frames=_build_event_frames(first_image=True)
        holder.update(coord=coord,transport=transport); return coord.secret_boundary
    def construct(capability,secret,target):
        events.append("backend_construct"); require_future_live_io(capability); return holder["coord"]
    dependencies.materialize_secret_once=materialize; dependencies.construct_coordinator=construct
    with mock.patch.object(Tls12PskServerSession,"from_boundary",_fake_tls_factory):
        report=run(git_authority,dependencies,events,seed_result_for_offline_rehearsal=synthetic_seed())
    coord=holder["coord"]; trace=list(coord.lifecycle.device_command_trace); audit=coord.audit()
    assert report["result"] == "PASS_STOP_AFTER_FIRST_IMAGE" and trace == [0x36,0x50,0x36,0x82,0x20,0x36,0x32,0x22]
    assert audit["usb_transport_session_count"] == audit["tls_server_handshake_count"] == audit["tls_server_session_object_count"] == 1
    assert audit["retry_count"] == audit["persistent_device_write_count"] == 0
    assert audit["transport_cleanup_count"] == audit["tls_close_count"] == 1 and audit["secret_boundary_zeroized"]
    assert report["first_image_raster_shape"] == [80,64]
    assert [p.mode.value for req,p in holder["transport"].submissions if req[4]==0x22] == ["FIXED64_ZERO_TAIL"]


def test_real_runtime_tls_consume_failure_is_specific():
    from tests.test_d263_phase2_first_image_terminal import (_armed_lifecycle, _build_coordinator,
        ScriptedEventSource, ScriptedTransport, ack, irq2, outer, TLS)
    coord=_build_coordinator(_armed_lifecycle(),ScriptedTransport([ack(0x22),outer(TLS,b"record")]),ScriptedEventSource(irq2()))
    coord.tls_session.application_session.consume_application_record=mock.Mock(side_effect=RuntimeError("consume"))
    with pytest.raises(Exception,match="first_image_b0_consumption_failed"):
        coord._run_first_image_terminal()


def test_real_public_runtime_rejects_buffered_unexpected_frame():
    from tests.test_d263_phase2_public_run import (Tls12PskServerSession,_build_event_frames,
        _build_receive_frames,_fake_tls_factory,_make_coordinator,synthetic_seed)
    coord,transport,event_source=_make_coordinator(operational_physical_policy=True,record_submissions=True)
    transport._receive=_build_receive_frames(first_image=True); event_source._frames=_build_event_frames(first_image=True)
    transport.assert_no_buffered_frames=mock.Mock(side_effect=RuntimeError("buffered_unexpected_frame"))
    with mock.patch.object(Tls12PskServerSession,"from_boundary",_fake_tls_factory):
        with pytest.raises(RuntimeError,match="buffered_unexpected_frame"):
            coord.run(seed_result=synthetic_seed(),ts16=0x4242,terminal_mode=TerminalBoundary.STOP_AFTER_FIRST_IMAGE)
    assert coord.audit()["retry_count"]==0 and transport.cleanup_count==1 and coord.secret_boundary.zeroized


def test_cli_hard_disabled_and_d261_arm_only(tmp_path):
    launcher=REPO/"operator_kit/d264-first-image-prelive.sh"
    good=subprocess.run((str(launcher),"--dry-run"),cwd=tmp_path,text=True,capture_output=True)
    assert good.returncode==0; report=json.loads(good.stdout)
    assert all(report[k]==0 for k in ("REAL_USB_OPEN_COUNT","REAL_SECRET_READ_COUNT","REAL_SINGLE_USE_MARKER_CREATE_COUNT","FPRINTD_MUTATION_COUNT","REAL_SENSOR_COMMAND_COUNT","D264_03_LIVE_TLS_HANDSHAKE_COUNT"))
    blocked=subprocess.run((str(launcher),D265_FUTURE_LIVE_AUTHORIZATION_FLAG),cwd=tmp_path,text=True,capture_output=True)
    assert blocked.returncode==2 and "HARD_DISABLED_D264_03" in blocked.stderr
    source=(REPO/"tools/d261_live_fdt_arm_once.py").read_text()
    assert "result = coordinator.run(ts16=ts16)" in source and "terminal_mode=TerminalBoundary.STOP_AFTER_FIRST_IMAGE" not in source


def test_import_has_no_real_side_effects():
    code="import core.future_first_image_operator; print('IMPORT_OFFLINE_OK')"
    completed=subprocess.run((os.sys.executable,"-c",code),cwd=REPO,text=True,capture_output=True)
    assert completed.returncode==0 and completed.stdout.strip()=="IMPORT_OFFLINE_OK"
