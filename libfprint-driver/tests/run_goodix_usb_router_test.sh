#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_dir=$(mktemp -d /tmp/goodix-d276-router.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM

cflags=$(pkg-config --cflags glib-2.0)
libs=$(pkg-config --libs glib-2.0)
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"

build_and_run () {
  suffix=$1
  extra=$2
  gcc $strict $extra $cflags -I"$root/libfprint-driver" \
    "$root/libfprint-driver/goodix_usb_router.c" \
    "$script_dir/test_goodix_usb_router.c" $libs \
    -o "$build_dir/router_test_$suffix"
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build_dir/router_test_$suffix"
}

build_and_run normal ""
echo "NORMAL_TEST_RUN=PASS"
build_and_run sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo "SANITIZER_TEST_RUN=PASS"
echo "PHYSICAL_RECEIVE_OWNER_COUNT=1"
echo "MAX_OUTSTANDING_RECEIVES=1"
echo "SECOND_READER_API_PATH=ABSENT"
echo "REAL_USB_ACCESS=false"
echo "LIVE_AUTHORIZED=false"
