#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("d279_36_authentic_aggregate_review.py")
SPEC = importlib.util.spec_from_file_location("d279_36_review", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def synthetic_summary():
    variants = []
    for scale in review.EXPECTED_SCALES:
        for orientation in review.EXPECTED_ORIENTATIONS:
            for polarity in review.EXPECTED_POLARITIES:
                maximum = 5 if (scale, orientation, polarity) == (
                    "robust_p01_p99", "hflip", "inverted"
                ) else 0
                variants.append(
                    {
                        "variant": f"{scale}/{orientation}/{polarity}",
                        "scale": scale,
                        "orientation": orientation,
                        "polarity": polarity,
                        "groups": {
                            "baseline": {
                                "frame_count": 1,
                                "frames_with_minutiae": 0,
                                "frames_with_at_least_10_minutiae": 0,
                                "minimum": 0,
                                "median": 0,
                                "maximum": 0,
                            },
                            "primary": {
                                "frame_count": 21,
                                "frames_with_minutiae": 9 if maximum else 0,
                                "frames_with_at_least_10_minutiae": 0,
                                "minimum": 0,
                                "median": 0,
                                "maximum": maximum,
                            },
                            "auxiliary": {
                                "frame_count": 21,
                                "frames_with_minutiae": 17 if maximum else 0,
                                "frames_with_at_least_10_minutiae": 0,
                                "minimum": 0,
                                "median": 0,
                                "maximum": 3 if maximum else 0,
                            },
                        },
                    }
                )
    return {
        "schema": "D279_35_ONE_OFFLINE_PROTECTED_EVALUATION_V1",
        "outcome": "AUTHENTIC_AGGREGATE_READY",
        "baseline_sha": review.EXPECTED_BASELINE_SHA,
        "operation": review.EXPECTED_OPERATION,
        "capture_sha256": review.EXPECTED_CAPTURE_SHA256,
        "transport_input_verified": True,
        "transport_or_psk_exported": False,
        "plaintext_or_raster_exported": False,
        "template_exported": False,
        "live_or_usb_action_count": 0,
        "aggregate": {
            "schema": "D279_34_EXACT_NBIS_AGGREGATE_V1",
            "nbis": "FEDORA44_LIBFPRINT_1_94_100_G_LFSPARMS_V2_PPMM_0_FLAGS_0",
            "variant_count": 48,
            "frame_roles": review.EXPECTED_ROLES,
            "per_frame_counts_exported": False,
            "raster_exported": False,
            "template_exported": False,
            "variants": variants,
        },
    }


class AuthenticAggregateReviewTests(unittest.TestCase):
    def test_build_review_keeps_only_aggregate_information(self):
        result = review.build_review(synthetic_summary())
        self.assertTrue(result["all_variants_zero_frames_at_or_above_10"])
        self.assertEqual(result["best_primary"]["maximum"], 5)
        self.assertEqual(result["best_auxiliary_by_presence"]["frames_with_minutiae"], 17)
        self.assertNotIn("variants", result)
        self.assertNotIn("raster", json.dumps(result))

    def test_matrix_or_privacy_contract_change_is_rejected(self):
        bad_matrix = synthetic_summary()
        bad_matrix["aggregate"]["variants"].pop()
        with self.assertRaisesRegex(review.ReviewError, "VARIANTS"):
            self._validate_without_authentic_digest(bad_matrix)

        bad_privacy = synthetic_summary()
        bad_privacy["plaintext_or_raster_exported"] = True
        with self.assertRaisesRegex(review.ReviewError, "RASTER_EXPORT"):
            self._validate_without_authentic_digest(bad_privacy)

    def test_exact_source_digest_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "summary.json")
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(review.ReviewError, "SOURCE_SHA256"):
                review.load_authentic_summary(path)

    def test_write_new_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "result.json")
            review._write_new(path, b"first")
            with self.assertRaises(FileExistsError):
                review._write_new(path, b"second")
            self.assertEqual(path.read_bytes(), b"first")

    @staticmethod
    def _validate_without_authentic_digest(value):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "summary.json")
            payload = (json.dumps(value, sort_keys=True) + "\n").encode()
            path.write_bytes(payload)
            original = review.EXPECTED_SOURCE_SHA256
            try:
                review.EXPECTED_SOURCE_SHA256 = hashlib.sha256(payload).hexdigest()
                review.load_authentic_summary(path)
            finally:
                review.EXPECTED_SOURCE_SHA256 = original


if __name__ == "__main__":
    unittest.main()
