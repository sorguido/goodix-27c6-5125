#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed validator for the D279/56 aggregate-only result."""

import json
import sys
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(path: Path, baseline: str) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(set(value) == {
        "schema", "outcome", "baseline_sha", "operation", "capture_sha256",
        "authority_source_sha256", "rockytkg_policy_source_sha256",
        "transport_input_verified", "transport_or_psk_exported",
        "plaintext_or_raster_exported",
        "biometric_feature_or_template_exported", "live_or_usb_action_count",
        "aggregate",
    }, "TOP_LEVEL_FIELDS")
    require(value["schema"] == "D279_56_AUTHENTIC_DYNAMIC_ENROLLMENT_AGGREGATE_V1",
            "SCHEMA")
    require(value["outcome"] == "AUTHENTIC_DYNAMIC_POLICY_AGGREGATE_READY",
            "OUTCOME")
    require(value["baseline_sha"] == baseline, "BASELINE")
    require(value["transport_input_verified"] is True, "TRANSPORT")
    require(value["transport_or_psk_exported"] is False, "SECRET_EXPORT")
    require(value["plaintext_or_raster_exported"] is False, "RASTER_EXPORT")
    require(value["biometric_feature_or_template_exported"] is False,
            "FEATURE_EXPORT")
    require(value["live_or_usb_action_count"] == 0, "LIVE_USB")
    aggregate = value["aggregate"]
    require(set(aggregate) == {
        "schema", "policy", "input_primary_stage_count",
        "evaluated_stage_count", "distinct_sample_accept_count",
        "first_possible_convergence_stage", "final_selected_stage_count",
        "duplicate_reject_count", "max_stage_reached", "terminal_reason",
        "per_stage", "numeric_per_stage_mad_exported",
        "raster_or_biometric_feature_exported", "target_raster_role_order",
        "preprocessing", "baseline_semantics", "auxiliary_rasters_used",
        "dataset_single_session_same_finger", "production_policy_validated",
    }, "AGGREGATE_FIELDS")
    require(aggregate["schema"] ==
            "D279_56_ROCKYTKG_DYNAMIC_ENROLLMENT_REPLAY_V1", "AGGREGATE_SCHEMA")
    require(aggregate["input_primary_stage_count"] == 21, "INPUT_COUNT")
    require(aggregate["policy"] == {
        "minimum_distinct_samples": 3,
        "maximum_delivered_stages": 8,
        "duplicate_streak_to_converge": 2,
        "mad_duplicate_threshold": "8.0_EXCLUSIVE",
    }, "POLICY")
    require(1 <= aggregate["evaluated_stage_count"] <= 21, "EVALUATED_COUNT")
    require(0 <= aggregate["distinct_sample_accept_count"] <= 8,
            "DISTINCT_COUNT")
    require(aggregate["final_selected_stage_count"] is None or
            4 <= aggregate["final_selected_stage_count"] <= 8,
            "FINAL_COUNT")
    require(aggregate["terminal_reason"] in {
        "DUPLICATE_STREAK_CONVERGENCE", "MAX_STAGE_REACHED",
        "INPUT_EXHAUSTED_WITHOUT_COMPLETION",
    }, "TERMINAL_REASON")
    per_stage = aggregate["per_stage"]
    require(len(per_stage) == aggregate["evaluated_stage_count"],
            "PER_STAGE_COUNT")
    for index, item in enumerate(per_stage, start=1):
        require(set(item) == {"stage_index", "classification"},
                "PER_STAGE_FIELDS")
        require(item["stage_index"] == index, "PER_STAGE_INDEX")
        require(item["classification"] in {"ACCEPT", "DUPLICATE", "CONVERGE"},
                "PER_STAGE_CLASS")
    require(aggregate["numeric_per_stage_mad_exported"] is False,
            "NUMERIC_MAD_EXPORT")
    require(aggregate["raster_or_biometric_feature_exported"] is False,
            "AGGREGATE_RASTER_EXPORT")
    require(aggregate["auxiliary_rasters_used"] is False, "AUXILIARY_USAGE")
    require(aggregate["production_policy_validated"] is False,
            "PRODUCTION_CLAIM")


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 3, "USAGE")
        validate(Path(sys.argv[1]), sys.argv[2])
        print("D279_56_AGGREGATE_VALIDATION=PASS")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"D279_56_AGGREGATE_VALIDATION=FAIL:{type(error).__name__}:{error}",
              file=sys.stderr)
        raise SystemExit(3)
