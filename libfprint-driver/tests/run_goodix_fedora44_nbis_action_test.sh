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
  echo D279_52_STANDARD_DRIVER_REGISTRY=PASS
  echo D279_52_NATIVE_SIGFM_ACTION_21_STAGE=PASS
  echo D279_52_ACTION_TEST_COMPATIBILITY_FILENAME=run_goodix_fedora44_nbis_action_test.sh
  exit 0
fi

echo "BLOCKED_ENVIRONMENT: Freedesktop SDK 25.08 unavailable" >&2
exit 2
