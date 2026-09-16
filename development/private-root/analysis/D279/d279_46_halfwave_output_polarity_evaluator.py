#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Aggregate NBIS evaluation of the two half-wave output polarities missing in D279/44."""

from __future__ import annotations

from typing import Sequence

import d279_39_nbis_quality_evaluator as quality
import d279_42_baseline_delta_nbis_evaluator as signed_delta
import d279_44_halfwave_delta_nbis_evaluator as halfwave


WIDTH = 80
HEIGHT = 64
PIXELS = WIDTH * HEIGHT
ROLES = quality.TARGET_RASTER_ROLES
PREPROCESSORS = (
    "frame_minus_baseline_signed_control",
    "frame_above_baseline_halfwave_dark_on_white",
    "baseline_above_frame_halfwave_dark_on_white",
)


def preprocess(frame: Sequence[int], baseline: Sequence[int], method: str) -> bytearray:
    if method == "frame_minus_baseline_signed_control":
        return signed_delta.preprocess(frame, baseline, "frame_minus_baseline")
    if method == "frame_above_baseline_halfwave_dark_on_white":
        source_method = "frame_minus_baseline_halfwave"
    elif method == "baseline_above_frame_halfwave_dark_on_white":
        source_method = "baseline_minus_frame_halfwave"
    else:
        raise quality.QualityEvaluatorError("HALFWAVE_OUTPUT_POLARITY_METHOD")
    bright = halfwave.preprocess(frame, baseline, source_method)
    try:
        return bytearray(255 - value for value in bright)
    finally:
        quality.cleanse(bright)


def _variant_metadata(method: str) -> tuple[str, str]:
    if method == "frame_minus_baseline_signed_control":
        return "both", "signed_frame_minus_baseline_minmax"
    if method.startswith("frame_above"):
        return "frame_above_baseline", "retained_deviation_dark_on_white"
    return "baseline_above_frame", "retained_deviation_dark_on_white"


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
        retained_sign, output_polarity = _variant_metadata(method)
        variants.append({
            "variant": f"{method}/identity/spatial_x2",
            "baseline_preprocessing": method,
            "retained_delta_sign": retained_sign,
            "output_polarity": output_polarity,
            "intensity_scale": "post_delta_minmax",
            "orientation": "identity",
            "spatial_factor": 2,
            "groups": {
                role: quality._aggregate_group(measured[role]) for role in quality.ROLES
            },
        })
    return {
        "schema": "D279_46_HALFWAVE_OUTPUT_POLARITY_NBIS_AGGREGATE_V1",
        "hypothesis": "COMPLEMENTARY_OUTPUT_POLARITY_CAN_DISCRIMINATE_HALFWAVE_SIGN_SUPPORT_EFFECT",
        "d279_44_matrix_relation": "SIGNED_CONTROL_PLUS_TWO_PREVIOUSLY_UNMEASURED_HALFWAVE_COMPLEMENTS",
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
