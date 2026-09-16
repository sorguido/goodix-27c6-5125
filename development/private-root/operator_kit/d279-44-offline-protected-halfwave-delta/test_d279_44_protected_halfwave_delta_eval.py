#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("d279_44_protected_halfwave_delta_eval.py")
SPEC = importlib.util.spec_from_file_location("d279_44_runner_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class ProtectedHalfwaveDeltaRunnerTests(unittest.TestCase):
    def test_normal_user_refused_before_any_input_path(self):
        if os.geteuid() == 0:
            self.skipTest("normal-user gate cannot be exercised as root")
        args = SimpleNamespace(
            baseline="0" * 40, capture=Path("/must-not-read"),
            nbis_helper=Path("/must-not-run"), output=Path("/must-not-write"),
        )
        with self.assertRaisesRegex(RUNNER.ProtectedEvaluationError, "ROOT_REQUIRED"):
            RUNNER.evaluate(args)

    def test_operation_is_new_and_exact(self):
        self.assertEqual(
            RUNNER.OPERATION,
            "D279_44_ONE_OFFLINE_PROTECTED_HALFWAVE_DELTA_EVALUATION",
        )
        self.assertNotIn("D279_42", RUNNER.OPERATION)

    def test_missing_module_is_fail_closed(self):
        with self.assertRaisesRegex(RUNNER.ProtectedEvaluationError, "missing_NOT_REGULAR"):
            RUNNER.load_module("missing", Path("/missing/module.py"))


if __name__ == "__main__":
    unittest.main()
