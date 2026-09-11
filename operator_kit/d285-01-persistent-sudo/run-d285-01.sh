#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

d285_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
d284_script_dir=$(CDPATH= cd -- "$d285_script_dir/../d284-01-transient-sudo-pilot" && pwd)
D284_LIBRARY_ONLY=true
# shellcheck source=../d284-01-transient-sudo-pilot/run-d284-01.sh
source "$d284_script_dir/run-d284-01.sh"
unset D284_LIBRARY_ONLY

operation=D285_01_PERSISTENT_SINGLE_USER_SUDO_INSTALL
d285_state=/etc/goodix-27c6-5125/d285-01.state
d285_state_dir=/etc/goodix-27c6-5125
d285_runtime_parent=/usr/local/lib64/goodix-27c6-5125
d285_wrapper=/usr/local/sbin/goodix-d285-01-fprintd
d285_dropin=/etc/systemd/system/fprintd.service.d/90-goodix-d285-01.conf
d285_pam=/etc/pam.d/goodix-d285-01-sudo
d285_sudoers=/etc/sudoers.d/90-goodix-d285-01
d285_result_prefix=/var/tmp/goodix-d285-01-results
d285_expected_authselect_before='local with-silent-lastlog with-mdns4 with-fingerprint'
d285_expected_authselect_active='local with-silent-lastlog with-mdns4'
d285_critical=(libfprint-driver Rockytkg
  reference/libfprint-fedora44-1.94.100/source
  reference/fprintd-fedora44-1.94.5
  analysis/D282 analysis/D283 analysis/D284 analysis/D285
  operator_kit/d282-01-fprintd-target
  operator_kit/d283-01-pam-dedicated
  operator_kit/d284-01-transient-sudo-pilot
  operator_kit/d285-01-persistent-sudo
  operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256
  "Goodix 27c6 5125 manuale tecnico.md")

d285_result=
d285_private=
d285_export=
d285_runtime=
d285_backup_name=
d285_user=
d285_user_storage=
d285_service_before=unknown
d285_install_started=false
d285_authselect_changed=false
d285_template_created=false
d285_template_relative=
d285_template_sha=
d285_install_committed=false
d285_rollback_ok=true
d285_offline_work=
d285_runtime_test_mode=false
d285_since=
d285_authselect_conf_before=
d285_system_auth_before=
d285_password_auth_before=
d285_fingerprint_auth_before=
d285_pam_sudo_before=
d285_system_lib_before=

refuse () {
  local reason=$1
  if [[ -n ${d285_result:-} && -f ${d285_result:-}/summary.env ]]; then
    sed -i 's/^D285_01_RESULT=.*/D285_01_RESULT=FAIL/' \
      "$d285_result/summary.env" 2>/dev/null || true
    sed -i "s/^D285_01_FAILURE_PHASE=.*/D285_01_FAILURE_PHASE=${reason}/" \
      "$d285_result/summary.env" 2>/dev/null || true
    echo "D285_01_FAILURE_PHASE=$reason" >>"$d285_result/operator.log" \
      2>/dev/null || true
  fi
  echo D285_01_GATE_REFUSED=true >&2
  echo "D285_01_REFUSAL_REASON=$reason" >&2
  echo AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false >&2
  echo "REAL_USB_ENUMERATION_ATTEMPTED=${real_usb_enumeration_attempted:-false}" >&2
  echo "REAL_SENSOR_ACCESSED=${real_sensor_accessed:-false}" >&2
  echo "LIVE_EXECUTION_PERFORMED=${live_execution_performed:-false}" >&2
  exit 3
}

d285_safe_user () {
  [[ $1 =~ ^[a-z_][a-z0-9_-]*$ ]]
}

d285_is_sha256 () {
  [[ ${1:-} =~ ^[0-9a-f]{64}$ ]]
}

d285_verify_baseline () {
  local baseline=$1
  is_sha "$baseline" || refuse INVALID_BASELINE
  [[ $(git -C "$root" branch --show-current) == development ]] ||
    refuse WRONG_BRANCH
  [[ $(git -C "$root" rev-parse HEAD) == "$baseline" ]] ||
    refuse HEAD_MISMATCH
  [[ $(git -C "$root" rev-parse origin/development) == "$baseline" ]] ||
    refuse ORIGIN_DEVELOPMENT_MISMATCH
  [[ -z $(git -C "$root" status --porcelain --untracked-files=all -- \
    "${d285_critical[@]}") ]] || refuse LIVE_CRITICAL_DIRTY
}

d285_validate_host_contract () {
  [[ $(rpm -q sudo) == sudo-1.9.17-8.p2.fc44.x86_64 ]] || refuse SUDO_NEVRA_DRIFT
  [[ $(rpm -q pam) == pam-1.7.2-2.fc44.x86_64 ]] || refuse PAM_NEVRA_DRIFT
  [[ $(rpm -q fprintd) == fprintd-1.94.5-5.fc44.x86_64 ]] ||
    refuse FPRINTD_NEVRA_DRIFT
  [[ $(rpm -q fprintd-pam) == fprintd-pam-1.94.5-5.fc44.x86_64 ]] ||
    refuse FPRINTD_PAM_NEVRA_DRIFT
  [[ $(rpm -q libfprint) == libfprint-1.94.100-1.fc44.x86_64 ]] ||
    refuse LIBFPRINT_NEVRA_DRIFT
  authselect check >/dev/null || refuse AUTHSELECT_INVALID
  command -v visudo >/dev/null || refuse HOST_TOOL_MISSING_visudo
  command -v restorecon >/dev/null || refuse HOST_TOOL_MISSING_restorecon
  command -v runuser >/dev/null || refuse HOST_TOOL_MISSING_runuser
}

d285_paths_absent () {
  local path
  for path in "$d285_state" "$d285_wrapper" "$d285_dropin" "$d285_pam" \
      "$d285_sudoers" "$d285_runtime"; do
    [[ ! -e $path && ! -L $path ]] || refuse INSTALL_COLLISION
  done
}

d285_validate_local_sbin_path () {
  local path=$1 expected=$2 link_target resolved
  if [[ -L $path ]]; then
    link_target=$(readlink -- "$path") || refuse PARENT_PATH_UNSAFE
    [[ $link_target == bin ]] || refuse PARENT_PATH_UNSAFE
    resolved=$(readlink -f -- "$path") || refuse PARENT_PATH_UNSAFE
    [[ $resolved == "$expected" ]] || refuse PARENT_PATH_UNSAFE
    [[ -d $expected && ! -L $expected ]] || refuse PARENT_PATH_UNSAFE
    return
  fi
  [[ -d $path ]] || refuse PARENT_PATH_UNSAFE
}

