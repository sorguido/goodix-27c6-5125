#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed schema/privacy validator for a D279/48 authentic summary."""

from __future__ import annotations

import json
import sys
from pathlib import Path


class SummaryValidationError(ValueError):
    pass


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SummaryValidationError(label)


def validate(document: dict, approved: str) -> None:
    require(set(document) == {
        "schema", "outcome", "baseline_sha", "operation", "capture_sha256",
        "r0_summary_sha256", "transport_input_verified", "transport_or_psk_exported",
        "plaintext_or_raster_exported", "biometric_feature_or_template_exported",
        "live_or_usb_action_count", "aggregate",
    }, "TOP_LEVEL_KEYS")
    require(document["schema"] == "D279_48_ONE_OFFLINE_PROTECTED_ROCKY_NBIS_SIGFM_COMPARISON_V1", "SCHEMA")
    require(document["outcome"] == "AUTHENTIC_ROCKY_NBIS_SIGFM_AGGREGATE_READY", "OUTCOME")
    require(document["baseline_sha"] == approved, "BASELINE")
    require(document["operation"] == "D279_48_ONE_OFFLINE_PROTECTED_ROCKY_NBIS_SIGFM_COMPARISON", "OPERATION")
    require(document["capture_sha256"] == "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab", "CAPTURE_HASH")
    require(document["r0_summary_sha256"] == "7dfb2feab05a11b01830903c773211d811f5b9a55aac35bd478fd57e4707f90b", "R0_HASH")
    require(document["transport_input_verified"] is True, "TRANSPORT_VERIFIED")
    require(document["transport_or_psk_exported"] is False, "TRANSPORT_PRIVACY")
    require(document["plaintext_or_raster_exported"] is False, "RASTER_PRIVACY")
    require(document["biometric_feature_or_template_exported"] is False, "FEATURE_PRIVACY")
    require(document["live_or_usb_action_count"] == 0, "USB_COUNT")

    aggregate = document["aggregate"]
    require(aggregate["schema"] == "D279_48_ROCKY_NBIS_SIGFM_COMPARISON_AGGREGATE_V1", "AGGREGATE_SCHEMA")
    require(aggregate["target_raster_role_order"] == "baseline,(primary,auxiliary)*21", "ROLE_ORDER")
    require(aggregate["frame_roles"] == {"baseline": 1, "primary": 21, "auxiliary": 21}, "ROLE_COUNTS")
    require(aggregate["checkpoint_count"] == 2, "CHECKPOINT_COUNT")
    require(aggregate["decision_classification"] == "PENDING_AUTHENTIC_AGGREGATE_REVIEW_A_B_C_OR_D", "DECISION_PENDING")
    require(aggregate["historical_r0"]["source_summary_sha256"] == document["r0_summary_sha256"], "R0_BINDING")
    require(aggregate["dataset_limitations"] == {
        "single_session_finger_context_only": True,
        "different_finger_control_available": False,
        "far_frr_or_accuracy_claim_permitted": False,
        "production_threshold_validation_permitted": False,
    }, "DATASET_LIMITS")
    for key in (
        "per_frame_metrics_exported", "rasters_exported", "minutiae_exported",
        "sigfm_keypoints_or_descriptors_exported", "templates_exported",
    ):
        require(aggregate[key] is False, f"PRIVACY_{key}")
    checkpoints = aggregate["checkpoints"]
    require({item["checkpoint"] for item in checkpoints} == {
        "R1_ROCKY_COMMON_NATIVE_80X64", "R2_ROCKY_SIGFM_CHAIN_NATIVE_80X64",
    }, "CHECKPOINT_IDENTITIES")
    expected_pairs = {
        "paired_cycle_primary_to_auxiliary": 21,
        "within_primary": 210,
        "within_auxiliary": 210,
        "all_cross_role_primary_to_auxiliary": 441,
    }
    for checkpoint in checkpoints:
        require(checkpoint["native_shape"] == "80x64", "NATIVE_SHAPE")
        require(checkpoint["resize_applied"] is False, "NO_RESIZE")
        require(checkpoint["same_preprocessed_raster_delivered_to_both_extractors"] is True,
                "SAME_INPUT")
        for extractor in ("nbis", "sigfm"):
            pairs = checkpoint[extractor]["same_session_pairs"]
            require(set(pairs) == set(expected_pairs), f"{extractor}_PAIR_SETS")
            for name, logical_count in expected_pairs.items():
                value = pairs[name]
                require(value["logical_pair_count"] == logical_count, f"{extractor}_{name}_LOGICAL")
                require(value["directed_score_count"] == logical_count * 2, f"{extractor}_{name}_DIRECTED")
                require(value["all_pair_scores"]["count"] == logical_count * 2,
                        f"{extractor}_{name}_DISTRIBUTION")


def main() -> int:
    document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    validate(document, sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
