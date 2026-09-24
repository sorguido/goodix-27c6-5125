#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077
[[ $# -ge 1 && $# -le 2 && $EUID != 0 ]] || exit 2
output=$1
mode=${2:-normal}
[[ $mode == normal || $mode == sanitizer ]] || exit 2
[[ $output == /* && $output != / && ! -L $output ]] || exit 2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
mkdir -p -- "$output"
[[ -O $output && -z $(find "$output" -mindepth 1 -maxdepth 1 -print -quit) ]] || exit 2
base=c0e13ff5f78ac32403a753446dcbc44aa7f30556
loader=e61fce313794922a2dab156a1b38a8ddc5837f19
mkdir "$output/source"
git -C "$root" archive "$base" libfprint-driver production \
  reference/libfprint-fedora44-1.94.100/source Rockytkg/libfprint/libfprint/sigfm |
  tar -x -C "$output/source"
# Current canonical driver; only the installed D293 loader representation is retained.
while read -r sha name; do cp "$root/$name" "$output/source/$name"; done <"$root/production/source-files.sha256"
for name in goodix_target_material.c goodix_target_material.h goodix_runtime_material.c goodix_runtime_inputs.c; do
  git -C "$root" show "$loader:libfprint-driver/$name" >"$output/source/libfprint-driver/$name"
done
python3 - "$output/source" <<'PY'
from pathlib import Path
import hashlib, sys
r = Path(sys.argv[1]); p = r / 'production/source-files.sha256'
p.write_text(''.join(f'{hashlib.sha256((r / line.split()[1]).read_bytes()).hexdigest()}  {line.split()[1]}\n' for line in p.read_text().splitlines()))
PY
ln -s "$root/GoodixArtifacts" "$output/source/GoodixArtifacts"
"$output/source/production/build.sh" "$mode" "$output/driver"
cp -a "$root/development/reference/fprintd-fedora44-1.94.5/source" "$output/fprintd"
patch --batch --fuzz=0 -d "$output/fprintd" -p1 <"$here/fprintd.patch"
mkdir -p "$output/deps/prefix" "$output/deps/lib" "$output/deps/pc" "$output/deps/rpms"
# Header-only prerequisites: copied from a verified cache or downloaded, never installed.
if [[ -n ${GOODIX_LOGIN_HEADER_RPMS:-} ]]; then
  cp "$GOODIX_LOGIN_HEADER_RPMS"/{pam-devel-1.7.2-2.fc44.x86_64,polkit-devel-127-2.fc44.2.x86_64}.rpm "$output/deps/rpms/"
else
  dnf --disable-repo='*' --enable-repo=fedora --enable-repo=updates \
    --setopt="cachedir=$output/deps/cache" --setopt="logdir=$output/deps/log" \
    download --destdir="$output/deps/rpms" pam-devel-1.7.2-2.fc44.x86_64 polkit-devel-127-2.fc44.2.x86_64
fi
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
Libs: -L$output/driver -lfprint-2
Cflags: -I$output/source/reference/libfprint-fedora44-1.94.100/source/libfprint -I$output/driver/build/libfprint
Requires: gio-2.0
PC
flatpak run --user --unshare=network --filesystem="$output" --filesystem="$here:ro" \
  --command=sh org.freedesktop.Sdk//25.08 "$here/build-stack.sh" "$output" "$here" "$mode"
mkdir "$output/candidate"
san=()
if [[ $mode == sanitizer ]]; then
  san=("$output/deps/lib/libasan.so.8" "$output/deps/lib/libubsan.so.1")
fi
# Fedora 44's libpam requires GLIBC_2.43; SDK compilation + native link avoids
# replacing the host toolchain, libc or PAM. No binary is executed here.
gcc "${san[@]}" -shared -Wl,--no-undefined -Wl,--version-script,"$output/fprintd/pam/pam_fprintd.ver" \
  "$output/stack/pam/pam_fprintd.so.p/pam_fprintd.c.o" /usr/lib64/libpam.so.0 /usr/lib64/libsystemd.so.0 \
  -o "$output/candidate/pam_fprintd.so"
gcc "${san[@]}" -Wl,--no-undefined -Wl,--export-dynamic -Wl,-rpath-link,"$output/driver" \
  "$output/stack/src/fprintd.p/"*.o "$output/stack/src/libfprintd-private.a" \
  /usr/lib64/libgio-2.0.so.0 /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libgmodule-2.0.so.0 \
  /usr/lib64/libglib-2.0.so.0 /usr/lib64/libpolkit-gobject-1.so.0 "$output/driver/libfprint-2.so.2" \
  -o "$output/candidate/fprintd"
gcc "${san[@]}" -Wl,--no-undefined "$output/stack/greeter.o" \
  /usr/lib64/libgio-2.0.so.0 /usr/lib64/libgobject-2.0.so.0 /usr/lib64/libglib-2.0.so.0 \
  -o "$output/candidate/greeter"
for name in libfprint-2.so.2.0.0 libgusb.so.2 libopencv_{core,features2d,flann,imgproc}.so.413; do
  cp "$output/driver/$name" "$output/candidate/"
done
{
  printf 'RECIPE_COMMIT=%s\nSOURCE_BASE=%s\nMATERIAL_LOADER_BASE=%s\nMODE=%s\n' "$(git -C "$root" rev-parse HEAD)" "$base" "$loader" "$mode"
  printf 'PURPOSE=EARLY_LOGIN_PREPARATION\nBUILD_REAL_USB_ACCESS=false\nBUILD_PROTECTED_MATERIAL_READ=false\n'
  sha256sum "$here/fprintd.patch" "$here/greeter.c" "$here/build-stack.sh" "$here/prepare.sh"
} >"$output/candidate/PROVENANCE"
cp "$output/source/production/source-files.sha256" "$output/candidate/source-files.sha256"
(cd "$output/candidate" && sha256sum lib*.so* fprintd greeter pam_fprintd.so PROVENANCE source-files.sha256 >SHA256SUMS)
if [[ $mode == normal ]]; then
  for file in fprintd greeter pam_fprintd.so; do
    LD_LIBRARY_PATH="$output/driver" ldd "$output/candidate/$file" >"$output/$file.ldd"
    ! grep -F 'not found' "$output/$file.ldd"
    ! readelf -d "$output/candidate/$file" | grep -E 'RPATH|RUNPATH'
  done
fi
echo "EARLY_LOGIN_BUILD=PASS mode=$mode candidate=$output/candidate"
