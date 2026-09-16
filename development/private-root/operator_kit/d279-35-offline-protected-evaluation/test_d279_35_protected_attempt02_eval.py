#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("d279_35_protected_attempt02_eval.py")
SPEC = importlib.util.spec_from_file_location("d279_35_runner_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class ProtectedAttempt02RunnerTests(unittest.TestCase):
    def test_normal_user_refused_before_any_input_path(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("normal-user gate cannot be exercised as root")
        args = SimpleNamespace(
            baseline="0" * 40,
            capture=Path("/path-that-must-not-be-read"),
            nbis_helper=Path("/path-that-must-not-be-run"),
            output=Path("/path-that-must-not-be-written"),
        )
        with self.assertRaisesRegex(RUNNER.ProtectedEvaluationError,
                                    "ROOT_REQUIRED_FOR_PROTECTED_READ"):
            RUNNER.evaluate(args)

    def test_synthetic_transport_read_and_owned_buffer_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            transport = bytearray((index * 7) & 0xFF for index in range(88))
            path = directory / RUNNER.TRANSPORT_NAME
            path.write_bytes(transport)
            path.chmod(0o600)
            actual, psk = RUNNER.read_transport_psk(
                directory,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                expected_hash=hashlib.sha256(transport).hexdigest(),
            )
            self.assertEqual(psk, transport[24:56])
            RUNNER.cleanse(actual)
            RUNNER.cleanse(psk)
            self.assertFalse(any(actual))
            self.assertFalse(any(psk))

    def test_transport_rejects_mode_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            path = directory / RUNNER.TRANSPORT_NAME
            path.write_bytes(bytes(88))
            path.chmod(0o644)
            with self.assertRaisesRegex(RUNNER.ProtectedEvaluationError,
                                        "TRANSPORT_FILE_MODE"):
                RUNNER.read_transport_psk(
                    directory, expected_uid=os.getuid(), expected_gid=os.getgid(),
                    expected_hash=hashlib.sha256(bytes(88)).hexdigest(),
                )
            path.chmod(0o600)
            with self.assertRaisesRegex(RUNNER.ProtectedEvaluationError,
                                        "TRANSPORT_FILE_HASH"):
                RUNNER.read_transport_psk(
                    directory, expected_uid=os.getuid(), expected_gid=os.getgid(),
                    expected_hash="0" * 64,
                )

    def test_output_is_exclusive_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "aggregate.json"
            RUNNER.write_aggregate(output, {"aggregate": {"count": 1}})
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                RUNNER.write_aggregate(output, {})


if __name__ == "__main__":
    unittest.main()
