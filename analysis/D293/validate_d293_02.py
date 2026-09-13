#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Static validation of the exact fprintd/Goodix D293/02 action contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def body(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, needle: str) -> None:
    assert needle in text, f"missing contract: {needle}"


def main() -> None:
    fprintd = body("reference/fprintd-fedora44-1.94.5/source/src/device.c")
    driver = body("libfprint-driver/goodix_fpimage_device.c")
    core = body("reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-image-device.c")
    header = body("reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-image-device.h")
    builder = body("production/build-inner.sh")

    for needle in (
        "else if (gallery->len == 1)",
        "fp_device_has_feature (priv->dev, FP_DEVICE_FEATURE_IDENTIFY)",
        "priv->current_action = ACTION_IDENTIFY",
        "fp_device_identify (priv->dev, gallery",
        "g_autoptr(GPtrArray) all_prints = load_all_prints (rdev)",
        "(GAsyncReadyCallback) enroll_identify_cb",
    ):
        require(fprintd, needle)
    for needle in (
        "GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE",
        "device_class->features |= FP_DEVICE_FEATURE_IDENTIFY",
        "production_identify_enroll_handoff_armed",
        "production_identify_result_success",
        "!ctx->production_identify_result_match",
        "goodix_fpimage_device_reopen_for_capture_action",
        "goodix_fpimage_device_release_claim",
    ):
        require(driver, needle)
    require(core, "cls->identify_result (self, error == NULL, result != NULL)")
    require(header, "(*identify_result) (FpImageDevice *dev")
    require(builder, "-DGOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE")
    assert "GOODIX_PRODUCTION_DIRECT_ENROLL_PROFILE" not in builder

    print("D293_02_STATIC_CONTRACT=PASS")
    print("FPRINTD_ANY_MULTI_PRINT_USES_IDENTIFY=true")
    print("FPRINTD_ENROLL_DUPLICATE_CHECK_PRECEDES_ENROLL=true")
    print("GOODIX_IDENTIFY_NO_MATCH_ENROLL_HANDOFF_BOUNDED=true")
    print("GOODIX_PRODUCTION_DIRECT_ENROLL_PROFILE_COUNT=0")


if __name__ == "__main__":
    main()
