#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_root=$(mktemp -d /tmp/goodix-d279-27-nbis.XXXXXX)
build_dir="$build_root/build"
pkgconfig_dir="$build_root/pkgconfig"
inner="$script_dir/run_goodix_fedora44_nbis_action_test_inner.sh"
pc_template="$script_dir/support/d279/gusb.pc.in"
include_dir="$script_dir/support/d279"
fixture="$repo_root/reference/libfprint-fedora44-1.94.100/source/examples/prints/whorl.png"

cleanup ()
{
  if [ "${KEEP_BUILD:-0}" = 1 ]; then
    echo "D279_27_BUILD_ROOT=$build_root"
    return
  fi
  find "$build_root" -depth -delete 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$pkgconfig_dir"
host_gusb=
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

cp "$host_gusb" "$pkgconfig_dir/libgusb.so.2"
sed -e "s|@PREFIX@|$pkgconfig_dir|g" \
    -e "s|@INCLUDEDIR@|$include_dir|g" \
    "$pc_template" >"$pkgconfig_dir/gusb.pc"

if command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  flatpak run --user --unshare=network \
    --filesystem="$repo_root":ro \
    --filesystem="$build_root" \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$repo_root" "$build_dir" "$pkgconfig_dir" "$fixture"
  exit $?
fi

echo "BLOCKED_ENVIRONMENT: Freedesktop SDK 25.08 unavailable" >&2
exit 2
