#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

d290_original_hash=c6fc4a0bc2d89f88fa15ca7e9a6c5aaeccfbe66897755b5416ce9c5e35b4e40b
d290_candidate_hash=89d389e6c2ee59dcee374029a5428a81dc9138c4f5e86068159b3d5a2c77ab2d
d290_package=plasma-login-manager-6.7.5-1.fc44.x86_64
d290_fingerprint_line='auth        sufficient    /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=45 debug'
d290_max_direct_session_delay_us=2000000
d290_error=
d290_arm_cleanup_needed=false
d290_arm_committed=false
d290_close_rollback_pending=false
d290_close_tmp=

d290_die () {
  echo D290_01_GATE_REFUSED=true >&2
  echo "D290_01_REFUSAL_REASON=$1" >&2
  exit 3
}

d290_is_sha256 () { [[ ${1:-} =~ ^[0-9a-f]{64}$ ]]; }
d290_safe_user () { [[ ${1:-} =~ ^[a-z_][a-z0-9_-]*$ ]]; }
d290_hash () { sha256sum "$1" | awk '{print $1}'; }

d290_script=$(readlink -f -- "$0") || exit 2
d290_script_dir=$(CDPATH= cd -- "$(dirname -- "$d290_script")" && pwd -P)
d290_test_root=${D290_TEST_ROOT:-}
if [[ -n $d290_test_root ]]; then
  [[ $d290_test_root == /tmp/goodix-d290-test.* && -d $d290_test_root && ! -L $d290_test_root ]] ||
    d290_die TEST_ROOT_INVALID
  [[ $d290_script == "$d290_test_root/repo/operator_kit/d290-01-plasmalogin-persistent-test/run-d290-01.sh" ]] ||
    d290_die TEST_SCRIPT_PATH_INVALID
  d290_root=$d290_test_root/repo
  d290_host=$d290_test_root/host
  d290_sysfs=$d290_test_root/sys/bus/usb/devices
  d290_expected_uid=$(id -u)
  d290_expected_gid=$(id -g)
  d290_operator_uid=$d290_expected_uid
  d290_operator_gid=$d290_expected_gid
  d290_operator_user=$(id -un)
else
  if [[ $EUID -ne 0 ]]; then
    exec pkexec "$d290_script" "$@"
  fi
  [[ ${PKEXEC_UID:-} =~ ^[1-9][0-9]*$ ]] || d290_die OPERATOR_UID_MISSING
  d290_operator_uid=$PKEXEC_UID
  d290_operator_user=$(id -nu "$d290_operator_uid") || d290_die OPERATOR_USER_UNKNOWN
  d290_operator_gid=$(id -g "$d290_operator_user") || d290_die OPERATOR_GROUP_UNKNOWN
  d290_safe_user "$d290_operator_user" || d290_die OPERATOR_USER_INVALID
  d290_root=$(readlink -f -- "$d290_script_dir/../..") || d290_die REPOSITORY_NOT_FOUND
  [[ -d $d290_root/.git && ! -L $d290_root/.git ]] || d290_die REPOSITORY_NOT_FOUND
  [[ $(git -c "safe.directory=$d290_root" -C "$d290_root" rev-parse --show-toplevel) == "$d290_root" ]] ||
    d290_die REPOSITORY_IDENTITY_MISMATCH
  d290_host=
  d290_sysfs=/sys/bus/usb/devices
  d290_expected_uid=0
  d290_expected_gid=0
fi

d290_git () {
  git -c "safe.directory=$d290_root" -C "$d290_root" "$@"
}

d290_target=$d290_host/usr/lib/pam.d/plasmalogin
d290_password_auth=$d290_host/etc/authselect/password-auth
d290_pam_module=$d290_host/usr/lib64/security/pam_fprintd.so
d290_state_parent=$d290_host/etc/goodix-27c6-5125
d290_state_dir=$d290_state_parent/d290-01-plasmalogin-persistent-test
d290_state=$d290_state_dir/state.env
d290_backup=$d290_state_dir/plasmalogin.original
d290_candidate=$d290_root/operator_kit/live_probe/experiments/d290-plasmalogin/goodix-d290-plasmalogin.pam
d290_d286=$d290_root/operator_kit/d286-01-reboot-survival/run-d286-01.sh
d290_capture_root=$d290_root/captures/D290_01
d290_critical=(
  "Goodix 27c6 5125 manuale tecnico.md"
  analysis/D290
  operator_kit/d285-01-persistent-sudo
  operator_kit/d286-01-reboot-survival
  operator_kit/d290-01-plasmalogin-persistent-test
  operator_kit/live_probe
)

d290_context () {
  if [[ -n $d290_test_root ]]; then
    printf '%s\n' "${D290_TEST_CONTEXT:-system_u:object_r:lib_t:s0}"
  else
    stat -Lc %C "$1"
  fi
}

d290_policy_context () {
  matchpathcon -n "$1"
}

d290_require_tools () {
  local command
  for command in awk chmod chown cmp cp date dirname find getent grep id install \
      git journalctl loginctl matchpathcon mkdir mktemp mountpoint mv pgrep \
      readlink restorecon rm rmdir rpm sed sha256sum sort stat touch wc xargs; do
    command -v "$command" >/dev/null || d290_die "HOST_TOOL_MISSING_${command}"
  done
}

d290_verify_repo_for_arm () {
  local head remote
  [[ $(d290_git branch --show-current) == development ]] || d290_die WRONG_BRANCH
  head=$(d290_git rev-parse HEAD) || d290_die HEAD_UNREADABLE
  remote=$(d290_git rev-parse origin/development) || d290_die ORIGIN_UNREADABLE
  [[ $head == "$remote" ]] || d290_die HEAD_REMOTE_MISMATCH
  [[ -z $(d290_git status --porcelain --untracked-files=all -- "${d290_critical[@]}") ]] ||
    d290_die LIVE_CRITICAL_SET_DIRTY
  d290_baseline=$head
}

