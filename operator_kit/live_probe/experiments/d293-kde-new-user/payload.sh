#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -eEuo pipefail

max_actions= max_contacts= max_retries= timeout_seconds=
while [[ $# -gt 0 ]]; do
  case $1 in
    --max-actions) max_actions=$2; shift 2 ;;
    --max-contacts) max_contacts=$2; shift 2 ;;
    --max-retries) max_retries=$2; shift 2 ;;
    --timeout-seconds) timeout_seconds=$2; shift 2 ;;
    *) printf 'D293_04_PAYLOAD=FAIL phase=arguments reason=unknown_argument\n' >&2; exit 2 ;;
  esac
done
[[ $max_actions == 5 && $max_contacts == 24 && $max_retries == 0 &&
   $timeout_seconds == 1800 ]] || {
  printf 'D293_04_PAYLOAD=FAIL phase=arguments reason=budget_handoff\n' >&2
  exit 2
}

work=${LIVE_PROBE_WORK_DIR:?}
capture=${LIVE_PROBE_CAPTURE_DIR:?}
telemetry=${LIVE_PROBE_TELEMETRY_FILE:?}
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
user=d293-phase-b-test
public=${D293_04_PUBLIC_ROOT:-/run/goodix-d293-04-public}
systemsettings_command=/usr/bin/systemsettings
fprintd_list_command=/usr/bin/fprintd-list
fprintd_verify_command=/usr/bin/fprintd-verify
ui_start_delay=2
control_poll_delay=0.1
if [[ ${LIVE_PROBE_MODE:-} == offline-script-test ]]; then
  test_commands=${D293_04_TEST_COMMAND_DIR:-}
  [[ $test_commands == /tmp/d293-04-script-test.* && -d $test_commands &&
     ! -L $test_commands && -O $test_commands ]] || {
    printf 'D293_04_PAYLOAD=FAIL phase=initialization reason=offline_test_command_root_invalid\n' >&2
    exit 2
  }
  for command in systemsettings fprintd-list fprintd-verify; do
    [[ -f $test_commands/$command && ! -L $test_commands/$command &&
       -x $test_commands/$command && -O $test_commands/$command ]] || {
      printf 'D293_04_PAYLOAD=FAIL phase=initialization reason=offline_test_command_invalid\n' >&2
      exit 2
    }
  done
  user=$(id -un)
  systemsettings_command=$test_commands/systemsettings
  fprintd_list_command=$test_commands/fprintd-list
  fprintd_verify_command=$test_commands/fprintd-verify
  ui_start_delay=0.02
  control_poll_delay=0.01
elif [[ ${LIVE_PROBE_MODE:-} != offline-test && ${LIVE_PROBE_MODE:-} != operator-run ]]; then
  printf 'D293_04_PAYLOAD=FAIL phase=initialization reason=mode_invalid\n' >&2
  exit 2
fi
control=$public/control
results=$public/results
phase=initialization
failure_reason=unexpected_exit
telemetry_final=false
actions_observed=0
contacts_observed=0
drained_observed=0
counts_known=true

write_telemetry() {
  local outcome=$1 complete=$2 outstanding=$3
  local tmp=$telemetry.tmp retry=UNKNOWN persistent=UNKNOWN
  local actions=$actions_observed contacts=$contacts_observed drained=$drained_observed
  if [[ $counts_known != true ]]; then
    actions=UNKNOWN
    contacts=UNKNOWN
    drained=UNKNOWN
    outstanding=UNKNOWN
  fi
  if [[ $complete == true ]]; then retry=0; persistent=0; fi
  {
    printf 'PAYLOAD_OUTCOME=%s\n' "$outcome"
    printf 'ACTION_ATTEMPT_COUNT=%s\n' "$actions"
    printf 'CONTACT_COUNT=%s\n' "$contacts"
    printf 'RETRY_COUNT=%s\n' "$retry"
    printf 'MAX_ACTIONS_ENFORCED=%s\n' "$max_actions"
    printf 'MAX_CONTACTS_ENFORCED=%s\n' "$max_contacts"
    printf 'MAX_RETRIES_ENFORCED=%s\n' "$max_retries"
    printf 'GUI_OPERATION_COUNT_CONTROL=OPERATOR_PROTOCOL\n'
    printf 'GUI_SESSION_HARD_CAP_REQUIRED=false\n'
    printf 'PER_ACTION_TECHNICAL_FENCES=UNCHANGED\n'
    printf 'VERIFY_SERIES_CONTROL=SCRIPT_BOUNDED\n'
    printf 'RUN_TOTALS_CHECK=OBSERVED_PROTOCOL_BOUNDS\n'
    printf 'EXTRA_MANUAL_UI_ACTION=PROTOCOL_DEVIATION_STOP\n'
    printf 'MAX_ACTIONS_ENFORCEMENT_SCOPE=OBSERVED_PROTOCOL_ACCEPTANCE\n'
    printf 'PERSISTENT_WRITE_FAMILY_COUNT=%s\n' "$persistent"
    printf 'OUTSTANDING_COUNT=%s\n' "$outstanding"
    printf 'DRAINED_COUNT=%s\n' "$drained"
    printf 'CONTEXT_CLOSED_COUNT=%s\n' "$drained"
    printf 'D293_04_OBSERVATION_COMPLETE=%s\n' "$complete"
    printf 'D293_04_FAILURE_PHASE=%s\n' "$phase"
    printf 'D293_04_FAILURE_REASON=%s\n' "$failure_reason"
  } >"$tmp"
  mv -f -- "$tmp" "$telemetry"
}

