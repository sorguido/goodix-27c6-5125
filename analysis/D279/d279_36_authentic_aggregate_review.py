#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate and summarize the authentic D279/35 aggregate-only result.

This tool accepts only the already-sanitized JSON produced by D279/35.  It has
no protected-material, capture, USB, image, template, or NBIS execution path.
The exact source digest is part of the input contract so that a different
result cannot silently enter the canonical review set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable


EXPECTED_SOURCE_SHA256 = (
    "5010f695f539b60b1f03e63d0bcbd6b60d57c06607f9a6340216cf7518cb7d04"
)
EXPECTED_BASELINE_SHA = "5b2cb03b04e68225134316fb049712830f7ff9f8"
EXPECTED_CAPTURE_SHA256 = (
    "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"
)
EXPECTED_OPERATION = "D279_35_ONE_OFFLINE_PROTECTED_EVALUATION"
EXPECTED_ROLES = {"baseline": 1, "primary": 21, "auxiliary": 21}
EXPECTED_SCALES = ("fixed_12bit", "frame_minmax", "robust_p01_p99")
EXPECTED_ORIENTATIONS = (
    "identity",
    "hflip",
    "vflip",
    "rot180",
    "transpose",
    "transpose_hflip",
    "transpose_vflip",
    "transpose_rot180",
)
EXPECTED_POLARITIES = ("normal", "inverted")


