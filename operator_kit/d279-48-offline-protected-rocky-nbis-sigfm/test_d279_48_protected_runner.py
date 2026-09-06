#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("d279_48_protected_rocky_nbis_sigfm_eval.py")
SPEC = importlib.util.spec_from_file_location("d279_48_runner_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)
VALIDATOR_PATH = Path(__file__).with_name("d279_48_validate_summary.py")
VALIDATOR_SPEC = importlib.util.spec_from_file_location("d279_48_validator_tested", VALIDATOR_PATH)
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/D279"))
import d279_48_rocky_nbis_sigfm_evaluator as COMPARISON  # noqa: E402
import test_d279_48_rocky_nbis_sigfm_evaluator as FIXTURES  # noqa: E402


class ProtectedRunnerTests(unittest.TestCase):
    def test_normal_user_refused_before_any_input(self):
        if os.geteuid() == 0:
            self.skipTest("normal-user gate cannot be exercised as root")
        missing = Path("/must-not-read")
        args = SimpleNamespace(
            baseline="0" * 40, capture=missing, r0_summary=missing,
            preprocess_helper=missing, nbis_helper=missing,
            sigfm_helper=missing, output=Path("/must-not-write"),
        )
        with self.assertRaisesRegex(RUNNER.ProtectedComparisonError, "ROOT_REQUIRED"):
            RUNNER.evaluate(args)

    def test_operation_is_new_exact_and_not_live(self):
        self.assertEqual(
            RUNNER.OPERATION,
            "D279_48_ONE_OFFLINE_PROTECTED_ROCKY_NBIS_SIGFM_COMPARISON",
        )
        self.assertNotIn("LIVE", RUNNER.OPERATION)
        self.assertNotIn("D279_46", RUNNER.OPERATION)

    def test_missing_module_fails_closed(self):
        with self.assertRaisesRegex(RUNNER.ProtectedComparisonError, "missing_NOT_REGULAR"):
            RUNNER.load_module("missing", Path("/missing/module.py"))

    def test_launcher_pins_snapshot_python_dependency_closure(self):
        launcher = MODULE_PATH.with_name("run-d279-48.sh").read_text(encoding="utf-8")
        self.assertIn("src/goodix5125_cleanroom.py", launcher)
        self.assertIn("verify_snapshot_python_closure", launcher)
        self.assertIn('verify_snapshot_python_closure "$snapshot"', launcher)

    def test_output_validator_accepts_only_complete_aggregate_contract(self):
        rasters = [[1000] * COMPARISON.PIXELS]
        rasters += [[1000 + index] * COMPARISON.PIXELS for index in range(1, 43)]
        aggregate = COMPARISON.evaluate_target_attempt(
            rasters, FIXTURES.FakePreprocess(), FIXTURES.FakeNbis(), FIXTURES.FakeSigfm()
        )
        approved = "1" * 40
        document = {
            "schema": "D279_48_ONE_OFFLINE_PROTECTED_ROCKY_NBIS_SIGFM_COMPARISON_V1",
            "outcome": "AUTHENTIC_ROCKY_NBIS_SIGFM_AGGREGATE_READY",
            "baseline_sha": approved,
            "operation": RUNNER.OPERATION,
            "capture_sha256": RUNNER.CAPTURE_SHA256,
            "r0_summary_sha256": RUNNER.R0_SUMMARY_SHA256,
            "transport_input_verified": True,
            "transport_or_psk_exported": False,
            "plaintext_or_raster_exported": False,
            "biometric_feature_or_template_exported": False,
            "live_or_usb_action_count": 0,
            "aggregate": aggregate,
        }
        VALIDATOR.validate(document, approved)
        document["plaintext_or_raster_exported"] = True
        with self.assertRaises(VALIDATOR.SummaryValidationError):
            VALIDATOR.validate(document, approved)


if __name__ == "__main__":
    unittest.main()
