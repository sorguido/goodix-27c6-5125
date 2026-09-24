#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Focused regression runner. All device I/O is synthetic; D-Bus is private.
set -euo pipefail
[[ $# == 2 && $EUID != 0 ]] || { echo 'usage: check-offline.sh NORMAL_BUILD SANITIZER_BUILD'; exit 2; }
normal=$(realpath "$1")
sanitized=$(realpath "$2")
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(CDPATH= cd -- "$here/../.." && pwd -P)
work=$(mktemp -d /tmp/goodix-login-offline.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
mkdir "$work/shell"
flatpak run --user --unshare=network --filesystem="$root:ro" --filesystem="$work" \
  --env=GOODIX_D278_12_IN_SDK=1 --command=sh org.freedesktop.Sdk//25.08 \
  "$root/libfprint-driver/tests/run_goodix_d278_12_post_tls_test.sh"
flatpak run --user --unshare=network --filesystem="$root:ro" --filesystem="$work" \
  --command=sh org.freedesktop.Sdk//25.08 \
  "$root/libfprint-driver/tests/run_goodix_fpimage_device_test_inner.sh" "$root" "$work/shell"
for mode in normal sanitizer; do
  build=$normal
  [[ $mode != sanitizer ]] || build=$sanitized
  flatpak run --user --unshare=network --filesystem="$work" --filesystem="$build:ro" \
    --filesystem="$root:ro" --command=sh org.freedesktop.Sdk//25.08 \
    "$here/test-stack-build.sh" "$build" "$here" "$work" "$mode"
  san=()
  [[ $mode != sanitizer ]] || san=("$build/login/deps/lib/libasan.so.8" "$build/login/deps/lib/libubsan.so.1")
  gcc "${san[@]}" -Wl,--no-undefined -Wl,-rpath-link,"$build" \
    "$work/test-daemon-$mode.o" "$build/login/stack/src/fprintd.p/meson-generated_.._fprintd-enums.c.o" \
    "$build/login/stack/src/fprintd.p/meson-generated_.._fprintd-dbus.c.o" \
    /usr/lib64/libgio-2.0.so.0 /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libgmodule-2.0.so.0 \
    /usr/lib64/libglib-2.0.so.0 /usr/lib64/libpolkit-gobject-1.so.0 "$build/libfprint-2.so.2" \
    -o "$work/test-daemon-$mode"
  gcc "${san[@]}" "$work/test-greeter-$mode.o" /usr/lib64/libgio-2.0.so.0 \
    /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libglib-2.0.so.0 -o "$work/test-greeter-$mode"
  export LD_LIBRARY_PATH="$build:$build/login/deps/lib"
  export ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1
  timeout 20 "$work/test-daemon-$mode"
  /usr/bin/python3 "$here/test_greeter.py" "$work/test-greeter-$mode"
  unset LD_LIBRARY_PATH ASAN_OPTIONS UBSAN_OPTIONS
 done
python3 "$root/deployment/managed-install/test_offline.py"
echo CANONICAL_LOGIN_OFFLINE=PASS
