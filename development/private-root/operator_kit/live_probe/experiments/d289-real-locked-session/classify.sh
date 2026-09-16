#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
capture=${1:?}
grep -Fx LIVE_PROBE_COMMON_CLASSIFICATION=PASS "$capture/common-classification.env" >/dev/null

if grep -Fx 'LIVE_PROBE_MODE=offline-test' "$capture/context.env" >/dev/null; then
  grep -Fx LIVE_PROBE_PAYLOAD_OUTCOME=D289_OFFLINE_COMPATIBILITY_PASS "$capture/common-classification.env" >/dev/null
  grep -Fx D289_OFFLINE_PAYLOAD_COMPATIBILITY=PASS "$capture/payload.log" >/dev/null
  echo D289_PAYLOAD_CLASSIFICATION=PASS_OFFLINE
  exit 0
fi

details=$capture/payload-details.env
overlay=$capture/root-overlay.log
[[ -f $details && -f $overlay ]]
outcome=$(sed -n 's/^D289_SERIES_OUTCOME=//p' "$details")
attempts=$(sed -n 's/^D289_ATTEMPTS_PERFORMED=//p' "$details")
contacts=$(sed -n 's/^D289_CONTACTS_CONSUMED=//p' "$details")
matched=$(sed -n 's/^D289_MATCHED_ATTEMPT=//p' "$details")
cycles=$(sed -n 's/^D289_REAL_LOCK_CYCLES=//p' "$details")
[[ $attempts =~ ^[123]$ && $contacts == "$attempts" && $cycles == "$attempts" && $matched =~ ^[0-3]$ ]]
grep -Fx D289_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false "$details" >/dev/null
for marker in D289_ROOT_NAMESPACE_MATCH=true D289_ROOT_OVERLAY_READ_ONLY=true \
  D289_ROOT_OVERLAY_READY=true D289_ROOT_OVERLAY_UNMOUNTED=true \
  D289_USER_OVERLAY_VISIBLE_AND_PASSWORD_SERVICE_UNCHANGED=true \
  D289_ROOT_HOST_PAM_RESTORED=true D289_ROOT_RUNTIME_REMOVED=true; do
  [[ $(grep -Fxc "$marker" "$overlay") -eq $attempts ]]
done

for (( attempt=1; attempt<=attempts; attempt++ )); do
  state=$capture/attempt-$attempt-lock-state.env
  journal=$capture/attempt-$attempt-journal.log
  [[ -f $state && -f $journal ]]
  grep -Fx "D289_ATTEMPT=$attempt" "$state" >/dev/null
  grep -Fx D289_LOCK_ACTIVE_BEFORE=false "$state" >/dev/null
  grep -Fx D289_LOCK_ACTIVE_OBSERVED=true "$state" >/dev/null
  grep -Fx D289_GREETER_PARENT_KWIN=true "$state" >/dev/null
  grep -Fx D289_LOCK_ACTIVE_AFTER=false "$state" >/dev/null
  [[ $(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$journal") -eq 1 ]]
  result=$(sed -n 's/^D289_FINGERPRINT_RESULT=//p' "$state")
  if (( attempt == matched )); then
    [[ $result == match ]]
    grep -Fx D289_NON_FINGERPRINT_RECOVERY_AFTER_NO_MATCH=false "$state" >/dev/null
  else
    [[ $result == no_match ]]
    grep -Fx D289_NON_FINGERPRINT_RECOVERY_AFTER_NO_MATCH=true "$state" >/dev/null
  fi
done

if [[ $outcome == REAL_LOCK_MATCH ]]; then
  [[ $matched =~ ^[123]$ ]]
else
  [[ $outcome == REAL_LOCK_NO_MATCH_SERIES && $attempts -eq 3 && $matched -eq 0 ]]
fi
echo D289_PAYLOAD_CLASSIFICATION=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
