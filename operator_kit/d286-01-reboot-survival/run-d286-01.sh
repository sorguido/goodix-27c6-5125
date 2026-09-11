#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

d286_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
d286_root=$(CDPATH= cd -- "$d286_script_dir/../.." && pwd)
d285_script="$d286_script_dir/../d285-01-persistent-sudo/run-d285-01.sh"
D285_LIBRARY_ONLY=true
# shellcheck source=../d285-01-persistent-sudo/run-d285-01.sh
source "$d285_script"
unset D285_LIBRARY_ONLY

d286_installed_baseline=a9e234e43d2bdf3e81630df143eb7a809a19bff5
d286_capture_root="$d286_root/captures/D286_01"
d286_journal_tmp=
d286_attempt_input_dir=
d286_attempt_fifo=
d286_attempt_fd=
d286_attempt_pid=
d286_attempt_rc=
d286_attempt_fallback_blocked=false
d286_attempt_watchdog_timeout=false
d286_max_verify_attempts=3
d286_critical=(analysis/D284 analysis/D285 analysis/D286
  operator_kit/d284-01-transient-sudo-pilot
  operator_kit/d285-01-persistent-sudo
  operator_kit/d286-01-reboot-survival
  GoodixArtifacts .gitignore
  "Goodix 27c6 5125 manuale tecnico.md")

d286_refuse () {
  echo D286_01_GATE_REFUSED=true >&2
  echo "D286_01_REFUSAL_REASON=$1" >&2
  echo AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false >&2
  exit 3
}

d286_safe_user () {
  [[ $1 =~ ^[a-z_][a-z0-9_-]*$ ]]
}

d286_verify_repo () {
  local baseline=$1
  [[ $baseline =~ ^[0-9a-f]{40}$ ]] || d286_refuse INVALID_BASELINE
  [[ $(git -C "$d286_root" branch --show-current) == development ]] ||
    d286_refuse WRONG_BRANCH
  [[ $(git -C "$d286_root" rev-parse HEAD) == "$baseline" ]] ||
    d286_refuse HEAD_MISMATCH
  [[ $(git -C "$d286_root" rev-parse origin/development) == "$baseline" ]] ||
    d286_refuse ORIGIN_DEVELOPMENT_MISMATCH
  [[ -z $(git -C "$d286_root" status --porcelain --untracked-files=all -- \
    "${d286_critical[@]}") ]] || d286_refuse LIVE_CRITICAL_DIRTY
}

d286_cleanup_journal_tmp () {
  [[ -z $d286_journal_tmp ]] && return 0
  [[ $d286_journal_tmp == /tmp/goodix-d286-journal.* &&
     -f $d286_journal_tmp && ! -L $d286_journal_tmp ]] || return 1
  rm -f -- "$d286_journal_tmp"
  d286_journal_tmp=
}

d286_cleanup_attempt () {
  local rc=0
  if [[ -n $d286_attempt_pid ]]; then
    if kill -0 "$d286_attempt_pid" 2>/dev/null; then
      kill -KILL "$d286_attempt_pid" 2>/dev/null || rc=1
    fi
    wait "$d286_attempt_pid" 2>/dev/null || true
    d286_attempt_pid=
  fi
  if [[ -n $d286_attempt_fd ]]; then
    exec {d286_attempt_fd}>&- || rc=1
    d286_attempt_fd=
  fi
  if [[ -n $d286_attempt_fifo ]]; then
    [[ $d286_attempt_fifo == /tmp/goodix-d286-input.*/password-input &&
       -p $d286_attempt_fifo && ! -L $d286_attempt_fifo ]] || return 1
    rm -f -- "$d286_attempt_fifo" || rc=1
    d286_attempt_fifo=
  fi
  if [[ -n $d286_attempt_input_dir ]]; then
    [[ $d286_attempt_input_dir == /tmp/goodix-d286-input.* &&
       -d $d286_attempt_input_dir && ! -L $d286_attempt_input_dir ]] || return 1
    rmdir -- "$d286_attempt_input_dir" || rc=1
    d286_attempt_input_dir=
  fi
  return "$rc"
}

