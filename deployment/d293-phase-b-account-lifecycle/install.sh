#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
source_hook=$here/50-goodix-fprint-account-delete

fail() {
  printf 'D293_B5_INSTALL=FAIL reason=%s\n' "$1" >&2
  exit 1
}

is_sha256() { [[ ${1:-} =~ ^[0-9a-f]{64}$ ]]; }
is_git_sha() { [[ ${1:-} =~ ^[0-9a-f]{40}$ ]]; }
digest() { sha256sum "$1" | awk '{print $1}'; }

test_mode=${D293_B5_TEST_MODE:-false}
fsroot=
if [[ $test_mode == true ]]; then
  fsroot=${D293_B5_TEST_ROOT:?}
  [[ $fsroot == /tmp/d293-b5-test.* && -d $fsroot && -O $fsroot && ! -L $fsroot ]] ||
    fail unsafe_test_root
elif [[ $test_mode != false ]]; then
  fail invalid_test_mode
fi

p() { printf '%s%s\n' "$fsroot" "$1"; }
shadow_parent=$(p /etc/shadow-maint)
hook_parent=$(p /etc/shadow-maint/userdel-pre.d)
hook=$(p /etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete)
state_parent=$(p /etc/goodix-27c6-5125)
state=$(p /etc/goodix-27c6-5125/d293-phase-b-account-lifecycle.state)
d293_wrapper=$(p /usr/local/sbin/goodix-d293-native-fprintd)
d293_dropin=$(p /etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf)

state_value() {
  local file=$1 key=$2 count value
  count=$(awk -F= -v key="$key" '$1 == key { count++ } END { print count + 0 }' "$file")
  [[ $count -eq 1 ]] || return 1
  value=$(awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print }' "$file")
  [[ $value != *$'\n'* ]] || return 1
  printf '%s\n' "$value"
}

require_regular() { [[ -f $1 && ! -L $1 ]] || fail "$2"; }
require_directory() { [[ -d $1 && ! -L $1 ]] || fail "$2"; }

ensure_directory() {
  local path=$1 mode=$2
  if [[ -e $path || -L $path ]]; then
    require_directory "$path" directory_collision
    printf 'false\n'
  else
    mkdir -m "$mode" -- "$path"
    printf 'true\n'
  fi
}

cleanup_partial_install() {
  local status=$?
  if [[ ${install_cleanup_armed:-false} == true ]]; then
    set +e
    rm -f -- "${install_pending:-}" "${install_state:-}"
    if [[ ${install_hook_copied:-false} == true ]]; then
      rm -f -- "${install_hook:-}"
    fi
    if [[ ${install_created_hook_parent:-false} == true ]]; then
      rmdir -- "${install_hook_parent:-}"
    fi
    if [[ ${install_created_shadow_parent:-false} == true ]]; then
      rmdir -- "${install_shadow_parent:-}"
    fi
    printf 'D293_B5_INSTALL=FAIL reason=partial_install_rolled_back\n' >&2
  fi
  exit "$status"
}

validate_d293_baseline() {
  local runtime
  require_regular "$d293_wrapper" d293_wrapper_missing
  require_regular "$d293_dropin" d293_dropin_missing
  grep -Fx 'ExecStart=/usr/local/sbin/goodix-d293-native-fprintd' "$d293_dropin" >/dev/null ||
    fail d293_dropin_not_effective
  runtime=$(sed -n "s|^runtime='\(/usr/local/lib64/goodix-27c6-5125/d293-native-[0-9a-f]\\{40\\}\)'$|\\1|p" "$d293_wrapper")
  [[ $(printf '%s\n' "$runtime" | sed '/^$/d' | wc -l) -eq 1 ]] || fail d293_runtime_invalid
  if [[ -n $fsroot ]]; then runtime=$fsroot$runtime; fi
  require_directory "$runtime" d293_runtime_missing
  printf '%s\n' "${runtime#"$fsroot"}"
}