d285_validate_parent_paths () {
  local path
  for path in /usr/local/lib64 /etc /etc/pam.d \
      /etc/sudoers.d /etc/systemd/system /var/lib/fprint \
      /var/lib/authselect; do
    [[ -d $path && ! -L $path ]] || refuse PARENT_PATH_UNSAFE
  done
  d285_validate_local_sbin_path /usr/local/sbin /usr/local/bin
  for path in "$d285_runtime_parent" "$d285_state_dir" \
      "$(dirname "$d285_dropin")" /var/lib/authselect/backups; do
    [[ ! -e $path && ! -L $path ]] ||
      [[ -d $path && ! -L $path ]] || refuse D285_PARENT_PATH_UNSAFE
  done
}

d285_write_sudoers () {
  local user=$1 output=$2
  d285_safe_user "$user" || return 1
  printf 'Defaults:%s pam_service=goodix-d285-01-sudo\n' "$user" >"$output"
  chmod 0440 "$output"
}

d285_write_wrapper () {
  local runtime=$1 daemon_sha=$2 output=$3
  [[ $runtime == /usr/local/lib64/goodix-27c6-5125/d285-01-* ]] || return 1
  d285_is_sha256 "$daemon_sha" || return 1
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    "runtime='$runtime'" \
    "expected_daemon_sha='$daemon_sha'" \
    'actual_daemon_sha=$(sha256sum /usr/libexec/fprintd | awk '\''{print $1}'\'')' \
    '[[ $actual_daemon_sha == "$expected_daemon_sha" ]] || {' \
    '  echo D285_01_DAEMON_PROVENANCE_DRIFT=true >&2' \
    '  exit 126' \
    '}' \
    '[[ -d $runtime && ! -L $runtime ]] || exit 126' \
    '[[ -L $runtime/libfprint-2.so.2 && $(readlink "$runtime/libfprint-2.so.2") == libfprint-2.so.2.0.0 ]] || exit 126' \
    '[[ -L $runtime/libfprint-2.so && $(readlink "$runtime/libfprint-2.so") == libfprint-2.so.2 ]] || exit 126' \
    '(cd "$runtime" && sha256sum -c artifacts.sha256 >/dev/null) || {' \
    '  echo D285_01_RUNTIME_INTEGRITY_DRIFT=true >&2' \
    '  exit 126' \
    '}' \
    'exec env LD_LIBRARY_PATH="$runtime" FP_DRIVERS_ALLOWLIST=goodix_27c6_5125 /usr/libexec/fprintd' \
    >"$output"
  chmod 0755 "$output"
}

d285_write_dropin () {
  local output=$1
  printf '%s\n' \
    '[Service]' \
    'ExecStart=' \
    'ExecStart=/usr/local/sbin/goodix-d285-01-fprintd' \
    >"$output"
  chmod 0644 "$output"
}

d285_hash_host_config () {
  local output=$1 path
  : >"$output"
  for path in /etc/authselect/authselect.conf /etc/authselect/system-auth \
      /etc/authselect/password-auth /etc/authselect/fingerprint-auth \
      /etc/pam.d/sudo /etc/sudoers /usr/libexec/fprintd \
      /usr/lib64/libfprint-2.so.2.0.0; do
    [[ -f $path && ! -L $path ]] || return 1
    sha256sum "$path" >>"$output" || return 1
  done
}

d285_hash_for_path () {
  local manifest=$1 path=$2 value
  value=$(awk -v path="$path" '$2 == path {print $1}' "$manifest")
  [[ $(awk -v path="$path" '$2 == path {count++} END {print count+0}' "$manifest") -eq 1 ]] ||
    return 1
  d285_is_sha256 "$value" || return 1
  printf '%s\n' "$value"
}

d285_remove_result () {
  local result=$1
  [[ $result == /var/tmp/goodix-d285-01-results/* &&
     -d $result && ! -L $result ]] || return 1
  find "$result" -xdev -depth -delete
  rmdir "$d285_result_prefix" 2>/dev/null || true
}

d285_stage_persistent_runtime () {
  local candidate=$1 runtime=$2 name
  [[ -d $candidate && ! -L $candidate && -d $runtime && ! -L $runtime ]] ||
    return 1
  if [[ $d285_runtime_test_mode == true ]]; then
    [[ $runtime == /tmp/goodix-d285-01-offline.*/d285-01-* ]] || return 1
  else
    [[ $runtime == /usr/local/lib64/goodix-27c6-5125/d285-01-* ]] || return 1
  fi
  [[ -z $(find "$runtime" -mindepth 1 -maxdepth 1 -print -quit) ]] || return 1
  for name in libfprint-2.so.2.0.0 libgusb.so.2 \
    libopencv_core.so.413 libopencv_features2d.so.413 \
    libopencv_flann.so.413 libopencv_imgproc.so.413; do
    [[ -f $candidate/$name && ! -L $candidate/$name ]] || return 1
    install -m 0644 "$candidate/$name" "$runtime/$name" || return 1
  done
  install -m 0644 "$candidate/d282-01-artifacts.sha256" \
    "$runtime/artifacts.sha256" || return 1
  ln -s libfprint-2.so.2.0.0 "$runtime/libfprint-2.so.2" || return 1
  ln -s libfprint-2.so.2 "$runtime/libfprint-2.so" || return 1
  (cd "$runtime" && sha256sum -c artifacts.sha256 >/dev/null) || return 1
}

d285_remove_runtime () {
  local runtime=$1
  [[ -d $runtime && ! -L $runtime ]] || return 1
  if [[ $d285_runtime_test_mode == true ]]; then
    [[ $runtime == /tmp/goodix-d285-01-offline.*/d285-01-* ]] || return 1
  else
    [[ $runtime == /usr/local/lib64/goodix-27c6-5125/d285-01-* ]] || return 1
  fi
  find "$runtime" -xdev -depth -delete || return 1
  rmdir "$d285_runtime_parent" 2>/dev/null || true
}

d285_restore_service_state () {
  case $d285_service_before in
    active) systemctl start fprintd.service ;;
    inactive) systemctl stop fprintd.service ;;
    *) return 1 ;;
  esac
}

d285_remove_config_files () {
  local path
  for path in "$d285_sudoers" "$d285_pam" "$d285_dropin" "$d285_wrapper"; do
    if [[ -e $path || -L $path ]]; then
      [[ -f $path && ! -L $path ]] || return 1
      rm -f -- "$path" || return 1
    fi
  done
  visudo -cf /etc/sudoers >/dev/null || return 1
}

d285_remove_owned_backup () {
  local backup=/var/lib/authselect/backups/$d285_backup_name
  [[ $d285_backup_name == d285-01-[0-9T]*-[0-9a-f]* &&
     $backup == /var/lib/authselect/backups/d285-01-* ]] || return 1
  if [[ -d $backup && ! -L $backup ]]; then
    find "$backup" -xdev -depth -delete || return 1
  elif [[ -e $backup || -L $backup ]]; then
    return 1
  fi
}

