#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

max_actions= max_contacts= max_retries= timeout_seconds=
while [[ $# -gt 0 ]]; do
  case $1 in
    --max-actions) max_actions=$2; shift 2;;
    --max-contacts) max_contacts=$2; shift 2;;
    --max-retries) max_retries=$2; shift 2;;
    --timeout-seconds) timeout_seconds=$2; shift 2;;
    *) exit 2;;
  esac
done
[[ $max_actions == 5 && $max_contacts == 24 && $max_retries == 0 && $timeout_seconds == 1800 ]]
work=${LIVE_PROBE_WORK_DIR:?}; capture=${LIVE_PROBE_CAPTURE_DIR:?}; telemetry=${LIVE_PROBE_TELEMETRY_FILE:?}
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
user=d293-phase-b-test

write_telemetry() {
  local outcome=$1 actions=$2 contacts=$3 drained=$4
  cat >"$telemetry" <<EOF
PAYLOAD_OUTCOME=$outcome
ACTION_ATTEMPT_COUNT=$actions
CONTACT_COUNT=$contacts
RETRY_COUNT=0
MAX_ACTIONS_ENFORCED=$max_actions
MAX_CONTACTS_ENFORCED=$max_contacts
MAX_RETRIES_ENFORCED=$max_retries
PERSISTENT_WRITE_FAMILY_COUNT=0
OUTSTANDING_COUNT=0
DRAINED_COUNT=$drained
CONTEXT_CLOSED_COUNT=$drained
EOF
}
if [[ ${LIVE_PROBE_MODE:-} == offline-test ]]; then
  [[ -x $here/prepare.sh && -x $here/root-helper.sh && -x $here/recover.sh ]]
  write_telemetry D293_04_OFFLINE_COMPATIBILITY_PASS 0 0 1
  echo D293_04_OFFLINE_PAYLOAD_COMPATIBILITY=PASS
  exit 0
fi