d286_abort_attempt () {
  d286_cleanup_attempt || true
  d286_refuse OPERATOR_INTERRUPTED_NO_RETRY
}

d286_require_polkit_password_path () {
  [[ -x /usr/bin/pkexec && -f /usr/lib/pam.d/polkit-1 ]] ||
    d286_refuse POLKIT_PATH_UNAVAILABLE
  grep -Eq '^auth[[:space:]]+include[[:space:]]+system-auth[[:space:]]*$' \
    /usr/lib/pam.d/polkit-1 || d286_refuse POLKIT_PAM_TOPOLOGY_DRIFT
  ! grep -F pam_fprintd.so /etc/authselect/system-auth >/dev/null ||
    d286_refuse POLKIT_SYSTEM_AUTH_FINGERPRINT_ENABLED
}

d286_verify_installed_file () {
  local path=$1 expected=$2
  [[ -f $path && ! -L $path &&
     $(sha256sum "$path" | awk '{print $1}') == "$expected" ]]
}

d286_root_audit_installed () {
  local phase=$1 user=$2 state=$d285_state baseline runtime auth_active backup
  local daemon_sha pam_sha sudoers_sha wrapper_sha dropin_sha manifest_sha
  local pam_sudo_before system_lib_before template_relative template_sha storage value
  [[ $EUID -eq 0 ]] || d286_refuse ROOT_AUDIT_REQUIRES_ROOT
  d286_safe_user "$user" || d286_refuse OPERATOR_USER_INVALID
  [[ -f $state && ! -L $state && $(stat -c %a "$state") == 600 &&
     $(stat -c %U:%G "$state") == root:root ]] || d286_refuse STATE_MODE_OR_OWNER_DRIFT
  [[ $(state_value "$state" D285_01_INSTALL_STATUS) == ACTIVE ]] ||
    d286_refuse STATE_INACTIVE
  baseline=$(state_value "$state" D285_01_BASELINE_SHA) || d286_refuse STATE_INVALID
  [[ $baseline == "$d286_installed_baseline" ]] || d286_refuse INSTALLED_BASELINE_DRIFT
  [[ $(state_value "$state" D285_01_USER) == "$user" ]] || d286_refuse STATE_USER_DRIFT
  runtime=$(state_value "$state" D285_01_RUNTIME) || d286_refuse STATE_INVALID
  auth_active=$(state_value "$state" D285_01_AUTHSELECT_ACTIVE) || d286_refuse STATE_INVALID
  backup=$(state_value "$state" D285_01_AUTHSELECT_BACKUP) || d286_refuse STATE_INVALID
  daemon_sha=$(state_value "$state" D285_01_DAEMON_SHA256) || d286_refuse STATE_INVALID
  pam_sha=$(state_value "$state" D285_01_PAM_SHA256) || d286_refuse STATE_INVALID
  sudoers_sha=$(state_value "$state" D285_01_SUDOERS_SHA256) || d286_refuse STATE_INVALID
  wrapper_sha=$(state_value "$state" D285_01_WRAPPER_SHA256) || d286_refuse STATE_INVALID
  dropin_sha=$(state_value "$state" D285_01_DROPIN_SHA256) || d286_refuse STATE_INVALID
  manifest_sha=$(state_value "$state" D285_01_MANIFEST_SHA256) || d286_refuse STATE_INVALID
  pam_sudo_before=$(state_value "$state" D285_01_PAM_SUDO_BEFORE_SHA256) ||
    d286_refuse STATE_INVALID
  system_lib_before=$(state_value "$state" D285_01_SYSTEM_LIBFPRINT_BEFORE_SHA256) ||
    d286_refuse STATE_INVALID
  template_relative=$(state_value "$state" D285_01_TEMPLATE_RELATIVE_PATH) ||
    d286_refuse STATE_INVALID
  template_sha=$(state_value "$state" D285_01_TEMPLATE_SHA256) || d286_refuse STATE_INVALID
  for value in "$daemon_sha" "$pam_sha" "$sudoers_sha" "$wrapper_sha" \
      "$dropin_sha" "$manifest_sha" "$pam_sudo_before" "$system_lib_before" \
      "$template_sha"; do
    d285_is_sha256 "$value" || d286_refuse STATE_HASH_INVALID
  done
  [[ $runtime == /usr/local/lib64/goodix-27c6-5125/d285-01-$baseline &&
     $auth_active == "$d285_expected_authselect_active" &&
     $backup == d285-01-[0-9T]*-[0-9a-f]* &&
     $template_relative =~ ^[A-Za-z0-9_.:+-]+/[A-Za-z0-9_.:+-]+/[0-9a-f]$ ]] ||
    d286_refuse STATE_SEMANTIC_DRIFT
  [[ -d /var/lib/authselect/backups/$backup &&
     ! -L /var/lib/authselect/backups/$backup ]] || d286_refuse AUTHSELECT_BACKUP_DRIFT
  [[ $(authselect current --raw) == "$auth_active" ]] || d286_refuse AUTHSELECT_ACTIVE_DRIFT
  authselect check >/dev/null || d286_refuse AUTHSELECT_INVALID
  ! grep -F pam_fprintd.so /etc/authselect/system-auth >/dev/null ||
    d286_refuse SYSTEM_AUTH_FINGERPRINT_ENABLED
  grep -Fx 'auth required pam_debug.so auth=authinfo_unavail' \
    /etc/authselect/fingerprint-auth >/dev/null || d286_refuse FINGERPRINT_AUTH_NOT_CLOSED
  [[ $(sha256sum /usr/libexec/fprintd | awk '{print $1}') == "$daemon_sha" ]] ||
    d286_refuse DAEMON_PROVENANCE_DRIFT
  d286_verify_installed_file "$d285_pam" "$pam_sha" || d286_refuse PAM_FILE_DRIFT
  d286_verify_installed_file "$d285_sudoers" "$sudoers_sha" || d286_refuse SUDOERS_FILE_DRIFT
  d286_verify_installed_file "$d285_wrapper" "$wrapper_sha" || d286_refuse WRAPPER_FILE_DRIFT
  d286_verify_installed_file "$d285_dropin" "$dropin_sha" || d286_refuse DROPIN_FILE_DRIFT
  grep -Eq '^auth[[:space:]]+sufficient[[:space:]]+pam_fprintd\.so max-tries=1 timeout=45[[:space:]]*$' \
    "$d285_pam" || d286_refuse PAM_FINGERPRINT_DRIFT
  grep -Eq '^auth[[:space:]]+sufficient[[:space:]]+pam_unix\.so nullok[[:space:]]*$' \
    "$d285_pam" || d286_refuse PASSWORD_FALLBACK_MISSING
  grep -Fx "Defaults:$user pam_service=goodix-d285-01-sudo" "$d285_sudoers" >/dev/null ||
    d286_refuse SUDOERS_SCOPE_DRIFT
  [[ -d $runtime && ! -L $runtime &&
     $(sha256sum "$runtime/artifacts.sha256" | awk '{print $1}') == "$manifest_sha" ]] ||
    d286_refuse RUNTIME_MANIFEST_DRIFT
  (cd "$runtime" && sha256sum -c artifacts.sha256 >/dev/null) ||
    d286_refuse RUNTIME_ARTIFACT_DRIFT
  [[ $(sha256sum /etc/pam.d/sudo | awk '{print $1}') == "$pam_sudo_before" ]] ||
    d286_refuse SYSTEM_SUDO_PAM_DRIFT
  [[ $(sha256sum /usr/lib64/libfprint-2.so.2.0.0 | awk '{print $1}') == "$system_lib_before" ]] ||
    d286_refuse SYSTEM_LIBFPRINT_DRIFT
  storage=/var/lib/fprint/$user
  [[ -d $storage && ! -L $storage &&
     $(find "$storage" -type l | wc -l) -eq 0 &&
     $(find "$storage" -type f | wc -l) -eq 1 &&
     -f $storage/$template_relative &&
     $(sha256sum "$storage/$template_relative" | awk '{print $1}') == "$template_sha" ]] ||
    d286_refuse TEMPLATE_OWNERSHIP_DRIFT
  systemctl show fprintd.service -p DropInPaths --value | grep -F "$d285_dropin" >/dev/null ||
    d286_refuse SYSTEMD_DROPIN_NOT_LOADED
  echo "D286_01_ROOT_AUDIT_PHASE=$phase"
  echo D286_01_STATE_COHERENCE=PASS_ROOT_ONLY
  echo D286_01_RUNTIME_INTEGRITY=PASS
  echo D286_01_WRAPPER_PROVENANCE=PASS
  echo D286_01_AUTHSELECT_SCOPE=PASS_REDUCED
  echo D286_01_PASSWORD_FALLBACK=PASS
  echo D286_01_TEMPLATE_OWNERSHIP=PASS_PINNED_EXACTLY_ONE
  echo D286_01_SYSTEM_LIBFPRINT_UNCHANGED=true
  echo D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES
  echo "D286_01_BOOT_ID=$(cat /proc/sys/kernel/random/boot_id)"
  echo "D286_01_${phase}_ROOT_AUDIT_SENSOR_ACTION_COUNT=0"
}