fail() {
  failure_reason=$1
  printf 'D293_04_PAYLOAD=FAIL phase=%s reason=%s cleanup=pending\n' \
    "$phase" "$failure_reason" >&2
  exit "${2:-1}"
}

on_exit() {
  local rc=$?
  if [[ $telemetry_final != true ]]; then
    write_telemetry D293_04_INCOMPLETE false UNKNOWN || true
    printf 'D293_04_PARTIAL_TELEMETRY=RECORDED phase=%s reason=%s rc=%d\n' \
      "$phase" "$failure_reason" "$rc" >&2
  fi
}
trap on_exit EXIT

if [[ ${LIVE_PROBE_MODE:-} == offline-test ]]; then
  phase=offline
  failure_reason=NONE
  drained_observed=1
  [[ -x $here/prepare.sh && -x $here/root-helper.sh && -x $here/recover.sh ]] ||
    fail offline_executable_missing
  write_telemetry D293_04_OFFLINE_COMPATIBILITY_PASS true 0
  telemetry_final=true
  echo D293_04_OFFLINE_PAYLOAD_COMPATIBILITY=PASS
  exit 0
fi

one_from_file() {
  local key=$1 file=$2 values
  [[ -f $file && ! -L $file ]] || return 1
  values=$(sed -n "s/^${key}=//p" "$file")
  [[ $(printf '%s\n' "$values" | sed '/^$/d' | wc -l) -eq 1 && -n $values ]] ||
    return 1
  printf '%s\n' "$values"
}

prompt_confirmation() {
  local expected=$1
  printf 'Digitare esattamente: %s\n' "$expected"
  printf 'RISPOSTA_ATTESA=%s\n' "$expected"
  IFS= read -r confirmation || fail terminal_input_closed
  [[ $confirmation == "$expected" ]] || fail operator_confirmation_mismatch
}

wait_regular_file() {
  local file=$1
  for _ in $(seq 1 200); do
    [[ -f $file && ! -L $file ]] && return 0
    sleep "$control_poll_delay"
  done
  return 1
}

control_request() {
  local request=$1 ack
  ack=$results/$request.env
  [[ $request =~ ^(arm-enroll|finish-enroll|arm-verify-[123]|finish-verify-[123]|complete-verify|arm-delete|finish-delete)$ ]] ||
    fail control_request_invalid
  [[ -d $control && -O $control && ! -e $control/$request && ! -L $control/$request ]] ||
    fail control_channel_invalid
  : >"$control/$request"
  wait_regular_file "$ack" || fail "control_${request}_timeout"
  [[ $(one_from_file D293_04_CONTROL "$ack") == "$request" &&
     $(one_from_file D293_04_CONTROL_RESULT "$ack") == PASS ]] ||
    fail "control_${request}_rejected"
}