d285_export_failure () {
  [[ -n $d285_result && -d $d285_result &&
     ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]] || return 0
  if [[ -n $d285_since ]]; then
    journalctl -u fprintd.service --since "$d285_since" --no-pager \
      >"$d285_private/failure-journal.raw" 2>&1 || true
    sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT .*$\)/\1/p; s/^.*\(GOODIX_SIGFM_.*$\)/\1/p' \
      "$d285_private/failure-journal.raw" | sort -u \
      >>"$d285_result/operator.log" 2>/dev/null || true
  fi
  d285_export=$(mktemp -d /tmp/goodix-d285-01-failure-export.XXXXXX) || return 1
  chmod 0700 "$d285_export" || return 1
  install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" \
    "$d285_result/operator.log" "$d285_export/operator.log" || return 1
  install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" \
    "$d285_result/summary.env" "$d285_export/summary.env" || return 1
  chown "$SUDO_UID:$SUDO_GID" "$d285_export" || return 1
  echo "EXPORT_DIRECTORY=$d285_export"
}

d285_rollback_install () {
  local exit_status=$? cleanup_status=0
  [[ $d285_install_committed == false ]] || return "$exit_status"
  [[ $d285_install_started == true ]] || return "$exit_status"
  set +e
  if [[ -n $d285_user_storage && (-e $d285_user_storage || -L $d285_user_storage) ]]; then
    if [[ $d285_template_created == true &&
          -d $d285_user_storage && ! -L $d285_user_storage &&
          $(find "$d285_user_storage" -type l | wc -l) -eq 0 &&
          $(find "$d285_user_storage" -type f | wc -l) -eq 1 &&
          -f $d285_user_storage/$d285_template_relative &&
          $(sha256sum "$d285_user_storage/$d285_template_relative" | awk '{print $1}') == "$d285_template_sha" ]]; then
      fprintd-delete "$d285_user" >/dev/null 2>&1 || cleanup_status=1
      [[ ! -e $d285_user_storage && ! -L $d285_user_storage ]] || cleanup_status=1
    else
      cleanup_status=1
    fi
  fi
  if [[ $cleanup_status -ne 0 ]]; then
    set -e
    if [[ -n $d285_result && -f $d285_result/summary.env ]]; then
      echo D285_01_FAILURE_ROLLBACK_COMPLETE=false >>"$d285_result/summary.env"
      echo D285_01_RECOVERY_REQUIRED=TEMPLATE_OWNERSHIP_OR_DELETE_REVIEW \
        >>"$d285_result/summary.env"
    fi
    echo D285_01_RECOVERY_REQUIRED=true >&2
    d285_export_failure || true
    return 1
  fi
  systemctl stop fprintd.service >/dev/null 2>&1 || cleanup_status=1
  d285_remove_config_files || cleanup_status=1
  if [[ $d285_authselect_changed == true ]]; then
    authselect enable-feature with-fingerprint >/dev/null 2>&1 || cleanup_status=1
  fi
  [[ -z $d285_runtime ]] || d285_remove_runtime "$d285_runtime" || cleanup_status=1
  [[ ! -e $d285_state ]] || rm -f -- "$d285_state" || cleanup_status=1
  rmdir "$d285_state_dir" 2>/dev/null || true
  systemctl daemon-reload >/dev/null 2>&1 || cleanup_status=1
  d285_restore_service_state >/dev/null 2>&1 || cleanup_status=1
  [[ -z $d285_backup_name ]] || d285_remove_owned_backup || cleanup_status=1
  set -e
  if [[ -n $d285_result && -f $d285_result/summary.env ]]; then
    echo "D285_01_FAILURE_ROLLBACK_COMPLETE=$([[ $cleanup_status -eq 0 ]] && echo true || echo false)" \
      >>"$d285_result/summary.env"
  fi
  if [[ $cleanup_status -ne 0 ]]; then
    echo D285_01_RECOVERY_REQUIRED=true >&2
    d285_export_failure || true
    return 1
  fi
  d285_export_failure || true
  d285_remove_result "$d285_result" || true
  d285_result=
  d285_private=
  return "$exit_status"
}

d285_write_state () {
  local baseline=$1 user=$2 template_relative=$3 template_sha=$4
  local daemon_sha pam_sha sudoers_sha wrapper_sha dropin_sha manifest_sha
  daemon_sha=$(sha256sum /usr/libexec/fprintd | awk '{print $1}')
  pam_sha=$(sha256sum "$d285_pam" | awk '{print $1}')
  sudoers_sha=$(sha256sum "$d285_sudoers" | awk '{print $1}')
  wrapper_sha=$(sha256sum "$d285_wrapper" | awk '{print $1}')
  dropin_sha=$(sha256sum "$d285_dropin" | awk '{print $1}')
  manifest_sha=$(sha256sum "$d285_runtime/artifacts.sha256" | awk '{print $1}')
  {
    echo D285_01_INSTALL_STATUS=ACTIVE
    echo "D285_01_BASELINE_SHA=$baseline"
    echo "D285_01_USER=$user"
    echo "D285_01_RUNTIME=$d285_runtime"
    echo "D285_01_AUTHSELECT_BEFORE=$d285_expected_authselect_before"
    echo "D285_01_AUTHSELECT_ACTIVE=$d285_expected_authselect_active"
    echo "D285_01_AUTHSELECT_BACKUP=$d285_backup_name"
    echo "D285_01_SERVICE_BEFORE=$d285_service_before"
    echo "D285_01_DAEMON_SHA256=$daemon_sha"
    echo "D285_01_PAM_SHA256=$pam_sha"
    echo "D285_01_SUDOERS_SHA256=$sudoers_sha"
    echo "D285_01_WRAPPER_SHA256=$wrapper_sha"
    echo "D285_01_DROPIN_SHA256=$dropin_sha"
    echo "D285_01_MANIFEST_SHA256=$manifest_sha"
    echo "D285_01_AUTHSELECT_CONF_BEFORE_SHA256=$d285_authselect_conf_before"
    echo "D285_01_SYSTEM_AUTH_BEFORE_SHA256=$d285_system_auth_before"
    echo "D285_01_PASSWORD_AUTH_BEFORE_SHA256=$d285_password_auth_before"
    echo "D285_01_FINGERPRINT_AUTH_BEFORE_SHA256=$d285_fingerprint_auth_before"
    echo "D285_01_PAM_SUDO_BEFORE_SHA256=$d285_pam_sudo_before"
    echo "D285_01_SYSTEM_LIBFPRINT_BEFORE_SHA256=$d285_system_lib_before"
    echo "D285_01_TEMPLATE_RELATIVE_PATH=$template_relative"
    echo "D285_01_TEMPLATE_SHA256=$template_sha"
  } >"$d285_state"
  chmod 0600 "$d285_state"
  restorecon "$d285_state"
}