d286_valid_cursor () {
  local pattern='^[A-Za-z0-9_=.;:-]{20,512}$'
  [[ $1 =~ $pattern ]]
}

d286_current_cursor () {
  local output cursor
  output=$(LC_ALL=C journalctl -b -u fprintd.service -n 0 --show-cursor --no-pager) ||
    d286_refuse JOURNAL_CURSOR_READ_FAILED
  cursor=$(printf '%s\n' "$output" | sed -n 's/^-- cursor: //p')
  [[ $(printf '%s\n' "$cursor" | grep -c . || true) -eq 1 ]] ||
    d286_refuse JOURNAL_CURSOR_AMBIGUOUS
  d286_valid_cursor "$cursor" || d286_refuse JOURNAL_CURSOR_INVALID
  printf '%s\n' "$cursor"
}

d286_root_attempt_audit () {
  local user=$1 cursor=$2 attempt=$3 sudo_rc=$4 fallback_blocked=$5 watchdog_timeout=$6
  local raw audit matcher extract total_epoch_count epoch_count retry_count reopen_count
  local reset_count clear_halt_count persistent_count match_count no_match_count
  local comparison_count extract_count consumed_tls_count drained_count outcome poll
  [[ $EUID -eq 0 ]] || d286_refuse ROOT_AUDIT_REQUIRES_ROOT
  d286_safe_user "$user" || d286_refuse OPERATOR_USER_INVALID
  d286_valid_cursor "$cursor" || d286_refuse JOURNAL_CURSOR_INVALID
  [[ $attempt =~ ^[123]$ && $sudo_rc =~ ^[0-9]{1,3}$ &&
     $fallback_blocked =~ ^(true|false)$ && $watchdog_timeout =~ ^(true|false)$ ]] ||
    d286_refuse ATTEMPT_AUDIT_ARGUMENT_INVALID
  d286_root_audit_installed "ATTEMPT_${attempt}_POST" "$user"
  raw=$(mktemp /tmp/goodix-d286-journal.XXXXXX)
  d286_journal_tmp=$raw
  trap d286_cleanup_journal_tmp EXIT
  for poll in {1..50}; do
    LC_ALL=C journalctl -b -u fprintd.service --after-cursor "$cursor" --no-pager >"$raw" ||
      d286_refuse JOURNAL_READ_FAILED
    grep -F GOODIX_D282_EPOCH_AUDIT "$raw" >/dev/null && break
    sleep 0.1
  done
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
  outcome=PAM_ERROR
  if [[ $total_epoch_count -gt 1 || $epoch_count -gt 1 || $retry_count -ne 0 ||
        $reopen_count -ne 0 || $reset_count -ne 0 || $clear_halt_count -ne 0 ||
        $persistent_count -ne 0 ]]; then
    outcome=SAFETY_VIOLATION
  elif [[ $total_epoch_count -eq 1 && $epoch_count -eq 1 && $extract_count -eq 1 &&
          $comparison_count -ge 1 && $consumed_tls_count -eq 1 && $drained_count -eq 1 &&
          $match_count -eq 1 && $no_match_count -eq 0 && $sudo_rc -eq 0 &&
          $fallback_blocked == false && $watchdog_timeout == false ]]; then
    outcome=MATCH
  elif [[ $total_epoch_count -eq 1 && $epoch_count -eq 1 && $extract_count -eq 1 &&
          $comparison_count -ge 1 && $consumed_tls_count -eq 1 && $drained_count -eq 1 &&
          $match_count -eq 0 && $no_match_count -eq 1 && $sudo_rc -ne 0 &&
          $fallback_blocked == true && $watchdog_timeout == false ]]; then
    outcome=NO_MATCH
  fi
  sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT .*$\)/\1/p; s/^.*\(GOODIX_SIGFM_.*$\)/\1/p' \
    "$raw" | sort -u
  echo "D286_01_ATTEMPT_INDEX=$attempt"
  echo "D286_01_ATTEMPT_OUTCOME=$outcome"
  echo "D286_01_ATTEMPT_SUDO_RETURN_CODE=$sudo_rc"
  echo "D286_01_ATTEMPT_PASSWORD_FALLBACK_BLOCKED=$fallback_blocked"
  echo "D286_01_ATTEMPT_WATCHDOG_TIMEOUT=$watchdog_timeout"
  echo "D286_01_ATTEMPT_VERIFY_EPOCH_COUNT=$epoch_count"
  echo "D286_01_ATTEMPT_PROBE_EXTRACT_COUNT=$extract_count"
  echo "D286_01_ATTEMPT_COMPARISON_COUNT=$comparison_count"
  echo "D286_01_ATTEMPT_MATCH_COUNT=$match_count"
  echo "D286_01_ATTEMPT_NO_MATCH_COUNT=$no_match_count"
  echo "D286_01_ATTEMPT_RETRY_COUNT=$retry_count"
  echo "D286_01_ATTEMPT_REOPEN_COUNT=$reopen_count"
  echo "D286_01_ATTEMPT_RESET_COUNT=$reset_count"
  echo "D286_01_ATTEMPT_CLEAR_HALT_COUNT=$clear_halt_count"
  echo "D286_01_ATTEMPT_PERSISTENT_WRITE_FAMILY_COUNT=$persistent_count"
  d286_cleanup_journal_tmp || d286_refuse JOURNAL_CLEANUP_FAILED
  trap - EXIT
}

