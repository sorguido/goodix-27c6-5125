#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("d279_39_nbis_quality_evaluator.py")
SPEC = importlib.util.spec_from_file_location("d279_39_quality_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
QUALITY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = QUALITY
SPEC.loader.exec_module(QUALITY)


def raster(value: int = 0) -> tuple[int, ...]:
    return (value,) * QUALITY.PIXELS


def scale(source, _method):
    return bytearray((source[0],)) * QUALITY.PIXELS


class SyntheticRunner:
    def __init__(self):
        self.borrowed = []
        self.calls = []

    def measure(self, pixels, width, height, factor):
        self.borrowed.append(pixels)
        self.calls.append((width, height, factor))
        total = pixels[0]
        rel25 = total // 2
        rel50 = total // 4
        return QUALITY.NbisQualityMetrics(
            total, rel25, rel50, (1, 2, 3, factor, 1), factor + 7, 1
        )


class NbisQualityEvaluatorTests(unittest.TestCase):
    def test_metric_validation_and_derived_ratios(self):
        metrics = QUALITY.NbisQualityMetrics(8, 4, 2, (1, 2, 3, 1, 1), 8, 1)
        values = metrics.as_aggregate_inputs()
        self.assertEqual(values["quality_blocks_ab"], 2)
        self.assertEqual(values["quality_blocks_ab_per_mille"], 250)
        self.assertEqual(values["minutiae_ab_fraction_per_mille"], 500)
        with self.assertRaisesRegex(
            QUALITY.QualityEvaluatorError, "QUALITY_MAP_LEVEL_SUM"
        ):
            QUALITY.NbisQualityMetrics(0, 0, 0, (1, 0, 0, 0, 0), 2, 1).as_aggregate_inputs()

    def test_nine_variants_are_aggregate_only_and_cleansed(self):
        runner = SyntheticRunner()
        result = QUALITY.evaluate(
            [
                QUALITY.Frame("baseline", raster(0)),
                QUALITY.Frame("primary", raster(4)),
                QUALITY.Frame("auxiliary", raster(8)),
            ],
            runner,
            scale,
        )
        self.assertEqual(result["variant_count"], 9)
        self.assertEqual(len(runner.calls), 27)
        self.assertTrue(all(not any(buffer) for buffer in runner.borrowed))
        self.assertFalse(result["per_frame_metrics_exported"])
        self.assertFalse(result["quality_maps_exported"])
        serialized = repr(result).replace("per_frame_metrics_exported", "")
        self.assertNotIn("quality_levels", serialized)
        self.assertNotIn("rasters", serialized)

    def test_target_roles_are_alternating_not_contiguous(self):
        runner = SyntheticRunner()
        result = QUALITY.evaluate_target_attempt(
            [raster(index) for index in range(43)], runner, scale
        )
        groups = result["variants"][0]["groups"]
        self.assertEqual(result["frame_roles"], {
            "baseline": 1, "primary": 21, "auxiliary": 21,
        })
        self.assertEqual(
            groups["primary"]["metrics"]["minutiae_total"]["minimum"], 1
        )
        self.assertEqual(
            groups["primary"]["metrics"]["minutiae_total"]["maximum"], 41
        )
        self.assertEqual(
            groups["auxiliary"]["metrics"]["minutiae_total"]["minimum"], 2
        )
        self.assertEqual(
            groups["auxiliary"]["metrics"]["minutiae_total"]["maximum"], 42
        )


if __name__ == "__main__":
    unittest.main()
