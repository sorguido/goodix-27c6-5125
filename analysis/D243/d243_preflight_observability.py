#!/usr/bin/env python3
"""Render a redacted, actionable D243 preflight failure summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_SCHEMA = "d243-preflight-report-v1"


def _safe(value: object) -> str:
    text = str(value)
    return "".join(
        character if character.isalnum() or character in "._:/,-" else "_"
        for character in text
    )


def render(report_path: Path) -> tuple[str, ...]:
    failure_class = "PREFLIGHT_REPORT_MISSING"
    failures = "preflight_report_missing"
    marker_path = "UNAVAILABLE"
    usb_open_count = 0
    goodix_command_count = 0
    exception_class: str | None = None
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(report, dict) or report.get("schema") != EXPECTED_SCHEMA:
                raise ValueError("unexpected preflight report schema")
            raw_failures = report.get("failures")
            if not isinstance(raw_failures, list) or not raw_failures:
                raise ValueError("missing concrete preflight failures")
            safe_failures = [_safe(item) for item in raw_failures]
            raw_class = _safe(report.get("failure_class", "")).upper()
            if raw_class in ("", "NONE", "PREFLIGHT_FAILED"):
                raw_class = safe_failures[0].upper()
            failure_class = raw_class
            failures = ",".join(safe_failures)
            marker = report.get("marker_namespace_status")
            if isinstance(marker, dict) and marker.get("namespace"):
                marker_path = _safe(marker["namespace"])
            raw_usb = report.get("usb_open_count", 0)
            raw_commands = report.get("goodix_command_count", 0)
            usb_open_count = raw_usb if isinstance(raw_usb, int) and raw_usb >= 0 else 0
            goodix_command_count = (
                raw_commands if isinstance(raw_commands, int) and raw_commands >= 0 else 0
            )
            if report.get("preflight_exception"):
                exception_class = _safe(report["preflight_exception"])
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
            failure_class = "PREFLIGHT_REPORT_INVALID"
            failures = "preflight_report_invalid"
    lines = [
        "D243_PHASE=PREFLIGHT",
        "D243_RESULT=FAIL",
        f"D243_FAILURE_CLASS={failure_class}",
        f"D243_PREFLIGHT_FAILURES={failures}",
        f"D243_MARKER_PATH={marker_path}",
        f"D243_USB_OPEN_COUNT={usb_open_count}",
        f"D243_GOODIX_COMMAND_COUNT={goodix_command_count}",
        "D243_REAL_SECRET_READ_COUNT=0",
        "D243_FPRINTD_MUTATION_COUNT=0",
        "D243_LIVE_MARKER_CREATE_COUNT=0",
        "D243_LIVE_USB_EXECUTION=NOT_STARTED",
    ]
    if exception_class is not None:
        lines.append(f"D243_PREFLIGHT_EXCEPTION={exception_class}")
    return tuple(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    arguments = parser.parse_args()
    print("\n".join(render(arguments.report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
