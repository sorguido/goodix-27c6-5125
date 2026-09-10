#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

d28202_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
d28201_script_dir=$(CDPATH= cd -- "$d28202_script_dir/../d282-01-fprintd-target" && pwd)
D282_LIBRARY_ONLY=true
# shellcheck source=../d282-01-fprintd-target/run-d282-01.sh
source "$d28201_script_dir/run-d282-01.sh"
unset D282_LIBRARY_ONLY
script_dir=$d28201_script_dir

live_result_prefix=D282_02
verified_daemon_pid=
verified_daemon_invocation_id=
d28202_critical=(libfprint-driver Rockytkg
  reference/libfprint-fedora44-1.94.100/source
  reference/fprintd-fedora44-1.94.5 analysis/D282
  operator_kit/d282-01-fprintd-target
  operator_kit/d282-02-matcher-order
  operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256
  "Goodix 27c6 5125 manuale tecnico.md")

refuse () {
  echo D282_02_GATE_REFUSED=true >&2
  echo "D282_02_REFUSAL_REASON=$1" >&2
  echo AUTHORIZATION_CREDENTIAL_REQUIRED=false >&2
  echo AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false >&2
  echo "TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count" >&2
  echo "REAL_USB_ENUMERATION_ATTEMPTED=$real_usb_enumeration_attempted" >&2
  echo "REAL_SENSOR_ACCESSED=$real_sensor_accessed" >&2
  echo "LIVE_EXECUTION_PERFORMED=$live_execution_performed" >&2
  exit 3
}

verify_d28202_baseline () {
  local baseline=$1
  is_sha "$baseline" || refuse INVALID_BASELINE
  [[ $(git -C "$root" branch --show-current) == development ]] ||
    refuse WRONG_BRANCH
  [[ $(git -C "$root" rev-parse HEAD) == "$baseline" ]] ||
    refuse HEAD_MISMATCH
  [[ $(git -C "$root" rev-parse origin/development) == "$baseline" ]] ||
    refuse ORIGIN_DEVELOPMENT_MISMATCH
  [[ -z $(git -C "$root" status --porcelain --untracked-files=all -- \
    "${d28202_critical[@]}") ]] || refuse LIVE_CRITICAL_DIRTY
}

prepare_d28202_candidate () {
  local baseline=$1 rpm_dir=$2
  verify_d28202_baseline "$baseline"
  prepare_candidate "$baseline" "$rpm_dir"
  {
    echo "D282_02_BASELINE_SHA=$baseline"
    echo D282_02_ENROLLMENT_CONTACT_COUNT=8
    echo D282_02_VERIFY_TRIAL_COUNT=4
    echo D282_02_BLOCK_COUNT=2
    echo D282_02_TRIALS_PER_BLOCK=2
    echo D282_02_PHYSICAL_FINGER=RIGHT_INDEX
    echo D282_02_SIGFM_THRESHOLD_EXPECTED=40
  } >"$prepared_candidate/d282-02-candidate.state"
  chmod 0600 "$prepared_candidate/d282-02-candidate.state"
  echo D282_02_CANDIDATE_PREPARED=true
  echo "D282_02_CANDIDATE_DIRECTORY=$prepared_candidate"
}

capture_d28202_failure () {
  local phase=$1 return_code=$2 evidence=$3 since=$4 baseline=$5 stamp=$6
  local user=$7 journal_file="$live_private/failure-journal.raw"

  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$journal_file" 2>&1 || true
  {
    echo "D282_02_FAILURE_PHASE=$phase"
    echo "D282_02_FAILURE_RETURN_CODE=$return_code"
    if [[ -f $evidence ]]; then
      sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" \
        "$evidence"
    fi
    grep -E 'GOODIX_(D282_EPOCH|SIGFM_MATCH|SIGFM_EXTRACT)_AUDIT|fprintd' \
      "$journal_file" |
      tail -n 300 |
      sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" || true
  } >>"$live_result/operator.log"
}

