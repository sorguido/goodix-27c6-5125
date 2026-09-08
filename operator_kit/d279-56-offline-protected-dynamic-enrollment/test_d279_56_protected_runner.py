#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]


def load_validator():
    path = KIT / "d279_56_validate_summary.py"
    spec = importlib.util.spec_from_file_location("d279_56_validator_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProtectedRunnerTests(unittest.TestCase):
    def test_authority_is_exactly_bounded_and_origin_granted(self):
        authority = json.loads((KIT / "D279_56_authority.json").read_text())
        self.assertEqual(authority["authorization_status"], "GRANTED_AT_ORIGIN")
        self.assertFalse(authority["further_per_run_user_authorization_required"])
        self.assertTrue(authority["technical_retries_within_same_study_authorized"])
        self.assertFalse(authority["new_capture_or_live_usb_authorized"])
        self.assertFalse(authority["agent_sudo_authorized"])
        self.assertFalse(authority["raw_or_biometric_export_authorized"])

    def test_runner_has_no_live_or_install_surface(self):
        runner = (KIT / "run-d279-56.sh").read_text()
        protected = (KIT / "d279_56_protected_replay.py").read_text()
        for forbidden in ("dnf install", "rpm -i", "g_usb_device_open",
                          "libusb_open", "fp_context_enumerate", "ClearApp",
                          "0xe0", "0xa4", "0xf0", "0xf4"):
            self.assertNotIn(forbidden, runner + protected)
        self.assertIn("--offline-preflight", runner)
        self.assertIn("--prepare-authorized-study", runner)
        self.assertIn("--run-authorized-study", runner)
        self.assertIn("RUN_REQUIRES_VISIBLE_SUDO_OPERATOR", runner)

    def test_validator_accepts_only_classification_aggregate(self):
        validator = load_validator()
        baseline = "a" * 40
        payload = {
            "schema": "D279_56_AUTHENTIC_DYNAMIC_ENROLLMENT_AGGREGATE_V1",
            "outcome": "AUTHENTIC_DYNAMIC_POLICY_AGGREGATE_READY",
            "baseline_sha": baseline,
            "operation": "D279_56_AUTHORIZED_OFFLINE_DYNAMIC_ENROLLMENT_REPLAY",
            "capture_sha256": "c" * 64,
            "authority_source_sha256": "d" * 64,
            "rockytkg_policy_source_sha256": "e" * 64,
            "transport_input_verified": True,
            "transport_or_psk_exported": False,
            "plaintext_or_raster_exported": False,
            "biometric_feature_or_template_exported": False,
            "live_or_usb_action_count": 0,
            "aggregate": {
                "schema": "D279_56_ROCKYTKG_DYNAMIC_ENROLLMENT_REPLAY_V1",
                "policy": {
                    "minimum_distinct_samples": 3,
                    "maximum_delivered_stages": 8,
                    "duplicate_streak_to_converge": 2,
                    "mad_duplicate_threshold": "8.0_EXCLUSIVE",
                },
                "input_primary_stage_count": 21,
                "evaluated_stage_count": 5,
                "distinct_sample_accept_count": 3,
                "first_possible_convergence_stage": 5,
                "final_selected_stage_count": 4,
                "duplicate_reject_count": 1,
                "max_stage_reached": False,
                "terminal_reason": "DUPLICATE_STREAK_CONVERGENCE",
                "per_stage": [
                    {"stage_index": index, "classification": classification}
                    for index, classification in enumerate(
                        ["ACCEPT", "ACCEPT", "ACCEPT", "DUPLICATE", "CONVERGE"], 1)
                ],
                "numeric_per_stage_mad_exported": False,
                "raster_or_biometric_feature_exported": False,
                "auxiliary_rasters_used": False,
                "target_raster_role_order": "baseline,(primary,auxiliary)*21",
                "preprocessing": "ROCKYTKG_R2_D279_49_PRODUCTION_COMPONENT",
                "baseline_semantics": "experimental",
                "dataset_single_session_same_finger": True,
                "production_policy_validated": False,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            path.write_text(json.dumps(payload))
            validator.validate(path, baseline)
            payload["aggregate"]["per_stage"][0]["mad"] = 1.0
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                validator.validate(path, baseline)


if __name__ == "__main__":
    unittest.main()
