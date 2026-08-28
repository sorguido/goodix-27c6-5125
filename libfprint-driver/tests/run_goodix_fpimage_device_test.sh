#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
git_root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_dir=$(mktemp -d /tmp/goodix-d276-fpimage-device.XXXXXX)

cleanup ()
{
  if [ "${KEEP_BUILD:-0}" = "1" ]; then
    echo "KEEP_BUILD: build artifacts left in $build_dir"
    return
  fi
  find "$build_dir" -maxdepth 1 -type f -delete 2>/dev/null || true
  rmdir "$build_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

flatpak run --user --unshare=network \
  --filesystem="$git_root" \
  --filesystem=/tmp \
  --command=sh org.freedesktop.Sdk//25.08 -c '
set -eu

git_root=$1
build_dir=$2
shift 2
local_fp_dir="$git_root/Rockytkg/libfprint/libfprint"
test_dir="$git_root/libfprint-driver/tests"

glib_cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0)
glib_libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0)
includes="-I$test_dir/support -I$git_root/libfprint-driver -I$git_root/Rockytkg/libfprint -I$local_fp_dir -I$local_fp_dir/nbis/include -I$local_fp_dir/nbis/libfprint-include -I$build_dir"
strict_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion -ffunction-sections -fdata-sections"
local_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter -Wno-missing-prototypes -Wno-discarded-qualifiers -Wno-sign-compare -Wno-cast-function-type -Wno-enum-conversion -Wno-maybe-uninitialized -ffunction-sections -fdata-sections"

# ---- Generated enum registrations (host-only Python shim) ----
python3 "$test_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fpi --symbol-prefix fpi \
  --header-guard FPI_ENUMS_H --header-name fpi-enums.h \
  --output-header "$build_dir/fpi-enums.h" \
  --output-source "$build_dir/fpi-enums.c" \
  "$local_fp_dir/fpi-device.h" \
  "$local_fp_dir/fpi-image-device.h" \
  "$local_fp_dir/fpi-print.h"

python3 "$test_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fp --symbol-prefix fp \
  --header-guard FP_ENUMS_H --header-name fp-enums.h \
  --output-header "$build_dir/fp-enums.h" \
  --output-source "$build_dir/fp-enums.c" \
  "$local_fp_dir/fp-device.h" \
  "$local_fp_dir/fp-print.h"

# ---- libfprint core subset needed for real FpImageDevice actions ----
compile_libfprint() {
  gcc $local_flags $glib_cflags $includes -c "$1" -o "$2"
}

compile_libfprint "$local_fp_dir/fp-device.c"       "$build_dir/fp-device.o"
compile_libfprint "$local_fp_dir/fpi-device.c"      "$build_dir/fpi-device.o"
compile_libfprint "$local_fp_dir/fp-image-device.c" "$build_dir/fp-image-device.o"
compile_libfprint "$local_fp_dir/fpi-image-device.c" "$build_dir/fpi-image-device.o"
compile_libfprint "$local_fp_dir/fp-image.c"        "$build_dir/fp-image.o"
compile_libfprint "$local_fp_dir/fp-print.c"        "$build_dir/fp-print.o"
compile_libfprint "$local_fp_dir/fpi-print.c"       "$build_dir/fpi-print.o"
compile_libfprint "$build_dir/fpi-enums.c"          "$build_dir/fpi-enums.o"
compile_libfprint "$build_dir/fp-enums.c"           "$build_dir/fp-enums.o"

# ---- Project code ----
gcc $strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_u16_to_fpimage.c" \
  -o "$build_dir/goodix_u16_to_fpimage.o"
gcc $strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_fpimage_pipeline.c" \
  -o "$build_dir/goodix_fpimage_pipeline.o"
gcc $strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_fpimage_device.c" \
  -o "$build_dir/goodix_fpimage_device.o"
gcc $strict_flags $glib_cflags $includes -c \
  "$test_dir/test_goodix_fpimage_device.c" \
  -o "$build_dir/test_goodix_fpimage_device.o"

# ---- Host-only test seams ----
gcc $local_flags $glib_cflags $includes -c \
  "$test_dir/support/gusb_stub.c" \
  -o "$build_dir/gusb_stub.o"
gcc $local_flags $glib_cflags $includes -c \
  "$test_dir/support/fpimage_link_stubs.c" \
  -o "$build_dir/fpimage_link_stubs.o"

# ---- Forbidden-symbol audit on the fake backend / shell ----
if nm -u "$build_dir/goodix_fpimage_device.o" | \
     grep -E "(^|[[:space:]])(libusb_|usb_|fopen|open|read|write|socket|SSL_|mbedtls_|gnutls_)"; then
  echo "forbidden I/O, USB, or TLS symbol in Goodix FpImageDevice shell" >&2
  exit 1
fi
echo "goodix_fpimage_device forbidden-symbol audit: PASS"

