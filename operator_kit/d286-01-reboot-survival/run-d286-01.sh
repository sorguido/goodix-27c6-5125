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
d286_critical=(analysis/D284 analysis/D285 analysis/D286
  operator_kit/d284-01-transient-sudo-pilot
  operator_kit/d285-01-persistent-sudo
  operator_kit/d286-01-reboot-survival
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

d286_root_final_audit () {
  local user=$1 since=$2 raw audit matcher total_epoch_count epoch_count retry_count reopen_count
  local reset_count clear_halt_count persistent_count match_count
  d286_root_audit_installed POST_REBOOT_POST_VERIFY "$user"
  [[ $since =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T ]] || d286_refuse INVALID_SINCE
  raw=$(mktemp /tmp/goodix-d286-journal.XXXXXX)
  d286_journal_tmp=$raw
  trap d286_cleanup_journal_tmp EXIT
  journalctl -b -u fprintd.service --since "$since" --no-pager >"$raw" ||
    d286_refuse JOURNAL_READ_FAILED
  audit=$(grep GOODIX_D282_EPOCH_AUDIT "$raw" || true)
  matcher=$(grep GOODIX_SIGFM_MATCH_AUDIT "$raw" || true)
  total_epoch_count=$(grep -c GOODIX_D282_EPOCH_AUDIT "$raw" || true)
  epoch_count=$(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$raw" || true)
  retry_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^(secure_retry|post_retry)=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  reopen_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^reopen=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  reset_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^reset=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  clear_halt_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^clear_halt=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  persistent_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^persistent=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  match_count=$(printf '%s\n' "$matcher" | grep -c 'event=outcome result=match' || true)
  [[ $total_epoch_count -eq 1 && $epoch_count -eq 1 &&
     $(printf '%s\n' "$audit" | grep -c 'consumed=1.*tls=1' || true) -eq 1 &&
     $(printf '%s\n' "$audit" | grep -c 'outstanding=0 drained=1 context_closed=1' || true) -eq 1 &&
     $retry_count -eq 0 && $reopen_count -eq 0 && $reset_count -eq 0 &&
     $clear_halt_count -eq 0 && $persistent_count -eq 0 && $match_count -eq 1 ]] ||
    d286_refuse POST_REBOOT_LIVE_AUDIT_FAILED
  sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT .*$\)/\1/p; s/^.*\(GOODIX_SIGFM_.*$\)/\1/p' \
    "$raw" | sort -u
  echo D286_01_POST_REBOOT_VERIFY_AUDIT=PASS_SINGLE_MATCH
  d286_cleanup_journal_tmp || d286_refuse JOURNAL_CLEANUP_FAILED
  trap - EXIT
}

d286_root_failure_audit () {
  local user=$1 since=$2 raw audit matcher total_epoch_count epoch_count
  local retry_count reopen_count reset_count clear_halt_count persistent_count match_count
  d286_root_audit_installed POST_REBOOT_FAILED_VERIFY "$user"
  [[ $since =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T ]] || d286_refuse INVALID_SINCE
  raw=$(mktemp /tmp/goodix-d286-journal.XXXXXX)
  d286_journal_tmp=$raw
  trap d286_cleanup_journal_tmp EXIT
  journalctl -b -u fprintd.service --since "$since" --no-pager >"$raw" ||
    d286_refuse JOURNAL_READ_FAILED
  audit=$(grep GOODIX_D282_EPOCH_AUDIT "$raw" || true)
  matcher=$(grep GOODIX_SIGFM_MATCH_AUDIT "$raw" || true)
  total_epoch_count=$(grep -c GOODIX_D282_EPOCH_AUDIT "$raw" || true)
  epoch_count=$(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$raw" || true)
  retry_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^(secure_retry|post_retry)=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  reopen_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^reopen=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  reset_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^reset=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  clear_halt_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^clear_halt=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  persistent_count=$(printf '%s\n' "$audit" | awk '{for(i=1;i<=NF;i++)if($i~/^persistent=/){split($i,a,"=");s+=a[2]}}END{print s+0}')
  match_count=$(printf '%s\n' "$matcher" | grep -c 'event=outcome result=match' || true)
  sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT .*$\)/\1/p; s/^.*\(GOODIX_SIGFM_.*$\)/\1/p' \
    "$raw" | sort -u
  echo D286_01_FAILURE_AUDIT=COLLECTED_NO_RETRY
  echo "D286_01_FAILURE_TOTAL_EPOCH_COUNT=$total_epoch_count"
  echo "D286_01_FAILURE_VERIFY_EPOCH_COUNT=$epoch_count"
  echo "D286_01_FAILURE_RETRY_COUNT=$retry_count"
  echo "D286_01_FAILURE_REOPEN_COUNT=$reopen_count"
  echo "D286_01_FAILURE_RESET_COUNT=$reset_count"
  echo "D286_01_FAILURE_CLEAR_HALT_COUNT=$clear_halt_count"
  echo "D286_01_FAILURE_PERSISTENT_WRITE_FAMILY_COUNT=$persistent_count"
  echo "D286_01_FAILURE_MATCH_COUNT=$match_count"
  d286_cleanup_journal_tmp || d286_refuse JOURNAL_CLEANUP_FAILED
  trap - EXIT
}

d286_capture_path () {
  local path=$1 resolved
  resolved=$(realpath -e -- "$path") || d286_refuse CAPTURE_PATH_INVALID
  [[ $resolved == "$d286_capture_root"/D28601_CYCLE_*/sanitized &&
     -d $resolved && ! -L $resolved ]] || d286_refuse CAPTURE_PATH_UNSAFE
  printf '%s\n' "$resolved"
}

operator_pre_reboot () {
  local baseline user stamp capture rc confirmation boot_id
  [[ $EUID -ne 0 ]] || d286_refuse OPERATOR_MUST_BE_UNPRIVILEGED
  baseline=$(git -C "$d286_root" rev-parse HEAD)
  d286_verify_repo "$baseline"
  d286_require_polkit_password_path
  user=$(id -un); d286_safe_user "$user" || d286_refuse OPERATOR_USER_INVALID
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  capture="$d286_capture_root/D28601_CYCLE_${stamp}_${baseline:0:12}/sanitized"
  [[ ! -e $capture && ! -L $capture ]] || d286_refuse CAPTURE_COLLISION
  install -d -m 0700 "$capture"
  set +e
  pkexec "$d286_script_dir/run-d286-01.sh" --root-audit PRE_REBOOT --user "$user" \
    2>&1 | tee "$capture/pre-reboot.log"
  rc=${PIPESTATUS[0]}
  set -e
  [[ $rc -eq 0 ]] || d286_refuse PRE_REBOOT_ROOT_AUDIT_FAILED
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES \
    "$capture/pre-reboot.log" >/dev/null || d286_refuse PRE_REBOOT_AUDIT_INCOMPLETE
  boot_id=$(sed -n 's/^D286_01_BOOT_ID=//p' "$capture/pre-reboot.log")
  [[ $boot_id =~ ^[0-9a-f-]{36}$ ]] || d286_refuse PRE_REBOOT_BOOT_ID_INVALID
  {
    echo D286_01_CYCLE_STATUS=PRE_REBOOT_PASS_PENDING_REBOOT
    echo "D286_01_REPO_BASELINE=$baseline"
    echo "D286_01_BOOT_ID_BEFORE=$boot_id"
    echo D286_01_PRE_REBOOT_ROOT_AUDIT=PASS
    echo D286_01_PRE_REBOOT_SENSOR_ACTION_COUNT=0
  } >"$capture/cycle.env"
  chmod 0600 "$capture/pre-reboot.log" "$capture/cycle.env"
  echo "D286_01_CAPTURE_DIRECTORY=$capture"
  echo "DOPO_IL_RIAVVIO=operator_kit/d286-01-reboot-survival/run-d286-01.sh --operator-post-reboot $capture"
  echo 'Il computer verrà riavviato. Salvare il lavoro nelle altre applicazioni.'
  printf 'Digitare RIAVVIA D286 per eseguire il reboot controllato: '
  read -r confirmation
  [[ $confirmation == 'RIAVVIA D286' ]] || d286_refuse REBOOT_CANCELLED
  sync "$capture/pre-reboot.log" "$capture/cycle.env"
  systemctl reboot || d286_refuse REBOOT_COMMAND_FAILED
}

operator_post_reboot () {
  local capture=$1 baseline user before now since rc audit_rc confirmation
  [[ $EUID -ne 0 ]] || d286_refuse OPERATOR_MUST_BE_UNPRIVILEGED
  baseline=$(git -C "$d286_root" rev-parse HEAD)
  d286_verify_repo "$baseline"
  d286_require_polkit_password_path
  user=$(id -un); d286_safe_user "$user" || d286_refuse OPERATOR_USER_INVALID
  capture=$(d286_capture_path "$capture")
  [[ $(state_value "$capture/cycle.env" D286_01_CYCLE_STATUS) == PRE_REBOOT_PASS_PENDING_REBOOT &&
     $(state_value "$capture/cycle.env" D286_01_REPO_BASELINE) == "$baseline" ]] ||
    d286_refuse CYCLE_STATE_INVALID
  before=$(state_value "$capture/cycle.env" D286_01_BOOT_ID_BEFORE) ||
    d286_refuse CYCLE_STATE_INVALID
  now=$(cat /proc/sys/kernel/random/boot_id)
  [[ $now != "$before" ]] || d286_refuse REBOOT_NOT_OBSERVED
  set +e
  pkexec "$d286_script_dir/run-d286-01.sh" --root-audit POST_REBOOT_PRE_VERIFY \
    --user "$user" 2>&1 | tee "$capture/post-reboot-pre-verify.log"
  rc=${PIPESTATUS[0]}
  set -e
  [[ $rc -eq 0 ]] || d286_refuse POST_REBOOT_ROOT_AUDIT_FAILED
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES \
    "$capture/post-reboot-pre-verify.log" >/dev/null || d286_refuse POST_REBOOT_ROOT_AUDIT_FAILED
  sudo -K || d286_refuse SUDO_TIMESTAMP_INVALIDATION_FAILED
  echo 'Una sola verifica sudo post-reboot. Non digitare la password.'
  printf 'Confermare il dito fisico digitando INDICE DESTRO: '
  read -r confirmation
  [[ $confirmation == 'INDICE DESTRO' ]] || d286_refuse PHYSICAL_FINGER_NOT_CONFIRMED
  since=$(date --iso-8601=ns)
  set +e
  timeout --signal=INT --kill-after=20s 75s env -u SUDO_ASKPASS sudo -v \
    2>&1 | tee "$capture/sudo-verify.log"
  rc=${PIPESTATUS[0]}
  set -e
  sudo -K || d286_refuse SUDO_TIMESTAMP_FINAL_INVALIDATION_FAILED
  if [[ $rc -ne 0 ]]; then
    set +e
    pkexec "$d286_script_dir/run-d286-01.sh" --root-failure-audit --user "$user" \
      --since "$since" 2>&1 | tee "$capture/post-reboot-failure-audit.log"
    audit_rc=${PIPESTATUS[0]}
    set -e
    {
      echo D286_01_RESULT=FAIL_LIVE_NO_RETRY_PENDING_INDEPENDENT_REVIEW
      echo "D286_01_REPO_BASELINE=$baseline"
      echo D286_01_REBOOT_OBSERVED=true
      echo D286_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
      echo "D286_01_SUDO_VALIDATE_RETURN_CODE=$rc"
      echo "D286_01_FAILURE_AUDIT_RETURN_CODE=$audit_rc"
    } >"$capture/failure-summary.env"
    chmod 0600 "$capture"/*
    [[ $audit_rc -eq 0 ]] ||
      d286_refuse SUDO_VALIDATE_FAILED_AND_FAILURE_AUDIT_FAILED_NO_RETRY
    d286_refuse SUDO_VALIDATE_FAILED_NO_RETRY
  fi
  set +e
  pkexec "$d286_script_dir/run-d286-01.sh" --root-final-audit --user "$user" \
    --since "$since" 2>&1 | tee "$capture/post-reboot-final-audit.log"
  rc=${PIPESTATUS[0]}
  set -e
  [[ $rc -eq 0 ]] || d286_refuse POST_REBOOT_FINAL_AUDIT_FAILED
  grep -Fx D286_01_POST_REBOOT_VERIFY_AUDIT=PASS_SINGLE_MATCH \
    "$capture/post-reboot-final-audit.log" >/dev/null || d286_refuse FINAL_AUDIT_INCOMPLETE
  {
    echo D286_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
    echo "D286_01_REPO_BASELINE=$baseline"
    echo D286_01_REBOOT_OBSERVED=true
    echo D286_01_POST_REBOOT_STATE_COHERENCE=true
    echo D286_01_POST_REBOOT_RUNTIME_INTEGRITY=true
    echo D286_01_POST_REBOOT_TEMPLATE_OWNERSHIP_PINNED=true
    echo D286_01_POST_REBOOT_UNINSTALL_READINESS=true
    echo D286_01_VERIFY_ACTION_COUNT=1
    echo D286_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
    echo D286_01_SUDO_VALIDATE_RETURN_CODE=0
    echo D286_01_SIGFM_MATCH_OUTCOME=match
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
    echo REAL_USB_ENUMERATION_ATTEMPTED=true
    echo REAL_SENSOR_ACCESSED=true
    echo LIVE_EXECUTION_PERFORMED=true
  } >"$capture/summary.env"
  echo D286_01_CYCLE_STATUS=PASS_LIVE_PENDING_INDEPENDENT_REVIEW >"$capture/cycle.env"
  echo "D286_01_REPO_BASELINE=$baseline" >>"$capture/cycle.env"
  echo "D286_01_BOOT_ID_BEFORE=$before" >>"$capture/cycle.env"
  echo "D286_01_BOOT_ID_AFTER=$now" >>"$capture/cycle.env"
  chmod 0600 "$capture"/*
  sha256sum "$capture"/*
  echo D286_01_POST_REBOOT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
  echo "D286_01_CAPTURE_DIRECTORY=$capture"
}

offline_preflight () {
  [[ $EUID -ne 0 ]] || d286_refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  bash -n "$d286_script_dir/run-d286-01.sh"
  (cd "$d286_root" && python3 -m unittest -v analysis.D286.test_d286_01_offline_contract)
  d286_require_polkit_password_path
  echo D286_01_OFFLINE_PREFLIGHT=PASS
  echo D286_01_PRIVILEGED_AUDIT_PATH=POLKIT_SYSTEM_AUTH_WITHOUT_FINGERPRINT
  echo D286_01_REBOOT_EXECUTION=HUMAN_REQUIRED
  echo D286_01_POST_REBOOT_VERIFY_ACTION_MAX=1
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
  --root-audit)
    [[ $# -eq 4 && $3 == --user ]] || d286_refuse USAGE
    d286_root_audit_installed "$2" "$4"
    ;;
  --root-final-audit)
    [[ $# -eq 5 && $2 == --user && $4 == --since ]] || d286_refuse USAGE
    d286_root_final_audit "$3" "$5"
    ;;
  --root-failure-audit)
    [[ $# -eq 5 && $2 == --user && $4 == --since ]] || d286_refuse USAGE
    d286_root_failure_audit "$3" "$5"
    ;;
  *)
    echo "Uso: $0 --offline-preflight | --operator-pre-reboot | --operator-post-reboot <capture-dir>" >&2
    exit 2
    ;;
esac
