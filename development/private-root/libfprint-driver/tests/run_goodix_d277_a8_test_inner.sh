#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <git-root> <build-dir> <host-libgusb>" >&2
  exit 2
fi
root=$1
build=$2
host_gusb=$3
test_dir="$root/libfprint-driver/tests"
local_fp="$root/Rockytkg/libfprint/libfprint"

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0)
strict="-std=gnu11 -O2 -g -DGOODIX_ENABLE_TEST_SEAMS -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion -ffunction-sections -fdata-sections"
includes="-I$test_dir/support/d277 -I$test_dir/support -I$root/libfprint-driver -I$root/Rockytkg/libfprint -I$local_fp -I$build"

python3 "$test_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fpi --symbol-prefix fpi \
  --header-guard FPI_ENUMS_H --header-name fpi-enums.h \
  --output-header "$build/fpi-enums.h" --output-source "$build/fpi-enums.c" \
  "$local_fp/fpi-device.h" "$local_fp/fpi-image-device.h" "$local_fp/fpi-print.h"
python3 "$test_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fp --symbol-prefix fp \
  --header-guard FP_ENUMS_H --header-name fp-enums.h \
  --output-header "$build/fp-enums.h" --output-source "$build/fp-enums.c" \
  "$local_fp/fp-device.h" "$local_fp/fp-print.h"
cp "$test_dir/support/config.h" "$build/config.h"

build_host_test () {
  name=$1
  extra=$2
  gcc $strict $extra $cflags $includes \
    "$root/libfprint-driver/goodix_usb_router.c" \
    "$root/libfprint-driver/goodix_fpi_usb_backend.c" \
    "$root/tools/d277_native_a8_once.c" \
    "$test_dir/support/fpi_usb_transfer_compile_stub.c" \
    $libs -Wl,--gc-sections -o "$build/$name"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build/$name" --self-test
}

build_host_test d277_a8_selftest ""
echo NORMAL_TEST_RUN=PASS
build_host_test d277_a8_selftest_sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo SANITIZER_TEST_RUN=PASS

test -f "$host_gusb"

local_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter -Wno-missing-prototypes -Wno-discarded-qualifiers -Wno-sign-compare -Wno-cast-function-type -Wno-enum-conversion -Wno-maybe-uninitialized -ffunction-sections -fdata-sections"
compile_local () { gcc $local_flags $cflags $includes -c "$1" -o "$2"; }
compile_local "$local_fp/fp-device.c" "$build/fp-device.o"
compile_local "$local_fp/fpi-device.c" "$build/fpi-device.o"
compile_local "$local_fp/fpi-usb-transfer.c" "$build/fpi-usb-transfer.o"
compile_local "$build/fp-enums.c" "$build/fp-enums.o"
compile_local "$build/fpi-enums.c" "$build/fpi-enums.o"

gcc $strict -DD277_LIVE_BINDING $cflags $includes -c \
  "$root/libfprint-driver/goodix_usb_router.c" -o "$build/goodix_usb_router.o"
gcc $strict -DD277_LIVE_BINDING $cflags $includes -c \
  "$root/libfprint-driver/goodix_fpi_usb_backend.c" -o "$build/goodix_fpi_usb_backend.o"
gcc $strict -DD277_LIVE_BINDING $cflags $includes -c \
  "$root/tools/d277_native_a8_once.c" -o "$build/d277_native_a8_once.o"

gcc -Wl,--gc-sections \
  "$build/fp-device.o" "$build/fpi-device.o" "$build/fpi-usb-transfer.o" \
  "$build/fp-enums.o" "$build/fpi-enums.o" \
  "$build/goodix_usb_router.o" "$build/goodix_fpi_usb_backend.o" \
  "$build/d277_native_a8_once.o" \
  -L"$build" -Wl,-rpath-link,"$build" -l:libgusb.so.2 $libs -lm \
  -o "$build/d277_native_a8_once"

echo LIVE_HARNESS_BUILD=PASS
echo LIVE_HARNESS_PATH="$build/d277_native_a8_once"
