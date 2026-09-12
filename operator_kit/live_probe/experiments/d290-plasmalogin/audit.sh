#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

phase=
if [[ $# -eq 2 && $1 == --phase && ( $2 == pre || $2 == post ) ]]; then
  phase=$2
else
  echo D290_AUDIT_FAILURE=ARGUMENTS_INVALID >&2
  exit 2
fi
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
# shellcheck source=session-model.sh
source "$here/session-model.sh"

d290_fail () {
  printf 'D290_%s_AUDIT=FAIL\nD290_AUDIT_FAILURE=%s\n' "${phase^^}" "$1" >&2
  exit 1
}

d290_hash () {
  local path=$1 expected=$2 label=$3 actual
  [[ -f $path && ! -L $path ]] || d290_fail "${label}_TYPE"
  actual=$(sha256sum "$path" 2>/dev/null | awk '{print $1}') || d290_fail "${label}_HASH_UNREADABLE"
  [[ $actual == "$expected" ]] || d290_fail "${label}_HASH_MISMATCH"
}

d290_exact () {
  local label=$1 expected=$2 output
  shift 2
  output=$("$@" 2>/dev/null) || d290_fail "${label}_UNREADABLE"
  [[ $output == "$expected" ]] || d290_fail "${label}_MISMATCH"
}

d290_hash "$here/goodix-d290-plasmalogin.pam" \
  89d389e6c2ee59dcee374029a5428a81dc9138c4f5e86068159b3d5a2c77ab2d D290_CANDIDATE_PAM
d290_hash /usr/lib/pam.d/plasmalogin \
  c6fc4a0bc2d89f88fa15ca7e9a6c5aaeccfbe66897755b5416ce9c5e35b4e40b PLASMALOGIN_HOST_PAM
d290_hash /usr/bin/plasmalogin \
  4de1dfb9181818c43e6a4481d3c1ba2272ddac1218f727418301e45bffc54ebd PLASMALOGIN_DAEMON
d290_hash /usr/libexec/plasmalogin-helper \
  382bbf8d62b78cff1b93a2e811e67edd82c87054ea4614aca6e7cd355c61ffe4 PLASMALOGIN_HELPER
d290_hash /usr/libexec/plasma-login-greeter \
  b40c3c90d1de811ffcb41b45afd4d485e1f0c478d173607b2b48c03c540e7ac0 PLASMALOGIN_GREETER
d290_exact PLASMALOGIN_RPM plasma-login-manager-6.7.5-1.fc44.x86_64 rpm -q plasma-login-manager
d290_exact PAM_RPM pam-1.7.2-2.fc44.x86_64 rpm -q pam
d290_exact FPRINTD_RPM fprintd-1.94.5-5.fc44.x86_64 rpm -q fprintd
d290_exact FPRINTD_PAM_RPM fprintd-pam-1.94.5-5.fc44.x86_64 rpm -q fprintd-pam
for command in loginctl systemctl pgrep pkexec journalctl sha256sum awk sed grep \
  mountpoint findmnt mount umount chcon; do
  command -v "$command" >/dev/null || d290_fail "COMMAND_${command}_MISSING"
done
echo D290_TARGET_VERSIONS_AND_HASHES=PASS

if [[ ${LIVE_PROBE_MODE:-} == operator-run ]]; then
  user=$(id -un)
  uid=$(id -u)
  [[ $uid -ne 0 ]] || d290_fail ROOT_EXECUTION_FORBIDDEN
  [[ ${XDG_SESSION_TYPE:-} == tty ]] || d290_fail OPERATOR_NOT_IN_TTY_SESSION
  [[ ${XDG_SESSION_ID:-} =~ ^[0-9]+$ ]] || d290_fail OPERATOR_SESSION_ID_INVALID
  d290_exact OPERATOR_SESSION_USER "$uid" loginctl show-session "$XDG_SESSION_ID" -p User --value
  d290_exact OPERATOR_SESSION_TYPE tty loginctl show-session "$XDG_SESSION_ID" -p Type --value
  d290_exact OPERATOR_SESSION_CLASS user loginctl show-session "$XDG_SESSION_ID" -p Class --value
  d290_exact OPERATOR_SESSION_STATE active loginctl show-session "$XDG_SESSION_ID" -p State --value
  d290_exact OPERATOR_SESSION_TTY tty3 loginctl show-session "$XDG_SESSION_ID" -p TTY --value
  d290_exact PLASMALOGIN_SERVICE_STATE active systemctl show plasmalogin.service -p ActiveState --value
  d290_exact PLASMALOGIN_SERVICE_SUBSTATE running systemctl show plasmalogin.service -p SubState --value
  d290_exact PLASMALOGIN_PAM_MODE root:root:644 stat -Lc '%U:%G:%a' /usr/lib/pam.d/plasmalogin
  mountpoint -q /usr/lib/pam.d/plasmalogin && d290_fail PLASMALOGIN_PAM_ALREADY_MOUNTED
  [[ ! -e /run/goodix-d290-plasmalogin-$uid ]] || d290_fail D290_RUNTIME_ALREADY_PRESENT

  daemon_pid=$(systemctl show plasmalogin.service -p MainPID --value 2>/dev/null) || d290_fail DAEMON_PID_UNREADABLE
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || d290_fail DAEMON_PID_INVALID
  daemon_uid=$(awk '/^Uid:/ {print $2}' "/proc/$daemon_pid/status" 2>/dev/null) || d290_fail DAEMON_UID_UNREADABLE
  daemon_comm=$(<"/proc/$daemon_pid/comm") || d290_fail DAEMON_COMM_UNREADABLE
  daemon_cgroup=$(awk -F: 'NR==1 {print $NF}' "/proc/$daemon_pid/cgroup" 2>/dev/null) || d290_fail DAEMON_CGROUP_UNREADABLE
  [[ $daemon_uid == 0 && $daemon_comm == plasmalogin && $daemon_cgroup == /system.slice/plasmalogin.service ]] ||
    d290_fail DAEMON_COMPOSITE_IDENTITY

  graphical_records=
  if [[ $phase == pre ]]; then
    graphical_records=$(d290_initial_graphical_session_records "$uid" "$XDG_SESSION_ID") ||
      d290_fail INITIAL_GRAPHICAL_SESSION_ENUMERATION_FAILED
  else
    graphical_records=$(d290_current_graphical_session_records "$uid" "$XDG_SESSION_ID") ||
      d290_fail POST_GRAPHICAL_SESSION_ENUMERATION_FAILED
  fi
  graphical_rows=()
  [[ -z $graphical_records ]] || mapfile -t graphical_rows <<<"$graphical_records"
  graphical=${#graphical_rows[@]}
  graphical_ids=()
  for record in "${graphical_rows[@]}"; do
    IFS='|' read -r session_id tty service type class state <<<"$record"
    graphical_ids+=("$session_id")
  done

  if [[ $phase == pre ]]; then
    initial_id=NONE initial_tty=NONE initial_service=NONE
    initial_type=NONE initial_class=NONE initial_state=NONE
    if [[ $graphical -eq 1 ]]; then
      IFS='|' read -r initial_id initial_tty initial_service initial_type initial_class initial_state \
        <<<"${graphical_rows[0]}"
    elif [[ $graphical -gt 1 ]]; then
      initial_id=AMBIGUOUS
    fi
    printf '%s\n' \
      "D290_OPERATOR_TTY_SESSION=$XDG_SESSION_ID" \
      "D290_INITIAL_GRAPHICAL_SESSION_COUNT=$graphical" \
      "D290_INITIAL_GRAPHICAL_SESSION_ID=$initial_id" \
      "D290_INITIAL_GRAPHICAL_SESSION_TTY=$initial_tty" \
      "D290_INITIAL_GRAPHICAL_SESSION_SERVICE=$initial_service" \
      "D290_INITIAL_GRAPHICAL_SESSION_TYPE=$initial_type" \
      "D290_INITIAL_GRAPHICAL_SESSION_CLASS=$initial_class" \
      "D290_INITIAL_GRAPHICAL_SESSION_STATE=$initial_state"
    [[ $graphical -eq 1 ]] || d290_fail INITIAL_GRAPHICAL_SESSION_CARDINALITY_NOT_ONE
    greeter_uid=$(id -u plasmalogin) || d290_fail GREETER_UID_UNREADABLE
    pgrep -u "$greeter_uid" -f '^/usr/libexec/plasma-login-greeter([[:space:]]|$)' >/dev/null &&
      d290_fail GREETER_ALREADY_RUNNING
  else
    (( graphical <= 1 )) || d290_fail POST_GRAPHICAL_SESSION_CARDINALITY_OVER_ONE
  fi

  count=0
  for device in /sys/bus/usb/devices/*; do
    [[ -f $device/idVendor && -f $device/idProduct ]] || continue
    if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      count=$((count + 1))
    fi
  done
  [[ $count -eq 1 ]] || d290_fail GOODIX_SYSFS_CARDINALITY_NOT_ONE
  printf '%s\n' \
    "D290_PLASMALOGIN_DAEMON_PID=$daemon_pid" \
    'D290_PLASMALOGIN_DAEMON_IDENTITY=PASS_COMPOSITE' \
    "D290_${phase^^}_GRAPHICAL_SESSION_COUNT=$graphical" \
    "D290_${phase^^}_GRAPHICAL_SESSION_IDS=${graphical_ids[*]:-NONE}" \
    'D290_PLASMALOGIN_PAM_MOUNTPOINT=false' \
    'D290_RUNTIME_PRESENT=false' \
    'D290_TARGET_SYSFS_CARDINALITY=1'

  audit_phase="D290_PLASMALOGIN_${phase^^}"
  if ! audit_output=$(pkexec "$root/operator_kit/d286-01-reboot-survival/run-d286-01.sh" \
    --root-audit "$audit_phase" --user "$user"); then
    d290_fail D286_ROOT_AUDIT_COMMAND_FAILED
  fi
  printf '%s\n' "$audit_output"
  grep -Fx "D286_01_ROOT_AUDIT_PHASE=$audit_phase" <<<"$audit_output" >/dev/null ||
    d290_fail D286_ROOT_AUDIT_PHASE_MISSING
  grep -Fx D286_01_STATE_COHERENCE=PASS_ROOT_ONLY <<<"$audit_output" >/dev/null ||
    d290_fail D286_STATE_COHERENCE_FAILED
  grep -Fx D286_01_PASSWORD_FALLBACK=PASS <<<"$audit_output" >/dev/null ||
    d290_fail D286_PASSWORD_FALLBACK_FAILED
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES <<<"$audit_output" >/dev/null ||
    d290_fail D286_UNINSTALL_READINESS_FAILED
  grep -Fx "D286_01_${audit_phase}_ROOT_AUDIT_SENSOR_ACTION_COUNT=0" <<<"$audit_output" >/dev/null ||
    d290_fail D286_ROOT_AUDIT_SENSOR_COUNT_INVALID
else
  echo "D290_${phase^^}_ROOT_AUDIT=NOT_APPLICABLE_OFFLINE"
fi
echo "D290_${phase^^}_AUDIT=PASS"
echo "D290_${phase^^}_AUDIT_SENSOR_ACTION_COUNT=0"
