#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd -P)
[ "$#" -eq 0 ] || exit 2

if [ "${GOODIX_ENROLLMENT_DIVERSITY_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  exec flatpak run --user --unshare=network --nodevice=all \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_ENROLLMENT_DIVERSITY_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0"
fi

build=$(mktemp -d /tmp/goodix-enrollment-diversity.XXXXXX)
trap 'find "$build" -depth -delete 2>/dev/null || true' EXIT HUP INT TERM
cflags=$(pkg-config --cflags glib-2.0)
libs=$(pkg-config --libs glib-2.0)
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
sources="$root/libfprint-driver/goodix_enrollment_diversity.c $script_dir/test_goodix_enrollment_diversity.c"
export CCACHE_DISABLE=1

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

run_build enrollment_diversity_normal ""
echo ENROLLMENT_DIVERSITY_V2_NORMAL=PASS
run_build enrollment_diversity_sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo ENROLLMENT_DIVERSITY_V2_ASAN_UBSAN=PASS
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
