#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

die() {
    printf 'D281_01_PRIVATE_FLOW=FAIL reason=%s\n' "$1" >&2
    exit 1
}

for required in D281_01_PROBE_ROOT D281_01_REPO_ROOT D281_01_LIB_DIR D281_01_GUSB_DIR; do
    [[ -n "${!required:-}" ]] || die "missing_${required}"
done

case "${DBUS_SESSION_BUS_ADDRESS:-}" in
    unix:path=/tmp/*) ;;
    *) die non_tmp_private_bus ;;
esac
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
export D281_01_PRIVATE_BUS=1
export STATE_DIRECTORY="$D281_01_PROBE_ROOT/state"
export FP_VIRTUAL_IMAGE="$D281_01_PROBE_ROOT/virtual-image.socket"
export FP_DRIVERS_ALLOWLIST=virtual_image
export LD_LIBRARY_PATH="$D281_01_LIB_DIR:$D281_01_GUSB_DIR"

[[ "$STATE_DIRECTORY" == "$D281_01_PROBE_ROOT"/* ]] || die state_outside_probe
[[ "$FP_VIRTUAL_IMAGE" == "$D281_01_PROBE_ROOT"/* ]] || die socket_outside_probe
[[ ! -e /dev/bus/usb/001/001 || ! -w /dev/bus/usb/001/001 ]] || die unexpected_writable_usb_node

mkdir -m 0700 "$STATE_DIRECTORY"
polkit_pid=
daemon_pid=
sender_pid=

stop_daemon() {
    if [[ -n "$daemon_pid" ]] && kill -0 "$daemon_pid" 2>/dev/null; then
        kill "$daemon_pid"
        wait "$daemon_pid" || true
    fi
    daemon_pid=
}

cleanup() {
    if [[ -n "$sender_pid" ]] && kill -0 "$sender_pid" 2>/dev/null; then
        kill "$sender_pid" || true
        wait "$sender_pid" || true
    fi
    stop_daemon
    if [[ -n "$polkit_pid" ]] && kill -0 "$polkit_pid" 2>/dev/null; then
        kill "$polkit_pid" || true
        wait "$polkit_pid" || true
    fi
}
trap cleanup EXIT INT TERM

python3 "$D281_01_REPO_ROOT/analysis/D281/d281_01_private_polkit_mock.py" \
    >"$D281_01_PROBE_ROOT/polkit.log" 2>&1 &
polkit_pid=$!

for _ in $(seq 1 100); do
    if gdbus call --system \
        --dest org.freedesktop.PolicyKit1 \
        --object-path /org/freedesktop/PolicyKit1/Authority \
        --method org.freedesktop.DBus.Properties.Get \
        org.freedesktop.PolicyKit1.Authority BackendName \
        >"$D281_01_PROBE_ROOT/polkit-ready.out" 2>"$D281_01_PROBE_ROOT/polkit-ready.err"; then
        break
    fi
    sleep 0.05
done
kill -0 "$polkit_pid" 2>/dev/null || die polkit_mock_exited

start_daemon() {
    local label=$1
    /usr/libexec/fprintd >"$D281_01_PROBE_ROOT/fprintd-${label}.log" 2>&1 &
    daemon_pid=$!
    gdbus wait --system --timeout 10 net.reactivated.Fprint \
        >"$D281_01_PROBE_ROOT/fprintd-${label}-ready.out" 2>&1 || die "daemon_${label}_not_ready"
    kill -0 "$daemon_pid" 2>/dev/null || die "daemon_${label}_exited"
    grep -F "$D281_01_LIB_DIR/libfprint-2.so.2.0.0" "/proc/$daemon_pid/maps" \
        >"$D281_01_PROBE_ROOT/fprintd-${label}-maps.out" || die "daemon_${label}_wrong_libfprint"
}

send_images() {
    local count=$1
    local image=$2
    local label=$3
    (
        for _ in $(seq 1 "$count"); do
            sent=false
            for _ in $(seq 1 200); do
                if FP_VIRTUAL_IMAGE="$FP_VIRTUAL_IMAGE" \
                    python3 "$D281_01_REPO_ROOT/reference/libfprint-fedora44-1.94.100/source/examples/sendvirtimg.py" "$image" \
                    >>"$D281_01_PROBE_ROOT/sender-${label}.log" 2>&1; then
                    sent=true
                    # The virtual image listener needs to complete the
                    # current callback and re-arm before the next sample.
                    sleep 0.5
                    break
                fi
                sleep 0.05
            done
            [[ "$sent" == true ]] || exit 1
        done
    ) &
    sender_pid=$!
}

image="$D281_01_REPO_ROOT/reference/libfprint-fedora44-1.94.100/source/examples/prints/whorl.png"
user_name=$(id -un)

start_daemon enroll
send_images 6 "$image" enroll
/usr/bin/fprintd-enroll -f right-index-finger "$user_name" \
    >"$D281_01_PROBE_ROOT/enroll.out" 2>"$D281_01_PROBE_ROOT/enroll.err"
wait "$sender_pid" || die enroll_sender_failed
sender_pid=
grep -Fx 'Enroll result: enroll-completed' "$D281_01_PROBE_ROOT/enroll.out" >/dev/null || die enroll_not_completed
stop_daemon

mapfile -t print_files < <(find "$STATE_DIRECTORY" -type f -print)
[[ ${#print_files[@]} -eq 1 ]] || die unexpected_enrolled_file_count
print_file=${print_files[0]}
[[ "$print_file" == "$STATE_DIRECTORY"/* ]] || die print_outside_state
[[ $(head -c 3 "$print_file") == FP3 ]] || die stored_print_not_fp3
print_sha256=$(sha256sum "$print_file" | awk '{print $1}')
print_size=$(stat -c '%s' "$print_file")
print_mode=$(stat -c '%a' "$print_file")
cp --preserve=mode,timestamps "$print_file" "$D281_01_PROBE_ROOT/original-print.fp3"

start_daemon reload
/usr/bin/fprintd-list "$user_name" >"$D281_01_PROBE_ROOT/list-reload.out" 2>"$D281_01_PROBE_ROOT/list-reload.err"
grep -F 'right-index-finger' "$D281_01_PROBE_ROOT/list-reload.out" >/dev/null || die reload_list_missing_finger
send_images 1 "$image" verify
/usr/bin/fprintd-verify -f right-index-finger "$user_name" \
    >"$D281_01_PROBE_ROOT/verify-reload.out" 2>"$D281_01_PROBE_ROOT/verify-reload.err"
wait "$sender_pid" || die verify_sender_failed
sender_pid=
grep -Fx 'Verify result: verify-match (done)' "$D281_01_PROBE_ROOT/verify-reload.out" >/dev/null || die reload_verify_not_match
stop_daemon

printf 'X' | dd of="$print_file" bs=1 count=1 conv=notrunc status=none
[[ $(head -c 3 "$print_file") != FP3 ]] || die corruption_not_applied
start_daemon corrupt
set +e
/usr/bin/fprintd-verify -f right-index-finger "$user_name" \
    >"$D281_01_PROBE_ROOT/verify-corrupt.out" 2>"$D281_01_PROBE_ROOT/verify-corrupt.err"
corrupt_verify_rc=$?
set -e
[[ $corrupt_verify_rc -ne 0 ]] || die corrupted_print_accepted
stop_daemon

cp --preserve=mode,timestamps "$D281_01_PROBE_ROOT/original-print.fp3" "$print_file"
start_daemon delete
/usr/bin/fprintd-delete "$user_name" >"$D281_01_PROBE_ROOT/delete.out" 2>"$D281_01_PROBE_ROOT/delete.err"
stop_daemon
remaining_files=$(find "$STATE_DIRECTORY" -type f | wc -l)
[[ $remaining_files -eq 0 ]] || die delete_left_print_files

printf 'D281_01_PRIVATE_BUS_FLOW=PASS\n'
printf 'D281_01_INSTALLED_FPRINTD=%s\n' "$(rpm -q fprintd)"
printf 'D281_01_HOST_LIBFPRINT=%s\n' "$(rpm -q libfprint)"
printf 'D281_01_DRIVER=virtual_image\n'
printf 'D281_01_USB_CONTEXT_COMPILE_DISABLED=true\n'
printf 'D281_01_REAL_USB_ENUMERATION_ATTEMPTED=false\n'
printf 'D281_01_STATE_DIRECTORY=%s\n' "$STATE_DIRECTORY"
printf 'D281_01_STORED_FP3_SHA256=%s\n' "$print_sha256"
printf 'D281_01_STORED_FP3_SIZE=%s\n' "$print_size"
printf 'D281_01_STORED_FP3_MODE=%s\n' "$print_mode"
printf 'D281_01_RELOAD_LIST_PASS=true\n'
printf 'D281_01_RELOAD_VERIFY_MATCH_PASS=true\n'
printf 'D281_01_CORRUPT_VERIFY_REJECTED=true\n'
printf 'D281_01_CORRUPT_VERIFY_RETURN_CODE=%s\n' "$corrupt_verify_rc"
printf 'D281_01_DELETE_PASS=true\n'
printf 'D281_01_REMAINING_STATE_FILE_COUNT=%s\n' "$remaining_files"
printf 'D281_01_REAL_BIOMETRIC_DATA_USED=false\n'
printf 'D281_01_REAL_SENSOR_ACCESSED=false\n'
