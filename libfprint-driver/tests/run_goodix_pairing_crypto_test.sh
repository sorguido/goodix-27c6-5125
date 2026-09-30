#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd -P)
[ "$#" -eq 0 ] || exit 2

if [ "${GOODIX_PAIRING_CRYPTO_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  exec flatpak run --user --unshare=network --nodevice=all \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_PAIRING_CRYPTO_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0"
fi

build=$(mktemp -d /tmp/goodix-pairing-crypto.XXXXXX)
trap 'find "$build" -depth -delete 2>/dev/null || true' EXIT HUP INT TERM
cflags=$(pkg-config --cflags glib-2.0 openssl)
libs=$(pkg-config --libs glib-2.0 openssl)
strict="-std=gnu11 -O2 -g -DGOODIX_ENABLE_TEST_SEAMS -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
sources="$root/libfprint-driver/goodix_pairing_crypto.c $script_dir/test_goodix_pairing_crypto.c"

run_build () {
  name=$1
  extra=$2
  # shellcheck disable=SC2086
  cc $strict $extra $cflags -I"$root/libfprint-driver" $sources $libs \
    -o "$build/$name"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 60 "$build/$name"
}

run_build pairing_crypto_normal ""
echo PAIRING_CRYPTO_NORMAL=PASS
run_build pairing_crypto_sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo PAIRING_CRYPTO_ASAN_UBSAN=PASS
echo PAIRING_CRYPTO_OFFLINE_TEST=PASS
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
