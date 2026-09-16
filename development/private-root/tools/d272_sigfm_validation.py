#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D272 future validation surface: offline dry-run only."""

from __future__ import annotations

import argparse
import json


ZERO_COUNTS = {
    "REAL_USB_OPEN_COUNT": 0,
    "REAL_SECRET_MATERIALIZATION_COUNT": 0,
    "REAL_FPRINTD_MUTATION_COUNT": 0,
    "REAL_BIOMETRIC_CAPTURE_COUNT": 0,
    "PERSISTENT_DEVICE_WRITE_COUNT": 0,
}


def report(message: str, dry_run: str) -> dict[str, object]:
    return {
        "schema": "D272_SIGFM_VALIDATION_OPERATOR_V1",
        "MESSAGGIO_OPERATORE": message,
        "D272_OPERATOR_DRY_RUN": dry_run,
        "BASELINE_APPROVED": False,
        "LIVE_AUTHORIZED": False,
        "READY_FOR_LIVE": False,
        "LIVE_EXECUTION": "NOT_PERFORMED",
        "BLOCKERS": [
            "D272_0X34_UP_TABLE_SOURCE_AND_FRESHNESS_NOT_TARGET_CLOSED",
            "D272_REAL_SIGFM_BUILD_BLOCKED_OPENCV4_DEV_UNAVAILABLE",
        ],
        **ZERO_COUNTS,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preflight offline D272; il percorso live non è autorizzato."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--future-live", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.future_live:
        print(json.dumps(report(
            "BLOCCATO: il percorso live D272 non è implementato né autorizzato.",
            "NOT_RUN",
        ), sort_keys=True))
        return 1
    print(json.dumps(report(
        "Dry-run offline completato: nessun dispositivo o dato biometrico è stato toccato.",
        "PASS",
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