d286_run_sudo_attempt () {
  local attempt=$1 log=$2 marker=D286_PASSWORD_FALLBACK_BLOCKED deadline rc
  [[ $attempt =~ ^[123]$ && $log == "$d286_capture_root"/D28601_RETRY_*/sanitized/attempt-*.sudo.log ]] ||
    d286_refuse ATTEMPT_PATH_INVALID
  d286_attempt_input_dir=$(mktemp -d /tmp/goodix-d286-input.XXXXXX)
  [[ -d $d286_attempt_input_dir && ! -L $d286_attempt_input_dir ]] ||
    d286_refuse ATTEMPT_INPUT_DIR_INVALID
  chmod 0700 "$d286_attempt_input_dir"
  d286_attempt_fifo="$d286_attempt_input_dir/password-input"
  mkfifo -m 0600 "$d286_attempt_fifo"
  exec {d286_attempt_fd}<>"$d286_attempt_fifo"
  : >"$log"
  chmod 0600 "$log"
  trap d286_cleanup_attempt EXIT
  trap d286_abort_attempt HUP INT TERM
  LC_ALL=C /usr/bin/sudo -S -p "$marker" -v \
    <"$d286_attempt_fifo" >"$log" 2>&1 &
  d286_attempt_pid=$!
  deadline=$((SECONDS + 70))
  while kill -0 "$d286_attempt_pid" 2>/dev/null; do
    if grep -Fq "$marker" "$log"; then
      d286_attempt_fallback_blocked=true
      kill -KILL "$d286_attempt_pid" 2>/dev/null || true
      break
    fi
    if (( SECONDS >= deadline )); then
      d286_attempt_watchdog_timeout=true
      kill -KILL "$d286_attempt_pid" 2>/dev/null || true
      break
    fi
    sleep 0.1
  done
  set +e
  wait "$d286_attempt_pid"
  rc=$?
  set -e
  d286_attempt_pid=
  d286_attempt_rc=$rc
  d286_cleanup_attempt || d286_refuse ATTEMPT_INPUT_CLEANUP_FAILED
  trap - EXIT HUP INT TERM
}

