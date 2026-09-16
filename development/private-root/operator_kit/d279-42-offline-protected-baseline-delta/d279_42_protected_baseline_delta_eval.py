#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Authorized one-shot aggregate baseline-delta NBIS evaluation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import sys
from pathlib import Path


OPERATION = "D279_42_ONE_OFFLINE_PROTECTED_BASELINE_DELTA_EVALUATION"
CAPTURE_SHA256 = "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"


class ProtectedEvaluationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtectedEvaluationError(message)


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
    require(os.environ.get("D279_42_AUTHORIZED_OPERATION") == OPERATION,
            "AUTHORIZED_OPERATION_ENV_MISSING")
    require(os.environ.get("D279_42_AUTHORIZED_SHA") == args.baseline,
            "AUTHORIZED_SHA_ENV_MISMATCH")
    require(len(args.baseline) == 40 and all(c in "0123456789abcdef" for c in args.baseline),
            "BASELINE_SHA")
    require(args.capture.is_file() and not args.capture.is_symlink(), "CAPTURE_FILE")
    require(hashlib.sha256(args.capture.read_bytes()).hexdigest() == CAPTURE_SHA256, "CAPTURE_HASH")
    require(args.nbis_helper.is_file() and not args.nbis_helper.is_symlink(), "NBIS_HELPER_FILE")
    require(not args.output.exists(), "OUTPUT_COLLISION")

    root = Path(__file__).resolve().parents[2]
    d33 = load_module("d279_42_d33", root / "analysis/D279/d279_33_attempt02_in_memory_composer.py")
    d35 = load_module(
        "d279_42_d35",
        root / "operator_kit/d279-35-offline-protected-evaluation/d279_35_protected_attempt02_eval.py",
    )
    d39 = load_module("d279_39_nbis_quality_evaluator", root / "analysis/D279/d279_39_nbis_quality_evaluator.py")
    d42 = load_module("d279_42_evaluator", root / "analysis/D279/d279_42_baseline_delta_nbis_evaluator.py")

    transport = psk = None
    try:
        transport, psk = d35.read_transport_psk(
            d35.TRANSPORT_DIRECTORY, expected_uid=0, expected_gid=0,
            expected_hash=d35.TRANSPORT_SHA256,
        )
        d35.cleanse(transport)
        with d33.decrypt_target_attempt(psk, args.capture) as attempt:
            with d39.ExactLibfprintResizeNbisQualityPipe(args.nbis_helper) as runner:
                aggregate = d42.evaluate_target_attempt(attempt.rasters, runner)
        output = {
            "schema": "D279_42_ONE_OFFLINE_PROTECTED_BASELINE_DELTA_EVALUATION_V1",
            "outcome": "AUTHENTIC_BASELINE_DELTA_NBIS_AGGREGATE_READY",
            "baseline_sha": args.baseline,
            "operation": OPERATION,
            "capture_sha256": CAPTURE_SHA256,
            "transport_input_verified": True,
            "transport_or_psk_exported": False,
            "plaintext_or_raster_exported": False,
            "template_exported": False,
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
    parser.add_argument("--nbis-helper", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        evaluate(args)
        print("OUTCOME=AUTHENTIC_BASELINE_DELTA_NBIS_AGGREGATE_READY")
        print("TARGET_PSK_ACCESSED=true")
        print("PSK_EXPORTED=false")
        print("RASTER_OR_TEMPLATE_EXPORTED=false")
        print("LIVE_OR_USB_ACTION_COUNT=0")
        return 0
    except (ProtectedEvaluationError, OSError, ValueError, RuntimeError) as error:
        print("OUTCOME=FAIL_CLOSED")
        print(f"FAILURE_CLASS={type(error).__name__}:{error}")
        print("LIVE_OR_USB_ACTION_COUNT=0")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
