#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
capture=${1:?}
grep -Fx LIVE_PROBE_COMMON_CLASSIFICATION=PASS "$capture/common-classification.env" >/dev/null
if grep -Fx 'LIVE_PROBE_MODE=offline-test' "$capture/context.env" >/dev/null; then
  grep -Fx LIVE_PROBE_PAYLOAD_OUTCOME=D288_OFFLINE_COMPATIBILITY_PASS "$capture/common-classification.env" >/dev/null
  grep -Fx D288_OFFLINE_PAYLOAD_COMPATIBILITY=PASS "$capture/payload.log" >/dev/null
  echo D288_PAYLOAD_CLASSIFICATION=PASS_OFFLINE
else
  details=$capture/payload-details.env
  [[ -f $details ]]
  outcome=$(sed -n 's/^D288_SERIES_OUTCOME=//p' "$details")
  attempts=$(sed -n 's/^D288_ATTEMPTS_PERFORMED=//p' "$details")
  contacts=$(sed -n 's/^D288_CONTACTS_CONSUMED=//p' "$details")
  matched=$(sed -n 's/^D288_MATCHED_ATTEMPT=//p' "$details")
  [[ $attempts =~ ^[123]$ && $contacts == "$attempts" && $matched =~ ^[0-3]$ ]]
  if [[ $outcome == KSCREENLOCKER_MATCH ]]; then
    [[ $matched =~ ^[123]$ ]]
  else
    [[ $outcome == KSCREENLOCKER_NO_MATCH_SERIES && $attempts -eq 3 && $matched -eq 0 ]]
  fi
  grep -Fx D288_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false "$details" >/dev/null
  echo D288_PAYLOAD_CLASSIFICATION=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
fi