d290_verify_candidate_delta () {
  local generated rc=0
  generated=$(mktemp "${TMPDIR:-/tmp}/goodix-d290-pam.XXXXXX") || return 1
  awk -v line="$d290_fingerprint_line" '
    NR == 1 && $0 == "auth     [success=done ignore=ignore default=bad] pam_selinux_permit.so" {
      print; print line; inserted=1; next
    }
    { print }
    END { if (inserted != 1) exit 1 }
  ' "$d290_target" >"$generated" || rc=1
  [[ $rc -ne 0 ]] || cmp -s "$generated" "$d290_candidate" || rc=1
  rm -f -- "$generated"
  [[ $rc -eq 0 ]]
}

d290_count_goodix () {
  local device count=0
  for device in "$d290_sysfs"/*; do
    [[ -f $device/idVendor && -f $device/idProduct ]] || continue
    if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      count=$((count + 1))
    fi
  done
  printf '%s\n' "$count"
}

d290_old_method_clean () {
  if mountpoint -q "$d290_target"; then return 1; fi
  [[ ! -e $d290_host/run/goodix-d290-plasmalogin-$d290_operator_uid ]]
  if pgrep -f '[r]oot-overlay\.sh --hold' >/dev/null; then return 1; fi
  if pgrep -f '[p]kexec .*root-overlay\.sh' >/dev/null; then return 1; fi
}

d290_run_d286_audit () {
  local phase=$1 output
  output=$("$d290_d286" --root-audit "$phase" --user "$d290_operator_user") || return 1
  grep -Fx D286_01_STATE_COHERENCE=PASS_ROOT_ONLY <<<"$output" >/dev/null || return 1
  grep -Fx D286_01_RUNTIME_INTEGRITY=PASS <<<"$output" >/dev/null || return 1
  grep -Fx D286_01_PASSWORD_FALLBACK=PASS <<<"$output" >/dev/null || return 1
  grep -Fx D286_01_TEMPLATE_OWNERSHIP=PASS_PINNED_EXACTLY_ONE <<<"$output" >/dev/null || return 1
  printf '%s\n' "$output"
}

d290_package_verify_snapshot () {
  local output errors verify_rc
  output=$(mktemp "${TMPDIR:-/tmp}/goodix-d290-rpm-output.XXXXXX") || return 1
  errors=$(mktemp "${TMPDIR:-/tmp}/goodix-d290-rpm-errors.XXXXXX") || {
    rm -f -- "$output"
    return 1
  }
  if rpm -V plasma-login-manager >"$output" 2>"$errors"; then
    verify_rc=0
  else
    verify_rc=$?
  fi
  if [[ $verify_rc -gt 1 || -s $errors || ( $verify_rc -eq 1 && ! -s $output ) ]] ||
      awk -v target="$d290_target" '$NF == target { found=1 } END { exit !found }' "$output"; then
    rm -f -- "$output" "$errors"
    return 1
  fi
  d290_package_verify_rc=$verify_rc
  d290_package_verify_hash=$(d290_hash "$output") || {
    rm -f -- "$output" "$errors"
    return 1
  }
  rm -f -- "$output" "$errors"
  d290_is_sha256 "$d290_package_verify_hash"
}

d290_validate_arm_preflight () {
  d290_verify_repo_for_arm
  [[ ! -e $d290_state_dir && ! -L $d290_state_dir ]] || d290_die PREEXISTING_ARM_STATE
  [[ -d $d290_state_parent && ! -L $d290_state_parent ]] || d290_die STATE_PARENT_UNSAFE
  [[ $(stat -Lc '%u:%g:%a' "$d290_state_parent") == "$d290_expected_uid:$d290_expected_gid:755" ]] ||
    d290_die STATE_PARENT_METADATA_DRIFT
  [[ -f $d290_target && ! -L $d290_target ]] || d290_die HOST_PAM_TYPE_DRIFT
  [[ $(d290_hash "$d290_target") == "$d290_original_hash" ]] || d290_die HOST_PAM_HASH_DRIFT
  [[ $(stat -Lc '%u:%g:%a' "$d290_target") == "$d290_expected_uid:$d290_expected_gid:644" ]] ||
    d290_die HOST_PAM_METADATA_DRIFT
  [[ -f $d290_candidate && ! -L $d290_candidate && $(d290_hash "$d290_candidate") == "$d290_candidate_hash" ]] ||
    d290_die CANDIDATE_HASH_DRIFT
  d290_verify_candidate_delta || d290_die CANDIDATE_DELTA_DRIFT
  [[ -f $d290_pam_module && ! -L $d290_pam_module ]] || d290_die PAM_FPRINTD_MODULE_MISSING
  [[ -f $d290_password_auth && ! -L $d290_password_auth ]] || d290_die PASSWORD_AUTH_UNSAFE
  grep -Fx 'auth        substack      password-auth' "$d290_candidate" >/dev/null ||
    d290_die PASSWORD_AUTH_FALLBACK_MISSING
  ! grep -F pam_fprintd.so "$d290_password_auth" >/dev/null ||
    d290_die GLOBAL_PASSWORD_AUTH_FINGERPRINT_ENABLED
  [[ $(rpm -q plasma-login-manager) == "$d290_package" ]] || d290_die PACKAGE_VERSION_DRIFT
  [[ $(rpm -qf "$d290_target") == "$d290_package" ]] || d290_die PACKAGE_OWNERSHIP_DRIFT
  d290_original_mtime=$(stat -Lc %Y "$d290_target") || d290_die HOST_PAM_MTIME_UNREADABLE
  [[ $d290_original_mtime =~ ^[0-9]+$ ]] || d290_die HOST_PAM_MTIME_INVALID
  d290_package_verify_snapshot || d290_die PACKAGE_VERIFY_BASELINE_FAILED
  d290_package_verify_baseline_rc=$d290_package_verify_rc
  d290_package_verify_baseline_hash=$d290_package_verify_hash
  [[ $(d290_count_goodix) -eq 1 ]] || d290_die GOODIX_CARDINALITY_NOT_ONE
  d290_old_method_clean || d290_die OLD_D290_METHOD_RESIDUAL
  d290_original_context=$(d290_context "$d290_target") || d290_die HOST_PAM_CONTEXT_UNREADABLE
  [[ $d290_original_context =~ ^[A-Za-z0-9_:.-]+$ ]] || d290_die HOST_PAM_CONTEXT_INVALID
  d290_policy_context=$(d290_policy_context "$d290_target") || d290_die HOST_PAM_POLICY_CONTEXT_UNREADABLE
  [[ $d290_policy_context == "$d290_original_context" ]] || d290_die HOST_PAM_SELINUX_POLICY_DRIFT
  d290_run_d286_audit D290_PERSISTENT_ARM_PRE >/dev/null || d290_die D286_PREFLIGHT_FAILED
}

d290_write_state () {
  local status=$1 temporary=$d290_state_dir/.state.env.tmp
  [[ ! -e $temporary && ! -L $temporary ]] || return 1
  {
    echo D290_01_STATE_VERSION=2
    echo "D290_01_ARM_STATUS=$status"
    echo "D290_01_BASELINE=$d290_baseline"
    echo "D290_01_OPERATOR_UID=$d290_operator_uid"
    echo "D290_01_OPERATOR_USER=$d290_operator_user"
    echo "D290_01_ARM_BOOT_ID=$d290_arm_boot_id"
    echo "D290_01_PACKAGE=$d290_package"
    echo "D290_01_ORIGINAL_HASH=$d290_original_hash"
    echo "D290_01_CANDIDATE_HASH=$d290_candidate_hash"
    echo D290_01_ORIGINAL_MODE=644
    echo "D290_01_ORIGINAL_CONTEXT=$d290_original_context"
    echo "D290_01_ORIGINAL_MTIME=$d290_original_mtime"
    echo "D290_01_PACKAGE_VERIFY_BASELINE_RC=$d290_package_verify_baseline_rc"
    echo "D290_01_PACKAGE_VERIFY_BASELINE_HASH=$d290_package_verify_baseline_hash"
  } >"$temporary"
  chmod 0600 "$temporary"
  chown "$d290_expected_uid:$d290_expected_gid" "$temporary"
  restorecon "$temporary" >/dev/null
  mv -f -- "$temporary" "$d290_state"
}

d290_force_arm_rollback () {
  local rc=0
  if [[ -f $d290_backup && ! -L $d290_backup &&
        $(d290_hash "$d290_backup") == "$d290_original_hash" &&
        $(stat -Lc %Y "$d290_backup") == "$d290_original_mtime" ]]; then
    install -o "$d290_expected_uid" -g "$d290_expected_gid" -m 0644 "$d290_backup" "$d290_target" || rc=1
    touch -r "$d290_backup" "$d290_target" || rc=1
  elif [[ ! -f $d290_target || -L $d290_target || $(d290_hash "$d290_target") != "$d290_original_hash" ]]; then
    return 1
  fi
  [[ -f $d290_target && ! -L $d290_target ]] || rc=1
  chown "$d290_expected_uid:$d290_expected_gid" "$d290_target" || rc=1
  chmod 0644 "$d290_target" || rc=1
  restorecon "$d290_target" >/dev/null || rc=1
  [[ $(d290_hash "$d290_target") == "$d290_original_hash" ]] || rc=1
  [[ $(stat -Lc '%u:%g:%a' "$d290_target") == "$d290_expected_uid:$d290_expected_gid:644" ]] || rc=1
  [[ $(d290_context "$d290_target") == "$d290_original_context" ]] || rc=1
  [[ $(stat -Lc %Y "$d290_target") == "$d290_original_mtime" ]] || rc=1
  d290_package_verify_snapshot || rc=1
  [[ ${d290_package_verify_rc:-INVALID} == "$d290_package_verify_baseline_rc" &&
     ${d290_package_verify_hash:-INVALID} == "$d290_package_verify_baseline_hash" ]] || rc=1
  if [[ $rc -eq 0 ]]; then
    if [[ -e $d290_state_dir/.state.env.tmp || -L $d290_state_dir/.state.env.tmp ]]; then
      [[ -f $d290_state_dir/.state.env.tmp && ! -L $d290_state_dir/.state.env.tmp ]] || return 1
    fi
    rm -f -- "$d290_state" "$d290_backup" "$d290_state_dir/.state.env.tmp"
    rmdir -- "$d290_state_dir" || rc=1
  fi
  return "$rc"
}

d290_arm_exit () {
  local rc=$?
  trap - EXIT HUP INT TERM
  if [[ $d290_arm_cleanup_needed == true && $d290_arm_committed == false ]]; then
    set +e
    d290_force_arm_rollback
    local rollback_rc=$?
    set -e
    if [[ $rollback_rc -eq 0 ]]; then
      echo D290_ARM_FAILURE_ROLLBACK=PASS >&2
    else
      echo D290_ARM_FAILURE_ROLLBACK=FAILED_STATE_RETAINED >&2
      rc=1
    fi
  fi
  exit "$rc"
}

d290_operator_arm () {
  d290_validate_arm_preflight
  d290_arm_boot_id=$(<"$d290_host/proc/sys/kernel/random/boot_id") || d290_die BOOT_ID_UNREADABLE
  [[ $d290_arm_boot_id =~ ^[0-9a-f-]{36}$ ]] || d290_die BOOT_ID_INVALID
  install -d -o "$d290_expected_uid" -g "$d290_expected_gid" -m 0700 "$d290_state_dir" ||
    d290_die STATE_DIRECTORY_CREATE_FAILED
  d290_arm_cleanup_needed=true
  trap d290_arm_exit EXIT
  trap 'exit 130' HUP INT
  trap 'exit 143' TERM
  cp -p -- "$d290_target" "$d290_backup" || d290_die BACKUP_CREATE_FAILED
  chown "$d290_expected_uid:$d290_expected_gid" "$d290_backup" || d290_die BACKUP_OWNER_FAILED
  chmod 0600 "$d290_backup" || d290_die BACKUP_MODE_FAILED
  restorecon -RF "$d290_state_dir" >/dev/null || d290_die BACKUP_SELINUX_CONTEXT_FAILED
  d290_write_state PREPARING || d290_die PREPARING_STATE_WRITE_FAILED
  [[ $(d290_hash "$d290_backup") == "$d290_original_hash" ]] || d290_die BACKUP_HASH_MISMATCH
  [[ $(stat -Lc %Y "$d290_backup") == "$d290_original_mtime" ]] || d290_die BACKUP_MTIME_MISMATCH
  install -o "$d290_expected_uid" -g "$d290_expected_gid" -m 0644 "$d290_candidate" "$d290_target" ||
    d290_die CANDIDATE_INSTALL_FAILED
  restorecon "$d290_target" >/dev/null || d290_die CANDIDATE_SELINUX_CONTEXT_APPLY_FAILED
  [[ $(d290_hash "$d290_target") == "$d290_candidate_hash" ]] || d290_die CANDIDATE_INSTALL_HASH_MISMATCH
  [[ $(stat -Lc '%u:%g:%a' "$d290_target") == "$d290_expected_uid:$d290_expected_gid:644" ]] ||
    d290_die CANDIDATE_INSTALL_METADATA_MISMATCH
  [[ $(d290_context "$d290_target") == "$d290_original_context" ]] || d290_die CANDIDATE_SELINUX_CONTEXT_MISMATCH
  d290_write_state ARMED || d290_die ARMED_STATE_WRITE_FAILED
  [[ $(stat -Lc '%u:%g:%a' "$d290_state_dir") == "$d290_expected_uid:$d290_expected_gid:700" ]] ||
    d290_die STATE_DIRECTORY_METADATA_MISMATCH
  [[ $(stat -Lc '%u:%g:%a' "$d290_state") == "$d290_expected_uid:$d290_expected_gid:600" ]] ||
    d290_die STATE_FILE_METADATA_MISMATCH
  [[ $(stat -Lc '%u:%g:%a' "$d290_backup") == "$d290_expected_uid:$d290_expected_gid:600" ]] ||
    d290_die BACKUP_METADATA_MISMATCH
  d290_arm_committed=true
  trap - EXIT HUP INT TERM
  echo D290_PERSISTENT_TEST_ARMED=true
  echo D290_PLASMALOGIN_PAM_CANDIDATE_INSTALLED=true
  echo D290_PASSWORD_FALLBACK_PRESERVED=true
  echo D290_ORIGINAL_PAM_BACKUP_PINNED=true
  echo 'D290 pronto. Non ripetere ARM: eseguire ora manualmente sudo reboot.'
}

d290_state_value () {
  local key=$1 value count
  count=$(grep -c "^${key}=" "$d290_state" || true)
  [[ $count -eq 1 ]] || return 1
  value=$(sed -n "s/^${key}=//p" "$d290_state")
  [[ -n $value ]] || return 1
  printf '%s\n' "$value"
}

d290_load_state () {
  local entry_count link_count temporary=$d290_state_dir/.state.env.tmp
  d290_error=
  [[ -d $d290_state_dir && ! -L $d290_state_dir && -f $d290_state && ! -L $d290_state &&
     -f $d290_backup && ! -L $d290_backup ]] || { d290_error=STATE_MISSING_OR_UNSAFE; return 1; }
  [[ $(stat -Lc '%u:%g:%a' "$d290_state_dir") == "$d290_expected_uid:$d290_expected_gid:700" &&
     $(stat -Lc '%u:%g:%a' "$d290_state") == "$d290_expected_uid:$d290_expected_gid:600" &&
     $(stat -Lc '%u:%g:%a' "$d290_backup") == "$d290_expected_uid:$d290_expected_gid:600" ]] ||
    { d290_error=STATE_METADATA_DRIFT; return 1; }
  if [[ -e $temporary || -L $temporary ]]; then
    [[ -f $temporary && ! -L $temporary &&
       $(stat -Lc '%u:%g:%a' "$temporary") == "$d290_expected_uid:$d290_expected_gid:600" ]] ||
      { d290_error=STATE_TEMPORARY_DRIFT; return 1; }
    rm -f -- "$temporary" || { d290_error=STATE_TEMPORARY_REMOVE_FAILED; return 1; }
  fi
  entry_count=$(find "$d290_state_dir" -mindepth 1 -maxdepth 1 -printf x | wc -c)
  link_count=$(find "$d290_state_dir" -mindepth 1 -maxdepth 1 -type l -printf x | wc -c)
  [[ $entry_count -eq 2 && $link_count -eq 0 ]] || { d290_error=STATE_TOPOLOGY_DRIFT; return 1; }
  d290_baseline=$(d290_state_value D290_01_BASELINE) || { d290_error=STATE_INVALID; return 1; }
  d290_arm_boot_id=$(d290_state_value D290_01_ARM_BOOT_ID) || { d290_error=STATE_INVALID; return 1; }
  d290_original_context=$(d290_state_value D290_01_ORIGINAL_CONTEXT) || { d290_error=STATE_INVALID; return 1; }
  d290_original_mtime=$(d290_state_value D290_01_ORIGINAL_MTIME) || { d290_error=STATE_INVALID; return 1; }
  d290_package_verify_baseline_rc=$(d290_state_value D290_01_PACKAGE_VERIFY_BASELINE_RC) || { d290_error=STATE_INVALID; return 1; }
  d290_package_verify_baseline_hash=$(d290_state_value D290_01_PACKAGE_VERIFY_BASELINE_HASH) || { d290_error=STATE_INVALID; return 1; }
  d290_arm_status=$(d290_state_value D290_01_ARM_STATUS) || { d290_error=STATE_INVALID; return 1; }
  [[ $(d290_state_value D290_01_STATE_VERSION) == 2 &&
     $d290_arm_status =~ ^(ARMED|PREPARING)$ &&
     $(d290_state_value D290_01_OPERATOR_UID) == "$d290_operator_uid" &&
     $(d290_state_value D290_01_OPERATOR_USER) == "$d290_operator_user" &&
     $(d290_state_value D290_01_PACKAGE) == "$d290_package" &&
     $(d290_state_value D290_01_ORIGINAL_HASH) == "$d290_original_hash" &&
     $(d290_state_value D290_01_CANDIDATE_HASH) == "$d290_candidate_hash" &&
     $(d290_state_value D290_01_ORIGINAL_MODE) == 644 &&
     $d290_baseline =~ ^[0-9a-f]{40}$ && $d290_arm_boot_id =~ ^[0-9a-f-]{36}$ &&
     $d290_original_context =~ ^[A-Za-z0-9_:.-]+$ && $d290_original_mtime =~ ^[0-9]+$ &&
     $d290_package_verify_baseline_rc =~ ^[01]$ ]] || { d290_error=STATE_CONTENT_DRIFT; return 1; }
  d290_is_sha256 "$d290_package_verify_baseline_hash" || { d290_error=STATE_CONTENT_DRIFT; return 1; }
  [[ $(d290_hash "$d290_backup") == "$d290_original_hash" ]] || { d290_error=BACKUP_HASH_DRIFT; return 1; }
  [[ $(stat -Lc %Y "$d290_backup") == "$d290_original_mtime" ]] || { d290_error=BACKUP_MTIME_DRIFT; return 1; }
}

d290_rollback_internal () {
  local current policy_context rc=0
  d290_load_state || return 1
  [[ $(rpm -q plasma-login-manager) == "$d290_package" ]] || { d290_error=PACKAGE_VERSION_DRIFT; return 1; }
  [[ -f $d290_target && ! -L $d290_target ]] || { d290_error=HOST_PAM_TYPE_DRIFT; return 1; }
  current=$(d290_hash "$d290_target") || { d290_error=HOST_PAM_UNREADABLE; return 1; }
  if [[ $current == "$d290_candidate_hash" ]]; then
    install -o "$d290_expected_uid" -g "$d290_expected_gid" -m 0644 "$d290_backup" "$d290_target" || rc=1
  elif [[ $current != "$d290_original_hash" ]]; then
    d290_error=UNKNOWN_HOST_PAM_DRIFT
    return 1
  fi
  touch -r "$d290_backup" "$d290_target" || rc=1
  chown "$d290_expected_uid:$d290_expected_gid" "$d290_target" || rc=1
  chmod 0644 "$d290_target" || rc=1
  restorecon "$d290_target" >/dev/null || rc=1
  [[ $(d290_hash "$d290_target") == "$d290_original_hash" ]] || rc=1
  [[ $(stat -Lc '%u:%g:%a' "$d290_target") == "$d290_expected_uid:$d290_expected_gid:644" ]] || rc=1
  [[ $(d290_context "$d290_target") == "$d290_original_context" ]] || rc=1
  [[ $(stat -Lc %Y "$d290_target") == "$d290_original_mtime" ]] || rc=1
  policy_context=$(d290_policy_context "$d290_target") || rc=1
  [[ $policy_context == "$d290_original_context" ]] || rc=1
  [[ $(rpm -qf "$d290_target") == "$d290_package" ]] || rc=1
  d290_package_verify_snapshot || rc=1
  [[ ${d290_package_verify_rc:-INVALID} == "$d290_package_verify_baseline_rc" &&
     ${d290_package_verify_hash:-INVALID} == "$d290_package_verify_baseline_hash" ]] || rc=1
  d290_run_d286_audit D290_PERSISTENT_ROLLBACK_POST >/dev/null || rc=1
  if [[ $rc -ne 0 ]]; then
    d290_error=ROLLBACK_VERIFICATION_FAILED
    return 1
  fi
  rm -f -- "$d290_state" "$d290_backup" || { d290_error=STATE_REMOVE_FAILED; return 1; }
  rmdir -- "$d290_state_dir" || { d290_error=STATE_DIRECTORY_REMOVE_FAILED; return 1; }
  echo D290_HOST_PAM_RESTORED=true
  echo D290_STATE_REMOVED=true
  echo D290_ROLLBACK=PASS
}

d290_sanitize () {
  sed -E "s/${d290_operator_user//\//\\/}/<USER>/g"
}

d290_field_sum () {
  local key=$1 file=$2
  awk -v key="$key" '/GOODIX_D282_EPOCH_AUDIT / {
    for (i=1;i<=NF;i++) { split($i,a,"="); if (a[1]==key && a[2]~/^[0-9]+$/) s+=a[2] }
  } END { print s+0 }' "$file"
}

d290_log_monotonic_us () {
  local file=$1 marker=$2
  awk -v marker="$marker" '
    index($0, marker) {
      stamp=$0
      if (!sub(/^\[[[:space:]]*/, "", stamp)) exit 2
      sub(/\].*$/, "", stamp)
      split(stamp, part, /[.]/)
      if (part[1] !~ /^[0-9]+$/ || part[2] !~ /^[0-9]+$/ || length(part[2]) != 6) exit 2
      printf "%.0f\n", (part[1] * 1000000) + part[2]
    }
  ' "$file"
}

