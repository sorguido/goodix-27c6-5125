#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

[[ $# -ge 1 ]]
mode=$1
kwin_pid=${2:-}
if [[ $mode == --hold ]]; then
  [[ $# -eq 2 && $kwin_pid =~ ^[0-9]+$ ]]
elif [[ $mode == --recover ]]; then
  [[ $# -eq 1 ]]
else
  exit 2
fi
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=kwin-identity.sh
source "$here/kwin-identity.sh"
target=/etc/pam.d/kde-fingerprint
candidate=$here/goodix-d289-kde-fingerprint.pam
expected_host=8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437
expected_candidate=126af52cd63c346fdf9fb053172506a49f851d45b0a49e4490fd807a12c328b6
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
    echo D289_ROOT_OVERLAY_UNMOUNTED=true
  else
    echo D289_ROOT_OVERLAY_UNMOUNTED=false
    rc=1
  fi
  if [[ -f $target && ! -L $target && $(digest "$target") == "$expected_host" ]]; then
    echo D289_ROOT_HOST_PAM_RESTORED=true
  else
    echo D289_ROOT_HOST_PAM_RESTORED=false
    rc=1
  fi
  if [[ -n $runtime && $runtime == /run/goodix-d289-real-lock-[0-9]* && -e $runtime ]] && ! mountpoint -q "$target"; then
    if [[ -f $runtime/kde-fingerprint ]]; then
      if [[ ! -L $runtime/kde-fingerprint && $(digest "$runtime/kde-fingerprint") == "$expected_candidate" ]]; then
        rm -f -- "$runtime/kde-fingerprint"
      else
        rc=1
      fi
    fi
    rmdir -- "$runtime" 2>/dev/null || rc=1
  fi
  if [[ -z $runtime || ! -e $runtime ]]; then
    echo D289_ROOT_RUNTIME_REMOVED=true
  else
    echo D289_ROOT_RUNTIME_REMOVED=false
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
runtime=/run/goodix-d289-real-lock-$operator_uid
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
D289_PROC_ROOT=/proc d289_verify_kwin_identity "$kwin_pid" "$operator_uid" >/dev/null
[[ $(stat -Lc %i /proc/self/ns/mnt) == $(stat -Lc %i "/proc/$kwin_pid/ns/mnt") ]]

install -d -o root -g root -m 0700 "$runtime"
install -o root -g root -m 0644 "$candidate" "$runtime/kde-fingerprint"
chcon --reference="$target" "$runtime/kde-fingerprint"
mount --bind "$runtime/kde-fingerprint" "$target"
mounted=true
mount -o remount,bind,ro "$target"
mountpoint -q "$target"
[[ $(digest "$target") == "$expected_candidate" ]]
findmnt -n -o OPTIONS --target "$target" | tr ',' '\n' | grep -Fx ro >/dev/null
echo D289_ROOT_NAMESPACE_MATCH=true
echo D289_ROOT_OVERLAY_READ_ONLY=true
echo D289_ROOT_OVERLAY_READY=true

IFS= read -r command
[[ $command == RELEASE ]]
