#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Aggregate NBIS evaluation of polarity-specific half-wave baseline deltas."""

from __future__ import annotations

from typing import Sequence

import d279_39_nbis_quality_evaluator as quality
import d279_42_baseline_delta_nbis_evaluator as signed_delta


WIDTH = 80
HEIGHT = 64
PIXELS = WIDTH * HEIGHT
ROLES = quality.TARGET_RASTER_ROLES
PREPROCESSORS = (
    "frame_minus_baseline_signed_control",
    "frame_minus_baseline_halfwave",
    "baseline_minus_frame_halfwave",
)


def preprocess(frame: Sequence[int], baseline: Sequence[int], method: str) -> bytearray:
    if len(frame) != PIXELS or len(baseline) != PIXELS:
        raise quality.QualityEvaluatorError("HALFWAVE_DELTA_LENGTH")
    if not all(type(value) is int and 0 <= value <= 0xFFF for value in frame):
        raise quality.QualityEvaluatorError("HALFWAVE_DELTA_RANGE")
    if not all(type(value) is int and 0 <= value <= 0xFFF for value in baseline):
        raise quality.QualityEvaluatorError("HALFWAVE_DELTA_RANGE")
    if method == "frame_minus_baseline_signed_control":
        return signed_delta.preprocess(frame, baseline, "frame_minus_baseline")
    if method == "frame_minus_baseline_halfwave":
        sign = 1
    elif method == "baseline_minus_frame_halfwave":
        sign = -1
    else:
        raise quality.QualityEvaluatorError("HALFWAVE_DELTA_METHOD")
    lower = min(max(sign * (sample - base), 0) for sample, base in zip(frame, baseline))
    upper = max(max(sign * (sample - base), 0) for sample, base in zip(frame, baseline))
    if upper == lower:
        return bytearray(PIXELS)
    return bytearray(
        ((max(sign * (sample - base), 0) - lower) * 255 + (upper - lower) // 2)
        // (upper - lower)
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
            "intensity_scale": "post_delta_minmax",
            "orientation": "identity",
            "polarity": "frame_positive" if not method.startswith("baseline_minus") else "baseline_positive",
            "spatial_factor": 2,
            "groups": {
                role: quality._aggregate_group(measured[role]) for role in quality.ROLES
            },
        })
    return {
        "schema": "D279_44_HALFWAVE_DELTA_NBIS_AGGREGATE_V1",
        "hypothesis": "POLARITY_SPECIFIC_HALF_WAVE_REJECTION_IMPROVES_RELIABLE_MINUTIAE_AFTER_BASELINE_SUBTRACTION",
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
