#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Compile/run the existing synthetic adapter suite; never install a runtime.
set -euo pipefail
umask 077
if [[ ${1:-} == --help && $# -eq 1 ]]; then
  echo "usage: $0 <new-absolute-output-directory>"
  echo "Human VM-only synthetic tests; no sensor, materials, daemon or installation."
  exit 0
fi
[[ $# -eq 1 && $1 == /* && $1 != / ]] || { echo "new absolute output directory required" >&2; exit 2; }
systemd-detect-virt --vm --quiet || { echo R3_TEST=FAIL_VM_REQUIRED >&2; exit 1; }
[[ $EUID -ne 0 ]] || { echo "run as the ordinary VM user" >&2; exit 1; }
source /etc/os-release
[[ $ID == fedora && $VERSION_ID == 44 && $(uname -m) == x86_64 ]] || exit 1
for device in /sys/bus/usb/devices/*; do
  if [[ -f $device/idVendor && -f $device/idProduct &&
        $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
    echo "disconnect the reader from the VM" >&2; exit 1
  fi
done
root=$(git -C "$(dirname -- "$(realpath -- "$0")")" rev-parse --show-toplevel)
[[ $(git -C "$root" branch --show-current) == development &&
   -z $(git -C "$root" status --porcelain) ]] || { echo "clean development required" >&2; exit 1; }
source_commit=$(git -C "$root" rev-parse HEAD)
output=$(realpath -m -- "$1")
[[ ! -e $output && ! -L $output ]] || { echo "output already exists" >&2; exit 1; }
case "$output/" in "$root/"*) echo "output must be outside the checkout" >&2; exit 1;; esac
for path in "$root" "$output"; do
  [[ $path != *[[:space:]\\\|\&]* ]] || { echo "use paths without whitespace or shell separators" >&2; exit 1; }
done
flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null
"$root/production/check-source.sh" --driver-only
mkdir -m 0700 -- "$output"
printf 'SOURCE_COMMIT=%s\nTEST_SCOPE=SYNTHETIC_STOCK_ATTEMPTS\n' "$source_commit" >"$output/provenance.txt"
rpm -q fprintd >>"$output/provenance.txt"
mkdir -- "$output/build"
flatpak run --user --unshare=network --nodevice=all --nofilesystem=host:reset \
  --filesystem="$root:ro" --filesystem="$output" \
  --env=GOODIX_STOCK_ATTEMPT_TEST=1 \
  --env=GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE_TEST=1 \
  --command=sh org.freedesktop.Sdk//25.08 \
  "$root/libfprint-driver/tests/run_goodix_fpimage_device_test_inner.sh" \
  "$root" "$output/build" 2>&1 | tee "$output/tests.log"
[[ $(git -C "$root" rev-parse HEAD) == "$source_commit" &&
   -z $(git -C "$root" status --porcelain) ]] || { echo "source changed" >&2; exit 1; }
printf 'SOURCE_COMMIT=%s\nR3_STOCK_ATTEMPTS_VM_TEST=PASS\nR3_INSTALLED_RUNTIME_CHANGED=false\n' "$source_commit"
cat "$output/provenance.txt"
