#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Static, content-free validation of the D293/01 offline contract."""

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]


def text(path: str) -> str:
    candidate = ROOT / path
    if not candidate.is_file():
        raise AssertionError(f"missing source: {path}")
    return candidate.read_text(encoding="utf-8")


def require(haystack: str, needle: str, label: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> int:
    fprintd_device = text("reference/fprintd-fedora44-1.94.5/source/src/device.c")
    storage = text("reference/fprintd-fedora44-1.94.5/source/src/file_storage.c")
    policy = text(
        "reference/fprintd-fedora44-1.94.5/source/data/"
        "net.reactivated.fprint.device.policy.in"
    )
    unit = text("reference/fprintd-fedora44-1.94.5/source/data/fprintd.service.in")
    dbus = text(
        "reference/fprintd-fedora44-1.94.5/source/src/"
        "net.reactivated.Fprint.Device.xml"
    )
    fp_device = text(
        "reference/libfprint-fedora44-1.94.100/source/libfprint/fp-device.c"
    )
    fp_print = text(
        "reference/libfprint-fedora44-1.94.100/source/libfprint/fp-print.c"
    )
    goodix = text("libfprint-driver/goodix_fpimage_device.c")
    runtime = text("libfprint-driver/goodix_runtime_material.c")
    target = text("libfprint-driver/goodix_target_material.c")
    inputs = text("libfprint-driver/goodix_runtime_inputs.c")
    report = text("analysis/D293/D293_01_MULTI_USER_AND_RUNTIME_MATERIAL_CONTRACT.md")

    for needle in (
        '#define FILE_STORAGE_PATH "/var/lib/fprint"',
        'g_getenv ("STATE_DIRECTORY")',
        "g_build_filename (get_storage_path (), username, NULL)",
        "g_build_filename (base_store, driver, device_id, NULL)",
        "fp_print_get_username (new), username",
        "fp_print_compatible (new, dev)",
    ):
        require(storage, needle, "fprintd storage contract")
    for needle in (
        '"GetConnectionUnixUser"',
        "user = getpwuid (uid)",
        "FPRINT_DEVICE_PERMISSION_SETUSERNAME",
        'g_str_equal (method_name, "Claim")',
        'g_str_equal (method_name, "ListEnrolledFingers")',
        'g_str_equal (method_name, "DeleteEnrolledFingers2")',
        "session->username",
        "g_ptr_array_index (gallery, 0)",
    ):
        require(fprintd_device, needle, "fprintd user/action contract")

    methods = set(re.findall(r'<method name="([A-Za-z0-9]+)"', dbus))
    expected_methods = {
        "ListEnrolledFingers",
        "DeleteEnrolledFingers",
        "DeleteEnrolledFingers2",
        "DeleteEnrolledFinger",
        "Claim",
        "Release",
        "VerifyStart",
        "VerifyStop",
        "EnrollStart",
        "EnrollStop",
    }
    if methods != expected_methods:
        raise AssertionError(f"D-Bus method drift: {sorted(methods)}")
    for action in ("verify", "enroll", "setusername"):
        require(policy, f"net.reactivated.fprint.device.{action}", "PolicyKit action")
    require(unit, "StateDirectory=fprint", "systemd storage root")
    require(unit, "StateDirectoryMode=0700", "systemd storage mode")

    require(fp_device, 'priv->device_id = g_strdup ("0")', "default device ID")
    require(fp_device, "if (!FP_DEVICE_GET_CLASS (self)->probe)", "probe default")
    require(fp_print, "self->driver, fp_device_get_driver (device)", "driver compatibility")
    require(fp_print, "self->device_id, fp_device_get_device_id (device)", "device compatibility")
    require(goodix, 'device_class->id        = "goodix_27c6_5125"', "Goodix driver ID")
    require(goodix, "~((guint) FP_DEVICE_FEATURE_IDENTIFY)", "production IDENTIFY mask")
    if re.search(r"device_class->probe\s*=", goodix):
        raise AssertionError("Goodix device-id contract changed: probe vfunc added")

    expected_runtime_paths = {
        "/var/lib/goodix-5125-poc",
        "/var/lib/goodix-5125-poc/target-material-manifest.json",
        "/var/lib/goodix-5125-poc/transport-material.bin",
        "/var/lib/goodix-5125-poc/target-config-90.bin",
        "/var/lib/goodix-5125-poc/gfusb.dll",
        "/var/lib/goodix-5125-poc/fdt-cache.bin",
    }
    runtime_paths = set(re.findall(r'"(/var/lib/goodix-5125-poc[^"\\]*)"', runtime))
    if runtime_paths != expected_runtime_paths:
        raise AssertionError(f"runtime path drift: {sorted(runtime_paths)}")
    for source, needle in (
        (runtime, "policy->directory_owner_uid = 0"),
        (runtime, "policy->directory_owner_gid = 0"),
        (runtime, "policy->directory_mode = 0700"),
        (target, "policy->mode = 0600"),
        (inputs, "policy->mode = 0600"),
        (target, "O_RDONLY | O_CLOEXEC | O_NOFOLLOW"),
        (inputs, "O_RDONLY | O_CLOEXEC | O_NOFOLLOW"),
    ):
        require(source, needle, "runtime protected-material policy")

    manifest_lines = text("production/source-files.tsv").splitlines()
    manifest_paths = [line.split("\t", 1)[0] for line in manifest_lines if line]
    if len(manifest_paths) != len(set(manifest_paths)):
        raise AssertionError("duplicate production source manifest path")
    forbidden = re.compile(
        r"(?:/home/|g_get_home_dir|getpw(?:uid|nam)|\busername\b|\$HOME|XDG_)"
    )
    hits = []
    for path in manifest_paths:
        body = text(path)
        if forbidden.search(body):
            hits.append(path)
    if hits:
        raise AssertionError(f"user/home coupling in production source: {hits}")

    for marker in (
        "D293_01_OUTCOME=PASS_OFFLINE_CONTRACT",
        "PHASE_B_B1=COMPLETED",
        "PROTECTED_FILE_CONTENT_READ=false",
        "NEXT_BOUNDARY=PHASE_B_B2_MULTI_USER_STORAGE_MODEL_AND_MULTI_FINGER_ANY_OFFLINE",
    ):
        require(report, marker, "report marker")

    print("D293_01_CONTRACT_VALIDATION=PASS")
    print(f"FPRINTD_DBUS_METHOD_COUNT={len(methods)}")
    print(f"PRODUCTION_SOURCE_MANIFEST_PATH_COUNT={len(manifest_paths)}")
    print("PRODUCTION_USER_HOME_HARDCODE_COUNT=0")
    print(f"PRODUCTION_RUNTIME_PATH_COUNT={len(runtime_paths)}")
    print("PROTECTED_FILE_CONTENT_READ=false")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"D293_01_CONTRACT_VALIDATION=FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
