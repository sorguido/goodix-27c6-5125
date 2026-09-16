#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("d279_46_protected_halfwave_polarity_eval.py")
SPEC = importlib.util.spec_from_file_location("d279_46_runner_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class ProtectedHalfwavePolarityRunnerTests(unittest.TestCase):
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
            "D279_46_ONE_OFFLINE_PROTECTED_HALFWAVE_POLARITY_COMPLETION_EVALUATION",
        )
        self.assertNotIn("D279_44", RUNNER.OPERATION)

    def test_missing_module_is_fail_closed(self):
        with self.assertRaisesRegex(RUNNER.ProtectedEvaluationError, "missing_NOT_REGULAR"):
            RUNNER.load_module("missing", Path("/missing/module.py"))

    def test_signed_control_must_reproduce_d279_44(self):
        groups = {"baseline": {}, "primary": {}, "auxiliary": {}}
        aggregate = {"variants": [{
            "baseline_preprocessing": "frame_minus_baseline_signed_control",
            "groups": groups,
        }]}
        prior = {"aggregate": {"variants": [{
            "baseline_preprocessing": "frame_minus_baseline_signed_control",
            "groups": groups,
        }]}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "summary.json")
            payload = (json.dumps(prior, sort_keys=True) + "\n").encode()
            path.write_bytes(payload)
            original = RUNNER.PRIOR_SUMMARY_SHA256
            try:
                import hashlib
                RUNNER.PRIOR_SUMMARY_SHA256 = hashlib.sha256(payload).hexdigest()
                RUNNER.require_signed_control_reproduction(aggregate, path)
                aggregate["variants"][0]["groups"] = {"baseline": {"drift": 1}}
                with self.assertRaisesRegex(RUNNER.ProtectedEvaluationError, "SIGNED_CONTROL_DRIFT"):
                    RUNNER.require_signed_control_reproduction(aggregate, path)
            finally:
                RUNNER.PRIOR_SUMMARY_SHA256 = original


if __name__ == "__main__":
    unittest.main()
