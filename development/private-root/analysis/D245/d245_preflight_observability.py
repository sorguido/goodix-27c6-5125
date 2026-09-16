"""Render a redacted, actionable D245 preflight failure summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(report: dict[str, object]) -> str:
    failures = report.get("failures", ())
    if not isinstance(failures, list):
        failures = ["malformed_failure_list"]
    marker = report.get("marker_namespace_status", {})
    marker_path = marker.get("namespace", "UNAVAILABLE") if isinstance(marker, dict) else "UNAVAILABLE"
    return "\n".join(
        (
            "D245_PHASE=PREFLIGHT",
            "D245_RESULT=FAIL",
            f"D245_FAILURE_CLASS={str(report.get('failure_class', 'PREFLIGHT_UNRESOLVED')).upper()}",
            f"D245_PREFLIGHT_FAILURES={','.join(str(item) for item in failures) or 'unknown'}",
            f"D245_MARKER_PATH={marker_path}",
            f"D245_USB_OPEN_COUNT={report.get('usb_open_count', 0)}",
            f"D245_GOODIX_COMMAND_COUNT={report.get('goodix_command_count', 0)}",
            "D245_REAL_SECRET_READ_COUNT=0",
            "D245_FPRINTD_MUTATION_COUNT=0",
            "D245_LIVE_MARKER_CREATE_COUNT=0",
            "D245_LIVE_USB_EXECUTION=NOT_STARTED",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"d245_preflight_observability: {type(exc).__name__}: {exc}")
        return 1
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
