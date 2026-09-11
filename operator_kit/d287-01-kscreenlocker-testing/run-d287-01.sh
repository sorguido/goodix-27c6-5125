#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

d287_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
d287_root=$(CDPATH= cd -- "$d287_script_dir/../.." && pwd)
d287_d286_script="$d287_script_dir/../d286-01-reboot-survival/run-d286-01.sh"
d287_pam="$d287_script_dir/goodix-d287-01-kde-fingerprint.pam"
d287_capture_root="$d287_root/captures/D287_01"
d287_expected_pam_sha=73bed123e2b863a82ea3608b346ba84088428e805bfdf1af1c999720f9851472
d287_expected_greeter_sha=45d5a60737ff966b93f60639a662396956b28d50122741261f4351fef941be48
d287_expected_kde_pam_sha=7d91b3ad73a998e8b10f9edccd74ba04179a778c4a5e61d9176872f43c7bbac3
d287_expected_kde_fingerprint_sha=8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437
d287_expected_lock_qml_sha=328501780ab06cc0497a25ff48c6f027a1abed8506f0969f39a5f8bc6696181c
d287_max_attempts=3
d287_critical=(analysis/D285 analysis/D286 analysis/D287
  operator_kit/d285-01-persistent-sudo
  operator_kit/d286-01-reboot-survival
  operator_kit/d287-01-kscreenlocker-testing
  "Goodix 27c6 5125 manuale tecnico.md")

d287_tmp=
d287_greeter_log=
d287_journal_log=
d287_greeter_pgid=
d287_series_log=
d287_tmp_mount_active=false

d287_refuse () {
  echo D287_01_GATE_REFUSED=true >&2
  echo "D287_01_REFUSAL_REASON=$1" >&2
  echo AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false >&2
  exit 3
}

d287_is_sha256 () {
  [[ ${1:-} =~ ^[0-9a-f]{64}$ ]]
}

d287_safe_user () {
  [[ ${1:-} =~ ^[a-z_][a-z0-9_-]*$ ]]
}

d287_valid_cursor () {
  local pattern='^[A-Za-z0-9_=.;:-]{20,512}$'
  [[ ${1:-} =~ $pattern ]]
}

d287_verify_repo () {
  local baseline=$1
  [[ $baseline =~ ^[0-9a-f]{40}$ ]] || d287_refuse INVALID_BASELINE
  [[ $(git -C "$d287_root" branch --show-current) == development ]] ||
    d287_refuse WRONG_BRANCH
  [[ $(git -C "$d287_root" rev-parse HEAD) == "$baseline" ]] ||
    d287_refuse HEAD_MISMATCH
  [[ $(git -C "$d287_root" rev-parse origin/development) == "$baseline" ]] ||
    d287_refuse ORIGIN_DEVELOPMENT_MISMATCH
  [[ -z $(git -C "$d287_root" status --porcelain --untracked-files=all -- \
    "${d287_critical[@]}") ]] || d287_refuse LIVE_CRITICAL_DIRTY
}

d287_verify_hash () {
  local path=$1 expected=$2
  d287_is_sha256 "$expected" || return 1
  [[ -f $path && ! -L $path &&
     $(sha256sum "$path" | awk '{print $1}') == "$expected" ]]
}

