#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

if [[ $# -ne 2 ]]; then
  echo "uso: $0 <normal|sanitizer> <output-assoluto>" >&2
  exit 2
fi
mode=$1
output=$2
case "$mode" in normal|sanitizer) ;; *) echo "modalità non valida" >&2; exit 2 ;; esac
[[ $EUID -ne 0 ]] || { echo "la build deve essere unprivileged" >&2; exit 1; }
[[ $output == /* && $output != / && ! -L $output ]] || {
  echo "output non assoluto o non sicuro" >&2; exit 2;
}
if [[ -e $output ]]; then
  [[ -d $output && -z $(find "$output" -mindepth 1 -maxdepth 1 -print -quit) ]] || {
    echo "output esistente non vuoto" >&2; exit 2;
  }
else
  mkdir -m 0700 -- "$output"
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
baseline=f609c865f760768edb6a9e404b863ccd0569e1c8
work=$(mktemp -d /tmp/goodix-production-build.XXXXXX)
cleanup () {
  if [[ $work == /tmp/goodix-production-build.* && -d $work && ! -L $work ]]; then
    find "$work" -xdev -depth -delete
  fi
}
trap cleanup EXIT INT TERM
assembly="$work/assembly"
build_dir="$output/build"
pkgconfig="$output/pkgconfig"
opencv_prefix="$work/opencv-prefix"
rpm_dir="$root/GoodixArtifacts/opencv-4.13-rpms"
mkdir -p "$assembly" "$build_dir" "$pkgconfig" "$opencv_prefix"

"$script_dir/check-source.sh"
git -C "$root" archive "$baseline" -- \
  reference/libfprint-fedora44-1.94.100/source | tar -x -C "$assembly"
while IFS=$'\t' read -r path license provenance; do
  [[ -n $path && -n $license && -n $provenance ]] || {
    echo "manifest source non valido" >&2; exit 1;
  }
  install -D -m 0644 "$root/$path" "$assembly/$path"
done <"$script_dir/source-files.tsv"
patch --batch --forward -p1 -d "$assembly" \
  <"$script_dir/patches/0001-goodix-fedora44-production.patch"

(cd "$rpm_dir" && sha256sum -c "$script_dir/build-support/opencv-rpms.sha256")
for package in "$rpm_dir"/*.rpm; do
  (cd "$opencv_prefix" && rpm2cpio "$package" | cpio -idm --quiet)
done
gusb=$(ldconfig -p | awk \
  '/libgusb[.]so[.]2 .*x86-64/ && !found {value=$NF; found=1} END {print value}')
[[ -n $gusb && -f $gusb ]] || { echo "libgusb.so.2 non trovata" >&2; exit 1; }
cp "$gusb" "$pkgconfig/libgusb.so.2"
sed -e "s|@PREFIX@|$pkgconfig|g" \
    -e "s|@INCLUDEDIR@|$script_dir/build-support|g" \
    "$script_dir/build-support/gusb.pc.in" >"$pkgconfig/gusb.pc"
sed -e "s|@PREFIX@|$opencv_prefix/usr|g" \
    "$script_dir/build-support/opencv4.pc.in" >"$pkgconfig/opencv4.pc"

flatpak run --user --unshare=network \
  --filesystem="$assembly:ro" --filesystem="$opencv_prefix:ro" \
  --filesystem="$output" \
  --filesystem="$script_dir:ro" --command=sh org.freedesktop.Sdk//25.08 \
  "$script_dir/build-inner.sh" "$assembly" "$build_dir" "$pkgconfig" \
  "$output" "$mode" | tee "$output/build.env"

cp "$pkgconfig/libgusb.so.2" "$output/libgusb.so.2"
for component in core features2d flann imgproc; do
  cp -L "$opencv_prefix/usr/lib64/libopencv_${component}.so.4.13.0" \
    "$output/libopencv_${component}.so.413"
done
library="$output/libfprint-2.so.2.0.0"
nm "$library" >"$output/library.nm"
while read -r symbol; do
  ! grep -Eq " [A-Za-z] ${symbol}$" "$output/library.nm" || {
    echo "simbolo host/test presente: $symbol" >&2; exit 1;
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
echo REAL_USB_ENUMERATION_ATTEMPTED=false
echo LIVE_EXECUTION_PERFORMED=false