root_install() {
  local caller=$1 head=$2 runtime created_shadow created_hook_parent hook_sha install_sha pending
  [[ $test_mode == true || $EUID -eq 0 ]] || fail root_required
  [[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || fail installer_invalid
  is_git_sha "$head" || fail head_invalid
  if [[ $test_mode != true ]]; then
    [[ ${SUDO_USER:-} == "$caller" ]] || fail installer_identity_mismatch
    [[ $(git -C "$root" branch --show-current) == development ]] || fail wrong_branch
    [[ $(git -C "$root" rev-parse HEAD) == "$head" ]] || fail head_mismatch
    [[ $(git -C "$root" rev-parse origin/development) == "$head" ]] || fail origin_mismatch
    [[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
  fi
  require_regular "$source_hook" source_hook_missing
  runtime=$(validate_d293_baseline)
  require_directory "$state_parent" state_parent_missing
  [[ ! -e $state && ! -L $state && ! -e $hook && ! -L $hook ]] || fail already_installed_or_collision
  install_cleanup_armed=true
  install_hook_copied=false
  install_created_shadow_parent=false
  install_created_hook_parent=false
  install_pending=$state.pending.$$
  install_state=$state
  install_hook=$hook
  install_hook_parent=$hook_parent
  install_shadow_parent=$shadow_parent
  trap cleanup_partial_install EXIT
  created_shadow=$(ensure_directory "$shadow_parent" 0755)
  install_created_shadow_parent=$created_shadow
  created_hook_parent=$(ensure_directory "$hook_parent" 0755)
  install_created_hook_parent=$created_hook_parent
  install -m 0755 -- "$source_hook" "$hook"
  install_hook_copied=true
  hook_sha=$(digest "$hook")
  install_sha=$(digest "$here/install.sh")
  pending=$install_pending
  cat >"$pending" <<EOF
D293_B5_STATUS=ACTIVE
D293_B5_INSTALLER=$caller
D293_B5_REPOSITORY_HEAD=$head
D293_B5_D293_RUNTIME=$runtime
D293_B5_HOOK_SHA256=$hook_sha
D293_B5_INSTALL_SCRIPT_SHA256=$install_sha
D293_B5_CREATED_SHADOW_PARENT=$created_shadow
D293_B5_CREATED_HOOK_PARENT=$created_hook_parent
EOF
  chmod 0600 "$pending"
  mv -- "$pending" "$state"
  install_cleanup_armed=false
  trap - EXIT
  printf '%s\n' \
    'D293_B5_INSTALL=PASS' \
    "D293_B5_REPOSITORY_HEAD=$head" \
    "D293_B5_D293_RUNTIME=$runtime" \
    'D293_B5_SENSOR_ACCESS=0'
}

root_uninstall() {
  local caller=$1 expected_hook expected_install created_shadow created_hook_parent
  [[ $test_mode == true || $EUID -eq 0 ]] || fail root_required
  [[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || fail caller_invalid
  [[ $test_mode == true || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  require_regular "$state" state_missing
  [[ $(stat -c %a "$state") == 600 ]] || fail state_mode_drift
  [[ $(state_value "$state" D293_B5_STATUS) == ACTIVE ]] || fail state_invalid
  [[ $(state_value "$state" D293_B5_INSTALLER) == "$caller" ]] || fail installer_mismatch
  expected_hook=$(state_value "$state" D293_B5_HOOK_SHA256) || fail state_invalid
  expected_install=$(state_value "$state" D293_B5_INSTALL_SCRIPT_SHA256) || fail state_invalid
  created_shadow=$(state_value "$state" D293_B5_CREATED_SHADOW_PARENT) || fail state_invalid
  created_hook_parent=$(state_value "$state" D293_B5_CREATED_HOOK_PARENT) || fail state_invalid
  [[ $created_shadow == true || $created_shadow == false ]] || fail state_invalid
  [[ $created_hook_parent == true || $created_hook_parent == false ]] || fail state_invalid
  is_sha256 "$expected_hook" && is_sha256 "$expected_install" || fail state_invalid
  require_regular "$hook" hook_missing
  [[ $(digest "$hook") == "$expected_hook" ]] || fail hook_drift
  [[ $(digest "$here/install.sh") == "$expected_install" ]] || fail installer_drift
  validate_d293_baseline >/dev/null
  if [[ $created_hook_parent == true ]]; then
    [[ $(find "$hook_parent" -mindepth 1 -maxdepth 1 -printf '%f\n') == 50-goodix-fprint-account-delete ]] ||
      fail hook_parent_gained_entries
  fi
  if [[ $created_shadow == true ]]; then
    [[ $(find "$shadow_parent" -mindepth 1 -maxdepth 1 -printf '%f\n') == userdel-pre.d ]] ||
      fail shadow_parent_gained_entries
  fi
  rm -f -- "$hook"
  if [[ $created_hook_parent == true ]]; then rmdir -- "$hook_parent"; fi
  if [[ $created_shadow == true ]]; then rmdir -- "$shadow_parent"; fi
  rm -f -- "$state"
  printf '%s\n' 'D293_B5_ROLLBACK=PASS' 'D293_B5_D293_BASELINE=PRESERVED' 'D293_B5_SENSOR_ACCESS=0'
}

case ${1:-} in
  --root-install)
    [[ $# -eq 3 ]] || fail invalid_internal_arguments
    root_install "$2" "$3"
    ;;
  --root-uninstall)
    [[ $# -eq 2 ]] || fail invalid_internal_arguments
    root_uninstall "$2"
    ;;
  '')
    [[ $test_mode == false ]] || fail test_mode_requires_internal_entrypoint
    [[ $EUID -ne 0 ]] || fail entrypoint_must_be_unprivileged
    [[ $(git -C "$root" branch --show-current) == development ]] || fail wrong_branch
    head=$(git -C "$root" rev-parse HEAD)
    [[ $(git -C "$root" rev-parse origin/development) == "$head" ]] || fail origin_mismatch
    [[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
    [[ $(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' shadow-utils) == 4.19.0-7.fc44.x86_64 ]] ||
      fail unsupported_shadow_utils
    caller=$(id -un)
    [[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || fail installer_invalid
    validate_d293_baseline >/dev/null
    sudo -- "$here/install.sh" --root-install "$caller" "$head"
    ;;
  *) fail invalid_arguments ;;
esac