d287_validate_host_contract () {
  [[ $(rpm -q kscreenlocker) == kscreenlocker-6.7.5-1.fc44.x86_64 ]] ||
    d287_refuse KSCREENLOCKER_NEVRA_DRIFT
  [[ $(rpm -q plasma-workspace) == plasma-workspace-6.7.5-1.fc44.x86_64 ]] ||
    d287_refuse PLASMA_WORKSPACE_NEVRA_DRIFT
  [[ $(rpm -q pam) == pam-1.7.2-2.fc44.x86_64 ]] || d287_refuse PAM_NEVRA_DRIFT
  [[ $(rpm -q fprintd-pam) == fprintd-pam-1.94.5-5.fc44.x86_64 ]] ||
    d287_refuse FPRINTD_PAM_NEVRA_DRIFT
  d287_verify_hash "$d287_pam" "$d287_expected_pam_sha" ||
    d287_refuse CANDIDATE_PAM_DRIFT
  d287_verify_hash /usr/libexec/kscreenlocker_greet "$d287_expected_greeter_sha" ||
    d287_refuse GREETER_BINARY_DRIFT
  d287_verify_hash /etc/pam.d/kde "$d287_expected_kde_pam_sha" ||
    d287_refuse KDE_PASSWORD_PAM_DRIFT
  d287_verify_hash /etc/pam.d/kde-fingerprint "$d287_expected_kde_fingerprint_sha" ||
    d287_refuse KDE_FINGERPRINT_PAM_DRIFT
  d287_verify_hash \
    /usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml \
    "$d287_expected_lock_qml_sha" || d287_refuse LOCKSCREEN_QML_DRIFT
  strings -el /usr/libexec/kscreenlocker_greet | grep -Fx kde-fingerprint >/dev/null ||
    d287_refuse GREETER_FINGERPRINT_SERVICE_NOT_PROVEN
  grep -Eq '^auth[[:space:]]+required[[:space:]]+pam_fprintd\.so max-tries=1 timeout=45[[:space:]]*$' \
    "$d287_pam" || d287_refuse CANDIDATE_PAM_CONTRACT_INVALID
  [[ $(grep -c pam_fprintd.so "$d287_pam") -eq 1 ]] ||
    d287_refuse CANDIDATE_PAM_MODULE_COUNT_INVALID
  for command in pkexec unshare mount umount mountpoint runuser setsid journalctl \
      chcon sha256sum findmnt getent pgrep strings; do
    command -v "$command" >/dev/null || d287_refuse "HOST_TOOL_MISSING_${command}"
  done
}

d287_require_polkit_password_path () {
  [[ -x /usr/bin/pkexec && -f /usr/lib/pam.d/polkit-1 ]] ||
    d287_refuse POLKIT_PATH_UNAVAILABLE
  grep -Eq '^auth[[:space:]]+include[[:space:]]+system-auth[[:space:]]*$' \
    /usr/lib/pam.d/polkit-1 || d287_refuse POLKIT_PAM_TOPOLOGY_DRIFT
  ! grep -F pam_fprintd.so /etc/authselect/system-auth >/dev/null ||
    d287_refuse POLKIT_SYSTEM_AUTH_FINGERPRINT_ENABLED
}

