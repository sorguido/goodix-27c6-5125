#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <repository-root> <build-root> <pkgconfig-dir> <sanitizers>" >&2
  exit 2
fi

repo_root=$1
build_root=$2
pkgconfig_dir=$3
sanitizers=$4
source_root="$repo_root/reference/libfprint-fedora44-1.94.100/source"
meson_build="$build_root/meson"
objects="$build_root/objects"
test_binary="$build_root/test-goodix-fedora44-sigfm-print"

export PKG_CONFIG_PATH=$pkgconfig_dir

grep -F 'fp_image_detect_sigfm (' \
  "$source_root/libfprint/fpi-image-device.c" >/dev/null
grep -F 'fpi_image_device_add_enroll_sample_checked (' \
  "$source_root/libfprint/fpi-image-device.c" >/dev/null
if grep -F 'fpi_print_add_print (enroll_print, print)' \
     "$source_root/libfprint/fpi-image-device.c" >/dev/null; then
  echo "unchecked enrollment append remains in FpImageDevice" >&2
  exit 1
fi
grep -F 'img_class->algorithm    = FPI_DEVICE_ALGO_SIGFM' \
  "$repo_root/libfprint-driver/goodix_fpimage_device.c" >/dev/null
echo D279_52_SIGFM_ACTION_DISPATCH_SOURCE_AUDIT=PASS
mkdir -p "$objects"
meson setup "$meson_build" "$source_root" \
  -Ddrivers=virtual_image \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled
ninja -C "$meson_build" --quiet libfprint/libfprint-2.so.2.0.0

includes="-I$source_root -I$source_root/libfprint -I$source_root/libfprint/nbis/include -I$source_root/libfprint/nbis/libfprint-include -I$meson_build -I$meson_build/libfprint -I$repo_root/libfprint-driver -I$repo_root/libfprint-driver/tests"
cflags="-std=c11 -O1 -g -fPIC -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wno-unused-parameter -Wno-sign-compare -DGOODIX_LIBFPRINT_SIGFM"
cxxflags="-std=c++17 -O1 -g -fPIC -ffunction-sections -fdata-sections -Wall -Wextra -Werror -DGOODIX_LIBFPRINT_SIGFM"
san=
if [ "$sanitizers" = yes ]; then
  san="-fno-omit-frame-pointer -fsanitize=address,undefined"
fi
glib_cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0 gusb)
glib_libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0)

cc $cflags $san $includes $glib_cflags \
  -c "$source_root/libfprint/fp-print.c" -o "$objects/fp-print.o"
cc $cflags $san $includes $glib_cflags \
  -c "$source_root/libfprint/fpi-print.c" -o "$objects/fpi-print.o"
cc $cflags $san $includes $glib_cflags \
  -c "$meson_build/libfprint/fpi-enums.c" -o "$objects/fpi-enums.o"
cc $cflags $san $includes \
  -c "$repo_root/libfprint-driver/goodix_u16_to_fpimage.c" \
  -o "$objects/goodix_u16_to_fpimage.o"
c++ $cxxflags $san $includes \
  -I"$repo_root/Rockytkg/libfprint/libfprint/sigfm" \
  -c "$repo_root/libfprint-driver/goodix_sigfm_metrics.cpp" \
  -o "$objects/goodix_sigfm_metrics.o"
c++ $cxxflags $san $includes \
  -I"$repo_root/Rockytkg/libfprint/libfprint/sigfm" \
  -c "$repo_root/libfprint-driver/tests/support/sigfm_metric_test_double.cpp" \
  -o "$objects/sigfm_double.o"
cc $cflags $san $includes $glib_cflags \
  -c "$repo_root/libfprint-driver/tests/test_goodix_fedora44_sigfm_print.c" \
  -o "$objects/test.o"

c++ $san -Wl,--gc-sections \
  "$objects/fp-print.o" "$objects/fpi-print.o" "$objects/fpi-enums.o" \
  "$objects/goodix_u16_to_fpimage.o" "$objects/goodix_sigfm_metrics.o" \
  "$objects/sigfm_double.o" "$objects/test.o" \
  -L"$meson_build/libfprint" -lfprint-2 $glib_libs \
  -Wl,-rpath,"$meson_build/libfprint" -o "$test_binary"

if [ "$sanitizers" = yes ]; then
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  G_DEBUG=fatal-warnings "$test_binary"
else
  G_DEBUG=fatal-warnings "$test_binary"
fi

echo D279_51_FEDORA44_SIGFM_PRINT_CORE=PASS
echo D279_51_FP3_STRICT_MULTI_SAMPLE=PASS
echo D279_51_CORRUPTION_AND_SAMPLE_BOUNDS=PASS
echo D279_52_CHECKED_APPEND_ATOMIC=PASS
echo D279_52_ENROLL_STAGE_STABLE_ON_COPY_FAILURE=PASS
echo D279_51_REAL_USB_ACCESS=0
