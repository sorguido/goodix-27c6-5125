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
    _checksum,
)


REPOSITORY = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY / "operator_kit/d250-live-af-once.sh"


def payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def outer(body: bytes) -> bytes:
    return bytes((PLAIN, len(body) & 0xFF, len(body) >> 8, (PLAIN + len(body)) & 0xFF)) + body


def ae(flags: int = 2) -> bytes:
    return outer(payload(0xAE, bytes((1, flags)) + bytes(14)))


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
        self.assertFalse(derived["all_af_tails_zero"])

    def test_launcher_rejects_every_non_dry_run_invocation(self):
        for arguments in ((), ("--wrong",), ("--i-authorize-one-d250-af-live-attempt",)):
            result = subprocess.run([str(LAUNCHER), *arguments], cwd=REPOSITORY, text=True, capture_output=True)
            self.assertEqual(result.returncode, 64)
            self.assertIn("EXPLICIT_SEPARATE_D250_LIVE_AUTHORIZATION_REQUIRED", result.stderr)
            self.assertIn("D250_USB_OPEN_COUNT=0", result.stderr)

    def test_real_offline_invocation_from_repository_and_external_cwd(self):
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        for cwd in (REPOSITORY, Path(tempfile.gettempdir())):
            result = subprocess.run([str(LAUNCHER), "--offline-dry-run"], cwd=cwd, env=environment, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("D250_RESULT=PASS", result.stdout)
            self.assertIn("D250_TERMINAL_BOUNDARY=STOP_AFTER_AF", result.stdout)
            self.assertIn("D250_USB_OPEN_COUNT=0", result.stdout)
            self.assertIn("D250_AF_SEND_COUNT=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
