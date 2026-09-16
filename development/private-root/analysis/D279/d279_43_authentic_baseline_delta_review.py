#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate and summarize the authentic aggregate-only D279/42 result."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


EXPECTED_SOURCE_SHA256 = "0fc29eb7ece380e548b3cdc2caa995564a15c4e062bce4e83677c6367ee6ffb3"
EXPECTED_BASELINE_SHA = "cf7ecb6c4df7f053e4a8f4203e6a6262b12e35f2"
EXPECTED_CAPTURE_SHA256 = "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"
EXPECTED_OPERATION = "D279_42_ONE_OFFLINE_PROTECTED_BASELINE_DELTA_EVALUATION"
EXPECTED_ROLES = {"baseline": 1, "primary": 21, "auxiliary": 21}
EXPECTED_PREPROCESSORS = (
    "frame_minmax_control",
    "frame_minus_baseline",
    "baseline_minus_frame",
)
EXPECTED_METRICS = (
    "minutiae_total",
    "minutiae_reliability_ge_025",
    "minutiae_reliability_ge_050",
    "quality_blocks_total",
    "quality_blocks_level_0",
    "quality_blocks_level_1",
    "quality_blocks_level_2",
    "quality_blocks_level_3",
    "quality_blocks_level_4",
    "quality_blocks_ab",
    "quality_blocks_a",
    "quality_blocks_ab_per_mille",
    "quality_blocks_a_per_mille",
    "minutiae_ab_fraction_per_mille",
    "minutiae_a_fraction_per_mille",
)


