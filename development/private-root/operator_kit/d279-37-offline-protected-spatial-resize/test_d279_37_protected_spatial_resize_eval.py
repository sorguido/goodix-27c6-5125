#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("d279_37_protected_spatial_resize_eval.py")
SPEC = importlib.util.spec_from_file_location("d279_37_runner_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class ProtectedSpatialResizeRunnerTests(unittest.TestCase):
    def test_normal_user_refused_before_any_input_path(self):
        if os.geteuid() == 0:
            self.skipTest("normal-user gate cannot be exercised as root")
        args = SimpleNamespace(
            baseline="0" * 40,
            capture=Path("/path-that-must-not-be-read"),
            nbis_helper=Path("/path-that-must-not-be-run"),
            output=Path("/path-that-must-not-be-written"),
        )
        with self.assertRaisesRegex(
            RUNNER.ProtectedEvaluationError, "ROOT_REQUIRED_FOR_PROTECTED_READ"
        ):
            RUNNER.evaluate(args)

    def test_operation_is_distinct_from_consumed_d279_35_grant(self):
        self.assertEqual(
            RUNNER.OPERATION,
            "D279_37_ONE_OFFLINE_PROTECTED_SPATIAL_RESIZE_EVALUATION",
        )
        self.assertNotEqual(RUNNER.OPERATION, "D279_35_ONE_OFFLINE_PROTECTED_EVALUATION")

    def test_missing_module_is_fail_closed(self):
        with self.assertRaisesRegex(
            RUNNER.ProtectedEvaluationError, "missing_test_module_NOT_REGULAR"
        ):
            RUNNER.load_module("missing_test_module", Path("/missing/module.py"))


if __name__ == "__main__":
    unittest.main()
