#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

d283_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
d282_script_dir=$(CDPATH= cd -- "$d283_script_dir/../d282-01-fprintd-target" && pwd)
D282_LIBRARY_ONLY=true
# shellcheck source=../d282-01-fprintd-target/run-d282-01.sh
source "$d282_script_dir/run-d282-01.sh"
unset D282_LIBRARY_ONLY
script_dir=$d282_script_dir

live_result_prefix=D283_01
d283_live_standby=false
d283_critical=(libfprint-driver Rockytkg
  reference/libfprint-fedora44-1.94.100/source
  reference/fprintd-fedora44-1.94.5 analysis/D282 analysis/D283
  operator_kit/d282-01-fprintd-target
  operator_kit/d282-03-balanced-same-different
  operator_kit/d283-01-pam-dedicated
  captures/D282_03/D28203_ATTEMPT_02_20260910T222713Z_4a3ee4bb96f6/sanitized
  operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256
  "Goodix 27c6 5125 manuale tecnico.md")

refuse () {
  echo D283_01_GATE_REFUSED=true >&2
  echo "D283_01_REFUSAL_REASON=$1" >&2
  echo AUTHORIZATION_CREDENTIAL_REQUIRED=false >&2
  echo AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false >&2
  echo "TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count" >&2
  echo "REAL_USB_ENUMERATION_ATTEMPTED=$real_usb_enumeration_attempted" >&2
  echo "REAL_SENSOR_ACCESSED=$real_sensor_accessed" >&2
  echo "LIVE_EXECUTION_PERFORMED=$live_execution_performed" >&2
  exit 3
}

verify_d283_baseline () {
  local baseline=$1
  is_sha "$baseline" || refuse INVALID_BASELINE
  [[ $(git -C "$root" branch --show-current) == development ]] ||
    refuse WRONG_BRANCH
  [[ $(git -C "$root" rev-parse HEAD) == "$baseline" ]] ||
    refuse HEAD_MISMATCH
  [[ $(git -C "$root" rev-parse origin/development) == "$baseline" ]] ||
    refuse ORIGIN_DEVELOPMENT_MISMATCH
  [[ -z $(git -C "$root" status --porcelain --untracked-files=all -- \
    "${d283_critical[@]}") ]] || refuse LIVE_CRITICAL_DIRTY
}

build_pam_runner () {
  local candidate=$1 manifest_sha
  install -d -m 0700 "$candidate/pam.d"
  cc -std=c11 -O2 -Wall -Wextra -Werror \
    "$d283_script_dir/pam-confdir-runner.c" \
    -Wl,-l:libpam.so.0 -o "$candidate/d283-pam-confdir-runner"
  install -m 0600 "$d283_script_dir/goodix-d283-01.pam" \
    "$candidate/pam.d/goodix-d283-01"
  chmod 0700 "$candidate/d283-pam-confdir-runner"
  (cd "$candidate" && sha256sum d283-pam-confdir-runner \
    pam.d/goodix-d283-01 >d283-01-artifacts.sha256)
  manifest_sha=$(sha256sum "$candidate/d283-01-artifacts.sha256" |
    awk '{print $1}')
  {
    echo "D283_01_BASELINE_SHA=$(git -C "$root" rev-parse HEAD)"
    echo "D283_01_MANIFEST_SHA256=$manifest_sha"
    echo D283_01_PAM_SERVICE=goodix-d283-01
    echo D283_01_PAM_MAX_TRIES=1
    echo D283_01_PAM_TIMEOUT_SECONDS=45
  } >"$candidate/d283-01-candidate.state"
  chmod 0600 "$candidate/d283-01-artifacts.sha256" \
    "$candidate/d283-01-candidate.state"
}

