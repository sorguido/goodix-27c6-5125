#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("d279_34_exact_nbis_variant_evaluator.py")
SPEC = importlib.util.spec_from_file_location("d279_34_evaluator_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
EVALUATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EVALUATOR
SPEC.loader.exec_module(EVALUATOR)


class SyntheticRunner:
    def __init__(self):
        self.calls = []
        self.borrowed = []

    def count(self, pixels: bytearray, width: int, height: int) -> int:
        self.calls.append((width, height, pixels[0], pixels[-1]))
        self.borrowed.append(pixels)
        return sum(value >= 128 for value in pixels) // 512


def ramp(offset: int = 0) -> tuple[int, ...]:
    return tuple((index * 37 + offset) & 0xFFF for index in range(5120))


class ExactNbisVariantEvaluatorTests(unittest.TestCase):
    def test_fixed_scaling_and_dihedral_coordinates(self) -> None:
        raster = tuple(index & 0xFFF for index in range(5120))
        scaled = EVALUATOR.scale_raster(raster, "fixed_12bit")
        self.assertEqual(scaled[0], 0)
        self.assertEqual(scaled[4095], 255)
        transposed, width, height = EVALUATOR.orient(scaled, "transpose")
        self.assertEqual((width, height), (64, 80))
        self.assertEqual(transposed[1 * width + 2], scaled[2 * 80 + 1])
        rotated, width, height = EVALUATOR.orient(scaled, "rot180")
        self.assertEqual((width, height), (80, 64))
        self.assertEqual(rotated[0], scaled[-1])
        EVALUATOR.cleanse(scaled)
        EVALUATOR.cleanse(transposed)
        EVALUATOR.cleanse(rotated)

    def test_robust_scaling_clips_outliers(self) -> None:
        raster = [1000 + index % 101 for index in range(5120)]
        raster[0], raster[-1] = 0, 4095
        scaled = EVALUATOR.scale_raster(raster, "robust_p01_p99")
        self.assertEqual(scaled[0], 0)
        self.assertEqual(scaled[-1], 255)
        self.assertGreater(len(set(scaled)), 90)
        EVALUATOR.cleanse(scaled)

    def test_matrix_is_48_variants_aggregate_only_and_cleansed(self) -> None:
        runner = SyntheticRunner()
        result = EVALUATOR.evaluate(
            [
                EVALUATOR.Frame("baseline", ramp(0)),
                EVALUATOR.Frame("primary", ramp(11)),
                EVALUATOR.Frame("primary", ramp(22)),
                EVALUATOR.Frame("auxiliary", ramp(33)),
                EVALUATOR.Frame("auxiliary", ramp(44)),
            ],
            runner,
        )
        self.assertEqual(result["variant_count"], 48)
        self.assertEqual(result["frame_roles"], {
            "baseline": 1, "primary": 2, "auxiliary": 2,
        })
        self.assertEqual(len(runner.calls), 48 * 5)
        self.assertEqual({(width, height) for width, height, _, _ in runner.calls},
                         {(80, 64), (64, 80)})
        self.assertTrue(all(not any(buffer) for buffer in runner.borrowed))
        serialized_keys = repr(result)
        self.assertNotIn("pixels", serialized_keys)
        self.assertNotIn("per_frame", serialized_keys.replace(
            "per_frame_counts_exported", ""))
        self.assertFalse(result["per_frame_counts_exported"])
        for variant in result["variants"]:
            self.assertEqual(set(variant["groups"]), set(EVALUATOR.ROLES))
            self.assertNotIn("counts", variant["groups"]["primary"])

    def test_target_role_decomposition_is_exact(self) -> None:
        runner = SyntheticRunner()
        result = EVALUATOR.evaluate_target_attempt([ramp(index) for index in range(43)],
                                                   runner)
        self.assertEqual(result["frame_roles"], {
            "baseline": 1, "primary": 21, "auxiliary": 21,
        })
        self.assertEqual(len(runner.calls), 48 * 43)


if __name__ == "__main__":
    unittest.main()
