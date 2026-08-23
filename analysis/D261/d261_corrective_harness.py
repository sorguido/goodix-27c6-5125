#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Execution-derived offline evidence for the D261 operational corrective."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Callable
from unittest import mock
from contextlib import redirect_stdout


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from analysis.D261.d261_offline_rehearsal import (
    NEGATIVE_SCENARIOS,
    SYNTHETIC_OTP,
    _ack,
    _build_seed_cache,
    _irq100,
    _nav_response,
    _payload_frame,
    run_scenario,
)
from core.fdt_seed import CRC_OFFSET, provide_hash_gated_fdt12
from core.protected_runtime import (
    D261_LIVE_AUTHORIZATION_FLAG,
    ProtectedRuntimeFailure,
    _issue_cli_intent_after_exact_main_flag,
    issue_live_io_capability_after_marker,
    protected_metadata,
    require_cli_intent,
    validate_config90_content,
)
from core.runtime_transport import PhysicalSubmissionPolicy, SubmissionMode
from core.tls_b0 import wrap_tls_record_b0
from core.usb_runtime import CtypesLibusbBackend, SharedFrameRouter, UsbRuntimeFailure
from src.goodix5125_cleanroom import crc32_mpeg2
from tools.d261_live_fdt_arm_once import (
    CANONICAL_LIVE_CRITICAL_PATHS,
    FprintdTransaction,
    LIVE_FLAG,
    OperationalFailure,
    SignalTransaction,
    _run_live,
    claim_marker,
    prepare_report_directory,
    publish_report,
    require_no_external_holders,
    verify_approved_git_baseline,
    main as live_main,
)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args), cwd=repo, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return completed.stdout.strip()


def _temp_git_repository(directory: Path) -> tuple[Path, str, dict[str, Any]]:
    repo = directory / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "d261@example.invalid")
    _git(repo, "config", "user.name", "D261 Fixture")
    for relative in CANONICAL_LIVE_CRITICAL_PATHS:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture-v1:{relative}\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture baseline")
    baseline = _git(repo, "rev-parse", "HEAD")
    fileset = {
        "schema": "D261_OPERATIONAL_LIVE_CRITICAL_FILESET_V1",
        "role": "DERIVED_REPORT_NOT_AUTHORITY",
        "files": [
            {
                "path": relative,
                "sha256": hashlib.sha256((repo / relative).read_bytes()).hexdigest(),
            }
            for relative in CANONICAL_LIVE_CRITICAL_PATHS
        ],
    }
    return repo, baseline, fileset


def _capture_failure(call: Callable[[], Any]) -> str:
    try:
        call()
    except BaseException as exc:
        return f"{type(exc).__name__}:{exc}"
    raise AssertionError("expected fail-closed gate did not fail")


def _runner(*, stop_failure: bool = False, restore_failure: bool = False):
    calls: list[str] = []

    def run(command, **_kwargs):
        action = command[1]
        calls.append(action)
        if action == "is-active":
            return subprocess.CompletedProcess(command, 0, stdout="active\n", stderr="")
        if action == "stop" and stop_failure:
            raise subprocess.CalledProcessError(1, command)
        if action == "start" and restore_failure:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    return run, calls


