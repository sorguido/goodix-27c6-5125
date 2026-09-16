#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

d290_digest () { sha256sum "$1" | awk '{print $1}'; }

d290_owner_alive () {
  local actual_uid actual_start
  [[ $owner_pid =~ ^[1-9][0-9]*$ && $owner_start_time =~ ^[1-9][0-9]*$ && -r /proc/$owner_pid/status && -r /proc/$owner_pid/stat ]]
  actual_uid=$(awk '/^Uid:/ {print $2}' "/proc/$owner_pid/status")
  actual_start=$(awk '{print $22}' "/proc/$owner_pid/stat")
  [[ $actual_uid == "$operator_uid" && $actual_start == "$owner_start_time" ]]
}

d290_stop_control_watchdog () {
  local wait_rc
  [[ ${control_watchdog_pid:-} =~ ^[1-9][0-9]*$ ]] || return 0
  kill "$control_watchdog_pid" 2>/dev/null || true
  set +e
  wait "$control_watchdog_pid" 2>/dev/null
  wait_rc=$?
  set -e
  control_watchdog_pid=
  [[ $wait_rc -eq 0 || $wait_rc -eq 143 ]]
}

d290_control_watchdog () {
  while d290_owner_alive; do
    sleep 0.2
  done
  printf 'OWNER_DIED\n' >"$control_fifo" 2>/dev/null || true
}

d290_cleanup_overlay () {
  local rc=0
  d290_stop_control_watchdog || rc=1
  if [[ $mounted == true ]]; then
    if umount "$target"; then
      mounted=false
    else
      rc=1
    fi
  fi
  if ! mountpoint -q "$target"; then
    echo D290_ROOT_OVERLAY_UNMOUNTED=true
  else
    echo D290_ROOT_OVERLAY_UNMOUNTED=false
    rc=1
  fi
  if [[ -f $target && ! -L $target && $(d290_digest "$target") == "$expected_host" ]]; then
    echo D290_ROOT_HOST_PAM_RESTORED=true
  else
    echo D290_ROOT_HOST_PAM_RESTORED=false
    rc=1
  fi
  if [[ -n $runtime && $runtime == "$expected_runtime" && -e $runtime ]] &&
     ! mountpoint -q "$target"; then
    if [[ -f $runtime/plasmalogin ]]; then
      if [[ ! -L $runtime/plasmalogin && $(d290_digest "$runtime/plasmalogin") == "$expected_candidate" ]]; then
        rm -f -- "$runtime/plasmalogin"
      else
        rc=1
      fi
    fi
    rmdir -- "$runtime" 2>/dev/null || rc=1
  fi
  if [[ -z $runtime || ! -e $runtime ]]; then
    echo D290_ROOT_RUNTIME_REMOVED=true
  else
    echo D290_ROOT_RUNTIME_REMOVED=false
    rc=1
  fi
  return "$rc"
}

d290_validate_control_fifo () {
  local parent canonical fifo_uid fifo_mode fifo_type parent_uid parent_mode parent_type
  [[ -n $control_fifo && -p $control_fifo && ! -L $control_fifo ]]
  parent=$(dirname -- "$control_fifo")
  [[ $(basename -- "$control_fifo") == d290-root-control.fifo ]]
  [[ $(basename -- "$parent") == goodix-live-probe.* ]]
  canonical=$(readlink -f -- "$control_fifo")
  [[ $canonical == "$control_fifo" ]]
  IFS=: read -r fifo_uid fifo_mode fifo_type < <(stat -Lc '%u:%a:%F' "$control_fifo")
  IFS=: read -r parent_uid parent_mode parent_type < <(stat -Lc '%u:%a:%F' "$parent")
  [[ $fifo_uid == "$operator_uid" && $fifo_mode == 600 && $fifo_type == fifo ]]
  [[ $parent_uid == "$operator_uid" && $parent_mode == 700 && $parent_type == directory ]]
}

d290_validate_daemon_identity () {
  local daemon_pid
  daemon_pid=$(systemctl show plasmalogin.service -p MainPID --value)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]]
  [[ $(awk '/^Uid:/ {print $2}' "/proc/$daemon_pid/status") == 0 ]]
  [[ $(<"/proc/$daemon_pid/comm") == plasmalogin ]]
  [[ $(tr '\0' ' ' <"/proc/$daemon_pid/cmdline") == '/usr/bin/plasmalogin ' ]]
  [[ $(awk -F: 'NR==1 {print $NF}' "/proc/$daemon_pid/cgroup") == /system.slice/plasmalogin.service ]]
  [[ $(readlink -f "/proc/$daemon_pid/exe") == /usr/bin/plasmalogin ]]
  [[ $(stat -Lc %i /proc/self/ns/mnt) == $(stat -Lc %i "/proc/$daemon_pid/ns/mnt") ]]
}

d290_prepare_overlay () {
  [[ ! -e $runtime ]]
  [[ -f $target && ! -L $target ]]
  if mountpoint -q "$target"; then
    return 1
  fi
  [[ $(d290_digest "$target") == "$expected_host" ]]
  [[ -f $candidate && ! -L $candidate && $(d290_digest "$candidate") == "$expected_candidate" ]]
  d290_validate_daemon_identity

  install -d -o root -g root -m 0700 "$runtime"
  install -o root -g root -m 0644 "$candidate" "$runtime/plasmalogin"
  chcon --reference="$target" "$runtime/plasmalogin"
  mount --bind "$runtime/plasmalogin" "$target"
  mounted=true
  mount -o remount,bind,ro "$target"
  mountpoint -q "$target"
  [[ $(d290_digest "$target") == "$expected_candidate" ]]
  findmnt -n -o OPTIONS --target "$target" | tr ',' '\n' | grep -Fx ro >/dev/null
  echo D290_ROOT_DAEMON_IDENTITY=true
  echo D290_ROOT_NAMESPACE_MATCH=true
  echo D290_ROOT_OVERLAY_READ_ONLY=true
  echo D290_ROOT_OVERLAY_READY=true
}

d290_recover_overlay () {
  if mountpoint -q "$target"; then
    [[ $(d290_digest "$target") == "$expected_candidate" ]]
    mounted=true
  fi
}

d290_hold_overlay () {
  local command control_read_fd
  d290_validate_control_fifo
  d290_owner_alive
  d290_control_watchdog &
  control_watchdog_pid=$!
  exec {control_read_fd}<"$control_fifo"
  d290_owner_alive || return 125
  d290_prepare_overlay
  if ! IFS= read -r command <&"$control_read_fd"; then
    exec {control_read_fd}<&-
    d290_stop_control_watchdog
    return 125
  fi
  exec {control_read_fd}<&-
  d290_stop_control_watchdog
  [[ $command == RELEASE ]]
}
