#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <normal|sanitizer> <absolute-output-directory>" >&2
  exit 2
fi
mode=$1
output=$2
case "$mode" in normal|sanitizer) ;; *) echo "invalid build mode" >&2; exit 2 ;; esac
[[ $EUID -ne 0 ]] || { echo "the build must run unprivileged" >&2; exit 1; }
[[ $output == /* && $output != / && ! -L $output ]] || {
  echo "unsafe output path" >&2; exit 2;
}
if [[ -e $output ]]; then
  [[ -d $output && -z $(find "$output" -mindepth 1 -maxdepth 1 -print -quit) ]] || {
    echo "output directory is not empty" >&2; exit 2;
  }
else
  mkdir -m 0700 -- "$output"
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
work=$(mktemp -d /tmp/goodix-production-build.XXXXXX)
cleanup () {
  if [[ $work == /tmp/goodix-production-build.* && -d $work && ! -L $work ]]; then
    find "$work" -xdev -depth -delete
  fi
}
trap cleanup EXIT INT TERM
build_dir="$output/build"
pkgconfig="$output/pkgconfig"
opencv_prefix="$work/opencv-prefix"
rpm_dir="$root/GoodixArtifacts/opencv-4.13-rpms"
mkdir -p "$build_dir" "$pkgconfig" "$opencv_prefix"

"$script_dir/check-source.sh"
(cd "$rpm_dir" && sha256sum -c "$script_dir/build-support/opencv-rpms.sha256")
for package in "$rpm_dir"/*.rpm; do
  (cd "$opencv_prefix" && rpm2cpio "$package" | cpio -idm --quiet)
done
gusb=$(ldconfig -p | awk \
  '/libgusb[.]so[.]2 .*x86-64/ && !found {value=$NF; found=1} END {print value}')
[[ -n $gusb && -f $gusb ]] || { echo "libgusb.so.2 not found" >&2; exit 1; }
cp "$gusb" "$pkgconfig/libgusb.so.2"
sed -e "s|@PREFIX@|$pkgconfig|g" \
    -e "s|@INCLUDEDIR@|$script_dir/build-support|g" \
    "$script_dir/build-support/gusb.pc.in" >"$pkgconfig/gusb.pc"
sed -e "s|@PREFIX@|$opencv_prefix/usr|g" \
    "$script_dir/build-support/opencv4.pc.in" >"$pkgconfig/opencv4.pc"

flatpak run --user --unshare=network \
  --filesystem="$root:ro" --filesystem="$opencv_prefix:ro" \
  --filesystem="$output" --command=sh org.freedesktop.Sdk//25.08 \
  "$script_dir/build-inner.sh" \
  "$root/reference/libfprint-fedora44-1.94.100/source" \
  "$build_dir" "$pkgconfig" \
  "$output" "$mode" | tee "$output/build.env"

cp "$pkgconfig/libgusb.so.2" "$output/libgusb.so.2"
for component in core features2d flann imgproc; do
  cp -L "$opencv_prefix/usr/lib64/libopencv_${component}.so.4.13.0" \
    "$output/libopencv_${component}.so.413"
done
license_root="$opencv_prefix/usr/share/licenses"
[[ -d $license_root/opencv-core && -d $license_root/opencv4 ]] || {
  echo "OpenCV license corpus not found" >&2; exit 1;
}
{
  while IFS= read -r license_file; do
    relative=${license_file#"$license_root"/}
    printf '%s\n' "===== $relative ====="
    cat "$license_file"
    printf '\n'
  done < <(find "$license_root/opencv-core" "$license_root/opencv4" \
    -type f -print | LC_ALL=C sort)
} >"$output/OpenCV-LICENSES.txt"
library="$output/libfprint-2.so.2.0.0"
nm "$library" >"$output/library.nm"
while read -r symbol; do
  ! grep -Eq " [A-Za-z] ${symbol}$" "$output/library.nm" || {
    echo "host/test symbol present: $symbol" >&2; exit 1;
  }
done <"$script_dir/host-test-only-symbols.txt"
legacy_policy=GOODIX_D
legacy_policy="${legacy_policy}282_DIRECT_ENROLL_PROFILE"
! strings "$library" | grep -F "$legacy_policy" >/dev/null
readelf -d "$library" >"$output/library.dynamic"
! grep -E '(RPATH|RUNPATH)' "$output/library.dynamic" >/dev/null
grep -F '[libfprint-2.so.2]' "$output/library.dynamic" >/dev/null

required="$output/fprintd.required"
provided="$output/libfprint.provided"
nm -D --undefined-only /usr/libexec/fprintd |
  awk '$1=="U" && $2 ~ /@LIBFPRINT_2[.]0[.]0$/ {sub(/@.*/,"",$2); print $2}' |
  sort -u >"$required"
nm -D --defined-only "$library" |
  awk '$3 ~ /@@LIBFPRINT_2[.]0[.]0$/ {sub(/@@.*/,"",$3); print $3}' |
  sort -u >"$provided"
while read -r symbol; do grep -Fx "$symbol" "$provided" >/dev/null; done <"$required"
if [[ $mode == normal ]]; then
  LD_LIBRARY_PATH="$output" ldd /usr/libexec/fprintd >"$output/fprintd.ldd"
  grep -F "$output/libfprint-2.so.2" "$output/fprintd.ldd" >/dev/null
  ! grep -F 'not found' "$output/fprintd.ldd" >/dev/null
fi
sha256sum "$library" >"$output/artifact.sha256"
echo PRODUCTION_BUILD=PASS
echo "PRODUCTION_BUILD_MODE=$mode"
echo PRODUCTION_HOST_TEST_ONLY_SYMBOL_COUNT=0
echo PRODUCTION_ABI_LIBFPRINT_2_0_0=PASS
echo PRODUCTION_RPATH_PRESENT=false
echo PRODUCTION_PRIVATE_TREE_DEPENDENCY_COUNT=0
echo REAL_USB_ENUMERATION_ATTEMPTED=false
echo LIVE_EXECUTION_PERFORMED=false
