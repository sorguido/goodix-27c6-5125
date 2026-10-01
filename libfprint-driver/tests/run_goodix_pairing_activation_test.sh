#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
build_dir=${1:-/tmp/goodix-pairing-activation-test}

if [ "${GOODIX_PAIRING_ACTIVATION_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  exec flatpak run --user --unshare=network --nodevice=all \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_PAIRING_ACTIVATION_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0" "$@"
fi

mkdir -p "$build_dir"
common_flags="-std=c11 -Wall -Wextra -Werror -D_GNU_SOURCE -DGOODIX_ENABLE_TEST_SEAMS"
sources="$root/libfprint-driver/goodix_a0_protocol.c
$root/libfprint-driver/goodix_bb010002.c
$root/libfprint-driver/goodix_pairing_crypto.c
$root/libfprint-driver/goodix_pairing_provision.c
$root/libfprint-driver/goodix_self_state.c
$root/libfprint-driver/goodix_pairing_activation.c
$script_dir/test_goodix_pairing_activation.c"
libs=$(pkg-config --cflags --libs glib-2.0 gio-2.0 openssl)

# shellcheck disable=SC2086
cc $common_flags \
  -I"$root/libfprint-driver" $sources $libs \
  -o "$build_dir/test_goodix_pairing_activation"
"$build_dir/test_goodix_pairing_activation"

# shellcheck disable=SC2086
cc $common_flags -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I"$root/libfprint-driver" $sources $libs \
  -o "$build_dir/test_goodix_pairing_activation_san"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1 \
  "$build_dir/test_goodix_pairing_activation_san"
