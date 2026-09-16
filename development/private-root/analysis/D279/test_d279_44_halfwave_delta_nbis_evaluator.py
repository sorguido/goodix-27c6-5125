#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
import d279_44_halfwave_delta_nbis_evaluator as evaluator


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


class HalfwaveDeltaNbisEvaluatorTests(unittest.TestCase):
    def test_halfwave_rejects_opposite_sign(self):
        baseline = [100] * evaluator.PIXELS
        frame = [98, 99, 100, 101, 102] * (evaluator.PIXELS // 5)
        positive = evaluator.preprocess(frame, baseline, "frame_minus_baseline_halfwave")
        negative = evaluator.preprocess(frame, baseline, "baseline_minus_frame_halfwave")
        self.assertEqual(list(positive[:5]), [0, 0, 0, 128, 255])
        self.assertEqual(list(negative[:5]), [255, 128, 0, 0, 0])

    def test_signed_control_preserves_both_signs(self):
        baseline = [100] * evaluator.PIXELS
        frame = [98, 99, 100, 101, 102] * (evaluator.PIXELS // 5)
        signed = evaluator.preprocess(frame, baseline, "frame_minus_baseline_signed_control")
        self.assertEqual(list(signed[:5]), [0, 64, 128, 191, 255])

    def test_halfwave_then_minmax_when_every_delta_is_positive(self):
        baseline = [100] * evaluator.PIXELS
        frame = [101, 102, 103, 104, 105] * (evaluator.PIXELS // 5)
        positive = evaluator.preprocess(frame, baseline, "frame_minus_baseline_halfwave")
        self.assertEqual(list(positive[:5]), [0, 64, 128, 191, 255])

    def test_equal_baseline_is_zero_for_all_methods(self):
        baseline = [2048] * evaluator.PIXELS
        for method in evaluator.PREPROCESSORS:
            with self.subTest(method=method):
                self.assertEqual(evaluator.preprocess(baseline, baseline, method), bytearray(evaluator.PIXELS))

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
        self.assertEqual(
            {item["baseline_preprocessing"] for item in result["variants"]},
            set(evaluator.PREPROCESSORS),
        )
        self.assertEqual(
            {item["polarity"] for item in result["variants"]},
            {"frame_positive", "baseline_positive"},
        )

    def test_bad_shape_range_or_method_fails_closed(self):
        with self.assertRaisesRegex(evaluator.quality.QualityEvaluatorError, "LENGTH"):
            evaluator.preprocess([0], [0], "frame_minus_baseline_halfwave")
        frame = [0] * evaluator.PIXELS
        bad = frame.copy()
        bad[-1] = 4096
        with self.assertRaisesRegex(evaluator.quality.QualityEvaluatorError, "RANGE"):
            evaluator.preprocess(bad, frame, "frame_minus_baseline_halfwave")
        with self.assertRaisesRegex(evaluator.quality.QualityEvaluatorError, "METHOD"):
            evaluator.preprocess(frame, frame, "unknown")


if __name__ == "__main__":
    unittest.main()
