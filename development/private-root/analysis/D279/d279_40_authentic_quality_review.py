#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate and summarize the authentic aggregate-only D279/39 result.

The tool has no capture, protected-material, image, template, NBIS, or USB
entry point.  It accepts only the byte-exact sanitized summary supplied after
the consumed D279/39 operator run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


EXPECTED_SOURCE_SHA256 = (
    "861bc73e743a444b4894598c34c11b20c31b5152a0f5410e6deb7febba8b677c"
)
EXPECTED_BASELINE_SHA = "4001bf07413ec09afb29db39d78fb65aa7c6f904"
EXPECTED_CAPTURE_SHA256 = (
    "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"
)
EXPECTED_OPERATION = "D279_39_ONE_OFFLINE_PROTECTED_NBIS_QUALITY_EVALUATION"
EXPECTED_ROLES = {"baseline": 1, "primary": 21, "auxiliary": 21}
EXPECTED_SCALES = ("fixed_12bit", "frame_minmax", "robust_p01_p99")
EXPECTED_FACTORS = (1, 2, 3)
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
    """The supplied result does not satisfy the D279/39 review contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def _require_exact_keys(value: dict[str, Any], keys: Iterable[str], label: str) -> None:
    require(set(value) == set(keys), f"{label}_KEYS")


def _validate_metric(metric: dict[str, Any], frames: int, label: str) -> None:
    _require_exact_keys(metric, ("frames_nonzero", "minimum", "median", "maximum"), label)
    require(all(type(metric[key]) is int for key in metric), f"{label}_TYPE")
    require(0 <= metric["frames_nonzero"] <= frames, f"{label}_FRAMES_NONZERO")
    require(
        0 <= metric["minimum"] <= metric["median"] <= metric["maximum"],
        f"{label}_RANGE",
    )
    require(
        (metric["frames_nonzero"] == 0) == (metric["maximum"] == 0),
        f"{label}_PRESENCE",
    )


def _validate_group(group: dict[str, Any], frames: int, factor: int, label: str) -> None:
    _require_exact_keys(group, ("frame_count", "metrics"), label)
    require(group["frame_count"] == frames, f"{label}_FRAME_COUNT")
    metrics = group["metrics"]
    require(type(metrics) is dict, f"{label}_METRICS_ROOT")
    _require_exact_keys(metrics, EXPECTED_METRICS, f"{label}_METRICS")
    for name, metric in metrics.items():
        require(type(metric) is dict, f"{label}_{name}_ROOT")
        _validate_metric(metric, frames, f"{label}_{name}")

    total = {1: 80, 2: 320, 3: 720}[factor]
    total_metric = metrics["quality_blocks_total"]
    require(
        total_metric == {
            "frames_nonzero": frames,
            "minimum": total,
            "median": total,
            "maximum": total,
        },
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
    require(
        summary["schema"] == "D279_39_ONE_OFFLINE_PROTECTED_NBIS_QUALITY_EVALUATION_V1",
        "SOURCE_SCHEMA",
    )
    require(summary["outcome"] == "AUTHENTIC_NBIS_QUALITY_AGGREGATE_READY", "SOURCE_OUTCOME")
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
            "schema", "resize", "nbis", "ppmm_zero_reliability_scope",
            "target_raster_role_order", "variant_count", "frame_roles",
            "per_frame_metrics_exported", "quality_maps_exported",
            "raster_exported", "template_exported", "variants",
        ),
        "AGGREGATE",
    )
    require(aggregate["schema"] == "D279_39_EXACT_NBIS_QUALITY_AGGREGATE_V1", "AGGREGATE_SCHEMA")
    require(
        aggregate["resize"] == "FEDORA44_LIBFPRINT_1_94_100_FPI_IMAGE_RESIZE_PIXMAN_BILINEAR",
        "RESIZE_PROFILE",
    )
    require(
        aggregate["nbis"] == "FEDORA44_LIBFPRINT_1_94_100_G_LFSPARMS_V2_PPMM_0_FLAGS_0",
        "NBIS_PROFILE",
    )
    require(
        aggregate["ppmm_zero_reliability_scope"]
        == "QUALITY_MAP_TIER_ONLY_NOT_PHYSICAL_GRAYSCALE_RELIABILITY",
        "PPMM_SCOPE",
    )
    require(aggregate["target_raster_role_order"] == "baseline,(primary,auxiliary)*21", "ROLE_ORDER")
    require(aggregate["frame_roles"] == EXPECTED_ROLES, "FRAME_ROLES")
    require(aggregate["variant_count"] == 9, "VARIANT_COUNT")
    require(aggregate["per_frame_metrics_exported"] is False, "PER_FRAME_EXPORT")
    require(aggregate["quality_maps_exported"] is False, "QUALITY_MAP_EXPORT")
    require(aggregate["raster_exported"] is False, "AGGREGATE_RASTER_EXPORT")
    require(aggregate["template_exported"] is False, "AGGREGATE_TEMPLATE_EXPORT")

    variants = aggregate["variants"]
    require(type(variants) is list and len(variants) == 9, "VARIANTS")
    expected_names = {
        f"{scale}/identity/normal/spatial_x{factor}"
        for scale in EXPECTED_SCALES
        for factor in EXPECTED_FACTORS
    }
    observed_names: set[str] = set()
    for index, variant in enumerate(variants):
        label = f"VARIANT_{index}"
        require(type(variant) is dict, f"{label}_ROOT")
        _require_exact_keys(
            variant,
            ("variant", "intensity_scale", "orientation", "polarity", "spatial_factor", "groups"),
            label,
        )
        require(variant["intensity_scale"] in EXPECTED_SCALES, f"{label}_SCALE")
        require(variant["orientation"] == "identity", f"{label}_ORIENTATION")
        require(variant["polarity"] == "normal", f"{label}_POLARITY")
        factor = variant["spatial_factor"]
        require(factor in EXPECTED_FACTORS, f"{label}_FACTOR")
        name = f'{variant["intensity_scale"]}/identity/normal/spatial_x{factor}'
        require(variant["variant"] == name, f"{label}_NAME")
        require(name not in observed_names, f"{label}_DUPLICATE")
        observed_names.add(name)
        groups = variant["groups"]
        require(type(groups) is dict and set(groups) == set(EXPECTED_ROLES), f"{label}_GROUPS")
        for role, frames in EXPECTED_ROLES.items():
            require(type(groups[role]) is dict, f"{label}_{role}_ROOT")
            _validate_group(groups[role], frames, factor, f"{label}_{role}")
    require(observed_names == expected_names, "VARIANT_MATRIX")
    return summary


def _variant(summary: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [item for item in summary["aggregate"]["variants"] if item["variant"] == name]
    require(len(matches) == 1, "REVIEW_VARIANT_LOOKUP")
    return matches[0]


def _compact_group(group: dict[str, Any]) -> dict[str, Any]:
    metrics = group["metrics"]
    names = (
        "minutiae_total", "minutiae_reliability_ge_025",
        "minutiae_reliability_ge_050", "quality_blocks_ab_per_mille",
        "quality_blocks_a_per_mille",
    )
    return {name: metrics[name] for name in names}


def build_review(summary: dict[str, Any]) -> dict[str, Any]:
    frame_x2 = _variant(summary, "frame_minmax/identity/normal/spatial_x2")
    frame_x3 = _variant(summary, "frame_minmax/identity/normal/spatial_x3")
    robust_x2 = _variant(summary, "robust_p01_p99/identity/normal/spatial_x2")
    return {
        "schema": "D279_40_AUTHENTIC_NBIS_QUALITY_REVIEW_V1",
        "source_summary_sha256": EXPECTED_SOURCE_SHA256,
        "baseline_sha": summary["baseline_sha"],
        "capture_sha256": summary["capture_sha256"],
        "source_contract_valid": True,
        "aggregate_contract_valid": True,
        "privacy_contract_valid": True,
        "correct_role_order_valid": True,
        "live_or_usb_action_count": 0,
        "frame_minmax_x2": {
            role: _compact_group(frame_x2["groups"][role]) for role in EXPECTED_ROLES
        },
        "frame_minmax_x3": {
            role: _compact_group(frame_x3["groups"][role]) for role in EXPECTED_ROLES
        },
        "robust_x2_baseline": _compact_group(robust_x2["groups"]["baseline"]),
        "frame_minmax_x2_quality_ab_discriminates_baseline_in_this_capture": (
            frame_x2["groups"]["baseline"]["metrics"]["quality_blocks_ab"]["maximum"] == 0
            and frame_x2["groups"]["primary"]["metrics"]["quality_blocks_ab"]["frames_nonzero"] == 21
            and frame_x2["groups"]["auxiliary"]["metrics"]["quality_blocks_ab"]["frames_nonzero"] == 20
        ),
        "frame_minmax_x2_all_fingerprint_maxima_below_10_minutiae": all(
            frame_x2["groups"][role]["metrics"]["minutiae_total"]["maximum"] < 10
            for role in ("primary", "auxiliary")
        ),
        "frame_minmax_x2_no_a_tier_minutiae": all(
            frame_x2["groups"][role]["metrics"]["minutiae_reliability_ge_050"]["maximum"] == 0
            for role in ("primary", "auxiliary")
        ),
        "interpretation": {
            "quality_ab": "BLOCK_LEVEL_DIRECTION_CONTRAST_SUPPORT_NOT_MINUTIA_DENSITY_OR_MATCHABILITY",
            "reliability_ge_025_at_ppmm_zero": "MINUTIA_LOCATED_IN_QUALITY_TIER_B_OR_A",
            "reliability_ge_050_at_ppmm_zero": "MINUTIA_LOCATED_IN_QUALITY_TIER_A",
            "physical_grayscale_reliability": "NOT_MEASURED_WITH_PPMM_ZERO",
            "production_preprocessing_decision": "NOT_AUTHORIZED_BY_THIS_RESULT",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    review = build_review(load_authentic_summary(args.source))
    print(json.dumps(review, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
