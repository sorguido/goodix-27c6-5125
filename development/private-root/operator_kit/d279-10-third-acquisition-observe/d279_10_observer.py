#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Passive, non-terminal milestone observer for D279/10."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from d279_10_third_cycle import EvidenceError, inspect_growing_capture


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_once(path: Path, document: dict) -> None:
    if path.exists():
        raise EvidenceError("OBSERVER_RESULT_OUTPUT_COLLISION")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise EvidenceError("OBSERVER_RESULT_TEMP_COLLISION")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def append_journal(stream, event: dict) -> None:
    stream.write(json.dumps(event, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def observe(pcap: Path, journal: Path, stop_control: Path, result: Path,
            deadline: float, poll_ms: int) -> dict:
    if journal.exists():
        raise EvidenceError("OBSERVER_JOURNAL_COLLISION")
    journal.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    last_signature = None
    with journal.open("x", encoding="utf-8") as stream:
        append_journal(stream, {
            "schema": "D279_10_OBSERVER_JOURNAL_EVENT_V2",
            "event": "OBSERVER_STARTED",
            "observed_utc": utc_now(),
            "automatic_retry_count": 0,
        })
        while time.monotonic() - started <= deadline:
            state = inspect_growing_capture(pcap)
            if state["status"] == "FAIL_CLOSED":
                raise EvidenceError(state["failure_class"])
            signature = (
                state.get("wire_acquisition_cycle_count", 0),
                state.get("third_b0_milestone_observed", False),
                state.get("protocol_contradiction_count", 0),
            )
            if signature != last_signature:
                append_journal(stream, {
                    "schema": "D279_10_OBSERVER_JOURNAL_EVENT_V2",
                    "event": "WIRE_MILESTONE",
                    "observed_utc": utc_now(),
                    "wire_acquisition_cycle_count": signature[0],
                    "third_b0_milestone_observed": signature[1],
                    "protocol_contradiction_count": signature[2],
                    "stop_triggered": False,
                    "automatic_retry_count": 0,
                })
                last_signature = signature
            if stop_control.is_file():
                final = {
                    "schema": "D279_10_WIRE_OBSERVER_RESULT_V2",
                    "status": "STOP_REQUESTED_BY_RUNNER_AFTER_UI_AND_TAIL",
                    "wire_acquisition_cycle_count": signature[0],
                    "third_b0_milestone_observed": signature[1],
                    "protocol_contradiction_count": signature[2],
                    "stop_trigger": "RUNNER_CONTROL_FILE",
                    "automatic_retry_count": 0,
                }
                append_journal(stream, {
                    "schema": "D279_10_OBSERVER_JOURNAL_EVENT_V2",
                    "event": "OBSERVER_STOPPED",
                    "observed_utc": utc_now(),
                    **{key: value for key, value in final.items()
                       if key not in {"schema", "status"}},
                })
                write_once(result, final)
                return final
            time.sleep(poll_ms / 1000.0)
    raise EvidenceError("FULL_ENROLLMENT_OBSERVER_DEADLINE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--journal-output", type=Path, required=True)
    parser.add_argument("--stop-control", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=float, default=1200.0)
    parser.add_argument("--poll-milliseconds", type=int, default=100)
    args = parser.parse_args()
    try:
        result = observe(
            args.pcap, args.journal_output, args.stop_control,
            args.result_output, args.deadline_seconds, args.poll_milliseconds)
        print(json.dumps({"status": result["status"],
                          "wire_acquisition_cycle_count":
                              result["wire_acquisition_cycle_count"]}))
        return 0
    except (EvidenceError, OSError, ValueError) as exc:
        failure = {
            "schema": "D279_10_WIRE_OBSERVER_FAILURE_V2",
            "status": "FAIL_CLOSED",
            "failure_class": str(exc),
            "automatic_retry_count": 0,
        }
        try:
            write_once(args.result_output, failure)
        except (EvidenceError, OSError):
            pass
        print(json.dumps(failure))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
