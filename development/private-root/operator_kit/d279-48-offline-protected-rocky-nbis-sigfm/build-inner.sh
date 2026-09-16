#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <snapshot-root> <work-dir> <opencv-prefix> <pkgconfig-dir>" >&2
  exit 2
fi

snapshot_root=$1
work_dir=$2
opencv_prefix=$3
pkgconfig_dir=$4
source_root="$snapshot_root/reference/libfprint-fedora44-1.94.100/source"
runtime_dir="$work_dir/runtime"
include_dir="$work_dir/include/pixman-1"
kit_dir="$snapshot_root/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm"

export PKG_CONFIG_PATH=$pkgconfig_dir
pixman_version=$(pkg-config --modversion pixman-1)
pixman_libdir=$(pkg-config --variable=libdir pixman-1)
pixman_includedir=$(pkg-config --variable=includedir pixman-1)/pixman-1
test -f "$pixman_libdir/libpixman-1.so.0"
test -f "$pixman_includedir/pixman.h"
mkdir -p "$runtime_dir" "$include_dir" "$work_dir/objects"
cp -L "$pixman_libdir/libpixman-1.so.0" "$runtime_dir/libpixman-1.so"
cp -L "$pixman_libdir/libpixman-1.so.0" "$runtime_dir/libpixman-1.so.0"
cp -R "$pixman_includedir/." "$include_dir/"
chmod 0600 "$runtime_dir/libpixman-1.so" "$runtime_dir/libpixman-1.so.0"
sed -e "s|@PREFIX@|$runtime_dir|g" \
    -e "s|@INCLUDEDIR@|$include_dir|g" \
    -e "s|@VERSION@|$pixman_version|g" \
    "$kit_dir/pixman-1.pc.in" >"$pkgconfig_dir/pixman-1.pc"

export LD_LIBRARY_PATH=$runtime_dir
meson setup "$work_dir/nbis-build" "$source_root" \
  -Ddrivers=goodix_27c6_5125,aes3500 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled
meson compile -C "$work_dir/nbis-build" test-goodix-nbis-pair-pipe
grep -F 'test_goodix_nbis_pair_pipe.c' \
  "$work_dir/nbis-build/compile_commands.json" >/dev/null
cp "$work_dir/nbis-build/tests/test-goodix-nbis-pair-pipe" \
  "$work_dir/d279_nbis_pair.pending"

cc -std=c11 -O2 -g -flto -ffunction-sections -fdata-sections \
  -Wall -Wextra -Werror \
  -I"$snapshot_root/Rockytkg/include" \
  -include "$snapshot_root/analysis/D279/d279_48_rocky_imgproc_noenv.h" \
  -Dgetenv=d279_48_no_environment \
  "$snapshot_root/Rockytkg/src/goodix_imgproc.c" \
  "$snapshot_root/analysis/D279/d279_48_rocky_imgproc_pipe.c" \
  -Wl,--gc-sections -flto -lm -o "$work_dir/d279_rocky_imgproc.pending"

cxxflags="-std=c++17 -O2 -g -fPIC -ffunction-sections -fdata-sections -I$opencv_prefix/usr/include/opencv4 -I$snapshot_root/Rockytkg/libfprint/libfprint/sigfm"
# The preserved third-party file retains its own warning profile.  The local
# pipe wrapper is compiled strictly; both objects are linked on the Fedora 44
# host because Fedora OpenCV 4.13 requires glibc 2.43 while SDK 25.08 has 2.42.
c++ $cxxflags -c \
  "$snapshot_root/Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp" \
  -o "$work_dir/objects/sigfm.o"
c++ $cxxflags -Wall -Wextra -Werror -c \
  "$snapshot_root/libfprint-driver/tests/test_goodix_sigfm_pair_pipe.cpp" \
  -o "$work_dir/objects/sigfm-pipe.o"

chmod 0600 "$work_dir/d279_nbis_pair.pending" \
  "$work_dir/d279_rocky_imgproc.pending" \
  "$work_dir/objects/sigfm.o" "$work_dir/objects/sigfm-pipe.o"
echo D279_48_EXACT_TARGET_LIBFPRINT=1.94.100
echo "D279_48_PINNED_PIXMAN=$pixman_version"
echo D279_48_ROCKY_IMGPROC_OBJECT_SOURCE=227eba219fa9e3fbac5bd59aca79f624f67cd11b
echo D279_48_SIGFM_OBJECT_SOURCE=7ebe0c809b4d1df3400e84299a4ec4acdea84590
echo D279_48_INNER_BUILD=PASS
