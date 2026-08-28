#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
build=${D277_BUILD_DIR:-$(mktemp -d /tmp/goodix-d277-a8.XXXXXX)}
inner="$script_dir/run_goodix_d277_a8_test_inner.sh"
host_gusb=/usr/lib64/libgusb.so.2.0.10

cleanup () {
  if [ "${KEEP_BUILD:-0}" = "1" ]; then
    echo "KEEP_BUILD: $build"
    return
  fi
  find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true
  rmdir "$build" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

test -f "$host_gusb" || {
  echo "BLOCKED_ENVIRONMENT: installed libgusb runtime not found" >&2
  exit 2
}
mkdir -p "$build"
cp "$host_gusb" "$build/libgusb.so.2"

flatpak run --user --unshare=network \
  --filesystem="$root":ro --filesystem=/tmp \
  --command=sh org.freedesktop.Sdk//25.08 \
  "$inner" "$root" "$build" "$build/libgusb.so.2"

test -x "$build/d277_native_a8_once"
ldd "$build/d277_native_a8_once"
sha256sum "$build/d277_native_a8_once"
