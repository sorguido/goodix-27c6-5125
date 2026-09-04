#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Passive metadata-only observer for the D279/10 third B0 boundary."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from d279_10_third_cycle import EvidenceError, inspect_growing_capture


def write_signal(path: Path, document: dict) -> None:
    if path.exists():
        raise EvidenceError("OBSERVER_SIGNAL_OUTPUT_COLLISION")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def observe(pcap: Path, signal: Path, deadline: float, poll_ms: int) -> dict:
    started = time.monotonic()
    while time.monotonic() - started <= deadline:
        state = inspect_growing_capture(pcap)
        if state["status"] == "THIRD_FINGERPRINT_B0_OBSERVED":
            result = {
                "schema": "D279_10_WIRE_OBSERVER_SIGNAL_V1",
                **state,
                "stop_trigger": "WIRE_DRIVEN",
                "automatic_retry_count": 0,
            }
            write_signal(signal, result)
            return result
        if state["status"] == "FAIL_CLOSED":
            raise EvidenceError(state["failure_class"])
        time.sleep(poll_ms / 1000.0)
    raise EvidenceError("THIRD_B0_OBSERVER_DEADLINE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--signal-output", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=float, default=300.0)
    parser.add_argument("--poll-milliseconds", type=int, default=100)
    args = parser.parse_args()
    try:
        result = observe(args.pcap, args.signal_output,
                         args.deadline_seconds, args.poll_milliseconds)
        print(json.dumps({"status": result["status"],
                          "terminal_frame": result["terminal_frame"]}))
        return 0
    except (EvidenceError, OSError, ValueError) as exc:
        result = {
            "schema": "D279_10_WIRE_OBSERVER_FAILURE_V1",
            "status": "FAIL_CLOSED",
            "failure_class": str(exc),
            "automatic_retry_count": 0,
        }
        try:
            write_signal(args.signal_output, result)
        except (EvidenceError, OSError):
            pass
        print(json.dumps(result))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