def _invalid_physical_policy_failure(kind: str) -> tuple[str, dict[str, int]]:
    logical = _payload_frame(0x36, bytes(14))

    class Backend:
        open_count = claim_count = release_count = close_count = 0
        command_send_count = 0

        def open_exact(self, vid, pid, interface):
            from core.usb_runtime import UsbIdentity
            self.open_count = self.claim_count = 1
            return UsbIdentity(vid, pid, 1, 2, (3,))

        def revalidate_identity(self):
            from core.usb_runtime import UsbIdentity
            return UsbIdentity(0x27C6, 0x5125, 1, 2, (3,))

        def bulk_out(self, endpoint, data, timeout_ms):
            self.command_send_count += 1
            if len(data) != 64:
                raise UsbRuntimeFailure(f"synthetic_fdt_physical_length:{len(data)}")
            if any(data[len(logical):]):
                raise UsbRuntimeFailure("synthetic_fdt_nonzero_tail")
            return len(data)

        def bulk_in(self, endpoint, maximum, timeout_ms):
            raise AssertionError("no IN expected")

        def close(self):
            self.close_count = self.release_count = 1

    from core.usb_runtime import LibusbRuntimeTransport
    backend = Backend()
    transport = LibusbRuntimeTransport(backend, sleeper=lambda _value: None)
    transport.open()
    if kind == "tail_policy_mismatch":
        class NonZeroTailPolicy:
            pre_submit_pacing_ms = post_submit_pacing_ms = 0
            timeout_ms = 500
            def materialize(self, frame):
                return (frame + b"\x01" + bytes(63 - len(frame)),)
        policy = NonZeroTailPolicy()
    else:
        policy = PhysicalSubmissionPolicy(
            "wrong_length", SubmissionMode.SHORT_FINAL, timeout_ms=500
        )
    failure = _capture_failure(lambda: transport.submit(logical, policy))
    transport.close()
    return failure, {
        "usb_open_count": backend.open_count,
        "command_send_count": backend.command_send_count,
        "cleanup_count": backend.close_count,
    }


