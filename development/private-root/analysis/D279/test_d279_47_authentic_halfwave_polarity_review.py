#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("d279_47_authentic_halfwave_polarity_review.py")
SPEC = importlib.util.spec_from_file_location("d279_47_review", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)
ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "captures/D279_46/D27946_20260906_USER_SUPPLIED/sanitized/summary.json"
PRIOR = ROOT / "captures/D279_44/D27944_20260906T094424Z/sanitized/summary.json"


class AuthenticHalfwavePolarityReviewTests(unittest.TestCase):
    def test_authentic_source_and_replan(self):
        result = review.build_review(review.load_authentic_summary(SOURCE, PRIOR))
        self.assertTrue(result["source_contract_valid"])
        self.assertTrue(result["privacy_contract_valid"])
        self.assertTrue(result["signed_control_reproduced_exactly"])
        self.assertEqual(result["fingerprint_frames_with_reliable_minutiae"], {
            "signed_control": {"quality_tier_b_or_a": 10, "quality_tier_a": 2},
            "frame_above_baseline_dark_on_white": {
                "quality_tier_b_or_a": 1, "quality_tier_a": 0,
            },
            "baseline_above_frame_dark_on_white": {
                "quality_tier_b_or_a": 9, "quality_tier_a": 2,
            },
        })
        self.assertFalse(result["decision"]["output_polarity_material_rescue"])
        self.assertNotIn("variants", result)

    def test_source_digest_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "summary.json")
            source.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(review.ReviewError, "SOURCE_SHA256"):
                review.load_authentic_summary(source, PRIOR)

    def test_privacy_role_and_matrix_changes_are_rejected(self):
        authentic = json.loads(SOURCE.read_text(encoding="utf-8"))
        changed = copy.deepcopy(authentic)
        changed["plaintext_or_raster_exported"] = True
        self._load_with_digest(changed, "RASTER_EXPORT")
        changed = copy.deepcopy(authentic)
        changed["aggregate"]["target_raster_role_order"] = "blocked"
        self._load_with_digest(changed, "ROLE_ORDER")
        changed = copy.deepcopy(authentic)
        changed["aggregate"]["variants"].pop()
        self._load_with_digest(changed, "VARIANTS")

    def test_signed_control_drift_is_rejected(self):
        authentic = json.loads(SOURCE.read_text(encoding="utf-8"))
        changed = copy.deepcopy(authentic)
        changed["aggregate"]["variants"][0]["groups"]["primary"]["frame_count"] = 20
        self._load_with_digest(changed, "FRAME_COUNT")

    @staticmethod
    def _load_with_digest(value, expected_error):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "summary.json")
            payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
            source.write_bytes(payload)
            original = review.EXPECTED_SOURCE_SHA256
            try:
                review.EXPECTED_SOURCE_SHA256 = hashlib.sha256(payload).hexdigest()
                with unittest.TestCase().assertRaisesRegex(review.ReviewError, expected_error):
                    review.load_authentic_summary(source, PRIOR)
            finally:
                review.EXPECTED_SOURCE_SHA256 = original


if __name__ == "__main__":
    unittest.main()
