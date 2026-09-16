#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Observer passivo metadata-only del secondo B0 su pcapng in crescita."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from d274_03_postprocess_second_cycle import EvidenceError, inspect_growing_capture


def write_signal(path: Path, result: dict) -> None:
    if path.exists():
        raise EvidenceError("OBSERVER_SIGNAL_OUTPUT_COLLISION")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def observe(path: Path, signal_output: Path, deadline_seconds: float,
            poll_milliseconds: int) -> dict:
    started = time.monotonic()
    while time.monotonic() - started <= deadline_seconds:
        state = inspect_growing_capture(path)
        if state["status"] == "SECOND_FINGERPRINT_B0_OBSERVED":
            result = {
                "schema": "D274_03_WIRE_OBSERVER_SIGNAL_V1",
                **state,
                "stop_trigger": "WIRE_DRIVEN",
                "automatic_retry_count": 0,
            }
            write_signal(signal_output, result)
            return result
        if state["status"] == "FAIL_CLOSED":
            raise EvidenceError(state["failure_class"])
        time.sleep(poll_milliseconds / 1000.0)
    raise EvidenceError("SECOND_B0_OBSERVER_DEADLINE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--signal-output", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=float, default=180.0)
    parser.add_argument("--poll-milliseconds", type=int, default=100)
    args = parser.parse_args()
    try:
        result = observe(args.pcap, args.signal_output, args.deadline_seconds,
                         args.poll_milliseconds)
        print(json.dumps({"status": result["status"],
                          "terminal_frame": result["terminal_frame"]}))
        return 0
    except (EvidenceError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "failure_class": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
