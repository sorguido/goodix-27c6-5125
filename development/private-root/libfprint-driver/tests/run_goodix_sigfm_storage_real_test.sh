#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Reproducible host-only closure for the real Rockytkg SIGFM implementation.
# Input is a directory containing the five Fedora 44 OpenCV RPMs pinned by the
# D279/48 manifest. RPMs are extracted under /tmp; nothing is installed.
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <directory-containing-pinned-opencv-rpms>" >&2
  exit 2
fi

export CCACHE_DISABLE=1
rpm_dir=$1
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
git_root=$(git -C "$script_dir" rev-parse --show-toplevel)
manifest="$git_root/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256"
build_dir=$(mktemp -d /tmp/goodix-sigfm-storage-real.XXXXXX)
prefix="$build_dir/opencv-prefix"
objects="$build_dir/objects"
runtime="$build_dir/runtime"

cleanup ()
{
  find "$build_dir" -depth -delete
}
trap cleanup EXIT HUP INT TERM

test -d "$rpm_dir"
(cd "$rpm_dir" && sha256sum -c "$manifest")
mkdir -p "$prefix" "$objects" "$runtime"
for package in "$rpm_dir"/*.rpm; do
  (cd "$prefix" && rpm2cpio "$package" | cpio -idm --quiet)
done

test "$(sha256sum "$git_root/Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp" |
  awk '{print $1}')" = 95ba50258d68a145841e3f51c4f9927ed5ec518e86f09b1222d725281f56c9c5

flatpak run --user --unshare=network \
  --filesystem="$git_root":ro --filesystem="$build_dir" \
  --command=sh org.freedesktop.Sdk//25.08 -c '
set -eu
root=$1
work=$2
inc="-I$root/libfprint-driver -I$root/Rockytkg/libfprint/libfprint/sigfm -I$work/opencv-prefix/usr/include/opencv4"
cflags="-std=c11 -O2 -g -fPIC -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wconversion"
cxxflags="-std=c++17 -O2 -g -fPIC -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wconversion -Wshadow -Wold-style-cast"
gcc $cflags $inc -c "$root/libfprint-driver/goodix_u16_to_fpimage.c" -o "$work/objects/adapter.o"
g++ $cxxflags $inc -c "$root/libfprint-driver/goodix_sigfm_metrics.cpp" -o "$work/objects/metrics.o"
g++ -std=c++17 -O2 -g -fPIC -ffunction-sections -fdata-sections $inc \
  -c "$root/Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp" -o "$work/objects/sigfm.o"
g++ $cxxflags $inc -c "$root/libfprint-driver/tests/test_goodix_sigfm_metrics_real.cpp" \
  -o "$work/objects/test.o"
' d279-50-real "$git_root" "$build_dir"

if nm -u "$objects/metrics.o" | awk '{print $NF}' |
   grep -E '^(fopen|open|read|write|socket|libusb_.*|g_usb_.*|SSL_.*|gnutls_.*|gx_.*)$'; then
  echo "D279_50_REAL_SIGFM_FORBIDDEN_SYMBOL_AUDIT=FAIL" >&2
  exit 1
fi
echo "D279_50_REAL_SIGFM_FORBIDDEN_SYMBOL_AUDIT=PASS"

for component in core features2d flann imgproc; do
  cp -L "$prefix/usr/lib64/libopencv_${component}.so.4.13.0" \
    "$runtime/libopencv_${component}.so.413"
done

test "$(rpm -q tbb)" = tbb-2022.3.0-3.fc44.x86_64
test "$(rpm -q flexiblas)" = flexiblas-3.5.0-2.fc44.x86_64
test "$(rpm -q flexiblas-netlib)" = flexiblas-netlib-3.5.0-2.fc44.x86_64

gcc "$objects/adapter.o" "$objects/metrics.o" "$objects/sigfm.o" \
  "$objects/test.o" -Wl,--gc-sections -Wl,--no-undefined \
  '-Wl,-rpath,$ORIGIN/runtime' \
  "$runtime/libopencv_features2d.so.413" \
  "$runtime/libopencv_flann.so.413" \
  "$runtime/libopencv_imgproc.so.413" \
  "$runtime/libopencv_core.so.413" \
  /usr/lib64/libtbb.so.12 /usr/lib64/libflexiblas.so.3 \
  /usr/lib64/libstdc++.so.6 -lm -o "$build_dir/test-real"

LD_LIBRARY_PATH="$runtime" "$build_dir/test-real"
echo "D279_50_REAL_SIGFM_STORAGE_EXECUTABLE_CLOSURE=PASS_HOST_ONLY"
