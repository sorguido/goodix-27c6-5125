#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Public, synthetic regression entrypoint. No private fixtures or live USB.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd -P)
[ "$#" -eq 0 ] || exit 2
if [ "${GOODIX_ZERO_MASK_IN_SDK:-0}" != 1 ]; then
  exec flatpak run --user --unshare=network --nodevice=all \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_ZERO_MASK_IN_SDK=1 --env=GOODIX_ENROLLMENT_A0_IN_SDK=1 \
    --env=GOODIX_STOCK_ATTEMPT_TEST=0 \
    --env=GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE_TEST=1 --env=CCACHE_DISABLE=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0"
fi
build=$(mktemp -d /tmp/goodix-zero-mask.XXXXXX)
trap 'find "$build" -depth -delete 2>/dev/null || true' EXIT HUP INT TERM
mkdir "$build/production" "$build/probe"
GOODIX_ZERO_MASK_PROBE_TEST=0 sh "$script_dir/run_goodix_fpimage_device_test_inner.sh" "$root" "$build/production"
GOODIX_ZERO_MASK_PROBE_TEST=1 sh "$script_dir/run_goodix_fpimage_device_test_inner.sh" "$root" "$build/probe"
sh "$script_dir/run_goodix_enrollment_a0_test.sh"
python3 -B "$root/operator_kit/phase-c-zero-mask/test_kit.py"
echo ZERO_MASK_PROBE_OFFLINE=PASS
