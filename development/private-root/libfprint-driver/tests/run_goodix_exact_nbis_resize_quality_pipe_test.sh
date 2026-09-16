#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
work=$(mktemp -d /tmp/goodix-nbis-resize-quality-pipe.XXXXXX)
cleanup ()
{
  if [[ $work == /tmp/goodix-nbis-resize-quality-pipe.* ]]; then
    find "$work" -depth -delete 2>/dev/null || true
  fi
}
trap cleanup EXIT HUP INT TERM

pkgconfig_dir="$work/pkgconfig"
mkdir -p "$pkgconfig_dir"
host_gusb=
for candidate in \
  /usr/lib64/libgusb.so.2.0.10 \
  /usr/lib64/libgusb.so.2 \
  /usr/lib/x86_64-linux-gnu/libgusb.so.2; do
  if [[ -f $candidate ]]; then
    host_gusb=$candidate
    break
  fi
done
[[ -n $host_gusb ]] || { echo HOST_GUSB_RUNTIME_NOT_FOUND >&2; exit 1; }
cp "$host_gusb" "$pkgconfig_dir/libgusb.so.2"
sed -e "s|@PREFIX@|$pkgconfig_dir|g" \
    -e "s|@INCLUDEDIR@|$root/libfprint-driver/tests/support/d279|g" \
    "$root/libfprint-driver/tests/support/d279/gusb.pc.in" >"$pkgconfig_dir/gusb.pc"

command -v flatpak >/dev/null 2>&1
flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null
flatpak run --user --unshare=network \
  --filesystem="$root":ro \
  --filesystem="$work" \
  --command=sh org.freedesktop.Sdk//25.08 \
  "$root/libfprint-driver/tests/run_goodix_exact_nbis_resize_quality_pipe_test_inner.sh" \
  "$root" "$work/build" "$pkgconfig_dir"
