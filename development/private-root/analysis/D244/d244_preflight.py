"""D244 root preflight; no libusb call and no sensor traffic."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from analysis.D244.d244_dependency_gate import verify_dependencies

verify_dependencies()

from analysis.D241 import d241_preflight as base
from src.goodix5125_d235_entrypoint import ProductionRuntimePaths


REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = REPOSITORY / "analysis/D244/D244_preflight_report.json"
D244_MARKER_NAME = "d244-operator-invocation.marker"
HISTORICAL_MARKER_NAMES = (
    "d236-live-single-use.marker",
    "d238-live-single-use.marker",
    "d238-operator-invocation.marker",
    "d239-operator-invocation.marker",
    "d241-operator-invocation.marker",
    "d242-operator-invocation.marker",
    "d243-operator-invocation.marker",
)
_SEALED_SYSTEM_DEFAULT = ProductionRuntimePaths.system_default


def d244_runtime_paths() -> ProductionRuntimePaths:
    sealed = _SEALED_SYSTEM_DEFAULT()
    store = sealed.psk_store.parent
    reports = store / "d244-results"
    return ProductionRuntimePaths(
        psk_store=sealed.psk_store,
        target_material_manifest=sealed.target_material_manifest,
        config90_store=sealed.config90_store,
        canonical_gfusb=sealed.canonical_gfusb,
        report_directory=reports,
        checkpoint_report=reports / "d244-live-pre-restore.json",
        final_report=reports / "d244-live-result.json",
        single_use_marker=store / D244_MARKER_NAME,
    )


def marker_namespace_status(store: Path) -> dict[str, object]:
    current = store / D244_MARKER_NAME
    return {
        "namespace": str(current),
        "d244_marker_absent": not os.path.lexists(current),
        "historical_markers_present_benign": [
            name for name in HISTORICAL_MARKER_NAMES if os.path.lexists(store / name)
        ],
        "historical_markers_blocking": False,
    }


def offline_import_probe() -> int:
    paths = d244_runtime_paths()
    paths.validate()
    report = {
        "schema": "d244-preflight-import-probe-v1",
        "status": "pass",
        "repository": str(REPOSITORY),
        "marker_namespace": str(paths.single_use_marker),
        "report_directory": str(paths.report_directory),
        "libusb_init_count": 0,
        "usb_open_count": 0,
        "goodix_command_count": 0,
        "live_marker_create_count": 0,
    }
    print(json.dumps(report, sort_keys=True))
    return 0


def offline_sandbox_preflight(root: Path) -> dict[str, object]:
    store = root.resolve() / "var/lib/goodix-5125-poc"
    reports = store / "d244-results"
    reports.mkdir(parents=True, mode=0o700, exist_ok=True)
    reports.chmod(0o700)
    for name in HISTORICAL_MARKER_NAMES:
        marker = store / name
        marker.write_text("historical fixture\n", encoding="ascii")
        marker.chmod(0o600)
    first = marker_namespace_status(store)
    current = store / D244_MARKER_NAME
    current.write_text("consumed fixture\n", encoding="ascii")
    current.chmod(0o600)
    second = marker_namespace_status(store)
    directory = base.report_directory_status(reports, owner_uid=os.getuid())
    return {
        "schema": "d244-offline-preflight-fixture-v1",
        "status": "PASS"
        if first["d244_marker_absent"]
        and not second["d244_marker_absent"]
        and directory["pass"]
        else "FAIL",
        "historical_markers_case": first,
        "consumed_d244_marker_case": second,
        "report_directory": directory,
        "libusb_init_count": 0,
        "usb_open_count": 0,
        "goodix_command_count": 0,
    }


def live_preflight() -> int:
    original = base.ProductionRuntimePaths.system_default
    try:
        base.ProductionRuntimePaths.system_default = classmethod(
            lambda cls: d244_runtime_paths()
        )
        base.OUTPUT = OUTPUT
        base.HISTORICAL_MARKER_NAMES = HISTORICAL_MARKER_NAMES
        base.D241_MARKER_NAME = D244_MARKER_NAME
        status = base.live_preflight()
    finally:
        base.ProductionRuntimePaths.system_default = original
    report = json.loads(OUTPUT.read_text(encoding="utf-8"))
    report["schema"] = "d244-preflight-report-v1"
    marker = report.get("marker_namespace_status", {})
    if "d241_marker_absent" in marker:
        marker["d244_marker_absent"] = marker.pop("d241_marker_absent")
    report["failure_class"] = str(report.get("failure_class", "none")).replace(
        "d241_", "d244_"
    )
    report["D244_FRESH_BOOT_DOCUMENTED"] = os.environ.get(
        "D244_FRESH_BOOT_DOCUMENTED", "false"
    ) == "true"
    report["D244_FRESH_BOOT_EVIDENCE"] = os.environ.get(
        "D244_FRESH_BOOT_EVIDENCE", "unavailable"
    )
    report["D244_FRESH_STATE_CONTROL_VALID"] = os.environ.get(
        "D244_FRESH_STATE_CONTROL_VALID", "false"
    ) == "true"
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
        print("d244_preflight: unexpected arguments", file=sys.stderr)
        return 64
    return live_preflight()


if __name__ == "__main__":
    raise SystemExit(main())
