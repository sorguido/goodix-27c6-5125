#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
test_user=d293-phase-b-test
capture_base=/var/tmp/goodix-d293-04-captures
sysfs_root=/sys/bus/usb/devices
runtime_private=/run/goodix-d293-04
runtime_public=/run/goodix-d293-04-public
git_command=/usr/bin/git
rpm_command=/usr/bin/rpm
getent_command=/usr/bin/getent
pgrep_command=/usr/bin/pgrep
pkexec_command=/usr/bin/pkexec
fail() { printf 'D293_04_PREPARE=FAIL reason=%s\n' "$1" >&2; exit 1; }

if [[ ${D293_04_PREPARE_MODE:-operator} == offline-script-test ]]; then
  test_root=${D293_04_PREPARE_TEST_ROOT:?}
  [[ $test_root == /tmp/d293-04-prepare-test.* && -d $test_root && -O $test_root &&
     ! -L $test_root ]] || fail unsafe_test_root
  command_dir=$test_root/commands
  [[ -d $command_dir && -O $command_dir && ! -L $command_dir ]] || fail unsafe_test_commands
  for name in git rpm getent pgrep pkexec build; do
    [[ -f $command_dir/$name && -x $command_dir/$name && -O $command_dir/$name &&
       ! -L $command_dir/$name ]] || fail "unsafe_test_command_$name"
  done
  git_command=$command_dir/git
  rpm_command=$command_dir/rpm
  getent_command=$command_dir/getent
  pgrep_command=$command_dir/pgrep
  pkexec_command=$command_dir/pkexec
  build_command=$command_dir/build
  capture_base=$test_root/captures
  sysfs_root=$test_root/sysfs
  runtime_private=$test_root/runtime-private
  runtime_public=$test_root/runtime-public
else
  [[ ${D293_04_PREPARE_MODE:-operator} == operator ]] || fail invalid_mode
fi

root=$($git_command -C "$here" rev-parse --show-toplevel) || fail git_root
[[ ${EUID:-$(id -u)} -ne 0 ]] || fail root_forbidden
[[ $($git_command -C "$root" branch --show-current) == development ]] || fail wrong_branch
head=$($git_command -C "$root" rev-parse HEAD)
[[ $head == "$($git_command -C "$root" rev-parse origin/development)" ]] || fail head_origin_mismatch
critical=(production libfprint-driver Rockytkg reference/libfprint-fedora44-1.94.100
  reference/fprintd-fedora44-1.94.5 operator_kit/live_probe
  operator_kit/d285-01-persistent-sudo operator_kit/d286-01-reboot-survival
  "Goodix 27c6 5125 manuale tecnico.md")
[[ -z $($git_command -C "$root" status --porcelain=v1 --untracked-files=all -- "${critical[@]}") ]] ||
  fail critical_set_dirty
[[ $($rpm_command -q fprintd) == fprintd-1.94.5-5.fc44.x86_64 ]] || fail fprintd_nevra
[[ $($rpm_command -q libfprint) == libfprint-1.94.100-1.fc44.x86_64 ]] || fail libfprint_nevra
[[ $($rpm_command -q plasma-workspace-libs) == plasma-workspace-libs-6.7.5-1.fc44.x86_64 ]] ||
  fail plasma_nevra
$getent_command passwd "$test_user" >/dev/null && fail test_account_already_exists
[[ ! -e $runtime_private && ! -e $runtime_public ]] || fail prior_runtime_present
[[ ! -e $capture_base || (-d $capture_base && ! -L $capture_base) ]] || fail capture_base_invalid

random_hex=$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')
[[ $random_hex =~ ^[0-9a-f]{12}$ ]] || fail run_random_invalid
run_id=d293-04-$(date -u +%Y%m%dT%H%M%SZ)-$random_hex
[[ ! -e $capture_base/$run_id && ! -L $capture_base/$run_id ]] || fail run_capture_collision

count=0
for device in "$sysfs_root"/*; do
  [[ -f $device/idVendor && -f $device/idProduct ]] || continue
  if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
    count=$((count + 1))
  fi
done
[[ $count -eq 1 ]] || fail goodix_sysfs_cardinality_not_one
for process in fprintd-enroll fprintd-verify fprintd-delete; do
  ! $pgrep_command -x "$process" >/dev/null || fail concurrent_consumer
done

build=$(mktemp -d /tmp/goodix-d293-04-build.XXXXXX)
cleanup_build() {
  if [[ $build == /tmp/goodix-d293-04-build.* && -d $build && ! -L $build ]]; then
    find "$build" -xdev -depth -delete
  fi
}
trap cleanup_build EXIT INT TERM
if [[ ${D293_04_PREPARE_MODE:-operator} == offline-script-test ]]; then
  "$build_command" normal "$build/output"
else
  "$root/production/build.sh" normal "$build/output"
fi
(
  cd "$build/output"
  sha256sum libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
    libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413 \
    >deploy.sha256
)
"$pkexec_command" "$here/root-helper.sh" --deploy "$build/output" "$head" "$(id -un)" "$run_id"

printf '%s\n' \
  'D293_04_PREPARE=PASS' \
  "D293_04_PRODUCTION_HEAD=$head" \
  "D293_04_RUN_ID=$run_id" \
  'D293_04_TRANSIENT_RUNTIME=ACTIVE' \
  'Aprire ora Impostazioni di sistema → Utenti e creare un normale utente locale con nome:' \
  "  $test_user" \
  'Non eseguire enrollment dall’utente corrente. Attendere il valore esatto:' \
  '  D293_04_PHASE=READY_FOR_NEW_USER' \
  'nel file /run/goodix-d293-04-public/public.env.' \
  'Poi entrare in una vera sessione Plasma del nuovo utente e seguire README_IT.md.'
