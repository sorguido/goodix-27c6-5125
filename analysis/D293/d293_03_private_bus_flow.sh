#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

die() { printf 'D293_03_PRIVATE_FLOW=FAIL reason=%s\n' "$1" >&2; exit 1; }
for required in D293_03_PROBE_ROOT D293_03_REPO_ROOT D293_03_LIB_DIR D293_03_GUSB_DIR; do
  [[ -n "${!required:-}" ]] || die "missing_${required}"
done
case "${DBUS_SESSION_BUS_ADDRESS:-}" in unix:path=/tmp/*) ;; *) die non_tmp_bus ;; esac
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
export D281_01_PRIVATE_BUS=1
export STATE_DIRECTORY="$D293_03_PROBE_ROOT/state"
export FP_VIRTUAL_IMAGE="$D293_03_PROBE_ROOT/virtual-image.socket"
export FP_DRIVERS_ALLOWLIST=virtual_image
export LD_LIBRARY_PATH="$D293_03_LIB_DIR:$D293_03_GUSB_DIR"
[[ "$STATE_DIRECTORY" == "$D293_03_PROBE_ROOT"/* ]] || die unsafe_state
[[ "$FP_VIRTUAL_IMAGE" == "$D293_03_PROBE_ROOT"/* ]] || die unsafe_socket
mkdir -m 0700 "$STATE_DIRECTORY"

polkit_pid= daemon_pid= sender_pid=
stop_daemon() {
  if [[ -n "$daemon_pid" ]] && kill -0 "$daemon_pid" 2>/dev/null; then
    kill "$daemon_pid"; wait "$daemon_pid" || true
  fi
  daemon_pid=
}
cleanup() {
  if [[ -n "$sender_pid" ]] && kill -0 "$sender_pid" 2>/dev/null; then kill "$sender_pid" || true; wait "$sender_pid" || true; fi
  stop_daemon
  if [[ -n "$polkit_pid" ]] && kill -0 "$polkit_pid" 2>/dev/null; then kill "$polkit_pid" || true; wait "$polkit_pid" || true; fi
}
trap cleanup EXIT INT TERM

python3 "$D293_03_REPO_ROOT/analysis/D281/d281_01_private_polkit_mock.py" \
  >"$D293_03_PROBE_ROOT/polkit.log" 2>&1 & polkit_pid=$!
for _ in $(seq 1 100); do
  gdbus call --system --dest org.freedesktop.PolicyKit1 \
    --object-path /org/freedesktop/PolicyKit1/Authority \
    --method org.freedesktop.DBus.Properties.Get \
    org.freedesktop.PolicyKit1.Authority BackendName >/dev/null 2>&1 && break
  sleep 0.05
done
kill -0 "$polkit_pid" 2>/dev/null || die polkit_exited

start_daemon() {
  local label=$1
  /usr/libexec/fprintd >"$D293_03_PROBE_ROOT/fprintd-${label}.log" 2>&1 & daemon_pid=$!
  gdbus wait --system --timeout 10 net.reactivated.Fprint >/dev/null 2>&1 || die "daemon_${label}_not_ready"
  grep -F "$D293_03_LIB_DIR/libfprint-2.so.2.0.0" "/proc/$daemon_pid/maps" >/dev/null || die wrong_library
}
send_images() {
  local count=$1 image=$2 label=$3
  (
    for _ in $(seq 1 "$count"); do
      sent=false
      for _ in $(seq 1 200); do
        if FP_VIRTUAL_IMAGE="$FP_VIRTUAL_IMAGE" python3 \
          "$D293_03_REPO_ROOT/reference/libfprint-fedora44-1.94.100/source/examples/sendvirtimg.py" "$image" \
          >>"$D293_03_PROBE_ROOT/sender-${label}.log" 2>&1; then sent=true; sleep 0.5; break; fi
        sleep 0.05
      done
      [[ $sent == true ]] || exit 1
    done
  ) & sender_pid=$!
}
enroll() {
  local user=$1 finger=$2 image=$3 count=$4 label=$5
  send_images "$count" "$image" "$label"
  /usr/bin/fprintd-enroll -f "$finger" "$user" >"$D293_03_PROBE_ROOT/${label}.out" 2>"$D293_03_PROBE_ROOT/${label}.err"
  wait "$sender_pid" || die "${label}_sender"; sender_pid=
  grep -Fx 'Enroll result: enroll-completed' "$D293_03_PROBE_ROOT/${label}.out" >/dev/null || die "${label}_failed"
}
verify() {
  local user=$1 finger=$2 image=$3 expected=$4 label=$5
  send_images 1 "$image" "$label"
  if ! /usr/bin/fprintd-verify -f "$finger" "$user" >"$D293_03_PROBE_ROOT/${label}.out" 2>"$D293_03_PROBE_ROOT/${label}.err"; then
    [[ $expected == verify-no-match ]] || die "${label}_command"
  fi
  wait "$sender_pid" || die "${label}_sender"; sender_pid=
  grep -Fx "Verify result: ${expected} (done)" "$D293_03_PROBE_ROOT/${label}.out" >/dev/null || die "${label}_unexpected"
}

prints="$D293_03_REPO_ROOT/reference/libfprint-fedora44-1.94.100/source/examples/prints"
whorl="$prints/whorl.png"; loop="$prints/loop-right.png"; arch="$prints/arch.png"; tented="$prints/tented_arch.png"
alpha=d293-alpha; beta=d293-beta

start_daemon enroll
enroll "$alpha" right-index-finger "$whorl" 6 alpha-right
enroll "$alpha" left-index-finger "$loop" 6 alpha-left
enroll "$beta" right-index-finger "$tented" 6 beta-right
[[ $(find "$STATE_DIRECTORY/$alpha" -type f | wc -l) -eq 2 ]] || die alpha_count
[[ $(find "$STATE_DIRECTORY/$beta" -type f | wc -l) -eq 1 ]] || die beta_count
stop_daemon

start_daemon reload
/usr/bin/fprintd-list "$alpha" >"$D293_03_PROBE_ROOT/list-alpha.out"
/usr/bin/fprintd-list "$beta" >"$D293_03_PROBE_ROOT/list-beta.out"
grep -F 'left-index-finger' "$D293_03_PROBE_ROOT/list-alpha.out" >/dev/null || die alpha_left_missing
grep -F 'right-index-finger' "$D293_03_PROBE_ROOT/list-alpha.out" >/dev/null || die alpha_right_missing
grep -F 'right-index-finger' "$D293_03_PROBE_ROOT/list-beta.out" >/dev/null || die beta_right_missing
verify "$alpha" any "$loop" verify-match alpha-any
verify "$beta" any "$whorl" verify-no-match beta-isolation

enroll "$alpha" right-index-finger "$arch" 6 alpha-replace
verify "$alpha" any "$arch" verify-match alpha-replaced-any
/usr/bin/fprintd-delete "$alpha" -f left-index-finger >"$D293_03_PROBE_ROOT/delete-single.out"
[[ $(find "$STATE_DIRECTORY/$alpha" -type f | wc -l) -eq 1 ]] || die delete_single_count
/usr/bin/fprintd-delete "$beta" >"$D293_03_PROBE_ROOT/delete-beta.out"
beta_remaining=0
if [[ -d "$STATE_DIRECTORY/$beta" ]]; then
  beta_remaining=$(find "$STATE_DIRECTORY/$beta" -type f | wc -l)
fi
[[ $beta_remaining -eq 0 ]] || die delete_complete_count
grep -F 'D281_01_POLKIT_ACTION=net.reactivated.fprint.device.setusername AUTHORIZED=true' \
  "$D293_03_PROBE_ROOT/polkit.log" >/dev/null || die setusername_not_authorized
stop_daemon

printf 'D293_03_PRIVATE_BUS_FLOW=PASS\n'
printf 'D293_03_PRINCIPAL_COUNT=2\n'
printf 'D293_03_UNIX_UID_COUNT=1\n'
printf 'D293_03_SETUSERNAME_AUTHORIZED=true\n'
printf 'D293_03_ALPHA_INITIAL_FINGER_COUNT=2\n'
printf 'D293_03_RESTART_RELOAD=PASS\n'
printf 'D293_03_VERIFY_ANY_MULTI_FINGER=PASS\n'
printf 'D293_03_PRINCIPAL_ISOLATION=PASS\n'
printf 'D293_03_REPLACE=PASS\n'
printf 'D293_03_DELETE_SINGLE=PASS\n'
printf 'D293_03_DELETE_COMPLETE=PASS\n'
printf 'D293_03_STATE_DIRECTORY=%s\n' "$STATE_DIRECTORY"
printf 'D293_03_REAL_USB_ENUMERATION_ATTEMPTED=false\n'
printf 'D293_03_REAL_SENSOR_ACCESSED=false\n'
printf 'D293_03_REAL_BIOMETRIC_DATA_USED=false\n'