class ReviewError(RuntimeError):
    """The supplied result does not satisfy the D279/42 review contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def _require_exact_keys(value: dict[str, Any], keys: Iterable[str], label: str) -> None:
    require(set(value) == set(keys), f"{label}_KEYS")


def _validate_metric(metric: dict[str, Any], frames: int, label: str) -> None:
    _require_exact_keys(metric, ("frames_nonzero", "minimum", "median", "maximum"), label)
    require(all(type(metric[key]) is int for key in metric), f"{label}_TYPE")
    require(0 <= metric["frames_nonzero"] <= frames, f"{label}_FRAMES_NONZERO")
    require(0 <= metric["minimum"] <= metric["median"] <= metric["maximum"], f"{label}_RANGE")
    require((metric["frames_nonzero"] == 0) == (metric["maximum"] == 0), f"{label}_PRESENCE")


def _validate_group(group: dict[str, Any], frames: int, label: str) -> None:
    _require_exact_keys(group, ("frame_count", "metrics"), label)
    require(group["frame_count"] == frames, f"{label}_FRAME_COUNT")
    metrics = group["metrics"]
    require(type(metrics) is dict, f"{label}_METRICS_ROOT")
    _require_exact_keys(metrics, EXPECTED_METRICS, f"{label}_METRICS")
    for name, metric in metrics.items():
        require(type(metric) is dict, f"{label}_{name}_ROOT")
        _validate_metric(metric, frames, f"{label}_{name}")
    require(
        metrics["quality_blocks_total"]
        == {"frames_nonzero": frames, "minimum": 320, "median": 320, "maximum": 320},
        f"{label}_QUALITY_TOTAL",
    )
    for name in (
        "quality_blocks_ab_per_mille",
        "quality_blocks_a_per_mille",
        "minutiae_ab_fraction_per_mille",
        "minutiae_a_fraction_per_mille",
    ):
        require(metrics[name]["maximum"] <= 1000, f"{label}_{name}_BOUND")
    require(
        metrics["minutiae_reliability_ge_050"]["frames_nonzero"]
        <= metrics["minutiae_reliability_ge_025"]["frames_nonzero"]
        <= metrics["minutiae_total"]["frames_nonzero"],
        f"{label}_RELIABILITY_PRESENCE_ORDER",
    )
    require(
        metrics["minutiae_reliability_ge_050"]["maximum"]
        <= metrics["minutiae_reliability_ge_025"]["maximum"]
        <= metrics["minutiae_total"]["maximum"],
        f"{label}_RELIABILITY_MAXIMUM_ORDER",
    )


def load_authentic_summary(source: Path) -> dict[str, Any]:
    payload = source.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == EXPECTED_SOURCE_SHA256, "SOURCE_SHA256")
    try:
        summary = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ReviewError("SOURCE_JSON") from error
    require(type(summary) is dict, "SOURCE_ROOT")
    _require_exact_keys(
        summary,
        (
            "schema", "outcome", "baseline_sha", "operation", "capture_sha256",
            "transport_input_verified", "transport_or_psk_exported",
            "plaintext_or_raster_exported", "template_exported",
            "live_or_usb_action_count", "aggregate",
        ),
        "SOURCE",
    )
    require(summary["schema"] == "D279_42_ONE_OFFLINE_PROTECTED_BASELINE_DELTA_EVALUATION_V1", "SOURCE_SCHEMA")
    require(summary["outcome"] == "AUTHENTIC_BASELINE_DELTA_NBIS_AGGREGATE_READY", "SOURCE_OUTCOME")
    require(summary["baseline_sha"] == EXPECTED_BASELINE_SHA, "BASELINE_SHA")
    require(summary["operation"] == EXPECTED_OPERATION, "OPERATION")
    require(summary["capture_sha256"] == EXPECTED_CAPTURE_SHA256, "CAPTURE_SHA256")
    require(summary["transport_input_verified"] is True, "TRANSPORT_VERIFIED")
    require(summary["transport_or_psk_exported"] is False, "TRANSPORT_EXPORT")
    require(summary["plaintext_or_raster_exported"] is False, "RASTER_EXPORT")
    require(summary["template_exported"] is False, "TEMPLATE_EXPORT")
    require(summary["live_or_usb_action_count"] == 0, "LIVE_OR_USB_COUNT")

    aggregate = summary["aggregate"]
    require(type(aggregate) is dict, "AGGREGATE_ROOT")
    _require_exact_keys(
        aggregate,
        (
            "schema", "hypothesis", "ppmm_zero_reliability_scope",
            "target_raster_role_order", "frame_roles", "variant_count",
            "per_frame_metrics_exported", "quality_maps_exported",
            "raster_exported", "template_exported", "variants",
        ),
        "AGGREGATE",
    )
    require(aggregate["schema"] == "D279_42_BASELINE_DELTA_NBIS_AGGREGATE_V1", "AGGREGATE_SCHEMA")
    require(
        aggregate["hypothesis"]
        == "PER_PIXEL_NO_FINGER_BASELINE_DELTA_REMOVES_FIXED_FIELD_BEFORE_MINMAX_X2",
        "HYPOTHESIS",
    )
    require(
        aggregate["ppmm_zero_reliability_scope"]
        == "QUALITY_MAP_TIER_ONLY_NOT_PHYSICAL_GRAYSCALE_RELIABILITY",
        "PPMM_SCOPE",
    )
    require(aggregate["target_raster_role_order"] == "baseline,(primary,auxiliary)*21", "ROLE_ORDER")
    require(aggregate["frame_roles"] == EXPECTED_ROLES, "FRAME_ROLES")
    require(aggregate["variant_count"] == 3, "VARIANT_COUNT")
    require(aggregate["per_frame_metrics_exported"] is False, "PER_FRAME_EXPORT")
    require(aggregate["quality_maps_exported"] is False, "QUALITY_MAP_EXPORT")
    require(aggregate["raster_exported"] is False, "AGGREGATE_RASTER_EXPORT")
    require(aggregate["template_exported"] is False, "AGGREGATE_TEMPLATE_EXPORT")

    variants = aggregate["variants"]
    require(type(variants) is list and len(variants) == 3, "VARIANTS")
    observed: set[str] = set()
    for index, variant in enumerate(variants):
        label = f"VARIANT_{index}"
        require(type(variant) is dict, f"{label}_ROOT")
        _require_exact_keys(
            variant,
            (
                "variant", "baseline_preprocessing", "intensity_scale",
                "orientation", "polarity", "spatial_factor", "groups",
            ),
            label,
        )
        method = variant["baseline_preprocessing"]
        require(method in EXPECTED_PREPROCESSORS, f"{label}_METHOD")
        require(method not in observed, f"{label}_DUPLICATE")
        observed.add(method)
        require(variant["variant"] == f"{method}/identity/normal/spatial_x2", f"{label}_NAME")
        require(variant["intensity_scale"] == "frame_minmax", f"{label}_SCALE")
        require(variant["orientation"] == "identity", f"{label}_ORIENTATION")
        expected_polarity = "delta_inverted" if method == "baseline_minus_frame" else "normal"
        require(variant["polarity"] == expected_polarity, f"{label}_POLARITY")
        require(variant["spatial_factor"] == 2, f"{label}_FACTOR")
        groups = variant["groups"]
        require(type(groups) is dict and set(groups) == set(EXPECTED_ROLES), f"{label}_GROUPS")
        for role, frames in EXPECTED_ROLES.items():
            _validate_group(groups[role], frames, f"{label}_{role}")
    require(observed == set(EXPECTED_PREPROCESSORS), "VARIANT_MATRIX")
    return summary


def _variant(summary: dict[str, Any], method: str) -> dict[str, Any]:
    matches = [
        item for item in summary["aggregate"]["variants"]
        if item["baseline_preprocessing"] == method
    ]
    require(len(matches) == 1, "REVIEW_VARIANT_LOOKUP")
    return matches[0]


def _fingerprint_frames_nonzero(variant: dict[str, Any], metric: str) -> int:
    return sum(variant["groups"][role]["metrics"][metric]["frames_nonzero"] for role in ("primary", "auxiliary"))


def build_review(summary: dict[str, Any]) -> dict[str, Any]:
    control = _variant(summary, "frame_minmax_control")
    forward = _variant(summary, "frame_minus_baseline")
    inverse = _variant(summary, "baseline_minus_frame")
    return {
        "schema": "D279_43_AUTHENTIC_BASELINE_DELTA_REVIEW_V1",
        "source_summary_sha256": EXPECTED_SOURCE_SHA256,
        "baseline_sha": summary["baseline_sha"],
        "capture_sha256": summary["capture_sha256"],
        "source_contract_valid": True,
        "aggregate_contract_valid": True,
        "privacy_contract_valid": True,
        "correct_role_order_valid": True,
        "live_or_usb_action_count": 0,
        "fingerprint_frames_with_minutiae_in_quality_tier_b_or_a": {
            "frame_minmax_control": _fingerprint_frames_nonzero(control, "minutiae_reliability_ge_025"),
            "frame_minus_baseline": _fingerprint_frames_nonzero(forward, "minutiae_reliability_ge_025"),
            "baseline_minus_frame": _fingerprint_frames_nonzero(inverse, "minutiae_reliability_ge_025"),
        },
        "fingerprint_frames_with_minutiae_in_quality_tier_a": {
            "frame_minmax_control": _fingerprint_frames_nonzero(control, "minutiae_reliability_ge_050"),
            "frame_minus_baseline": _fingerprint_frames_nonzero(forward, "minutiae_reliability_ge_050"),
            "baseline_minus_frame": _fingerprint_frames_nonzero(inverse, "minutiae_reliability_ge_050"),
        },
        "interpretation": {
            "baseline_subtraction_signal": "POSITIVE_BUT_INSUFFICIENT_FOR_ENROLLMENT_OR_PRODUCTION",
            "signed_polarity_variants": "COMPLEMENTARY_IMAGES_NOT_INDEPENDENT_FIXED_FIELD_REPLICATIONS",
            "self_subtracted_baseline": "CONSTRUCTED_ZERO_NOT_INDEPENDENT_DISCRIMINATOR",
            "frame_minus_baseline": "SLIGHT_EXPERIMENTAL_PREFERENCE_ONLY",
            "next_minimal_hypothesis": "POLARITY_SPECIFIC_HALF_WAVE_RECTIFICATION_BEFORE_MINMAX_X2",
            "production_preprocessing_decision": "NOT_AUTHORIZED_BY_THIS_RESULT",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_review(load_authentic_summary(args.source)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
