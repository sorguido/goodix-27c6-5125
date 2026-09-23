#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

fail() { printf 'MINIMAL_RUNTIME_BUILD=FAIL reason=%s\n' "$*" >&2; exit 1; }
trap 'printf "MINIMAL_RUNTIME_BUILD=FAIL line=%s\n" "$LINENO" >&2' ERR
if [[ ${1:-} == --help && $# -eq 1 ]]; then
  echo "usage: $0 <normal|sanitizer> <new-absolute-output-directory>"
  echo "VM-only, unprivileged, build/link audit only; no service/device execution."
  exit 0
fi

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
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
# Before creating output, require an actual VM and the expected source baseline.
systemd-detect-virt --vm --quiet || fail VM_REQUIRED
[[ $(uname -m) == x86_64 ]] || fail X86_64_REQUIRED
source /etc/os-release
[[ ${ID:-} == fedora && ${VERSION_ID:-} == 44 ]] || fail FEDORA_44_REQUIRED
[[ $(git -C "$root" branch --show-current) == development ]] || fail DEVELOPMENT_REQUIRED
[[ -z $(git -C "$root" status --porcelain --untracked-files=normal) ]] || fail CLEAN_CHECKOUT_REQUIRED
source_commit=$(git -C "$root" rev-parse HEAD)
# No existing directory is accepted: failed builds remain available for diagnosis.
[[ ! -e $output ]] || fail OUTPUT_ALREADY_EXISTS
for path in "$root" "$output"; do
  [[ $path != *[[:space:]\\\|\&]* ]] || fail PATH_UNSUPPORTED
done
case "$(realpath -m -- "$output")/" in
  "$root/"*) fail OUTPUT_MUST_BE_OUTSIDE_CHECKOUT ;;
esac
for tool in flatpak rpm rpm2cpio cpio readelf nm strings ldconfig sha256sum; do
  command -v "$tool" >/dev/null || fail "MISSING_TOOL_$tool"
done
[[ -f /usr/libexec/fprintd && ! -L /usr/libexec/fprintd ]] || fail FEDORA_FPRINTD_MISSING
rpm -qf /usr/libexec/fprintd | grep -E '^fprintd-[0-9]' >/dev/null || fail FEDORA_FPRINTD_OWNER
flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null || fail SDK_25_08_REQUIRED
"$script_dir/check-source.sh" --driver-only
(cd "$root/GoodixArtifacts/opencv-4.13-rpms" &&
  sha256sum -c "$script_dir/build-support/opencv-rpms.sha256")
mkdir -m 0700 -- "$output"
output=$(realpath -- "$output")
{
  printf 'SOURCE_COMMIT=%s\nBUILD_MODE=%s\n' "$source_commit" "$mode"
  printf 'VM_TYPE=%s\n' "$(systemd-detect-virt --vm)"
  cat /etc/os-release
  uname -m
  rpm -q fprintd libfprint libgusb opencv-core systemd
  flatpak info --user org.freedesktop.Sdk//25.08
} >"$output/build-provenance.txt"
# Verify the daemon's RPM payload before using it as the stock ABI reference.
rpm -V fprintd >"$output/fprintd-rpm-verify.txt" || fail FEDORA_FPRINTD_MODIFIED
# Record only source inputs; protected/private workspace content is never hashed.
git -C "$root" ls-files -z -- production/minimal-runtime production/build-inner.sh \
  production/check-source.sh production/build-support production/source-files.tsv \
  production/source-files.sha256 production/host-test-only-symbols.txt \
  libfprint-driver reference/libfprint-fedora44-1.94.100 \
  Rockytkg/libfprint/libfprint/sigfm LICENSES docs/LICENSING_AND_PROVENANCE.md |
  (cd "$root" && xargs -0 sha256sum) >"$output/build-source.sha256"
work=$(mktemp -d /tmp/goodix-production-build.XXXXXX)
cleanup () {
  if [[ $work == /tmp/goodix-production-build.* && -d $work && ! -L $work ]]; then
    find "$work" -xdev -depth -delete
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
build_dir="$output/build"
pkgconfig="$output/pkgconfig"
opencv_prefix="$work/opencv-prefix"
rpm_dir="$root/GoodixArtifacts/opencv-4.13-rpms"
mkdir -p "$build_dir" "$pkgconfig" "$opencv_prefix"

while read -r _ package_name; do
  package="$rpm_dir/$package_name"
  # cpio may stop at the archive trailer before rpm2cpio writes its padding.
  # A file keeps pipefail from turning that benign SIGPIPE into a build failure.
  rpm2cpio "$package" >"$work/package.cpio"
  (cd "$opencv_prefix" && cpio -idm --quiet <"$work/package.cpio")
  rm -- "$work/package.cpio"
done <"$script_dir/build-support/opencv-rpms.sha256"
gusb=$(ldconfig -p | awk \
  '/libgusb[.]so[.]2 .*x86-64/ && !found {value=$NF; found=1} END {print value}')
[[ -n $gusb && -f $gusb ]] || { echo "libgusb.so.2 not found" >&2; exit 1; }
cp "$gusb" "$pkgconfig/libgusb.so.2"
sed -e "s|@PREFIX@|$pkgconfig|g" \
    -e "s|@INCLUDEDIR@|$script_dir/build-support|g" \
    "$script_dir/build-support/gusb.pc.in" >"$pkgconfig/gusb.pc"
sed -e "s|@PREFIX@|$opencv_prefix/usr|g" \
    "$script_dir/build-support/opencv4.pc.in" >"$pkgconfig/opencv4.pc"

flatpak run --user --unshare=network --nodevice=all \
  --filesystem="$root:ro" --filesystem="$opencv_prefix:ro" \
  --filesystem="$output" --command=sh org.freedesktop.Sdk//25.08 \
  "$script_dir/build-inner.sh" \
  "$root/reference/libfprint-fedora44-1.94.100/source" \
  "$build_dir" "$pkgconfig" \
  "$output" "$mode" | tee "$output/build.env"

# libgusb is supplied by Fedora; its copy under pkgconfig is build-only.
# Keep the deployable libraries separate from all build inputs and reports.
runtime="$output/runtime"
mkdir -m 0700 -- "$runtime"
mv "$output/libfprint-2.so.2.0.0" "$output/libfprint-2.so.2" \
  "$output/libfprint-2.so" "$runtime/"
for component in core features2d flann imgproc; do
  cp -L "$opencv_prefix/usr/lib64/libopencv_${component}.so.4.13.0" \
    "$runtime/libopencv_${component}.so.413"
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
library="$runtime/libfprint-2.so.2.0.0"
nm "$library" >"$output/library.nm"
while read -r symbol; do
  ! grep -Eq " [A-Za-z] ${symbol}$" "$output/library.nm" || {
    echo "host/test symbol present: $symbol" >&2; exit 1;
  }
done <"$script_dir/host-test-only-symbols.txt"
legacy_policy=GOODIX_D
legacy_policy="${legacy_policy}282_DIRECT_ENROLL_PROFILE"
strings "$library" >"$output/library.strings"
if grep -F "$legacy_policy" "$output/library.strings" >/dev/null; then
  fail HISTORICAL_BUILD_POLICY
fi
readelf -d "$library" >"$output/library.dynamic"
if grep -E '(RPATH|RUNPATH)' "$output/library.dynamic" >/dev/null; then
  fail PRIVATE_RPATH
fi
grep -F '[libfprint-2.so.2]' "$output/library.dynamic" >/dev/null

required="$output/fprintd.required"
provided="$output/libfprint.provided"
nm -D --undefined-only /usr/libexec/fprintd |
  awk '$1=="U" && $2 ~ /@LIBFPRINT_2[.]0[.]0$/ {sub(/@.*/,"",$2); print $2}' |
  sort -u >"$required"
nm -D --defined-only "$library" |
  awk '$3 ~ /@@LIBFPRINT_2[.]0[.]0$/ {sub(/@@.*/,"",$3); print $3}' |
  sort -u >"$provided"
[[ -s $required && -s $provided ]] || fail EMPTY_ABI_SYMBOL_SET
while read -r symbol; do grep -Fx "$symbol" "$provided" >/dev/null; done <"$required"
if [[ $mode == normal ]]; then
  LD_LIBRARY_PATH="$runtime" ldd /usr/libexec/fprintd >"$output/fprintd.ldd" 2>&1
  grep -F "$runtime/libfprint-2.so.2" "$output/fprintd.ldd" >/dev/null
  if grep -F 'not found' "$output/fprintd.ldd" >/dev/null; then
    fail MISSING_RUNTIME_DEPENDENCY
  fi
fi
cp "$output/OpenCV-LICENSES.txt" "$runtime/"
mkdir "$runtime/licenses"
for license in GPL-2.0-or-later LGPL-2.1-or-later GPL-3.0-or-later Apache-2.0; do
  cp "$root/LICENSES/$license.txt" "$runtime/licenses/"
done
cp "$root/docs/LICENSING_AND_PROVENANCE.md" "$runtime/"
cp "$script_dir/source-files.tsv" "$script_dir/source-files.sha256" "$runtime/"
(cd "$runtime" && sha256sum libfprint-2.so.2.0.0 libopencv_*.so.413 >SHA256SUMS)
# Confirm the compile did not alter versioned inputs.
[[ $(git -C "$root" rev-parse HEAD) == "$source_commit" &&
   -z $(git -C "$root" status --porcelain --untracked-files=normal) ]] || fail SOURCE_CHANGED
[[ $(find "$runtime" -maxdepth 1 -type f -name '*.so*' | wc -l) -eq 5 ]] || fail RUNTIME_CONTENTS
printf 'FEDORA_COMPONENTS_REPLACED=NONE\n'
printf 'STOCK_FPRINTD_EXECUTED=false\nUSB_ACCESSED=false\nMATERIAL_LOADER_EXECUTED=false\n'
printf 'RUNTIME_DIRECTORY=%s\nSOURCE_COMMIT=%s\n' "$runtime" "$source_commit"

sha256sum "$library" >"$output/artifact.sha256"
echo MINIMAL_RUNTIME_SCOPE=LIBFPRINT_AND_OPENCV_ONLY
echo "PRODUCTION_BUILD_MODE=$mode"
echo PRODUCTION_HOST_TEST_ONLY_SYMBOL_COUNT=0
echo PRODUCTION_ABI_LIBFPRINT_2_0_0=PASS
echo PRODUCTION_RPATH_PRESENT=false
echo PRODUCTION_PRIVATE_TREE_DEPENDENCY_COUNT=0
echo REAL_USB_ENUMERATION_ATTEMPTED=false
echo LIVE_EXECUTION_PERFORMED=false

echo MINIMAL_RUNTIME_BUILD=PASS
