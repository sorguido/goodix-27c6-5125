#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_root=$(mktemp -d /tmp/goodix-d279-51-sigfm-print.XXXXXX)
pkgconfig_dir="$build_root/pkgconfig"
inner="$script_dir/run_goodix_fedora44_sigfm_print_test_inner.sh"
pc_template="$script_dir/support/d279/gusb.pc.in"
include_dir="$script_dir/support/d279"

cleanup ()
{
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
test -n "$host_gusb"
cp "$host_gusb" "$pkgconfig_dir/libgusb.so.2"
sed -e "s|@PREFIX@|$pkgconfig_dir|g" \
    -e "s|@INCLUDEDIR@|$include_dir|g" \
    "$pc_template" >"$pkgconfig_dir/gusb.pc"

for sanitizers in no yes; do
  run_root="$build_root/$sanitizers"
  mkdir -p "$run_root"
  flatpak run --user --unshare=network \
    --filesystem="$repo_root":ro --filesystem="$build_root" \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$repo_root" "$run_root" "$pkgconfig_dir" "$sanitizers"
done

echo D279_51_NORMAL_AND_ASAN_UBSAN=PASS
echo LIVE_EXECUTION_PERFORMED=false
