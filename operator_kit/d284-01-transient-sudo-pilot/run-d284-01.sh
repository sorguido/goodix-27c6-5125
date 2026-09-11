#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

d284_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
d283_script_dir=$(CDPATH= cd -- "$d284_script_dir/../d283-01-pam-dedicated" && pwd)
D283_LIBRARY_ONLY=true
# shellcheck source=../d283-01-pam-dedicated/run-d283-01.sh
source "$d283_script_dir/run-d283-01.sh"
unset D283_LIBRARY_ONLY

live_result_prefix=D284_01
d284_critical=(libfprint-driver Rockytkg
  reference/libfprint-fedora44-1.94.100/source
  reference/fprintd-fedora44-1.94.5
  analysis/D282 analysis/D283 analysis/D284
  operator_kit/d282-01-fprintd-target
  operator_kit/d283-01-pam-dedicated
  operator_kit/d284-01-transient-sudo-pilot
  captures/D283_01
  operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256
  "Goodix 27c6 5125 manuale tecnico.md")

d284_pam_path=
d284_sudoers_path=
d284_pam_installed=false
d284_sudoers_installed=false
d284_config_before_ready=false
d284_config_rollback=true
d284_timestamp_invalidated=false
d284_cleanup_test_mode=false
d284_user=
d284_offline_work=

refuse () {
  local reason=$1
  if [[ -n ${live_result:-} && -f ${live_result:-}/summary.env ]]; then
    sed -i 's/^D284_01_RESULT=.*/D284_01_RESULT=FAIL_GATE_REFUSED/' \
      "$live_result/summary.env" || true
    sed -i "s/^D284_01_FAILURE_PHASE=.*/D284_01_FAILURE_PHASE=GATE_${reason}/" \
      "$live_result/summary.env" || true
    {
      echo "D284_01_FAILURE_PHASE=GATE_$reason"
      echo D284_01_FAILURE_RETURN_CODE=3
    } >>"$live_result/operator.log" 2>/dev/null || true
  fi
  echo D284_01_GATE_REFUSED=true >&2
  echo "D284_01_REFUSAL_REASON=$reason" >&2
  echo AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false >&2
  echo "REAL_USB_ENUMERATION_ATTEMPTED=${real_usb_enumeration_attempted:-false}" >&2
  echo "REAL_SENSOR_ACCESSED=${real_sensor_accessed:-false}" >&2
  echo "LIVE_EXECUTION_PERFORMED=${live_execution_performed:-false}" >&2
  exit 3
}

verify_d284_baseline () {
  local baseline=$1
  is_sha "$baseline" || refuse INVALID_BASELINE
  [[ $(git -C "$root" branch --show-current) == development ]] ||
    refuse WRONG_BRANCH
  [[ $(git -C "$root" rev-parse HEAD) == "$baseline" ]] ||
    refuse HEAD_MISMATCH
  [[ $(git -C "$root" rev-parse origin/development) == "$baseline" ]] ||
    refuse ORIGIN_DEVELOPMENT_MISMATCH
  [[ -z $(git -C "$root" status --porcelain --untracked-files=all -- \
    "${d284_critical[@]}") ]] || refuse LIVE_CRITICAL_DIRTY
}

stage_d284_runtime () {
  local candidate=$1 runtime=$2 name
  [[ -d $candidate && ! -L $candidate && -d $runtime && ! -L $runtime ]] ||
    return 1
  [[ $runtime == /run/goodix-d284-01/* ||
     $runtime == /tmp/goodix-d284-01-offline.*/* ]] || return 1
  [[ -z $(find "$runtime" -mindepth 1 -maxdepth 1 -print -quit) ]] || return 1
  for name in libfprint-2.so.2.0.0 libgusb.so.2 \
    libopencv_core.so.413 libopencv_features2d.so.413 \
    libopencv_flann.so.413 libopencv_imgproc.so.413; do
    [[ -f $candidate/$name && ! -L $candidate/$name ]] || return 1
    install -m 0600 "$candidate/$name" "$runtime/$name" || return 1
  done
  ln -s libfprint-2.so.2.0.0 "$runtime/libfprint-2.so.2" || return 1
  ln -s libfprint-2.so.2 "$runtime/libfprint-2.so" || return 1
}

hash_d284_host_config () {
  local output=$1 path
  : >"$output" || return 1
  for path in /etc/sudoers /etc/pam.d/sudo /etc/authselect/authselect.conf \
    /etc/authselect/system-auth /etc/authselect/password-auth \
    /etc/authselect/fingerprint-auth; do
    [[ -f $path && ! -L $path ]] || return 1
    sha256sum "$path" >>"$output" || return 1
  done
}

