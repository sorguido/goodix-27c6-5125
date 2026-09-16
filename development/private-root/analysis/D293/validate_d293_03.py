#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate the D293/03 host-only integration and installed KDE contract."""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
D293 = ROOT / "analysis" / "D293"


def fail(reason: str) -> None:
    print(f"D293_03_VALIDATOR=FAIL reason={reason}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, reason: str) -> None:
    if not condition:
        fail(reason)


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


runner = D293 / "d293_03_fprintd_integration.sh"
flow = D293 / "d293_03_private_bus_flow.sh"
result = D293 / "D293_03_OFFLINE_RESULT.env"
for path in (runner, flow, result):
    require(path.is_file(), f"missing_{path.name}")
subprocess.run(["bash", "-n", str(runner), str(flow)], check=True)

runner_text = runner.read_text()
flow_text = flow.read_text()
result_values = dict(
    line.split("=", 1)
    for line in result.read_text().splitlines()
    if line and not line.startswith("#")
)
for token in (
    "--unshare=network",
    "-Ddrivers=virtual_image",
    "d281_01_disable_usb_context.patch",
    "! grep -F 'goodix_27c6_5125'",
    "g_usb_context_(new|enumerate)",
):
    require(token in runner_text, f"runner_guard_missing_{token}")
for forbidden in ("sudo", "/var/lib/fprint", "FP_DRIVERS_ALLOWLIST=goodix"):
    require(forbidden not in runner_text + flow_text, f"forbidden_{forbidden}")
for token in (
    'export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"',
    'export STATE_DIRECTORY="$D293_03_PROBE_ROOT/state"',
    "D281_01_PRIVATE_BUS=1",
    "alpha=d293-alpha; beta=d293-beta",
    'verify "$alpha" any "$loop" verify-match',
    'verify "$beta" any "$whorl" verify-no-match',
    'fprintd-delete "$alpha" -f left-index-finger',
    'fprintd-delete "$beta"',
    "setusername AUTHORIZED=true",
):
    require(token in flow_text, f"flow_contract_missing_{token}")

fprintd_source = ROOT / "reference/fprintd-fedora44-1.94.5/source/src/device.c"
xml = ROOT / "reference/fprintd-fedora44-1.94.5/source/src/net.reactivated.Fprint.Device.xml"
require(fprintd_source.is_file() and xml.is_file(), "fprintd_exact_source_missing")
source_contract = fprintd_source.read_text() + xml.read_text()
for method in (
    "Claim",
    "ListEnrolledFingers",
    "EnrollStart",
    "VerifyStart",
    "DeleteEnrolledFinger",
    "DeleteEnrolledFingers2",
    "setusername",
):
    require(method in source_contract, f"fprintd_method_missing_{method}")

expected_results = {
    "D293_03_OUTCOME": "PASS_HOST_ONLY",
    "D293_03_PRINCIPAL_NAME_COUNT": "2",
    "D293_03_UNIX_UID_COUNT": "1",
    "D293_03_SETUSERNAME_AUTHORIZED": "true",
    "D293_03_ALPHA_INITIAL_FINGER_COUNT": "2",
    "D293_03_RESTART_RELOAD": "PASS",
    "D293_03_VERIFY_ANY_MULTI_FINGER": "PASS",
    "D293_03_PRINCIPAL_NAMESPACE_ISOLATION": "PASS",
    "D293_03_REPLACE": "PASS",
    "D293_03_DELETE_SINGLE": "PASS",
    "D293_03_DELETE_COMPLETE": "PASS",
    "PHASE_B_B3_OFFLINE_PREREQUISITES": "COMPLETED",
    "KDE_KCM_STATIC_CONTRACT": "PASS",
    "PHASE_B_B4_OFFLINE_PREREQUISITES": "COMPLETED",
    "D293_03_REAL_USB_ENUMERATION_ATTEMPTED": "false",
    "D293_03_REAL_SENSOR_ACCESSED": "false",
    "D293_03_PROTECTED_FILE_CONTENT_READ": "false",
    "PHASE_B_CLOSED": "false",
    "PRODUCTION_READY": "false",
}
for key, expected in expected_results.items():
    require(result_values.get(key) == expected, f"result_{key}")

kcm = pathlib.Path("/usr/lib64/qt6/plugins/plasma/kcms/systemsettings/kcm_users.so")
desktop = pathlib.Path("/usr/share/applications/kcm_users.desktop")
require(kcm.is_file() and desktop.is_file(), "kde_files_missing")
require(output("rpm", "-q", "fprintd") == "fprintd-1.94.5-5.fc44.x86_64", "fprintd_nevra")
require(output("rpm", "-q", "libfprint") == "libfprint-1.94.100-1.fc44.x86_64", "libfprint_nevra")
require(output("rpm", "-qf", str(kcm)) == result_values["D293_03_KDE_KCM_USERS_PACKAGE"], "kcm_owner")
require(output("rpm", "-qf", str(desktop)) == result_values["D293_03_KDE_METADATA_PACKAGE"], "desktop_owner")
require(sha256(kcm) == result_values["D293_03_KDE_KCM_USERS_SHA256"], "kcm_hash")
require(sha256(desktop) == result_values["D293_03_KDE_METADATA_SHA256"], "desktop_hash")
strings = output("strings", "-a", str(kcm))
kde_methods = {
    "net.reactivated.Fprint.Manager",
    "net.reactivated.Fprint.Device",
    "GetDefaultDevice",
    "Claim",
    "Release",
    "ListEnrolledFingers",
    "EnrollStart",
    "EnrollStop",
    "DeleteEnrolledFinger",
    "DeleteEnrolledFingers",
    "DeleteEnrolledFingers2",
}
missing = sorted(kde_methods.difference(strings.splitlines()))
require(not missing, "kde_methods_missing_" + ",".join(missing))
for token in ("deleteFingerprint", "reenrollFinger", "Re-enroll finger"):
    require(token in strings, f"kde_fingerprint_ux_missing_{token}")
require("Exec=systemsettings kcm_users" in desktop.read_text(), "kde_metadata_exec")

print("D293_03_VALIDATOR=PASS")
print("D293_03_FPRINTD_METHOD_COUNT=7")
print(f"D293_03_KDE_DBUS_METHOD_TOKEN_COUNT={len(kde_methods) - 2}")
print("D293_03_PRINCIPAL_NAME_COUNT=2")
print("D293_03_UNIX_UID_COUNT=1")
print("D293_03_REAL_USB_ACCESS=0")
