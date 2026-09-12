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
[[ $max_actions == 1 && $max_contacts == 1 && $max_retries == 0 && $timeout_seconds == 1200 ]]
work=${LIVE_PROBE_WORK_DIR:?}
capture=${LIVE_PROBE_CAPTURE_DIR:?}
telemetry=${LIVE_PROBE_TELEMETRY_FILE:?}
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
uid=$(id -u)
attempts=0 contacts=0 outcome=D290_OFFLINE_COMPATIBILITY_PASS
overlay_started=false overlay_closed=false
root_pid= root_in_fd= root_out_fd=
root_log=$work/root-overlay.log

if [[ ${LIVE_PROBE_MODE:-} == offline-test ]]; then
  [[ -x $here/root-overlay.sh && -f $here/goodix-d290-plasmalogin.pam ]]
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
  echo D290_OFFLINE_PAYLOAD_COMPATIBILITY=PASS
  exit 0
fi

active_graphical_sessions () {
  local session_id session_uid rest service type class state
  while read -r session_id session_uid rest; do
    [[ $session_uid == "$uid" && $session_id != "${XDG_SESSION_ID:-}" ]] || continue
    service=$(loginctl show-session "$session_id" -p Service --value 2>/dev/null || true)
    type=$(loginctl show-session "$session_id" -p Type --value 2>/dev/null || true)
    class=$(loginctl show-session "$session_id" -p Class --value 2>/dev/null || true)
    state=$(loginctl show-session "$session_id" -p State --value 2>/dev/null || true)
    if [[ $service == plasmalogin && $type == wayland && $class == user && $state == active ]]; then
      printf '%s\n' "$session_id"
    fi
  done < <(loginctl list-sessions --no-legend 2>/dev/null)
}

current_cursor () {
  local output cursor
  output=$(LC_ALL=C journalctl -b -n 0 --show-cursor --no-pager)
  cursor=$(sed -n 's/^-- cursor: //p' <<<"$output")
  [[ $(sed '/^$/d' <<<"$cursor" | wc -l) -eq 1 ]]
  printf '%s\n' "$cursor"
}

collect_fprintd () {
  journalctl -b -u fprintd.service --after-cursor "$1" --no-pager -o short-iso-precise |
    "$here/sanitize.sh" >"$2"
}

collect_plasmalogin () {
  journalctl -b -u plasmalogin.service --after-cursor "$1" --no-pager -o short-iso-precise |
    "$here/sanitize.sh" >"$2"
}

field_sum () {
  local key=$1 file=$2
  awk -v key="$key" '/GOODIX_D282_EPOCH_AUDIT / { for (i=1;i<=NF;i++) { split($i,a,"="); if (a[1]==key && a[2]~/^[0-9]+$/) s+=a[2] } } END { print s+0 }' "$file"
}

release_overlay () {
  local line rc=0 wait_rc
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
  coproc D290_ROOT_HELPER { pkexec "$here/root-overlay.sh" --hold; }
  root_pid=$D290_ROOT_HELPER_PID
  exec {root_out_fd}<&"${D290_ROOT_HELPER[0]}"
  exec {root_in_fd}>&"${D290_ROOT_HELPER[1]}"
  overlay_started=true
  IFS= read -r -t 60 ready <&"$root_out_fd"
  [[ $ready == D290_ROOT_DAEMON_IDENTITY=true ]]
  printf '%s\n' "$ready" | tee -a "$root_log"
  for expected in D290_ROOT_NAMESPACE_MATCH=true D290_ROOT_OVERLAY_READ_ONLY=true D290_ROOT_OVERLAY_READY=true; do
    IFS= read -r -t 10 line <&"$root_out_fd"
    [[ $line == "$expected" ]]
    printf '%s\n' "$line" | tee -a "$root_log"
  done
  [[ $(sha256sum /usr/lib/pam.d/plasmalogin | awk '{print $1}') == 89d389e6c2ee59dcee374029a5428a81dc9138c4f5e86068159b3d5a2c77ab2d ]]
  echo D290_USER_OVERLAY_VISIBLE=true | tee -a "$root_log"
}

on_exit () {
  local rc=$? overlay_cleanup_ok=true
  trap - EXIT
  release_overlay || { overlay_cleanup_ok=false; rc=1; }
  if [[ $rc -ne 0 ]]; then
    if [[ $overlay_cleanup_ok == true ]]; then
      echo 'D290 arrestato: l’overlay è stato rilasciato. Usare la password solo dopo il completamento del kit.' >&2
    else
      echo 'D290 arrestato: cleanup overlay non confermato. Non usare il login; eseguire dalla TTY la recovery documentata.' >&2
    fi
  fi
  exit "$rc"
}
trap 'exit 130' HUP INT TERM
trap on_exit EXIT