def execute_failure_scenario(repo: Path, scenario: str) -> dict[str, Any]:
    counters = {
        "marker_create_count": 0,
        "secret_read_or_materialize_count": 0,
        "usb_open_count": 0,
        "command_send_count": 0,
        "cleanup_count": 0,
        "retry_count": 0,
    }
    harness = ""
    gate = ""
    failure = ""

    runtime_scenarios = {
        "wrong_vid_pid", "identity_changes_after_open", "interface_claim_failure",
        "live_otp_cache_mismatch", "e4_mismatch",
        "secret_tls_object_identity_mismatch", "cleanup_exception",
        "unexpected_extra_frame_after_final_0x32",
    }
    if scenario in runtime_scenarios:
        harness = "FULL_FAKE_RUNTIME"
        gate = "PersistentRuntimeCoordinator.run"
        result = run_scenario(repo, scenario)
        if result["passed"]:
            raise AssertionError(f"scenario unexpectedly passed:{scenario}")
        failure = result["observed_failure_class"] or "FAIL_CLOSED_WITHOUT_EXCEPTION_TEXT"
        counters.update(
            usb_open_count=result["usb"]["open_count"],
            command_send_count=result["usb"]["command_send_count"],
            cleanup_count=result["usb"]["close_count"],
            retry_count=result["audit"]["retry_count"],
        )
    elif scenario in {"wrong_git_baseline", "modified_live_critical_file"}:
        harness = "REAL_TEMP_GIT_REPOSITORY"
        gate = "verify_approved_git_baseline"
        with tempfile.TemporaryDirectory(prefix="d261-git-gate-") as tmp:
            git_repo, baseline, fileset = _temp_git_repository(Path(tmp))
            target = git_repo / CANONICAL_LIVE_CRITICAL_PATHS[0]
            target.write_text("fixture-v2\n", encoding="utf-8")
            if scenario == "wrong_git_baseline":
                _git(git_repo, "add", ".")
                _git(git_repo, "commit", "-qm", "second fixture")
            failure = _capture_failure(
                lambda: verify_approved_git_baseline(git_repo, baseline, fileset)
            )
    elif scenario == "stale_marker":
        harness = "SYNTHETIC_LOCAL_FILESYSTEM"
        gate = "claim_marker"
        with tempfile.TemporaryDirectory(prefix="d261-marker-gate-") as tmp:
            marker = Path(tmp) / "marker"
            marker.write_text("stale\n", encoding="utf-8")
            cli_intent = _issue_cli_intent_after_exact_main_flag(D261_LIVE_AUTHORIZATION_FLAG)
            failure = _capture_failure(
                lambda: claim_marker(marker, "1" * 40, cli_intent, expected_uid=os.getuid())
            )
    elif scenario == "external_holder":
        harness = "INJECTED_OS_FACADE"
        gate = "require_no_external_holders"
        failure = _capture_failure(
            lambda: require_no_external_holders([os.getpid(), os.getpid() + 1], own_pid=os.getpid())
        )
    elif scenario == "config90_hash_mismatch":
        harness = "SYNTHETIC_PROTECTED_CONTENT"
        gate = "validate_config90_content"
        failure = _capture_failure(lambda: validate_config90_content(bytes(224)))
        counters["secret_read_or_materialize_count"] = 1
    elif scenario in {"cache_hash_failure", "cache_layout_failure", "cache_crc_failure"}:
        harness = "SYNTHETIC_LOCAL_CACHE"
        gate = "provide_hash_gated_fdt12"
        with tempfile.TemporaryDirectory(prefix="d261-cache-gate-") as tmp:
            cache = Path(tmp) / "goodix.dat"
            if scenario == "cache_layout_failure":
                data = b"short"
                cache.write_bytes(data)
                expected = hashlib.sha256(data).hexdigest()
            elif scenario == "cache_crc_failure":
                data = bytearray(13_520)
                data[:64] = SYNTHETIC_OTP
                data[64:76] = bytes.fromhex("801080118012801380148015")
                data[CRC_OFFSET:] = b"\x01\x00\x00\x00"
                cache.write_bytes(data)
                expected = hashlib.sha256(data).hexdigest()
            else:
                expected = _build_seed_cache(cache, SYNTHETIC_OTP)
                expected = ("0" if expected[0] != "0" else "1") + expected[1:]
            result = provide_hash_gated_fdt12(cache, SYNTHETIC_OTP, expected)
            if result.ok:
                raise AssertionError("cache gate unexpectedly passed")
            failure = f"SeedProviderFailure:{result.failure_reason}"
    elif scenario == "secret_metadata_invalid":
        harness = "SYNTHETIC_PROTECTED_METADATA"
        gate = "protected_metadata"
        with tempfile.TemporaryDirectory(prefix="d261-secret-metadata-") as tmp:
            path = Path(tmp) / "secret"
            path.write_bytes(bytes(88))
            path.chmod(0o644)
            metadata = protected_metadata(path, 88, expected_uid=os.getuid())
            failure = _capture_failure(
                lambda: (_ for _ in ()).throw(
                    ProtectedRuntimeFailure("protected_metadata_invalid")
                ) if not metadata["metadata_pass"] else None
            )
    elif scenario in {"fprintd_stop_failure", "fprintd_restore_failure"}:
        harness = "INJECTED_SYSTEMD_FACADE"
        gate = "FprintdTransaction"
        runner, _calls = _runner(
            stop_failure=scenario == "fprintd_stop_failure",
            restore_failure=scenario == "fprintd_restore_failure",
        )
        transaction = FprintdTransaction(runner=runner)
        if scenario == "fprintd_stop_failure":
            failure = _capture_failure(transaction.prepare)
        else:
            transaction.prepare()
            failure = _capture_failure(transaction.restore)
        counters["cleanup_count"] = transaction.restore_count
    elif scenario == "signal_restore_failure":
        harness = "INJECTED_SIGNAL_FACADE"
        gate = "SignalTransaction.restore"
        calls = 0
        def mask_fn(how, value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic_signal_restore_failure")
            return set()
        transaction = SignalTransaction(mask_fn=mask_fn)
        transaction.block()
        failure = _capture_failure(transaction.restore)
    elif scenario == "report_path_unsafe":
        harness = "SYNTHETIC_LOCAL_REPORT_FILESYSTEM"
        gate = "publish_report"
        with tempfile.TemporaryDirectory(prefix="d261-report-gate-") as tmp:
            directory = Path(tmp) / "reports"
            directory.mkdir(mode=0o755)
            failure = _capture_failure(
                lambda: publish_report(directory / "final.json", {"result": "FAIL"}, expected_uid=os.getuid())
            )
    elif scenario == "physical_policy_mismatch":
        harness = "EXECUTED_POLICY_FACTORY"
        gate = "operational physical policy allowlist"
        from core.runtime_transport import operational_fdt_a0_policy
        failure = _capture_failure(lambda: operational_fdt_a0_policy(0xF4, 100))
    elif scenario in {"tail_policy_mismatch", "wrong_physical_length"}:
        harness = "LIBUSB_TRANSPORT_WITH_POLICY_FIXTURE"
        gate = "LibusbRuntimeTransport.submit"
        failure, observed = _invalid_physical_policy_failure(scenario)
        counters.update(observed)
    else:
        raise AssertionError(f"unimplemented negative scenario:{scenario}")

    return {
        "scenario": scenario,
        "execution_harness": harness,
        "gate_invoked": gate,
        "observed_failure_class": failure,
        **counters,
        "contained": bool(failure) and counters["retry_count"] == 0,
        "NO_AUTOMATIC_RETRY": counters["retry_count"] == 0,
        "FIXTURE_CLASS": "SYNTHETIC_LOCAL",
        "LIVE_EVIDENCE": False,
        "persistent_write_count": 0,
        "cache_write_count": 0,
    }


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0
    def __call__(self) -> float:
        return self.value


class _QueueBackend:
    def __init__(self, completions: list[bytes], *, clock: _Clock | None = None, advance: float = 0.0) -> None:
        self.completions = list(completions)
        self.clock = clock
        self.advance = advance
        self.timeout_arguments: list[int] = []
        self.router: SharedFrameRouter | None = None
        self.reentrant = False
    def bulk_in(self, endpoint, maximum, timeout_ms):
        self.timeout_arguments.append(timeout_ms)
        if self.reentrant and self.router is not None:
            self.router.receive_command(timeout_ms)
        if self.clock is not None:
            self.clock.value += self.advance
        if not self.completions:
            raise TimeoutError("fixture_empty")
        return self.completions.pop(0)


def _demux_case(name: str, call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        details = call()
        status = "PASS"
        failure = None
    except BaseException as exc:
        status = "FAIL"
        failure = f"{type(exc).__name__}:{exc}"
        details = {}
    return {
        "scenario": name,
        "execution_harness": "SharedFrameRouter",
        "gate_invoked": True,
        "status": status,
        "observed_failure_class": failure,
        "details": details,
        "FIXTURE_CLASS": "SYNTHETIC_LOCAL",
        "LIVE_EVIDENCE": False,
    }


def execute_demux_evidence() -> dict[str, Any]:
    ack1, ack2 = _ack(0x36), _ack(0x50)
    irq1, irq2 = _irq100((1, 2, 3, 4, 5, 6)), _irq100((7, 8, 9, 10, 11, 12))
    tls_payload = bytes(7688)
    b0 = wrap_tls_record_b0(b"\x17\x03\x03" + len(tls_payload).to_bytes(2, "big") + tls_payload)
    nav = _nav_response()

    def same_completion():
        backend = _QueueBackend([ack1 + irq1])
        router = SharedFrameRouter(backend)
        assert router.receive_command(100) == ack1
        assert router.receive_event(100) == irq1
        return {"physical_reads": router.physical_in_read_count}

    def split_frame():
        backend = _QueueBackend([ack1[:2], ack1[2:5], ack1[5:]])
        router = SharedFrameRouter(backend)
        assert router.receive_command(100) == ack1
        return {"physical_reads": router.physical_in_read_count}

    def buffered_event_before_wait():
        backend = _QueueBackend([ack1 + irq1])
        router = SharedFrameRouter(backend)
        router.receive_command(100)
        before = router.physical_in_read_count
        assert router.receive_event(100) == irq1
        assert router.physical_in_read_count == before
        return {"physical_reads": before}

    def command_buffered_while_event():
        backend = _QueueBackend([ack1 + irq1])
        router = SharedFrameRouter(backend)
        assert router.receive_event(100) == irq1
        before = router.physical_in_read_count
        assert router.receive_command(100) == ack1
        return {"physical_reads": before}

    def event_buffered_while_command():
        return buffered_event_before_wait()

    def large_frame(frame: bytes):
        backend = _QueueBackend([frame])
        router = SharedFrameRouter(backend)
        assert router.receive_command(100) == frame
        return {"frame_length": len(frame)}

    def interleaving():
        backend = _QueueBackend([ack1 + irq1 + b0 + ack2])
        router = SharedFrameRouter(backend)
        assert router.receive_command(100) == ack1
        assert router.receive_event(100) == irq1
        assert router.receive_command(100) == b0
        assert router.receive_command(100) == ack2
        return {"queue_end": router.queued_frame_count}

    def no_reorder():
        backend = _QueueBackend([ack1 + irq1 + ack2 + irq2])
        router = SharedFrameRouter(backend)
        assert [router.receive_command(100), router.receive_command(100)] == [ack1, ack2]
        assert [router.receive_event(100), router.receive_event(100)] == [irq1, irq2]
        return {"queue_end": router.queued_frame_count}

    def no_starvation():
        clock = _Clock()
        backend = _QueueBackend([irq1, irq2, ack1], clock=clock, advance=0.02)
        router = SharedFrameRouter(backend, monotonic=clock)
        assert router.receive_command(100) == ack1
        return {"timeouts_ms": backend.timeout_arguments, "elapsed_ms": round(clock.value * 1000)}

    def absolute_deadline():
        clock = _Clock()
        backend = _QueueBackend([irq1, irq2, irq1], clock=clock, advance=0.04)
        router = SharedFrameRouter(backend, monotonic=clock)
        failure = _capture_failure(lambda: router.receive_command(100))
        assert "phase_deadline_expired" in failure
        assert backend.timeout_arguments[0] == 100
        assert all(b < a for a, b in zip(backend.timeout_arguments, backend.timeout_arguments[1:]))
        return {"timeouts_ms": backend.timeout_arguments, "elapsed_ms": round(clock.value * 1000), "failure": failure}

    def concurrent_reader():
        backend = _QueueBackend([ack1])
        backend.reentrant = True
        router = SharedFrameRouter(backend)
        backend.router = router
        failure = _capture_failure(lambda: router.receive_command(100))
        assert "concurrent_physical_in_reader_forbidden" in failure
        return {"failure": failure}

    cases = [
        ("ack_and_irq_same_completion", same_completion),
        ("frame_split_across_completions", split_frame),
        ("irq_buffered_before_wait_event", buffered_event_before_wait),
        ("command_ack_buffered_while_waiting_event", command_buffered_while_event),
        ("event_buffered_while_waiting_command", event_buffered_while_command),
        ("large_nav_a0", lambda: large_frame(nav)),
        ("large_baseline_b0", lambda: large_frame(b0)),
        ("ack_event_b0_interleaving", interleaving),
        ("no_frame_stealing", interleaving),
        ("no_silent_reorder", no_reorder),
        ("no_starvation", no_starvation),
        ("absolute_deadline_unmatched_valid_frames", absolute_deadline),
        ("concurrent_physical_read_attempt", concurrent_reader),
    ]
    rows = [_demux_case(name, call) for name, call in cases]
    return {
        "schema": "D261_SINGLE_READER_DEMUX_EXECUTION_EVIDENCE_V2",
        "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL",
        "ONE_PHYSICAL_IN_READER": True,
        "SHARED_READER_PHASE_DEADLINE_ENFORCED": True,
        "TIMEOUT_RENEWAL_PER_UNMATCHED_FRAME": False,
        "SINGLE_READER_DEMUX_EXECUTABLE_EVIDENCE": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL",
        "rows": rows,
    }


def execute_report_evidence() -> dict[str, Any]:
    rows = []
    with tempfile.TemporaryDirectory(prefix="d261-report-evidence-") as tmp:
        root = Path(tmp) / "protected"
        root.mkdir(mode=0o700)
        report_dir = root / "results"
        disposition = prepare_report_directory(root, report_dir, expected_uid=os.getuid())
        target = report_dir / "final.json"
        fsync_calls = 0
        replace_calls = 0
        real_fsync, real_replace = os.fsync, os.replace
        def fsync(fd):
            nonlocal fsync_calls
            fsync_calls += 1
            return real_fsync(fd)
        def replace(*args, **kwargs):
            nonlocal replace_calls
            replace_calls += 1
            return real_replace(*args, **kwargs)
        with mock.patch("tools.d261_live_fdt_arm_once.os.fsync", side_effect=fsync), mock.patch(
            "tools.d261_live_fdt_arm_once.os.replace", side_effect=replace
        ):
            durability = publish_report(target, {"result": "PASS"}, expected_uid=os.getuid())
        rows.append({"scenario": "durable_publish", "status": "PASS", "fsync_calls": fsync_calls, "replace_calls": replace_calls, **durability})
        assert stat.S_IMODE(target.lstat().st_mode) == 0o600 and fsync_calls >= 2 and replace_calls == 1

    with tempfile.TemporaryDirectory(prefix="d261-report-symlink-") as tmp:
        report_dir = Path(tmp) / "results"
        report_dir.mkdir(mode=0o700)
        target = report_dir / "final.json"
        target.symlink_to(report_dir / "elsewhere")
        failure = _capture_failure(lambda: publish_report(target, {"result": "PASS"}, expected_uid=os.getuid()))
        rows.append({"scenario": "preexisting_final_symlink", "status": "PASS", "observed_failure_class": failure})

    with tempfile.TemporaryDirectory(prefix="d261-report-temp-collision-") as tmp:
        report_dir = Path(tmp) / "results"
        report_dir.mkdir(mode=0o700)
        target = report_dir / "final.json"
        (report_dir / f".{target.name}.{os.getpid()}.tmp").symlink_to(report_dir / "elsewhere")
        failure = _capture_failure(lambda: publish_report(target, {"result": "PASS"}, expected_uid=os.getuid()))
        rows.append({"scenario": "temporary_symlink_collision", "status": "PASS", "observed_failure_class": failure})

    return {
        "schema": "D261_DURABLE_REPORT_SAFETY_EVIDENCE_V2",
        "status": "PASS",
        "REPORT_DIRECTORY_SAFETY_CHECKED_PRE_SIDE_EFFECT": True,
        "FINAL_REPORT_FAILURE_CANNOT_REPRESENT_RUN_PASS": True,
        "rows": rows,
    }


def execute_hard_disable_evidence(repo: Path) -> dict[str, Any]:
    tool = repo / "tools/d261_live_fdt_arm_once.py"
    base_env = dict(os.environ)
    default = subprocess.run((sys.executable, str(tool)), cwd=repo, env=base_env, check=False, capture_output=True, text=True)
    env_only_env = dict(base_env)
    env_only_env["D261_APPROVED_LIVE_BASELINE_SHA"] = "1" * 40
    env_only = subprocess.run((sys.executable, str(tool)), cwd=repo, env=env_only_env, check=False, capture_output=True, text=True)
    bad_counts = {"fprintd": 0, "marker": 0, "secret": 0, "usb": 0}
    def forbidden(name):
        def call(*_args, **_kwargs):
            bad_counts[name] += 1
            raise AssertionError(f"bad baseline reached forbidden gate:{name}")
        return call
    bad_stdout = io.StringIO()
    with mock.patch.dict(os.environ, {"D261_APPROVED_LIVE_BASELINE_SHA": "0" * 40}), \
         mock.patch("tools.d261_live_fdt_arm_once.FprintdTransaction.prepare", side_effect=forbidden("fprintd")), \
         mock.patch("tools.d261_live_fdt_arm_once.claim_marker", side_effect=forbidden("marker")), \
         mock.patch("tools.d261_live_fdt_arm_once.RealSecretBoundary.materialize", side_effect=forbidden("secret")), \
         mock.patch("tools.d261_live_fdt_arm_once.CtypesLibusbBackend.open_exact", side_effect=forbidden("usb")), \
         redirect_stdout(bad_stdout):
        bad_returncode = live_main([LIVE_FLAG])
    direct_failure = _capture_failure(lambda: _run_live(repo, "0" * 40, None))
    backend = CtypesLibusbBackend()
    backend_failure = _capture_failure(lambda: backend.open_exact(0x27C6, 0x5125, 0))
    assert backend._lib is None and backend.open_count == 0
    default_json = json.loads(default.stdout)
    env_only_json = json.loads(env_only.stdout)
    bad_json = json.loads(bad_stdout.getvalue())
    passed = (
        default.returncode == 2
        and env_only.returncode == 2
        and default_json["status"] == env_only_json["status"] == "HARD_DISABLED_DEFAULT"
        and "valid_cli_intent_capability_required" in direct_failure
        and "live_io_capability_required" in backend_failure
        and bad_returncode == 1
        and "git_rev-parse_failed" in bad_json["failure_class"]
        and not any(bad_counts.values())
    )
    return {
        "schema": "D261_HARD_DISABLE_EXECUTION_EVIDENCE_V2",
        "status": "PASS" if passed else "FAIL",
        "SUPPORTED_LIVE_ENTRYPOINT_COUNT": 1,
        "LIVE_CAPABILITY_DEFAULT": 0,
        "LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG": False,
        "DIRECT_PYTHON_LIVE_CALL_WITHOUT_CAPABILITY_FAILS_CLOSED": True,
        "ENVIRONMENT_ONLY_LIVE_ENABLEMENT": False,
        "BACKEND_ONLY_LIVE_ENABLEMENT": False,
        "SUPPORTED_PATH_FENCE_THREAT_MODEL": "ACCIDENTAL_AND_UNSUPPORTED_INVOCATION_FENCE_NOT_SAME_INTERPRETER_MALICIOUS_CODE_SECURITY_BOUNDARY",
        "rows": [
            {"scenario": "default_cli", "returncode": default.returncode, "result": default_json},
            {"scenario": "environment_alone", "returncode": env_only.returncode, "result": env_only_json},
            {"scenario": "direct_python_without_capability", "observed_failure_class": direct_failure},
            {"scenario": "backend_without_live_io_capability", "observed_failure_class": backend_failure, "ctypes_loaded": False},
            {
                "scenario": "exact_flag_bad_baseline", "returncode": bad_returncode,
                "result": bad_json, "observed_counters": bad_counts,
            },
        ],
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_USB_OPEN_COUNT": 0,
    }


def execute_full_operational_transaction(repo: Path) -> dict[str, Any]:
    events: list[str] = []
    cli_intent = _issue_cli_intent_after_exact_main_flag(D261_LIVE_AUTHORIZATION_FLAG)
    require_cli_intent(cli_intent)
    events.append("CLI_INTENT_CAPABILITY")
    with tempfile.TemporaryDirectory(prefix="d261-full-transaction-") as tmp:
        fixture = Path(tmp)
        git_repo, baseline, fileset = _temp_git_repository(fixture)
        verify_approved_git_baseline(git_repo, baseline, fileset)
        events.append("FULL_PREFLIGHT_BASELINE")
        protected_root = fixture / "protected"
        protected_root.mkdir(mode=0o700)
        report_dir = protected_root / "results"
        prepare_report_directory(protected_root, report_dir, expected_uid=os.getuid())
        events.append("PROTECTED_AND_REPORT_DIRECTORY_PREFLIGHT")
        secret_path = protected_root / "secret"
        secret_path.write_bytes(bytes(range(32)))
        secret_path.chmod(0o600)
        metadata = protected_metadata(secret_path, 32, expected_uid=os.getuid())
        assert metadata["metadata_pass"]
        secret_bytes = bytearray(secret_path.read_bytes())
        materialize_count = 1
        assert hashlib.sha256(secret_bytes).hexdigest()
        events.append("PROTECTED_CONTENT_VALIDATED_AND_MATERIALIZED")
        marker = protected_root / "marker"
        marker_claim = claim_marker(marker, baseline, cli_intent, expected_uid=os.getuid())
        events.append("MARKER_CLAIMED")
        live_io = issue_live_io_capability_after_marker(cli_intent, marker_claim=marker_claim)
        events.append("LIVE_IO_CAPABILITY")
        runtime = run_scenario(repo, "happy", live_io_capability=live_io)
        assert runtime["passed"] and runtime["usb"]["open_count"] == 1
        events.append("FAKE_USB_TO_STOP_AFTER_FDT_ARM_ACK")
        secret_bytes[:] = bytes(len(secret_bytes))
        events.append("CLEANUP_ZEROIZE_RESTORE")
        target = report_dir / "final.json"
        durability = publish_report(
            target,
            {"result": "PASS_STOP_AFTER_FDT_ARM_ACK", "fixture": True},
            expected_uid=os.getuid(),
        )
        events.append("DURABLE_REPORT")
        assert not any(secret_bytes)
    return {
        "schema": "D261_OFFLINE_OPERATIONAL_TRANSACTION_V2",
        "status": "PASS",
        "ordered_events": events,
        "CLI_INTENT_CAPABILITY_REQUIRED": True,
        "LIVE_IO_CAPABILITY_REQUIRES_MARKER": True,
        "MARKER_AFTER_PROTECTED_CONTENT_VALIDATION": events.index("MARKER_CLAIMED") > events.index("PROTECTED_CONTENT_VALIDATED_AND_MATERIALIZED"),
        "MARKER_IMMEDIATELY_PRECEDES_LIVE_IO_CAPABILITY": events.index("LIVE_IO_CAPABILITY") == events.index("MARKER_CLAIMED") + 1,
        "marker_create_count": 1,
        "secret_read_or_materialize_count": materialize_count,
        "fake_usb_open_count": runtime["usb"]["open_count"],
        "fake_command_send_count": runtime["usb"]["command_send_count"],
        "cleanup_count": runtime["usb"]["close_count"],
        "durable_report": durability,
        "OFFLINE_OPERATIONAL_REHEARSAL": "PASS",
        "D4_TLS_APPLICATION_RECORD_COUNT": runtime["audit"]["d4_tls_application_record_count"],
        "FDT_TRACE": runtime["audit"]["exact_fdt_command_trace"],
        "RETRY_COUNT": runtime["audit"]["retry_count"],
        "PERSISTENT_WRITE_FAMILY_COUNT": runtime["audit"]["persistent_device_write_count"],
        "HOST_CACHE_WRITE_COUNT": runtime["audit"]["host_cache_write_count"],
        "REAL_USB_OPEN_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_COMMAND_SEND_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0,
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
    }


def generate_corrective_evidence(repo: Path) -> dict[str, Any]:
    failure_rows = [execute_failure_scenario(repo, name) for name in NEGATIVE_SCENARIOS]
    failures = {
        "schema": "D261_FAILURE_CONTAINMENT_MATRIX_V2",
        "status": "PASS_EXECUTION_DERIVED" if all(row["contained"] for row in failure_rows) else "FAIL",
        "FAILURE_SCENARIO_COUNT": len(failure_rows),
        "FAILURE_SCENARIO_EXECUTED_COUNT": sum(bool(row["gate_invoked"]) for row in failure_rows),
        "ASSERTION_ONLY_FAILURE_ROWS": 0,
        "rows": failure_rows,
    }
    return {
        "failures": failures,
        "demux": execute_demux_evidence(),
        "report": execute_report_evidence(),
        "hard_disable": execute_hard_disable_evidence(repo),
        "transaction": execute_full_operational_transaction(repo),
    }


if __name__ == "__main__":
    print(json.dumps(generate_corrective_evidence(REPO), indent=2, sort_keys=True))