class ReviewError(RuntimeError):
    """The supplied result does not satisfy the D279/35 review contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_exact_keys(value: dict[str, Any], keys: Iterable[str], label: str) -> None:
    require(set(value) == set(keys), f"{label}_KEYS")


def _validate_group(group: dict[str, Any], expected_frames: int, label: str) -> None:
    _require_exact_keys(
        group,
        (
            "frame_count",
            "frames_with_minutiae",
            "frames_with_at_least_10_minutiae",
            "minimum",
            "median",
            "maximum",
        ),
        label,
    )
    require(group["frame_count"] == expected_frames, f"{label}_FRAME_COUNT")
    for key in (
        "frame_count",
        "frames_with_minutiae",
        "frames_with_at_least_10_minutiae",
        "minimum",
        "maximum",
    ):
        require(type(group[key]) is int and group[key] >= 0, f"{label}_{key}_TYPE")
    require(
        type(group["median"]) in (int, float) and group["median"] >= 0,
        f"{label}_MEDIAN_TYPE",
    )
    require(
        group["frames_with_at_least_10_minutiae"]
        <= group["frames_with_minutiae"]
        <= expected_frames,
        f"{label}_PRESENCE_ORDER",
    )
    require(
        group["minimum"] <= group["median"] <= group["maximum"],
        f"{label}_RANGE_ORDER",
    )
    require(
        (group["frames_with_minutiae"] == 0) == (group["maximum"] == 0),
        f"{label}_PRESENCE_MAXIMUM",
    )
    require(
        (group["frames_with_at_least_10_minutiae"] == 0)
        == (group["maximum"] < 10),
        f"{label}_THRESHOLD_MAXIMUM",
    )


def load_authentic_summary(source: Path) -> tuple[bytes, dict[str, Any]]:
    payload = source.read_bytes()
    require(_sha256(payload) == EXPECTED_SOURCE_SHA256, "SOURCE_SHA256")
    try:
        summary = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ReviewError("SOURCE_JSON") from error
    require(type(summary) is dict, "SOURCE_ROOT")
    _require_exact_keys(
        summary,
        (
            "schema",
            "outcome",
            "baseline_sha",
            "operation",
            "capture_sha256",
            "transport_input_verified",
            "transport_or_psk_exported",
            "plaintext_or_raster_exported",
            "template_exported",
            "live_or_usb_action_count",
            "aggregate",
        ),
        "SOURCE",
    )
    require(
        summary["schema"] == "D279_35_ONE_OFFLINE_PROTECTED_EVALUATION_V1",
        "SOURCE_SCHEMA",
    )
    require(summary["outcome"] == "AUTHENTIC_AGGREGATE_READY", "SOURCE_OUTCOME")
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
            "schema",
            "nbis",
            "variant_count",
            "frame_roles",
            "per_frame_counts_exported",
            "raster_exported",
            "template_exported",
            "variants",
        ),
        "AGGREGATE",
    )
    require(aggregate["schema"] == "D279_34_EXACT_NBIS_AGGREGATE_V1", "AGGREGATE_SCHEMA")
    require(
        aggregate["nbis"]
        == "FEDORA44_LIBFPRINT_1_94_100_G_LFSPARMS_V2_PPMM_0_FLAGS_0",
        "NBIS_PROFILE",
    )
    require(aggregate["variant_count"] == 48, "VARIANT_COUNT")
    require(aggregate["frame_roles"] == EXPECTED_ROLES, "FRAME_ROLES")
    require(aggregate["per_frame_counts_exported"] is False, "PER_FRAME_EXPORT")
    require(aggregate["raster_exported"] is False, "AGGREGATE_RASTER_EXPORT")
    require(aggregate["template_exported"] is False, "AGGREGATE_TEMPLATE_EXPORT")

    variants = aggregate["variants"]
    require(type(variants) is list and len(variants) == 48, "VARIANTS")
    expected_names = {
        f"{scale}/{orientation}/{polarity}"
        for scale in EXPECTED_SCALES
        for orientation in EXPECTED_ORIENTATIONS
        for polarity in EXPECTED_POLARITIES
    }
    observed_names: set[str] = set()
    for index, variant in enumerate(variants):
        label = f"VARIANT_{index}"
        require(type(variant) is dict, f"{label}_ROOT")
        _require_exact_keys(
            variant, ("variant", "scale", "orientation", "polarity", "groups"), label
        )
        require(variant["scale"] in EXPECTED_SCALES, f"{label}_SCALE")
        require(variant["orientation"] in EXPECTED_ORIENTATIONS, f"{label}_ORIENTATION")
        require(variant["polarity"] in EXPECTED_POLARITIES, f"{label}_POLARITY")
        expected_name = f'{variant["scale"]}/{variant["orientation"]}/{variant["polarity"]}'
        require(variant["variant"] == expected_name, f"{label}_NAME")
        require(expected_name not in observed_names, f"{label}_DUPLICATE")
        observed_names.add(expected_name)
        groups = variant["groups"]
        require(type(groups) is dict and set(groups) == set(EXPECTED_ROLES), f"{label}_GROUPS")
        for role, frame_count in EXPECTED_ROLES.items():
            require(type(groups[role]) is dict, f"{label}_{role}_ROOT")
            _validate_group(groups[role], frame_count, f"{label}_{role}")
    require(observed_names == expected_names, "VARIANT_MATRIX")
    return payload, summary


def _marginal(variants: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    values = sorted({variant[dimension] for variant in variants})
    result = []
    for value in values:
        selected = [variant for variant in variants if variant[dimension] == value]
        result.append(
            {
                dimension: value,
                "variant_count": len(selected),
                "primary_best_frames_with_minutiae": max(
                    variant["groups"]["primary"]["frames_with_minutiae"]
                    for variant in selected
                ),
                "primary_best_maximum": max(
                    variant["groups"]["primary"]["maximum"] for variant in selected
                ),
                "auxiliary_best_frames_with_minutiae": max(
                    variant["groups"]["auxiliary"]["frames_with_minutiae"]
                    for variant in selected
                ),
                "auxiliary_best_maximum": max(
                    variant["groups"]["auxiliary"]["maximum"] for variant in selected
                ),
                "baseline_best_maximum": max(
                    variant["groups"]["baseline"]["maximum"] for variant in selected
                ),
            }
        )
    return result


def build_review(summary: dict[str, Any]) -> dict[str, Any]:
    variants = summary["aggregate"]["variants"]
    best_primary = max(
        variants,
        key=lambda variant: (
            variant["groups"]["primary"]["maximum"],
            variant["groups"]["primary"]["frames_with_minutiae"],
            variant["variant"],
        ),
    )
    best_auxiliary = max(
        variants,
        key=lambda variant: (
            variant["groups"]["auxiliary"]["frames_with_minutiae"],
            variant["groups"]["auxiliary"]["maximum"],
            variant["variant"],
        ),
    )
    baseline_nonzero = [
        variant for variant in variants if variant["groups"]["baseline"]["maximum"] > 0
    ]
    return {
        "schema": "D279_36_AUTHENTIC_AGGREGATE_REVIEW_V1",
        "source_summary_sha256": EXPECTED_SOURCE_SHA256,
        "baseline_sha": summary["baseline_sha"],
        "capture_sha256": summary["capture_sha256"],
        "source_contract_valid": True,
        "aggregate_contract_valid": True,
        "privacy_contract_valid": True,
        "live_or_usb_action_count": 0,
        "variant_count": len(variants),
        "frame_roles": summary["aggregate"]["frame_roles"],
        "all_variants_zero_frames_at_or_above_10": all(
            variant["groups"][role]["frames_with_at_least_10_minutiae"] == 0
            for variant in variants
            for role in EXPECTED_ROLES
        ),
        "best_primary": {
            "variant": best_primary["variant"],
            **best_primary["groups"]["primary"],
        },
        "best_auxiliary_by_presence": {
            "variant": best_auxiliary["variant"],
            **best_auxiliary["groups"]["auxiliary"],
        },
        "baseline_nonzero_variant_count": len(baseline_nonzero),
        "baseline_best_maximum": max(
            variant["groups"]["baseline"]["maximum"] for variant in variants
        ),
        "marginals": {
            "scale": _marginal(variants, "scale"),
            "orientation": _marginal(variants, "orientation"),
            "polarity": _marginal(variants, "polarity"),
        },
    }


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--preserve-exact", type=Path)
    parser.add_argument("--review-output", type=Path)
    args = parser.parse_args()

    source_payload, summary = load_authentic_summary(args.source)
    review = build_review(summary)
    review_payload = (json.dumps(review, indent=2, sort_keys=True) + "\n").encode()
    if args.preserve_exact is not None:
        _write_new(args.preserve_exact, source_payload)
    if args.review_output is not None:
        _write_new(args.review_output, review_payload)
    if args.review_output is None:
        print(review_payload.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
