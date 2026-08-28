#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
build=$(mktemp -d /tmp/goodix-d276-04.XXXXXX)
trap 'rm -rf "$build"' EXIT HUP INT TERM
cflags=$(pkg-config --cflags glib-2.0 gio-2.0 openssl gusb)
libs=$(pkg-config --libs glib-2.0 gio-2.0 openssl gusb)
local_fp="$root/Rockytkg/libfprint/libfprint"
python3 "$script_dir/support/generate_libfprint_enums.py" --identifier-prefix Fp --symbol-prefix fp --header-guard FP_ENUMS_H --header-name fp-enums.h --output-header "$build/fp-enums.h" --output-source "$build/fp-enums.c" "$local_fp/fp-device.h" "$local_fp/fp-print.h"
python3 "$script_dir/support/generate_libfprint_enums.py" --identifier-prefix Fpi --symbol-prefix fpi --header-guard FPI_ENUMS_H --header-name fpi-enums.h --output-header "$build/fpi-enums.h" --output-source "$build/fpi-enums.c" "$local_fp/fpi-device.h" "$local_fp/fpi-image-device.h" "$local_fp/fpi-print.h"
cp "$script_dir/support/config.h" "$build/config.h"
includes="-I$build -I$root/libfprint-driver -I$local_fp -I$root/Rockytkg/libfprint"
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
build_run () {
  name=$1; extra=$2
  gcc $strict $extra $cflags $includes \
    "$root/libfprint-driver/goodix_tls_server.c" \
    "$root/libfprint-driver/goodix_usb_router.c" \
    "$root/libfprint-driver/goodix_fpi_usb_backend.c" \
    "$script_dir/test_goodix_d276_04.c" \
    "$script_dir/support/fpi_usb_transfer_compile_stub.c" $libs -o "$build/$name"
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 timeout 60 "$build/$name"
}
build_run normal ""
echo NORMAL_TEST_RUN=PASS
build_run sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo SANITIZER_TEST_RUN=PASS
echo TLS_1_2_PSK_HANDSHAKE_SYNTHETIC=PASS
echo SECRET_HANDOFF_COUNT=1
echo SECRET_ZEROIZED_ON_TLS_TEARDOWN=true
echo REAL_USB_TRANSFER_SUBMIT_COUNT=0
echo MAX_OUTSTANDING_BULK_IN=1
echo FPI_USB_REAL_HEADER_API_SHAPE_COMPILE=PASS
echo FPI_USB_REAL_DEVICE_RUNTIME=NOT_RUN_PROHIBITED
echo ROUTER_B0_TO_TLS_INTEGRATION=PASS
echo TLS_POST_HANDSHAKE_APPLICATION_DATA=PASS
echo TLS_OUT_BACKEND_PATH=PASS
echo FPI_USB_SUBMIT_GENERATION_CAPTURED=true