d290_collect_session () {
  local session_id session_uid user service type class state tty timestamp leader count=0
  while read -r session_id session_uid _; do
    [[ $session_uid == "$d290_operator_uid" ]] || continue
    service=$(loginctl show-session "$session_id" -p Service --value 2>/dev/null || true)
    type=$(loginctl show-session "$session_id" -p Type --value 2>/dev/null || true)
    class=$(loginctl show-session "$session_id" -p Class --value 2>/dev/null || true)
    state=$(loginctl show-session "$session_id" -p State --value 2>/dev/null || true)
    tty=$(loginctl show-session "$session_id" -p TTY --value 2>/dev/null || true)
    user=$(loginctl show-session "$session_id" -p User --value 2>/dev/null || true)
    timestamp=$(loginctl show-session "$session_id" -p TimestampMonotonic --value 2>/dev/null || true)
    leader=$(loginctl show-session "$session_id" -p Leader --value 2>/dev/null || true)
    if [[ $user == "$d290_operator_uid" && $service == plasmalogin && $type == wayland &&
          $class == user && $state =~ ^(active|online)$ && $timestamp =~ ^[0-9]+$ &&
          $leader =~ ^[1-9][0-9]*$ ]]; then
      count=$((count + 1))
      d290_session_id=$session_id
      d290_session_service=$service
      d290_session_type=$type
      d290_session_class=$class
      d290_session_state=$state
      d290_session_tty=${tty:-NONE}
      d290_session_timestamp_monotonic=$timestamp
      d290_session_leader=$leader
    fi
  done < <(loginctl list-sessions --no-legend 2>/dev/null)
  d290_session_count=$count
  [[ $count -eq 1 ]]
}

