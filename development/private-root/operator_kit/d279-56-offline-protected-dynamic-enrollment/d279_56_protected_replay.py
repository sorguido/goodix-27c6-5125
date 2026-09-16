#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Protected ATTEMPT02 R2 replay with aggregate-only D279/56 output."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path


OPERATION = "D279_56_AUTHORIZED_OFFLINE_DYNAMIC_ENROLLMENT_REPLAY"
CAPTURE_SHA256 = "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"
AUTHORITY_SHA256 = "9b93693a27eaa6456b1d72a13d0d61e9bd01a3cd0842ae6f9e5c530ec9c631f6"
POLICY_SOURCE_SHA256 = "cb2fffe7539bac17e70a7d2ed8c01dd5fe4a275a02a430805b6ed6aa5b4fbacd"


class ProtectedReplayError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtectedReplayError(message)


def load_module(name: str, path: Path):
    require(path.is_file() and not path.is_symlink(), f"{name}_NOT_REGULAR")
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"{name}_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def evaluate(args) -> None:
    require(os.geteuid() == 0, "ROOT_REQUIRED_FOR_PROTECTED_READ")
    require(os.environ.get("D279_56_AUTHORIZED_OPERATION") == OPERATION,
            "AUTHORIZED_OPERATION_ENV_MISSING")
    require(os.environ.get("D279_56_AUTHORIZED_SHA") == args.baseline,
            "AUTHORIZED_SHA_ENV_MISMATCH")
    require(len(args.baseline) == 40 and
            all(character in "0123456789abcdef" for character in args.baseline),
            "BASELINE_SHA")
    require(args.capture.is_file() and not args.capture.is_symlink(),
            "CAPTURE_FILE")
    require(hashlib.sha256(args.capture.read_bytes()).hexdigest() == CAPTURE_SHA256,
            "CAPTURE_HASH")
    require(args.helper.is_file() and not args.helper.is_symlink(),
            "R2_HELPER_FILE")
    require(not args.output.exists(), "OUTPUT_COLLISION")

    root = Path(__file__).resolve().parents[2]
    authority_path = Path(__file__).with_name("D279_56_authority.json")
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    require(authority["authorization_status"] == "GRANTED_AT_ORIGIN",
            "AUTHORITY_NOT_GRANTED")
    require(authority["source_document_sha256"] == AUTHORITY_SHA256,
            "AUTHORITY_SOURCE_HASH")
    require(authority["authorized_scope"] ==
            "ATTEMPT02_PROTECTED_OFFLINE_READ_RECONSTRUCTION_PREPROCESSING_ANALYSIS_AND_AGGREGATE_REPLAY_ONLY",
            "AUTHORITY_SCOPE")
    require(authority["further_per_run_user_authorization_required"] is False,
            "AUTHORITY_PER_RUN_STATE")
    require(authority["new_capture_or_live_usb_authorized"] is False,
            "AUTHORITY_LIVE_STATE")
    require(hashlib.sha256((root / "Rockytkg/src/goodixgf.c").read_bytes()).hexdigest()
            == POLICY_SOURCE_SHA256, "ROCKYTKG_POLICY_SOURCE_HASH")

    d33 = load_module(
        "d279_56_d33",
        root / "analysis/D279/d279_33_attempt02_in_memory_composer.py",
    )
    d35 = load_module(
        "d279_56_d35",
        root / "operator_kit/d279-35-offline-protected-evaluation/d279_35_protected_attempt02_eval.py",
    )
    policy = load_module(
        "d279_56_policy",
        root / "analysis/D279/d279_56_dynamic_enrollment_policy.py",
    )

    transport = psk = None
    try:
        transport, psk = d35.read_transport_psk(
            d35.TRANSPORT_DIRECTORY,
            expected_uid=0,
            expected_gid=0,
            expected_hash=d35.TRANSPORT_SHA256,
        )
        d35.cleanse(transport)
        with d33.decrypt_target_attempt(psk, args.capture) as attempt:
            with policy.R2Pipe(args.helper) as r2:
                aggregate = policy.evaluate_target_attempt(attempt.rasters, r2)
        output = {
            "schema": "D279_56_AUTHENTIC_DYNAMIC_ENROLLMENT_AGGREGATE_V1",
            "outcome": "AUTHENTIC_DYNAMIC_POLICY_AGGREGATE_READY",
            "baseline_sha": args.baseline,
            "operation": OPERATION,
            "capture_sha256": CAPTURE_SHA256,
            "authority_source_sha256": AUTHORITY_SHA256,
            "rockytkg_policy_source_sha256": POLICY_SOURCE_SHA256,
            "transport_input_verified": True,
            "transport_or_psk_exported": False,
            "plaintext_or_raster_exported": False,
            "biometric_feature_or_template_exported": False,
            "live_or_usb_action_count": 0,
            "aggregate": aggregate,
        }
        d35.write_aggregate(args.output, output)
    finally:
        if psk is not None:
            d35.cleanse(psk)
        if transport is not None:
            d35.cleanse(transport)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        evaluate(args)
        print("OUTCOME=AUTHENTIC_DYNAMIC_POLICY_AGGREGATE_READY")
        print("TARGET_PSK_ACCESSED=true")
        print("PSK_EXPORTED=false")
        print("RASTER_OR_BIOMETRIC_FEATURE_EXPORTED=false")
        print("LIVE_OR_USB_ACTION_COUNT=0")
        return 0
    except (ProtectedReplayError, OSError, ValueError, RuntimeError, KeyError) as error:
        print("OUTCOME=FAIL_CLOSED")
        print(f"FAILURE_CLASS={type(error).__name__}:{error}")
        print("LIVE_OR_USB_ACTION_COUNT=0")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