d285_install () {
  local candidate=$1 user=$2 candidate_state baseline manifest observed_manifest
  local stamp since daemon_sha daemon_pid raw action_rc confirmation
  local authselect_now template_relative template_sha epoch_count retry_count
  local reopen_count reset_count clear_halt_count persistent_count match_count
  [[ $EUID -eq 0 ]] || refuse INSTALL_REQUIRES_ROOT
  d285_safe_user "$user" || refuse OPERATOR_USER_INVALID
  [[ ${SUDO_USER:-} == "$user" ]] || refuse OPERATOR_USER_MISMATCH
  candidate_state="$candidate/d282-01-candidate.state"
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -d $candidate &&
     ! -L $candidate && -f $candidate_state && ! -L $candidate_state ]] ||
    refuse CANDIDATE_INVALID
  baseline=$(state_value "$candidate_state" D282_01_BASELINE_SHA) ||
    refuse CANDIDATE_STATE_INVALID
  manifest=$(state_value "$candidate_state" D282_01_MANIFEST_SHA256) ||
    refuse CANDIDATE_STATE_INVALID
  d285_verify_baseline "$baseline"
  observed_manifest=$(sha256sum "$candidate/d282-01-artifacts.sha256" | awk '{print $1}')
  [[ $observed_manifest == "$manifest" ]] || refuse CANDIDATE_MANIFEST_DRIFT
  (cd "$candidate" && sha256sum -c d282-01-artifacts.sha256 >/dev/null) ||
    refuse CANDIDATE_ARTIFACT_DRIFT
  d285_validate_host_contract
  authselect_now=$(authselect current --raw) || refuse AUTHSELECT_UNREADABLE
  [[ $authselect_now == "$d285_expected_authselect_before" ]] ||
    refuse AUTHSELECT_INITIAL_TOPOLOGY_DRIFT
  getent passwd "$user" >/dev/null || refuse OPERATOR_USER_UNKNOWN
  sudo -U "$user" -l >/dev/null 2>&1 || refuse OPERATOR_NOT_SUDOER
  [[ $(count_goodix_targets /sys/bus/usb/devices) -eq 1 ]] ||
    refuse TARGET_CARDINALITY_NOT_ONE
  d285_user=$user
  d285_user_storage=/var/lib/fprint/$user
  [[ ! -e $d285_user_storage && ! -L $d285_user_storage ]] ||
    refuse PREEXISTING_USER_FPRINT_STORAGE
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  d285_runtime="$d285_runtime_parent/d285-01-$baseline"
  d285_backup_name="d285-01-${stamp}-${baseline:0:12}"
  d285_validate_parent_paths
  d285_paths_absent
  [[ ! -e /var/lib/authselect/backups/$d285_backup_name ]] ||
    refuse AUTHSELECT_BACKUP_COLLISION
  d285_service_before=$(systemctl is-active fprintd.service 2>/dev/null || true)
  [[ $d285_service_before == active || $d285_service_before == inactive ]] ||
    refuse FPRINTD_INITIAL_STATE_UNSAFE

  d285_result="$d285_result_prefix/${stamp}-${baseline:0:12}"
  d285_private="$d285_result/private"
  install -d -m 0700 "$d285_private"
  : >"$d285_result/operator.log"
  {
    echo D285_01_RESULT=FAIL_PENDING_INSTALL
    echo "D285_01_BASELINE_SHA=$baseline"
    echo D285_01_CONSUMER=SUDO_VALIDATE_PERSISTENT
    echo D285_01_FAILURE_PHASE=PRE_PERSISTENT_STAGING
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
  } >"$d285_result/summary.env"
  chmod 0600 "$d285_result/operator.log" "$d285_result/summary.env"
  d285_hash_host_config "$d285_private/host.before.sha256" ||
    refuse HOST_CONFIG_SNAPSHOT_FAILED
  d285_authselect_conf_before=$(d285_hash_for_path \
    "$d285_private/host.before.sha256" /etc/authselect/authselect.conf) ||
    refuse HOST_CONFIG_SNAPSHOT_PARSE_FAILED
  d285_system_auth_before=$(d285_hash_for_path \
    "$d285_private/host.before.sha256" /etc/authselect/system-auth) ||
    refuse HOST_CONFIG_SNAPSHOT_PARSE_FAILED
  d285_password_auth_before=$(d285_hash_for_path \
    "$d285_private/host.before.sha256" /etc/authselect/password-auth) ||
    refuse HOST_CONFIG_SNAPSHOT_PARSE_FAILED
  d285_fingerprint_auth_before=$(d285_hash_for_path \
    "$d285_private/host.before.sha256" /etc/authselect/fingerprint-auth) ||
    refuse HOST_CONFIG_SNAPSHOT_PARSE_FAILED
  d285_pam_sudo_before=$(d285_hash_for_path \
    "$d285_private/host.before.sha256" /etc/pam.d/sudo) ||
    refuse HOST_CONFIG_SNAPSHOT_PARSE_FAILED
  d285_system_lib_before=$(d285_hash_for_path \
    "$d285_private/host.before.sha256" /usr/lib64/libfprint-2.so.2.0.0) ||
    refuse HOST_CONFIG_SNAPSHOT_PARSE_FAILED
  systemctl cat fprintd.service >"$d285_private/unit.before" ||
    refuse UNIT_SNAPSHOT_FAILED

  d285_install_started=true
  trap d285_rollback_install EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  systemctl stop fprintd.service
  install -d -m 0755 "$d285_runtime_parent" "$d285_runtime" \
    "$(dirname "$d285_dropin")" "$d285_state_dir"
  d285_stage_persistent_runtime "$candidate" "$d285_runtime" ||
    refuse RUNTIME_INSTALL_FAILED
  daemon_sha=$(sha256sum /usr/libexec/fprintd | awk '{print $1}')
  d285_write_wrapper "$d285_runtime" "$daemon_sha" "$d285_wrapper" ||
    refuse WRAPPER_INSTALL_FAILED
  d285_write_dropin "$d285_dropin" || refuse DROPIN_INSTALL_FAILED
  install -m 0644 "$d285_script_dir/goodix-d285-01-sudo.pam" "$d285_pam"
  d285_write_sudoers "$user" "$d285_sudoers" || refuse SUDOERS_INSTALL_FAILED
  restorecon -RF "$d285_runtime_parent" "$d285_wrapper" "$d285_dropin" \
    "$d285_pam" "$d285_sudoers" "$d285_state_dir"
  visudo -cf /etc/sudoers >/dev/null || refuse SUDOERS_GLOBAL_INVALID
  authselect disable-feature with-fingerprint --backup="$d285_backup_name"
  d285_authselect_changed=true
  [[ $(authselect current --raw) == "$d285_expected_authselect_active" ]] ||
    refuse AUTHSELECT_SCOPE_REDUCTION_FAILED
  ! grep -F pam_fprintd.so /etc/authselect/system-auth >/dev/null ||
    refuse SYSTEM_AUTH_FINGERPRINT_STILL_ENABLED
  grep -Fx 'auth required pam_debug.so auth=authinfo_unavail' \
    /etc/authselect/fingerprint-auth >/dev/null ||
    refuse FINGERPRINT_AUTH_NOT_FAIL_CLOSED
  grep -Eq '^auth[[:space:]]+sufficient[[:space:]]+pam_fprintd\.so max-tries=1 timeout=45[[:space:]]*$' \
    "$d285_pam" || refuse D285_PAM_FINGERPRINT_DRIFT
  grep -Eq '^auth[[:space:]]+sufficient[[:space:]]+pam_unix\.so nullok[[:space:]]*$' \
    "$d285_pam" || refuse D285_PAM_PASSWORD_FALLBACK_MISSING

  since=$(date --iso-8601=seconds)
  d285_since=$since
  systemctl daemon-reload
  real_usb_enumeration_attempted=true
  real_sensor_accessed=true
  live_execution_performed=true
  systemctl start fprintd.service
  [[ $(count_goodix_targets /sys/bus/usb/devices) -eq 1 ]] ||
    refuse TARGET_CARDINALITY_CHANGED
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse DAEMON_PID_INVALID
  grep -F "$d285_runtime/libfprint-2.so.2.0.0" /proc/"$daemon_pid"/maps \
    >"$d285_private/maps" || refuse DAEMON_RUNTIME_MAP_MISSING
  tr '\0' '\n' </proc/"$daemon_pid"/environ >"$d285_private/environ"
  grep -Fx "LD_LIBRARY_PATH=$d285_runtime" "$d285_private/environ" >/dev/null ||
    refuse DAEMON_RUNTIME_ENVIRONMENT_DRIFT
  grep -Fx 'FP_DRIVERS_ALLOWLIST=goodix_27c6_5125' \
    "$d285_private/environ" >/dev/null || refuse DAEMON_ALLOWLIST_DRIFT

  echo 'PHASE_A=Enrollment persistente indice destro: otto contatti.'
  printf 'Confermare il dito enrollment digitando DESTRO: '
  read -r confirmation || refuse ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED
  [[ $confirmation == DESTRO ]] || refuse ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED
  echo ENROLL_OPERATOR_CONFIRMATION=DESTRO >>"$d285_result/operator.log"
  raw="$d285_private/enroll.raw"
  set +e
  timeout --signal=INT --kill-after=20s 1060s \
    fprintd-enroll -f right-index-finger "$user" 2>&1 | tee "$raw"
  action_rc=${PIPESTATUS[0]}
  set -e
  if [[ $action_rc -ne 0 ||
        $(grep -c '^Enroll result: enroll-completed$' "$raw") -ne 1 ||
        $(grep -c 'enroll-retry-' "$raw" || true) -ne 0 ]]; then
    refuse ENROLL_FAILED_OR_RETRY_OBSERVED
  fi
  [[ -d $d285_user_storage && ! -L $d285_user_storage &&
     $(find "$d285_user_storage" -type l | wc -l) -eq 0 &&
     $(find "$d285_user_storage" -type f | wc -l) -eq 1 ]] ||
    refuse TEMPLATE_OWNERSHIP_AMBIGUOUS
  template_relative=$(find "$d285_user_storage" -type f -printf '%P\n')
  [[ $template_relative =~ ^[A-Za-z0-9_.:+-]+/[A-Za-z0-9_.:+-]+/[0-9a-f]$ ]] ||
    refuse TEMPLATE_PATH_UNSAFE
  template_sha=$(sha256sum "$d285_user_storage/$template_relative" | awk '{print $1}')
  d285_is_sha256 "$template_sha" || refuse TEMPLATE_HASH_FAILED
  d285_template_relative=$template_relative
  d285_template_sha=$template_sha
  d285_template_created=true

  systemctl restart fprintd.service || refuse DAEMON_RESTART_AFTER_ENROLL_FAILED
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse DAEMON_PID_INVALID_AFTER_RESTART
  grep -F "$d285_runtime/libfprint-2.so.2.0.0" /proc/"$daemon_pid"/maps \
    >>"$d285_private/maps" || refuse DAEMON_RUNTIME_MAP_MISSING_AFTER_RESTART

  runuser -u "$user" -- sudo -K || refuse SUDO_TIMESTAMP_INVALIDATION_FAILED
  echo 'PHASE_B=Un solo sudo -v persistente con impronta; non digitare password.'
  printf 'Confermare il dito fisico digitando INDICE DESTRO: '
  read -r confirmation || refuse SUDO_PHYSICAL_FINGER_NOT_CONFIRMED
  [[ $confirmation == 'INDICE DESTRO' ]] || refuse SUDO_PHYSICAL_FINGER_NOT_CONFIRMED
  echo SUDO_OPERATOR_CONFIRMATION=INDICE_DESTRO >>"$d285_result/operator.log"
  raw="$d285_private/sudo.raw"
  set +e
  timeout --signal=INT --kill-after=20s 75s \
    runuser -u "$user" -- env -u SUDO_ASKPASS sudo -v 2>&1 | tee "$raw"
  action_rc=${PIPESTATUS[0]}
  set -e
  [[ $action_rc -eq 0 ]] || refuse SUDO_VALIDATE_FAILED
  runuser -u "$user" -- sudo -K || refuse SUDO_TIMESTAMP_FINAL_INVALIDATION_FAILED

  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$d285_private/journal.raw"
  grep GOODIX_D282_EPOCH_AUDIT "$d285_private/journal.raw" \
    >"$d285_private/audit.raw"
  grep GOODIX_SIGFM_MATCH_AUDIT "$d285_private/journal.raw" \
    >"$d285_private/matcher.raw"
  epoch_count=$(wc -l <"$d285_private/audit.raw")
  retry_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^(secure_retry|post_retry)=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$d285_private/audit.raw")
  reopen_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^reopen=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$d285_private/audit.raw")
  reset_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^reset=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$d285_private/audit.raw")
  clear_halt_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^clear_halt=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$d285_private/audit.raw")
  persistent_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^persistent=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$d285_private/audit.raw")
  match_count=$(grep -c 'event=outcome result=match' "$d285_private/matcher.raw" || true)
  [[ $epoch_count -eq 2 &&
     $(grep -c 'action=FPI_DEVICE_ACTION_ENROLL.*consumed=1' "$d285_private/audit.raw") -eq 1 &&
     $(grep -c 'action=FPI_DEVICE_ACTION_VERIFY.*consumed=1' "$d285_private/audit.raw") -eq 1 &&
     $(grep -c 'outstanding=0 drained=1 context_closed=1' "$d285_private/audit.raw") -eq 2 &&
     $retry_count -eq 0 && $reopen_count -eq 0 && $reset_count -eq 0 &&
     $clear_halt_count -eq 0 && $persistent_count -eq 0 && $match_count -eq 1 ]] ||
    refuse FINAL_LIVE_AUDIT_FAILED

  sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT .*$\)/\1/p; s/^.*\(GOODIX_SIGFM_.*$\)/\1/p' \
    "$d285_private/journal.raw" | sort -u >>"$d285_result/operator.log"
  d285_write_state "$baseline" "$user" "$template_relative" "$template_sha"
  d285_hash_host_config "$d285_private/host.active.sha256" ||
    refuse ACTIVE_HOST_CONFIG_SNAPSHOT_FAILED
  d285_export=$(mktemp -d /tmp/goodix-d285-01-install-export.XXXXXX)
  chmod 0700 "$d285_export"
  {
    echo D285_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
    echo "D285_01_BASELINE_SHA=$baseline"
    echo D285_01_INSTALL_STATUS=ACTIVE
    echo D285_01_CONSUMER=SUDO_VALIDATE_PERSISTENT
    echo D285_01_PAM_SERVICE=goodix-d285-01-sudo
    echo D285_01_PAM_MAX_TRIES=1
    echo D285_01_PASSWORD_FALLBACK_PRESENT=true
    echo D285_01_GLOBAL_AUTHSELECT_FINGERPRINT_DISABLED=true
    echo D285_01_SYSTEM_AUTH_PAM_FPRINTD_COUNT=0
    echo D285_01_ENROLL_ACTION_COUNT=1
    echo D285_01_VERIFY_ACTION_COUNT=1
    echo D285_01_DAEMON_RESTART_COUNT=1
    echo D285_01_OBSERVED_RETRY_COUNT=0
    echo D285_01_HIDDEN_REOPEN_COUNT=0
    echo D285_01_RESET_COUNT=0
    echo D285_01_CLEAR_HALT_COUNT=0
    echo D285_01_KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0
    echo D285_01_SIGFM_MATCH_OUTCOME=match
    echo D285_01_SUDO_VALIDATE_RETURN_CODE=0
    echo D285_01_RUNTIME_INTEGRITY_WRAPPER_ACTIVE=true
    echo D285_01_DAEMON_PROVENANCE_WRAPPER_ACTIVE=true
    echo D285_01_UNINSTALL_TEMPLATE_OWNERSHIP_PINNED=true
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
    echo REAL_USB_ENUMERATION_ATTEMPTED=true
    echo REAL_SENSOR_ACCESSED=true
    echo LIVE_EXECUTION_PERFORMED=true
    echo AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
  } >"$d285_result/summary.env"
  chmod 0600 "$d285_result/summary.env"
  install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" \
    "$d285_result/operator.log" "$d285_export/operator.log"
  install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" \
    "$d285_result/summary.env" "$d285_export/summary.env"
  chown "$SUDO_UID:$SUDO_GID" "$d285_export"
  d285_remove_result "$d285_result" || refuse RESULT_CLEANUP_FAILED
  d285_result=
  d285_private=
  d285_install_committed=true
  trap - EXIT INT TERM
  echo D285_01_INSTALL=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
  echo "EXPORT_DIRECTORY=$d285_export"
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
}