d290_collect_and_classify () {
  local capture=$1 current_hash epoch_count outcome_count result valid_epoch=false session_valid=false
  local journal_ok=true fprint_status plasma_status direct_login_causality=false
  local match_time=NONE session_open_time=NONE match_to_session_delta=NONE match_to_open_delta=NONE
  local session_open_count password_auth_continuation_count session_open_marker
  d290_close_boot_id=$(<"$d290_host/proc/sys/kernel/random/boot_id") || return 1
  current_hash=$(d290_hash "$d290_target") || current_hash=UNREADABLE
  {
    echo "D290_01_BASELINE=$d290_baseline"
    echo "D290_01_ARM_BOOT_ID=$d290_arm_boot_id"
    echo "D290_01_CLOSE_BOOT_ID=$d290_close_boot_id"
    echo "D290_01_REBOOT_OBSERVED=$([[ $d290_close_boot_id != "$d290_arm_boot_id" ]] && echo true || echo false)"
    echo "D290_01_CURRENT_PAM_HASH_BEFORE_ROLLBACK=$current_hash"
    echo "D290_01_REPOSITORY_CONTINUITY_OK=$d290_close_repo_valid"
    echo D290_01_MAX_VERIFY_ACTIONS=1
    echo D290_01_MAX_PHYSICAL_CONTACTS=1
    echo D290_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
  } >"$capture/context.env"
  if d290_collect_session; then session_valid=true; fi
  {
    echo "D290_CURRENT_GRAPHICAL_SESSION_COUNT=${d290_session_count:-0}"
    echo "D290_CURRENT_GRAPHICAL_SESSION_ID=${d290_session_id:-NONE}"
    echo "D290_CURRENT_GRAPHICAL_SESSION_USER=$d290_operator_uid"
    echo "D290_CURRENT_GRAPHICAL_SESSION_SERVICE=${d290_session_service:-NONE}"
    echo "D290_CURRENT_GRAPHICAL_SESSION_TYPE=${d290_session_type:-NONE}"
    echo "D290_CURRENT_GRAPHICAL_SESSION_CLASS=${d290_session_class:-NONE}"
    echo "D290_CURRENT_GRAPHICAL_SESSION_STATE=${d290_session_state:-NONE}"
    echo "D290_CURRENT_GRAPHICAL_SESSION_TTY=${d290_session_tty:-NONE}"
    echo "D290_CURRENT_GRAPHICAL_SESSION_TIMESTAMP_MONOTONIC=${d290_session_timestamp_monotonic:-NONE}"
    echo "D290_CURRENT_GRAPHICAL_SESSION_LEADER=${d290_session_leader:-NONE}"
  } >"$capture/session.env"
  journalctl -b -u fprintd.service --no-pager -o short-monotonic 2>/dev/null |
    awk '/GOODIX_/' | d290_sanitize >"$capture/fprintd-goodix.log"
  fprint_status=("${PIPESTATUS[@]}")
  journalctl -b -u plasmalogin.service --no-pager -o short-monotonic 2>/dev/null |
    d290_sanitize >"$capture/plasmalogin.log"
  plasma_status=("${PIPESTATUS[@]}")
  [[ ${fprint_status[0]} -eq 0 && ${fprint_status[1]} -eq 0 && ${fprint_status[2]} -eq 0 ]] || journal_ok=false
  [[ ${plasma_status[0]} -eq 0 && ${plasma_status[1]} -eq 0 ]] || journal_ok=false
  {
    echo "D290_01_FPRINTD_JOURNAL_RETURN_CODE=${fprint_status[0]}"
    echo "D290_01_PLASMALOGIN_JOURNAL_RETURN_CODE=${plasma_status[0]}"
    echo "D290_01_JOURNAL_COLLECTION_OK=$journal_ok"
  } >"$capture/journal-status.env"
  epoch_count=$(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' \
    "$capture/fprintd-goodix.log" || true)
  outcome_count=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=\(match\|no_match\)' \
    "$capture/fprintd-goodix.log" || true)
  result=$(sed -n 's/.*GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=\(match\|no_match\).*/\1/p' \
    "$capture/fprintd-goodix.log")
  session_open_marker="plasmalogin-helper[${d290_session_leader:-NONE}]: pam_unix(plasmalogin:session): session opened for user <USER>(uid=$d290_operator_uid)"
  session_open_count=$(grep -Fc "$session_open_marker" "$capture/plasmalogin.log" || true)
  password_auth_continuation_count=$(grep -Fc 'pam_kwallet5(plasmalogin:auth):' \
    "$capture/plasmalogin.log" || true)
  if [[ $result == match && $session_valid == true && $session_open_count -eq 1 &&
        $password_auth_continuation_count -eq 0 ]]; then
    match_time=$(d290_log_monotonic_us "$capture/fprintd-goodix.log" \
      'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match') || match_time=INVALID
    session_open_time=$(d290_log_monotonic_us "$capture/plasmalogin.log" \
      "$session_open_marker") || session_open_time=INVALID
    if [[ $match_time =~ ^[0-9]+$ && $session_open_time =~ ^[0-9]+$ &&
          ${d290_session_timestamp_monotonic:-NONE} =~ ^[0-9]+$ ]] &&
        (( d290_session_timestamp_monotonic >= match_time && session_open_time >= match_time )); then
      match_to_session_delta=$((d290_session_timestamp_monotonic - match_time))
      match_to_open_delta=$((session_open_time - match_time))
      if (( match_to_session_delta <= d290_max_direct_session_delay_us &&
            match_to_open_delta <= d290_max_direct_session_delay_us )); then
        direct_login_causality=true
      fi
    fi
  fi
  if [[ $epoch_count -eq 1 && $outcome_count -eq 1 && $(grep -c . <<<"$result") -eq 1 &&
        $(d290_field_sum attempts "$capture/fprintd-goodix.log") -eq 1 &&
        $(d290_field_sum rejected "$capture/fprintd-goodix.log") -eq 0 &&
        $(d290_field_sum consumed "$capture/fprintd-goodix.log") -eq 1 &&
        $(d290_field_sum tls "$capture/fprintd-goodix.log") -eq 1 &&
        $(d290_field_sum first_image "$capture/fprintd-goodix.log") -eq 1 &&
        $(d290_field_sum secure_retry "$capture/fprintd-goodix.log") -eq 0 &&
        $(d290_field_sum post_retry "$capture/fprintd-goodix.log") -eq 0 &&
        $(d290_field_sum reopen "$capture/fprintd-goodix.log") -eq 0 &&
        $(d290_field_sum reset "$capture/fprintd-goodix.log") -eq 0 &&
        $(d290_field_sum clear_halt "$capture/fprintd-goodix.log") -eq 0 &&
        $(d290_field_sum persistent "$capture/fprintd-goodix.log") -eq 0 &&
        $(d290_field_sum outstanding "$capture/fprintd-goodix.log") -eq 0 &&
        $(d290_field_sum drained "$capture/fprintd-goodix.log") -eq 1 &&
        $(d290_field_sum context_closed "$capture/fprintd-goodix.log") -eq 1 ]]; then
    valid_epoch=true
  fi
  d290_classification=AMBIGUOUS_REVIEW_REQUIRED
  if [[ $journal_ok == true && $d290_close_repo_valid == true &&
        $d290_close_boot_id != "$d290_arm_boot_id" &&
        $current_hash == "$d290_candidate_hash" ]]; then
    if [[ $valid_epoch == true && $result == match && $session_valid == true &&
          $direct_login_causality == true ]]; then
      d290_classification=PASS_MATCH_NEW_SESSION
    elif [[ $valid_epoch == true && $result == no_match ]]; then
      d290_classification=NO_MATCH_PASSWORD_RECOVERY
    elif [[ $epoch_count -eq 0 && $outcome_count -eq 0 ]]; then
      d290_classification=NO_VERIFY_REACHED
    fi
  fi
  {
    echo "D290_01_CLASSIFICATION=$d290_classification"
    echo "D290_01_VERIFY_EPOCH_COUNT=$epoch_count"
    echo "D290_01_SIGFM_OUTCOME_COUNT=$outcome_count"
    echo "D290_01_SIGFM_RESULT=${result:-NONE}"
    echo "D290_01_EPOCH_INVARIANTS_VALID=$valid_epoch"
    echo "D290_01_NEW_PLASMALOGIN_WAYLAND_SESSION_VALID=$session_valid"
    echo "D290_01_MATCH_TIMESTAMP_MONOTONIC_US=$match_time"
    echo "D290_01_SESSION_OPEN_TIMESTAMP_MONOTONIC_US=$session_open_time"
    echo "D290_01_MATCH_TO_SESSION_DELTA_US=$match_to_session_delta"
    echo "D290_01_MATCH_TO_SESSION_OPEN_DELTA_US=$match_to_open_delta"
    echo "D290_01_PLASMALOGIN_SESSION_OPEN_COUNT=$session_open_count"
    echo "D290_01_PASSWORD_AUTH_CONTINUATION_COUNT=$password_auth_continuation_count"
    echo "D290_01_DIRECT_LOGIN_CAUSALITY_VALID=$direct_login_causality"
  } >"$capture/classification.env"
  [[ $journal_ok == true ]]
}

d290_check_close_repo () {
  d290_close_repo_valid=false
  [[ $(d290_git branch --show-current 2>/dev/null) == development ]] || return 0
  [[ $(d290_git rev-parse HEAD 2>/dev/null) == "$d290_baseline" ]] || return 0
  [[ $(d290_git rev-parse origin/development 2>/dev/null) == "$d290_baseline" ]] || return 0
  [[ -z $(d290_git status --porcelain --untracked-files=all -- "${d290_critical[@]}" 2>/dev/null) ]] || return 0
  [[ -f $d290_candidate && ! -L $d290_candidate && $(d290_hash "$d290_candidate") == "$d290_candidate_hash" ]] || return 0
  d290_close_repo_valid=true
}

d290_close_exit () {
  local rc=$? rollback_rc
  trap - EXIT HUP INT TERM
  if [[ -n $d290_close_tmp && -f $d290_close_tmp && ! -L $d290_close_tmp ]]; then
    rm -f -- "$d290_close_tmp"
  fi
  if [[ $d290_close_rollback_pending == true ]]; then
    set +e
    d290_rollback_internal >&2
    rollback_rc=$?
    set -e
    if [[ $rollback_rc -ne 0 && ! -e $d290_state_dir && -f $d290_target && ! -L $d290_target &&
          $(d290_hash "$d290_target") == "$d290_original_hash" &&
          $(stat -Lc '%u:%g:%a' "$d290_target") == "$d290_expected_uid:$d290_expected_gid:644" &&
          $(d290_context "$d290_target") == "$d290_original_context" &&
          $(stat -Lc %Y "$d290_target") == "$d290_original_mtime" ]]; then
      rollback_rc=0
    fi
    if [[ $rollback_rc -ne 0 ]]; then
      echo "D290_01_EMERGENCY_ROLLBACK_FAILED=${d290_error:-UNKNOWN}" >&2
      rc=1
    else
      echo D290_01_EMERGENCY_ROLLBACK=PASS >&2
    fi
  fi
  exit "$rc"
}

d290_finalize_capture () {
  local capture=$1
  (cd "$capture" && find . -maxdepth 1 -type f ! -name capture.sha256 -print0 |
    sort -z | xargs -0 sha256sum >capture.sha256)
  chown -R "$d290_operator_uid:$d290_operator_gid" "$capture"
  chmod 0755 "$capture"
  find "$capture" -maxdepth 1 -type f -exec chmod 0644 {} +
}

d290_operator_close () {
  local stamp capture collect_rc=0 rollback_rc=0 rollback_output rollback_tmp
  d290_load_state || d290_die "$d290_error"
  [[ $d290_arm_status == ARMED ]] || d290_die STATE_NOT_ARMED
  d290_close_rollback_pending=true
  trap d290_close_exit EXIT
  trap 'exit 130' HUP INT
  trap 'exit 143' TERM
  d290_check_close_repo
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  capture=$d290_capture_root/D290_01_PERSISTENT_${stamp}_${d290_baseline:0:12}/sanitized
  [[ ! -e ${capture%/sanitized} ]] || d290_die CAPTURE_COLLISION
  [[ -d $d290_root/captures && ! -L $d290_root/captures ]] || d290_die CAPTURE_PARENT_UNSAFE
  [[ ! -e $d290_capture_root && ! -L $d290_capture_root ]] ||
    [[ -d $d290_capture_root && ! -L $d290_capture_root ]] || d290_die CAPTURE_ROOT_UNSAFE
  install -d -o "$d290_operator_uid" -g "$d290_operator_gid" -m 0755 "$d290_capture_root"
  install -d -o "$d290_operator_uid" -g "$d290_operator_gid" -m 0700 "$capture"
  rollback_tmp=$(mktemp "${TMPDIR:-/tmp}/goodix-d290-rollback.XXXXXX")
  d290_close_tmp=$rollback_tmp
  set +e
  d290_collect_and_classify "$capture"
  collect_rc=$?
  d290_rollback_internal >"$rollback_tmp" 2>&1
  rollback_rc=$?
  d290_close_rollback_pending=false
  set -e
  rollback_output=$(<"$rollback_tmp")
  rm -f -- "$rollback_tmp"
  d290_close_tmp=
  printf '%s\n' "$rollback_output" | d290_sanitize >"$capture/rollback.log"
  {
    echo "D290_01_RESULT=${d290_classification:-AMBIGUOUS_REVIEW_REQUIRED}"
    echo "D290_01_EVIDENCE_COLLECTION_RETURN_CODE=$collect_rc"
    echo "D290_01_ROLLBACK_RETURN_CODE=$rollback_rc"
    echo "D290_01_HOST_PAM_RESTORED=$([[ $rollback_rc -eq 0 ]] && echo true || echo false)"
    echo "D290_01_STATE_REMOVED=$([[ $rollback_rc -eq 0 ]] && echo true || echo false)"
    echo D290_01_MAX_VERIFY_ACTIONS=1
    echo D290_01_MAX_PHYSICAL_CONTACTS=1
    echo D290_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_COUNT=0
  } >"$capture/summary.env"
  d290_finalize_capture "$capture"
  trap - EXIT HUP INT TERM
  printf '%s\n' "$rollback_output"
  echo "D290_01_CLASSIFICATION=${d290_classification:-AMBIGUOUS_REVIEW_REQUIRED}"
  echo "D290_01_CAPTURE=$capture"
  [[ $rollback_rc -eq 0 ]] || d290_die "${d290_error:-ROLLBACK_FAILED}"
  [[ $collect_rc -eq 0 && ${d290_classification:-} == PASS_MATCH_NEW_SESSION ]]
}

d290_operator_rollback () {
  local rollback_rc
  set +e
  d290_rollback_internal
  rollback_rc=$?
  set -e
  if [[ $rollback_rc -ne 0 ]]; then
    d290_die "${d290_error:-ROLLBACK_FAILED}"
  fi
}

d290_require_tools
[[ $# -eq 1 ]] || d290_die USAGE
case $1 in
  --operator-arm) d290_operator_arm ;;
  --operator-close) d290_operator_close ;;
  --operator-rollback) d290_operator_rollback ;;
  *) d290_die USAGE ;;
esac
