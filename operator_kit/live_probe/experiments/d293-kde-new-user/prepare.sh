#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
test_user=d293-phase-b-test
fail() { printf 'D293_04_PREPARE=FAIL reason=%s\n' "$1" >&2; exit 1; }

[[ $(id -u) -ne 0 ]] || fail root_forbidden
[[ $(git -C "$root" branch --show-current) == development ]] || fail wrong_branch
head=$(git -C "$root" rev-parse HEAD)
[[ $head == "$(git -C "$root" rev-parse origin/development)" ]] || fail head_origin_mismatch
critical=(production libfprint-driver Rockytkg reference/libfprint-fedora44-1.94.100
  reference/fprintd-fedora44-1.94.5 operator_kit/live_probe
  operator_kit/d285-01-persistent-sudo operator_kit/d286-01-reboot-survival
  "Goodix 27c6 5125 manuale tecnico.md")
[[ -z $(git -C "$root" status --porcelain=v1 --untracked-files=all -- "${critical[@]}") ]] || fail critical_set_dirty
[[ $(rpm -q fprintd) == fprintd-1.94.5-5.fc44.x86_64 ]] || fail fprintd_nevra
[[ $(rpm -q libfprint) == libfprint-1.94.100-1.fc44.x86_64 ]] || fail libfprint_nevra
[[ $(rpm -q plasma-workspace-libs) == plasma-workspace-libs-6.7.5-1.fc44.x86_64 ]] || fail plasma_nevra
getent passwd "$test_user" >/dev/null && fail test_account_already_exists
[[ ! -e /run/goodix-d293-04 && ! -e /run/goodix-d293-04-public ]] || fail prior_runtime_present
[[ ! -e /var/tmp/goodix-d293-04-captures &&
   ! -L /var/tmp/goodix-d293-04-captures ]] || fail prior_capture_root_present

count=0
for device in /sys/bus/usb/devices/*; do
  [[ -f $device/idVendor && -f $device/idProduct ]] || continue
  if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
    count=$((count + 1))
  fi
done
[[ $count -eq 1 ]] || fail goodix_sysfs_cardinality_not_one
for process in fprintd-enroll fprintd-verify fprintd-delete; do
  ! pgrep -x "$process" >/dev/null || fail concurrent_consumer
done

build=$(mktemp -d /tmp/goodix-d293-04-build.XXXXXX)
cleanup_build() {
  if [[ $build == /tmp/goodix-d293-04-build.* && -d $build && ! -L $build ]]; then
    find "$build" -xdev -depth -delete
  fi
}
trap cleanup_build EXIT INT TERM
"$root/production/build.sh" normal "$build/output"
(
  cd "$build/output"
  sha256sum libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
    libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413 \
    >deploy.sha256
)
pkexec "$here/root-helper.sh" --deploy "$build/output" "$head" "$(id -un)"

printf '%s\n' \
  'D293_04_PREPARE=PASS' \
  "D293_04_PRODUCTION_HEAD=$head" \
  'D293_04_TRANSIENT_RUNTIME=ACTIVE' \
  'Aprire ora Impostazioni di sistema → Utenti e creare un normale utente locale con nome:' \
  "  $test_user" \
  'Non eseguire enrollment dall’utente corrente. Attendere la comparsa di:' \
  '  /run/goodix-d293-04-public/public.env' \
  'Poi entrare in una vera sessione Plasma del nuovo utente e seguire README_IT.md.'
