#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
if [ "${GOODIX_D278_02_IN_SDK:-0}" != 1 ] && command -v flatpak >/dev/null 2>&1 && flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
 exec flatpak run --user --unshare=network --filesystem="$root":ro --filesystem=/tmp --env=GOODIX_D278_02_IN_SDK=1 --command=sh org.freedesktop.Sdk//25.08 "$0"
fi
b=$(mktemp -d);trap 'rm -rf "$b"' EXIT
cflags="$(pkg-config --cflags glib-2.0 openssl) -I$root/libfprint-driver -I$root/tools"
libs=$(pkg-config --libs glib-2.0 openssl)
for mode in normal sanitized; do extra=""; [ "$mode" = normal ] || extra="-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"; gcc -std=gnu11 -O2 -g -Wall -Wextra -Werror $extra $cflags "$root/libfprint-driver/goodix_d190_binder.c" "$root/tools/goodix_d190_pe.c" "$root/libfprint-driver/tests/test_goodix_d278_02_material.c" $libs -o "$b/test"; GOODIX_CANONICAL_PE="$root/analysis/D230/work/GoodixExport/gfusb.dll" ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$b/test";done
echo D278_02_HOST_ONLY_RESULT=PASS
echo NATIVE_D190_E4_BINDER_KAT_PROVEN=true
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
echo CURRENT_LIVE_AUTHORIZED=false