d285_verify_installed_file () {
  local path=$1 expected=$2
  [[ -f $path && ! -L $path && $(sha256sum "$path" | awk '{print $1}') == "$expected" ]]
}

d285_uninstall () {
  local user=$1 baseline runtime auth_before auth_active backup service_before
  local template_relative template_sha daemon_sha pam_sha sudoers_sha wrapper_sha
  local dropin_sha manifest_sha user_storage
  local authselect_conf_before system_auth_before password_auth_before
  local fingerprint_auth_before pam_sudo_before system_lib_before
  [[ $EUID -eq 0 ]] || refuse UNINSTALL_REQUIRES_ROOT
  d285_safe_user "$user" || refuse OPERATOR_USER_INVALID
  [[ ${SUDO_USER:-} == "$user" ]] || refuse OPERATOR_USER_MISMATCH
  [[ -f $d285_state && ! -L $d285_state ]] || refuse STATE_MISSING
  [[ $(stat -c %a "$d285_state") == 600 ]] || refuse STATE_MODE_DRIFT
  [[ $(state_value "$d285_state" D285_01_INSTALL_STATUS) == ACTIVE ]] || refuse STATE_INACTIVE
  baseline=$(state_value "$d285_state" D285_01_BASELINE_SHA) || refuse STATE_INVALID
  [[ $(state_value "$d285_state" D285_01_USER) == "$user" ]] || refuse STATE_USER_MISMATCH
  runtime=$(state_value "$d285_state" D285_01_RUNTIME) || refuse STATE_INVALID
  auth_before=$(state_value "$d285_state" D285_01_AUTHSELECT_BEFORE) || refuse STATE_INVALID
  auth_active=$(state_value "$d285_state" D285_01_AUTHSELECT_ACTIVE) || refuse STATE_INVALID
  backup=$(state_value "$d285_state" D285_01_AUTHSELECT_BACKUP) || refuse STATE_INVALID
  service_before=$(state_value "$d285_state" D285_01_SERVICE_BEFORE) || refuse STATE_INVALID
  daemon_sha=$(state_value "$d285_state" D285_01_DAEMON_SHA256) || refuse STATE_INVALID
  pam_sha=$(state_value "$d285_state" D285_01_PAM_SHA256) || refuse STATE_INVALID
  sudoers_sha=$(state_value "$d285_state" D285_01_SUDOERS_SHA256) || refuse STATE_INVALID
  wrapper_sha=$(state_value "$d285_state" D285_01_WRAPPER_SHA256) || refuse STATE_INVALID
  dropin_sha=$(state_value "$d285_state" D285_01_DROPIN_SHA256) || refuse STATE_INVALID
  manifest_sha=$(state_value "$d285_state" D285_01_MANIFEST_SHA256) || refuse STATE_INVALID
  authselect_conf_before=$(state_value "$d285_state" D285_01_AUTHSELECT_CONF_BEFORE_SHA256) || refuse STATE_INVALID
  system_auth_before=$(state_value "$d285_state" D285_01_SYSTEM_AUTH_BEFORE_SHA256) || refuse STATE_INVALID
  password_auth_before=$(state_value "$d285_state" D285_01_PASSWORD_AUTH_BEFORE_SHA256) || refuse STATE_INVALID
  fingerprint_auth_before=$(state_value "$d285_state" D285_01_FINGERPRINT_AUTH_BEFORE_SHA256) || refuse STATE_INVALID
  pam_sudo_before=$(state_value "$d285_state" D285_01_PAM_SUDO_BEFORE_SHA256) || refuse STATE_INVALID
  system_lib_before=$(state_value "$d285_state" D285_01_SYSTEM_LIBFPRINT_BEFORE_SHA256) || refuse STATE_INVALID
  template_relative=$(state_value "$d285_state" D285_01_TEMPLATE_RELATIVE_PATH) || refuse STATE_INVALID
  template_sha=$(state_value "$d285_state" D285_01_TEMPLATE_SHA256) || refuse STATE_INVALID
  is_sha "$baseline" && d285_is_sha256 "$daemon_sha" &&
    d285_is_sha256 "$pam_sha" && d285_is_sha256 "$sudoers_sha" &&
    d285_is_sha256 "$wrapper_sha" && d285_is_sha256 "$dropin_sha" &&
    d285_is_sha256 "$manifest_sha" && d285_is_sha256 "$template_sha" &&
    d285_is_sha256 "$authselect_conf_before" &&
    d285_is_sha256 "$system_auth_before" &&
    d285_is_sha256 "$password_auth_before" &&
    d285_is_sha256 "$fingerprint_auth_before" &&
    d285_is_sha256 "$pam_sudo_before" && d285_is_sha256 "$system_lib_before" ||
    refuse STATE_HASH_INVALID
  [[ $runtime == /usr/local/lib64/goodix-27c6-5125/d285-01-$baseline &&
     $auth_before == "$d285_expected_authselect_before" &&
     $auth_active == "$d285_expected_authselect_active" &&
     $backup == d285-01-[0-9T]*-[0-9a-f]* &&
     ($service_before == active || $service_before == inactive) &&
     $template_relative =~ ^[A-Za-z0-9_.:+-]+/[A-Za-z0-9_.:+-]+/[0-9a-f]$ ]] ||
    refuse STATE_SEMANTIC_DRIFT
  d285_validate_host_contract
  [[ $(authselect current --raw) == "$auth_active" ]] || refuse AUTHSELECT_ACTIVE_DRIFT
  [[ $(sha256sum /usr/libexec/fprintd | awk '{print $1}') == "$daemon_sha" ]] ||
    refuse DAEMON_PROVENANCE_DRIFT
  d285_verify_installed_file "$d285_pam" "$pam_sha" || refuse PAM_FILE_DRIFT
  d285_verify_installed_file "$d285_sudoers" "$sudoers_sha" || refuse SUDOERS_FILE_DRIFT
  d285_verify_installed_file "$d285_wrapper" "$wrapper_sha" || refuse WRAPPER_FILE_DRIFT
  d285_verify_installed_file "$d285_dropin" "$dropin_sha" || refuse DROPIN_FILE_DRIFT
  [[ -d $runtime && ! -L $runtime &&
     $(sha256sum "$runtime/artifacts.sha256" | awk '{print $1}') == "$manifest_sha" ]] ||
    refuse RUNTIME_MANIFEST_DRIFT
  (cd "$runtime" && sha256sum -c artifacts.sha256 >/dev/null) ||
    refuse RUNTIME_ARTIFACT_DRIFT
  user_storage=/var/lib/fprint/$user
  [[ -d $user_storage && ! -L $user_storage &&
     $(find "$user_storage" -type l | wc -l) -eq 0 &&
     $(find "$user_storage" -type f | wc -l) -eq 1 &&
     -f $user_storage/$template_relative &&
     $(sha256sum "$user_storage/$template_relative" | awk '{print $1}') == "$template_sha" ]] ||
    refuse TEMPLATE_OWNERSHIP_DRIFT_HUMAN_REVIEW_REQUIRED
  [[ $(count_goodix_targets /sys/bus/usb/devices) -eq 1 ]] ||
    refuse TARGET_CARDINALITY_NOT_ONE

  real_usb_enumeration_attempted=true
  real_sensor_accessed=true
  live_execution_performed=true
  systemctl start fprintd.service
  fprintd-delete "$user"
  [[ ! -e $user_storage ]] || refuse TEMPLATE_DELETE_INCOMPLETE
  systemctl stop fprintd.service
  d285_remove_config_files || refuse CONFIG_REMOVE_FAILED
  authselect enable-feature with-fingerprint
  [[ $(authselect current --raw) == "$auth_before" ]] ||
    refuse AUTHSELECT_RESTORE_FAILED
  [[ $(sha256sum /etc/authselect/authselect.conf | awk '{print $1}') == "$authselect_conf_before" &&
     $(sha256sum /etc/authselect/system-auth | awk '{print $1}') == "$system_auth_before" &&
     $(sha256sum /etc/authselect/password-auth | awk '{print $1}') == "$password_auth_before" &&
     $(sha256sum /etc/authselect/fingerprint-auth | awk '{print $1}') == "$fingerprint_auth_before" &&
     $(sha256sum /etc/pam.d/sudo | awk '{print $1}') == "$pam_sudo_before" &&
     $(sha256sum /usr/lib64/libfprint-2.so.2.0.0 | awk '{print $1}') == "$system_lib_before" ]] ||
    refuse HOST_CONFIG_EXACT_RESTORE_FAILED
  d285_runtime=$runtime
  d285_remove_runtime "$runtime" || refuse RUNTIME_REMOVE_FAILED
  rm -f -- "$d285_state"
  rmdir "$d285_state_dir" 2>/dev/null || true
  d285_backup_name=$backup
  d285_remove_owned_backup || refuse AUTHSELECT_BACKUP_REMOVE_FAILED
  systemctl daemon-reload
  d285_service_before=$service_before
  d285_restore_service_state || refuse SERVICE_RESTORE_FAILED
  visudo -cf /etc/sudoers >/dev/null || refuse SUDOERS_FINAL_INVALID
  authselect check >/dev/null || refuse AUTHSELECT_FINAL_INVALID
  echo D285_01_UNINSTALL=PASS
  echo D285_01_TEMPLATE_DELETE=PASS_OWNERSHIP_PINNED
  echo D285_01_AUTHSELECT_RESTORED=true
  echo D285_01_PERSISTENT_FILES_REMOVED=true
}

