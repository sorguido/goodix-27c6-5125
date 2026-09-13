#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
capture=${1:?}
grep -Fx LIVE_PROBE_COMMON_CLASSIFICATION=PASS "$capture/common-classification.env" >/dev/null
if grep -Fx LIVE_PROBE_MODE=offline-test "$capture/context.env" >/dev/null; then
  grep -Fx LIVE_PROBE_PAYLOAD_OUTCOME=D293_04_OFFLINE_COMPATIBILITY_PASS "$capture/common-classification.env" >/dev/null
  grep -Fx D293_04_OFFLINE_PAYLOAD_COMPATIBILITY=PASS "$capture/payload.log" >/dev/null
  echo D293_04_PAYLOAD_CLASSIFICATION=PASS_OFFLINE
  exit 0
fi
details=$capture/payload-details.env
[[ -f $details && -f $capture/enroll-journal.log && -f $capture/runtime-journal.log ]]
for marker in \
  D293_04_KCM_DEVICE_DETECTION_CONFIRMED=true \
  D293_04_KCM_ENROLLMENT_COUNT=1 D293_04_KCM_DELETE_COUNT=1 \
  D293_04_INITIAL_FINGER_COUNT=0 D293_04_ENROLLED_FINGER_COUNT=1 \
  D293_04_FINAL_FINGER_COUNT=0 D293_04_STOP_ON_FIRST_MATCH=true \
  D293_04_FOURTH_ATTEMPT_ALLOWED=false D293_04_TRANSPORT_RETRY_COUNT=0 \
  D293_04_ENROLLMENT_BIOMETRIC_REPEAT_BUDGET_MAX=20; do
  grep -Fx "$marker" "$details" >/dev/null
done
attempts=$(sed -n 's/^D293_04_VERIFY_ATTEMPTS=//p' "$details")
matched=$(sed -n 's/^D293_04_MATCHED_ATTEMPT=//p' "$details")
contacts=$(sed -n 's/^D293_04_ENROLLMENT_PHASE_CONTACT_COUNT=//p' "$details")
[[ $attempts =~ ^[123]$ && $matched =~ ^[123]$ && $matched -eq $attempts ]]
[[ $contacts =~ ^([89]|1[0-9]|20)$ && $((1 + contacts + attempts)) -le 24 ]]
grep -Fx "ACTION_ATTEMPT_COUNT=$((2 + attempts))" "$capture/telemetry.env" >/dev/null
grep -Fx "CONTACT_COUNT=$((1 + contacts + attempts))" "$capture/telemetry.env" >/dev/null
grep -Fx "DRAINED_COUNT=$((2 + attempts))" "$capture/telemetry.env" >/dev/null
grep -Fx "CONTEXT_CLOSED_COUNT=$((2 + attempts))" "$capture/telemetry.env" >/dev/null
head=$(sed -n 's/^D293_04_PRODUCTION_HEAD=//p' /run/goodix-d293-04-public/public.env)
library_sha=$(sed -n 's/^D293_04_LIBRARY_SHA256=//p' /run/goodix-d293-04-public/public.env)
grep -Fx "D293_04_RUNTIME_AUDIT head=$head library_sha=$library_sha manifest=pass" \
  "$capture/runtime-journal.log" >/dev/null
[[ $(grep -c 'GOODIX_PRODUCTION_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_IDENTIFY' "$capture/enroll-journal.log") -eq 1 ]]
[[ $(grep -c 'GOODIX_PRODUCTION_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_ENROLL' "$capture/enroll-journal.log") -eq 1 ]]
for (( attempt=1; attempt<=attempts; attempt++ )); do
  [[ -f $capture/verify-$attempt-journal.log ]]
  [[ $(grep -c 'GOODIX_PRODUCTION_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$capture/verify-$attempt-journal.log") -eq 1 ]]
done
grep -Fx D293_04_RUNTIME_ROLLBACK=PASS "$capture/cleanup.log" >/dev/null
grep -Fx D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=true "$capture/cleanup.log" >/dev/null
grep -Fx D293_04_TEST_STORAGE_CLEAN=true "$capture/cleanup.log" >/dev/null
echo D293_04_PAYLOAD_CLASSIFICATION=PASS_LIVE
