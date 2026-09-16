# SPDX-License-Identifier: GPL-2.0-or-later
"""Render a redacted, actionable D250 preflight failure summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(report: dict[str, object]) -> str:
    failures = report.get("failures", ())
    if not isinstance(failures, list):
        failures = ["malformed_failure_list"]
    marker = report.get("marker_namespace_status", {})
    marker_path = (
        marker.get("namespace", "UNAVAILABLE")
        if isinstance(marker, dict)
        else "UNAVAILABLE"
    )
    return "\n".join(
        (
            "D250_PHASE=PREFLIGHT",
            "D250_RESULT=FAIL",
            f"D250_FAILURE_CLASS={str(report.get('failure_class', 'PREFLIGHT_UNRESOLVED')).upper()}",
            f"D250_PREFLIGHT_FAILURES={','.join(str(item) for item in failures) or 'unknown'}",
            f"D250_MARKER_PATH={marker_path}",
            f"D250_LIVE_CRITICAL_SET_STATUS={report.get('live_critical_set_status', 'UNAVAILABLE')}",
            f"D250_USB_OPEN_COUNT={report.get('usb_open_count', 0)}",
            f"D250_AF_ATTEMPT_COUNT={report.get('af_attempt_count', 0)}",
            f"D250_AF_SEND_COUNT={report.get('af_send_count', 0)}",
            f"D250_TLS_HANDSHAKE_COUNT={report.get('tls_handshake_count', 0)}",
            f"D250_D4_SEND_COUNT={report.get('d4_send_count', 0)}",
            f"D250_REAL_SECRET_READ_COUNT={report.get('real_secret_read_count', 0)}",
            f"D250_LIVE_MARKER_CREATE_COUNT={report.get('live_marker_create_count', 0)}",
            "D250_LIVE_USB_EXECUTION=NOT_STARTED",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"d250_preflight_observability: {type(exc).__name__}: {exc}")
        return 1
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
