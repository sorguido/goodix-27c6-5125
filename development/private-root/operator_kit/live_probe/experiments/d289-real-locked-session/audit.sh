#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

mode=phase
phase=
if [[ $# -eq 1 && $1 == --read-only-preflight ]]; then
  mode=read-only-preflight
  phase=pre
elif [[ $# -eq 2 && $1 == --phase && ( $2 == pre || $2 == post ) ]]; then
  phase=$2
else
  echo D289_AUDIT_FAILURE=ARGUMENTS_INVALID >&2
  exit 2
fi

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
# shellcheck source=kwin-identity.sh
source "$here/kwin-identity.sh"

d289_audit_fail () {
  printf 'D289_%s_AUDIT=FAIL\nD289_AUDIT_FAILURE=%s\n' "${phase^^}" "$1" >&2
  exit 1
}

d289_require_hash () {
  local path=$1 expected=$2 label=$3 actual
  [[ -f $path && ! -L $path ]] || d289_audit_fail "${label}_TYPE"
  actual=$(sha256sum "$path" 2>/dev/null | awk '{print $1}') || d289_audit_fail "${label}_HASH_UNREADABLE"
  [[ $actual == "$expected" ]] || d289_audit_fail "${label}_HASH_MISMATCH"
}

d289_require_exact_output () {
  local label=$1 expected=$2 output
  shift 2
  output=$("$@" 2>/dev/null) || d289_audit_fail "${label}_UNREADABLE"
  [[ $output == "$expected" ]] || d289_audit_fail "${label}_MISMATCH"
}

d289_require_hash "$here/goodix-d289-kde-fingerprint.pam" \
  126af52cd63c346fdf9fb053172506a49f851d45b0a49e4490fd807a12c328b6 D289_CANDIDATE_PAM
d289_require_exact_output KWIN_RPM kwin-6.7.5-1.fc44.x86_64 rpm -q kwin
d289_require_exact_output KSCREENLOCKER_RPM kscreenlocker-6.7.5-1.fc44.x86_64 rpm -q kscreenlocker
d289_require_exact_output PLASMA_WORKSPACE_RPM plasma-workspace-6.7.5-1.fc44.x86_64 rpm -q plasma-workspace
d289_require_exact_output PAM_RPM pam-1.7.2-2.fc44.x86_64 rpm -q pam
d289_require_exact_output FPRINTD_PAM_RPM fprintd-pam-1.94.5-5.fc44.x86_64 rpm -q fprintd-pam
d289_require_hash /usr/bin/kwin_wayland f6ca8b06614e692bf3c328ff8ec6fa0d22b5b5bca36c28dd6d2aefca40b0c847 KWIN_BINARY
d289_require_hash /usr/lib64/libKScreenLocker.so.6.7.5 3726f465476c039ff877f05b341ed5d88c192bd77356619eb76d4e0ba8a59839 KSCREENLOCKER_LIBRARY
d289_require_hash /usr/libexec/kscreenlocker_greet 45d5a60737ff966b93f60639a662396956b28d50122741261f4351fef941be48 KSCREENLOCKER_GREETER
d289_require_hash /etc/pam.d/kde 7d91b3ad73a998e8b10f9edccd74ba04179a778c4a5e61d9176872f43c7bbac3 KDE_PASSWORD_PAM
d289_require_hash /etc/pam.d/kde-fingerprint 8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437 KDE_FINGERPRINT_PAM
d289_require_hash /usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml \
  328501780ab06cc0497a25ff48c6f027a1abed8506f0969f39a5f8bc6696181c KSCREENLOCKER_QML
if ! strings -el /usr/libexec/kscreenlocker_greet | grep -Fx kde-fingerprint >/dev/null; then
  d289_audit_fail GREETER_FINGERPRINT_SERVICE_MISSING
fi
for command in busctl loginctl pgrep mountpoint pkexec journalctl sha256sum awk sed grep findmnt mount umount chcon; do
  command -v "$command" >/dev/null || d289_audit_fail "COMMAND_${command}_MISSING"
done
echo D289_TARGET_VERSIONS_AND_HASHES=PASS

if [[ ${LIVE_PROBE_MODE:-} == operator-run || $mode == read-only-preflight ]]; then
  user=$(id -un)
  uid=$(id -u)
  [[ $uid -ne 0 ]] || d289_audit_fail ROOT_USER_SESSION_FORBIDDEN
  [[ ${XDG_SESSION_TYPE:-} == wayland ]] || d289_audit_fail SESSION_NOT_WAYLAND
  [[ -n ${WAYLAND_DISPLAY:-} ]] || d289_audit_fail WAYLAND_DISPLAY_MISSING
  d289_require_exact_output KDE_PASSWORD_PAM_MODE root:root:644 stat -Lc '%U:%G:%a' /etc/pam.d/kde
  d289_require_exact_output KDE_FINGERPRINT_PAM_MODE root:root:644 stat -Lc '%U:%G:%a' /etc/pam.d/kde-fingerprint

  owner=$(busctl --user call org.freedesktop.DBus /org/freedesktop/DBus \
    org.freedesktop.DBus GetConnectionUnixProcessID s org.freedesktop.ScreenSaver 2>/dev/null) ||
    d289_audit_fail KWIN_DBUS_OWNER_UNREADABLE
  if ! kwin_pid=$(d289_parse_dbus_owner "$owner"); then
    d289_audit_fail KWIN_DBUS_OWNER_UNPARSABLE
  fi
  if ! identity_output=$(D289_PROC_ROOT=/proc d289_verify_kwin_identity "$kwin_pid" "$uid" 2>&1); then
    printf '%s\n' "$identity_output" >&2
    d289_audit_fail KWIN_COMPOSITE_IDENTITY
  fi
  printf '%s\n' "$identity_output"

  d289_require_exact_output SCREEN_LOCK_ACTIVE 'b false' busctl --user call \
    org.freedesktop.ScreenSaver /ScreenSaver org.freedesktop.ScreenSaver GetActive
  session=$(loginctl show-user "$uid" -p Display --value 2>/dev/null) ||
    d289_audit_fail LOGIND_DISPLAY_SESSION_UNREADABLE
  [[ $session =~ ^[0-9]+$ ]] || d289_audit_fail LOGIND_DISPLAY_SESSION_INVALID
  d289_require_exact_output LOGIND_ACTIVE yes loginctl show-session "$session" -p Active --value
  d289_require_exact_output LOGIND_STATE active loginctl show-session "$session" -p State --value
  d289_require_exact_output LOGIND_TYPE wayland loginctl show-session "$session" -p Type --value
  d289_require_exact_output LOGIND_LOCKED_HINT no loginctl show-session "$session" -p LockedHint --value

  if [[ $phase == pre ]]; then
    if pgrep -u "$uid" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null; then
      d289_audit_fail GREETER_ALREADY_RUNNING
    fi
  else
    deadline=$((SECONDS + 10))
    while pgrep -u "$uid" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null && (( SECONDS < deadline )); do
      sleep 0.1
    done
    if pgrep -u "$uid" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null; then
      d289_audit_fail GREETER_REMAINS_AFTER_RUN
    fi
  fi
  mountpoint -q /etc/pam.d/kde-fingerprint && d289_audit_fail FINGERPRINT_PAM_ALREADY_MOUNTED
  [[ ! -e /run/goodix-d289-real-lock-$uid ]] || d289_audit_fail D289_RUNTIME_ALREADY_PRESENT
  count=0
  for device in /sys/bus/usb/devices/*; do
    [[ -f $device/idVendor && -f $device/idProduct ]] || continue
    if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      count=$((count + 1))
    fi
  done
  [[ $count -eq 1 ]] || d289_audit_fail GOODIX_SYSFS_CARDINALITY_NOT_ONE
  printf '%s\n' \
    "D289_KWIN_DBUS_OWNER=$owner" \
    "D289_KWIN_PID=$kwin_pid" \
    "D289_LOGIND_SESSION=$session" \
    'D289_LOGIND_SESSION_ACTIVE=yes' \
    'D289_LOGIND_SESSION_STATE=active' \
    'D289_LOGIND_SESSION_TYPE=wayland' \
    'D289_LOGIND_LOCKED_HINT=no' \
    'D289_SCREEN_LOCK_ACTIVE=false' \
    'D289_PAM_MODES=root:root:644' \
    'D289_EXISTING_GREETER_COUNT=0' \
    'D289_FINGERPRINT_PAM_MOUNTPOINT=false' \
    'D289_RUNTIME_PRESENT=false' \
    'D289_TARGET_SYSFS_CARDINALITY=1'

  if [[ $mode == read-only-preflight ]]; then
    echo D289_ROOT_AUDIT=NOT_APPLICABLE_READ_ONLY_PREFLIGHT
    echo D289_READ_ONLY_PREFLIGHT=PASS
    echo D289_READ_ONLY_PREFLIGHT_SENSOR_ACTION_COUNT=0
    exit 0
  fi

  audit_phase="D289_REAL_LOCK_${phase^^}"
  if ! audit_output=$(pkexec "$root/operator_kit/d286-01-reboot-survival/run-d286-01.sh" \
    --root-audit "$audit_phase" --user "$user"); then
    d289_audit_fail D286_ROOT_AUDIT_COMMAND_FAILED
  fi
  printf '%s\n' "$audit_output"
  grep -Fx "D286_01_ROOT_AUDIT_PHASE=$audit_phase" <<<"$audit_output" >/dev/null ||
    d289_audit_fail D286_ROOT_AUDIT_PHASE_MISSING
  grep -Fx D286_01_STATE_COHERENCE=PASS_ROOT_ONLY <<<"$audit_output" >/dev/null ||
    d289_audit_fail D286_STATE_COHERENCE_FAILED
  grep -Fx D286_01_PASSWORD_FALLBACK=PASS <<<"$audit_output" >/dev/null ||
    d289_audit_fail D286_PASSWORD_FALLBACK_FAILED
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES <<<"$audit_output" >/dev/null ||
    d289_audit_fail D286_UNINSTALL_READINESS_FAILED
  grep -Fx "D286_01_${audit_phase}_ROOT_AUDIT_SENSOR_ACTION_COUNT=0" <<<"$audit_output" >/dev/null ||
    d289_audit_fail D286_ROOT_AUDIT_SENSOR_COUNT_INVALID
else
  echo "D289_${phase^^}_ROOT_AUDIT=NOT_APPLICABLE_OFFLINE"
fi
echo "D289_${phase^^}_AUDIT=PASS"
echo "D289_${phase^^}_AUDIT_SENSOR_ACTION_COUNT=0"
