#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
git_root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_dir=$(mktemp -d /tmp/goodix-runtime-inputs.XXXXXX)

cleanup ()
{
  find "$build_dir" -maxdepth 1 -type f -delete 2>/dev/null || true
  rmdir "$build_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

run_tests ()
{
  root=$1
  build=$2
  cflags=$(pkg-config --cflags glib-2.0 openssl)
  libs=$(pkg-config --libs glib-2.0 openssl)
  strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"

  gcc $strict $cflags -I"$root/libfprint-driver" \
    "$root/libfprint-driver/goodix_d190_binder.c" \
    "$root/libfprint-driver/goodix_target_material.c" \
    "$root/libfprint-driver/goodix_runtime_inputs.c" \
    "$root/libfprint-driver/goodix_runtime_material.c" \
    "$root/libfprint-driver/tests/test_goodix_runtime_inputs.c" \
    $libs -o "$build/test-goodix-runtime-inputs"
  timeout 30 "$build/test-goodix-runtime-inputs"
  echo D279_06_RUNTIME_MATERIAL_NORMAL=PASS

  gcc $strict -O1 -fno-omit-frame-pointer -fsanitize=address,undefined \
    $cflags -I"$root/libfprint-driver" \
    "$root/libfprint-driver/goodix_d190_binder.c" \
    "$root/libfprint-driver/goodix_target_material.c" \
    "$root/libfprint-driver/goodix_runtime_inputs.c" \
    "$root/libfprint-driver/goodix_runtime_material.c" \
    "$root/libfprint-driver/tests/test_goodix_runtime_inputs.c" \
    $libs -o "$build/test-goodix-runtime-inputs-sanitized"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
    UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build/test-goodix-runtime-inputs-sanitized"
  echo D279_06_RUNTIME_MATERIAL_ASAN_UBSAN=PASS
}

if command -v flatpak >/dev/null 2>&1 && \
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  flatpak run --user --unshare=network \
    --filesystem="$git_root" --filesystem=/tmp \
    --command=sh org.freedesktop.Sdk//25.08 -c \
    'set -eu
     run_tests () {
       root=$1; build=$2
       cflags=$(pkg-config --cflags glib-2.0 openssl)
       libs=$(pkg-config --libs glib-2.0 openssl)
       strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
       gcc $strict $cflags -I"$root/libfprint-driver" "$root/libfprint-driver/goodix_d190_binder.c" "$root/libfprint-driver/goodix_target_material.c" "$root/libfprint-driver/goodix_runtime_inputs.c" "$root/libfprint-driver/goodix_runtime_material.c" "$root/libfprint-driver/tests/test_goodix_runtime_inputs.c" $libs -o "$build/test-goodix-runtime-inputs"
       timeout 30 "$build/test-goodix-runtime-inputs"
       echo D279_06_RUNTIME_MATERIAL_NORMAL=PASS
       gcc $strict -O1 -fno-omit-frame-pointer -fsanitize=address,undefined $cflags -I"$root/libfprint-driver" "$root/libfprint-driver/goodix_d190_binder.c" "$root/libfprint-driver/goodix_target_material.c" "$root/libfprint-driver/goodix_runtime_inputs.c" "$root/libfprint-driver/goodix_runtime_material.c" "$root/libfprint-driver/tests/test_goodix_runtime_inputs.c" $libs -o "$build/test-goodix-runtime-inputs-sanitized"
       ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 timeout 30 "$build/test-goodix-runtime-inputs-sanitized"
       echo D279_06_RUNTIME_MATERIAL_ASAN_UBSAN=PASS
     }
     run_tests "$1" "$2"' sh "$git_root" "$build_dir"
else
  run_tests "$git_root" "$build_dir"
fi

echo REAL_PRODUCTION_SECRET_READ=false
echo REAL_USB_ACCESS=false
echo LIVE_EXECUTION_PERFORMED=false
