"""Render a redacted, actionable D244 preflight failure summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence


def render(report: Mapping[str, object]) -> str:
    failures = report.get("failures", ())
    if not isinstance(failures, list):
        failures = ["malformed_failure_list"]
    marker = report.get("marker_namespace_status", {})
    marker_path = marker.get("namespace", "UNAVAILABLE") if isinstance(marker, dict) else "UNAVAILABLE"
    lines = (
        "D244_PHASE=PREFLIGHT",
        "D244_RESULT=FAIL",
        f"D244_FAILURE_CLASS={str(report.get('failure_class', 'PREFLIGHT_UNRESOLVED')).upper()}",
        f"D244_PREFLIGHT_FAILURES={','.join(str(item) for item in failures) or 'unknown'}",
        f"D244_MARKER_PATH={marker_path}",
        f"D244_USB_OPEN_COUNT={report.get('usb_open_count', 0)}",
        f"D244_GOODIX_COMMAND_COUNT={report.get('goodix_command_count', 0)}",
        "D244_REAL_SECRET_READ_COUNT=0",
        "D244_FPRINTD_MUTATION_COUNT=0",
        "D244_LIVE_MARKER_CREATE_COUNT=0",
        "D244_LIVE_USB_EXECUTION=NOT_STARTED",
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"d244_preflight_observability: {type(exc).__name__}: {exc}")
        return 1
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
