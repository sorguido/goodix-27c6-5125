#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Aggregate NBIS quality evaluation of baseline-delta preprocessing."""

from __future__ import annotations

from typing import Sequence

import d279_39_nbis_quality_evaluator as quality


WIDTH = 80
HEIGHT = 64
PIXELS = WIDTH * HEIGHT
ROLES = quality.TARGET_RASTER_ROLES
PREPROCESSORS = ("frame_minmax_control", "frame_minus_baseline", "baseline_minus_frame")


def minmax_signed(values: Sequence[int]) -> bytearray:
    if len(values) != PIXELS or not all(type(value) is int for value in values):
        raise quality.QualityEvaluatorError("SIGNED_RASTER_CONTRACT")
    lower, upper = min(values), max(values)
    if lower == upper:
        return bytearray(PIXELS)
    span = upper - lower
    return bytearray(((value - lower) * 255 + span // 2) // span for value in values)


def preprocess(frame: Sequence[int], baseline: Sequence[int], method: str) -> bytearray:
    if len(frame) != PIXELS or len(baseline) != PIXELS:
        raise quality.QualityEvaluatorError("BASELINE_DELTA_LENGTH")
    if not all(type(value) is int and 0 <= value <= 0xFFF for value in frame):
        raise quality.QualityEvaluatorError("BASELINE_DELTA_RANGE")
    if not all(type(value) is int and 0 <= value <= 0xFFF for value in baseline):
        raise quality.QualityEvaluatorError("BASELINE_DELTA_RANGE")
    if method == "frame_minmax_control":
        return minmax_signed(frame)
    if method not in ("frame_minus_baseline", "baseline_minus_frame"):
        raise quality.QualityEvaluatorError("BASELINE_DELTA_METHOD")
    sign = 1 if method == "frame_minus_baseline" else -1
    lower = min(sign * (sample - base) for sample, base in zip(frame, baseline))
    upper = max(sign * (sample - base) for sample, base in zip(frame, baseline))
    if lower == upper:
        return bytearray(PIXELS)
    span = upper - lower
    return bytearray(
        ((sign * (sample - base) - lower) * 255 + span // 2) // span
        for sample, base in zip(frame, baseline)
    )


def evaluate_target_attempt(rasters: Sequence[Sequence[int]], runner: quality.QualityRunner) -> dict:
    quality.require(len(rasters) == 43, "TARGET_RASTER_COUNT")
    baseline = rasters[0]
    variants = []
    for method in PREPROCESSORS:
        measured = {role: [] for role in quality.ROLES}
        for role, raster in zip(ROLES, rasters):
            pixels = preprocess(raster, baseline, method)
            try:
                metrics = runner.measure(pixels, WIDTH, HEIGHT, 2)
                metrics.as_aggregate_inputs()
                measured[role].append(metrics)
            finally:
                quality.cleanse(pixels)
        variants.append({
            "variant": f"{method}/identity/normal/spatial_x2",
            "baseline_preprocessing": method,
            "intensity_scale": "frame_minmax",
            "orientation": "identity",
            "polarity": "normal" if method != "baseline_minus_frame" else "delta_inverted",
            "spatial_factor": 2,
            "groups": {
                role: quality._aggregate_group(measured[role]) for role in quality.ROLES
            },
        })
    return {
        "schema": "D279_42_BASELINE_DELTA_NBIS_AGGREGATE_V1",
        "hypothesis": "PER_PIXEL_NO_FINGER_BASELINE_DELTA_REMOVES_FIXED_FIELD_BEFORE_MINMAX_X2",
        "ppmm_zero_reliability_scope": "QUALITY_MAP_TIER_ONLY_NOT_PHYSICAL_GRAYSCALE_RELIABILITY",
        "target_raster_role_order": "baseline,(primary,auxiliary)*21",
        "frame_roles": {"baseline": 1, "primary": 21, "auxiliary": 21},
        "variant_count": len(variants),
        "per_frame_metrics_exported": False,
        "quality_maps_exported": False,
        "raster_exported": False,
        "template_exported": False,
        "variants": variants,
    }
