#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)

if [ "${GOODIX_D279_12_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  exec flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_D279_12_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0"
fi

build=$(mktemp -d /tmp/goodix-d279-12-fdt.XXXXXX)
trap 'find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true; rmdir "$build" 2>/dev/null || true' EXIT HUP INT TERM
cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0)
local_fp="$root/Rockytkg/libfprint/libfprint"
includes="-I$root/libfprint-driver -I$root/Rockytkg/libfprint -I$local_fp -I$local_fp/nbis/include -I$local_fp/nbis/libfprint-include"
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"

if grep -En '(goodix_fpi_usb|goodix_a0_build|fixed64_command|submit_out)' \
    "$root/libfprint-driver/goodix_enrollment_fdt_state.c" \
    "$root/libfprint-driver/goodix_enrollment_fdt_state.h"; then
  echo "wire-frame serializer or sender dependency in D279/12 FDT state" >&2
  exit 1
fi
echo D279_12_ZERO_SENDER_SOURCE_AUDIT=PASS

run_build () {
  name=$1
  extra=$2
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes \
    "$root/libfprint-driver/goodix_enrollment_fdt_state.c" \
    "$script_dir/test_goodix_enrollment_fdt_state.c" $libs \
    -o "$build/$name"
  if nm -u "$build/$name" | \
     grep -E '(^|[[:space:]])(g_usb_|libusb_|SSL_|mbedtls_|gnutls_|open|read|write|socket)'; then
    echo "forbidden I/O, USB or TLS symbol in D279/12 FDT state" >&2
    exit 1
  fi
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 timeout 30 "$build/$name"
}

run_build normal ""
echo D279_12_NORMAL=PASS
run_build sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D279_12_ASAN_UBSAN=PASS
echo TARGET_LOCAL_FDT_RELATIONS=PASS
echo RAW_TABLE_BYTES_EXPORTED=false
echo A0_FRAME_BUILD_COUNT=0
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
