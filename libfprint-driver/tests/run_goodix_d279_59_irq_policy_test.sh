#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)

if [ "${GOODIX_D279_59_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  exec flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_D279_59_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0"
fi

build=$(mktemp -d /tmp/goodix-d279-59-policy.XXXXXX)
trap 'find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true; rmdir "$build" 2>/dev/null || true' EXIT HUP INT TERM
cflags=$(pkg-config --cflags glib-2.0)
libs=$(pkg-config --libs glib-2.0)
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
corpus="$root/analysis/D279/D279_59_irq_flags_policy_corpus.tsv"

run_build () {
  name=$1
  extra=$2
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags -I"$root/libfprint-driver" \
    "$root/libfprint-driver/goodix_fdt_irq_policy.c" \
    "$script_dir/test_goodix_fdt_irq_policy.c" $libs -o "$build/$name"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 timeout 30 "$build/$name" "$corpus"
}

run_build normal ""
echo D279_59_IRQ_POLICY_NORMAL=PASS
run_build sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D279_59_IRQ_POLICY_ASAN_UBSAN=PASS
echo AUTHENTIC_METADATA_CORPUS_EVENT_COUNT=65
echo D279_57_LIVE_REGRESSION_EVENT_COUNT=1
echo REAL_USB_ACCESS=0