operator_install () {
  local rpm_dir=$1 baseline user confirmation transcript output rc export
  [[ $EUID -ne 0 ]] || refuse OPERATOR_INSTALL_MUST_BE_UNPRIVILEGED
  user=$(id -un) || refuse OPERATOR_USER_UNKNOWN
  d285_safe_user "$user" || refuse OPERATOR_USER_INVALID
  baseline=$(git -C "$root" rev-parse HEAD) || refuse BASELINE_UNREADABLE
  d285_verify_baseline "$baseline"
  trap cleanup_prepared_candidate EXIT
  prepare_candidate "$baseline" "$rpm_dir"
  echo
  echo 'D285/01 installa un runtime persistente e modifica authselect, PAM, sudoers e systemd.'
  echo 'Esegue 8 contatti enrollment + 1 sudo -v. Password fallback sempre presente.'
  echo 'Non bloccare lo schermo, non usare altri consumer fprintd e non digitare password nel test.'
  printf 'Digitare INSTALLA D285 per avviare la singola installazione: '
  read -r confirmation
  [[ $confirmation == 'INSTALLA D285' ]] || refuse OPERATOR_CANCELLED
  transcript=$(mktemp /tmp/goodix-d285-01-install.XXXXXX)
  chmod 0600 "$transcript"
  set +e
  sudo "$d285_script_dir/run-d285-01.sh" --install "$prepared_candidate" \
    --user "$user" 2>&1 | tee "$transcript"
  rc=${PIPESTATUS[0]}
  set -e
  export=$(sed -n 's/^EXPORT_DIRECTORY=//p' "$transcript" | tail -n 1)
  if [[ $rc -eq 0 && $export == /tmp/goodix-d285-01-install-export.* &&
        -d $export && ! -L $export ]]; then
    install -m 0600 "$transcript" "$export/terminal-transcript.log"
    sha256sum "$export/operator.log" "$export/summary.env" \
      "$export/terminal-transcript.log"
  fi
  cleanup_prepared_candidate
  prepared_candidate=
  echo "TERMINAL_TRANSCRIPT=$transcript"
  trap - EXIT
  return "$rc"
}

