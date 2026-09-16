#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
git_root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_dir=$(mktemp -d /tmp/goodix-d270-fpimage.XXXXXX)

cleanup ()
{
  find "$build_dir" -maxdepth 1 -type f -delete
  rmdir "$build_dir"
}
trap cleanup EXIT HUP INT TERM

flatpak run --user --unshare=network \
  --filesystem="$git_root" \
  --filesystem=/tmp \
  --command=sh org.freedesktop.Sdk//25.08 -c '
set -eu

git_root=$1
build_dir=$2
local_fp_dir="$git_root/Rockytkg/libfprint/libfprint"
test_dir="$git_root/libfprint-driver/tests"
glib_cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0)
glib_libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0)
includes="-I$test_dir/support -I$git_root/libfprint-driver -I$git_root/Rockytkg/libfprint -I$local_fp_dir -I$local_fp_dir/nbis/include -I$local_fp_dir/nbis/libfprint-include"
strict_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion -ffunction-sections -fdata-sections"
local_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter -ffunction-sections -fdata-sections"

gcc $strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_u16_to_fpimage.c" \
  -o "$build_dir/goodix_u16_to_fpimage.o"
gcc $strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_fpimage_pipeline.c" \
  -o "$build_dir/goodix_fpimage_pipeline.o"
if nm -u "$build_dir/goodix_fpimage_pipeline.o" | \
     grep -E "(^|[[:space:]])(libusb_|usb_|fopen|open|read|write|socket|SSL_|mbedtls_|gnutls_)"; then
  echo "forbidden I/O, USB, or TLS symbol in production helper" >&2
  exit 1
fi
echo "goodix_fpimage_pipeline forbidden-symbol audit: PASS"
gcc $strict_flags $glib_cflags $includes -c \
  "$test_dir/test_goodix_fpimage_pipeline.c" \
  -o "$build_dir/test_goodix_fpimage_pipeline.o"
gcc $local_flags $glib_cflags $includes -c \
  "$local_fp_dir/fp-image.c" \
  -o "$build_dir/fp-image-local.o"
gcc $local_flags $glib_cflags $includes -c \
  "$test_dir/support/fpimage_link_stubs.c" \
  -o "$build_dir/fpimage_link_stubs.o"
gcc -Wl,--gc-sections \
  "$build_dir/goodix_u16_to_fpimage.o" \
  "$build_dir/goodix_fpimage_pipeline.o" \
  "$build_dir/test_goodix_fpimage_pipeline.o" \
  "$build_dir/fp-image-local.o" \
  "$build_dir/fpimage_link_stubs.o" \
  $glib_libs -o "$build_dir/test_goodix_fpimage_pipeline"
"$build_dir/test_goodix_fpimage_pipeline"

san_common="-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
san_strict_flags="$strict_flags $san_common"
san_local_flags="$local_flags $san_common"
gcc $san_strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_u16_to_fpimage.c" \
  -o "$build_dir/goodix_u16_to_fpimage_san.o"
gcc $san_strict_flags $glib_cflags $includes -c \
  "$git_root/libfprint-driver/goodix_fpimage_pipeline.c" \
  -o "$build_dir/goodix_fpimage_pipeline_san.o"
gcc $san_strict_flags $glib_cflags $includes -c \
  "$test_dir/test_goodix_fpimage_pipeline.c" \
  -o "$build_dir/test_goodix_fpimage_pipeline_san.o"
gcc $san_local_flags $glib_cflags $includes -c \
  "$local_fp_dir/fp-image.c" \
  -o "$build_dir/fp-image-local_san.o"
gcc $san_local_flags $glib_cflags $includes -c \
  "$test_dir/support/fpimage_link_stubs.c" \
  -o "$build_dir/fpimage_link_stubs_san.o"
gcc $san_common -Wl,--gc-sections \
  "$build_dir/goodix_u16_to_fpimage_san.o" \
  "$build_dir/goodix_fpimage_pipeline_san.o" \
  "$build_dir/test_goodix_fpimage_pipeline_san.o" \
  "$build_dir/fp-image-local_san.o" \
  "$build_dir/fpimage_link_stubs_san.o" \
  $glib_libs -o "$build_dir/test_goodix_fpimage_pipeline_sanitized"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1 \
  "$build_dir/test_goodix_fpimage_pipeline_sanitized"
' d270-test "$git_root" "$build_dir"