operator_pre_reboot () {
  d286_refuse FIRST_REBOOT_CYCLE_CLOSED_USE_OPERATOR_RETRY
}

operator_post_reboot () {
  d286_refuse FIRST_REBOOT_CYCLE_CLOSED_USE_OPERATOR_RETRY
}

operator_retry () {
  d286_refuse D286_01_LIVE_CLOSED_DO_NOT_RERUN
  local baseline user stamp capture rc audit_rc attempt cursor confirmation outcome epoch_count
  local final_outcome=FAIL_LIVE_PENDING_INDEPENDENT_REVIEW matched_attempt=0 verify_epoch_total=0
  local -a outcomes=()
  [[ $EUID -ne 0 ]] || d286_refuse OPERATOR_MUST_BE_UNPRIVILEGED
  baseline=$(git -C "$d286_root" rev-parse HEAD)
  d286_verify_repo "$baseline"
  d286_require_polkit_password_path
  [[ -x /usr/bin/sudo ]] || d286_refuse SUDO_NOT_FOUND
  user=$(id -un); d286_safe_user "$user" || d286_refuse OPERATOR_USER_INVALID
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  capture="$d286_capture_root/D28601_RETRY_${stamp}_${baseline:0:12}/sanitized"
  [[ ! -e $capture && ! -L $capture ]] || d286_refuse CAPTURE_COLLISION
  install -d -m 0700 "$capture"
  set +e
  pkexec "$d286_script_dir/run-d286-01.sh" --root-audit POST_REBOOT_RETRY_PRE \
    --user "$user" 2>&1 | tee "$capture/pre-retry-root-audit.log"
  rc=${PIPESTATUS[0]}
  set -e
  [[ $rc -eq 0 ]] || d286_refuse PRE_RETRY_ROOT_AUDIT_FAILED
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES \
    "$capture/pre-retry-root-audit.log" >/dev/null || d286_refuse PRE_RETRY_AUDIT_INCOMPLETE
  [[ $(count_goodix_targets /sys/bus/usb/devices) -eq 1 ]] ||
    d286_refuse REAL_TARGET_CARDINALITY_NOT_ONE
  /usr/bin/sudo -K || d286_refuse SUDO_TIMESTAMP_INVALIDATION_FAILED
  echo 'Massimo 3 tentativi sudo reali, ciascuno con un solo contatto esplicito.'
  echo 'La password sudo è tecnicamente esclusa dal test; gli audit polkit restano password-only.'
  printf 'Per il tentativo 1/3 digitare INDICE DESTRO: '
  read -r confirmation
  [[ $confirmation == 'INDICE DESTRO' ]] || d286_refuse PHYSICAL_FINGER_NOT_CONFIRMED
  for attempt in 1 2 3; do
    echo "TENTATIVO $attempt/$d286_max_verify_attempts — INDICE DESTRO"
    cursor=$(d286_current_cursor)
    d286_attempt_fallback_blocked=false
    d286_attempt_watchdog_timeout=false
    d286_run_sudo_attempt "$attempt" "$capture/attempt-${attempt}.sudo.log"
    /usr/bin/sudo -K || d286_refuse SUDO_TIMESTAMP_FINAL_INVALIDATION_FAILED
    set +e
    pkexec "$d286_script_dir/run-d286-01.sh" --root-attempt-audit --user "$user" \
      --cursor "$cursor" --attempt "$attempt" --sudo-rc "$d286_attempt_rc" \
      --fallback-blocked "$d286_attempt_fallback_blocked" \
      --watchdog-timeout "$d286_attempt_watchdog_timeout" \
      2>&1 | tee "$capture/attempt-${attempt}.audit.log"
    audit_rc=${PIPESTATUS[0]}
    set -e
    [[ $audit_rc -eq 0 ]] || d286_refuse ATTEMPT_AUDIT_FAILED
    outcome=$(sed -n 's/^D286_01_ATTEMPT_OUTCOME=//p' \
      "$capture/attempt-${attempt}.audit.log")
    [[ $(printf '%s\n' "$outcome" | grep -c . || true) -eq 1 ]] ||
      d286_refuse ATTEMPT_OUTCOME_AMBIGUOUS
    epoch_count=$(sed -n 's/^D286_01_ATTEMPT_VERIFY_EPOCH_COUNT=//p' \
      "$capture/attempt-${attempt}.audit.log")
    [[ $epoch_count =~ ^[0-9]+$ ]] || d286_refuse ATTEMPT_EPOCH_COUNT_INVALID
    verify_epoch_total=$((verify_epoch_total + epoch_count))
    outcomes+=("$outcome")
    case $outcome in
      MATCH)
        final_outcome=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
        matched_attempt=$attempt
        break
        ;;
      NO_MATCH)
        if [[ $attempt -lt $d286_max_verify_attempts ]]; then
          echo "NO_MATCH osservato al tentativo $attempt/$d286_max_verify_attempts."
          printf 'Per autorizzare esplicitamente il tentativo %d/3 digitare TENTATIVO %d: ' \
            "$((attempt + 1))" "$((attempt + 1))"
          read -r confirmation
          [[ $confirmation == "TENTATIVO $((attempt + 1))" ]] ||
            d286_refuse NEXT_ATTEMPT_NOT_CONFIRMED
        fi
        ;;
      PAM_ERROR|SAFETY_VIOLATION)
        break
        ;;
      *)
        d286_refuse ATTEMPT_OUTCOME_INVALID
        ;;
    esac
  done
  set +e
  pkexec "$d286_script_dir/run-d286-01.sh" --root-audit POST_REBOOT_RETRY_FINAL \
    --user "$user" 2>&1 | tee "$capture/post-retry-root-audit.log"
  rc=${PIPESTATUS[0]}
  set -e
  [[ $rc -eq 0 ]] || d286_refuse POST_RETRY_ROOT_AUDIT_FAILED
  {
    echo "D286_01_RESULT=$final_outcome"
    echo "D286_01_REPO_BASELINE=$baseline"
    echo D286_01_POST_REBOOT_PERSISTENT_STATE_AUDIT=PASS
    echo "D286_01_MAX_VERIFY_ATTEMPTS=$d286_max_verify_attempts"
    echo "D286_01_VERIFY_ATTEMPTS_PERFORMED=${#outcomes[@]}"
    echo "D286_01_VERIFY_EPOCH_COUNT=$verify_epoch_total"
    echo "D286_01_MATCHED_ATTEMPT=$matched_attempt"
    echo D286_01_PAM_MAX_TRIES_PER_ATTEMPT=1
    echo D286_01_MAX_PHYSICAL_CONTACTS=3
    echo D286_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
    echo D286_01_STOP_ON_FIRST_MATCH=true
    echo D286_01_PASSWORD_INPUT_POSSIBLE_DURING_SUDO_TEST=false
    echo D286_01_PASSWORD_FALLBACK_STRUCTURALLY_AVAILABLE=true
    printf 'D286_01_ATTEMPT_OUTCOMES='
    (IFS=,; echo "${outcomes[*]}")
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
    echo REAL_USB_ENUMERATION_ATTEMPTED=true
    if [[ $verify_epoch_total -gt 0 ]]; then
      echo REAL_SENSOR_ACCESSED=true
    else
      echo REAL_SENSOR_ACCESSED=false
    fi
    echo LIVE_EXECUTION_PERFORMED=true
  } >"$capture/summary.env"
  chmod 0600 "$capture"/*
  sha256sum "$capture"/*
  echo "D286_01_RETRY_RESULT=$final_outcome"
  echo "D286_01_CAPTURE_DIRECTORY=$capture"
  [[ $final_outcome == PASS_LIVE_PENDING_INDEPENDENT_REVIEW ]] ||
    d286_refuse RETRY_SERIES_FAILED_NO_FOURTH_ATTEMPT
}

offline_preflight () {
  [[ $EUID -ne 0 ]] || d286_refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  bash -n "$d286_script_dir/run-d286-01.sh"
  (cd "$d286_root" && python3 -m unittest -v analysis.D286.test_d286_01_offline_contract)
  d286_require_polkit_password_path
  d286_current_cursor >/dev/null
  echo D286_01_OFFLINE_PREFLIGHT=PASS
  echo D286_01_PRIVILEGED_AUDIT_PATH=POLKIT_SYSTEM_AUTH_WITHOUT_FINGERPRINT
  echo D286_01_FIRST_REBOOT_CYCLE=CLOSED_PRESERVED
  echo D286_01_RETRY_EXECUTION=HUMAN_REQUIRED
  echo D286_01_MAX_VERIFY_ATTEMPTS=3
  echo D286_01_MAX_PHYSICAL_CONTACTS=3
  echo D286_01_PAM_MAX_TRIES_PER_ATTEMPT=1
  echo D286_01_STOP_ON_FIRST_MATCH=true
  echo D286_01_PASSWORD_INPUT_POSSIBLE_DURING_SUDO_TEST=false
  echo D286_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo LIVE_EXECUTION_PERFORMED=false
}

case ${1:-} in
  --offline-preflight)
    [[ $# -eq 1 ]] || d286_refuse USAGE
    offline_preflight
    ;;
  --operator-pre-reboot)
    [[ $# -eq 1 ]] || d286_refuse USAGE
    operator_pre_reboot
    ;;
  --operator-post-reboot)
    [[ $# -eq 2 ]] || d286_refuse USAGE
    operator_post_reboot "$2"
    ;;
  --operator-retry)
    [[ $# -eq 1 ]] || d286_refuse USAGE
    operator_retry
    ;;
  --root-audit)
    [[ $# -eq 4 && $3 == --user ]] || d286_refuse USAGE
    d286_root_audit_installed "$2" "$4"
    ;;
  --root-attempt-audit)
    [[ $# -eq 13 && $2 == --user && $4 == --cursor && $6 == --attempt &&
       $8 == --sudo-rc && ${10} == --fallback-blocked &&
       ${12} == --watchdog-timeout ]] || d286_refuse USAGE
    d286_root_attempt_audit "$3" "$5" "$7" "$9" "${11}" "${13}"
    ;;
  *)
    echo "Uso: $0 --offline-preflight | --operator-retry" >&2
    exit 2
    ;;
esac
