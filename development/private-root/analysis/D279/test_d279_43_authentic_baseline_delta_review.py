#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("d279_43_authentic_baseline_delta_review.py")
SPEC = importlib.util.spec_from_file_location("d279_43_review", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)
SOURCE = Path(__file__).parents[2] / "captures/D279_42/D27942_20260906T091610Z/sanitized/summary.json"


class AuthenticBaselineDeltaReviewTests(unittest.TestCase):
    def test_authentic_source_and_compact_review(self):
        result = review.build_review(review.load_authentic_summary(SOURCE))
        self.assertTrue(result["source_contract_valid"])
        self.assertTrue(result["privacy_contract_valid"])
        self.assertTrue(result["correct_role_order_valid"])
        self.assertEqual(
            result["fingerprint_frames_with_minutiae_in_quality_tier_b_or_a"],
            {"frame_minmax_control": 5, "frame_minus_baseline": 10, "baseline_minus_frame": 10},
        )
        self.assertEqual(
            result["fingerprint_frames_with_minutiae_in_quality_tier_a"],
            {"frame_minmax_control": 0, "frame_minus_baseline": 2, "baseline_minus_frame": 1},
        )
        self.assertNotIn("variants", result)

    def test_digest_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "summary.json")
            source.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(review.ReviewError, "SOURCE_SHA256"):
                review.load_authentic_summary(source)

    def test_privacy_and_role_order_changes_are_rejected(self):
        authentic = json.loads(SOURCE.read_text(encoding="utf-8"))
        privacy = copy.deepcopy(authentic)
        privacy["plaintext_or_raster_exported"] = True
        self._load_with_digest(privacy, "RASTER_EXPORT")
        roles = copy.deepcopy(authentic)
        roles["aggregate"]["target_raster_role_order"] = "baseline,primary*21,auxiliary*21"
        self._load_with_digest(roles, "ROLE_ORDER")

    def test_matrix_and_statistical_invariants_are_rejected(self):
        authentic = json.loads(SOURCE.read_text(encoding="utf-8"))
        matrix = copy.deepcopy(authentic)
        matrix["aggregate"]["variants"].pop()
        self._load_with_digest(matrix, "VARIANTS")
        statistic = copy.deepcopy(authentic)
        metric = statistic["aggregate"]["variants"][0]["groups"]["primary"]["metrics"]["minutiae_total"]
        metric["median"] = metric["maximum"] + 1
        self._load_with_digest(statistic, "RANGE")

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
                    review.load_authentic_summary(source)
            finally:
                review.EXPECTED_SOURCE_SHA256 = original


if __name__ == "__main__":
    unittest.main()
