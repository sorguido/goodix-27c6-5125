#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <repository-root> <build-dir> <pkgconfig-dir> <fixture>" >&2
  exit 2
fi

repo_root=$1
build_dir=$2
pkgconfig_dir=$3
fixture=$4
source_root="$repo_root/reference/libfprint-fedora44-1.94.100/source"

export PKG_CONFIG_PATH=$pkgconfig_dir

meson setup "$build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled

meson compile -C "$build_dir" test-goodix-fpimage-nbis-action

compile_db="$build_dir/compile_commands.json"
grep -F -- '-DGOODIX_LIBFPRINT_1_94_100_NBIS' "$compile_db" >/dev/null
grep -F 'test_goodix_fedora44_nbis_action.c' "$compile_db" >/dev/null
if grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)' \
     "$repo_root/libfprint-driver/tests/test_goodix_fedora44_nbis_action.c"; then
  echo "NBIS action test unexpectedly contains a production/USB entry point" >&2
  exit 1
fi

G_DEBUG=fatal-warnings timeout --signal=TERM 45 \
  "$build_dir/tests/test-goodix-fpimage-nbis-action" "$fixture"

sanitized_build_dir="$build_dir-sanitized"
meson setup "$sanitized_build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled \
  -Db_sanitize=address,undefined
meson compile -C "$sanitized_build_dir" test-goodix-fpimage-nbis-action
# LeakSanitizer cannot operate under the Flatpak/ptrace boundary used by this
# repository; AddressSanitizer and UndefinedBehaviorSanitizer remain enabled.
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
G_DEBUG=fatal-warnings timeout --signal=TERM 45 \
  "$sanitized_build_dir/tests/test-goodix-fpimage-nbis-action" "$fixture"

echo D279_27_EXACT_TARGET_LIBFPRINT=1.94.100
echo D279_27_EXTRACTOR=NBIS_NATIVE
echo D279_27_NORMAL_AND_ASAN_UBSAN=PASS
echo D279_27_FIXTURE_PROVENANCE=NIST_PUBLIC_DOMAIN_LIBFPRINT_EXAMPLE
echo D279_27_TARGET_BIOMETRIC_VALIDATION=false
echo REAL_USB_ENUMERATION_COUNT=0
echo REAL_USB_OPEN_COUNT=0
echo REAL_USB_CLAIM_COUNT=0
echo REAL_USB_SUBMIT=0
echo LIVE_EXECUTION_PERFORMED=false