strict_finger_count() {
  local label=$1 file rc=0 found header zero rows other
  finger_count_result=
  file=$work/list-$label.out
  LC_ALL=C "$fprintd_list_command" "$user" >"$file" 2>&1 || rc=$?
  [[ $rc -eq 0 ]] || {
    if grep -Eqi 'PermissionDenied|Not Authorized|not authorized|permission denied' "$file"; then
      failure_reason=list_permission_denied
    elif grep -Eqi 'No devices available|NoDevice|Impossible to get devices' "$file"; then
      failure_reason=list_no_device
    elif grep -Eqi 'Failed to connect|service.*not|D-Bus|DBus' "$file"; then
      failure_reason=list_service_or_dbus_error
    else
      failure_reason=list_technical_error
    fi
    return 1
  }
  found=$(grep -c '^found 1 devices$' "$file" || true)
  [[ $found -eq 1 && $(grep -c '^Using device ' "$file" || true) -eq 1 ]] || {
    failure_reason=list_device_cardinality_or_format
    return 1
  }
  zero=$(grep -Ec "^User ${user} has no fingers enrolled for .+\.$" "$file" || true)
  header=$(grep -Ec "^Fingerprints for user ${user} on .+ \((press|swipe)\):$" "$file" || true)
  rows=$(grep -Ec '^ - #[0-9]+: (left-thumb|left-index-finger|left-middle-finger|left-ring-finger|left-little-finger|right-thumb|right-index-finger|right-middle-finger|right-ring-finger|right-little-finger)$' "$file" || true)
  other=$(grep -Ec '^User .* has no fingers enrolled|^Fingerprints for user |^ - #' "$file" || true)
  if [[ $zero -eq 1 && $header -eq 0 && $rows -eq 0 && $other -eq 1 ]]; then
    finger_count_result=0
  elif [[ $zero -eq 0 && $header -eq 1 && $rows -ge 1 && $other -eq $((1 + rows)) ]]; then
    finger_count_result=$rows
  else
    failure_reason=list_malformed_output
    return 1
  fi
}

audit_count() { grep -c '^GOODIX_PRODUCTION_EPOCH_AUDIT ' "$1" || true; }

