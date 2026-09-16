#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <repository-root> <work-dir> <pkgconfig-dir>" >&2
  exit 2
fi

repo_root=$1
work_dir=$2
pkgconfig_dir=$3
source_root="$repo_root/reference/libfprint-fedora44-1.94.100/source"
helper_source="$repo_root/libfprint-driver/tests/test_goodix_nbis_resize_quality_pipe.c"
evaluator="$repo_root/analysis/D279/d279_41_synthetic_nbis_scale_calibration.py"
export PKG_CONFIG_PATH=$pkgconfig_dir

configure ()
{
  directory=$1
  shift
  meson setup "$directory" "$source_root" \
    -Ddrivers=goodix_27c6_5125,aes3500 \
    -Dintrospection=true -Ddoc=false -Dinstalled-tests=false \
    -Dudev_rules=disabled -Dudev_hwdb=disabled "$@" >/dev/null
}

audit_helper ()
{
  helper=$1
  if grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)' "$helper_source"; then
    echo SYNTHETIC_HELPER_SOURCE_REACHES_USB >&2
    exit 1
  fi
  if nm "$helper" | grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)'; then
    echo SYNTHETIC_HELPER_BINARY_REACHES_USB >&2
    exit 1
  fi
  for symbol in get_minutiae free_minutiae g_lfsparms_V2 fpi_image_resize; do
    if nm -u "$helper" | grep -Eq "(^|[[:space:]])${symbol}$"; then
      echo "SYNTHETIC_HELPER_UNRESOLVED_$symbol" >&2
      exit 1
    fi
  done
}

normal_build="$work_dir/build"
configure "$normal_build"
meson compile -C "$normal_build" test-goodix-nbis-resize-quality-pipe >/dev/null
normal_helper="$normal_build/tests/test-goodix-nbis-resize-quality-pipe"
audit_helper "$normal_helper"
python3 -B "$evaluator" --helper "$normal_helper" >"$work_dir/normal.json"

sanitized_build="$work_dir/build-sanitized"
configure "$sanitized_build" -Db_sanitize=address,undefined
meson compile -C "$sanitized_build" test-goodix-nbis-resize-quality-pipe >/dev/null
sanitized_helper="$sanitized_build/tests/test-goodix-nbis-resize-quality-pipe"
audit_helper "$sanitized_helper"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  python3 -B "$evaluator" --helper "$sanitized_helper" >"$work_dir/sanitized.json"
cmp "$work_dir/normal.json" "$work_dir/sanitized.json"

echo D279_41_NORMAL_AND_ASAN_UBSAN=PASS >&2
echo D279_41_PROTECTED_OR_BIOMETRIC_INPUT=false >&2
echo D279_41_PRODUCTION_USB_REACHED=false >&2
cat "$work_dir/normal.json"