d284_override_paths_safe () {
  if [[ $d284_cleanup_test_mode == true ]]; then
    [[ ($d284_pam_path == /tmp/goodix-d284-cleanup-test.*/* &&
        $d284_sudoers_path == /tmp/goodix-d284-cleanup-test.*/*) ||
       ($d284_pam_path == /tmp/goodix-d284-01-offline.*/cleanup/goodix-d284-01-sudo &&
        $d284_sudoers_path == /tmp/goodix-d284-01-offline.*/cleanup/90-goodix-d284-01-pilot) ]]
  else
    [[ $d284_pam_path == /etc/pam.d/goodix-d284-01-sudo &&
       $d284_sudoers_path == /etc/sudoers.d/90-goodix-d284-01-pilot ]]
  fi
}

remove_d284_overrides () {
  d284_override_paths_safe || return 1
  if [[ $d284_sudoers_installed == true ]]; then
    rm -f -- "$d284_sudoers_path" || return 1
    d284_sudoers_installed=false
  fi
  if [[ $d284_pam_installed == true ]]; then
    rm -f -- "$d284_pam_path" || return 1
    d284_pam_installed=false
  fi
  if [[ $d284_cleanup_test_mode != true ]]; then
    visudo -cf /etc/sudoers >/dev/null || return 1
  fi
  [[ ! -e $d284_pam_path && ! -L $d284_pam_path &&
     ! -e $d284_sudoers_path && ! -L $d284_sudoers_path ]] || return 1
}

capture_d284_failure () {
  local phase=$1 return_code=$2 raw_file=$3 since=$4 baseline=$5 stamp=$6
  local user=$7 journal_file="$live_private/failure-journal.raw"
  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$journal_file" 2>&1 || true
  if [[ -f $live_result/summary.env ]]; then
    sed -i "s/^D284_01_RESULT=.*/D284_01_RESULT=FAIL_${phase}/" \
      "$live_result/summary.env"
    sed -i "s/^D284_01_FAILURE_PHASE=.*/D284_01_FAILURE_PHASE=${phase}/" \
      "$live_result/summary.env"
  fi
  {
    echo "D284_01_FAILURE_PHASE=$phase"
    echo "D284_01_FAILURE_RETURN_CODE=$return_code"
    if [[ -f $raw_file ]]; then
      sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" \
        "$raw_file"
    fi
    grep -E 'GOODIX_D282_EPOCH_AUDIT|GOODIX_SIGFM_|fprintd|pam_fprintd|sudo' \
      "$journal_file" | tail -n 240 |
      sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" || true
  } >>"$live_result/operator.log"
}

cleanup_d284 () {
  local exit_status=$? after_config
  trap - EXIT INT TERM
  set +e
  [[ $exit_status -eq 0 ]] || live_run_return_code=$exit_status
  if [[ -n $d284_user ]]; then
    if runuser -u "$d284_user" -- sudo -K >/dev/null 2>&1; then
      d284_timestamp_invalidated=true
    else
      d284_timestamp_invalidated=false
      d284_config_rollback=false
    fi
  fi
  remove_d284_overrides || d284_config_rollback=false
  if [[ $d284_config_before_ready == true ]]; then
    after_config="$live_private/host-config.after.sha256"
    hash_d284_host_config "$after_config" || d284_config_rollback=false
    cmp -s "$live_private/host-config.before.sha256" "$after_config" ||
      d284_config_rollback=false
  fi
  cleanup_live
  if [[ -n ${live_result:-} && -f $live_result/summary.env ]]; then
    echo "D284_01_PAM_SUDOERS_ROLLBACK=$d284_config_rollback" \
      >>"$live_result/summary.env"
    echo "D284_01_SUDO_TIMESTAMP_INVALIDATED=$d284_timestamp_invalidated" \
      >>"$live_result/summary.env"
    if [[ $d284_config_rollback != true ]]; then
      sed -i 's/^D284_01_RESULT=.*/D284_01_RESULT=FAIL_ROLLBACK/' \
        "$live_result/summary.env"
      sed -i 's/^ROLLBACK_COMPLETE=.*/ROLLBACK_COMPLETE=false/' \
        "$live_result/summary.env"
      echo "RECOVERY_REQUIRED=Rimuovere gli override D284 e verificare sudoers." >&2
    fi
  fi
  if [[ $d284_config_rollback != true ]] ||
      grep -Fx 'ROLLBACK_COMPLETE=false' "$live_result/summary.env" >/dev/null 2>&1; then
    [[ $exit_status -ne 0 ]] || exit_status=1
  fi
  exit "$exit_status"
}

