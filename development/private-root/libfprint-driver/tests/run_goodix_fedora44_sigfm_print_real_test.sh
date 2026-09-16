#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <directory-containing-pinned-opencv-rpms>" >&2
  exit 2
fi

rpm_dir=$1
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(git -C "$script_dir" rev-parse --show-toplevel)
manifest="$repo_root/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256"
build_root=$(mktemp -d /tmp/goodix-d279-51-sigfm-print-real.XXXXXX)
opencv_prefix="$build_root/opencv-prefix"
runtime="$build_root/runtime"
pkgconfig_dir="$build_root/pkgconfig"
objects="$build_root/objects"
meson_build="$build_root/meson"

cleanup ()
{
  find "$build_root" -depth -delete 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

(cd "$rpm_dir" && sha256sum -c "$manifest")
mkdir -p "$opencv_prefix" "$runtime" "$pkgconfig_dir"
for package in "$rpm_dir"/*.rpm; do
  (cd "$opencv_prefix" && rpm2cpio "$package" | cpio -idm --quiet)
done
test "$(sha256sum "$repo_root/Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp" | awk '{print $1}')" = \
  95ba50258d68a145841e3f51c4f9927ed5ec518e86f09b1222d725281f56c9c5

host_gusb=/usr/lib64/libgusb.so.2
test -f "$host_gusb"
cp "$host_gusb" "$pkgconfig_dir/libgusb.so.2"
sed -e "s|@PREFIX@|$pkgconfig_dir|g" \
    -e "s|@INCLUDEDIR@|$script_dir/support/d279|g" \
    "$script_dir/support/d279/gusb.pc.in" >"$pkgconfig_dir/gusb.pc"
sed -e "s|@PREFIX@|$opencv_prefix/usr|g" \
    "$script_dir/support/d279/opencv4.pc.in" >"$pkgconfig_dir/opencv4.pc"

flatpak run --user --unshare=network \
  --filesystem="$repo_root":ro --filesystem="$build_root" \
  --command=sh org.freedesktop.Sdk//25.08 \
  "$script_dir/run_goodix_fedora44_sigfm_print_real_test_inner.sh" \
  "$repo_root" "$build_root" "$pkgconfig_dir" "$opencv_prefix"

for component in core features2d flann imgproc; do
  cp -L "$opencv_prefix/usr/lib64/libopencv_${component}.so.4.13.0" \
    "$runtime/libopencv_${component}.so.413"
done
test "$(rpm -q tbb)" = tbb-2022.3.0-3.fc44.x86_64
test "$(rpm -q flexiblas)" = flexiblas-3.5.0-2.fc44.x86_64
test "$(rpm -q flexiblas-netlib)" = flexiblas-netlib-3.5.0-2.fc44.x86_64

gcc "$objects/fp-print.o" "$objects/fpi-print.o" "$objects/fpi-enums.o" \
  "$objects/adapter.o" "$objects/preprocess.o" "$objects/imgproc.o" \
  "$objects/metrics.o" "$objects/sigfm.o" \
  "$objects/test.o" -Wl,--gc-sections -Wl,--no-undefined \
  '-Wl,-rpath,$ORIGIN/meson/libfprint:$ORIGIN/runtime:$ORIGIN/pkgconfig' \
  -L"$meson_build/libfprint" -l:libfprint-2.so.2.0.0 \
  "$runtime/libopencv_features2d.so.413" "$runtime/libopencv_flann.so.413" \
  "$runtime/libopencv_imgproc.so.413" "$runtime/libopencv_core.so.413" \
  /usr/lib64/libtbb.so.12 /usr/lib64/libflexiblas.so.3 \
  /usr/lib64/libstdc++.so.6 /usr/lib64/libgio-2.0.so.0 \
  /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libglib-2.0.so.0 \
  -lm -o "$build_root/test-real"

LD_LIBRARY_PATH="$meson_build/libfprint:$runtime:$pkgconfig_dir" \
  G_DEBUG=fatal-warnings "$build_root/test-real"
echo D279_51_REAL_ROCKY_SIGFM_SOURCE=PASS
echo D279_51_REAL_SIGFM_PRINT_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
echo D279_52_PRODUCTION_MESON_SIGFM_ENABLED=true
echo D279_52_IMAGE_ACTION_SIGFM_COMPILED=true
echo REAL_USB_ACCESS_COUNT=0
echo LIVE_EXECUTION_PERFORMED=false