capture_d283_failure () {
  local phase=$1 return_code=$2 raw_file=$3 since=$4 baseline=$5 stamp=$6
  local user=$7 journal_file="$live_private/failure-journal.raw"

  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$journal_file" 2>&1 || true
  if [[ -f $live_result/summary.env ]]; then
    sed -i "s/^D283_01_RESULT=.*/D283_01_RESULT=FAIL_${phase}/" \
      "$live_result/summary.env"
    sed -i "s/^D283_01_FAILURE_PHASE=.*/D283_01_FAILURE_PHASE=${phase}/" \
      "$live_result/summary.env"
  fi
  {
    echo "D283_01_FAILURE_PHASE=$phase"
    echo "D283_01_FAILURE_RETURN_CODE=$return_code"
    if [[ -f $raw_file ]]; then
      sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" \
        "$raw_file"
    fi
    grep -E 'GOODIX_D282_EPOCH_AUDIT|fprintd|pam_fprintd' "$journal_file" |
      tail -n 200 |
      sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" || true
  } >>"$live_result/operator.log"
}

prepare_d283_candidate () {
  local baseline=$1 rpm_dir=$2
  verify_d283_baseline "$baseline"
  prepare_candidate "$baseline" "$rpm_dir"
  build_pam_runner "$prepared_candidate"
  echo D283_01_CANDIDATE_PREPARED=true
  echo "D283_01_CANDIDATE_DIRECTORY=$prepared_candidate"
}

stage_d283_runtime () {
  local candidate=$1 runtime=$2 name
  [[ -d $candidate && ! -L $candidate && -d $runtime && ! -L $runtime ]] ||
    return 1
  [[ $runtime == /run/goodix-d283-01/* ||
     $runtime == /tmp/goodix-d283-01-offline.*/* ]] || return 1
  [[ -z $(find "$runtime" -mindepth 1 -maxdepth 1 -print -quit) ]] || return 1
  for name in libfprint-2.so.2.0.0 libgusb.so.2 \
    libopencv_core.so.413 libopencv_features2d.so.413 \
    libopencv_flann.so.413 libopencv_imgproc.so.413; do
    [[ -f $candidate/$name && ! -L $candidate/$name ]] || return 1
    install -m 0600 "$candidate/$name" "$runtime/$name" || return 1
  done
  install -d -m 0700 "$runtime/pam.d" || return 1
  install -m 0700 "$candidate/d283-pam-confdir-runner" \
    "$runtime/d283-pam-confdir-runner" || return 1
  install -m 0600 "$candidate/pam.d/goodix-d283-01" \
    "$runtime/pam.d/goodix-d283-01" || return 1
  ln -s libfprint-2.so.2.0.0 "$runtime/libfprint-2.so.2" || return 1
  ln -s libfprint-2.so.2 "$runtime/libfprint-2.so" || return 1
}

copy_d283_result_set () {
  local result=$1 export=$2 owner=$3 group=$4 name source_sha copy_sha
  [[ -d $result/private && -d $export && ! -L $result && ! -L $export ]] ||
    return 1
  for name in operator.log summary.env; do
    [[ -f $result/$name && ! -L $result/$name ]] || return 1
    source_sha=$(sha256sum "$result/$name" | awk '{print $1}') || return 1
    install -m 0600 -o "$owner" -g "$group" "$result/$name" "$export/$name" ||
      return 1
    copy_sha=$(sha256sum "$export/$name" | awk '{print $1}') || return 1
    [[ $source_sha == "$copy_sha" ]] || return 1
    echo "${name}_SHA256=$source_sha"
  done
}

d283_offline_staging_and_export_regressions () {
  local candidate=$1 work=$2 runtime result export
  runtime="$work/runtime"
  install -d -m 0700 "$runtime"
  stage_d283_runtime "$candidate" "$runtime" || return 1
  [[ -f $runtime/libfprint-2.so.2.0.0 && ! -L $runtime/libfprint-2.so.2.0.0 &&
     -L $runtime/libfprint-2.so.2 &&
     $(readlink "$runtime/libfprint-2.so.2") == libfprint-2.so.2.0.0 &&
     -L $runtime/libfprint-2.so &&
     $(readlink "$runtime/libfprint-2.so") == libfprint-2.so.2 &&
     -x $runtime/d283-pam-confdir-runner &&
     -f $runtime/pam.d/goodix-d283-01 ]] || return 1
  result="$work/pre-action-result"; export="$work/pre-action-export"
  install -d -m 0700 "$result/private" "$export"
  printf 'D283_01_FAILURE_PHASE=PRE_SENSOR_STAGING\n' >"$result/operator.log"
  printf 'D283_01_RESULT=FAIL_PRE_SENSOR_STAGING\n' >"$result/summary.env"
  copy_d283_result_set "$result" "$export" "$(id -u)" "$(id -g)" >/dev/null ||
    return 1
  [[ -f $export/operator.log && -f $export/summary.env ]] || return 1
  echo D283_01_ACTUAL_CANDIDATE_SYMLINK_STAGING_REGRESSION=PASS
  echo D283_01_PRE_ACTION_RESULT_EXPORT_REGRESSION=PASS
}

