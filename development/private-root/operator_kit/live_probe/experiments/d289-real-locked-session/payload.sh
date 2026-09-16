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
[[ $max_actions == 3 && $max_contacts == 3 && $max_retries == 0 && $timeout_seconds == 900 ]]
work=${LIVE_PROBE_WORK_DIR:?}
capture=${LIVE_PROBE_CAPTURE_DIR:?}
telemetry=${LIVE_PROBE_TELEMETRY_FILE:?}
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=kwin-identity.sh
source "$here/kwin-identity.sh"
attempts=0 contacts=0 matched=0 outcome=D289_OFFLINE_COMPATIBILITY_PASS
overlay_started=false overlay_closed=false
root_pid= root_in_fd= root_out_fd=
root_log=$work/root-overlay.log

if [[ ${LIVE_PROBE_MODE:-} == offline-test ]]; then
  [[ -x $here/root-overlay.sh && -f $here/goodix-d289-kde-fingerprint.pam ]]
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
  echo D289_OFFLINE_PAYLOAD_COMPATIBILITY=PASS
  exit 0
fi

get_active () {
  local value
  value=$(busctl --user call org.freedesktop.ScreenSaver /ScreenSaver \
    org.freedesktop.ScreenSaver GetActive)
  [[ $value == 'b true' || $value == 'b false' ]]
  printf '%s\n' "${value#b }"
}

get_kwin_owner () {
  local owner
  owner=$(busctl --user call org.freedesktop.DBus /org/freedesktop/DBus \
    org.freedesktop.DBus GetConnectionUnixProcessID s org.freedesktop.ScreenSaver)
  d289_parse_dbus_owner "$owner"
}

wait_active () {
  local expected=$1 limit=$2
  while (( SECONDS < limit )); do
    [[ $(get_active) != "$expected" ]] || return 0
    sleep 0.1
  done
  return 1
}

wait_no_greeter () {
  local limit=$1
  while (( SECONDS < limit )); do
    ! pgrep -u "$(id -u)" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null && return 0
    sleep 0.1
  done
  return 1
}

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

release_overlay () {
  local line rc=0
  [[ $overlay_started == true && $overlay_closed == false ]] || return 0
  overlay_closed=true
  printf 'RELEASE\n' >&"$root_in_fd" || rc=1
  exec {root_in_fd}>&-
  while IFS= read -r line <&"$root_out_fd"; do
    printf '%s\n' "$line" | tee -a "$root_log"
  done
  exec {root_out_fd}>&-
  set +e
  wait "$root_pid"
  wait_rc=$?
  set -e
  [[ $wait_rc -eq 0 ]] || rc=1
  cp "$root_log" "$capture/root-overlay.log"
  return "$rc"
}

start_overlay () {
  local ready line expected
  overlay_started=false
  overlay_closed=false
  coproc D289_ROOT_HELPER { pkexec "$here/root-overlay.sh" --hold "$kwin_pid"; }
  root_pid=$D289_ROOT_HELPER_PID
  # Bash chiude automaticamente i descriptor originali del coproc quando il
  # processo termina. Duplichiamoli subito: il teardown deve poter drenare gli
  # ultimi marker anche se l'helper esce immediatamente dopo RELEASE.
  exec {root_out_fd}<&"${D289_ROOT_HELPER[0]}"
  exec {root_in_fd}>&"${D289_ROOT_HELPER[1]}"
  overlay_started=true
  IFS= read -r -t 60 ready <&"$root_out_fd"
  [[ $ready == D289_ROOT_NAMESPACE_MATCH=true ]]
  printf '%s\n' "$ready" | tee -a "$root_log"
  for expected in D289_ROOT_OVERLAY_READ_ONLY=true D289_ROOT_OVERLAY_READY=true; do
    IFS= read -r -t 10 line <&"$root_out_fd"
    [[ $line == "$expected" ]]
    printf '%s\n' "$line" | tee -a "$root_log"
  done
  [[ -r /etc/pam.d/kde-fingerprint ]]
  [[ $(sha256sum /etc/pam.d/kde-fingerprint | awk '{print $1}') == 126af52cd63c346fdf9fb053172506a49f851d45b0a49e4490fd807a12c328b6 ]]
  [[ $(sha256sum /etc/pam.d/kde | awk '{print $1}') == 7d91b3ad73a998e8b10f9edccd74ba04179a778c4a5e61d9176872f43c7bbac3 ]]
  echo D289_USER_OVERLAY_VISIBLE_AND_PASSWORD_SERVICE_UNCHANGED=true | tee -a "$root_log"
}

