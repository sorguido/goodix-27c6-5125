#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
capture=${1:?}

if [[ ! -e $capture/payload.log && ! -e $capture/telemetry.env ]]; then
  if [[ -f $capture/pre-audit.log ]] &&
     [[ $(grep -Fxc D290_PRE_AUDIT=FAIL "$capture/pre-audit.log" || true) -eq 1 ]]; then
    echo D290_PAYLOAD_CLASSIFICATION=NOT_APPLICABLE_PRE_AUDIT_FAILURE
    exit 0
  fi
  echo D290_PAYLOAD_CLASSIFICATION=FAIL_PRE_PAYLOAD_STATE_UNEXPLAINED
  exit 1
fi

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
grep -Fx D290_INITIAL_GRAPHICAL_SESSION_TTY=tty2 "$state" >/dev/null
grep -Fx D290_INITIAL_GRAPHICAL_SESSION_SERVICE=plasmalogin "$state" >/dev/null
grep -Fx D290_INITIAL_GRAPHICAL_SESSION_TYPE=wayland "$state" >/dev/null
grep -Fx D290_INITIAL_GRAPHICAL_SESSION_CLASS=user "$state" >/dev/null
initial_state=$(sed -n 's/^D290_INITIAL_GRAPHICAL_SESSION_STATE=//p' "$state")
[[ $initial_state == active || $initial_state == online ]]
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
initial_session=$(sed -n 's/^D290_INITIAL_GRAPHICAL_SESSION=//p' "$state")
new_session=$(sed -n 's/^D290_NEW_GRAPHICAL_SESSION=//p' "$state")
if [[ $outcome == PLASMALOGIN_MATCH_NEW_SESSION ]]; then
  [[ $result == match ]]
  grep -Fx D290_NEW_GRAPHICAL_SESSION_CREATED=true "$state" >/dev/null
  [[ -n $initial_session && -n $new_session && $new_session != NONE && $new_session != "$initial_session" ]]
  grep -Fx D290_NEW_GRAPHICAL_SESSION_SERVICE=plasmalogin "$state" >/dev/null
  grep -Fx D290_NEW_GRAPHICAL_SESSION_TYPE=wayland "$state" >/dev/null
  grep -Fx D290_NEW_GRAPHICAL_SESSION_CLASS=user "$state" >/dev/null
  new_tty=$(sed -n 's/^D290_NEW_GRAPHICAL_SESSION_TTY=//p' "$state")
  new_state=$(sed -n 's/^D290_NEW_GRAPHICAL_SESSION_STATE=//p' "$state")
  [[ $new_tty =~ ^tty[0-9]+$ && $new_tty != tty3 ]]
  [[ $new_state == active || $new_state == online ]]
else
  [[ $outcome == PLASMALOGIN_NO_MATCH_PASSWORD_RECOVERY_READY && $result == no_match ]]
  grep -Fx D290_NEW_GRAPHICAL_SESSION=NONE "$state" >/dev/null
  grep -Fx D290_NEW_GRAPHICAL_SESSION_CREATED=false "$state" >/dev/null
  for field in TTY SERVICE TYPE CLASS STATE; do
    grep -Fx "D290_NEW_GRAPHICAL_SESSION_${field}=NONE" "$state" >/dev/null
  done
fi
echo D290_PAYLOAD_CLASSIFICATION=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
