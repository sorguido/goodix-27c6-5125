#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE_TEST=1 \
  "$script_dir/run_goodix_fpimage_device_test.sh" \
  -p /goodix-fpimage-device/d282-direct-enroll-feature-profile
