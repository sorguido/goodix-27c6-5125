"""D243 root preflight; no libusb call and no sensor traffic."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from analysis.D243.d243_dependency_gate import verify_dependencies

verify_dependencies()

from analysis.D241 import d241_preflight as base
from src.goodix5125_d235_entrypoint import ProductionRuntimePaths


REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = REPOSITORY / "analysis/D243/D243_preflight_report.json"
D243_MARKER_NAME = "d243-operator-invocation.marker"
HISTORICAL_MARKER_NAMES = (
    "d236-live-single-use.marker",
    "d238-live-single-use.marker",
    "d238-operator-invocation.marker",
    "d239-operator-invocation.marker",
    "d241-operator-invocation.marker",
    "d242-operator-invocation.marker",
)


def marker_namespace_status(store: Path) -> dict[str, object]:
    current = store / D243_MARKER_NAME
    return {
        "namespace": str(current),
        "d243_marker_absent": not os.path.lexists(current),
        "historical_markers_present_benign": [
            name for name in HISTORICAL_MARKER_NAMES if os.path.lexists(store / name)
        ],
        "historical_markers_blocking": False,
    }


def offline_import_probe() -> int:
    paths = ProductionRuntimePaths.system_default()
    paths.validate()
    report = {
        "schema": "d243-preflight-import-probe-v1",
        "status": "pass",
        "repository": str(REPOSITORY),
        "marker_namespace": str(paths.single_use_marker),
        "report_directory": str(paths.report_directory),
        "libusb_init_count": 0,
        "usb_open_count": 0,
        "goodix_command_count": 0,
        "live_marker_create_count": 0,
    }
    if (
        paths.single_use_marker.name != D243_MARKER_NAME
        or paths.report_directory.name != "d243-results"
    ):
        report["status"] = "fail"
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


def offline_sandbox_preflight(root: Path) -> dict[str, object]:
    store = root.resolve() / "var/lib/goodix-5125-poc"
    reports = store / "d243-results"
    reports.mkdir(parents=True, mode=0o700, exist_ok=True)
    reports.chmod(0o700)
    for name in HISTORICAL_MARKER_NAMES:
        marker = store / name
        marker.write_text("historical fixture\n", encoding="ascii")
        marker.chmod(0o600)
    first = marker_namespace_status(store)
    current = store / D243_MARKER_NAME
    current.write_text("consumed fixture\n", encoding="ascii")
    current.chmod(0o600)
    second = marker_namespace_status(store)
    directory = base.report_directory_status(reports, owner_uid=os.getuid())
    return {
        "schema": "d243-offline-preflight-fixture-v1",
        "status": "PASS"
        if first["d243_marker_absent"]
        and not second["d243_marker_absent"]
        and directory["pass"]
        else "FAIL",
        "historical_markers_case": first,
        "consumed_d243_marker_case": second,
        "report_directory": directory,
        "libusb_init_count": 0,
        "usb_open_count": 0,
        "goodix_command_count": 0,
    }


def live_preflight() -> int:
    base.OUTPUT = OUTPUT
    base.HISTORICAL_MARKER_NAMES = HISTORICAL_MARKER_NAMES
    base.D241_MARKER_NAME = D243_MARKER_NAME
    status = base.live_preflight()
    report = json.loads(OUTPUT.read_text(encoding="utf-8"))
    report["schema"] = "d243-preflight-report-v1"
    marker = report.get("marker_namespace_status", {})
    if "d241_marker_absent" in marker:
        marker["d243_marker_absent"] = marker.pop("d241_marker_absent")
    report["failure_class"] = str(report.get("failure_class", "none")).replace(
        "d241_", "d243_"
    )
    base.publish(report)
    return status


def main(argv: tuple[str, ...] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments == ("--offline-import-probe",):
        return offline_import_probe()
    if len(arguments) == 2 and arguments[0] == "--offline-sandbox-preflight":
        report = offline_sandbox_preflight(Path(arguments[1]))
        print(json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "PASS" else 1
    if arguments:
        print("d243_preflight: unexpected arguments", file=sys.stderr)
        return 64
    return live_preflight()


if __name__ == "__main__":
    raise SystemExit(main())

