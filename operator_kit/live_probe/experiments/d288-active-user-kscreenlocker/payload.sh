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
[[ $max_actions == 3 && $max_contacts == 3 && $max_retries == 0 && $timeout_seconds == 240 ]]
work=${LIVE_PROBE_WORK_DIR:?}
capture=${LIVE_PROBE_CAPTURE_DIR:?}
telemetry=${LIVE_PROBE_TELEMETRY_FILE:?}
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
shim=$work/pam-start-redirect.so
pam_dir=$work/live-pam
pid_file=$work/greeter.pid
attempts=0 contacts=0 matched=0 outcome=D288_OFFLINE_COMPATIBILITY_PASS

stop_greeter () {
  if [[ -f $pid_file ]]; then
    pid=$(<"$pid_file")
    if [[ $pid =~ ^[0-9]+$ ]]; then
      kill -TERM -- "-$pid" 2>/dev/null || true
      for _ in {1..25}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
      kill -KILL -- "-$pid" 2>/dev/null || true
      for _ in {1..10}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
      wait "$pid" 2>/dev/null || true
      ! kill -0 "$pid" 2>/dev/null
    fi
    rm -f -- "$pid_file"
  fi
}
trap 'stop_greeter; exit 130' HUP INT TERM
trap stop_greeter EXIT

if [[ ${LIVE_PROBE_MODE:-} == offline-test ]]; then
  [[ -f $shim && ! -L $shim ]]
  cat >"$telemetry" <<EOF
PAYLOAD_OUTCOME=$outcome
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
  echo D288_OFFLINE_PAYLOAD_COMPATIBILITY=PASS
  exit 0
fi

[[ ${LIVE_PROBE_MODE:-} == operator-run && -f $shim && ! -L $shim ]]
[[ $(id -u) -ne 0 ]]
[[ ${XDG_SESSION_TYPE:-} == wayland && -n ${WAYLAND_DISPLAY:-} ]]
mkdir -m 0700 "$pam_dir"
install -m 0600 "$here/goodix-d288-kde-fingerprint.pam" "$pam_dir/kde-fingerprint"
[[ $(sha256sum "$pam_dir/kde-fingerprint" | awk '{print $1}') == 126af52cd63c346fdf9fb053172506a49f851d45b0a49e4490fd807a12c328b6 ]]

current_cursor () {
  local output cursor
  output=$(LC_ALL=C journalctl -b -n 0 --show-cursor --no-pager)
  cursor=$(sed -n 's/^-- cursor: //p' <<<"$output")
  [[ $(sed '/^$/d' <<<"$cursor" | wc -l) -eq 1 ]]
  printf '%s\n' "$cursor"
}

collect_attempt () {
  journalctl -b -u fprintd.service --after-cursor "$1" --no-pager -o short-iso-precise |
    "$here/sanitize.sh" >"$2"
}

field_sum () {
  local key=$1 file=$2
  awk -v key="$key" '/GOODIX_D282_EPOCH_AUDIT / { for (i=1;i<=NF;i++) { split($i,a,"="); if (a[1]==key && a[2]~/^[0-9]+$/) s+=a[2] } } END { print s+0 }' "$file"
}

