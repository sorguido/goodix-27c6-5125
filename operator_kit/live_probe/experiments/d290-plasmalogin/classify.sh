#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
capture=${1:?}
grep -Fx LIVE_PROBE_COMMON_CLASSIFICATION=PASS "$capture/common-classification.env" >/dev/null

if grep -Fx 'LIVE_PROBE_MODE=offline-test' "$capture/context.env" >/dev/null; then
  grep -Fx LIVE_PROBE_PAYLOAD_OUTCOME=D290_OFFLINE_COMPATIBILITY_PASS "$capture/common-classification.env" >/dev/null
  grep -Fx D290_OFFLINE_PAYLOAD_COMPATIBILITY=PASS "$capture/payload.log" >/dev/null
  echo D290_PAYLOAD_CLASSIFICATION=PASS_OFFLINE
  exit 0
fi

details=$capture/payload-details.env
state=$capture/login-state.env
finger=$capture/fprintd-attempt.log
overlay=$capture/root-overlay.log
[[ -f $details && -f $state && -f $finger && -f $overlay ]]
grep -Fx D290_ATTEMPTS_PERFORMED=1 "$details" >/dev/null
grep -Fx D290_CONTACTS_CONSUMED=1 "$details" >/dev/null
grep -Fx D290_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false "$details" >/dev/null
grep -Fx D290_OVERLAY_RELEASED_BEFORE_PASSWORD_RECOVERY=true "$details" >/dev/null
grep -Fx D290_INITIAL_GRAPHICAL_LOGOUT_OBSERVED=true "$state" >/dev/null
grep -Fx D290_PASSWORD_OR_PIN_USED_DURING_FINGERPRINT=NOT_MACHINE_TELEMETERED "$state" >/dev/null
[[ $(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$finger") -eq 1 ]]
for marker in D290_ROOT_DAEMON_IDENTITY=true D290_ROOT_NAMESPACE_MATCH=true \
  D290_ROOT_OVERLAY_READ_ONLY=true D290_ROOT_OVERLAY_READY=true \
  D290_USER_OVERLAY_VISIBLE=true D290_ROOT_OVERLAY_UNMOUNTED=true \
  D290_ROOT_HOST_PAM_RESTORED=true D290_ROOT_RUNTIME_REMOVED=true; do
  [[ $(grep -Fxc "$marker" "$overlay") -eq 1 ]]
done

outcome=$(sed -n 's/^D290_OUTCOME=//p' "$details")
result=$(sed -n 's/^D290_FINGERPRINT_RESULT=//p' "$state")
if [[ $outcome == PLASMALOGIN_MATCH_NEW_SESSION ]]; then
  [[ $result == match ]]
  grep -Fx D290_NEW_GRAPHICAL_SESSION_CREATED=true "$state" >/dev/null
  ! grep -Fx D290_NEW_GRAPHICAL_SESSION=NONE "$state" >/dev/null
else
  [[ $outcome == PLASMALOGIN_NO_MATCH_PASSWORD_RECOVERY_READY && $result == no_match ]]
  grep -Fx D290_NEW_GRAPHICAL_SESSION=NONE "$state" >/dev/null
  grep -Fx D290_NEW_GRAPHICAL_SESSION_CREATED=false "$state" >/dev/null
fi
echo D290_PAYLOAD_CLASSIFICATION=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