current_cursor() {
  local output cursor
  output=$(LC_ALL=C journalctl -b -n 0 --show-cursor --no-pager)
  cursor=$(sed -n 's/^-- cursor: //p' <<<"$output")
  [[ $(sed '/^$/d' <<<"$cursor" | wc -l) -eq 1 ]]
  printf '%s\n' "$cursor"
}
collect_since() {
  journalctl -b -u fprintd.service --after-cursor "$1" --no-pager -o short-iso-precise |
    "$here/sanitize.sh" >"$2"
}
field_sum() {
  awk -v key="$1" '/GOODIX_PRODUCTION_EPOCH_AUDIT / { for(i=1;i<=NF;i++){split($i,a,"="); if(a[1]==key && a[2]~/^[0-9]+$/)s+=a[2]}} END{print s+0}' "$2"
}
finger_count() {
  local file=$work/list.out rc=0
  fprintd-list "$user" >"$file" 2>&1 || rc=$?
  if grep -Eq 'No fingerprints for|No enrolled fingerprints|NoEnrolledPrints' "$file"; then echo 0; return; fi
  [[ $rc -eq 0 ]] || return 1
  grep -c '^ - #' "$file" || true
}
action_field() {
  local action=$1 key=$2 file=$3
  awk -v action="$action" -v key="$key" '
    /GOODIX_PRODUCTION_EPOCH_AUDIT / {
      selected=0
      for (i=1; i<=NF; i++) {
        split($i, a, "=")
        if (a[1] == "action" && a[2] == action) selected=1
      }
      if (selected) {
        lines++
        for (i=1; i<=NF; i++) {
          split($i, a, "=")
          if (a[1] == key && a[2] ~ /^[0-9]+$/) { values++; value=a[2] }
        }
      }
    }
    END { if (lines == 1 && values == 1) print value; else exit 1 }
  ' "$file"
}
verify_epoch() {
  local file=$1
  [[ $(grep -c 'GOODIX_PRODUCTION_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$file" || true) -eq 1 ]]
  [[ $(field_sum attempts "$file") -eq 1 && $(field_sum consumed "$file") -eq 1 &&
     $(field_sum tls "$file") -eq 1 && $(field_sum first_image "$file") -eq 1 &&
     $(field_sum secure_retry "$file") -eq 0 && $(field_sum post_retry "$file") -eq 0 &&
     $(field_sum reopen "$file") -eq 0 && $(field_sum reset "$file") -eq 0 &&
     $(field_sum clear_halt "$file") -eq 0 && $(field_sum persistent "$file") -eq 0 &&
     $(field_sum outstanding "$file") -eq 0 && $(field_sum drained "$file") -eq 1 &&
     $(field_sum context_closed "$file") -eq 1 ]]
}

[[ $(id -un) == "$user" ]]
runtime_cursor=$(current_cursor)
initial_finger_count=$(finger_count)
[[ $initial_finger_count -eq 0 ]]
collect_since "$runtime_cursor" "$work/runtime-journal.log"
cp "$work/runtime-journal.log" "$capture/runtime-journal.log"
production_head=$(sed -n 's/^D293_04_PRODUCTION_HEAD=//p' /run/goodix-d293-04-public/public.env)
library_sha=$(sed -n 's/^D293_04_LIBRARY_SHA256=//p' /run/goodix-d293-04-public/public.env)
[[ $production_head =~ ^[0-9a-f]{40}$ && $library_sha =~ ^[0-9a-f]{64}$ ]]
grep -Fx "D293_04_RUNTIME_AUDIT head=$production_head library_sha=$library_sha manifest=pass" \
  "$work/runtime-journal.log" >/dev/null
enroll_cursor=$(current_cursor)
/usr/bin/systemsettings kcm_users >/dev/null 2>&1 &
kcm_pid=$!; echo "$kcm_pid" >"$work/kcm.pid"
sleep 2; kill -0 "$kcm_pid"
printf '%s\n' \
  'Nel KCM Users appena aperto verificare che il lettore sia visibile.' \
  'Registrare UNA sola impronta (indice destro) seguendo la UI.' \
  'Non usare fprintd-enroll o altri strumenti. Non inserire password in questo terminale.' \
  'Al completamento digitare: ENROLLMENT KCM COMPLETATO'
IFS= read -r confirmation
[[ $confirmation == 'ENROLLMENT KCM COMPLETATO' ]]
[[ $(finger_count) -eq 1 ]]
collect_since "$enroll_cursor" "$work/enroll-journal.log"
cp "$work/enroll-journal.log" "$capture/enroll-journal.log"
[[ $(grep -c 'GOODIX_PRODUCTION_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_IDENTIFY' "$work/enroll-journal.log" || true) -eq 1 ]]
[[ $(grep -c 'GOODIX_PRODUCTION_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_ENROLL' "$work/enroll-journal.log" || true) -eq 1 ]]
[[ $(grep -c 'GOODIX_PRODUCTION_EPOCH_AUDIT ' "$work/enroll-journal.log" || true) -eq 2 ]]
enroll_contacts=$(action_field FPI_DEVICE_ACTION_ENROLL enroll_contacts "$work/enroll-journal.log")
enroll_retry_scans=$(action_field FPI_DEVICE_ACTION_ENROLL enroll_retry_scans "$work/enroll-journal.log")
[[ $enroll_contacts =~ ^[0-9]+$ && $enroll_contacts -ge 8 && $enroll_contacts -le 20 ]]
[[ $enroll_retry_scans =~ ^[0-9]+$ && $enroll_retry_scans -le 12 ]]
[[ $(field_sum enroll_stages "$work/enroll-journal.log") -eq 8 &&
   $(field_sum first_image "$work/enroll-journal.log") -eq 2 &&
   $(field_sum secure_retry "$work/enroll-journal.log") -eq 0 &&
   $(field_sum post_retry "$work/enroll-journal.log") -eq 0 &&
   $(field_sum reopen "$work/enroll-journal.log") -eq 0 &&
   $(field_sum reset "$work/enroll-journal.log") -eq 0 &&
   $(field_sum clear_halt "$work/enroll-journal.log") -eq 0 &&
   $(field_sum persistent "$work/enroll-journal.log") -eq 0 &&
   $(field_sum outstanding "$work/enroll-journal.log") -eq 0 &&
   $(field_sum drained "$work/enroll-journal.log") -eq 2 &&
   $(field_sum context_closed "$work/enroll-journal.log") -eq 2 ]]

attempts=0; matched=0
for attempt in 1 2 3; do
  (( attempts < 3 && 1 + enroll_contacts + attempts < max_contacts ))
  if (( attempt > 1 )); then
    printf 'Il tentativo precedente era NO_MATCH. Per procedere digitare TENTATIVO %d: ' "$attempt"
    IFS= read -r confirmation; [[ $confirmation == "TENTATIVO $attempt" ]]
  fi
  printf 'Tentativo %d/3: appoggiare una sola volta l’impronta registrata.\n' "$attempt"
  cursor=$(current_cursor); rc=0
  fprintd-verify "$user" >"$work/verify-$attempt.out" 2>&1 || rc=$?
  attempts=$((attempts + 1))
  collect_since "$cursor" "$work/verify-$attempt-journal.log"
  verify_epoch "$work/verify-$attempt-journal.log"
  cp "$work/verify-$attempt-journal.log" "$capture/verify-$attempt-journal.log"
  if grep -Fx 'Verify result: verify-match (done)' "$work/verify-$attempt.out" >/dev/null; then
    [[ $rc -eq 0 ]]; matched=$attempt; break
  fi
  grep -Fx 'Verify result: verify-no-match (done)' "$work/verify-$attempt.out" >/dev/null
done

printf '%s\n' \
  'Nel medesimo KCM Users cancellare ora l’unica impronta del nuovo utente.' \
  'La cancellazione è parte del cleanup e non deve essere eseguita da CLI.' \
  'Quando la UI mostra zero impronte digitare: IMPRONTA KCM CANCELLATA'
IFS= read -r confirmation
[[ $confirmation == 'IMPRONTA KCM CANCELLATA' && $(finger_count) -eq 0 ]]
printf 'Chiudere System Settings e digitare KCM CHIUSO: '
IFS= read -r confirmation; [[ $confirmation == 'KCM CHIUSO' ]]
for _ in $(seq 1 50); do kill -0 "$kcm_pid" 2>/dev/null || break; sleep 0.1; done
if kill -0 "$kcm_pid" 2>/dev/null; then kill "$kcm_pid"; wait "$kcm_pid" || true; fi

outcome=KDE_NEW_USER_NO_MATCH_SERIES
[[ $matched -eq 0 ]] || outcome=KDE_NEW_USER_MATCH
cat >"$capture/payload-details.env" <<EOF
D293_04_KCM_DEVICE_DETECTION_CONFIRMED=true
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
EOF
write_telemetry "$outcome" "$((2 + attempts))" "$((1 + enroll_contacts + attempts))" "$((2 + attempts))"
echo "D293_04_PAYLOAD_OUTCOME=$outcome"
[[ $matched -gt 0 ]]