d287_count_goodix_targets () {
  local sysfs=${1:-/sys/bus/usb/devices} device count=0
  [[ -d $sysfs && ! -L $sysfs ]] || return 1
  for device in "$sysfs"/*; do
    [[ -d $device && -f $device/idVendor && -f $device/idProduct ]] || continue
    if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      count=$((count + 1))
    fi
  done
  printf '%s\n' "$count"
}

d287_current_cursor () {
  local output cursor
  output=$(LC_ALL=C journalctl -b -u fprintd.service -n 0 --show-cursor --no-pager) ||
    d287_refuse JOURNAL_CURSOR_READ_FAILED
  cursor=$(printf '%s\n' "$output" | sed -n 's/^-- cursor: //p')
  [[ $(printf '%s\n' "$cursor" | grep -c . || true) -eq 1 ]] ||
    d287_refuse JOURNAL_CURSOR_AMBIGUOUS
  d287_valid_cursor "$cursor" || d287_refuse JOURNAL_CURSOR_INVALID
  printf '%s\n' "$cursor"
}

d287_check_no_existing_greeter () {
  ! pgrep -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null ||
    d287_refuse EXISTING_KSCREENLOCKER_GREETER
}

d287_run_d285_audit () {
  local phase=$1 user=$2 output
  output=$("$d287_d286_script" --root-audit "$phase" --user "$user") ||
    d287_refuse "D285_STATE_AUDIT_${phase}_FAILED"
  printf '%s\n' "$output"
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES <<<"$output" >/dev/null ||
    d287_refuse "D285_STATE_AUDIT_${phase}_INCOMPLETE"
}

d287_kill_greeter_group () {
  local signal=${1:-TERM}
  [[ -n $d287_greeter_pgid && $d287_greeter_pgid =~ ^[0-9]+$ ]] || return 0
  kill -"$signal" -- "$d287_greeter_pgid" 2>/dev/null || true
  kill -"$signal" -- "-$d287_greeter_pgid" 2>/dev/null || true
}

d287_greeter_running () {
  local running
  [[ -n $d287_greeter_pgid && $d287_greeter_pgid =~ ^[0-9]+$ ]] || return 1
  running=$(jobs -pr)
  grep -Fx "$d287_greeter_pgid" <<<"$running" >/dev/null
}

d287_inner_cleanup () {
  local rc=0
  if [[ -n $d287_greeter_pgid ]]; then
    d287_kill_greeter_group TERM
    sleep 0.2
    d287_kill_greeter_group KILL
    wait "$d287_greeter_pgid" 2>/dev/null || true
  fi
  d287_greeter_pgid=
  if mountpoint -q /etc/pam.d/kde-fingerprint; then
    umount /etc/pam.d/kde-fingerprint || rc=1
  fi
  if [[ -n $d287_tmp ]]; then
    [[ $d287_tmp == /tmp/goodix-d287-01 && -d $d287_tmp && ! -L $d287_tmp ]] ||
      return 1
    find "$d287_tmp" -xdev -depth -delete || rc=1
    d287_tmp=
  fi
  if [[ $d287_tmp_mount_active == true ]]; then
    umount /tmp || rc=1
    d287_tmp_mount_active=false
  fi
  return "$rc"
}

d287_inner_abort () {
  trap - EXIT HUP INT TERM
  d287_inner_cleanup || true
  exit 130
}

d287_series_cleanup () {
  [[ -z $d287_series_log ]] && return 0
  [[ $d287_series_log == /tmp/goodix-d287-inner.* &&
     -f $d287_series_log && ! -L $d287_series_log ]] || return 1
  find "$d287_series_log" -xdev -delete
  d287_series_log=
}

d287_collect_journal () {
  local cursor=$1 output=$2
  d287_valid_cursor "$cursor" || return 1
  [[ $output == /tmp/goodix-d287-01/journal.log ]] || return 1
  LC_ALL=C journalctl -b -u fprintd.service --after-cursor "$cursor" --no-pager >"$output"
}

d287_classify_attempt () {
  local raw=$1 attempt=$2 greeter_rc=$3 supervisor_terminated=$4 greeter_unlocked=$5
  local audit matcher extract total_epoch_count epoch_count retry_count reopen_count
  local reset_count clear_halt_count persistent_count match_count no_match_count
  local comparison_count extract_count consumed_tls_count drained_count outcome=PAM_ERROR
  [[ -f $raw && ! -L $raw && $attempt =~ ^[123]$ && $greeter_rc =~ ^[0-9]{1,3}$ &&
     $supervisor_terminated =~ ^(true|false)$ &&
     $greeter_unlocked =~ ^(true|false)$ ]] || return 1
  audit=$(grep GOODIX_D282_EPOCH_AUDIT "$raw" || true)
  matcher=$(grep GOODIX_SIGFM_MATCH_AUDIT "$raw" || true)
  extract=$(grep GOODIX_SIGFM_EXTRACT_AUDIT "$raw" || true)
  total_epoch_count=$(grep -c GOODIX_D282_EPOCH_AUDIT "$raw" || true)
  epoch_count=$(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$raw" || true)
  retry_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^(secure_retry|post_retry)=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  reopen_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^reopen=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  reset_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^reset=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  clear_halt_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^clear_halt=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  persistent_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^persistent=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  match_count=$(printf '%s\n' "$matcher" | grep -c 'event=outcome result=match' || true)
  no_match_count=$(printf '%s\n' "$matcher" | grep -c 'event=outcome result=no_match' || true)
  comparison_count=$(printf '%s\n' "$matcher" | grep -c 'event=comparison' || true)
  extract_count=$(printf '%s\n' "$extract" | grep -c GOODIX_SIGFM_EXTRACT_AUDIT || true)
  consumed_tls_count=$(printf '%s\n' "$audit" | grep -c 'consumed=1.*tls=1' || true)
  drained_count=$(printf '%s\n' "$audit" | grep -c 'outstanding=0 drained=1 context_closed=1' || true)
  if [[ $total_epoch_count -gt 1 || $epoch_count -gt 1 || $retry_count -ne 0 ||
        $reopen_count -ne 0 || $reset_count -ne 0 || $clear_halt_count -ne 0 ||
        $persistent_count -ne 0 ]]; then
    outcome=SAFETY_VIOLATION
  elif [[ $total_epoch_count -eq 1 && $epoch_count -eq 1 && $extract_count -eq 1 &&
          $comparison_count -ge 1 && $consumed_tls_count -eq 1 && $drained_count -eq 1 &&
          $match_count -eq 1 && $no_match_count -eq 0 && $greeter_rc -eq 0 &&
          $supervisor_terminated == false && $greeter_unlocked == true ]]; then
    outcome=MATCH
  elif [[ $total_epoch_count -eq 1 && $epoch_count -eq 1 && $extract_count -eq 1 &&
          $comparison_count -ge 1 && $consumed_tls_count -eq 1 && $drained_count -eq 1 &&
          $match_count -eq 0 && $no_match_count -eq 1 &&
          $supervisor_terminated == true && $greeter_unlocked == false ]]; then
    outcome=NO_MATCH
  fi
  sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT .*$\)/\1/p; s/^.*\(GOODIX_SIGFM_.*$\)/\1/p' \
    "$raw" | sort -u
  echo "D287_01_ATTEMPT_INDEX=$attempt"
  echo "D287_01_ATTEMPT_OUTCOME=$outcome"
  echo "D287_01_ATTEMPT_GREETER_RETURN_CODE=$greeter_rc"
  echo "D287_01_ATTEMPT_GREETER_UNLOCKED_MARKER=$greeter_unlocked"
  echo "D287_01_ATTEMPT_SUPERVISOR_TERMINATED_GREETER=$supervisor_terminated"
  echo "D287_01_ATTEMPT_VERIFY_EPOCH_COUNT=$epoch_count"
  echo "D287_01_ATTEMPT_PROBE_EXTRACT_COUNT=$extract_count"
  echo "D287_01_ATTEMPT_COMPARISON_COUNT=$comparison_count"
  echo "D287_01_ATTEMPT_MATCH_COUNT=$match_count"
  echo "D287_01_ATTEMPT_NO_MATCH_COUNT=$no_match_count"
  echo "D287_01_ATTEMPT_RETRY_COUNT=$retry_count"
  echo "D287_01_ATTEMPT_REOPEN_COUNT=$reopen_count"
  echo "D287_01_ATTEMPT_RESET_COUNT=$reset_count"
  echo "D287_01_ATTEMPT_CLEAR_HALT_COUNT=$clear_halt_count"
  echo "D287_01_ATTEMPT_PERSISTENT_WRITE_FAMILY_COUNT=$persistent_count"
  [[ $outcome == MATCH || $outcome == NO_MATCH ]]
}

d287_root_namespace_attempt () {
  local user=$1 uid=$2 runtime=$3 wayland=$4 dbus=$5 cursor=$6 attempt=$7
  local staged_pam deadline outcome_seen=false supervisor_terminated=false
  local greeter_unlocked=false rc=255 poll classify_rc
  [[ $EUID -eq 0 ]] || d287_refuse ROOT_NAMESPACE_REQUIRES_ROOT
  d287_safe_user "$user" || d287_refuse OPERATOR_USER_INVALID
  [[ $uid =~ ^[0-9]+$ && $(id -u "$user") == "$uid" ]] || d287_refuse OPERATOR_UID_INVALID
  [[ $runtime == "/run/user/$uid" && -d $runtime && ! -L $runtime &&
     $(stat -c %u "$runtime") == "$uid" ]] || d287_refuse XDG_RUNTIME_DIR_INVALID
  [[ $wayland =~ ^wayland-[0-9]+$ && -S $runtime/$wayland ]] ||
    d287_refuse WAYLAND_SOCKET_INVALID
  [[ $dbus == "unix:path=$runtime/bus" && -S $runtime/bus ]] ||
    d287_refuse DBUS_SESSION_BUS_INVALID
  d287_valid_cursor "$cursor" || d287_refuse JOURNAL_CURSOR_INVALID
  [[ $attempt =~ ^[123]$ ]] || d287_refuse ATTEMPT_INDEX_INVALID
  [[ $(readlink /proc/self/ns/mnt) != $(readlink /proc/1/ns/mnt) ]] ||
    d287_refuse PRIVATE_MOUNT_NAMESPACE_REQUIRED
  [[ $(findmnt -n -o PROPAGATION /) == private ]] ||
    d287_refuse PRIVATE_MOUNT_PROPAGATION_REQUIRED
  ! mountpoint -q /etc/pam.d/kde-fingerprint ||
    d287_refuse PREEXISTING_PAM_MOUNTPOINT
  trap d287_inner_cleanup EXIT
  trap d287_inner_abort HUP INT TERM
  mount -t tmpfs -o nodev,nosuid,noexec,size=4m,mode=1777 tmpfs /tmp
  d287_tmp_mount_active=true
  d287_tmp=/tmp/goodix-d287-01
  mkdir "$d287_tmp"
  [[ -d $d287_tmp && ! -L $d287_tmp ]] || d287_refuse TEMP_DIRECTORY_INVALID
  chmod 0700 "$d287_tmp"
  d287_greeter_log="$d287_tmp/greeter.log"
  d287_journal_log="$d287_tmp/journal.log"
  staged_pam="$d287_tmp/kde-fingerprint"
  install -o root -g root -m 0644 "$d287_pam" "$staged_pam"
  chcon --reference=/etc/pam.d/kde-fingerprint "$staged_pam"
  mount --bind "$staged_pam" /etc/pam.d/kde-fingerprint
  mount -o remount,bind,ro /etc/pam.d/kde-fingerprint
  d287_verify_hash /etc/pam.d/kde-fingerprint "$d287_expected_pam_sha" ||
    d287_refuse NAMESPACE_PAM_OVERLAY_FAILED
  setsid --wait runuser -u "$user" -- env -i \
    HOME="$(getent passwd "$user" | cut -d: -f6)" USER="$user" LOGNAME="$user" \
    PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 XDG_SESSION_TYPE=wayland \
    XDG_RUNTIME_DIR="$runtime" WAYLAND_DISPLAY="$wayland" \
    DBUS_SESSION_BUS_ADDRESS="$dbus" QT_QPA_PLATFORM=wayland \
    /usr/libexec/kscreenlocker_greet --testing >"$d287_greeter_log" 2>&1 &
  d287_greeter_pgid=$!
  deadline=$((SECONDS + 20))
  while d287_greeter_running; do
    grep -F 'Locked at ' "$d287_greeter_log" >/dev/null && break
    (( SECONDS < deadline )) || break
    sleep 0.1
  done
  grep -F 'Locked at ' "$d287_greeter_log" >/dev/null || {
    d287_kill_greeter_group TERM
    sleep 0.2
    d287_kill_greeter_group KILL
    wait "$d287_greeter_pgid" 2>/dev/null || true
    d287_greeter_pgid=
    echo D287_01_ATTEMPT_OUTCOME=PAM_ERROR
    echo D287_01_ATTEMPT_FAILURE=GREETER_NOT_READY
    return 4
  }
  echo D287_01_GREETER_TESTING_MODE_READY=true
  echo 'Muovere il puntatore per mostrare il form, quindi appoggiare una sola volta l’indice destro.'
  deadline=$((SECONDS + 90))
  while (( SECONDS < deadline )); do
    d287_collect_journal "$cursor" "$d287_journal_log" ||
      d287_refuse JOURNAL_READ_FAILED
    if grep -Eq 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=(match|no_match)' \
        "$d287_journal_log"; then
      outcome_seen=true
      break
    fi
    d287_greeter_running || break
    sleep 0.2
  done
  if [[ $outcome_seen == true ]] &&
      grep -F 'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=no_match' \
        "$d287_journal_log" >/dev/null; then
    supervisor_terminated=true
    d287_kill_greeter_group TERM
  fi
  if [[ $outcome_seen != true ]]; then
    supervisor_terminated=true
    d287_kill_greeter_group TERM
  fi
  if [[ $outcome_seen == true && $supervisor_terminated == false ]]; then
    deadline=$((SECONDS + 10))
    while d287_greeter_running && (( SECONDS < deadline )); do
      sleep 0.1
    done
    if d287_greeter_running; then
      supervisor_terminated=true
      d287_kill_greeter_group TERM
    fi
  fi
  deadline=$((SECONDS + 5))
  while d287_greeter_running && (( SECONDS < deadline )); do
    sleep 0.1
  done
  if d287_greeter_running; then
    d287_kill_greeter_group KILL
  fi
  if [[ $supervisor_terminated == true ]]; then
    d287_kill_greeter_group KILL
  fi
  set +e
  wait "$d287_greeter_pgid"
  rc=$?
  set -e
  d287_greeter_pgid=
  if grep -Fx Unlocked "$d287_greeter_log" >/dev/null; then
    greeter_unlocked=true
  fi
  for poll in {1..50}; do
    d287_collect_journal "$cursor" "$d287_journal_log" ||
      d287_refuse JOURNAL_READ_FAILED
    grep -F GOODIX_D282_EPOCH_AUDIT "$d287_journal_log" >/dev/null && break
    sleep 0.1
  done
  set +e
  d287_classify_attempt "$d287_journal_log" "$attempt" "$rc" \
    "$supervisor_terminated" "$greeter_unlocked"
  classify_rc=$?
  set -e
  d287_inner_cleanup || return 4
  trap - EXIT HUP INT TERM
  [[ $classify_rc -eq 0 ]] || return 4
}

d287_root_series () {
  local baseline=$1 user=$2 uid=$3 runtime=$4 wayland=$5 dbus=$6
  local attempt cursor confirmation inner_log inner_rc outcome matched_attempt=0
  local final=FAIL_LIVE_PENDING_INDEPENDENT_REVIEW
  local -a outcomes=()
  [[ $EUID -eq 0 ]] || d287_refuse ROOT_SERIES_REQUIRES_ROOT
  d287_verify_repo "$baseline"
  d287_validate_host_contract
  d287_require_polkit_password_path
  d287_check_no_existing_greeter
  [[ $(d287_count_goodix_targets /sys/bus/usb/devices) -eq 1 ]] ||
    d287_refuse REAL_TARGET_CARDINALITY_NOT_ONE
  d287_run_d285_audit D287_SERIES_PRE "$user"
  trap d287_series_cleanup EXIT
  echo 'Pilot del solo greeter KDE in modalità --testing: la sessione non viene bloccata.'
  echo 'Non digitare la password nel form. Ogni finestra ammette una sola VERIFY.'
  printf 'Per il tentativo 1/3 digitare INDICE DESTRO: '
  read -r confirmation
  [[ $confirmation == 'INDICE DESTRO' ]] || d287_refuse PHYSICAL_FINGER_NOT_CONFIRMED
  for attempt in 1 2 3; do
    d287_check_no_existing_greeter
    cursor=$(d287_current_cursor)
    inner_log=$(mktemp /tmp/goodix-d287-inner.XXXXXX)
    d287_series_log=$inner_log
    set +e
    unshare --mount --propagation private --fork --kill-child=KILL \
      "$d287_script_dir/run-d287-01.sh" --root-namespace-attempt \
      "$user" "$uid" "$runtime" "$wayland" "$dbus" "$cursor" "$attempt" \
      >"$inner_log" 2>&1
    inner_rc=$?
    set -e
    cat "$inner_log"
    outcome=$(sed -n 's/^D287_01_ATTEMPT_OUTCOME=//p' "$inner_log" | tail -n 1)
    d287_series_cleanup
    d287_validate_host_contract
    d287_run_d285_audit "D287_ATTEMPT_${attempt}_POST" "$user"
    [[ $inner_rc -eq 0 && $outcome =~ ^(MATCH|NO_MATCH)$ ]] ||
      d287_refuse ATTEMPT_FAILED_OR_AMBIGUOUS
    outcomes+=("$outcome")
    if [[ $outcome == MATCH ]]; then
      final=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
      matched_attempt=$attempt
      break
    fi
    if [[ $attempt -lt $d287_max_attempts ]]; then
      echo "NO_MATCH osservato al tentativo $attempt/$d287_max_attempts."
      printf 'Per autorizzare il tentativo %d/3 digitare TENTATIVO %d: ' \
        "$((attempt + 1))" "$((attempt + 1))"
      read -r confirmation
      [[ $confirmation == "TENTATIVO $((attempt + 1))" ]] ||
        d287_refuse NEXT_ATTEMPT_NOT_CONFIRMED
    fi
  done
  if [[ $matched_attempt -eq 0 && ${#outcomes[@]} -eq 3 ]]; then
    final=NO_MATCH_SERIES_PENDING_INDEPENDENT_REVIEW
  fi
  echo "D287_01_SERIES_RESULT=$final"
  echo "D287_01_REPO_BASELINE=$baseline"
  echo "D287_01_ATTEMPTS_PERFORMED=${#outcomes[@]}"
  echo "D287_01_MATCHED_ATTEMPT=$matched_attempt"
  printf 'D287_01_ATTEMPT_OUTCOMES='
  (IFS=,; echo "${outcomes[*]}")
  echo D287_01_CONSUMER=KSCREENLOCKER_GREETER_TESTING_MODE
  echo D287_01_REAL_SESSION_LOCKED=false
  echo D287_01_HOST_PAM_FILE_WRITE_COUNT=0
  echo D287_01_PAM_OVERLAY_SCOPE=PRIVATE_MOUNT_NAMESPACE_READ_ONLY
  echo D287_01_PAM_MAX_TRIES_PER_ATTEMPT=1
  echo D287_01_MAX_PHYSICAL_CONTACTS=3
  echo D287_01_STOP_ON_FIRST_MATCH=true
  echo D287_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=true
  echo REAL_SENSOR_ACCESSED=true
  echo LIVE_EXECUTION_PERFORMED=true
  trap - EXIT
  [[ $final == PASS_LIVE_PENDING_INDEPENDENT_REVIEW ]]
}

d287_operator_run () {
  local baseline user uid runtime wayland dbus stamp capture rc result
  [[ $EUID -ne 0 ]] || d287_refuse OPERATOR_MUST_BE_UNPRIVILEGED
  baseline=$(git -C "$d287_root" rev-parse HEAD)
  d287_verify_repo "$baseline"
  d287_validate_host_contract
  d287_require_polkit_password_path
  user=$(id -un); uid=$(id -u)
  d287_safe_user "$user" || d287_refuse OPERATOR_USER_INVALID
  runtime=${XDG_RUNTIME_DIR:-}; wayland=${WAYLAND_DISPLAY:-}; dbus=${DBUS_SESSION_BUS_ADDRESS:-}
  [[ ${XDG_SESSION_TYPE:-} == wayland ]] || d287_refuse WAYLAND_SESSION_REQUIRED
  [[ $runtime == "/run/user/$uid" && $wayland =~ ^wayland-[0-9]+$ &&
     $dbus == "unix:path=$runtime/bus" ]] || d287_refuse SESSION_ENVIRONMENT_INVALID
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  capture="$d287_capture_root/D28701_ATTEMPT_${stamp}_${baseline:0:12}/sanitized"
  [[ ! -e $capture && ! -L $capture ]] || d287_refuse CAPTURE_COLLISION
  install -d -m 0700 "$capture"
  set +e
  pkexec "$d287_script_dir/run-d287-01.sh" --root-series "$baseline" "$user" "$uid" \
    "$runtime" "$wayland" "$dbus" 2>&1 | tee "$capture/root-series.log"
  rc=${PIPESTATUS[0]}
  set -e
  result=$(sed -n 's/^D287_01_SERIES_RESULT=//p' "$capture/root-series.log" | tail -n 1)
  [[ -n $result ]] || result=ROOT_SERIES_NOT_COMPLETED
  {
    echo "D287_01_RESULT=$result"
    echo "D287_01_ROOT_SERIES_RETURN_CODE=$rc"
    echo "D287_01_REPO_BASELINE=$baseline"
    echo D287_01_CONSUMER=KSCREENLOCKER_GREETER_TESTING_MODE
    echo D287_01_REAL_SESSION_LOCKED=false
    echo D287_01_HOST_PAM_FILE_WRITE_COUNT=0
    echo D287_01_PAM_OVERLAY_SCOPE=PRIVATE_MOUNT_NAMESPACE_READ_ONLY
    echo D287_01_PAM_MAX_TRIES_PER_ATTEMPT=1
    echo D287_01_MAX_PHYSICAL_CONTACTS=3
    echo D287_01_STOP_ON_FIRST_MATCH=true
    echo D287_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
  } >"$capture/summary.env"
  chmod 0600 "$capture"/*
  sha256sum "$capture"/*
  echo "D287_01_CAPTURE_DIRECTORY=$capture"
  [[ $rc -eq 0 && $result == PASS_LIVE_PENDING_INDEPENDENT_REVIEW ]] || exit 4
}

d287_offline_preflight () {
  [[ $EUID -ne 0 ]] || d287_refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  bash -n "$d287_script_dir/run-d287-01.sh"
  d287_validate_host_contract
  d287_require_polkit_password_path
  d287_verify_hash /etc/pam.d/kde-fingerprint "$d287_expected_kde_fingerprint_sha" ||
    d287_refuse KDE_FINGERPRINT_PAM_DRIFT
  echo D287_01_OFFLINE_PREFLIGHT=PASS
  echo D287_01_CONSUMER=KSCREENLOCKER_GREETER_TESTING_MODE
  echo D287_01_REAL_SESSION_LOCKED=false
  echo D287_01_HOST_PAM_FILE_WRITE_COUNT=0
  echo D287_01_PAM_OVERLAY_SCOPE=PRIVATE_MOUNT_NAMESPACE_READ_ONLY
  echo D287_01_PAM_MAX_TRIES_PER_ATTEMPT=1
  echo D287_01_MAX_PHYSICAL_CONTACTS=3
  echo D287_01_STOP_ON_FIRST_MATCH=true
  echo D287_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
  echo D287_01_LIVE_EXECUTION=HUMAN_REQUIRED
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo LIVE_EXECUTION_PERFORMED=false
}

if [[ ${D287_LIBRARY_ONLY:-false} == true ]]; then
  return 0 2>/dev/null || exit 0
fi

case ${1:-} in
  --offline-preflight)
    [[ $# -eq 1 ]] || d287_refuse USAGE
    d287_offline_preflight
    ;;
  --operator-run)
    [[ $# -eq 1 ]] || d287_refuse USAGE
    d287_operator_run
    ;;
  --root-series)
    [[ $# -eq 7 ]] || d287_refuse USAGE
    d287_root_series "$2" "$3" "$4" "$5" "$6" "$7"
    ;;
  --root-namespace-attempt)
    [[ $# -eq 8 ]] || d287_refuse USAGE
    d287_root_namespace_attempt "$2" "$3" "$4" "$5" "$6" "$7" "$8"
    ;;
  *)
    echo "Uso: $0 --offline-preflight | --operator-run" >&2
    exit 2
    ;;
esac
