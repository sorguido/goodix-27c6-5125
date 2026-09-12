#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

[[ $# -eq 5 ]] || exit 2
telemetry=$1
max_actions=$2
max_contacts=$3
max_retries=$4
expected=$5

get_one () {
  local key=$1 values
  values=$(sed -n "s/^${key}=//p" "$telemetry")
  [[ $(printf '%s\n' "$values" | sed '/^$/d' | wc -l) -eq 1 ]] || return 1
  printf '%s\n' "$values"
}

result=PASS
reason=NONE
for key in PAYLOAD_OUTCOME ACTION_ATTEMPT_COUNT CONTACT_COUNT RETRY_COUNT \
  MAX_ACTIONS_ENFORCED MAX_CONTACTS_ENFORCED MAX_RETRIES_ENFORCED \
  PERSISTENT_WRITE_FAMILY_COUNT OUTSTANDING_COUNT DRAINED_COUNT CONTEXT_CLOSED_COUNT; do
  value=$(get_one "$key" 2>/dev/null || true)
  if [[ -z $value ]]; then result=FAIL; reason="MISSING_OR_DUPLICATE_${key}"; break; fi
  printf -v "$key" '%s' "$value"
done

if [[ $result == PASS ]]; then
  for key in ACTION_ATTEMPT_COUNT CONTACT_COUNT RETRY_COUNT MAX_ACTIONS_ENFORCED \
    MAX_CONTACTS_ENFORCED MAX_RETRIES_ENFORCED PERSISTENT_WRITE_FAMILY_COUNT \
    OUTSTANDING_COUNT DRAINED_COUNT CONTEXT_CLOSED_COUNT; do
    [[ ${!key} =~ ^[0-9]+$ ]] || { result=FAIL; reason="NON_NUMERIC_${key}"; break; }
  done
fi
if [[ $result == PASS &&
      ( $MAX_ACTIONS_ENFORCED -ne $max_actions ||
        $MAX_CONTACTS_ENFORCED -ne $max_contacts ||
        $MAX_RETRIES_ENFORCED -ne $max_retries ) ]]; then
  result=FAIL; reason=PAYLOAD_BUDGET_HANDOFF_MISMATCH
elif [[ $result == PASS &&
        ( $ACTION_ATTEMPT_COUNT -gt $max_actions ||
          $CONTACT_COUNT -gt $max_contacts ||
          $RETRY_COUNT -gt $max_retries ) ]]; then
  result=FAIL; reason=PAYLOAD_BUDGET_EXCEEDED
elif [[ $result == PASS && $PERSISTENT_WRITE_FAMILY_COUNT -ne 0 ]]; then
  result=FAIL; reason=PERSISTENT_WRITE_FAMILY_OBSERVED
elif [[ $result == PASS &&
        ( $OUTSTANDING_COUNT -ne 0 || $DRAINED_COUNT -lt 1 ||
          $CONTEXT_CLOSED_COUNT -lt 1 ) ]]; then
  result=FAIL; reason=CLEANUP_TELEMETRY_INCOMPLETE
elif [[ $result == PASS ]]; then
  expected_match=false
  for expected_value in $expected; do
    [[ $PAYLOAD_OUTCOME != "$expected_value" ]] || expected_match=true
  done
  if [[ $expected_match != true ]]; then
    result=FAIL; reason=UNEXPECTED_PAYLOAD_OUTCOME
  fi
fi

echo "LIVE_PROBE_COMMON_CLASSIFICATION=$result"
echo "LIVE_PROBE_COMMON_CLASSIFICATION_REASON=$reason"
echo "LIVE_PROBE_PAYLOAD_OUTCOME=${PAYLOAD_OUTCOME:-UNKNOWN}"
echo "LIVE_PROBE_ACTION_ATTEMPT_COUNT=${ACTION_ATTEMPT_COUNT:-UNKNOWN}"
echo "LIVE_PROBE_CONTACT_COUNT=${CONTACT_COUNT:-UNKNOWN}"
echo "LIVE_PROBE_RETRY_COUNT=${RETRY_COUNT:-UNKNOWN}"
echo "LIVE_PROBE_PERSISTENT_WRITE_FAMILY_COUNT=${PERSISTENT_WRITE_FAMILY_COUNT:-UNKNOWN}"
echo "LIVE_PROBE_OUTSTANDING_COUNT=${OUTSTANDING_COUNT:-UNKNOWN}"
echo "LIVE_PROBE_DRAINED_COUNT=${DRAINED_COUNT:-UNKNOWN}"
echo "LIVE_PROBE_CONTEXT_CLOSED_COUNT=${CONTEXT_CLOSED_COUNT:-UNKNOWN}"
[[ $result == PASS ]]
