# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.post_d4 import (
    ExactlyOneAfMachine,
    InvalidTransition,
    PLAIN,
    STOP_AFTER_AF,
    UnexpectedAck,
    UnexpectedStateVersion,
    _checksum,
)
from analysis.D250.d250_live_critical import (
    LIVE_CRITICAL_FILES,
    offline_stale_detection_test,
)
from analysis.D250.d250_preflight import offline_sandbox_preflight
from analysis.D250.d250_preflight_observability import render


REPOSITORY = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY / "operator_kit/d250-live-af-once.sh"
AUTHORIZATION = "--i-authorize-one-d250-af-live-attempt"


def payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def outer(body: bytes) -> bytes:
    return bytes((PLAIN, len(body) & 0xFF, len(body) >> 8, (PLAIN + len(body)) & 0xFF)) + body


def ae(flags: int = 2, *, version: int = 1) -> bytes:
    return outer(payload(0xAE, bytes((version, flags)) + bytes(14)))


class ScriptedTransport:
    def __init__(self, frames=None, error: BaseException | None = None):
        self.frames = [] if frames is None else list(frames)
        self.error = error
        self.requests: list[bytes] = []

    def exchange(self, request: bytes):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.frames


class D250CoreBoundaryTests(unittest.TestCase):
    def test_happy_is_terminal_and_preserves_unknown_bits(self):
        transport = ScriptedTransport([ae(0x32)])
        machine = ExactlyOneAfMachine(transport)
        state = machine.run(0x67B2)
        self.assertEqual(machine.phase, STOP_AFTER_AF)
        self.assertEqual((state.version, state.flags), (1, 0x32))
        self.assertEqual(state.unknown_flag_bits, 0x30)
        self.assertEqual((machine.af_attempt_count, machine.af_send_count, machine.af_response_count), (1, 1, 1))
        self.assertEqual((machine.retry_count, machine.persistent_write_family_count), (0, 0))
        with self.assertRaises(InvalidTransition):
            machine.run(0x67B3)
        self.assertEqual(len(transport.requests), 1)

    def test_timeout_latches_attempt_and_forbids_reentry(self):
        transport = ScriptedTransport(error=TimeoutError("synthetic AF timeout"))
        machine = ExactlyOneAfMachine(transport)
        with self.assertRaises(TimeoutError):
            machine.run(1)
        self.assertEqual(machine.phase, "STOP_AFTER_AF_FAILURE")
        self.assertEqual((machine.af_attempt_count, machine.af_send_count), (1, 0))
        with self.assertRaises(InvalidTransition):
            machine.run(2)
        self.assertEqual(len(transport.requests), 1)

    def test_ack_duplicate_and_malformed_are_terminal(self):
        ack = outer(payload(0xB0, b"\xaf\x01"))
        cases = ([ack], [ae(), ae()], [outer(payload(0xAC, bytes(16)))])
        for frames in cases:
            with self.subTest(count=len(frames), control=frames[0][4]):
                machine = ExactlyOneAfMachine(ScriptedTransport(frames))
                with self.assertRaises((UnexpectedAck, ValueError)):
                    machine.run(3)
                self.assertEqual(machine.phase, "STOP_AFTER_AF_FAILURE")
                self.assertEqual(machine.af_attempt_count, 1)
                self.assertEqual(machine.retry_count, 0)

    def test_state_version_mismatch_is_terminal(self):
        machine = ExactlyOneAfMachine(ScriptedTransport([ae(version=2)]))
        with self.assertRaises(UnexpectedStateVersion):
            machine.run(4)
        self.assertEqual(machine.phase, "STOP_AFTER_AF_FAILURE")
        self.assertEqual((machine.af_attempt_count, machine.af_send_count), (1, 1))

    def test_process_control_exceptions_are_not_intercepted(self):
        machine = ExactlyOneAfMachine(ScriptedTransport(error=KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            machine.run(5)
        self.assertEqual(machine.phase, "AF_ATTEMPTED")


class D250OperatorClosureTests(unittest.TestCase):
    def test_capture_audit_is_reproducible_and_redacted(self):
        result = subprocess.run(
            ["python3", "analysis/D250/d250_af_capture_audit.py"],
            cwd=REPOSITORY,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        derived = json.loads(result.stdout)
        recorded = json.loads((REPOSITORY / "analysis/D250/D250_af_capture_audit.json").read_text())
        self.assertEqual(derived, recorded)
        self.assertEqual(derived["all_capture_af_occurrences"], 5)
        self.assertEqual(derived["post_d4_boundary"]["intervening_nonempty_in_frame_count"], 0)
        self.assertFalse(derived["post_d4_boundary"]["af_ack_observed"])
        self.assertEqual(derived["post_d4_boundary"]["af_ack_occurrence_count"], 0)
        self.assertFalse(derived["all_af_tails_zero"])
        tail = derived["post_d4_boundary"]["af_submission_tail_redacted"]
        self.assertEqual(tail["length"], 51)
        self.assertEqual(tail["nonzero_byte_count"], 6)
        self.assertEqual(tail["nonzero_offsets_zero_based"], list(range(27, 33)))
        self.assertTrue(tail["tails_identical"])
        self.assertFalse(tail["raw_tail_in_output"])

    def test_launcher_syntax_and_exact_modes(self):
        syntax = subprocess.run(["bash", "-n", str(LAUNCHER)], capture_output=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr.decode())
        for arguments in ((), ("--wrong",), (AUTHORIZATION, "extra")):
            result = subprocess.run([str(LAUNCHER), *arguments], cwd=REPOSITORY, text=True, capture_output=True)
            self.assertEqual(result.returncode, 64)
            self.assertIn("EXPLICIT_D250_SINGLE_RUN_AUTHORIZATION_REQUIRED", result.stderr)
            self.assertIn("D250_USB_OPEN_COUNT=0", result.stderr)
            self.assertIn("D250_AF_ATTEMPT_COUNT=0", result.stderr)
            self.assertIn("D250_AF_SEND_COUNT=0", result.stderr)

    @unittest.skipIf(os.geteuid() == 0, "non-root invocation requires a non-root test process")
    def test_exact_live_argument_is_blocked_for_non_root(self):
        result = subprocess.run(
            [str(LAUNCHER), AUTHORIZATION],
            cwd=REPOSITORY,
            env={**os.environ, "D250_APPROVED_LIVE_BASELINE_SHA": "0" * 40},
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("ROOT_CONTEXT_REQUIRED", result.stderr)
        self.assertIn("D250_USB_OPEN_COUNT=0", result.stderr)

    def test_live_critical_baseline_matrix_is_index_independent(self):
        report = offline_stale_detection_test()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["clean_state"], "APPROVED")
        self.assertEqual(set(report["invalid_sha_states"].values()), {"UNAPPROVED"})
        self.assertEqual(report["stale_path_count"], len(LIVE_CRITICAL_FILES))
        self.assertEqual(report["stale_paths_checked"], list(LIVE_CRITICAL_FILES))

    def test_preflight_marker_namespace_and_failure_observability(self):
        with tempfile.TemporaryDirectory(prefix="d250-test-preflight-") as directory:
            report = offline_sandbox_preflight(Path(directory))
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["marker_absent_case"]["d250_marker_absent"])
        self.assertFalse(report["marker_present_case"]["d250_marker_absent"])
        self.assertFalse(report["historical_markers_touched"])
        output = render(
            {
                "failure_class": "live_critical_baseline_stale",
                "failures": ["live_critical_baseline_stale"],
                "marker_namespace_status": report["marker_present_case"],
                "live_critical_set_status": "STALE",
            }
        )
        self.assertIn("D250_FAILURE_CLASS=LIVE_CRITICAL_BASELINE_STALE", output)
        self.assertIn("D250_USB_OPEN_COUNT=0", output)
        self.assertIn("D250_AF_ATTEMPT_COUNT=0", output)
        self.assertIn("D250_AF_SEND_COUNT=0", output)

    def test_real_offline_invocation_from_repository_and_external_cwd(self):
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        for cwd in (REPOSITORY, Path(tempfile.gettempdir())):
            result = subprocess.run([str(LAUNCHER), "--offline-dry-run"], cwd=cwd, env=environment, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("D250_RESULT=PASS", result.stdout)
            self.assertIn("D250_TERMINAL_BOUNDARY=STOP_AFTER_AF", result.stdout)
            self.assertIn("D250_USB_OPEN_COUNT=0", result.stdout)
            self.assertIn("D250_AF_SEND_COUNT=0", result.stdout)
            self.assertIn("D250_LIVE_CAPABILITY=HARD_GATED", result.stdout)
            self.assertIn("D250_LIVE_EXECUTION=NOT_PERFORMED", result.stdout)
            self.assertIn("D250_LIVE_BASELINE_APPROVAL=PENDING_AI_PM_REVIEW", result.stdout)


if __name__ == "__main__":
    unittest.main()