strict_action_count() {
  local action=$1 file=$2
  local output rc=0
  output=$(awk -v action="$action" '
    BEGIN { invalid=0 }
    /^GOODIX_PRODUCTION_EPOCH_AUDIT / {
      hits=0
      for (i=1; i<=NF; i++) {
        split($i, a, "=")
        if (a[1] == "action") { hits++; if (a[2] == action) count++ }
      }
      if (hits != 1) invalid=1
    }
    END { if (invalid) exit 2; print count+0 }
  ' "$file") || rc=$?
  [[ $rc -eq 0 && $output =~ ^[0-9]+$ ]] || return 1
  action_count_result=$output
}

audit_sum() {
  local key=$1 expected_lines=$2 file=$3
  awk -v key="$key" -v expected="$expected_lines" '
    /^GOODIX_PRODUCTION_EPOCH_AUDIT / {
      lines++; hits=0
      for (i=1; i<=NF; i++) {
        split($i, a, "=")
        if (a[1] == key) {
          hits++
          if (a[2] !~ /^[0-9]+$/) exit 2
          sum += a[2]
        }
      }
      if (hits != 1) exit 2
    }
    END { if (lines != expected) exit 3; print sum }
  ' "$file"
}

action_field() {
  local action=$1 key=$2 file=$3
  awk -v action="$action" -v key="$key" '
    /^GOODIX_PRODUCTION_EPOCH_AUDIT / {
      selected=0; action_hits=0
      for (i=1; i<=NF; i++) {
        split($i, a, "=")
        if (a[1] == "action") { action_hits++; if (a[2] == action) selected=1 }
      }
      if (action_hits != 1) exit 2
      if (selected) {
        lines++
        for (i=1; i<=NF; i++) {
          split($i, a, "=")
          if (a[1] == key) {
            values++
            if (a[2] !~ /^[0-9]+$/) exit 2
            value=a[2]
          }
        }
      }
    }
    END { if (lines == 1 && values == 1) print value; else exit 3 }
  ' "$file"
}

verify_epoch() {
  local file=$1 key value
  [[ $(audit_count "$file") -eq 1 ]] || return 1
  strict_action_count FPI_DEVICE_ACTION_VERIFY "$file" || return 1
  [[ $action_count_result -eq 1 ]] || return 1
  for key in attempts consumed tls first_image drained context_closed; do
    value=$(audit_sum "$key" 1 "$file") || return 1
    [[ $value -eq 1 ]] || return 1
  done
  for key in secure_retry post_retry reopen reset clear_halt persistent outstanding; do
    value=$(audit_sum "$key" 1 "$file") || return 1
    [[ $value -eq 0 ]] || return 1
  done
}

close_kcm() {
  local label=$1
  phase=kcm_release
  printf '%s\n' \
    'Premere il pulsante finale di completamento nella UI, poi chiudere normalmente tutta la finestra Impostazioni di sistema.' \
    'Il kit non riavvia fprintd e non termina forzatamente il KCM.'
  prompt_confirmation "KCM CHIUSO DOPO $label"
  for _ in $(seq 1 100); do
    if ! kill -0 "$kcm_pid" 2>/dev/null; then
      wait "$kcm_pid" 2>/dev/null || true
      return 0
    fi
    sleep "$control_poll_delay"
  done
  fail kcm_process_still_holds_session
}

copy_result() {
  local source=$1 destination=$2
  [[ -f $results/$source && ! -L $results/$source ]] || fail "result_${source}_missing"
  cp -- "$results/$source" "$capture/$destination"
}

phase=preflight
[[ $(id -un) == "$user" ]] || fail wrong_test_account
public_env=$public/public.env
[[ $(one_from_file D293_04_PHASE "$public_env") == READY_FOR_NEW_USER ]] || fail runtime_not_ready
production_head=$(one_from_file D293_04_PRODUCTION_HEAD "$public_env") || fail production_head_missing
library_sha=$(one_from_file D293_04_LIBRARY_SHA256 "$public_env") || fail library_sha_missing
run_id=$(one_from_file D293_04_RUN_ID "$public_env") || fail run_id_missing
expected_capture_root=$(one_from_file D293_04_CAPTURE_ROOT "$public_env") || fail capture_root_missing
[[ $production_head =~ ^[0-9a-f]{40}$ && $library_sha =~ ^[0-9a-f]{64}$ &&
   $run_id =~ ^d293-04-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ &&
   $expected_capture_root == "$(dirname -- "$(dirname -- "$capture")")" ]] ||
  fail public_provenance_invalid

strict_finger_count initial || fail "$failure_reason"
initial_finger_count=$finger_count_result
[[ $initial_finger_count -eq 0 ]] || fail initial_finger_count_not_zero
wait_regular_file "$results/runtime-audit.env" || fail runtime_audit_missing
runtime_marker="D293_04_RUNTIME_AUDIT head=$production_head library_sha=$library_sha manifest=pass run_id=$run_id"
[[ $(grep -Fxc "$runtime_marker" "$results/runtime-audit.env") -eq 1 &&
   $(wc -l <"$results/runtime-audit.env") -eq 1 ]] || fail runtime_audit_invalid
copy_result runtime-audit.env runtime-audit.env
cat >"$capture/runtime-provenance.env" <<EOF
D293_04_PRODUCTION_HEAD=$production_head
D293_04_LIBRARY_SHA256=$library_sha
D293_04_RUN_ID=$run_id
EOF

phase=enrollment_arm
control_request arm-enroll
counts_known=false
"$systemsettings_command" kcm_users >/dev/null 2>&1 &
kcm_pid=$!
printf '%s\n' "$kcm_pid" >"$work/kcm.pid"
sleep "$ui_start_delay"
kill -0 "$kcm_pid" 2>/dev/null || fail kcm_failed_to_start
phase=enrollment_ui
printf '%s\n' \
  'Nel KCM Users verificare che il lettore sia visibile.' \
  'Scegliere UNA sola impronta fisica che non sia già registrata da alcun account su questa macchina.' \
  'Il nome del dito scelto nella GUI non prova che il dito fisico sia libero: la scelta è dell’operatore.' \
  'Il primo contatto esegue il duplicate-check globale IDENTIFY; non disabilitarlo e non riprovare con lo stesso dito se è segnalato duplicato.' \
  'Completare una sola enrollment guidata. Password e autorizzazioni restano soltanto nella UI KDE.' \
  'Se la UI segnala un duplicato digitare DUPLICATO RILEVATO; altrimenti digitare ENROLLMENT KCM COMPLETATO.'
printf '%s\n' 'RISPOSTA_ATTESA=ENROLLMENT KCM COMPLETATO oppure DUPLICATO RILEVATO'
IFS= read -r confirmation || fail terminal_input_closed
[[ $confirmation == 'ENROLLMENT KCM COMPLETATO' || $confirmation == 'DUPLICATO RILEVATO' ]] ||
  fail operator_confirmation_mismatch
enrollment_result=$confirmation
close_kcm ENROLLMENT
phase=enrollment_collect
control_request finish-enroll
copy_result enroll-journal.log enroll-journal.log
enroll_log=$capture/enroll-journal.log

if [[ $enrollment_result == 'DUPLICATO RILEVATO' ]]; then
  [[ $(audit_count "$enroll_log") -eq 1 ]] || fail duplicate_audit_inconsistent
  strict_action_count FPI_DEVICE_ACTION_IDENTIFY "$enroll_log" || fail duplicate_audit_inconsistent
  [[ $action_count_result -eq 1 ]] || fail duplicate_audit_inconsistent
  strict_action_count FPI_DEVICE_ACTION_ENROLL "$enroll_log" || fail duplicate_audit_inconsistent
  [[ $action_count_result -eq 0 ]] || fail duplicate_audit_inconsistent
  actions_observed=1
  contacts_observed=$(audit_sum first_image 1 "$enroll_log") || fail duplicate_contact_missing
  drained_observed=$(audit_sum drained 1 "$enroll_log") || fail duplicate_drain_missing
  for key in secure_retry post_retry persistent outstanding; do
    value=$(audit_sum "$key" 1 "$enroll_log") || fail "duplicate_${key}_missing"
    [[ $value -eq 0 ]] || fail "duplicate_${key}_invalid"
  done
  counts_known=true
  cat >"$capture/payload-details.env" <<EOF
D293_04_OUTCOME=DUPLICATE_RECOGNIZED_STOP
D293_04_DUPLICATE_CHECK_PRESERVED=true
D293_04_KCM_ENROLLMENT_COUNT=0
D293_04_KCM_DELETE_COUNT=0
EOF
  phase=duplicate_stop
  failure_reason=duplicate_recognized_no_retry
  write_telemetry D293_04_DUPLICATE_RECOGNIZED true 0
  telemetry_final=true
  fail duplicate_recognized_no_retry 20
fi

strict_finger_count enrolled || fail "$failure_reason"
enrolled_finger_count=$finger_count_result
[[ $enrolled_finger_count -eq 1 ]] || fail enrolled_finger_count_not_one
[[ $(audit_count "$enroll_log") -eq 2 ]] || fail enrollment_action_cardinality
strict_action_count FPI_DEVICE_ACTION_IDENTIFY "$enroll_log" || fail enrollment_action_cardinality
[[ $action_count_result -eq 1 ]] || fail enrollment_action_cardinality
strict_action_count FPI_DEVICE_ACTION_ENROLL "$enroll_log" || fail enrollment_action_cardinality
[[ $action_count_result -eq 1 ]] || fail enrollment_action_cardinality
enroll_contacts=$(action_field FPI_DEVICE_ACTION_ENROLL enroll_contacts "$enroll_log") ||
  fail enrollment_contacts_missing
enroll_retry_scans=$(action_field FPI_DEVICE_ACTION_ENROLL enroll_retry_scans "$enroll_log") ||
  fail enrollment_retry_scans_missing
[[ $enroll_contacts -ge 8 && $enroll_contacts -le 20 &&
   $enroll_retry_scans -le 12 ]] || fail enrollment_budget_invalid
for key_value in \
  'enroll_stages 8' 'first_image 1' 'secure_retry 0' 'post_retry 0' \
  'reopen 0' 'reset 0' 'clear_halt 0' 'persistent 0' 'outstanding 0' \
  'drained 2' 'context_closed 2'; do
  read -r key expected <<<"$key_value"
  value=$(audit_sum "$key" 2 "$enroll_log") || fail "enrollment_${key}_missing"
  [[ $value -eq $expected ]] || fail "enrollment_${key}_invalid"
done
actions_observed=2
contacts_observed=$((1 + enroll_contacts))
drained_observed=2
counts_known=true
(( actions_observed <= max_actions && contacts_observed <= max_contacts )) ||
  fail enrollment_session_budget_exceeded

phase=verify
attempts=0
matched=0
for attempt in 1 2 3; do
  (( actions_observed + 1 <= max_actions && contacts_observed + 1 <= max_contacts )) ||
    fail verify_pre_action_budget_exhausted
  if (( attempt > 1 )); then
    printf '%s\n' 'Il tentativo precedente era NO_MATCH. Non viene eseguito alcun retry automatico.'
    prompt_confirmation "TENTATIVO $attempt"
  fi
  control_request "arm-verify-$attempt"
  printf 'Tentativo %d/3: appoggiare una sola volta l’impronta registrata.\n' "$attempt"
  counts_known=false
  rc=0
  LC_ALL=C "$fprintd_verify_command" "$user" >"$work/verify-$attempt.out" 2>&1 || rc=$?
  control_request "finish-verify-$attempt"
  copy_result "verify-$attempt-journal.log" "verify-$attempt-journal.log"
  verify_epoch "$capture/verify-$attempt-journal.log" || fail verify_epoch_invalid
  attempts=$attempt
  actions_observed=$((actions_observed + 1))
  contacts_observed=$((contacts_observed + 1))
  drained_observed=$((drained_observed + 1))
  counts_known=true
  if grep -Fx 'Verify result: verify-match (done)' "$work/verify-$attempt.out" >/dev/null; then
    [[ $rc -eq 0 ]] || fail verify_match_return_code
    matched=$attempt
    break
  fi
  if grep -Fx 'Verify result: verify-no-match (done)' "$work/verify-$attempt.out" >/dev/null; then
    continue
  fi
  if grep -Eqi 'AlreadyInUse|already claimed|Device.*busy|device.*busy' "$work/verify-$attempt.out"; then
    fail verify_device_busy
  elif grep -Eqi 'PermissionDenied|Not Authorized|not authorized|permission denied' "$work/verify-$attempt.out"; then
    fail verify_permission_denied
  fi
  fail verify_technical_error
done
control_request complete-verify

phase=delete_ui
control_request arm-delete
counts_known=false
"$systemsettings_command" kcm_users >/dev/null 2>&1 &
kcm_pid=$!
printf '%s\n' "$kcm_pid" >"$work/kcm.pid"
sleep "$ui_start_delay"
kill -0 "$kcm_pid" 2>/dev/null || fail delete_kcm_failed_to_start
printf '%s\n' \
  'Il KCM è stato riaperto soltanto dopo il rilascio usato dalla verifica.' \
  'Cancellare dalla UI l’unica impronta del nuovo utente; non usare comandi CLI.' \
  'Quando la UI mostra zero impronte digitare IMPRONTA KCM CANCELLATA.'
prompt_confirmation 'IMPRONTA KCM CANCELLATA'
close_kcm DELETE
phase=delete_check
control_request finish-delete
copy_result delete-journal.log delete-journal.log
[[ $(audit_count "$capture/delete-journal.log") -eq 0 ]] || fail unexpected_action_during_delete
strict_finger_count final || fail "$failure_reason"
final_finger_count=$finger_count_result
[[ $final_finger_count -eq 0 ]] || fail final_finger_count_not_zero
counts_known=true

outcome=KDE_NEW_USER_NO_MATCH_SERIES
[[ $matched -eq 0 ]] || outcome=KDE_NEW_USER_MATCH
cat >"$capture/payload-details.env" <<EOF
D293_04_OUTCOME=$outcome
D293_04_KCM_DEVICE_DETECTION_CONFIRMED=true
D293_04_DUPLICATE_CHECK_PRESERVED=true
D293_04_PHYSICAL_FINGER_NOT_PREVIOUSLY_ENROLLED_CONFIRMED=true
D293_04_KCM_RELEASE_BEFORE_VERIFY=true
D293_04_KCM_REOPENED_FOR_DELETE=true
D293_04_KCM_ENROLLMENT_COUNT=1
D293_04_KCM_DELETE_COUNT=1
D293_04_INITIAL_FINGER_COUNT=0
D293_04_ENROLLED_FINGER_COUNT=1
D293_04_FINAL_FINGER_COUNT=0
D293_04_ENROLLMENT_PHASE_CONTACT_COUNT=$enroll_contacts
D293_04_VERIFY_ATTEMPTS=$attempts
D293_04_MATCHED_ATTEMPT=$matched
D293_04_STOP_ON_FIRST_MATCH=true
D293_04_FOURTH_ATTEMPT_ALLOWED=false
D293_04_TRANSPORT_RETRY_COUNT=0
D293_04_ENROLLMENT_BIOMETRIC_REPEAT_BUDGET_MAX=20
D293_04_VERIFY_ACTION_BUDGET_PRECHECKED=true
D293_04_GUI_OPERATION_COUNT_CONTROL=OPERATOR_PROTOCOL
D293_04_GUI_SESSION_HARD_CAP_REQUIRED=false
D293_04_PER_ACTION_TECHNICAL_FENCES=UNCHANGED
D293_04_VERIFY_SERIES_CONTROL=SCRIPT_BOUNDED
D293_04_RUN_TOTALS_CHECK=OBSERVED_PROTOCOL_BOUNDS
D293_04_EXTRA_MANUAL_UI_ACTION=PROTOCOL_DEVIATION_STOP
EOF
phase=complete
failure_reason=NONE
write_telemetry "$outcome" true 0
telemetry_final=true
echo "D293_04_PAYLOAD_OUTCOME=$outcome"
[[ $matched -gt 0 ]] || fail no_match_series_terminal 21
trap - EXIT
exit 0
