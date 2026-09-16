#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

max_actions= max_contacts= max_retries= timeout_seconds=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-actions) max_actions=$2; shift 2 ;;
    --max-contacts) max_contacts=$2; shift 2 ;;
    --max-retries) max_retries=$2; shift 2 ;;
    --timeout-seconds) timeout_seconds=$2; shift 2 ;;
    *) exit 2 ;;
  esac
done
[[ $max_actions == 1 && $max_contacts == 1 && $max_retries == 0 && $timeout_seconds == 5 ]]
[[ ${LIVE_PROBE_MODE:-} == offline-test ]]
[[ -n ${LIVE_PROBE_TELEMETRY_FILE:-} ]]
cat >"$LIVE_PROBE_TELEMETRY_FILE" <<EOF
PAYLOAD_OUTCOME=OFFLINE_REFERENCE_PASS
ACTION_ATTEMPT_COUNT=0
CONTACT_COUNT=0
RETRY_COUNT=0
MAX_ACTIONS_ENFORCED=$max_actions
MAX_CONTACTS_ENFORCED=$max_contacts
MAX_RETRIES_ENFORCED=$max_retries
PERSISTENT_WRITE_FAMILY_COUNT=0
OUTSTANDING_COUNT=0
DRAINED_COUNT=1
CONTEXT_CLOSED_COUNT=1
EOF
echo LIVE_PROBE_OFFLINE_REFERENCE_PAYLOAD=PASS
