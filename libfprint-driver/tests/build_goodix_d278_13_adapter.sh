#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
if [ -n "${D278_13_BUILD_DIR:-}" ]; then
  build=$D278_13_BUILD_DIR
  owned=0
else
  build=$(mktemp -d /tmp/goodix-d278-13-adapter.XXXXXX)
  owned=1
fi
approved=${D278_13_BUILD_APPROVED_BASELINE_SHA:-UNAPPROVED_FOR_LIVE}
inner="$script_dir/build_goodix_d278_13_adapter_inner.sh"
host_gusb=

cleanup () {
  if [ "$owned" = 0 ] || [ "${KEEP_BUILD:-0}" = 1 ]; then
    echo "D278_13_BUILD_DIR=$build"
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

if command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$root" "$build" "$build/libgusb.so.2" "$approved"
else
  echo EXECUTION_ENVIRONMENT=HOST
  "$inner" "$root" "$build" "$build/libgusb.so.2" "$approved"
fi

test -x "$build/d278_integrated_path_once"
ldd "$build/d278_integrated_path_once"
sha256sum "$build/d278_integrated_path_once"
