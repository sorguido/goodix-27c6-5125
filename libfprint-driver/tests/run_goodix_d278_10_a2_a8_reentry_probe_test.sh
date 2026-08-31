#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
build=${D278_10_BUILD_DIR:-$(mktemp -d /tmp/goodix-d278-10.XXXXXX)}
inner="$script_dir/run_goodix_d278_10_a2_a8_reentry_probe_test_inner.sh"
host_gusb=

cleanup () {
  if [ "${KEEP_BUILD:-0}" = "1" ]; then
    echo "KEEP_BUILD: $build"
    return
  fi
  find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true
  rmdir "$build" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

for candidate in \
  /usr/lib64/libgusb.so.2.0.10 \
  /usr/lib64/libgusb.so.2 \
  /usr/lib/x86_64-linux-gnu/libgusb.so.2; do
  if [ -f "$candidate" ]; then
    host_gusb=$candidate
    break
  fi
done
test -n "$host_gusb" || {
  echo "BLOCKED_ENVIRONMENT: installed libgusb runtime not found" >&2
  exit 2
}

mkdir -p "$build"
cp "$host_gusb" "$build/libgusb.so.2"

if [ "${D278_10_FORCE_HOST:-0}" != "1" ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$root" "$build" "$build/libgusb.so.2"
else
  echo EXECUTION_ENVIRONMENT=HOST
  "$inner" "$root" "$build" "$build/libgusb.so.2"
fi

test -x "$build/d278_a2_a8_reentry_observe_once"
ldd "$build/d278_a2_a8_reentry_observe_once"
sha256sum "$build/d278_a2_a8_reentry_observe_once"
