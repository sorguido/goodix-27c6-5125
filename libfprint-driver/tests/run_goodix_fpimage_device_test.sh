#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
git_root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_dir=$(mktemp -d /tmp/goodix-d276-fpimage-device.XXXXXX)
inner="$script_dir/run_goodix_fpimage_device_test_inner.sh"

cleanup ()
{
  if [ "${KEEP_BUILD:-0}" = "1" ]; then
    echo "KEEP_BUILD: build artifacts left in $build_dir"
    return
  fi
  find "$build_dir" -maxdepth 1 -type f -delete 2>/dev/null || true
  rmdir "$build_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

test -f "$inner" || {
  echo "missing host-only test helper: $inner" >&2
  exit 2
}

if command -v flatpak >/dev/null 2>&1 && \
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo "EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08"
  flatpak run --user --unshare=network \
    --filesystem="$git_root" \
    --filesystem=/tmp \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$git_root" "$build_dir" "$@"
  exit $?
fi

missing=""
for tool in gcc pkg-config python3 timeout nm grep; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing="$missing $tool"
  fi
done

if [ -z "$missing" ] && pkg-config --exists glib-2.0 gio-2.0 gobject-2.0; then
  echo "EXECUTION_ENVIRONMENT=HOST_NATIVE_FALLBACK"
  sh "$inner" "$git_root" "$build_dir" "$@"
  exit $?
fi

echo "D276/02 host-only validation environment unavailable" >&2
if [ -n "$missing" ]; then
  echo "missing tools:$missing" >&2
fi
if command -v pkg-config >/dev/null 2>&1 && \
   ! pkg-config --exists glib-2.0 gio-2.0 gobject-2.0; then
  echo "missing pkg-config metadata: glib-2.0 gio-2.0 gobject-2.0" >&2
fi
exit 2