recover_locked_session () {
  local state deadline
  state=$(get_active 2>/dev/null || echo unknown)
  if [[ $state == true ]]; then
    echo 'Il probe si è arrestato mentre la sessione è bloccata: usare ora la password per il recupero; il kit non forza lo sblocco.' >&2
    deadline=$((SECONDS + 180))
    wait_active false "$deadline"
  else
    [[ $state == false ]]
  fi
}

on_exit () {
  local rc=$?
  trap - EXIT
  release_overlay || rc=1
  recover_locked_session || rc=1
  exit "$rc"
}

on_signal () {
  exit 130
}
trap on_signal HUP INT TERM
trap on_exit EXIT

[[ ${LIVE_PROBE_MODE:-} == operator-run && $(id -u) -ne 0 ]]
[[ ${XDG_SESSION_TYPE:-} == wayland && -n ${WAYLAND_DISPLAY:-} ]]
[[ $(get_active) == false ]]
kwin_pid=$(get_kwin_owner)
D289_PROC_ROOT=/proc d289_verify_kwin_identity "$kwin_pid" "$(id -u)"

for attempt in 1 2 3; do
  (( attempts < max_actions && contacts < max_contacts ))
  if (( attempt > 1 )); then
    printf 'Il precedente contatto è NO_MATCH e la sessione è stata recuperata. Per un nuovo lock digitare TENTATIVO %d: ' "$attempt"
    IFS= read -r confirmation
    [[ $confirmation == "TENTATIVO $attempt" ]]
  fi
  [[ $(get_active) == false ]]
  [[ $(get_kwin_owner) == "$kwin_pid" ]]
  D289_PROC_ROOT=/proc d289_verify_kwin_identity "$kwin_pid" "$(id -u)" >/dev/null
  ! pgrep -u "$(id -u)" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null
  start_overlay
  cursor=$(current_cursor)
  journal_log=$work/attempt-$attempt-journal.log
  state_log=$capture/attempt-$attempt-lock-state.env
  printf '%s\n' \
    'La sessione verrà bloccata davvero. Appoggiare una sola volta l’indice destro.' \
    'Non digitare password o PIN mentre la verifica fingerprint è in corso.' \
    'Se il fingerprint viene rifiutato o dopo 70 secondi lo schermo resta bloccato, usare la password per il solo recupero.'
  busctl --user call org.freedesktop.ScreenSaver /ScreenSaver \
    org.freedesktop.ScreenSaver Lock >/dev/null
  lock_deadline=$((SECONDS + 20))
  wait_active true "$lock_deadline"
  greeter_pid=
  greeter_deadline=$((SECONDS + 10))
  while (( SECONDS < greeter_deadline )); do
    mapfile -t greeters < <(pgrep -u "$(id -u)" -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' || true)
    [[ ${#greeters[@]} -le 1 ]]
    if [[ ${#greeters[@]} -eq 1 ]]; then greeter_pid=${greeters[0]}; break; fi
    sleep 0.1
  done
  [[ $greeter_pid =~ ^[0-9]+$ ]]
  greeter_ppid=$(awk '/^PPid:/ {print $2}' "/proc/$greeter_pid/status")
  greeter_uid=$(awk '/^Uid:/ {print $2}' "/proc/$greeter_pid/status")
  greeter_cgroup=$(awk -F: 'NR==1 {print $NF}' "/proc/$greeter_pid/cgroup")
  [[ $greeter_ppid == "$kwin_pid" && $greeter_uid == "$(id -u)" ]]
  case "$greeter_cgroup" in /user.slice/user-0.slice/*|/system.slice/*) exit 4 ;; esac
  attempts=$((attempts + 1)); contacts=$((contacts + 1))
  echo "D289_ATTEMPT_${attempt}_REAL_LOCK_ACTIVE=true"
  echo "D289_ATTEMPT_${attempt}_GREETER_PID=$greeter_pid"
  echo "D289_ATTEMPT_${attempt}_GREETER_PARENT_KWIN=true"
  echo "D289_ATTEMPT_${attempt}_GREETER_CGROUP=$greeter_cgroup"

  result=
  outcome_deadline=$((SECONDS + 70))
  while (( SECONDS < outcome_deadline )); do
    collect_attempt "$cursor" "$journal_log"
    result=$(sed -n 's/.*GOODIX_SIGFM_MATCH_AUDIT event=outcome result=\(match\|no_match\).*/\1/p' "$journal_log")
    [[ $(sed '/^$/d' <<<"$result" | wc -l) -le 1 ]]
    [[ $(get_active) == true || -n $result ]] || exit 4
    [[ -z $result ]] || break
    sleep 0.2
  done
  [[ $result == match || $result == no_match ]] || exit 4
  collect_attempt "$cursor" "$journal_log"
  epoch=$(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$journal_log" || true)
  match_count=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=match' "$journal_log" || true)
  no_match_count=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=no_match' "$journal_log" || true)
  [[ $epoch -eq 1 && $(field_sum attempts "$journal_log") -eq 1 &&
     $(field_sum rejected "$journal_log") -eq 0 && $(field_sum consumed "$journal_log") -eq 1 &&
     $(field_sum tls "$journal_log") -eq 1 && $(field_sum first_image "$journal_log") -eq 1 &&
     $(field_sum secure_retry "$journal_log") -eq 0 && $(field_sum post_retry "$journal_log") -eq 0 &&
     $(field_sum reopen "$journal_log") -eq 0 && $(field_sum reset "$journal_log") -eq 0 &&
     $(field_sum clear_halt "$journal_log") -eq 0 && $(field_sum persistent "$journal_log") -eq 0 &&
     $(field_sum outstanding "$journal_log") -eq 0 && $(field_sum drained "$journal_log") -eq 1 &&
     $(field_sum context_closed "$journal_log") -eq 1 ]]

  if [[ $result == match ]]; then
    [[ $match_count -eq 1 && $no_match_count -eq 0 ]]
    unlock_deadline=$((SECONDS + 20))
    wait_active false "$unlock_deadline"
    matched=$attempt
    outcome=REAL_LOCK_MATCH
    recovery=false
  else
    [[ $match_count -eq 0 && $no_match_count -eq 1 ]]
    echo 'Fingerprint NO_MATCH: sbloccare ora con la password per recuperare la sessione. La password non viene acquisita dal kit.'
    recovery_deadline=$((SECONDS + 120))
    wait_active false "$recovery_deadline"
    outcome=REAL_LOCK_NO_MATCH_SERIES
    recovery=true
  fi
  cat >"$state_log" <<EOF
D289_ATTEMPT=$attempt
D289_LOCK_ACTIVE_BEFORE=false
D289_LOCK_ACTIVE_OBSERVED=true
D289_GREETER_PID=$greeter_pid
D289_GREETER_PARENT_KWIN=true
D289_GREETER_CGROUP=$greeter_cgroup
D289_FINGERPRINT_RESULT=$result
D289_LOCK_ACTIVE_AFTER=false
D289_NON_FINGERPRINT_RECOVERY_AFTER_NO_MATCH=$recovery
EOF
  cp "$journal_log" "$capture/attempt-$attempt-journal.log"
  greeter_exit_deadline=$((SECONDS + 10))
  wait_no_greeter "$greeter_exit_deadline"
  release_overlay
  [[ $matched -eq 0 ]] || break
done

[[ $(get_active) == false ]]
trap - EXIT HUP INT TERM
cat >"$capture/payload-details.env" <<EOF
D289_SERIES_OUTCOME=$outcome
D289_ATTEMPTS_PERFORMED=$attempts
D289_CONTACTS_CONSUMED=$contacts
D289_MATCHED_ATTEMPT=$matched
D289_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
D289_REAL_LOCK_CYCLES=$attempts
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
echo "D289_SERIES_OUTCOME=$outcome"
