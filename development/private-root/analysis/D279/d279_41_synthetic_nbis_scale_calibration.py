#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Calibrate pinned NBIS quality-map scale response on synthetic ridges."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Protocol

from d279_39_nbis_quality_evaluator import (
    ExactLibfprintResizeNbisQualityPipe,
    NbisQualityMetrics,
)


WIDTH = 80
HEIGHT = 64
PERIODS = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0,
           8.0, 9.0, 10.0, 11.0, 12.0, 14.0, 16.0)
ANGLES_DEGREES = (0, 30, 60, 90)
PHASE_FRACTIONS = (0.0, 0.25, 0.5, 0.75)
FACTORS = (1, 2, 3)


class QualityRunner(Protocol):
    def measure(
        self, pixels: bytearray, width: int, height: int, factor: int
    ) -> NbisQualityMetrics:
        ...


def synthetic_ridges(period: float, angle_degrees: int, phase_fraction: float) -> bytearray:
    if period <= 0 or angle_degrees not in ANGLES_DEGREES or phase_fraction not in PHASE_FRACTIONS:
        raise ValueError("SYNTHETIC_PATTERN_CONTRACT")
    angle = math.radians(angle_degrees)
    normal_x = math.cos(angle)
    normal_y = math.sin(angle)
    phase = 2.0 * math.pi * phase_fraction
    pixels = bytearray(WIDTH * HEIGHT)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            coordinate = (x - (WIDTH - 1) / 2.0) * normal_x
            coordinate += (y - (HEIGHT - 1) / 2.0) * normal_y
            value = round(127.5 + 96.0 * math.cos(2.0 * math.pi * coordinate / period + phase))
            pixels[y * WIDTH + x] = max(0, min(255, value))
    return pixels


def _aggregate(values: list[int]) -> dict[str, int | float]:
    return {
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
    }


def evaluate(runner: QualityRunner) -> dict:
    rows = []
    for period in PERIODS:
        for factor in FACTORS:
            minutiae = []
            quality_ab = []
            quality_a = []
            for angle in ANGLES_DEGREES:
                for phase in PHASE_FRACTIONS:
                    pixels = synthetic_ridges(period, angle, phase)
                    try:
                        metrics = runner.measure(pixels, WIDTH, HEIGHT, factor)
                    finally:
                        pixels[:] = b"\x00" * len(pixels)
                    values = metrics.as_aggregate_inputs()
                    minutiae.append(values["minutiae_total"])
                    quality_ab.append(values["quality_blocks_ab_per_mille"])
                    quality_a.append(values["quality_blocks_a_per_mille"])
            rows.append({
                "native_period_pixels": period,
                "spatial_factor": factor,
                "post_resize_nominal_period_pixels": period * factor,
                "sample_count": len(ANGLES_DEGREES) * len(PHASE_FRACTIONS),
                "minutiae_total": _aggregate(minutiae),
                "quality_blocks_ab_per_mille": _aggregate(quality_ab),
                "quality_blocks_a_per_mille": _aggregate(quality_a),
            })

    bands = {}
    for factor in FACTORS:
        selected = [row for row in rows if row["spatial_factor"] == factor]
        bands[f"spatial_x{factor}"] = {
            "maximum_median_ab_per_mille": max(
                row["quality_blocks_ab_per_mille"]["median"] for row in selected
            ),
            "native_periods_with_median_ab_at_least_250_per_mille": [
                row["native_period_pixels"] for row in selected
                if row["quality_blocks_ab_per_mille"]["median"] >= 250
            ],
        }
    return {
        "schema": "D279_41_SYNTHETIC_NBIS_SCALE_CALIBRATION_V1",
        "input": "ANALYTIC_COSINE_RIDGES_NO_BIOMETRIC_OR_PROTECTED_DATA",
        "dimensions": {"width": WIDTH, "height": HEIGHT},
        "amplitude": 96,
        "angles_degrees": list(ANGLES_DEGREES),
        "phase_fractions": list(PHASE_FRACTIONS),
        "spatial_factors": list(FACTORS),
        "nbis": "FEDORA44_LIBFPRINT_1_94_100_G_LFSPARMS_V2_PPMM_0_FLAGS_0",
        "resize": "FEDORA44_LIBFPRINT_1_94_100_FPI_IMAGE_RESIZE_PIXMAN_BILINEAR",
        "pinned_dft_nominal_periods_pixels": {
            "direction_tested": [12, 8, 6],
            "lowest_wave_excluded_from_direction_statistics": 24,
        },
        "row_count": len(rows),
        "bands": bands,
        "rows": rows,
        "live_or_usb_action_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--helper", required=True, type=Path)
    args = parser.parse_args()
    with ExactLibfprintResizeNbisQualityPipe(args.helper) as runner:
        result = evaluate(runner)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