verify_daemon_map () {
  local label=$1 daemon_pid invocation_id
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse "DAEMON_PID_INVALID_${label}"
  invocation_id=$(systemctl show -p InvocationID --value fprintd.service)
  [[ $invocation_id =~ ^[0-9a-f]{32}$ ]] ||
    refuse "DAEMON_INVOCATION_ID_INVALID_${label}"
  grep -F "$live_runtime/libfprint-2.so.2.0.0" "/proc/$daemon_pid/maps" \
    >>"$live_private/maps" || refuse "DAEMON_LIBRARY_MAP_MISSING_${label}"
  [[ $(readlink -f "/proc/$daemon_pid/exe") == /usr/libexec/fprintd ]] ||
    refuse "DAEMON_EXE_DRIFT_${label}"
  verified_daemon_pid=$daemon_pid
  verified_daemon_invocation_id=$invocation_id
  echo "EXACT_LIBRARY_MAP_${label}=true" >>"$live_result/operator.log"
}

run_verify_trial () {
  local trial=$1 block=$2 position=$3 user=$4 since=$5 baseline=$6 stamp=$7
  local expected_pid=$8 expected_invocation_id=$9 current_pid current_invocation_id
  local stem raw journal meta cursor action_rc match_count no_match_count
  local retry_count match_audit extract_audit epoch_audit result

  stem=$(printf 'trial-%02d' "$trial")
  raw="$live_private/$stem.raw"
  journal="$live_private/$stem.journal.raw"
  meta="$live_private/$stem.meta"
  printf '\nTEST %02d/04 — BLOCCO %s, POSIZIONE %d/2\n\n' \
    "$trial" "$block" "$position"
  echo 'PROSSIMO CONTATTO:'
  echo '>>> INDICE DESTRO <<<'
  printf 'Premi INVIO, poi appoggia il dito: '
  read -r || refuse "TRIAL_${trial}_OPERATOR_NOT_READY"
  current_pid=$(systemctl show -p MainPID --value fprintd.service)
  current_invocation_id=$(systemctl show -p InvocationID --value fprintd.service)
  [[ $current_pid == "$expected_pid" &&
     $current_invocation_id == "$expected_invocation_id" ]] ||
    refuse "TRIAL_${trial}_PROCESS_BLOCK_DRIFT_PRE_ACTION"
  cursor=$(journalctl -u fprintd.service -n 0 --show-cursor --no-pager |
    sed -n 's/^-- cursor: //p')
  [[ -n $cursor ]] || refuse "TRIAL_${trial}_JOURNAL_CURSOR_MISSING"
  set +e
  timeout --signal=INT --kill-after=20s 180s \
    fprintd-verify "$user" >"$raw" 2>&1
  action_rc=$?
  set -e
  journalctl --sync
  journalctl -u fprintd.service --after-cursor="$cursor" --no-pager \
    >"$journal"
  {
    echo "TRIAL=$trial"
    echo "GLOBAL_ORDER=$trial"
    echo "BLOCK=$block"
    echo "BLOCK_POSITION=$position"
    echo PHYSICAL_FINGER=RIGHT_INDEX
    echo "DAEMON_PID=$expected_pid"
    echo "DAEMON_INVOCATION_ID=$expected_invocation_id"
    echo "ACTION_RETURN_CODE=$action_rc"
  } >"$meta"
  match_count=$(grep -c '^Verify result: verify-match (done)$' "$raw" || true)
  no_match_count=$(grep -c '^Verify result: verify-no-match (done)$' "$raw" || true)
  retry_count=$(grep -c 'verify-retry-' "$raw" || true)
  match_audit=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT event=outcome' "$journal" || true)
  extract_audit=$(grep -c 'GOODIX_SIGFM_EXTRACT_AUDIT keypoints=' "$journal" || true)
  epoch_audit=$(grep -c 'GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY' "$journal" || true)
  if [[ $retry_count -ne 0 || $match_audit -ne 1 || $extract_audit -ne 1 ||
        $epoch_audit -ne 1 ]]; then
    capture_d28202_failure "TRIAL_${trial}_TELEMETRY" "$action_rc" \
      "$raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  if [[ $action_rc -eq 0 && $match_count -eq 1 && $no_match_count -eq 0 ]]; then
    result=MATCH
  elif [[ $action_rc -eq 1 && $match_count -eq 0 && $no_match_count -eq 1 ]]; then
    result=NO_MATCH
  else
    capture_d28202_failure "TRIAL_${trial}_CLIENT_RESULT" "$action_rc" \
      "$raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  echo "RISULTATO TEST $(printf '%02d' "$trial"): $result"
}

