#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Focused regression runner. All device I/O is synthetic; D-Bus is private.
set -euo pipefail
[[ $# == 2 && $EUID != 0 ]] || { echo 'usage: check-offline.sh NORMAL_BUILD SANITIZER_BUILD'; exit 2; }
normal=$(realpath "$1")
sanitized=$(realpath "$2")
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
work=$(mktemp -d /tmp/goodix-login-offline.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
cp -a "$normal/source" "$work/source"
cp -a "$root/development/private-root/libfprint-driver/tests" "$work/source/libfprint-driver/"
cp -a "$root/development/Rockytkg/snapshot/libfprint/." "$work/source/Rockytkg/libfprint/"
sed "s|root=\$(git -C \"\$script_dir\" rev-parse --show-toplevel)|root=$work/source|" \
  "$root/development/private-root/libfprint-driver/tests/run_goodix_d278_12_post_tls_test.sh" \
  >"$work/source/libfprint-driver/tests/run_goodix_d278_12_post_tls_test.sh"
mkdir "$work/shell"
flatpak run --user --unshare=network --filesystem="$work" --env=GOODIX_D278_12_IN_SDK=1 \
  --command=sh org.freedesktop.Sdk//25.08 "$work/source/libfprint-driver/tests/run_goodix_d278_12_post_tls_test.sh"
flatpak run --user --unshare=network --filesystem="$work" --command=sh org.freedesktop.Sdk//25.08 \
  "$work/source/libfprint-driver/tests/run_goodix_fpimage_device_test_inner.sh" "$work/source" "$work/shell"
for mode in normal sanitizer; do
  build=$normal
  [[ $mode != sanitizer ]] || build=$sanitized
  flatpak run --user --unshare=network --filesystem="$work" --filesystem="$build:ro" \
    --filesystem="$here:ro" --command=sh org.freedesktop.Sdk//25.08 \
    "$here/test-stack-build.sh" "$build" "$here" "$work" "$mode"
  san=()
  [[ $mode != sanitizer ]] || san=("$build/deps/lib/libasan.so.8" "$build/deps/lib/libubsan.so.1")
  gcc "${san[@]}" -Wl,--no-undefined -Wl,-rpath-link,"$build/driver" \
    "$work/test-daemon-$mode.o" "$build/stack/src/fprintd.p/meson-generated_.._fprintd-enums.c.o" \
    "$build/stack/src/fprintd.p/meson-generated_.._fprintd-dbus.c.o" \
    /usr/lib64/libgio-2.0.so.0 /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libgmodule-2.0.so.0 \
    /usr/lib64/libglib-2.0.so.0 /usr/lib64/libpolkit-gobject-1.so.0 "$build/driver/libfprint-2.so.2" \
    -o "$work/test-daemon-$mode"
  gcc "${san[@]}" "$work/test-greeter-$mode.o" /usr/lib64/libgio-2.0.so.0 \
    /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libglib-2.0.so.0 -o "$work/test-greeter-$mode"
  export LD_LIBRARY_PATH="$build/driver:$build/deps/lib"
  export ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1
  timeout 20 "$work/test-daemon-$mode"
  /usr/bin/python3 "$here/test_greeter.py" "$work/test-greeter-$mode"
  unset LD_LIBRARY_PATH ASAN_OPTIONS UBSAN_OPTIONS
 done
python3 "$here/test_transaction.py"
bash -n "$here/prepare.sh" "$here/install.sh" "$here/rollback.sh" "$here/check-offline.sh"
sh -n "$here/build-stack.sh" "$here/test-stack-build.sh" "$here/test-greeter-child.sh"
echo EARLY_LOGIN_OFFLINE=PASS
