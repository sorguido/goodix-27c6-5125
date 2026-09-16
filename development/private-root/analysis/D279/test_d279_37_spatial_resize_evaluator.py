#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


D34 = load("d279_37_test_d34", ROOT / "analysis/D279/d279_34_exact_nbis_variant_evaluator.py")
D37 = load("d279_37_tested", ROOT / "analysis/D279/d279_37_spatial_resize_evaluator.py")


def raster(offset=0):
    return tuple((index * 37 + offset) & 0xFFF for index in range(5120))


class SyntheticRunner:
    def __init__(self):
        self.calls = []
        self.borrowed = []

    def count(self, pixels, width, height, factor):
        self.calls.append((width, height, factor))
        self.borrowed.append(pixels)
        return factor + sum(value >= 128 for value in pixels) // 1024


class SpatialResizeEvaluatorTests(unittest.TestCase):
    def test_matrix_is_minimal_3_by_3_and_aggregate_only(self):
        runner = SyntheticRunner()
        result = D37.evaluate(
            [
                D37.Frame("baseline", raster()),
                D37.Frame("primary", raster(1)),
                D37.Frame("primary", raster(2)),
                D37.Frame("auxiliary", raster(3)),
            ],
            runner,
            D34.scale_raster,
        )
        self.assertEqual(result["variant_count"], 9)
        self.assertEqual(len(runner.calls), 9 * 4)
        self.assertEqual({call[2] for call in runner.calls}, {1, 2, 3})
        self.assertEqual({(call[0], call[1]) for call in runner.calls}, {(80, 64)})
        self.assertEqual(
            result["frame_roles"], {"baseline": 1, "primary": 2, "auxiliary": 1}
        )
        self.assertTrue(all(not any(buffer) for buffer in runner.borrowed))
        serialized_keys = repr(result).replace("per_frame_counts_exported", "")
        self.assertNotIn("'counts'", serialized_keys)
        self.assertFalse(result["per_frame_counts_exported"])

    def test_factor_one_variants_are_exact_d279_35_controls(self):
        runner = SyntheticRunner()
        result = D37.evaluate(
            [
                D37.Frame("baseline", raster()),
                D37.Frame("primary", raster(1)),
                D37.Frame("auxiliary", raster(2)),
            ],
            runner,
            D34.scale_raster,
        )
        controls = [
            variant for variant in result["variants"] if variant["spatial_factor"] == 1
        ]
        self.assertEqual(
            [variant["variant"] for variant in controls],
            [
                f"{scale}/identity/normal/spatial_x1"
                for scale in D37.INTENSITY_SCALES
            ],
        )
        self.assertTrue(result["factor_1_control_bypasses_interpolation"])

    def test_target_decomposition_is_exact(self):
        runner = SyntheticRunner()
        result = D37.evaluate_target_attempt(
            [raster(index) for index in range(43)], runner, D34.scale_raster
        )
        self.assertEqual(
            result["frame_roles"], {"baseline": 1, "primary": 21, "auxiliary": 21}
        )
        self.assertEqual(
            D37.TARGET_RASTER_ROLES[:7],
            ("baseline", "primary", "auxiliary", "primary", "auxiliary",
             "primary", "auxiliary"),
        )
        self.assertEqual(D37.TARGET_RASTER_ROLES[-2:],
                         ("primary", "auxiliary"))
        self.assertEqual(len(runner.calls), 9 * 43)

    def test_invalid_scale_output_is_cleansed_and_rejected(self):
        bad = bytearray(2)

        def bad_scale(_raster, _method):
            return bad

        with self.assertRaisesRegex(D37.EvaluatorError, "SCALE_RASTER_CONTRACT"):
            D37.evaluate(
                [
                    D37.Frame("baseline", raster()),
                    D37.Frame("primary", raster(1)),
                    D37.Frame("auxiliary", raster(2)),
                ],
                SyntheticRunner(),
                bad_scale,
            )
        self.assertEqual(bad, b"\x00\x00")


if __name__ == "__main__":
    unittest.main()