write_d284_sudoers () {
  local user=$1 output=$2
  [[ $user =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || return 1
  printf 'Defaults:%s pam_service=goodix-d284-01-sudo\n' "$user" >"$output"
  chmod 0440 "$output"
}

install_d284_overrides () {
  local user=$1 temp
  d284_override_paths_safe || return 1
  [[ ! -e $d284_pam_path && ! -L $d284_pam_path &&
     ! -e $d284_sudoers_path && ! -L $d284_sudoers_path ]] || return 1
  install -m 0644 "$d284_script_dir/goodix-d284-01-sudo.pam" \
    "$d284_pam_path" || return 1
  d284_pam_installed=true
  temp="$live_private/90-goodix-d284-01-pilot"
  write_d284_sudoers "$user" "$temp" || return 1
  visudo -cf "$temp" >/dev/null || return 1
  install -m 0440 "$temp" "$d284_sudoers_path" || return 1
  d284_sudoers_installed=true
  if [[ $validated_selinux_enforcement == Enforcing ]]; then
    restorecon "$d284_pam_path" "$d284_sudoers_path" || return 1
  fi
  visudo -cf /etc/sudoers >/dev/null || return 1
}

run_d284_live () {
  local candidate=$1 user=$2 state baseline manifest observed_manifest
  local stamp since daemon_pid raw action_rc confirmation target_count
  local epoch_count enroll_count verify_count cleanup_epoch_count consumed_count
  local attempts retry_count reopen_count reset_count clear_halt_count
  local persistent_count extract_count matcher_start_count matcher_match_count
  local matcher_outcome_count matcher_error_count observed_max_score
  local matched_sample comparison_count stored authselect_raw

  live_result=
  live_private=
  live_runtime=
  live_owned=
  live_storage_root=/var/lib/fprint
  live_dropin=/run/systemd/system/fprintd.service.d/90-goodix-d284-01.conf
  live_service_before=unknown
  live_unit_before=
  live_system_library=
  live_system_library_before=
  live_storage_existed=false
  live_before_inventory_ready=false
  live_unit_before_ready=false
  live_system_library_before_ready=false
  live_staging_started=false
  live_service_touched=false
  live_cleanup_armed=false
  live_cleanup_test_mode=false
  live_run_return_code=1
  live_result_prefix=D284_01
  live_current_direct_mode=true
  staging_probe_mode=true
  staging_probe_execution_performed=false
  real_usb_enumeration_attempted=false
  real_sensor_accessed=false
  live_execution_performed=false
  d284_pam_path=/etc/pam.d/goodix-d284-01-sudo
  d284_sudoers_path=/etc/sudoers.d/90-goodix-d284-01-pilot
  d284_pam_installed=false
  d284_sudoers_installed=false
  d284_config_before_ready=false
  d284_config_rollback=true
  d284_timestamp_invalidated=false
  d284_cleanup_test_mode=false
  d284_user=$user

  [[ $EUID -eq 0 ]] || refuse LIVE_REQUIRES_ROOT
  state="$candidate/d282-01-candidate.state"
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -f $state &&
     ! -L $candidate ]] || refuse CANDIDATE_INVALID
  baseline=$(state_value "$state" D282_01_BASELINE_SHA) || refuse CANDIDATE_STATE
  manifest=$(state_value "$state" D282_01_MANIFEST_SHA256) || refuse CANDIDATE_STATE
  verify_d284_baseline "$baseline"
  observed_manifest=$(sha256sum "$candidate/d282-01-artifacts.sha256" |
    awk '{print $1}')
  [[ $observed_manifest == "$manifest" ]] || refuse MANIFEST_DRIFT
  (cd "$candidate" && sha256sum -c d282-01-artifacts.sha256) ||
    refuse ARTIFACT_DRIFT
  [[ $user =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || refuse OPERATOR_USER_INVALID
  getent passwd "$user" >/dev/null || refuse OPERATOR_USER_UNKNOWN
  [[ ${SUDO_USER:-$user} == "$user" ]] || refuse OPERATOR_USER_MISMATCH
  command -v visudo >/dev/null || refuse HOST_TOOL_MISSING_visudo
  command -v runuser >/dev/null || refuse HOST_TOOL_MISSING_runuser
  [[ $(rpm -q sudo) == sudo-1.9.17-8.p2.fc44.x86_64 ]] || refuse SUDO_NEVRA_DRIFT
  [[ $(rpm -q pam) == pam-1.7.2-2.fc44.x86_64 ]] || refuse PAM_NEVRA_DRIFT
  [[ $(rpm -q fprintd) == fprintd-1.94.5-5.fc44.x86_64 ]] ||
    refuse FPRINTD_NEVRA_DRIFT
  [[ $(rpm -q fprintd-pam) == fprintd-pam-1.94.5-5.fc44.x86_64 ]] ||
    refuse FPRINTD_PAM_NEVRA_DRIFT
  authselect check >/dev/null || refuse AUTHSELECT_INVALID
  authselect_raw=$(authselect current --raw) || refuse AUTHSELECT_UNREADABLE
  [[ $authselect_raw == 'local with-silent-lastlog with-mdns4 with-fingerprint' ]] ||
    refuse AUTHSELECT_PROFILE_DRIFT
  grep -Eq '^auth[[:space:]]+sufficient[[:space:]]+pam_fprintd\.so[[:space:]]*$' \
    /etc/authselect/system-auth || refuse SYSTEM_AUTH_FPRINT_CONTRACT_DRIFT
  grep -Eq '^auth[[:space:]]+sufficient[[:space:]]+pam_unix\.so nullok[[:space:]]*$' \
    /etc/authselect/system-auth || refuse SYSTEM_AUTH_PASSWORD_FALLBACK_MISSING
  grep -Eq '^auth[[:space:]]+sufficient[[:space:]]+pam_fprintd\.so max-tries=1 timeout=45[[:space:]]*$' \
    "$d284_script_dir/goodix-d284-01-sudo.pam" || refuse PILOT_PAM_DRIFT
  grep -Eq '^auth[[:space:]]+sufficient[[:space:]]+pam_unix\.so nullok[[:space:]]*$' \
    "$d284_script_dir/goodix-d284-01-sudo.pam" || refuse PILOT_PASSWORD_FALLBACK_MISSING
  validate_live_tooling

  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  live_result="/var/tmp/goodix-d284-01-results/${stamp}-${baseline:0:12}"
  echo "RISULTATI_PRIVATI=$live_result"
  live_runtime="/run/goodix-d284-01/${stamp}-${baseline:0:12}"
  live_owned="$live_storage_root/.goodix-d284-01-${stamp}-${baseline:0:12}"
  [[ ! -e $live_runtime && ! -e $live_owned && ! -e $live_dropin &&
     ! -e $d284_pam_path && ! -e $d284_sudoers_path ]] || refuse STAGING_COLLISION
  live_private="$live_result/private"
  install -d -m 0700 "$live_private" || refuse RESULT_DIRECTORY_CREATE_FAILED
  {
    echo D284_01_RESULT=FAIL_PENDING_AUDIT
    echo "D284_01_BASELINE_SHA=$baseline"
    echo D284_01_CONSUMER=SUDO_VALIDATE
    echo D284_01_PAM_SERVICE=goodix-d284-01-sudo
    echo D284_01_PAM_MAX_TRIES=1
    echo D284_01_FAILURE_PHASE=PRE_SENSOR_PREFLIGHT
    echo D284_01_REAL_LOGIN_IN_SCOPE=false
    echo D284_01_KDE_LOCK_SCREEN_IN_SCOPE=false
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
  } >"$live_result/summary.env"
  : >"$live_result/operator.log"
  chmod 0600 "$live_result/operator.log" "$live_result/summary.env"
  hash_d284_host_config "$live_private/host-config.before.sha256" ||
    refuse HOST_CONFIG_SNAPSHOT_FAILED
  d284_config_before_ready=true
  sudo -U "$user" -l >"$live_private/sudo-policy.before" 2>&1 ||
    refuse OPERATOR_NOT_SUDOER
  live_service_before=$(systemctl is-active fprintd.service 2>/dev/null || true)
  [[ $live_service_before == active || $live_service_before == inactive ]] ||
    refuse FPRINTD_INITIAL_STATE_UNSAFE
  [[ -d $live_storage_root ]] && live_storage_existed=true
  live_system_library=$(readlink -f /usr/lib64/libfprint-2.so.2) ||
    refuse SYSTEM_LIBFPRINT_MISSING
  live_system_library_before=$(sha256sum "$live_system_library" | awk '{print $1}') ||
    refuse SYSTEM_LIBFPRINT_HASH_FAILED
  validate_selinux_preconditions "$live_system_library" "$live_storage_root"
  live_cleanup_armed=true
  trap cleanup_d284 EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  since=$(date --iso-8601=seconds) || refuse HOST_CLOCK_FAILED
  systemctl cat fprintd.service >"$live_private/unit.before" || refuse UNIT_SNAPSHOT_FAILED
  live_unit_before=$(sha256sum "$live_private/unit.before" | awk '{print $1}') ||
    refuse UNIT_SNAPSHOT_HASH_FAILED
  live_unit_before_ready=true
  "$d282_script_dir/d282_storage_inventory.py" "$live_storage_root" \
    "$live_private/storage.before.json" --exclude-name "${live_owned##*/}" \
    >"$live_private/storage.before.env" || refuse STORAGE_INVENTORY_FAILED
  live_before_inventory_ready=true
  live_system_library_before_ready=true
  target_preconsumption_match_count=$(count_goodix_targets /sys/bus/usb/devices)
  [[ $target_preconsumption_match_count -eq 1 ]] ||
    refuse TARGET_CARDINALITY_NOT_ONE

  live_staging_started=true
  sed -i 's/^D284_01_FAILURE_PHASE=.*/D284_01_FAILURE_PHASE=PRE_SENSOR_STAGING/' \
    "$live_result/summary.env"
  echo D284_01_PROGRESS_PHASE=PRE_SENSOR_STAGING >>"$live_result/operator.log"
  install -d -m 0700 "$live_runtime" "$live_owned" "$(dirname "$live_dropin")"
  stage_d284_runtime "$candidate" "$live_runtime" || refuse RUNTIME_STAGING_FAILED
  if [[ $validated_selinux_enforcement == Enforcing ]]; then
    for raw in "$live_runtime"/*.so.*; do
      chcon --reference=/usr/lib64/libfprint-2.so.2 "$raw"
    done
    restorecon -RF "$live_owned"
  fi
  write_systemd_dropin "$live_runtime" "$live_owned" "$live_dropin" live
  chmod 0600 "$live_dropin"
  live_service_touched=true
  systemctl stop fprintd.service
  systemctl daemon-reload
  real_usb_enumeration_attempted=true
  real_sensor_accessed=true
  live_execution_performed=true
  systemctl start fprintd.service
  target_count=$(count_goodix_targets /sys/bus/usb/devices)
  [[ $target_count -eq 1 ]] || refuse TARGET_CARDINALITY_NOT_ONE
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse DAEMON_PID_INVALID
  grep -F "$live_runtime/libfprint-2.so.2.0.0" /proc/"$daemon_pid"/maps \
    >"$live_private/maps" || refuse DAEMON_LIBRARY_MAP_MISSING

  echo "PHASE_A=Enrollment isolato indice destro: otto contatti."
  printf 'Confermare il dito enrollment digitando DESTRO: '
  read -r confirmation || refuse ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED
  [[ $confirmation == DESTRO ]] || refuse ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED
  echo ENROLL_OPERATOR_CONFIRMATION=DESTRO >>"$live_result/operator.log"
  raw="$live_private/enroll.raw"
  set +e
  timeout --signal=INT --kill-after=20s 1060s \
    fprintd-enroll -f right-index-finger "$user" 2>&1 | tee "$raw"
  action_rc=${PIPESTATUS[0]}
  set -e
  if [[ $action_rc -ne 0 ||
        $(grep -c '^Enroll result: enroll-completed$' "$raw") -ne 1 ||
        $(grep -c 'enroll-retry-' "$raw" || true) -ne 0 ]]; then
    capture_d284_failure ENROLL "$action_rc" "$raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  if [[ $(find "$live_owned" -type l | wc -l) -ne 0 ||
        $(find "$live_owned" -type f | wc -l) -ne 1 ]]; then
    capture_d284_failure ENROLL_STORAGE_AUDIT 1 "$raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  stored=$(find "$live_owned" -type f -print)
  if [[ $(head -c 3 "$stored") != FP3 ]]; then
    capture_d284_failure ENROLL_FORMAT_AUDIT 1 "$raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  systemctl restart fprintd.service || {
    capture_d284_failure DAEMON_RESTART_AFTER_ENROLL 1 "$raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  }
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse DAEMON_PID_INVALID_AFTER_RESTART
  grep -F "$live_runtime/libfprint-2.so.2.0.0" /proc/"$daemon_pid"/maps \
    >>"$live_private/maps" || refuse DAEMON_LIBRARY_MAP_MISSING_AFTER_RESTART

  install_d284_overrides "$user" || refuse PAM_SUDOERS_STAGING_FAILED
  runuser -u "$user" -- sudo -K || refuse SUDO_TIMESTAMP_INVALIDATION_FAILED
  d284_timestamp_invalidated=true
  echo "PHASE_B=Un solo sudo -v con impronta; non digitare password."
  printf 'Confermare il dito fisico digitando INDICE DESTRO: '
  read -r confirmation || refuse SUDO_PHYSICAL_FINGER_NOT_CONFIRMED
  [[ $confirmation == 'INDICE DESTRO' ]] || refuse SUDO_PHYSICAL_FINGER_NOT_CONFIRMED
  echo SUDO_OPERATOR_CONFIRMATION=INDICE_DESTRO >>"$live_result/operator.log"
  raw="$live_private/sudo.raw"
  set +e
  timeout --signal=INT --kill-after=20s 75s \
    runuser -u "$user" -- env -u SUDO_ASKPASS sudo -v 2>&1 | tee "$raw"
  action_rc=${PIPESTATUS[0]}
  set -e
  if [[ $action_rc -ne 0 ]]; then
    capture_d284_failure SUDO_VALIDATE "$action_rc" "$raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  fi

  if ! journalctl -u fprintd.service --since "$since" --no-pager \
      >"$live_private/pre-delete-journal.raw" 2>&1; then
    capture_d284_failure PRE_DELETE_AUDIT 1 "$live_private/pre-delete-journal.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  if ! grep GOODIX_D282_EPOCH_AUDIT "$live_private/pre-delete-journal.raw" \
      >"$live_private/pre-delete-audit.raw" ||
      [[ $(wc -l <"$live_private/pre-delete-audit.raw") -ne 2 ]] ||
      [[ $(grep -c 'action=FPI_DEVICE_ACTION_ENROLL' "$live_private/pre-delete-audit.raw") -ne 1 ]] ||
      ! verify_current_live_epoch_audit "$live_private/pre-delete-audit.raw" 1; then
    capture_d284_failure PRE_DELETE_AUDIT 1 "$live_private/pre-delete-journal.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  if ! grep GOODIX_SIGFM_MATCH_AUDIT "$live_private/pre-delete-journal.raw" \
      >"$live_private/pre-delete-matcher.raw" ||
      [[ $(grep -c 'event=outcome result=match' "$live_private/pre-delete-matcher.raw") -ne 1 ]]; then
    capture_d284_failure PRE_DELETE_MATCH_AUDIT 1 "$live_private/pre-delete-journal.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi

  if ! runuser -u "$user" -- sudo -K; then
    capture_d284_failure SUDO_TIMESTAMP_CLEANUP 1 "$live_private/sudo.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  d284_timestamp_invalidated=true
  if ! remove_d284_overrides; then
    capture_d284_failure PAM_SUDOERS_EARLY_REMOVE 1 "$live_private/sudo.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  echo D284_01_PAM_SUDOERS_REMOVED_BEFORE_DELETE=true >>"$live_result/operator.log"
  echo "PHASE_C=Delete del solo template isolato e rollback."
  set +e
  fprintd-delete "$user" >"$live_private/delete.raw" 2>&1
  action_rc=$?
  set -e
  if [[ $action_rc -ne 0 || $(find "$live_owned" -type f | wc -l) -ne 0 ]]; then
    capture_d284_failure HOST_ONLY_DELETE "$action_rc" "$live_private/delete.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi

  if ! journalctl -u fprintd.service --since "$since" --no-pager \
      >"$live_private/journal.raw" 2>&1 ||
      ! grep GOODIX_D282_EPOCH_AUDIT "$live_private/journal.raw" \
        >"$live_private/audit.raw" ||
      ! grep GOODIX_SIGFM_EXTRACT_AUDIT "$live_private/journal.raw" \
        >"$live_private/extract-audit.raw" ||
      ! grep GOODIX_SIGFM_MATCH_AUDIT "$live_private/journal.raw" \
        >"$live_private/matcher-audit.raw"; then
    capture_d284_failure FINAL_AUDIT 1 "$live_private/journal.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  epoch_count=$(wc -l <"$live_private/audit.raw")
  enroll_count=$(grep -c 'action=FPI_DEVICE_ACTION_ENROLL' "$live_private/audit.raw" || true)
  verify_count=$(grep -c 'action=FPI_DEVICE_ACTION_VERIFY' "$live_private/audit.raw" || true)
  cleanup_epoch_count=$(grep -c 'action=FPI_DEVICE_ACTION_NONE.*attempts=0 rejected=0 consumed=0 tls=0' "$live_private/audit.raw" || true)
  consumed_count=$(grep -c 'consumed=1' "$live_private/audit.raw" || true)
  attempts=$(awk '{for(i=1;i<=NF;i++)if($i~/^attempts=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$live_private/audit.raw")
  retry_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^(secure_retry|post_retry)=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$live_private/audit.raw")
  reopen_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^reopen=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$live_private/audit.raw")
  reset_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^reset=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$live_private/audit.raw")
  clear_halt_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^clear_halt=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$live_private/audit.raw")
  persistent_count=$(awk '{for(i=1;i<=NF;i++)if($i~/^persistent=/){split($i,a,"=");s+=a[2]}}END{print s+0}' "$live_private/audit.raw")
  extract_count=$(wc -l <"$live_private/extract-audit.raw")
  matcher_start_count=$(grep -c 'event=start' "$live_private/matcher-audit.raw" || true)
  matcher_outcome_count=$(grep -c 'event=outcome' "$live_private/matcher-audit.raw" || true)
  matcher_match_count=$(grep -c 'event=outcome result=match' "$live_private/matcher-audit.raw" || true)
  matcher_error_count=$(grep -c 'event=error' "$live_private/matcher-audit.raw" || true)
  observed_max_score=$(awk '{for(i=1;i<=NF;i++)if($i~/^score=/){split($i,a,"=");if(a[2]>m)m=a[2]}}END{print m+0}' "$live_private/matcher-audit.raw")
  matched_sample=$(awk '/event=outcome/{for(i=1;i<=NF;i++)if($i~/^matched_sample=/){split($i,a,"=");print a[2]}}' "$live_private/matcher-audit.raw")
  comparison_count=$(awk '/event=outcome/{for(i=1;i<=NF;i++)if($i~/^comparisons=/){split($i,a,"=");print a[2]}}' "$live_private/matcher-audit.raw")
  [[ $epoch_count -eq 3 && $enroll_count -eq 1 && $verify_count -eq 1 &&
     $cleanup_epoch_count -eq 1 && $consumed_count -eq 2 && $attempts -eq 2 &&
     $retry_count -eq 0 && $reopen_count -eq 0 && $reset_count -eq 0 &&
     $clear_halt_count -eq 0 && $persistent_count -eq 0 &&
     $extract_count -eq 9 && $matcher_start_count -eq 1 &&
     $matcher_outcome_count -eq 1 && $matcher_match_count -eq 1 &&
     $matcher_error_count -eq 0 && $observed_max_score -ge 40 &&
     $matched_sample =~ ^[1-8]$ && $comparison_count =~ ^[1-8]$ ]] || {
    capture_d284_failure FINAL_AUDIT 1 "$live_private/journal.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  }
  if [[ $(grep -c 'outstanding=0 drained=1 context_closed=1' "$live_private/audit.raw") -ne 3 ]] ||
      ! verify_current_live_epoch_audit "$live_private/audit.raw" 1; then
    capture_d284_failure FINAL_AUDIT 1 "$live_private/journal.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" \
    "$live_private"/*.raw >>"$live_result/operator.log"
  {
    echo D284_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
    echo "D284_01_BASELINE_SHA=$baseline"
    echo D284_01_CONSUMER=SUDO_VALIDATE
    echo D284_01_PAM_SERVICE=goodix-d284-01-sudo
    echo D284_01_PAM_MAX_TRIES=1
    echo D284_01_SUDO_VALIDATE_RETURN_CODE=0
    echo D284_01_PASSWORD_FALLBACK_PRESENT=true
    echo D284_01_AUTHSELECT_WRITE_COUNT=0
    echo D284_01_EXISTING_PAM_FILE_WRITE_COUNT=0
    echo D284_01_REAL_LOGIN_IN_SCOPE=false
    echo D284_01_KDE_LOCK_SCREEN_IN_SCOPE=false
    echo BIOMETRIC_ACTION_MAX=2
    echo EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=9
    echo "OPEN_EPOCH_COUNT=$epoch_count"
    echo "CONSUMED_BIOMETRIC_ACTION_COUNT=$consumed_count"
    echo "ENROLL_ACTION_COUNT=$enroll_count"
    echo "VERIFY_ACTION_COUNT=$verify_count"
    echo "HOST_ONLY_DELETE_OPEN_EPOCH_COUNT=$cleanup_epoch_count"
    echo "OBSERVED_RETRY_COUNT=$retry_count"
    echo "HIDDEN_REOPEN_COUNT=$reopen_count"
    echo "RESET_COUNT=$reset_count"
    echo "CLEAR_HALT_COUNT=$clear_halt_count"
    echo "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=$persistent_count"
    echo "SIGFM_EXTRACT_AUDIT_COUNT=$extract_count"
    echo SIGFM_MATCH_OUTCOME=match
    echo "SIGFM_MATCH_OBSERVED_MAX_SCORE=$observed_max_score"
    echo "SIGFM_MATCHED_SAMPLE=$matched_sample"
    echo "SIGFM_COMPARISON_COUNT=$comparison_count"
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
  } >"$live_result/summary.env"
  chmod 0600 "$live_result/operator.log" "$live_result/summary.env"
  live_run_return_code=0
  echo "RISULTATI=$live_result"
}

export_d284_results () {
  local result=$1 export
  [[ $EUID -eq 0 && ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]] ||
    refuse EXPORT_CALLER
  [[ $result == /var/tmp/goodix-d284-01-results/* ]] || refuse EXPORT_SOURCE
  [[ -d $result/private ]] || refuse EXPORT_SOURCE_INVALID
  export=$(mktemp -d /tmp/goodix-d284-01-export.XXXXXX)
  chmod 0700 "$export"
  copy_d283_result_set "$result" "$export" "$SUDO_UID" "$SUDO_GID" ||
    refuse EXPORT_RESULT_SET
  chown "$SUDO_UID:$SUDO_GID" "$export"
  echo D284_01_RESULTS_EXPORT=PASS_BYTE_IDENTICAL
  echo "EXPORT_DIRECTORY=$export"
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
}

operator_d284_run () {
  local rpm_dir=$1 user baseline transcript result output rc export_rc=1 confirmation
  [[ $EUID -ne 0 ]] || refuse OPERATOR_RUN_MUST_BE_UNPRIVILEGED
  command -v sudo >/dev/null || refuse HOST_TOOL_MISSING_sudo
  user=$(id -un) || refuse OPERATOR_USER_UNKNOWN
  baseline=$(git -C "$root" rev-parse HEAD) || refuse BASELINE_UNREADABLE
  verify_d284_baseline "$baseline"
  trap cleanup_prepared_candidate EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  prepare_candidate "$baseline" "$rpm_dir"
  echo
  echo "D284/01: 8 contatti enrollment + 1 sudo -v, max-tries=1."
  echo "Non bloccare lo schermo, non usare altri sudo e non digitare password."
  printf 'Digitare ESEGUI per avviare la singola run manuale: '
  read -r confirmation
  [[ $confirmation == ESEGUI ]] || refuse OPERATOR_CANCELLED
  transcript=$(mktemp /tmp/goodix-d284-01-operator.XXXXXX)
  chmod 0600 "$transcript"
  set +e
  sudo "$d284_script_dir/run-d284-01.sh" --run-live "$prepared_candidate" \
    --user "$user" 2>&1 | tee "$transcript"
  rc=${PIPESTATUS[0]}
  set -e
  result=$(sed -n 's/^RISULTATI_PRIVATI=//p' "$transcript" | tail -n 1)
  if [[ -n $result ]]; then
    set +e
    output=$(sudo "$d284_script_dir/run-d284-01.sh" --export-results "$result" 2>&1)
    export_rc=$?
    set -e
    printf '%s\n' "$output"
    [[ $export_rc -eq 0 ]] || rc=$export_rc
  fi
  cleanup_prepared_candidate
  prepared_candidate=
  echo "TERMINAL_TRANSCRIPT=$transcript"
  trap - EXIT INT TERM
  return "$rc"
}

offline_cleanup_regression () {
  local work=$1
  install -d -m 0700 "$work"
  d284_cleanup_test_mode=true
  d284_pam_path="$work/goodix-d284-01-sudo"
  d284_sudoers_path="$work/90-goodix-d284-01-pilot"
  : >"$d284_pam_path"
  : >"$d284_sudoers_path"
  d284_pam_installed=true
  d284_sudoers_installed=true
  remove_d284_overrides
  [[ ! -e $d284_pam_path && ! -e $d284_sudoers_path ]] || return 1
  d284_cleanup_test_mode=false
  echo D284_01_OVERRIDE_CLEANUP_REGRESSION=PASS
}

cleanup_d284_offline_work () {
  local work=$d284_offline_work
  [[ -z $work ]] && return 0
  [[ $work == /tmp/goodix-d284-01-offline.* && -d $work && ! -L $work ]] || {
    echo "D284_01_OFFLINE_CLEANUP_REFUSED=$work" >&2
    return 1
  }
  find "$work" -xdev -depth -delete
  d284_offline_work=
}

offline_preflight () {
  local rpm_dir=$1 work sudoers
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  bash -n "$d284_script_dir/run-d284-01.sh"
  (cd "$root" && python3 -m unittest -v \
    analysis.D284.test_d284_01_offline_contract \
    analysis.D283.test_d283_01_offline_contract \
    analysis.D282.test_d282_03_offline_contract \
    analysis.D282.test_d282_02_offline_contract \
    analysis.D282.test_d282_01_offline_contract)
  work=$(mktemp -d /tmp/goodix-d284-01-offline.XXXXXX)
  d284_offline_work=$work
  trap cleanup_d284_offline_work EXIT
  install -d -m 0700 "$work/candidate" "$work/runtime"
  build_candidate "$root" "$work/candidate" "$rpm_dir"
  abi_preflight "$work/candidate"
  stage_d284_runtime "$work/candidate" "$work/runtime"
  sudoers="$work/90-goodix-d284-01-pilot"
  write_d284_sudoers goodix_test "$sudoers"
  visudo -cf "$sudoers" >/dev/null
  offline_cleanup_regression "$work/cleanup"
  echo D284_01_OFFLINE_PREFLIGHT=PASS
  echo D284_01_REAL_TARGET_COMPATIBILITY=PASS
  echo D284_01_PAM_SERVICE=goodix-d284-01-sudo
  echo D284_01_PAM_MAX_TRIES=1
  echo D284_01_PASSWORD_FALLBACK_PRESENT=true
  echo D284_01_BIOMETRIC_ACTION_MAX=2
  echo D284_01_EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=9
  echo D284_01_LIVE_READINESS=HUMAN_REQUIRED_OPERATOR_RUN
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo LIVE_EXECUTION_PERFORMED=false
  trap - EXIT
  cleanup_d284_offline_work
}

if [[ ${D284_LIBRARY_ONLY:-false} != true ]]; then
  case ${1:-} in
    --offline-preflight) [[ $# -eq 2 ]] || refuse USAGE; offline_preflight "$2" ;;
    --operator-run) [[ $# -eq 2 ]] || refuse USAGE; operator_d284_run "$2" ;;
    --run-live) [[ $# -eq 4 && $3 == --user ]] || refuse USAGE; run_d284_live "$2" "$4" ;;
    --export-results) [[ $# -eq 2 ]] || refuse USAGE; export_d284_results "$2" ;;
    *) echo "Uso: $0 --offline-preflight <opencv-rpm-dir> | --operator-run <opencv-rpm-dir>" >&2; exit 2 ;;
  esac
fi
