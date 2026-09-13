#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# -eq 2 && $1 == --phase && ( $2 == pre || $2 == post ) ]] || exit 2
phase=$2
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
test_user=d293-phase-b-test
public=/run/goodix-d293-04-public
fail() { printf 'D293_04_%s_AUDIT=FAIL reason=%s\n' "${phase^^}" "$1" >&2; exit 1; }
require_output() { local expected=$1; shift; [[ $("$@") == "$expected" ]] || fail "output_$expected"; }
require_hash() { [[ -f $1 && ! -L $1 && $(sha256sum "$1" | awk '{print $1}') == "$2" ]] || fail "hash_$(basename "$1")"; }

require_output fprintd-1.94.5-5.fc44.x86_64 rpm -q fprintd
require_output libfprint-1.94.100-1.fc44.x86_64 rpm -q libfprint
require_output plasma-workspace-libs-6.7.5-1.fc44.x86_64 rpm -q plasma-workspace-libs
require_hash /usr/lib64/qt6/plugins/plasma/kcms/systemsettings/kcm_users.so \
  764b86abb81f4be9ee38c836a558955bca192546dc77158e2ace72e8bb2cf2d9
require_hash /usr/share/applications/kcm_users.desktop \
  c27ab075c4e07d07631ae584695bc62376d3e3f1db258f20e622d6fda9e6c4be
for command in fprintd-list fprintd-verify systemsettings journalctl findmnt pgrep; do
  command -v "$command" >/dev/null || fail "command_$command"
done

if [[ ${LIVE_PROBE_MODE:-} == offline-test ]]; then
  echo "D293_04_${phase^^}_AUDIT=PASS_OFFLINE"
  echo "D293_04_${phase^^}_AUDIT_SENSOR_ACTION_COUNT=0"
  exit 0
fi

[[ $(id -un) == "$test_user" && $(id -u) -ge 1000 ]] || fail wrong_test_account
[[ ${XDG_SESSION_TYPE:-} == wayland && -n ${WAYLAND_DISPLAY:-} ]] || fail not_wayland_session
[[ $(getent passwd "$test_user" | cut -d: -f6) == /home/$test_user ]] || fail home_mismatch
[[ -f $public/public.env && ! -L $public/public.env ]] || fail public_state_missing
head=$(sed -n 's/^D293_04_PRODUCTION_HEAD=//p' "$public/public.env")
[[ $head =~ ^[0-9a-f]{40}$ && $head == "$(git -C "$root" rev-parse HEAD)" ]] || fail provenance_mismatch
[[ $(git -C "$root" rev-parse HEAD) == "$(git -C "$root" rev-parse origin/development)" ]] || fail head_origin_mismatch
options=$(findmnt -n -o OPTIONS --target "$root") || fail repo_mount_missing
[[ ,$options, == *,ro,* && ,$options, == *,nodev,* && ,$options, == *,nosuid,* ]] || fail repo_mount_not_read_only

if [[ $phase == pre ]]; then
  grep -Fx D293_04_PHASE=READY_FOR_NEW_USER "$public/public.env" >/dev/null || fail runtime_not_ready
  systemctl cat fprintd.service 2>/dev/null |
    grep -Fx 'ExecStart=/run/goodix-d293-04/wrapper' >/dev/null || fail transient_dropin_not_loaded
  ! systemctl is-active --quiet fprintd.service || fail fprintd_already_active
  for process in fprintd-enroll fprintd-verify fprintd-delete systemsettings; do
    ! pgrep -u "$(id -u)" -x "$process" >/dev/null || fail concurrent_consumer
  done
else
  grep -Fx D293_04_PHASE=RUNTIME_ROLLED_BACK "$public/public.env" >/dev/null || fail rollback_phase
  [[ -f $public/rollback.env ]] || fail rollback_result_missing
  grep -Fx D293_04_RUNTIME_ROLLBACK=PASS "$public/rollback.env" >/dev/null || fail runtime_rollback
  grep -Fx D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=true "$public/rollback.env" >/dev/null || fail existing_principal_drift
  grep -Fx D293_04_TEST_STORAGE=PASS "$public/rollback.env" >/dev/null || fail test_storage_remains
fi

count=0
for device in /sys/bus/usb/devices/*; do
  [[ -f $device/idVendor && -f $device/idProduct ]] || continue
  [[ $(<"$device/idVendor") != 27c6 || $(<"$device/idProduct") != 5125 ]] || count=$((count + 1))
done
[[ $count -eq 1 ]] || fail goodix_sysfs_cardinality
echo "D293_04_${phase^^}_AUDIT=PASS"
echo "D293_04_${phase^^}_GOODIX_SYSFS_CARDINALITY=1"
echo "D293_04_${phase^^}_AUDIT_SENSOR_ACTION_COUNT=0"