run_d283_live () {
  local candidate=$1 user=$2 d282_state d283_state baseline manifest d283_manifest
  local observed_manifest observed_d283_manifest pam_service_line
  local stamp since daemon_pid raw action_rc enroll_retry_count stored
  local target_count epoch_count enroll_count verify_count cleanup_epoch_count
  local consumed_count attempts retry_count reopen_count reset_count clear_halt_count
  local persistent_count confirmation extract_count matcher_start_count
  local matcher_outcome_count matcher_match_count matcher_error_count
  local observed_max_score matched_sample comparison_count

  [[ $d283_live_standby != true ]] ||
    refuse D283_LIVE_STANDBY_MATCHER_CHARACTERIZATION_REQUIRED

  live_result=
  live_private=
  live_runtime=
  live_owned=
  live_storage_root=/var/lib/fprint
  live_dropin=/run/systemd/system/fprintd.service.d/90-goodix-d283-01.conf
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
  live_result_prefix=D283_01
  real_usb_enumeration_attempted=false
  real_sensor_accessed=false
  live_execution_performed=false
  staging_probe_execution_performed=false
  staging_probe_mode=false
  live_current_direct_mode=true

  [[ $EUID -eq 0 ]] || refuse LIVE_REQUIRES_ROOT
  d282_state="$candidate/d282-01-candidate.state"
  d283_state="$candidate/d283-01-candidate.state"
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -f $d282_state &&
     -f $d283_state && ! -L $candidate ]] || refuse CANDIDATE_INVALID
  baseline=$(state_value "$d282_state" D282_01_BASELINE_SHA) ||
    refuse CANDIDATE_STATE
  [[ $(state_value "$d283_state" D283_01_BASELINE_SHA) == "$baseline" ]] ||
    refuse CANDIDATE_BASELINE_DRIFT
  manifest=$(state_value "$d282_state" D282_01_MANIFEST_SHA256) ||
    refuse CANDIDATE_STATE
  d283_manifest=$(state_value "$d283_state" D283_01_MANIFEST_SHA256) ||
    refuse CANDIDATE_STATE
  verify_d283_baseline "$baseline"
  observed_manifest=$(sha256sum "$candidate/d282-01-artifacts.sha256" |
    awk '{print $1}')
  observed_d283_manifest=$(sha256sum "$candidate/d283-01-artifacts.sha256" |
    awk '{print $1}')
  [[ $observed_manifest == "$manifest" ]] || refuse MANIFEST_DRIFT
  [[ $observed_d283_manifest == "$d283_manifest" ]] || refuse PAM_MANIFEST_DRIFT
  (cd "$candidate" && sha256sum -c d282-01-artifacts.sha256 &&
    sha256sum -c d283-01-artifacts.sha256) || refuse ARTIFACT_DRIFT
  [[ $(state_value "$d283_state" D283_01_PAM_SERVICE) == goodix-d283-01 &&
     $(state_value "$d283_state" D283_01_PAM_MAX_TRIES) == 1 &&
     $(state_value "$d283_state" D283_01_PAM_TIMEOUT_SECONDS) == 45 ]] ||
    refuse PAM_STATE_DRIFT
  pam_service_line=$(cat "$candidate/pam.d/goodix-d283-01")
  [[ $pam_service_line == 'auth required /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=45' ]] ||
    refuse PAM_SERVICE_DRIFT
  [[ $(rpm -q fprintd-pam) == fprintd-pam-1.94.5-5.fc44.x86_64 ]] ||
    refuse FPRINTD_PAM_NEVRA_DRIFT
  ldd "$candidate/d283-pam-confdir-runner" | grep -F 'libpam.so.0' >/dev/null ||
    refuse PAM_RUNNER_LINKAGE_INVALID
  [[ $user =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || refuse OPERATOR_USER_INVALID
  getent passwd "$user" >/dev/null || refuse OPERATOR_USER_UNKNOWN
  [[ ${SUDO_USER:-$user} == "$user" ]] || refuse OPERATOR_USER_MISMATCH
  validate_live_tooling
  command -v rpm >/dev/null || refuse HOST_TOOL_MISSING_rpm
  command -v ldd >/dev/null || refuse HOST_TOOL_MISSING_ldd

  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  live_result="/var/tmp/goodix-d283-01-results/${stamp}-${baseline:0:12}"
  echo "RISULTATI_PRIVATI=$live_result"
  live_runtime="/run/goodix-d283-01/${stamp}-${baseline:0:12}"
  live_owned="$live_storage_root/.goodix-d283-01-${stamp}-${baseline:0:12}"
  [[ ! -e $live_runtime && ! -e $live_owned && ! -e $live_dropin ]] ||
    refuse STAGING_COLLISION
  live_private="$live_result/private"
  install -d -m 0700 "$live_private" || refuse RESULT_DIRECTORY_CREATE_FAILED
  {
    echo D283_01_RESULT=FAIL_PENDING_AUDIT
    echo "D283_01_BASELINE_SHA=$baseline"
    echo D283_01_PAM_SERVICE=goodix-d283-01
    echo D283_01_PAM_MAX_TRIES=1
    echo D283_01_FAILURE_PHASE=PRE_SENSOR_PREFLIGHT
    echo D283_01_REAL_LOGIN_IN_SCOPE=false
    echo D283_01_SUDO_BIOMETRIC_AUTHENTICATION_IN_SCOPE=false
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
  } >"$live_result/summary.env" || refuse RESULT_SUMMARY_CREATE_FAILED
  : >"$live_result/operator.log" || refuse RESULT_OPERATOR_LOG_CREATE_FAILED
  chmod 0600 "$live_result/operator.log" "$live_result/summary.env"
  live_service_before=$(systemctl is-active fprintd.service 2>/dev/null || true)
  [[ $live_service_before == active || $live_service_before == inactive ]] ||
    refuse FPRINTD_INITIAL_STATE_UNSAFE
  [[ -d $live_storage_root ]] && live_storage_existed=true
  live_system_library=$(readlink -f /usr/lib64/libfprint-2.so.2) ||
    refuse SYSTEM_LIBFPRINT_MISSING
  [[ -f $live_system_library ]] || refuse SYSTEM_LIBFPRINT_MISSING
  live_system_library_before=$(sha256sum "$live_system_library" | awk '{print $1}') ||
    refuse SYSTEM_LIBFPRINT_HASH_FAILED
  validate_selinux_preconditions "$live_system_library" "$live_storage_root"
  live_cleanup_armed=true
  trap cleanup_live EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  since=$(date --iso-8601=seconds) || refuse HOST_CLOCK_FAILED
  systemctl cat fprintd.service >"$live_private/unit.before" ||
    refuse UNIT_SNAPSHOT_FAILED
  live_unit_before=$(sha256sum "$live_private/unit.before" | awk '{print $1}') ||
    refuse UNIT_SNAPSHOT_HASH_FAILED
  live_unit_before_ready=true
  "$d282_script_dir/d282_storage_inventory.py" "$live_storage_root" \
    "$live_private/storage.before.json" --exclude-name "${live_owned##*/}" \
    >"$live_private/storage.before.env" || refuse STORAGE_INVENTORY_FAILED
  live_before_inventory_ready=true
  live_system_library_before_ready=true
  target_preconsumption_match_count=$(count_goodix_targets /sys/bus/usb/devices)
  echo "TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count" \
    >>"$live_result/summary.env"
  [[ $target_preconsumption_match_count -eq 1 ]] ||
    refuse TARGET_CARDINALITY_NOT_ONE

  live_staging_started=true
  sed -i 's/^D283_01_FAILURE_PHASE=.*/D283_01_FAILURE_PHASE=PRE_SENSOR_STAGING/' \
    "$live_result/summary.env"
  echo D283_01_FAILURE_PHASE=PRE_SENSOR_STAGING >>"$live_result/operator.log"
  install -d -m 0700 "$live_runtime" "$live_owned" "$(dirname "$live_dropin")"
  stage_d283_runtime "$candidate" "$live_runtime" ||
    refuse RUNTIME_LIBRARY_STAGING_FAILED
  if [[ $validated_selinux_enforcement == Enforcing ]]; then
    for raw in "$live_runtime"/*.so.*; do
      chcon --reference=/usr/lib64/libfprint-2.so.2 "$raw"
    done
    chcon --reference=/usr/bin/true "$live_runtime/d283-pam-confdir-runner"
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
  [[ $(readlink -f /proc/"$daemon_pid"/exe) == /usr/libexec/fprintd ]] ||
    refuse DAEMON_EXE_DRIFT
  echo EXACT_LIBRARY_MAP_VERIFIED=true >>"$live_result/operator.log"
  chmod 0600 "$live_result/operator.log"

  echo "PHASE_A=Enrollment indice destro: otto contatti, nessuna ripetizione extra."
  printf 'Confermare il dito enrollment digitando DESTRO: '
  read -r confirmation || refuse ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED
  [[ $confirmation == DESTRO ]] || refuse ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED
  {
    echo ENROLL_PHYSICAL_FINGER=RIGHT_INDEX
    echo ENROLL_OPERATOR_CONFIRMATION=DESTRO
  } >>"$live_result/operator.log"
  raw="$live_private/enroll.raw"
  set +e
  timeout --signal=INT --kill-after=20s 1060s \
    fprintd-enroll -f right-index-finger "$user" 2>&1 | tee "$raw"
  action_rc=${PIPESTATUS[0]}
  set -e
  enroll_retry_count=$(grep -c 'enroll-retry-' "$raw" || true)
  if ! [[ $action_rc -eq 0 &&
          $(grep -c '^Enroll result: enroll-completed$' "$raw") -eq 1 &&
          $enroll_retry_count -eq 0 ]]; then
    capture_d283_failure ENROLL "$action_rc" "$raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi
  if ! [[ $(find "$live_owned" -type l | wc -l) -eq 0 &&
          $(find "$live_owned" -type f | wc -l) -eq 1 ]]; then
    capture_d283_failure ENROLL_STORAGE_AUDIT 1 "$raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi
  stored=$(find "$live_owned" -type f -print)
  if [[ $(head -c 3 "$stored") != FP3 ]]; then
    capture_d283_failure ENROLL_FORMAT_AUDIT 1 "$raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi
  systemctl restart fprintd.service
  echo DAEMON_RESTART_COUNT=1 >>"$live_result/operator.log"
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse DAEMON_PID_INVALID_AFTER_RESTART
  grep -F "$live_runtime/libfprint-2.so.2.0.0" /proc/"$daemon_pid"/maps \
    >>"$live_private/maps" || refuse DAEMON_LIBRARY_MAP_MISSING_AFTER_RESTART
  [[ $(readlink -f /proc/"$daemon_pid"/exe) == /usr/libexec/fprintd ]] ||
    refuse DAEMON_EXE_DRIFT_AFTER_RESTART
  echo POST_RESTART_EXACT_LIBRARY_MAP_VERIFIED=true \
    >>"$live_result/operator.log"

  echo "PHASE_B=PAM dedicato: un solo contatto dell'indice DESTRO registrato."
  echo "Nessun login o comando sudo userà l'impronta; max-tries PAM è 1."
  printf 'Confermare il dito fisico digitando INDICE DESTRO: '
  read -r confirmation || refuse PAM_PHYSICAL_FINGER_NOT_CONFIRMED
  [[ $confirmation == "INDICE DESTRO" ]] ||
    refuse PAM_PHYSICAL_FINGER_NOT_CONFIRMED
  raw="$live_private/pam-auth.raw"
  set +e
  timeout --signal=INT --kill-after=20s 75s \
    "$live_runtime/d283-pam-confdir-runner" "$live_runtime/pam.d" "$user" \
    2>&1 | tee "$raw"
  action_rc=${PIPESTATUS[0]}
  set -e
  if ! [[ $action_rc -eq 0 &&
          $(grep -c '^D283_01_PAM_START_CONFDIR_RETURN_CODE=0$' "$raw") -eq 1 &&
          $(grep -c '^D283_01_PAM_AUTHENTICATE_RETURN_CODE=0$' "$raw") -eq 1 &&
          $(grep -c '^D283_01_PAM_END_RETURN_CODE=0$' "$raw") -eq 1 ]]; then
    capture_d283_failure PAM_AUTHENTICATE "$action_rc" "$raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi
  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$live_private/phase-b-journal.raw"
  if ! grep GOODIX_D282_EPOCH_AUDIT "$live_private/phase-b-journal.raw" \
      >"$live_private/phase-b-audit.raw" ||
     [[ $(wc -l <"$live_private/phase-b-audit.raw") -ne 2 ]] ||
     [[ $(grep -c 'action=FPI_DEVICE_ACTION_ENROLL.*enroll_stages=8 enroll_rearm32=7 enroll_terminal=1' "$live_private/phase-b-audit.raw") -ne 1 ]] ||
     ! verify_current_live_epoch_audit "$live_private/phase-b-audit.raw" 1; then
    capture_d283_failure PHASE_B_AUDIT 1 "$raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi

  echo "PHASE_C=Delete del solo template D283 isolato."
  set +e
  fprintd-delete "$user" >"$live_private/delete.raw" 2>&1
  action_rc=$?
  set -e
  if [[ $action_rc -ne 0 || $(find "$live_owned" -type f | wc -l) -ne 0 ]]; then
    capture_d283_failure HOST_ONLY_DELETE "$action_rc" \
      "$live_private/delete.raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$live_private/journal.raw"
  if ! grep GOODIX_D282_EPOCH_AUDIT "$live_private/journal.raw" \
      >"$live_private/audit.raw"; then
    capture_d283_failure FINAL_AUDIT_MISSING 1 "$live_private/journal.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  grep GOODIX_SIGFM_EXTRACT_AUDIT "$live_private/journal.raw" \
    >"$live_private/extract-audit.raw" || true
  grep GOODIX_SIGFM_MATCH_AUDIT "$live_private/journal.raw" \
    >"$live_private/matcher-audit.raw" || true
  extract_count=$(wc -l <"$live_private/extract-audit.raw")
  matcher_start_count=$(grep -c 'event=start' "$live_private/matcher-audit.raw" || true)
  matcher_outcome_count=$(grep -c 'event=outcome' "$live_private/matcher-audit.raw" || true)
  matcher_match_count=$(grep -c 'event=outcome result=match' "$live_private/matcher-audit.raw" || true)
  matcher_error_count=$(grep -c 'event=error' "$live_private/matcher-audit.raw" || true)
  observed_max_score=$(awk '{for(i=1;i<=NF;i++)if($i~/^score=/){split($i,a,"=");if(a[2]>m)m=a[2]}}END{print m+0}' "$live_private/matcher-audit.raw")
  matched_sample=$(awk '/event=outcome/{for(i=1;i<=NF;i++)if($i~/^matched_sample=/){split($i,a,"=");print a[2]}}' "$live_private/matcher-audit.raw")
  comparison_count=$(awk '/event=outcome/{for(i=1;i<=NF;i++)if($i~/^comparisons=/){split($i,a,"=");print a[2]}}' "$live_private/matcher-audit.raw")
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
  if ! [[ $epoch_count -eq 3 && $enroll_count -eq 1 && $verify_count -eq 1 &&
          $cleanup_epoch_count -eq 1 && $consumed_count -eq 2 && $attempts -eq 2 &&
          $retry_count -eq 0 && $reopen_count -eq 0 && $reset_count -eq 0 &&
          $clear_halt_count -eq 0 && $persistent_count -eq 0 &&
          $extract_count -eq 9 && $matcher_start_count -eq 1 &&
          $matcher_outcome_count -eq 1 && $matcher_match_count -eq 1 &&
          $matcher_error_count -eq 0 && $observed_max_score -ge 40 &&
          $matched_sample =~ ^[1-8]$ && $comparison_count =~ ^[1-8]$ ]] ||
     [[ $(grep -c 'outstanding=0 drained=1 context_closed=1' "$live_private/audit.raw") -ne 3 ]] ||
     ! verify_current_live_epoch_audit "$live_private/audit.raw" 1; then
    capture_d283_failure FINAL_AUDIT 1 "$live_private/audit.raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi
  sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" \
    "$live_private"/*.raw >>"$live_result/operator.log"
  {
    echo D283_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
    echo "D283_01_BASELINE_SHA=$baseline"
    echo D283_01_PAM_SERVICE=goodix-d283-01
    echo D283_01_PAM_MAX_TRIES=1
    echo D283_01_PAM_AUTHENTICATE_RETURN_CODE=0
    echo D283_01_REAL_LOGIN_IN_SCOPE=false
    echo D283_01_SUDO_BIOMETRIC_AUTHENTICATION_IN_SCOPE=false
    echo BIOMETRIC_ACTION_MAX=2
    echo EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=9
    echo "TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count"
    echo "TARGET_POSTSTART_MATCH_COUNT=$target_count"
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
    echo SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE=RESIDUAL_RISK
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
  } >"$live_result/summary.env"
  chmod 0600 "$live_result/operator.log" "$live_result/summary.env"
  live_run_return_code=0
  echo "RISULTATI=$live_result"
}

export_d283_results () {
  local result=$1 export
  [[ $EUID -eq 0 && ${SUDO_UID:-} =~ ^[0-9]+$ &&
     ${SUDO_GID:-} =~ ^[0-9]+$ ]] || refuse EXPORT_CALLER
  [[ $result == /var/tmp/goodix-d283-01-results/* ]] || refuse EXPORT_SOURCE
  if [[ ! -d $result/private ]]; then
    echo D283_01_RESULTS_EXPORT=NOT_AVAILABLE_BEFORE_RESULT_INITIALIZATION
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
    return 0
  fi
  export=$(mktemp -d /tmp/goodix-d283-01-export.XXXXXX)
  chmod 0700 "$export"
  copy_d283_result_set "$result" "$export" "$SUDO_UID" "$SUDO_GID" ||
    refuse EXPORT_RESULT_SET
  chown "$SUDO_UID:$SUDO_GID" "$export"
  echo D283_01_RESULTS_EXPORT=PASS_BYTE_IDENTICAL
  echo "EXPORT_DIRECTORY=$export"
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
}

operator_d283_run () {
  local rpm_dir=$1 user baseline transcript result output rc export_rc=1
  local confirmation
  [[ $d283_live_standby != true ]] ||
    refuse D283_LIVE_STANDBY_MATCHER_CHARACTERIZATION_REQUIRED
  [[ $EUID -ne 0 ]] || refuse OPERATOR_RUN_MUST_BE_UNPRIVILEGED
  command -v sudo >/dev/null || refuse HOST_TOOL_MISSING_sudo
  user=$(id -un) || refuse OPERATOR_USER_UNKNOWN
  baseline=$(git -C "$root" rev-parse HEAD) || refuse BASELINE_UNREADABLE
  verify_d283_baseline "$baseline"
  trap cleanup_prepared_candidate EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  prepare_d283_candidate "$baseline" "$rpm_dir"
  echo
  echo "D283/01 userà al massimo 9 contatti: 8 per enrollment e 1 per PAM."
  echo "Il servizio PAM è dedicato, max-tries=1; login e sudo biometrici sono esclusi."
  echo "Non esistono retry automatici autorizzati dal kit."
  printf 'Digitare ESEGUI per avviare la singola run manuale: '
  read -r confirmation
  [[ $confirmation == ESEGUI ]] || refuse OPERATOR_CANCELLED
  transcript=$(mktemp /tmp/goodix-d283-01-operator.XXXXXX)
  chmod 0600 "$transcript"
  set +e
  sudo "$d283_script_dir/run-d283-01.sh" --run-live "$prepared_candidate" \
    --user "$user" 2>&1 | tee "$transcript"
  rc=${PIPESTATUS[0]}
  set -e
  result=$(sed -n 's/^RISULTATI_PRIVATI=//p' "$transcript" | tail -n 1)
  if [[ -n $result ]]; then
    set +e
    output=$(sudo "$d283_script_dir/run-d283-01.sh" --export-results "$result" 2>&1)
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

offline_preflight () {
  local rpm_dir=$1 work user result
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  bash -n "$d283_script_dir/run-d283-01.sh"
  (cd "$root" && python3 -m unittest -v \
    analysis.D283.test_d283_01_offline_contract \
    analysis.D282.test_d282_03_offline_contract \
    analysis.D282.test_d282_02_offline_contract \
    analysis.D282.test_d282_01_offline_contract)
  work=$(mktemp -d /tmp/goodix-d283-01-offline.XXXXXX)
  trap 'find "$work" -xdev -depth -delete 2>/dev/null || true' EXIT
  install -d -m 0700 "$work/candidate"
  build_candidate "$root" "$work/candidate" "$rpm_dir"
  abi_preflight "$work/candidate"
  build_pam_runner "$work/candidate"
  d283_offline_staging_and_export_regressions "$work/candidate" "$work"
  install -d -m 0700 "$work/permit"
  printf 'auth required /usr/lib64/security/pam_permit.so\n' \
    >"$work/permit/goodix-d283-01"
  user=$(id -un)
  result=$("$work/candidate/d283-pam-confdir-runner" "$work/permit" "$user")
  grep -Fx D283_01_PAM_START_CONFDIR_RETURN_CODE=0 <<<"$result" >/dev/null
  grep -Fx D283_01_PAM_AUTHENTICATE_RETURN_CODE=0 <<<"$result" >/dev/null
  grep -Fx D283_01_PAM_END_RETURN_CODE=0 <<<"$result" >/dev/null
  echo D283_01_OFFLINE_PREFLIGHT=PASS
  echo D283_01_PAM_START_CONFDIR=PASS_REAL_LIBPAM_WITH_DEDICATED_PERMIT_SERVICE
  echo D283_01_PAM_SERVICE=goodix-d283-01
  echo D283_01_PAM_MAX_TRIES=1
  echo D283_01_REAL_LOGIN_IN_SCOPE=false
  echo D283_01_SUDO_BIOMETRIC_AUTHENTICATION_IN_SCOPE=false
  echo D283_01_BIOMETRIC_ACTION_MAX=2
  echo D283_01_EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=9
  echo D283_01_LIVE_READINESS=HUMAN_REQUIRED_OPERATOR_RUN
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo LIVE_EXECUTION_PERFORMED=false
  trap - EXIT
  find "$work" -xdev -depth -delete
}

if [[ ${D283_LIBRARY_ONLY:-false} != true ]]; then
  case ${1:-} in
    --offline-preflight) [[ $# -eq 2 ]] || refuse USAGE; offline_preflight "$2" ;;
    --operator-run) [[ $# -eq 2 ]] || refuse USAGE; operator_d283_run "$2" ;;
    --run-live) [[ $# -eq 4 && $3 == --user ]] || refuse USAGE; run_d283_live "$2" "$4" ;;
    --export-results) [[ $# -eq 2 ]] || refuse USAGE; export_d283_results "$2" ;;
    *) echo "Uso: $0 --offline-preflight <opencv-rpm-dir> | --operator-run <opencv-rpm-dir>" >&2; exit 2 ;;
  esac
fi
