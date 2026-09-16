#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).parent
sys.path.insert(0, str(MODULE_DIR))
MODULE_PATH = MODULE_DIR / "d279_41_synthetic_nbis_scale_calibration.py"
SPEC = importlib.util.spec_from_file_location("d279_41_calibration", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
calibration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calibration)


class FakeRunner:
    def measure(self, _pixels, _width, _height, factor):
        quality = (0, 0, 0, factor, 4 - factor)
        return calibration.NbisQualityMetrics(
            minutiae_total=factor,
            minutiae_reliability_ge_025=factor,
            minutiae_reliability_ge_050=0,
            quality_levels=quality,
            map_width=1,
            map_height=4,
        )


class SyntheticNbisScaleCalibrationTests(unittest.TestCase):
    def test_pattern_is_bounded_nonconstant_and_repeatable(self):
        first = calibration.synthetic_ridges(5.0, 30, 0.25)
        second = calibration.synthetic_ridges(5.0, 30, 0.25)
        self.assertEqual(len(first), 80 * 64)
        self.assertEqual(first, second)
        self.assertGreater(max(first), min(first))

    def test_invalid_pattern_contract_is_rejected(self):
        for arguments in ((0, 30, 0.25), (5, 31, 0.25), (5, 30, 0.2)):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, "SYNTHETIC_PATTERN_CONTRACT"):
                    calibration.synthetic_ridges(*arguments)

    def test_aggregate_has_complete_matrix_and_no_per_sample_data(self):
        result = calibration.evaluate(FakeRunner())
        self.assertEqual(result["row_count"], len(calibration.PERIODS) * 3)
        self.assertEqual({row["spatial_factor"] for row in result["rows"]}, {1, 2, 3})
        self.assertTrue(all(row["sample_count"] == 16 for row in result["rows"]))
        self.assertNotIn("pixels", result)
        self.assertEqual(result["live_or_usb_action_count"], 0)


if __name__ == "__main__":
    unittest.main()
