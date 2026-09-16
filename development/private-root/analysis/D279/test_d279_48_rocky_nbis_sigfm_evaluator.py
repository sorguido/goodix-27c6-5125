#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
import d279_48_rocky_nbis_sigfm_evaluator as evaluator


class FakePreprocess:
    def __init__(self):
        self.outputs = []

    def preprocess(self, raster, baseline, checkpoint):
        value = (raster[0] - baseline[0] + (17 if checkpoint == evaluator.CHECKPOINTS[0] else 29)) % 256
        output = bytearray([value]) * evaluator.PIXELS
        self.outputs.append(bytes(output))
        return output


class FakeNbis:
    def __init__(self):
        self.next_id = 0
        self.inputs = []

    def extract(self, pixels):
        identifier = self.next_id
        self.next_id += 1
        self.inputs.append(bytes(pixels))
        total = pixels[0] % 13
        metrics = evaluator.quality.NbisQualityMetrics(
            minutiae_total=total,
            minutiae_reliability_ge_025=min(total, 2),
            minutiae_reliability_ge_050=min(total, 1),
            quality_levels=(1, 2, 3, 4, 70), map_width=10, map_height=8,
        )
        return evaluator.NbisSample(identifier, metrics, total >= 10)

    def match(self, first, second):
        eligible = first.bozorth_computable and second.bozorth_computable
        return evaluator.PairScore(eligible, 41 if eligible else 0)


class FakeSigfm:
    def __init__(self):
        self.next_id = 0
        self.inputs = []

    def extract(self, pixels):
        identifier = self.next_id
        self.next_id += 1
        self.inputs.append(bytes(pixels))
        keypoints = pixels[0] + 5
        return evaluator.SigfmSample(identifier, keypoints, keypoints >= 25)

    def match(self, first, second):
        eligible = first.operational_gate_passed and second.operational_gate_passed
        return evaluator.PairScore(eligible, 21 if eligible else 0)


class ComparisonEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.rasters = [[1000] * evaluator.PIXELS]
        self.rasters += [[1000 + index] * evaluator.PIXELS for index in range(1, 43)]

    def test_complete_matrix_shared_inputs_and_privacy(self):
        pre = FakePreprocess()
        nbis = FakeNbis()
        sigfm = FakeSigfm()
        result = evaluator.evaluate_target_attempt(self.rasters, pre, nbis, sigfm)
        self.assertEqual(result["checkpoint_count"], 2)
        self.assertEqual(len(pre.outputs), 86)
        self.assertEqual(nbis.inputs, sigfm.inputs)
        self.assertTrue(all(item["same_preprocessed_raster_delivered_to_both_extractors"]
                            for item in result["checkpoints"]))
        self.assertFalse(result["per_frame_metrics_exported"])
        self.assertFalse(result["rasters_exported"])
        self.assertNotIn("inputs", result)

    def test_pair_cardinalities_are_exact(self):
        result = evaluator.evaluate_target_attempt(
            self.rasters, FakePreprocess(), FakeNbis(), FakeSigfm()
        )
        expected = {
            "paired_cycle_primary_to_auxiliary": 21,
            "within_primary": 210,
            "within_auxiliary": 210,
            "all_cross_role_primary_to_auxiliary": 441,
        }
        for checkpoint in result["checkpoints"]:
            for extractor in ("nbis", "sigfm"):
                observed = {
                    name: (
                        aggregate["logical_pair_count"],
                        aggregate["directed_score_count"],
                    )
                    for name, aggregate in checkpoint[extractor]["same_session_pairs"].items()
                }
                self.assertEqual(observed, {
                    name: (count, count * 2) for name, count in expected.items()
                })

    def test_historical_control_and_dataset_limits_are_explicit(self):
        result = evaluator.evaluate_target_attempt(
            self.rasters, FakePreprocess(), FakeNbis(), FakeSigfm()
        )
        self.assertEqual(result["historical_r0"]["source_summary_sha256"],
                         evaluator.R0_SUMMARY_SHA256)
        self.assertTrue(result["dataset_limitations"]["single_session_finger_context_only"])
        self.assertFalse(result["dataset_limitations"]["far_frr_or_accuracy_claim_permitted"])
        self.assertIn("NOT_PROVEN", result["baseline_semantics"])

    def test_bad_count_shape_range_fails_closed(self):
        with self.assertRaisesRegex(evaluator.ComparisonError, "COUNT"):
            evaluator.evaluate_target_attempt(self.rasters[:-1], FakePreprocess(), FakeNbis(), FakeSigfm())
        bad_shape = list(self.rasters)
        bad_shape[-1] = [1]
        with self.assertRaisesRegex(evaluator.ComparisonError, "LENGTH"):
            evaluator.evaluate_target_attempt(bad_shape, FakePreprocess(), FakeNbis(), FakeSigfm())
        bad_range = [list(raster) for raster in self.rasters]
        bad_range[-1][-1] = 4096
        with self.assertRaisesRegex(evaluator.ComparisonError, "RANGE"):
            evaluator.evaluate_target_attempt(bad_range, FakePreprocess(), FakeNbis(), FakeSigfm())


if __name__ == "__main__":
    unittest.main()
