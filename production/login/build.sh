#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 2 && $EUID != 0 ]] || exit 2
driver=$(realpath "$1")
mode=$2
[[ $mode == normal || $mode == sanitizer ]] || exit 2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(CDPATH= cd -- "$here/../.." && pwd -P)
output=$driver/login
mkdir "$output"
cp -a "$root/reference/fprintd-fedora44-1.94.5/source" "$output/fprintd"
patch --batch --fuzz=0 -d "$output/fprintd" -p1 <"$here/fprintd.patch"
patch --batch --fuzz=0 -d "$output/fprintd" -p1 <"$here/fprintd-cleanup.patch"
patch --batch --fuzz=0 -d "$output/fprintd" -p1 <"$here/fprintd-attempts.patch"
mkdir -p "$output/deps/prefix" "$output/deps/lib" "$output/deps/pc" "$output/deps/rpms"
# Header-only prerequisites: copied from a verified cache or downloaded, never installed.
rpm_dir=${GOODIX_HEADER_RPMS:-$root/GoodixArtifacts/login-header-rpms}
cp "$rpm_dir"/{pam-devel-1.7.2-2.fc44.x86_64,polkit-devel-127-2.fc44.2.x86_64}.rpm "$output/deps/rpms/"
(cd "$output/deps/rpms" && sha256sum -c "$here/headers.sha256")
for rpm in "$output/deps/rpms"/*.rpm; do
  (cd "$output/deps/prefix" && rpm2cpio "$rpm" | cpio -idm --quiet)
done
cp -L /usr/lib64/libpam.so.0 "$output/deps/lib/libpam.so"
cp -L /usr/lib64/libpolkit-gobject-1.so.0 "$output/deps/lib/libpolkit-gobject-1.so"
sed -e "s|^prefix=/usr|prefix=$output/deps/prefix/usr|" -e "s|^libdir=.*|libdir=$output/deps/lib|" \
  "$output/deps/prefix/usr/lib64/pkgconfig/polkit-gobject-1.pc" >"$output/deps/pc/polkit-gobject-1.pc"
cat >"$output/deps/pc/libfprint-2.pc" <<PC
Name: libfprint
Description: paired Goodix login candidate
Version: 1.94.100
Libs: -L$driver -lfprint-2
Cflags: -I$root/reference/libfprint-fedora44-1.94.100/source/libfprint -I$driver/build/libfprint
Requires: gio-2.0
PC
flatpak run --user --unshare=network --filesystem="$output" --filesystem="$root:ro" --filesystem="$driver" \
  --command=sh org.freedesktop.Sdk//25.08 "$here/build-stack.sh" "$output" "$here" "$mode" "$driver"
san=()
if [[ $mode == sanitizer ]]; then
  san=("$output/deps/lib/libasan.so.8" "$output/deps/lib/libubsan.so.1")
fi
# Fedora 44's libpam requires GLIBC_2.43; SDK compilation + native link avoids
# replacing the host toolchain, libc or PAM. No binary is executed here.
gcc "${san[@]}" -shared -Wl,--no-undefined -Wl,--version-script,"$output/fprintd/pam/pam_fprintd.ver" \
  "$output/stack/pam/pam_fprintd.so.p/pam_fprintd.c.o" /usr/lib64/libpam.so.0 /usr/lib64/libsystemd.so.0 \
  -o "$driver/pam_fprintd.so"
gcc "${san[@]}" -Wl,--no-undefined -Wl,--export-dynamic -Wl,-rpath-link,"$driver" \
  "$output/stack/src/fprintd.p/"*.o "$output/stack/src/libfprintd-private.a" \
  /usr/lib64/libgio-2.0.so.0 /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libgmodule-2.0.so.0 \
  /usr/lib64/libglib-2.0.so.0 /usr/lib64/libpolkit-gobject-1.so.0 "$driver/libfprint-2.so.2" \
  -o "$driver/fprintd"
gcc "${san[@]}" -Wl,--no-undefined "$output/stack/greeter.o" \
  /usr/lib64/libgio-2.0.so.0 /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libglib-2.0.so.0 \
  -o "$driver/greeter"
for file in fprintd greeter pam_fprintd.so; do
  readelf -d "$driver/$file" >"$output/$file.dynamic"
  ! grep -E 'RPATH|RUNPATH' "$output/$file.dynamic"
  if [[ $mode == normal ]]; then
    LD_LIBRARY_PATH="$driver" ldd "$driver/$file" >"$output/$file.ldd"
    ! grep -F 'not found' "$output/$file.ldd"
  fi
done
nm -D --defined-only "$driver/pam_fprintd.so" >"$output/pam.symbols"
grep -F pam_sm_authenticate "$output/pam.symbols" >/dev/null
echo PRODUCTION_LOGIN_BUILD=PASS