[[ ${LIVE_PROBE_MODE:-} == operator-run && $uid -ne 0 ]]
[[ ${XDG_SESSION_TYPE:-} == tty && ${XDG_SESSION_ID:-} =~ ^[0-9]+$ && ${XDG_VTNR:-} == 3 ]]
mapfile -t initial_sessions < <(active_graphical_sessions)
[[ ${#initial_sessions[@]} -eq 1 ]]
initial_session=${initial_sessions[0]}
[[ $(loginctl show-session "$initial_session" -p TTY --value) == tty2 ]]
cursor=$(current_cursor)
start_overlay

printf '%s\n' \
  "Sessione grafica iniziale: $initial_session. Questo terminale TTY resta attivo durante il logout." \
  '1. Premere Ctrl+Alt+F2, salvare il lavoro e fare logout dal menu Plasma.' \
  '2. Al login manager selezionare l’utente; lasciare il campo password completamente vuoto.' \
  '3. Premere Invio una sola volta, poi appoggiare una sola volta l’indice destro.' \
  '4. Non digitare password/PIN e non ripetere il contatto durante la verifica.' \
  '5. Dopo ingresso nel desktop oppure “Login Failed”, tornare subito qui con Ctrl+Alt+F3.'

logout_deadline=$((SECONDS + 300))
while loginctl show-session "$initial_session" -p State --value >/dev/null 2>&1 && (( SECONDS < logout_deadline )); do
  sleep 0.2
done
! loginctl show-session "$initial_session" -p State --value >/dev/null 2>&1
echo D290_INITIAL_GRAPHICAL_LOGOUT_OBSERVED=true

greeter_uid=$(id -u plasmalogin)
greeter_pid=
greeter_deadline=$((SECONDS + 60))
while (( SECONDS < greeter_deadline )); do
  mapfile -t greeters < <(pgrep -u "$greeter_uid" -f '^/usr/libexec/plasma-login-greeter([[:space:]]|$)' || true)
  [[ ${#greeters[@]} -le 1 ]]
  if [[ ${#greeters[@]} -eq 1 ]]; then greeter_pid=${greeters[0]}; break; fi
  sleep 0.2
done
[[ $greeter_pid =~ ^[1-9][0-9]*$ ]]
greeter_cgroup=$(awk -F: 'NR==1 {print $NF}' "/proc/$greeter_pid/cgroup")
case "$greeter_cgroup" in
  "/user.slice/user-$greeter_uid.slice/session-"[0-9]*.scope|\
  "/user.slice/user-$greeter_uid.slice/user@$greeter_uid.service/session.slice/plasma-login.service") ;;
  *) exit 4 ;;
esac
greeter_sessions=()
while read -r session_id session_uid _; do
  [[ $session_uid == "$greeter_uid" ]] || continue
  service=$(loginctl show-session "$session_id" -p Service --value 2>/dev/null || true)
  type=$(loginctl show-session "$session_id" -p Type --value 2>/dev/null || true)
  class=$(loginctl show-session "$session_id" -p Class --value 2>/dev/null || true)
  state=$(loginctl show-session "$session_id" -p State --value 2>/dev/null || true)
  if [[ $service == plasmalogin-greeter && $type == wayland && $class == greeter && $state == active ]]; then
    greeter_sessions+=("$session_id")
  fi
done < <(loginctl list-sessions --no-legend 2>/dev/null)
[[ ${#greeter_sessions[@]} -eq 1 ]]
greeter_session=${greeter_sessions[0]}
echo "D290_REAL_PLASMALOGIN_GREETER_PID=$greeter_pid"
echo "D290_REAL_PLASMALOGIN_GREETER_SESSION=$greeter_session"
echo "D290_REAL_PLASMALOGIN_GREETER_CGROUP=$greeter_cgroup"

finger_log=$work/fprintd-attempt.log
plasma_log=$work/plasmalogin-attempt.log
result=
outcome_deadline=$((SECONDS + 240))
while (( SECONDS < outcome_deadline )); do
  collect_fprintd "$cursor" "$finger_log"
  result=$(sed -n 's/.*GOODIX_SIGFM_MATCH_AUDIT event=outcome result=\(match\|no_match\).*/\1/p' "$finger_log")
  [[ $(sed '/^$/d' <<<"$result" | wc -l) -le 1 ]]
  [[ -z $result ]] || break
  sleep 0.2
done
[[ $result == match || $result == no_match ]]
collect_fprintd "$cursor" "$finger_log"
epoch_deadline=$((SECONDS + 15))
while (( SECONDS < epoch_deadline )); do
  collect_fprintd "$cursor" "$finger_log"
  epoch_count=$(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$finger_log" || true)
  (( epoch_count <= 1 ))
  [[ $epoch_count -eq 0 ]] || break
  sleep 0.1
done
[[ $epoch_count -eq 1 ]]
[[ $(field_sum attempts "$finger_log") -eq 1 && $(field_sum rejected "$finger_log") -eq 0 &&
   $(field_sum consumed "$finger_log") -eq 1 && $(field_sum tls "$finger_log") -eq 1 &&
   $(field_sum first_image "$finger_log") -eq 1 && $(field_sum secure_retry "$finger_log") -eq 0 &&
   $(field_sum post_retry "$finger_log") -eq 0 && $(field_sum reopen "$finger_log") -eq 0 &&
   $(field_sum reset "$finger_log") -eq 0 && $(field_sum clear_halt "$finger_log") -eq 0 &&
   $(field_sum persistent "$finger_log") -eq 0 && $(field_sum outstanding "$finger_log") -eq 0 &&
   $(field_sum drained "$finger_log") -eq 1 && $(field_sum context_closed "$finger_log") -eq 1 ]]
attempts=1 contacts=1

new_session=NONE
session_created=false
if [[ $result == match ]]; then
  [[ $(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=match' "$finger_log" || true) -eq 1 ]]
  session_deadline=$((SECONDS + 90))
  while (( SECONDS < session_deadline )); do
    mapfile -t new_sessions < <(active_graphical_sessions)
    if [[ ${#new_sessions[@]} -eq 1 && ${new_sessions[0]} != "$initial_session" ]]; then
      new_session=${new_sessions[0]}
      session_created=true
      break
    fi
    [[ ${#new_sessions[@]} -le 1 ]]
    sleep 0.2
  done
  [[ $session_created == true ]]
  outcome=PLASMALOGIN_MATCH_NEW_SESSION
else
  [[ $(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=no_match' "$finger_log" || true) -eq 1 ]]
  mapfile -t new_sessions < <(active_graphical_sessions)
  [[ ${#new_sessions[@]} -eq 0 ]]
  outcome=PLASMALOGIN_NO_MATCH_PASSWORD_RECOVERY_READY
fi
collect_plasmalogin "$cursor" "$plasma_log"

cp "$finger_log" "$capture/fprintd-attempt.log"
cp "$plasma_log" "$capture/plasmalogin-attempt.log"
cat >"$capture/login-state.env" <<EOF
D290_INITIAL_GRAPHICAL_SESSION=$initial_session
D290_INITIAL_GRAPHICAL_LOGOUT_OBSERVED=true
D290_REAL_GREETER_PID=$greeter_pid
D290_REAL_GREETER_SESSION=$greeter_session
D290_REAL_GREETER_CGROUP=$greeter_cgroup
D290_FINGERPRINT_RESULT=$result
D290_NEW_GRAPHICAL_SESSION=$new_session
D290_NEW_GRAPHICAL_SESSION_CREATED=$session_created
D290_PASSWORD_OR_PIN_USED_DURING_FINGERPRINT=NOT_MACHINE_TELEMETERED
EOF

release_overlay
printf '%s\n' \
  "D290_FINGERPRINT_OUTCOME=$result" \
  'D290_OVERLAY_RELEASED_BEFORE_PASSWORD_RECOVERY=true' \
  'Controllare sopra i marker UNMOUNTED/HOST_PAM_RESTORED/RUNTIME_REMOVED.'
if [[ $result == no_match ]]; then
  echo 'Dopo che il kit ha concluso anche il post-audit, tornare con Ctrl+Alt+F2 e usare la password; non ripetere il fingerprint.'
fi
printf 'Per consentire il post-audit digitare CHIUDI D290: '
IFS= read -r close_confirmation
[[ $close_confirmation == 'CHIUDI D290' ]]

trap - EXIT HUP INT TERM
cat >"$capture/payload-details.env" <<EOF
D290_OUTCOME=$outcome
D290_ATTEMPTS_PERFORMED=$attempts
D290_CONTACTS_CONSUMED=$contacts
D290_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
D290_OVERLAY_RELEASED_BEFORE_PASSWORD_RECOVERY=true
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
DRAINED_COUNT=1
CONTEXT_CLOSED_COUNT=1
EOF
echo "D290_OUTCOME=$outcome"
