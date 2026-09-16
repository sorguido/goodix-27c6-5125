#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
import d279_46_halfwave_output_polarity_evaluator as evaluator


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


class HalfwaveOutputPolarityEvaluatorTests(unittest.TestCase):
    def test_missing_variants_are_exact_d279_44_complements(self):
        baseline = [100] * evaluator.PIXELS
        frame = [98, 99, 100, 101, 102] * (evaluator.PIXELS // 5)
        pairs = (
            (
                "frame_above_baseline_halfwave_dark_on_white",
                "frame_minus_baseline_halfwave",
            ),
            (
                "baseline_above_frame_halfwave_dark_on_white",
                "baseline_minus_frame_halfwave",
            ),
        )
        for missing, observed in pairs:
            with self.subTest(missing=missing):
                actual = evaluator.preprocess(frame, baseline, missing)
                prior = evaluator.halfwave.preprocess(frame, baseline, observed)
                self.assertEqual(actual, bytearray(255 - value for value in prior))
                self.assertNotEqual(actual, prior)

    def test_signed_control_is_byte_exact_d279_42_forward(self):
        baseline = [100] * evaluator.PIXELS
        frame = [98, 99, 100, 101, 102] * (evaluator.PIXELS // 5)
        actual = evaluator.preprocess(frame, baseline, "frame_minus_baseline_signed_control")
        expected = evaluator.signed_delta.preprocess(frame, baseline, "frame_minus_baseline")
        self.assertEqual(actual, expected)

    def test_self_subtracted_halwaves_are_white_not_a_discriminator(self):
        baseline = [2048] * evaluator.PIXELS
        for method in evaluator.PREPROCESSORS[1:]:
            with self.subTest(method=method):
                self.assertEqual(
                    evaluator.preprocess(baseline, baseline, method),
                    bytearray([255]) * evaluator.PIXELS,
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
        self.assertEqual(
            {item["baseline_preprocessing"] for item in result["variants"]},
            set(evaluator.PREPROCESSORS),
        )
        self.assertEqual(
            {item["output_polarity"] for item in result["variants"]},
            {"signed_frame_minus_baseline_minmax", "retained_deviation_dark_on_white"},
        )

    def test_bad_shape_range_or_method_fails_closed(self):
        with self.assertRaisesRegex(evaluator.quality.QualityEvaluatorError, "LENGTH"):
            evaluator.preprocess([0], [0], "frame_above_baseline_halfwave_dark_on_white")
        frame = [0] * evaluator.PIXELS
        bad = frame.copy()
        bad[-1] = 4096
        with self.assertRaisesRegex(evaluator.quality.QualityEvaluatorError, "RANGE"):
            evaluator.preprocess(bad, frame, "baseline_above_frame_halfwave_dark_on_white")
        with self.assertRaisesRegex(evaluator.quality.QualityEvaluatorError, "METHOD"):
            evaluator.preprocess(frame, frame, "unknown")


if __name__ == "__main__":
    unittest.main()
