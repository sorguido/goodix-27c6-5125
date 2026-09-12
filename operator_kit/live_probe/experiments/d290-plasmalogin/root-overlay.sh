#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

[[ $# -ge 1 ]]
mode=$1
if [[ $mode == --hold ]]; then
  [[ $# -eq 1 ]]
elif [[ $mode == --recover ]]; then
  [[ $# -eq 1 ]]
else
  exit 2
fi
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
target=/usr/lib/pam.d/plasmalogin
candidate=$here/goodix-d290-plasmalogin.pam
expected_host=c6fc4a0bc2d89f88fa15ca7e9a6c5aaeccfbe66897755b5416ce9c5e35b4e40b
expected_candidate=89d389e6c2ee59dcee374029a5428a81dc9138c4f5e86068159b3d5a2c77ab2d
operator_uid=${PKEXEC_UID:-}
runtime=
mounted=false

digest () { sha256sum "$1" | awk '{print $1}'; }

cleanup_overlay () {
  local rc=0
  if [[ $mounted == true ]]; then
    umount "$target" || rc=1
  fi
  if ! mountpoint -q "$target"; then
    echo D290_ROOT_OVERLAY_UNMOUNTED=true
  else
    echo D290_ROOT_OVERLAY_UNMOUNTED=false
    rc=1
  fi
  if [[ -f $target && ! -L $target && $(digest "$target") == "$expected_host" ]]; then
    echo D290_ROOT_HOST_PAM_RESTORED=true
  else
    echo D290_ROOT_HOST_PAM_RESTORED=false
    rc=1
  fi
  if [[ -n $runtime && $runtime == /run/goodix-d290-plasmalogin-[0-9]* && -e $runtime ]] && ! mountpoint -q "$target"; then
    if [[ -f $runtime/plasmalogin ]]; then
      if [[ ! -L $runtime/plasmalogin && $(digest "$runtime/plasmalogin") == "$expected_candidate" ]]; then
        rm -f -- "$runtime/plasmalogin"
      else
        rc=1
      fi
    fi
    rmdir -- "$runtime" 2>/dev/null || rc=1
  fi
  if [[ -z $runtime || ! -e $runtime ]]; then
    echo D290_ROOT_RUNTIME_REMOVED=true
  else
    echo D290_ROOT_RUNTIME_REMOVED=false
    rc=1
  fi
  return "$rc"
}

on_exit () {
  local rc=$?
  trap - EXIT
  cleanup_overlay || rc=1
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' HUP INT TERM

[[ $EUID -eq 0 && $operator_uid =~ ^[1-9][0-9]*$ ]]
runtime=/run/goodix-d290-plasmalogin-$operator_uid
if [[ $mode == --recover ]]; then
  if mountpoint -q "$target"; then
    [[ $(digest "$target") == "$expected_candidate" ]]
    mounted=true
  fi
  exit 0
fi

[[ ! -e $runtime ]]
[[ -f $target && ! -L $target ]]
! mountpoint -q "$target"
[[ $(digest "$target") == "$expected_host" ]]
[[ -f $candidate && ! -L $candidate && $(digest "$candidate") == "$expected_candidate" ]]

daemon_pid=$(systemctl show plasmalogin.service -p MainPID --value)
[[ $daemon_pid =~ ^[1-9][0-9]*$ ]]
[[ $(awk '/^Uid:/ {print $2}' "/proc/$daemon_pid/status") == 0 ]]
[[ $(<"/proc/$daemon_pid/comm") == plasmalogin ]]
[[ $(tr '\0' ' ' <"/proc/$daemon_pid/cmdline") == '/usr/bin/plasmalogin ' ]]
[[ $(awk -F: 'NR==1 {print $NF}' "/proc/$daemon_pid/cgroup") == /system.slice/plasmalogin.service ]]
[[ $(readlink -f "/proc/$daemon_pid/exe") == /usr/bin/plasmalogin ]]
[[ $(stat -Lc %i /proc/self/ns/mnt) == $(stat -Lc %i "/proc/$daemon_pid/ns/mnt") ]]

install -d -o root -g root -m 0700 "$runtime"
install -o root -g root -m 0644 "$candidate" "$runtime/plasmalogin"
chcon --reference="$target" "$runtime/plasmalogin"
mount --bind "$runtime/plasmalogin" "$target"
mounted=true
mount -o remount,bind,ro "$target"
mountpoint -q "$target"
[[ $(digest "$target") == "$expected_candidate" ]]
findmnt -n -o OPTIONS --target "$target" | tr ',' '\n' | grep -Fx ro >/dev/null
echo D290_ROOT_DAEMON_IDENTITY=true
echo D290_ROOT_NAMESPACE_MATCH=true
echo D290_ROOT_OVERLAY_READ_ONLY=true
echo D290_ROOT_OVERLAY_READY=true

IFS= read -r command
[[ $command == RELEASE ]]
