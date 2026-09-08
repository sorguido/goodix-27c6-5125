#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

repo_root=$1
build_root=$2
pkgconfig_dir=$3
opencv_prefix=$4
source_root="$repo_root/reference/libfprint-fedora44-1.94.100/source"
meson_build="$build_root/meson"
objects="$build_root/objects"

export PKG_CONFIG_PATH=$pkgconfig_dir
mkdir -p "$objects"
meson setup "$meson_build" "$source_root" \
  -Ddrivers=goodix_27c6_5125 -Dintrospection=true -Ddoc=false \
  -Dinstalled-tests=false -Dudev_rules=disabled -Dudev_hwdb=disabled
ninja -C "$meson_build" --quiet libfprint/libfprint-2.so.2.0.0

compile_db="$meson_build/compile_commands.json"
grep -F -- '-DGOODIX_LIBFPRINT_SIGFM' "$compile_db" >/dev/null
grep -F 'goodix_sigfm_preprocess.c' "$compile_db" >/dev/null
grep -F 'rockytkg-imgproc/goodix_imgproc.c' "$compile_db" >/dev/null
grep -F 'goodix_sigfm_metrics.cpp' "$compile_db" >/dev/null
grep -F 'Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp' "$compile_db" >/dev/null
readelf -d "$meson_build/libfprint/libfprint-2.so.2.0.0" | \
  grep -F 'libopencv_features2d.so.413' >/dev/null
echo D279_52_PRODUCTION_MESON_SIGFM_SOURCE_CLOSURE=PASS

includes="-I$source_root -I$source_root/libfprint -I$source_root/libfprint/nbis/include -I$source_root/libfprint/nbis/libfprint-include -I$meson_build -I$meson_build/libfprint -I$repo_root/libfprint-driver -I$repo_root/libfprint-driver/tests -I$repo_root/Rockytkg/libfprint/libfprint/sigfm -I$opencv_prefix/usr/include/opencv4"
cflags="-std=c11 -O2 -g -fPIC -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wno-unused-parameter -Wno-sign-compare -DGOODIX_LIBFPRINT_SIGFM"
cxxflags="-std=c++17 -O2 -g -fPIC -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wconversion -Wshadow -Wold-style-cast"
dep_cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0 gusb)

cc $cflags $includes $dep_cflags -c "$source_root/libfprint/fp-print.c" -o "$objects/fp-print.o"
cc $cflags $includes $dep_cflags -c "$source_root/libfprint/fpi-print.c" -o "$objects/fpi-print.o"
cc $cflags $includes $dep_cflags -c "$meson_build/libfprint/fpi-enums.c" -o "$objects/fpi-enums.o"
cc $cflags $includes -c "$repo_root/libfprint-driver/goodix_u16_to_fpimage.c" -o "$objects/adapter.o"
c++ $cxxflags $includes -c "$repo_root/libfprint-driver/goodix_sigfm_metrics.cpp" -o "$objects/metrics.o"
c++ -std=c++17 -O2 -g -fPIC -ffunction-sections -fdata-sections $includes \
  -c "$repo_root/Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp" -o "$objects/sigfm.o"
cc $cflags $includes $dep_cflags \
  -c "$repo_root/libfprint-driver/tests/test_goodix_fedora44_sigfm_print_real.c" \
  -o "$objects/test.o"
