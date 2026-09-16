#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

d289_identity_failure () {
  printf 'D289_KWIN_IDENTITY_RESULT=FAIL\nD289_KWIN_IDENTITY_FAILURE=%s\n' "$1" >&2
  return 1
}

d289_parse_dbus_owner () {
  local owner=${1-}
  if [[ $owner =~ ^u\ ([1-9][0-9]*)$ ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
    return 0
  fi
  printf 'D289_KWIN_OWNER_PARSE=FAIL\n' >&2
  return 1
}

d289_verify_kwin_identity () {
  local pid=${1-} expected_uid=${2-}
  local proc_root=${D289_PROC_ROOT:-/proc} proc_dir actual_uid comm cmdline first cgroup exe
  local cmdline_status=UNREADABLE exe_status=UNREADABLE_ACCEPTED_WITH_COMPOSITE

  [[ $pid =~ ^[1-9][0-9]*$ ]] || d289_identity_failure PID_INVALID || return
  [[ $expected_uid =~ ^[1-9][0-9]*$ ]] || d289_identity_failure EXPECTED_UID_INVALID || return
  proc_dir=$proc_root/$pid
  [[ -d $proc_dir ]] || d289_identity_failure PROC_ENTRY_MISSING || return

  actual_uid=$(awk '/^Uid:/ {print $2}' "$proc_dir/status" 2>/dev/null) ||
    d289_identity_failure STATUS_UNREADABLE || return
  [[ $actual_uid =~ ^[0-9]+$ ]] || d289_identity_failure UID_UNPARSABLE || return
  [[ $actual_uid == "$expected_uid" ]] || d289_identity_failure UID_MISMATCH || return

  comm=$(sed -n '1p' "$proc_dir/comm" 2>/dev/null) ||
    d289_identity_failure COMM_UNREADABLE || return
  [[ $comm == kwin_wayland ]] || d289_identity_failure COMM_MISMATCH || return

  if cmdline=$(tr '\0' ' ' <"$proc_dir/cmdline" 2>/dev/null); then
    [[ -n ${cmdline//[[:space:]]/} ]] || d289_identity_failure CMDLINE_EMPTY || return
    first=${cmdline%%[[:space:]]*}
    [[ $first == /usr/bin/kwin_wayland ]] || d289_identity_failure CMDLINE_MISMATCH || return
    cmdline_status=COHERENT
  fi

  cgroup=$(sed -n 's/^0:://p' "$proc_dir/cgroup" 2>/dev/null) ||
    d289_identity_failure CGROUP_UNREADABLE || return
  [[ -n $cgroup && $cgroup != *$'\n'* ]] || d289_identity_failure CGROUP_UNPARSABLE || return
  case "$cgroup" in
    /user.slice/user-"$expected_uid".slice/user@"$expected_uid".service/*|/user.slice/user-"$expected_uid".slice/session-*.scope/*) ;;
    /user.slice/user-0.slice/*|/system.slice/*) d289_identity_failure ROOT_OR_SYSTEM_CGROUP; return ;;
    *) d289_identity_failure USER_CGROUP_MISMATCH; return ;;
  esac

  if [[ -L $proc_dir/exe ]] && exe=$(readlink -f "$proc_dir/exe" 2>/dev/null) && [[ -n $exe ]]; then
    [[ $exe == /usr/bin/kwin_wayland ]] || d289_identity_failure EXE_MISMATCH || return
    exe_status=COHERENT
  fi

  printf '%s\n' \
    'D289_KWIN_IDENTITY_RESULT=PASS' \
    "D289_KWIN_IDENTITY_PID=$pid" \
    "D289_KWIN_IDENTITY_UID=$actual_uid" \
    "D289_KWIN_IDENTITY_COMM=$comm" \
    "D289_KWIN_IDENTITY_CMDLINE=$cmdline_status" \
    "D289_KWIN_IDENTITY_CGROUP=$cgroup" \
    "D289_KWIN_IDENTITY_EXE=$exe_status"
}
