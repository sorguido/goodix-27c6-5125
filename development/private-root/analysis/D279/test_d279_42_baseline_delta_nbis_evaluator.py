#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
import d279_42_baseline_delta_nbis_evaluator as evaluator


class RecordingRunner:
    def __init__(self):
        self.inputs = []

    def measure(self, pixels, width, height, factor):
        self.inputs.append((bytes(pixels), width, height, factor))
        return evaluator.quality.NbisQualityMetrics(
            minutiae_total=1,
            minutiae_reliability_ge_025=0,
            minutiae_reliability_ge_050=0,
            quality_levels=(0, 0, 4, 0, 0),
            map_width=1,
            map_height=4,
        )


class BaselineDeltaNbisEvaluatorTests(unittest.TestCase):
    def test_signed_minmax_and_inverse(self):
        baseline = [100] * evaluator.PIXELS
        frame = [100 + (index % 5) for index in range(evaluator.PIXELS)]
        forward = evaluator.preprocess(frame, baseline, "frame_minus_baseline")
        inverse = evaluator.preprocess(frame, baseline, "baseline_minus_frame")
        self.assertEqual(min(forward), 0)
        self.assertEqual(max(forward), 255)
        self.assertTrue(
            all(abs(inverted - (255 - value)) <= 1
                for value, inverted in zip(forward, inverse))
        )

    def test_equal_baseline_is_zero(self):
        baseline = [2048] * evaluator.PIXELS
        self.assertEqual(
            evaluator.preprocess(baseline, baseline, "frame_minus_baseline"),
            bytearray(evaluator.PIXELS),
        )

    def test_complete_correct_role_aggregate(self):
        rasters = [[1000 + (index % 7) for index in range(evaluator.PIXELS)]]
        rasters += [
            [1000 + ((index + frame) % 11) for index in range(evaluator.PIXELS)]
            for frame in range(42)
        ]
        runner = RecordingRunner()
        result = evaluator.evaluate_target_attempt(rasters, runner)
        self.assertEqual(result["variant_count"], 3)
        self.assertEqual(result["frame_roles"], {"baseline": 1, "primary": 21, "auxiliary": 21})
        self.assertEqual(len(runner.inputs), 129)
        self.assertTrue(all(item[3] == 2 for item in runner.inputs))
        self.assertFalse(result["per_frame_metrics_exported"])

    def test_bad_shape_or_method_fails_closed(self):
        with self.assertRaisesRegex(evaluator.quality.QualityEvaluatorError, "LENGTH"):
            evaluator.preprocess([0], [0], "frame_minus_baseline")
        frame = [0] * evaluator.PIXELS
        with self.assertRaisesRegex(evaluator.quality.QualityEvaluatorError, "METHOD"):
            evaluator.preprocess(frame, frame, "unknown")


if __name__ == "__main__":
    unittest.main()