for attempt in 1 2 3; do
  (( attempts < max_actions && contacts < max_contacts ))
  if (( attempt > 1 )); then
    printf 'NO_MATCH precedente. Per il contatto %d/3 digitare TENTATIVO %d: ' "$attempt" "$attempt"
    IFS= read -r confirmation
    [[ $confirmation == "TENTATIVO $attempt" ]]
  fi
  cursor=$(current_cursor)
  greeter_log=$work/greeter-$attempt.log
  journal_log=$work/journal-$attempt.log
  setsid env GOODIX_D288_PAM_CONFDIR="$pam_dir" LD_PRELOAD="$shim" \
    /usr/libexec/kscreenlocker_greet --testing >"$greeter_log" 2>&1 &
  greeter_pid=$!
  echo "$greeter_pid" >"$pid_file"
  deadline=$((SECONDS + 20))
  until grep -F 'Locked at ' "$greeter_log" >/dev/null 2>&1; do
    kill -0 "$greeter_pid" 2>/dev/null || exit 4
    (( SECONDS < deadline )) || exit 4
    sleep 0.1
  done
  greeter_pgid=$(ps -o pgid= -p "$greeter_pid" | tr -d ' ')
  greeter_cgroup=$(awk -F: 'NR==1 {print $NF}' "/proc/$greeter_pid/cgroup")
  [[ $greeter_pgid == "$greeter_pid" ]]
  case "$greeter_cgroup" in /user.slice/user-0.slice/*|/system.slice/*) exit 4 ;; esac
  echo "D288_ATTEMPT_${attempt}_GREETER_CGROUP=$greeter_cgroup"
  attempts=$((attempts + 1)); contacts=$((contacts + 1))
  echo "D288_ATTEMPT_${attempt}_GREETER_READY=true"
  echo 'Muovere il puntatore per mostrare il form; non digitare password o PIN; appoggiare una sola volta l’indice destro.'
  deadline=$((SECONDS + 70))
  result=
  while (( SECONDS < deadline )); do
    collect_attempt "$cursor" "$journal_log"
    result=$(sed -n 's/.*GOODIX_SIGFM_MATCH_AUDIT event=outcome result=\(match\|no_match\).*/\1/p' "$journal_log")
    [[ $(sed '/^$/d' <<<"$result" | wc -l) -le 1 ]] || exit 4
    [[ -z $result ]] || break
    kill -0 "$greeter_pid" 2>/dev/null || exit 4
    sleep 0.2
  done
  [[ $result == match || $result == no_match ]] || exit 4
  if [[ $result == no_match ]]; then stop_greeter; greeter_rc=143
  else
    deadline=$((SECONDS + 10))
    while kill -0 "$greeter_pid" 2>/dev/null && (( SECONDS < deadline )); do sleep 0.1; done
    kill -0 "$greeter_pid" 2>/dev/null && exit 4
    set +e; wait "$greeter_pid"; greeter_rc=$?; set -e
    rm -f -- "$pid_file"
  fi
  collect_attempt "$cursor" "$journal_log"
  epoch=$(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$journal_log" || true)
  match_count=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=match' "$journal_log" || true)
  no_match_count=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=no_match' "$journal_log" || true)
  redirect_count=$(grep -c '^D288_PAM_REDIRECT_SERVICE=kde-fingerprint$' "$greeter_log" || true)
  unlocked_count=$(grep -c '^Unlocked$' "$greeter_log" || true)
  [[ $epoch -eq 1 && $redirect_count -eq 1 && $(field_sum attempts "$journal_log") -eq 1 &&
     $(field_sum rejected "$journal_log") -eq 0 && $(field_sum consumed "$journal_log") -eq 1 &&
     $(field_sum tls "$journal_log") -eq 1 && $(field_sum first_image "$journal_log") -eq 1 &&
     $(field_sum secure_retry "$journal_log") -eq 0 && $(field_sum post_retry "$journal_log") -eq 0 &&
     $(field_sum reopen "$journal_log") -eq 0 && $(field_sum reset "$journal_log") -eq 0 &&
     $(field_sum clear_halt "$journal_log") -eq 0 && $(field_sum persistent "$journal_log") -eq 0 &&
     $(field_sum outstanding "$journal_log") -eq 0 && $(field_sum drained "$journal_log") -eq 1 &&
     $(field_sum context_closed "$journal_log") -eq 1 ]]
  if [[ $result == match ]]; then
    [[ $match_count -eq 1 && $no_match_count -eq 0 && $unlocked_count -eq 1 && $greeter_rc -eq 0 ]]
    matched=$attempt; outcome=KSCREENLOCKER_MATCH
  else
    [[ $match_count -eq 0 && $no_match_count -eq 1 && $unlocked_count -eq 0 ]]
    outcome=KSCREENLOCKER_NO_MATCH_SERIES
  fi
  "$here/sanitize.sh" <"$greeter_log" >"$capture/greeter-$attempt.log"
  cp "$journal_log" "$capture/attempt-$attempt-journal.log"
  [[ $matched -eq 0 ]] || break
done

cat >"$capture/payload-details.env" <<EOF
D288_SERIES_OUTCOME=$outcome
D288_ATTEMPTS_PERFORMED=$attempts
D288_CONTACTS_CONSUMED=$contacts
D288_MATCHED_ATTEMPT=$matched
D288_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
EOF
cat >"$telemetry" <<EOF
PAYLOAD_OUTCOME=$outcome
ACTION_ATTEMPT_COUNT=$attempts
CONTACT_COUNT=$contacts
RETRY_COUNT=0
MAX_ACTIONS_ENFORCED=$max_actions
MAX_CONTACTS_ENFORCED=$max_contacts
MAX_RETRIES_ENFORCED=$max_retries
PERSISTENT_WRITE_FAMILY_COUNT=0
OUTSTANDING_COUNT=0
DRAINED_COUNT=$attempts
CONTEXT_CLOSED_COUNT=$attempts
EOF
trap - EXIT HUP INT TERM
stop_greeter
echo "D288_SERIES_OUTCOME=$outcome"