operator_uninstall () {
  local user confirmation
  [[ $EUID -ne 0 ]] || refuse OPERATOR_UNINSTALL_MUST_BE_UNPRIVILEGED
  user=$(id -un) || refuse OPERATOR_USER_UNKNOWN
  echo 'D285/01 rimuoverà il solo template ownership-pinned e tutta la configurazione D285.'
  printf 'Digitare RIMUOVI D285 per avviare il rollback persistente: '
  read -r confirmation
  [[ $confirmation == 'RIMUOVI D285' ]] || refuse OPERATOR_CANCELLED
  sudo "$d285_script_dir/run-d285-01.sh" --uninstall --user "$user"
}

cleanup_d285_offline_work () {
  local work=$d285_offline_work
  [[ -z $work ]] && return 0
  [[ $work == /tmp/goodix-d285-01-offline.* && -d $work && ! -L $work ]] || {
    echo "D285_01_OFFLINE_CLEANUP_REFUSED=$work" >&2
    return 1
  }
  find "$work" -xdev -depth -delete
  d285_offline_work=
}

offline_preflight () {
  local rpm_dir=$1 baseline work candidate runtime wrapper dropin sudoers daemon_sha
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  bash -n "$d285_script_dir/run-d285-01.sh"
  (cd "$root" && python3 -m unittest -v analysis.D285.test_d285_01_offline_contract)
  baseline=$(git -C "$root" rev-parse HEAD)
  work=$(mktemp -d /tmp/goodix-d285-01-offline.XXXXXX)
  d285_offline_work=$work
  trap cleanup_d285_offline_work EXIT
  candidate=$work/candidate
  runtime=$work/runtime
  install -d -m 0700 "$candidate" "$runtime"
  build_candidate "$root" "$candidate" "$rpm_dir"
  abi_preflight "$candidate"
  (cd "$candidate" && sha256sum libfprint-2.so.2.0.0 libgusb.so.2 \
    libopencv_core.so.413 libopencv_features2d.so.413 \
    libopencv_flann.so.413 libopencv_imgproc.so.413 >d282-01-artifacts.sha256)
  d285_runtime_parent=$work
  runtime="$work/d285-01-$baseline"
  install -d -m 0700 "$runtime"
  d285_runtime_test_mode=true
  d285_stage_persistent_runtime "$candidate" "$runtime"
  (cd "$runtime" && sha256sum -c artifacts.sha256 >/dev/null)
  wrapper=$work/goodix-d285-01-fprintd
  dropin=$work/90-goodix-d285-01.conf
  sudoers=$work/90-goodix-d285-01
  daemon_sha=$(sha256sum /usr/libexec/fprintd | awk '{print $1}')
  d285_write_wrapper "/usr/local/lib64/goodix-27c6-5125/d285-01-$baseline" \
    "$daemon_sha" "$wrapper"
  d285_write_dropin "$dropin"
  d285_write_sudoers goodix_test "$sudoers"
  visudo -cf "$sudoers" >/dev/null
  grep -F 'pam_debug.so auth=authinfo_unavail' \
    <(authselect test local -a with-silent-lastlog with-mdns4) >/dev/null
  echo D285_01_OFFLINE_PREFLIGHT=PASS
  echo D285_01_PERSISTENT_RUNTIME_BUILD=PASS_OFFLINE
  echo D285_01_FPRINTD_ABI_CLOSURE=PASS_OFFLINE
  echo D285_01_AUTHSELECT_SCOPE_REDUCTION=PASS_OFFLINE_RENDERED
  echo D285_01_PASSWORD_FALLBACK_PRESENT=true
  echo D285_01_INSTALL_LIVE_READINESS=HUMAN_REQUIRED_OPERATOR_RUN
  echo D285_01_UNINSTALL_PATH=OWNERSHIP_PINNED_FAIL_CLOSED
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo LIVE_EXECUTION_PERFORMED=false
  trap - EXIT
  cleanup_d285_offline_work
}

if [[ ${D285_LIBRARY_ONLY:-false} != true ]]; then
  case ${1:-} in
    --offline-preflight)
      [[ $# -eq 2 ]] || refuse USAGE
      offline_preflight "$2"
      ;;
    --operator-install)
      [[ $# -eq 2 ]] || refuse USAGE
      operator_install "$2"
      ;;
    --operator-uninstall)
      [[ $# -eq 1 ]] || refuse USAGE
      operator_uninstall
      ;;
    --install)
      [[ $# -eq 4 && $3 == --user ]] || refuse USAGE
      d285_install "$2" "$4"
      ;;
    --uninstall)
      [[ $# -eq 3 && $2 == --user ]] || refuse USAGE
      d285_uninstall "$3"
      ;;
    *)
      echo "Uso: $0 --offline-preflight <opencv-rpm-dir> | --operator-install <opencv-rpm-dir> | --operator-uninstall" >&2
      exit 2
      ;;
  esac
fi
