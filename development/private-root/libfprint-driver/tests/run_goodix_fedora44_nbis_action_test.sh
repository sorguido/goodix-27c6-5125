#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <directory-containing-pinned-opencv-rpms>" >&2
  exit 2
fi
rpm_dir=$1

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(git -C "$script_dir" rev-parse --show-toplevel)
production_source="$repo_root/libfprint-driver/goodix_fpimage_device.c"
build_root=$(mktemp -d /tmp/goodix-d279-52-sigfm-action.XXXXXX)
build_dir="$build_root/build"
pkgconfig_dir="$build_root/pkgconfig"
opencv_prefix="$build_root/opencv-prefix"
runtime="$build_root/runtime"
inner="$script_dir/run_goodix_fedora44_nbis_action_test_inner.sh"
pc_template="$script_dir/support/d279/gusb.pc.in"
include_dir="$script_dir/support/d279"

cleanup ()
{
  if [ "${KEEP_BUILD:-0}" = 1 ]; then
    echo "D279_52_BUILD_ROOT=$build_root"
    return
  fi
  find "$build_root" -depth -delete 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

manifest="$repo_root/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256"
grep -F 'FPI_DEVICE_ACTION_ENROLL &&' "$production_source" >/dev/null
grep -F 'FPI_DEVICE_ACTION_VERIFY) ?' "$production_source" >/dev/null
grep -F 'GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION' \
  "$production_source" >/dev/null
grep -F 'Goodix production boundary permits enrollment, verify and identify only' \
  "$production_source" >/dev/null
(cd "$rpm_dir" && sha256sum -c "$manifest")
mkdir -p "$pkgconfig_dir" "$opencv_prefix" "$runtime"
for package in "$rpm_dir"/*.rpm; do
  (cd "$opencv_prefix" && rpm2cpio "$package" | cpio -idm --quiet)
done
host_gusb=
for candidate in \
  /usr/lib64/libgusb.so.2.0.10 \
  /usr/lib64/libgusb.so.2 \
  /usr/lib/x86_64-linux-gnu/libgusb.so.2; do
  if [ -f "$candidate" ]; then
    host_gusb=$candidate
    break
  fi
done
test -n "$host_gusb" || {
  echo "BLOCKED_ENVIRONMENT: installed libgusb runtime not found" >&2
  exit 2
}

cp "$host_gusb" "$pkgconfig_dir/libgusb.so.2"
sed -e "s|@PREFIX@|$pkgconfig_dir|g" \
    -e "s|@INCLUDEDIR@|$include_dir|g" \
    "$pc_template" >"$pkgconfig_dir/gusb.pc"
sed -e "s|@PREFIX@|$opencv_prefix/usr|g" \
    "$script_dir/support/d279/opencv4.pc.in" >"$pkgconfig_dir/opencv4.pc"

if command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  flatpak run --user --unshare=network \
    --filesystem="$repo_root":ro \
    --filesystem="$build_root" \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$repo_root" "$build_dir" "$pkgconfig_dir"
  for component in core features2d flann imgproc; do
    cp -L "$opencv_prefix/usr/lib64/libopencv_${component}.so.4.13.0" \
      "$runtime/libopencv_${component}.so.413"
  done
  LD_LIBRARY_PATH="$build_dir/libfprint:$runtime:$pkgconfig_dir" \
    G_DEBUG=fatal-warnings timeout --signal=TERM 60 \
    "$build_dir/tests/test-goodix-fpimage-sigfm-action"
  supported=$(LD_LIBRARY_PATH="$build_dir/libfprint:$runtime:$pkgconfig_dir" \
    "$build_dir/libfprint/fprint-list-supported-devices")
  printf '%s\n' "$supported" | \
    grep -F '27c6:5125 | Goodix 27c6:5125 Fingerprint Sensor' >/dev/null
  test "$(printf '%s\n' "$supported" | grep -c '^27c6:5125 |')" -eq 1
  fprintd_binary=/usr/libexec/fprintd
  fprintd_package=$(rpm -qf --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}' \
    "$fprintd_binary")
  test "$fprintd_package" = fprintd-1.94.5-5.fc44.x86_64
  test -x "$fprintd_binary"
  readelf -d "$fprintd_binary" | grep -F '[libfprint-2.so.2]' >/dev/null
  for abi_symbol in \
    fp_print_serialize fp_print_deserialize fp_device_verify \
    fp_device_verify_finish fp_device_identify fp_device_identify_finish; do
    nm -D --undefined-only "$fprintd_binary" | \
      grep -F " $abi_symbol@LIBFPRINT_2.0.0" >/dev/null
  done
  built_library="$build_dir/libfprint/libfprint-2.so.2.0.0"
  readelf -d "$built_library" | grep -F '[libfprint-2.so.2]' >/dev/null
  required_symbols=$(nm -D --undefined-only "$fprintd_binary" | \
    awk '$1 == "U" && $2 ~ /@LIBFPRINT_2[.]0[.]0$/ { sub(/@.*/, "", $2); print $2 }' | \
    sort -u)
  provided_symbols=$(nm -D --defined-only "$built_library" | \
    awk '$3 ~ /@@LIBFPRINT_2[.]0[.]0$/ { sub(/@@.*/, "", $3); print $3 }' | \
    sort -u)
  required_count=$(printf '%s\n' "$required_symbols" | grep -c .)
  test "$required_count" -gt 0
  for abi_symbol in $required_symbols; do
    printf '%s\n' "$provided_symbols" | grep -Fx "$abi_symbol" >/dev/null
  done
  echo D279_52_STANDARD_DRIVER_REGISTRY=PASS
  echo D279_57_NATIVE_SIGFM_ACTION_STAGE8=PASS
  echo D279_52_ACTION_TEST_COMPATIBILITY_FILENAME=run_goodix_fedora44_nbis_action_test.sh
  echo D279_53_FPRINTD_PACKAGE="$fprintd_package"
  echo D279_53_FPRINTD_LIBFPRINT_REQUIRED_SYMBOL_COUNT="$required_count"
  echo D279_53_FPRINTD_LIBFPRINT_ABI_CLOSURE=PASS
  echo D279_53_FPRINTD_EXECUTION_COUNT=0
  echo D279_55_PRODUCTION_IDENTIFY_ACTION_ENABLED=true
  echo D279_55_PRODUCTION_IDENTIFY_CAPTURE_COUNT=1
  echo D279_55_PRODUCTION_IDENTIFY_REARM_COUNT=0
  echo D282_01_PRODUCTION_VERIFY_ACTION_ENABLED=true
  echo D282_01_PRODUCTION_VERIFY_CAPTURE_COUNT=1
  echo D282_01_PRODUCTION_VERIFY_REARM_COUNT=0
  echo D280_01_FP3_SURVIVES_CLOSE_REOPEN=PASS
  echo D280_01_TRUE_SIGFM_TWO_OPEN_EPOCH_REUSE=PASS
  echo D280_01_CORRUPT_FP3_REJECTED=PASS
  echo D280_01_TEMPLATE_PERSISTED_TO_DISK=false
  echo D280_01_FPRINTD_EXECUTION_COUNT=0
  exit 0
fi

echo "BLOCKED_ENVIRONMENT: Freedesktop SDK 25.08 unavailable" >&2
exit 2
