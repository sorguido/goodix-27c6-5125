#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Metadata-only audit of ATTEMPT02 TLS application-record role ordering."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
D10_PATH = Path(__file__).with_name("d279_10_attempt02_full_enrollment_audit.py")
D31_PATH = Path(__file__).with_name(
    "d279_31_attempt02_tls_reconstruction_feasibility.py"
)


class RoleOrderAuditError(RuntimeError):
    """The observed metadata does not match the bounded target profile."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RoleOrderAuditError(message)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"{name}_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def classify_roles(
    fingerprint_b0_frames: Sequence[int], primary_b0_frames: Sequence[int]
) -> tuple[str, ...]:
    """Classify the exact 1 + 21 paired records from wire-visible metadata."""

    require(len(fingerprint_b0_frames) == 43, "FINGERPRINT_B0_COUNT")
    require(len(primary_b0_frames) == 21, "PRIMARY_B0_COUNT")
    require(len(set(fingerprint_b0_frames)) == 43, "FINGERPRINT_B0_UNIQUE")
    require(tuple(fingerprint_b0_frames) == tuple(sorted(fingerprint_b0_frames)),
            "FINGERPRINT_B0_CAPTURE_ORDER")
    primary = set(primary_b0_frames)
    require(len(primary) == 21, "PRIMARY_B0_UNIQUE")
    require(primary.issubset(fingerprint_b0_frames), "PRIMARY_NOT_FINGERPRINT_B0")
    require(fingerprint_b0_frames[0] not in primary, "BASELINE_IS_PRIMARY")

    roles = ["baseline"]
    for cycle in range(21):
        primary_frame = fingerprint_b0_frames[1 + cycle * 2]
        auxiliary_frame = fingerprint_b0_frames[2 + cycle * 2]
        require(primary_frame in primary, f"CYCLE_{cycle + 1}_PRIMARY_ORDER")
        require(auxiliary_frame not in primary, f"CYCLE_{cycle + 1}_AUXILIARY_ORDER")
        roles.extend(("primary", "auxiliary"))
    require(primary == {
        fingerprint_b0_frames[1 + cycle * 2] for cycle in range(21)
    }, "PRIMARY_SET_MISMATCH")
    return tuple(roles)


def analyze() -> dict:
    d10 = _load_module("d279_38_d10", D10_PATH)
    d31 = _load_module("d279_38_d31", D31_PATH)
    enrollment = d10.analyze()
    tls = d31.analyze()
    require(enrollment["capture_sha256"] == tls["capture_sha256"],
            "CAPTURE_IDENTITY_MISMATCH")

    packets = d10.D274.parse_usbpcap_bytes(
        (d10.ATTEMPT / "raw" / "wire.pcapng").read_bytes()
    )
    frames, firmware_ok = d10.D274._target_frames(
        packets, include_incomplete=False
    )
    require(firmware_ok, "APP12509_NOT_OBSERVED")
    fingerprint_b0_frames = tuple(
        frame.packet_index
        for frame in frames
        if frame.outer == 0xB0
        and d10.D274.classify_b0(frame) == "FINGERPRINT_B0"
    )
    primary_b0_frames = tuple(
        row["primary_b0_frame"]
        for row in enrollment["cycle_shapes"]["primary_cycle_rows"]
    )
    roles = classify_roles(fingerprint_b0_frames, primary_b0_frames)

    old_first_group = roles[1:22]
    old_second_group = roles[22:43]
    return {
        "schema": "D279_38_TARGET_ROLE_ORDER_AUDIT_V1",
        "capture_sha256": enrollment["capture_sha256"],
        "target_firmware": tls["target_firmware"],
        "evidence": {
            "tls_application_to_fingerprint_b0_identity": True,
            "fingerprint_b0_count": len(fingerprint_b0_frames),
            "primary_b0_count": len(primary_b0_frames),
            "baseline_b0_count": 1,
            "auxiliary_b0_count": roles.count("auxiliary"),
            "all_21_primary_auxiliary_pairs_alternate": True,
        },
        "correct_application_sequence_roles": {
            "sequence_1": "baseline",
            "sequence_2n_for_n_1_through_21": "primary",
            "sequence_2n_plus_1_for_n_1_through_21": "auxiliary",
            "raster_role_pattern": "baseline,(primary,auxiliary)*21",
        },
        "superseded_contiguous_partition": {
            "old_primary_labeled_records": {
                "actual_primary": old_first_group.count("primary"),
                "actual_auxiliary": old_first_group.count("auxiliary"),
            },
            "old_auxiliary_labeled_records": {
                "actual_primary": old_second_group.count("primary"),
                "actual_auxiliary": old_second_group.count("auxiliary"),
            },
            "role_specific_d279_35_and_d279_37_aggregates_valid": False,
            "all_42_fingerprint_records_partition_valid": True,
        },
        "privacy": {
            "capture_payload_exported": False,
            "plaintext_or_raster_accessed": False,
            "secret_accessed": False,
            "biometric_metric_computed": False,
        },
        "live_or_usb_action_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze()
    document = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(document, end="")
    else:
        args.output.write_text(document, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
