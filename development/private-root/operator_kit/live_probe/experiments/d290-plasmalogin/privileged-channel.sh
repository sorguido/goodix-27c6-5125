#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

d290_release_overlay () {
  local line rc=0 wait_rc read_rc poll pipe_eof=false root_output_count=0
  local cleanup_unmounted=false cleanup_host=false cleanup_runtime=false
  [[ $helper_started == true && $overlay_closed == false ]] || return 0
  overlay_closed=true
  if [[ $root_control_fd =~ ^[0-9]+$ ]]; then
    printf 'RELEASE\n' >&"$root_control_fd" || rc=1
    exec {root_control_fd}>&-
  else
    rc=1
  fi
  if [[ $overlay_ready == false && $root_pid =~ ^[1-9][0-9]*$ ]]; then
    kill -TERM "$root_pid" 2>/dev/null || true
  fi
  if [[ $root_out_fd =~ ^[0-9]+$ ]]; then
    for ((poll=0; poll<32; poll++)); do
      set +e
      IFS= read -r -t 10 line <&"$root_out_fd"
      read_rc=$?
      set -e
      if [[ $read_rc -eq 0 ]]; then
        root_output_count=$((root_output_count + 1))
        [[ $line == D290_ROOT_OVERLAY_UNMOUNTED=true ]] && cleanup_unmounted=true
        [[ $line == D290_ROOT_HOST_PAM_RESTORED=true ]] && cleanup_host=true
        [[ $line == D290_ROOT_RUNTIME_REMOVED=true ]] && cleanup_runtime=true
        printf '%s\n' "$line" | tee -a "$root_log"
      elif [[ $read_rc -eq 1 ]]; then
        pipe_eof=true
        break
      else
        rc=1
        break
      fi
    done
    [[ $pipe_eof == true ]] || rc=1
    exec {root_out_fd}<&-
  else
    rc=1
  fi
  if [[ $pipe_eof == true && $root_pid =~ ^[1-9][0-9]*$ ]]; then
    set +e
    wait "$root_pid"
    wait_rc=$?
    set -e
    if [[ $wait_rc -ne 0 ]]; then
      if [[ $overlay_ready == false && ( $root_output_count -eq 0 ||
            ( $cleanup_unmounted == true && $cleanup_host == true && $cleanup_runtime == true ) ) &&
            ( $wait_rc -eq 130 || $wait_rc -eq 143 ) ]]; then
        :
      else
        rc=1
      fi
    fi
  fi
  [[ -f $root_log ]] && cp "$root_log" "$capture/root-overlay.log"
  rm -f -- "$control_fifo"
  return "$rc"
}

d290_start_overlay () {
  local ready line expected pgid tpgid owner_start_time
  [[ -t 0 && -r /dev/tty && -w /dev/tty ]]
  read -r pgid tpgid < <(ps -o pgid=,tpgid= -p $$)
  [[ $pgid =~ ^[0-9]+$ && $pgid == "$tpgid" ]]
  mkfifo -- "$control_fifo"
  chmod 0600 "$control_fifo"
  exec {root_control_fd}<>"$control_fifo"
  : >"$root_log"
  owner_start_time=$(awk '{print $22}' /proc/$$/stat)
  [[ $owner_start_time =~ ^[1-9][0-9]*$ ]]
  coproc D290_ROOT_HELPER {
    exec {root_control_fd}>&-
    exec pkexec "$root_helper" --hold --control-fifo "$control_fifo" \
      --owner-pid $$ --owner-start-time "$owner_start_time" </dev/tty
  }
  root_pid=$D290_ROOT_HELPER_PID
  helper_started=true
  exec {root_out_fd}<&"${D290_ROOT_HELPER[0]}"
  root_unused_fd=${D290_ROOT_HELPER[1]}
  exec {root_unused_fd}>&-
  IFS= read -r -t 60 ready <&"$root_out_fd"
  [[ $ready == D290_ROOT_DAEMON_IDENTITY=true ]]
  printf '%s\n' "$ready" | tee -a "$root_log"
  for expected in D290_ROOT_NAMESPACE_MATCH=true D290_ROOT_OVERLAY_READ_ONLY=true D290_ROOT_OVERLAY_READY=true; do
    IFS= read -r -t 10 line <&"$root_out_fd"
    [[ $line == "$expected" ]]
    printf '%s\n' "$line" | tee -a "$root_log"
  done
  [[ $(sha256sum "$overlay_target" | awk '{print $1}') == "$overlay_expected_hash" ]]
  overlay_ready=true
  echo D290_USER_OVERLAY_VISIBLE=true | tee -a "$root_log"
}

d290_close_unstarted_channel () {
  if [[ $helper_started == false ]]; then
    [[ -z $root_control_fd ]] || exec {root_control_fd}>&-
    rm -f -- "$control_fifo"
  fi
}
