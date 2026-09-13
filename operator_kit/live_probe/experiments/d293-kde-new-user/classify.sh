#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
capture=${1:?}

one() {
  local key=$1 file=$2 values
  [[ -f $file && ! -L $file ]] || return 1
  values=$(sed -n "s/^${key}=//p" "$file")
  [[ $(printf '%s\n' "$values" | sed '/^$/d' | wc -l) -eq 1 && -n $values ]] || return 1
  printf '%s\n' "$values"
}
require_exact() { [[ $(grep -Fxc "$1" "$2") -eq 1 ]]; }
audit_count() { grep -c '^GOODIX_PRODUCTION_EPOCH_AUDIT ' "$1" || true; }
strict_action_count() {
  local action=$1 file=$2
  local output rc=0
  output=$(awk -v action="$action" '
    BEGIN { invalid=0 }
    /^GOODIX_PRODUCTION_EPOCH_AUDIT / {
      action_hits=0
      for (i=1; i<=NF; i++) {
        split($i, a, "=")
        if (a[1] == "action") { action_hits++; if (a[2] == action) count++ }
      }
      if (action_hits != 1) invalid=1
    }
    END { if (invalid) exit 2; print count+0 }
  ' "$file") || rc=$?
  [[ $rc -eq 0 && $output =~ ^[0-9]+$ ]] || return 1
  action_count_result=$output
}

if grep -Fx LIVE_PROBE_MODE=offline-test "$capture/context.env" >/dev/null; then
  grep -Fx LIVE_PROBE_COMMON_CLASSIFICATION=PASS "$capture/common-classification.env" >/dev/null
  grep -Fx LIVE_PROBE_PAYLOAD_OUTCOME=D293_04_OFFLINE_COMPATIBILITY_PASS \
    "$capture/common-classification.env" >/dev/null
  grep -Fx D293_04_OFFLINE_PAYLOAD_COMPATIBILITY=PASS "$capture/payload.log" >/dev/null
  echo D293_04_PAYLOAD_CLASSIFICATION=PASS_OFFLINE
  exit 0
fi

details=$capture/payload-details.env
if [[ -f $details ]] && grep -Fx D293_04_OUTCOME=DUPLICATE_RECOGNIZED_STOP "$details" >/dev/null; then
  require_exact D293_04_DUPLICATE_CHECK_PRESERVED=true "$details"
  require_exact D293_04_KCM_ENROLLMENT_COUNT=0 "$details"
  [[ -f $capture/enroll-journal.log && $(audit_count "$capture/enroll-journal.log") -eq 1 ]]
  strict_action_count FPI_DEVICE_ACTION_IDENTIFY "$capture/enroll-journal.log"
  [[ $action_count_result -eq 1 ]]
  strict_action_count FPI_DEVICE_ACTION_ENROLL "$capture/enroll-journal.log"
  [[ $action_count_result -eq 0 ]]
  echo D293_04_PAYLOAD_CLASSIFICATION=DUPLICATE_RECOGNIZED_STOP
  exit 1
fi

grep -Fx LIVE_PROBE_COMMON_CLASSIFICATION=PASS "$capture/common-classification.env" >/dev/null
for file in "$details" "$capture/enroll-journal.log" "$capture/delete-journal.log" "$capture/runtime-audit.env" \
    "$capture/runtime-provenance.env" "$capture/telemetry.env"; do
  [[ -f $file && ! -L $file ]]
done
for marker in \
  D293_04_KCM_DEVICE_DETECTION_CONFIRMED=true \
  D293_04_DUPLICATE_CHECK_PRESERVED=true \
  D293_04_PHYSICAL_FINGER_NOT_PREVIOUSLY_ENROLLED_CONFIRMED=true \
  D293_04_KCM_RELEASE_BEFORE_VERIFY=true \
  D293_04_KCM_REOPENED_FOR_DELETE=true \
  D293_04_KCM_ENROLLMENT_COUNT=1 D293_04_KCM_DELETE_COUNT=1 \
  D293_04_INITIAL_FINGER_COUNT=0 D293_04_ENROLLED_FINGER_COUNT=1 \
  D293_04_FINAL_FINGER_COUNT=0 D293_04_STOP_ON_FIRST_MATCH=true \
  D293_04_FOURTH_ATTEMPT_ALLOWED=false D293_04_TRANSPORT_RETRY_COUNT=0 \
  D293_04_ENROLLMENT_BIOMETRIC_REPEAT_BUDGET_MAX=20 \
  D293_04_VERIFY_ACTION_BUDGET_PRECHECKED=true \
  D293_04_GUI_OPERATION_COUNT_CONTROL=OPERATOR_PROTOCOL \
  D293_04_GUI_SESSION_HARD_CAP_REQUIRED=false \
  D293_04_PER_ACTION_TECHNICAL_FENCES=UNCHANGED \
  D293_04_VERIFY_SERIES_CONTROL=SCRIPT_BOUNDED \
  D293_04_RUN_TOTALS_CHECK=OBSERVED_PROTOCOL_BOUNDS \
  D293_04_EXTRA_MANUAL_UI_ACTION=PROTOCOL_DEVIATION_STOP; do
  require_exact "$marker" "$details"
done
attempts=$(one D293_04_VERIFY_ATTEMPTS "$details")
matched=$(one D293_04_MATCHED_ATTEMPT "$details")
contacts=$(one D293_04_ENROLLMENT_PHASE_CONTACT_COUNT "$details")
[[ $attempts =~ ^[123]$ && $matched =~ ^[123]$ && $matched -eq $attempts ]]
[[ $contacts =~ ^([89]|1[0-9]|20)$ && $((1 + contacts + attempts)) -le 24 ]]
grep -Fx "ACTION_ATTEMPT_COUNT=$((2 + attempts))" "$capture/telemetry.env" >/dev/null
grep -Fx "CONTACT_COUNT=$((1 + contacts + attempts))" "$capture/telemetry.env" >/dev/null
grep -Fx "DRAINED_COUNT=$((2 + attempts))" "$capture/telemetry.env" >/dev/null
grep -Fx "CONTEXT_CLOSED_COUNT=$((2 + attempts))" "$capture/telemetry.env" >/dev/null
grep -Fx D293_04_OBSERVATION_COMPLETE=true "$capture/telemetry.env" >/dev/null
for marker in \
  GUI_OPERATION_COUNT_CONTROL=OPERATOR_PROTOCOL \
  GUI_SESSION_HARD_CAP_REQUIRED=false \
  PER_ACTION_TECHNICAL_FENCES=UNCHANGED \
  VERIFY_SERIES_CONTROL=SCRIPT_BOUNDED \
  RUN_TOTALS_CHECK=OBSERVED_PROTOCOL_BOUNDS \
  EXTRA_MANUAL_UI_ACTION=PROTOCOL_DEVIATION_STOP \
  MAX_ACTIONS_ENFORCEMENT_SCOPE=OBSERVED_PROTOCOL_ACCEPTANCE; do
  require_exact "$marker" "$capture/telemetry.env"
done

head=$(one D293_04_PRODUCTION_HEAD "$capture/runtime-provenance.env")
library_sha=$(one D293_04_LIBRARY_SHA256 "$capture/runtime-provenance.env")
run_id=$(one D293_04_RUN_ID "$capture/runtime-provenance.env")
[[ $head =~ ^[0-9a-f]{40}$ && $library_sha =~ ^[0-9a-f]{64}$ &&
   $run_id =~ ^d293-04-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]]
[[ $(one LIVE_PROBE_BASELINE "$capture/context.env") == "$head" ]]
runtime_marker="D293_04_RUNTIME_AUDIT head=$head library_sha=$library_sha manifest=pass run_id=$run_id"
require_exact "$runtime_marker" "$capture/runtime-audit.env"
[[ $(wc -l <"$capture/runtime-audit.env") -eq 1 ]]
[[ $(audit_count "$capture/enroll-journal.log") -eq 2 ]]
strict_action_count FPI_DEVICE_ACTION_IDENTIFY "$capture/enroll-journal.log"
[[ $action_count_result -eq 1 ]]
strict_action_count FPI_DEVICE_ACTION_ENROLL "$capture/enroll-journal.log"
[[ $action_count_result -eq 1 ]]
for (( attempt=1; attempt<=attempts; attempt++ )); do
  file=$capture/verify-$attempt-journal.log
  [[ -f $file && ! -L $file && $(audit_count "$file") -eq 1 ]]
  strict_action_count FPI_DEVICE_ACTION_VERIFY "$file"
  [[ $action_count_result -eq 1 ]]
done
[[ $(audit_count "$capture/delete-journal.log") -eq 0 ]]
grep -Fx D293_04_RUNTIME_ROLLBACK=PASS "$capture/cleanup.log" >/dev/null
grep -Fx D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=true "$capture/cleanup.log" >/dev/null
grep -Fx D293_04_TEST_STORAGE_CLEAN=true "$capture/cleanup.log" >/dev/null
echo D293_04_PAYLOAD_CLASSIFICATION=PASS_LIVE
