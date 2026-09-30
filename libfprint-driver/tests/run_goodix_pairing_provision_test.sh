#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd -P)

if [ "${GOODIX_P6_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  exec flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_P6_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0" "$@"
fi

build_dir=${1:-"$(mktemp -d /tmp/goodix-pairing-provision.XXXXXX)"}
mkdir -p "$build_dir"

common_flags="-std=c11 -Wall -Wextra -Werror -I$root/libfprint-driver"
libs=$(pkg-config --cflags --libs glib-2.0 openssl)

cc $common_flags \
  "$root/libfprint-driver/goodix_a0_protocol.c" \
  "$root/libfprint-driver/goodix_bb010002.c" \
  "$root/libfprint-driver/goodix_pairing_provision.c" \
  "$script_dir/test_goodix_pairing_provision.c" \
  $libs -o "$build_dir/test-goodix-pairing-provision"
"$build_dir/test-goodix-pairing-provision"

cc $common_flags -fsanitize=address,undefined -fno-omit-frame-pointer \
  "$root/libfprint-driver/goodix_a0_protocol.c" \
  "$root/libfprint-driver/goodix_bb010002.c" \
  "$root/libfprint-driver/goodix_pairing_provision.c" \
  "$script_dir/test_goodix_pairing_provision.c" \
  $libs -o "$build_dir/test-goodix-pairing-provision-san"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1 \
  "$build_dir/test-goodix-pairing-provision-san"
