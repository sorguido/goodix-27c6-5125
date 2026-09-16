#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# -eq 2 && $1 == --phase ]]
phase=$2
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
work=${LIVE_PROBE_WORK_DIR:?}
shim=$work/pam-start-redirect.so
smoke=$work/pam-smoke
conf=$work/pam-confdir

verify_hash () {
  [[ -f $1 && ! -L $1 && $(sha256sum "$1" | awk '{print $1}') == "$2" ]]
}

if [[ $phase == pre ]]; then
  verify_hash "$here/goodix-d288-kde-fingerprint.pam" 126af52cd63c346fdf9fb053172506a49f851d45b0a49e4490fd807a12c328b6
  verify_hash "$here/pam-start-redirect.c" 1a4e0f176bfb8877678104473da6fe726d80d9b87b7c2855814cea21d2426ba5
  verify_hash "$here/pam-start-redirect.map" da11c6299b127c32dad7bdf8e5fe5f7199e3e8c31fb6d560df01c96ec87da4d2
  verify_hash "$here/pam-smoke.c" 7b258a0add18ea9a9451c9208fd4c72059f715816adcdaed2b6345753ae52227
  [[ $(rpm -q kscreenlocker) == kscreenlocker-6.7.5-1.fc44.x86_64 ]]
  [[ $(rpm -q plasma-workspace) == plasma-workspace-6.7.5-1.fc44.x86_64 ]]
  [[ $(rpm -q pam) == pam-1.7.2-2.fc44.x86_64 ]]
  [[ $(rpm -q fprintd-pam) == fprintd-pam-1.94.5-5.fc44.x86_64 ]]
  verify_hash /usr/libexec/kscreenlocker_greet 45d5a60737ff966b93f60639a662396956b28d50122741261f4351fef941be48
  verify_hash /etc/pam.d/kde 7d91b3ad73a998e8b10f9edccd74ba04179a778c4a5e61d9176872f43c7bbac3
  verify_hash /etc/pam.d/kde-fingerprint 8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437
  verify_hash /usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml 328501780ab06cc0497a25ff48c6f027a1abed8506f0969f39a5f8bc6696181c
  strings -el /usr/libexec/kscreenlocker_greet | grep -Fx kde-fingerprint >/dev/null
  nm -D /usr/libexec/kscreenlocker_greet | grep -F 'pam_start@LIBPAM_1.0' >/dev/null
  mkdir -m 0700 "$conf"
  printf '%s\n' 'auth required pam_permit.so' >"$conf/kde-fingerprint"
  cc -std=c11 -Wall -Wextra -Werror -fPIC -shared -Wl,-z,defs,-z,relro,-z,now,--build-id=none \
    -Wl,--version-script="$here/pam-start-redirect.map" \
    "$here/pam-start-redirect.c" -o "$shim"
  cc -std=c11 -Wall -Wextra -Werror -Wl,--build-id=none "$here/pam-smoke.c" \
    /lib64/libpam.so.0 -o "$smoke"
  nm -D "$shim" | grep -F 'pam_start@@LIBPAM_1.0' >/dev/null
  GOODIX_D288_PAM_CONFDIR=$conf LD_PRELOAD=$shim "$smoke"
  echo D288_PRELOAD_PAM_START_CONFDIR_SMOKE=PASS
  echo D288_GREETER_PAM_START_DYNAMIC_SYMBOL=PASS
elif [[ $phase != post ]]; then
  exit 2
fi

if [[ ${LIVE_PROBE_MODE:-} == operator-run ]]; then
  user=$(id -un)
  ! pgrep -f '^/usr/libexec/kscreenlocker_greet([[:space:]]|$)' >/dev/null
  count=0
  for device in /sys/bus/usb/devices/*; do
    [[ -f $device/idVendor && -f $device/idProduct ]] || continue
    if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      count=$((count + 1))
    fi
  done
  [[ $count -eq 1 ]]
  echo D288_TARGET_SYSFS_CARDINALITY=1
  echo D288_EXISTING_GREETER_COUNT=0
  audit_phase="D288_KSCREENLOCKER_${phase^^}"
  audit_output=$(pkexec "$root/operator_kit/d286-01-reboot-survival/run-d286-01.sh" \
    --root-audit "$audit_phase" --user "$user")
  printf '%s\n' "$audit_output"
  grep -Fx "D286_01_ROOT_AUDIT_PHASE=$audit_phase" <<<"$audit_output" >/dev/null
  grep -Fx D286_01_STATE_COHERENCE=PASS_ROOT_ONLY <<<"$audit_output" >/dev/null
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES <<<"$audit_output" >/dev/null
  grep -Fx "D286_01_${audit_phase}_ROOT_AUDIT_SENSOR_ACTION_COUNT=0" <<<"$audit_output" >/dev/null
else
  echo "D288_${phase^^}_ROOT_AUDIT=NOT_APPLICABLE_OFFLINE"
fi
echo "D288_${phase^^}_AUDIT=PASS"
echo "D288_${phase^^}_AUDIT_SENSOR_ACTION_COUNT=0"
