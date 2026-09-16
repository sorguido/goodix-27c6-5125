#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <repository-root> <build-dir> <pkgconfig-dir>" >&2
  exit 2
fi

repo_root=$1
build_dir=$2
pkgconfig_dir=$3
source_root="$repo_root/reference/libfprint-fedora44-1.94.100/source"

export PKG_CONFIG_PATH=$pkgconfig_dir
# The extracted Fedora OpenCV DSOs retain runtime dependencies (TBB and
# FlexiBLAS) that are deliberately supplied by the host runner, not installed
# into this network-isolated SDK.  Permit those shared-library references while
# linking host-only test executables; runtime closure is checked by the outer
# runner.
export LDFLAGS=-Wl,--allow-shlib-undefined

meson setup "$build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled

meson compile -C "$build_dir" test-goodix-fpimage-sigfm-action \
  fprint-list-supported-devices

compile_db="$build_dir/compile_commands.json"
grep -F -- '-DGOODIX_LIBFPRINT_SIGFM' "$compile_db" >/dev/null
grep -F 'test_goodix_fedora44_nbis_action.c' "$compile_db" >/dev/null
if grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)' \
     "$repo_root/libfprint-driver/tests/test_goodix_fedora44_nbis_action.c"; then
  echo "SIGFM action test unexpectedly contains a production/USB entry point" >&2
  exit 1
fi

test -x "$build_dir/tests/test-goodix-fpimage-sigfm-action"
test -x "$build_dir/libfprint/fprint-list-supported-devices"
echo D279_52_EXACT_TARGET_LIBFPRINT=1.94.100
echo D279_52_EXTRACTOR=SIGFM_ROCKYTKG
echo D279_52_FIXTURE_PROVENANCE=DETERMINISTIC_STRUCTURED_NON_BIOMETRIC
echo D279_52_TARGET_BIOMETRIC_VALIDATION=false
echo REAL_USB_ENUMERATION_COUNT=0
echo REAL_USB_OPEN_COUNT=0
echo REAL_USB_CLAIM_COUNT=0
echo REAL_USB_SUBMIT=0
echo LIVE_EXECUTION_PERFORMED=false