# ---- Link ----
gcc -Wl,--gc-sections \
  "$build_dir/fp-device.o" \
  "$build_dir/fpi-device.o" \
  "$build_dir/fp-image-device.o" \
  "$build_dir/fpi-image-device.o" \
  "$build_dir/fp-image.o" \
  "$build_dir/fp-print.o" \
  "$build_dir/fpi-print.o" \
  "$build_dir/fpi-enums.o" \
  "$build_dir/fp-enums.o" \
  "$build_dir/goodix_u16_to_fpimage.o" \
  "$build_dir/goodix_fpimage_pipeline.o" \
  "$build_dir/goodix_fpimage_device.o" \
  "$build_dir/test_goodix_fpimage_device.o" \
  "$build_dir/gusb_stub.o" \
  "$build_dir/fpimage_link_stubs.o" \
  $glib_libs -lm -o "$build_dir/test_goodix_fpimage_device"

set +e
timeout --signal=TERM 30 "$build_dir/test_goodix_fpimage_device" "$@"
normal_rc=$?
case $normal_rc in
  0) echo "Normal test run: PASS" ;;
  124) echo "Normal test run: TIMEOUT" >&2 ;;
  134) echo "Normal test run: ABORT/assertion failure" >&2 ;;
  *) echo "Normal test run: FAIL/crash (exit $normal_rc)" >&2 ;;
esac
set -e

echo "Running address/undefined-behavior sanitized build..."
san_common="-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
san_strict_flags="$strict_flags $san_common"
san_local_flags="$local_flags $san_common"

compile_libfprint_san() {
  gcc $san_local_flags $glib_cflags $includes -c "$1" -o "$2"
}

compile_libfprint_san "$local_fp_dir/fp-device.c"       "$build_dir/fp-device_san.o"
compile_libfprint_san "$local_fp_dir/fpi-device.c"      "$build_dir/fpi-device_san.o"
compile_libfprint_san "$local_fp_dir/fp-image-device.c" "$build_dir/fp-image-device_san.o"
compile_libfprint_san "$local_fp_dir/fpi-image-device.c" "$build_dir/fpi-image-device_san.o"
compile_libfprint_san "$local_fp_dir/fp-image.c"        "$build_dir/fp-image_san.o"
compile_libfprint_san "$local_fp_dir/fp-print.c"        "$build_dir/fp-print_san.o"
compile_libfprint_san "$local_fp_dir/fpi-print.c"       "$build_dir/fpi-print_san.o"
compile_libfprint_san "$build_dir/fpi-enums.c"          "$build_dir/fpi-enums_san.o"
compile_libfprint_san "$build_dir/fp-enums.c"           "$build_dir/fp-enums_san.o"

gcc $san_strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_u16_to_fpimage.c" \
  -o "$build_dir/goodix_u16_to_fpimage_san.o"
gcc $san_strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_fpimage_pipeline.c" \
  -o "$build_dir/goodix_fpimage_pipeline_san.o"
gcc $san_strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_fpimage_device.c" \
  -o "$build_dir/goodix_fpimage_device_san.o"
gcc $san_strict_flags $glib_cflags $includes -c \
  "$test_dir/test_goodix_fpimage_device.c" \
  -o "$build_dir/test_goodix_fpimage_device_san.o"
gcc $san_local_flags $glib_cflags $includes -c \
  "$test_dir/support/gusb_stub.c" \
  -o "$build_dir/gusb_stub_san.o"
gcc $san_local_flags $glib_cflags $includes -c \
  "$test_dir/support/fpimage_link_stubs.c" \
  -o "$build_dir/fpimage_link_stubs_san.o"

gcc $san_common -Wl,--gc-sections \
  "$build_dir/fp-device_san.o" \
  "$build_dir/fpi-device_san.o" \
  "$build_dir/fp-image-device_san.o" \
  "$build_dir/fpi-image-device_san.o" \
  "$build_dir/fp-image_san.o" \
  "$build_dir/fp-print_san.o" \
  "$build_dir/fpi-print_san.o" \
  "$build_dir/fpi-enums_san.o" \
  "$build_dir/fp-enums_san.o" \
  "$build_dir/goodix_u16_to_fpimage_san.o" \
  "$build_dir/goodix_fpimage_pipeline_san.o" \
  "$build_dir/goodix_fpimage_device_san.o" \
  "$build_dir/test_goodix_fpimage_device_san.o" \
  "$build_dir/gusb_stub_san.o" \
  "$build_dir/fpimage_link_stubs_san.o" \
  $glib_libs -lm -o "$build_dir/test_goodix_fpimage_device_sanitized"

set +e
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1 \
  timeout --signal=TERM 30 "$build_dir/test_goodix_fpimage_device_sanitized" "$@"
san_rc=$?
case $san_rc in
  0) echo "Sanitizer test run: PASS" ;;
  124) echo "Sanitizer test run: TIMEOUT" >&2 ;;
  134) echo "Sanitizer test run: ABORT/assertion failure" >&2 ;;
  *) echo "Sanitizer test run: FAIL/crash/sanitizer finding (exit $san_rc)" >&2 ;;
esac
set -e

if [ "$normal_rc" -ne 0 ] || [ "$san_rc" -ne 0 ]; then
  exit 1
fi
' d276-fpimage-device "$git_root" "$build_dir" "$@"
