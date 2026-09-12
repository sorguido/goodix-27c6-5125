#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# -eq 2 && $1 == --phase ]]
phase=$2
[[ $phase == pre || $phase == post ]]
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)

verify_hash () {
  [[ -f $1 && ! -L $1 && $(sha256sum "$1" | awk '{print $1}') == "$2" ]]
}

verify_hash "$here/goodix-d289-kde-fingerprint.pam" 126af52cd63c346fdf9fb053172506a49f851d45b0a49e4490fd807a12c328b6
[[ $(rpm -q kwin) == kwin-6.7.5-1.fc44.x86_64 ]]
[[ $(rpm -q kscreenlocker) == kscreenlocker-6.7.5-1.fc44.x86_64 ]]
[[ $(rpm -q plasma-workspace) == plasma-workspace-6.7.5-1.fc44.x86_64 ]]
[[ $(rpm -q pam) == pam-1.7.2-2.fc44.x86_64 ]]
[[ $(rpm -q fprintd-pam) == fprintd-pam-1.94.5-5.fc44.x86_64 ]]
verify_hash /usr/bin/kwin_wayland f6ca8b06614e692bf3c328ff8ec6fa0d22b5b5bca36c28dd6d2aefca40b0c847
verify_hash /usr/lib64/libKScreenLocker.so.6.7.5 3726f465476c039ff877f05b341ed5d88c192bd77356619eb76d4e0ba8a59839
verify_hash /usr/libexec/kscreenlocker_greet 45d5a60737ff966b93f60639a662396956b28d50122741261f4351fef941be48
verify_hash /etc/pam.d/kde 7d91b3ad73a998e8b10f9edccd74ba04179a778c4a5e61d9176872f43c7bbac3
verify_hash /etc/pam.d/kde-fingerprint 8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437
verify_hash /usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml 328501780ab06cc0497a25ff48c6f027a1abed8506f0969f39a5f8bc6696181c
strings -el /usr/libexec/kscreenlocker_greet | grep -Fx kde-fingerprint >/dev/null
for command in busctl loginctl pgrep mountpoint pkexec journalctl sha256sum awk sed grep findmnt mount umount chcon; do
  command -v "$command" >/dev/null
done

if [[ ${LIVE_PROBE_MODE:-} == operator-run ]]; then
  user=$(id -un)
  uid=$(id -u)
  [[ $uid -ne 0 && ${XDG_SESSION_TYPE:-} == wayland ]]
  [[ $(stat -Lc '%U:%G:%a' /etc/pam.d/kde) == root:root:644 ]]
  [[ $(stat -Lc '%U:%G:%a' /etc/pam.d/kde-fingerprint) == root:root:644 ]]
  owner=$(busctl --user call org.freedesktop.DBus /org/freedesktop/DBus \
    org.freedesktop.DBus GetConnectionUnixProcessID s org.freedesktop.ScreenSaver)
  [[ $owner =~ ^u\ ([1-9][0-9]*)$ ]]
  kwin_pid=${BASH_REMATCH[1]}
  [[ $(readlink -f "/proc/$kwin_pid/exe") == /usr/bin/kwin_wayland ]]
  [[ $(awk '/^Uid:/ {print $2}' "/proc/$kwin_pid/status") == "$uid" ]]
  [[ $(busctl --user call org.freedesktop.ScreenSaver /ScreenSaver \
    org.freedesktop.ScreenSaver GetActive) == 'b false' ]]
  session=$(loginctl show-user "$uid" -p Display --value)
  [[ $session =~ ^[0-9]+$ ]]
  [[ $(loginctl show-session "$session" -p Active --value) == yes ]]
  [[ $(loginctl show-session "$session" -p State --value) == active ]]
  [[ $(loginctl show-session "$session" -p Type --value) == wayland ]]
  [[ $(loginctl show-session "$session" -p LockedHint --value) == no ]]
  if [[ $phase == pre ]]; then
    ! pgrep -u "$uid" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null
  else
    deadline=$((SECONDS + 10))
    while pgrep -u "$uid" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null && (( SECONDS < deadline )); do
      sleep 0.1
    done
    ! pgrep -u "$uid" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null
  fi
  ! mountpoint -q /etc/pam.d/kde-fingerprint
  [[ ! -e /run/goodix-d289-real-lock-$uid ]]
  count=0
  for device in /sys/bus/usb/devices/*; do
    [[ -f $device/idVendor && -f $device/idProduct ]] || continue
    if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      count=$((count + 1))
    fi
  done
  [[ $count -eq 1 ]]
  echo "D289_KWIN_PID=$kwin_pid"
  echo "D289_LOGIND_SESSION=$session"
  echo D289_SCREEN_LOCK_ACTIVE=false
  echo D289_TARGET_SYSFS_CARDINALITY=1
  echo D289_EXISTING_GREETER_COUNT=0
  audit_phase="D289_REAL_LOCK_${phase^^}"
  audit_output=$(pkexec "$root/operator_kit/d286-01-reboot-survival/run-d286-01.sh" \
    --root-audit "$audit_phase" --user "$user")
  printf '%s\n' "$audit_output"
  grep -Fx "D286_01_ROOT_AUDIT_PHASE=$audit_phase" <<<"$audit_output" >/dev/null
  grep -Fx D286_01_STATE_COHERENCE=PASS_ROOT_ONLY <<<"$audit_output" >/dev/null
  grep -Fx D286_01_PASSWORD_FALLBACK=PASS <<<"$audit_output" >/dev/null
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES <<<"$audit_output" >/dev/null
  grep -Fx "D286_01_${audit_phase}_ROOT_AUDIT_SENSOR_ACTION_COUNT=0" <<<"$audit_output" >/dev/null
else
  echo "D289_${phase^^}_ROOT_AUDIT=NOT_APPLICABLE_OFFLINE"
fi
echo "D289_${phase^^}_AUDIT=PASS"
echo "D289_${phase^^}_AUDIT_SENSOR_ACTION_COUNT=0"