run_d28202_live () {
  local candidate=$1 user=$2 state d282_state baseline manifest stamp since
  local target_count raw action_rc enroll_retry_count stored confirmation
  local epoch_count enroll_count verify_count cleanup_epoch_count
  local consumed_count attempts retry_count reopen_count reset_count
  local clear_halt_count persistent_count extract_count trial block position name
  local block_a_pid block_a_invocation_id block_b_pid block_b_invocation_id

  live_result=
  live_private=
  live_runtime=
  live_owned=
  live_storage_root=/var/lib/fprint
  live_dropin=/run/systemd/system/fprintd.service.d/90-goodix-d282-02.conf
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
  live_result_prefix=D282_02
  real_usb_enumeration_attempted=false
  real_sensor_accessed=false
  live_execution_performed=false
  staging_probe_execution_performed=false
  staging_probe_mode=false
  live_current_direct_mode=true

  [[ $EUID -eq 0 ]] || refuse LIVE_REQUIRES_ROOT
  state="$candidate/d282-02-candidate.state"
  d282_state="$candidate/d282-01-candidate.state"
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -f $state &&
     -f $d282_state && ! -L $candidate ]] || refuse CANDIDATE_INVALID
  baseline=$(state_value "$state" D282_02_BASELINE_SHA) || refuse CANDIDATE_STATE
  [[ $(state_value "$d282_state" D282_01_BASELINE_SHA) == "$baseline" ]] ||
    refuse CANDIDATE_BASELINE_DRIFT
  [[ $(state_value "$state" D282_02_ENROLLMENT_CONTACT_COUNT) == 8 &&
     $(state_value "$state" D282_02_VERIFY_TRIAL_COUNT) == 4 &&
     $(state_value "$state" D282_02_BLOCK_COUNT) == 2 &&
     $(state_value "$state" D282_02_TRIALS_PER_BLOCK) == 2 &&
     $(state_value "$state" D282_02_PHYSICAL_FINGER) == RIGHT_INDEX &&
     $(state_value "$state" D282_02_SIGFM_THRESHOLD_EXPECTED) == 40 ]] ||
    refuse EXPERIMENT_STATE_DRIFT
  verify_d28202_baseline "$baseline"
  manifest=$(state_value "$d282_state" D282_01_MANIFEST_SHA256) ||
    refuse CANDIDATE_STATE
  [[ $(sha256sum "$candidate/d282-01-artifacts.sha256" | awk '{print $1}') == "$manifest" ]] ||
    refuse MANIFEST_DRIFT
  (cd "$candidate" && sha256sum -c d282-01-artifacts.sha256) ||
    refuse ARTIFACT_DRIFT
  [[ $user =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || refuse OPERATOR_USER_INVALID
  getent passwd "$user" >/dev/null || refuse OPERATOR_USER_UNKNOWN
  [[ ${SUDO_USER:-$user} == "$user" ]] || refuse OPERATOR_USER_MISMATCH
  validate_live_tooling
  command -v stdbuf >/dev/null || refuse HOST_TOOL_MISSING_stdbuf
  [[ -x $root/analysis/D282/d282_02_trial_audit.py ]] ||
    refuse TRIAL_AUDITOR_INVALID

  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  live_result="/var/tmp/goodix-d282-02-results/${stamp}-${baseline:0:12}"
  echo "RISULTATI_PRIVATI=$live_result"
  live_runtime="/run/goodix-d282-02/${stamp}-${baseline:0:12}"
  live_owned="$live_storage_root/.goodix-d282-02-${stamp}-${baseline:0:12}"
  [[ ! -e $live_runtime && ! -e $live_owned && ! -e $live_dropin ]] ||
    refuse STAGING_COLLISION
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
  live_private="$live_result/private"
  install -d -m 0700 "$live_private" || refuse RESULT_DIRECTORY_CREATE_FAILED
  {
    echo D282_02_RESULT=FAIL_PENDING_AUDIT
    echo "D282_02_BASELINE_SHA=$baseline"
    echo D282_02_D283_LIVE_STANDBY=true
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
  } >"$live_result/summary.env" || refuse RESULT_SUMMARY_CREATE_FAILED
  chmod 0600 "$live_result/summary.env"
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
  "$d28201_script_dir/d282_storage_inventory.py" "$live_storage_root" \
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
  install -d -m 0700 "$live_runtime" "$live_owned" "$(dirname "$live_dropin")"
  install -m 0600 "$candidate"/*.so.* "$live_runtime/"
  ln -s libfprint-2.so.2.0.0 "$live_runtime/libfprint-2.so.2"
  ln -s libfprint-2.so.2 "$live_runtime/libfprint-2.so"
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
  : >"$live_result/operator.log"
  chmod 0600 "$live_result/operator.log"
  verify_daemon_map INITIAL

  printf '\nENROLLMENT — 8 CONTATTI\n\nUSA SOLO:\n>>> INDICE DESTRO <<<\n\n'
  printf 'Digita DESTRO per iniziare: '
  read -r confirmation || refuse ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED
  [[ $confirmation == DESTRO ]] || refuse ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED
  echo 'CONTATTO ENROLLMENT 01/08 — appoggia l’indice destro.'
  raw="$live_private/enroll.raw"
  : >"$raw"
  set +e
  timeout --signal=INT --kill-after=20s 1060s \
    stdbuf -oL -eL fprintd-enroll -f right-index-finger "$user" 2>&1 |
    while IFS= read -r name; do
      printf '%s\n' "$name" >>"$raw"
      if [[ $name == 'Enroll result: enroll-stage-passed' ]]; then
        action_rc=$(grep -c '^Enroll result: enroll-stage-passed$' "$raw" || true)
        printf 'CONTATTO COMPLETATO %02d/08\n' "$action_rc"
        printf 'PROSSIMO: CONTATTO %02d/08 — INDICE DESTRO\n' "$((action_rc + 1))"
      elif [[ $name == 'Enroll result: enroll-completed' ]]; then
        echo 'ENROLLMENT COMPLETATO 08/08'
      fi
    done
  action_rc=${PIPESTATUS[0]}
  set -e
  enroll_retry_count=$(grep -c 'enroll-retry-' "$raw" || true)
  if ! [[ $action_rc -eq 0 &&
          $(grep -c '^Enroll result: enroll-completed$' "$raw") -eq 1 &&
          $(grep -c '^Enroll result: enroll-stage-passed$' "$raw") -eq 7 &&
          $enroll_retry_count -eq 0 ]]; then
    capture_d28202_failure ENROLL "$action_rc" "$raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi
  if ! [[ $(find "$live_owned" -type l | wc -l) -eq 0 &&
          $(find "$live_owned" -type f | wc -l) -eq 1 ]]; then
    capture_d28202_failure ENROLL_STORAGE_AUDIT 1 "$raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi
  stored=$(find "$live_owned" -type f -print)
  if [[ $(head -c 3 "$stored") != FP3 ]]; then
    capture_d28202_failure ENROLL_FORMAT_AUDIT 1 "$raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi

  echo 'Preparazione BLOCCO A: restart controllato del daemon.'
  systemctl restart fprintd.service
  echo DAEMON_RESTART_AFTER_ENROLL=1 >>"$live_result/operator.log"
  verify_daemon_map BLOCK_A
  block_a_pid=$verified_daemon_pid
  block_a_invocation_id=$verified_daemon_invocation_id
  for trial in 1 2; do
    run_verify_trial "$trial" A "$trial" "$user" "$since" "$baseline" \
      "$stamp" "$block_a_pid" "$block_a_invocation_id"
  done
  echo 'Preparazione BLOCCO B: restart controllato del daemon.'
  systemctl restart fprintd.service
  echo DAEMON_RESTART_BETWEEN_BLOCKS=1 >>"$live_result/operator.log"
  verify_daemon_map BLOCK_B
  block_b_pid=$verified_daemon_pid
  block_b_invocation_id=$verified_daemon_invocation_id
  [[ $block_b_invocation_id != "$block_a_invocation_id" ]] ||
    refuse DAEMON_RESTART_INVOCATION_ID_UNCHANGED
  for trial in 3 4; do
    position=$((trial - 2))
    run_verify_trial "$trial" B "$position" "$user" "$since" "$baseline" \
      "$stamp" "$block_b_pid" "$block_b_invocation_id"
  done

  "$root/analysis/D282/d282_02_trial_audit.py" "$live_private" \
    "$live_result/trials.tsv" "$live_private/trial-summary.env" || {
      capture_d28202_failure TRIAL_AUDITOR 1 "$live_private/trial-04.journal.raw" \
        "$since" "$baseline" "$stamp" "$user"
      return 1
    }
  chmod 0600 "$live_result/trials.tsv" "$live_private/trial-summary.env"

  echo 'CLEANUP: eliminazione del solo template D282/02 isolato.'
  set +e
  fprintd-delete "$user" >"$live_private/delete.raw" 2>&1
  action_rc=$?
  set -e
  if [[ $action_rc -ne 0 || $(find "$live_owned" -type f | wc -l) -ne 0 ]]; then
    capture_d28202_failure HOST_ONLY_DELETE "$action_rc" \
      "$live_private/delete.raw" "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  journalctl --sync
  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$live_private/journal.raw"
  if ! grep GOODIX_D282_EPOCH_AUDIT "$live_private/journal.raw" \
      >"$live_private/audit.raw"; then
    capture_d28202_failure FINAL_AUDIT_MISSING 1 "$live_private/journal.raw" \
      "$since" "$baseline" "$stamp" "$user"
    return 1
  fi
  grep GOODIX_SIGFM_EXTRACT_AUDIT "$live_private/journal.raw" \
    >"$live_private/extract-audit.raw" || true
  grep GOODIX_SIGFM_MATCH_AUDIT "$live_private/journal.raw" \
    >"$live_private/matcher-audit.raw" || true
  extract_count=$(wc -l <"$live_private/extract-audit.raw")
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
  if ! [[ $epoch_count -eq 6 && $enroll_count -eq 1 && $verify_count -eq 4 &&
          $cleanup_epoch_count -eq 1 && $consumed_count -eq 5 && $attempts -eq 5 &&
          $retry_count -eq 0 && $reopen_count -eq 0 && $reset_count -eq 0 &&
          $clear_halt_count -eq 0 && $persistent_count -eq 0 &&
          $extract_count -eq 12 ]] ||
     [[ $(grep -c 'outstanding=0 drained=1 context_closed=1' "$live_private/audit.raw") -ne 6 ]] ||
     ! verify_current_live_epoch_audit "$live_private/audit.raw" 4; then
    capture_d28202_failure FINAL_AUDIT 1 "$live_private/audit.raw" "$since" \
      "$baseline" "$stamp" "$user"
    return 1
  fi
  for trial in 1 2 3 4; do
    name=$(printf 'trial-%02d' "$trial")
    {
      echo "BEGIN_${name}_EVIDENCE"
      cat "$live_private/$name.meta" "$live_private/$name.raw" \
        "$live_private/$name.journal.raw"
      echo "END_${name}_EVIDENCE"
    } >>"$live_result/operator.log"
  done
  {
    echo BEGIN_ENROLLMENT_EVIDENCE
    cat "$live_private/enroll.raw"
    echo END_ENROLLMENT_EVIDENCE
    echo BEGIN_FINAL_EPOCH_AUDIT
    cat "$live_private/audit.raw"
    echo END_FINAL_EPOCH_AUDIT
    echo BEGIN_SIGFM_EXTRACT_AUDIT
    cat "$live_private/extract-audit.raw"
    echo END_SIGFM_EXTRACT_AUDIT
    echo BEGIN_SIGFM_MATCH_AUDIT
    cat "$live_private/matcher-audit.raw"
    echo END_SIGFM_MATCH_AUDIT
  } >>"$live_result/operator.log"
  {
    echo D282_02_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
    echo "D282_02_BASELINE_SHA=$baseline"
    echo D282_02_D283_LIVE_STANDBY=true
    echo BIOMETRIC_ACTION_MAX=5
    echo EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=12
    echo ENROLL_ACTION_COUNT=1
    echo VERIFY_ACTION_COUNT=4
    echo PLANNED_VERIFY_SAMPLE_COUNT=4
    echo DAEMON_PROCESS_BLOCK_COUNT=2
    echo DAEMON_RESTART_COUNT=2
    echo "OPEN_EPOCH_COUNT=$epoch_count"
    echo "CONSUMED_BIOMETRIC_ACTION_COUNT=$consumed_count"
    echo "ACTION_ATTEMPT_COUNT=$attempts"
    echo "OBSERVED_RETRY_COUNT=$retry_count"
    echo "HIDDEN_REOPEN_COUNT=$reopen_count"
    echo "RESET_COUNT=$reset_count"
    echo "CLEAR_HALT_COUNT=$clear_halt_count"
    echo "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=$persistent_count"
    echo "SIGFM_EXTRACT_AUDIT_COUNT=$extract_count"
    echo "TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count"
    echo "TARGET_POSTSTART_MATCH_COUNT=$target_count"
    cat "$live_private/trial-summary.env"
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
    echo PAM_IN_SCOPE=false
  } >"$live_result/summary.env"
  chmod 0600 "$live_result/operator.log" "$live_result/summary.env"
  live_run_return_code=0
  echo "RISULTATI=$live_result"
}

export_d28202_results () {
  local result=$1 export name source_sha copy_sha
  [[ $EUID -eq 0 && ${SUDO_UID:-} =~ ^[0-9]+$ &&
     ${SUDO_GID:-} =~ ^[0-9]+$ ]] || refuse EXPORT_CALLER
  [[ $result == /var/tmp/goodix-d282-02-results/* && -d $result/private ]] ||
    refuse EXPORT_SOURCE
  export=$(mktemp -d /tmp/goodix-d282-02-export.XXXXXX)
  chmod 0700 "$export"
  for name in operator.log summary.env trials.tsv; do
    source_sha=$(sha256sum "$result/$name" | awk '{print $1}')
    install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" \
      "$result/$name" "$export/$name"
    copy_sha=$(sha256sum "$export/$name" | awk '{print $1}')
    [[ $source_sha == "$copy_sha" ]] || refuse EXPORT_HASH
    echo "${name}_SHA256=$source_sha"
  done
  chown "$SUDO_UID:$SUDO_GID" "$export"
  echo D282_02_RESULTS_EXPORT=PASS_BYTE_IDENTICAL
  echo "EXPORT_DIRECTORY=$export"
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
}

operator_d28202_run () {
  local rpm_dir=$1 user baseline transcript result output rc export_rc=1
  local confirmation
  [[ $EUID -ne 0 ]] || refuse OPERATOR_RUN_MUST_BE_UNPRIVILEGED
  command -v sudo >/dev/null || refuse HOST_TOOL_MISSING_sudo
  user=$(id -un) || refuse OPERATOR_USER_UNKNOWN
  baseline=$(git -C "$root" rev-parse HEAD) || refuse BASELINE_UNREADABLE
  verify_d28202_baseline "$baseline"
  trap cleanup_prepared_candidate EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  prepare_d28202_candidate "$baseline" "$rpm_dir"
  echo
  echo 'D282/02 usa 8 contatti enrollment + 4 VERIFY pianificate dello stesso dito.'
  echo 'Le VERIFY sono due coppie separate da restart; nessuna prova viene ripetuta.'
  echo 'D283/PAM resta in standby e non viene eseguito.'
  printf 'Digitare ESEGUI per avviare la singola run manuale: '
  read -r confirmation
  [[ $confirmation == ESEGUI ]] || refuse OPERATOR_CANCELLED
  transcript=$(mktemp /tmp/goodix-d282-02-operator.XXXXXX)
  chmod 0600 "$transcript"
  set +e
  sudo "$d28202_script_dir/run-d282-02.sh" --run-live "$prepared_candidate" \
    --user "$user" 2>&1 | tee "$transcript"
  rc=${PIPESTATUS[0]}
  set -e
  result=$(sed -n 's/^RISULTATI_PRIVATI=//p' "$transcript" | tail -n 1)
  if [[ -n $result ]]; then
    set +e
    output=$(sudo "$d28202_script_dir/run-d282-02.sh" --export-results "$result" 2>&1)
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
  local rpm_dir=$1 work telemetry
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  bash -n "$d28202_script_dir/run-d282-02.sh"
  (cd "$root" && python3 -m unittest -v \
    analysis.D282.test_d282_02_offline_contract \
    analysis.D282.test_d282_01_offline_contract \
    analysis.D283.test_d283_01_offline_contract)
  work=$(mktemp -d /tmp/goodix-d282-02-offline.XXXXXX)
  trap 'find "$work" -xdev -depth -delete 2>/dev/null || true' EXIT
  install -d -m 0700 "$work/candidate"
  build_candidate "$root" "$work/candidate" "$rpm_dir"
  abi_preflight "$work/candidate"
  telemetry="$work/sigfm-print.log"
  "$root/libfprint-driver/tests/run_goodix_fedora44_sigfm_print_test.sh" \
    >"$telemetry" 2>&1
  grep -F 'GOODIX_SIGFM_MATCH_AUDIT event=start' "$telemetry" >/dev/null
  grep -F 'GOODIX_SIGFM_MATCH_AUDIT event=comparison' "$telemetry" >/dev/null
  grep -F 'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match' "$telemetry" >/dev/null
  grep -F 'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=no_match' "$telemetry" >/dev/null
  echo D282_02_OFFLINE_PREFLIGHT=PASS
  echo D282_02_TELEMETRY_CHANGE_ONLY=true
  echo D282_02_ALGORITHM_CHANGE=false
  echo D282_02_PLANNED_VERIFY_SAMPLE_COUNT=4
  echo D282_02_DAEMON_PROCESS_BLOCK_COUNT=2
  echo D282_02_TRIALS_PER_BLOCK=2
  echo D282_02_BIOMETRIC_ACTION_MAX=5
  echo D282_02_EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=12
  echo D282_02_D283_LIVE_STANDBY=true
  echo D282_02_LIVE_READINESS=HUMAN_REQUIRED_OPERATOR_RUN
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo LIVE_EXECUTION_PERFORMED=false
  trap - EXIT
  find "$work" -xdev -depth -delete
}

case ${1:-} in
  --offline-preflight) [[ $# -eq 2 ]] || refuse USAGE; offline_preflight "$2" ;;
  --operator-run) [[ $# -eq 2 ]] || refuse USAGE; operator_d28202_run "$2" ;;
  --run-live) [[ $# -eq 4 && $3 == --user ]] || refuse USAGE; run_d28202_live "$2" "$4" ;;
  --export-results) [[ $# -eq 2 ]] || refuse USAGE; export_d28202_results "$2" ;;
  *) echo "Uso: $0 --offline-preflight <opencv-rpm-dir> | --operator-run <opencv-rpm-dir>" >&2; exit 2 ;;
esac
