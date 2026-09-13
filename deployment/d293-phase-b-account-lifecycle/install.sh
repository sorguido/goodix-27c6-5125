#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
source_hook=$here/50-goodix-fprint-account-delete
source_policy=$here/goodix_fprint_account_delete.te
source_fc=$here/goodix_fprint_account_delete.fc
policy_name=goodix_fprint_account_delete
policy_priority=400
policy_type=goodix_fprint_account_delete_exec_t
policy_rpm=selinux-policy-targeted-44.8-1.fc44.noarch
policy_hll=/usr/libexec/selinux/hll/pp

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
policy_marker=$(p /etc/goodix-27c6-5125/d293-b5-selinux-policy.test-state)
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

cleanup_policy_build() {
  if [[ -n ${policy_build_dir:-} ]]; then
    [[ $policy_build_dir == /tmp/d293-b5-policy.* && -d $policy_build_dir &&
       -O $policy_build_dir && ! -L $policy_build_dir ]] || return 1
    rm -f -- "$policy_build_dir/$policy_name.mod" "$policy_build_dir/$policy_name.pp"
    rmdir -- "$policy_build_dir"
    policy_build_dir=
  fi
}

policy_entries() {
  semodule -lfull -m | awk -v name="$policy_name" '$2 == name { print }'
}

policy_checksum() {
  semodule -l -m | awk -v name="$policy_name" '$1 == name { print $2 }'
}

policy_installed_exact() {
  local expected=$1 entries checksum priority_matches
  if [[ $test_mode == true ]]; then
    require_regular "$policy_marker" policy_module_missing
    [[ $(<"$policy_marker") == "$expected" ]] || fail policy_module_drift
    return
  fi
  entries=$(policy_entries)
  [[ $(printf '%s\n' "$entries" | sed '/^$/d' | wc -l) -eq 1 ]] || fail policy_module_drift
  priority_matches=$(printf '%s\n' "$entries" | awk -v priority="$policy_priority" \
    -v name="$policy_name" '$1 == priority && $2 == name { count++ } END { print count + 0 }')
  [[ $priority_matches -eq 1 ]] || fail policy_module_priority_drift
  checksum=$(policy_checksum)
  [[ $checksum == "sha256:$expected" ]] || fail policy_module_drift
}

validate_selinux_boundary() {
  local hook_context fprint_context installed
  [[ $test_mode == true ]] && {
    [[ ! -e $policy_marker && ! -L $policy_marker ]] || fail policy_module_collision
    return
  }
  [[ $(getenforce) == Enforcing ]] || fail selinux_not_enforcing
  [[ $(rpm -q selinux-policy-targeted) == "$policy_rpm" ]] || fail unsupported_selinux_policy
  for command in checkmodule semodule_package semodule matchpathcon restorecon; do
    command -v "$command" >/dev/null || fail "missing_$command"
  done
  require_regular "$policy_hll" policy_hll_missing
  installed=$(policy_entries)
  [[ -z $installed ]] || fail policy_module_collision
  hook_context=$(matchpathcon -n "$hook")
  [[ $hook_context == system_u:object_r:shadow_t:s0 ]] || fail unexpected_hook_default_context
  fprint_context=$(matchpathcon -n /var/lib/fprint)
  [[ $fprint_context == system_u:object_r:fprintd_var_lib_t:s0 ]] || fail unexpected_fprint_context
}

build_policy() {
  policy_build_dir=$(mktemp -d /tmp/d293-b5-policy.XXXXXX) || fail policy_build_tmp_failed
  policy_mod=$policy_build_dir/$policy_name.mod
  policy_package=$policy_build_dir/$policy_name.pp
  checkmodule -M -m -E -o "$policy_mod" "$source_policy" || fail policy_compile_failed
  semodule_package -o "$policy_package" -m "$policy_mod" -f "$source_fc" ||
    fail policy_package_failed
  policy_package_sha=$(digest "$policy_package")
  policy_cil_sha=$("$policy_hll" "$policy_package" | sha256sum | awk '{print $1}')
  is_sha256 "$policy_package_sha" && is_sha256 "$policy_cil_sha" || fail policy_digest_failed
}

install_policy() {
  if [[ $test_mode == true ]]; then
    printf '%s\n' "$policy_cil_sha" >"$policy_marker"
  else
    semodule -X "$policy_priority" -i "$policy_package" || fail policy_install_failed
  fi
  install_policy_installed=true
  policy_installed_exact "$policy_cil_sha"
  if [[ $test_mode != true ]]; then
    [[ $(matchpathcon -n "$hook") == system_u:object_r:$policy_type:s0 ]] ||
      fail policy_file_context_not_effective
  fi
}

remove_policy() {
  if [[ $test_mode == true ]]; then
    rm -f -- "$policy_marker"
  else
    semodule -X "$policy_priority" -r "$policy_name" || fail policy_remove_failed
    [[ -z $(policy_entries) ]] || fail policy_remove_incomplete
  fi
}

cleanup_partial_install() {
  local status=$? cleanup_failed=false remaining=
  if [[ ${install_cleanup_armed:-false} == true ]]; then
    set +e
    rm -f -- "${install_pending:-}" || cleanup_failed=true
    if [[ ${install_hook_copied:-false} == true ]]; then
      rm -f -- "${install_hook:-}" || cleanup_failed=true
    fi
    if [[ ${install_policy_installed:-false} == true ]]; then
      if [[ $test_mode == true ]]; then
        rm -f -- "$policy_marker" || cleanup_failed=true
      else
        semodule -X "$policy_priority" -r "$policy_name" || cleanup_failed=true
        remaining=$(policy_entries) || cleanup_failed=true
        [[ -z $remaining ]] || cleanup_failed=true
      fi
    fi
    if [[ ${install_created_hook_parent:-false} == true ]]; then
      rmdir -- "${install_hook_parent:-}" || cleanup_failed=true
    fi
    if [[ ${install_created_shadow_parent:-false} == true ]]; then
      rmdir -- "${install_shadow_parent:-}" || cleanup_failed=true
    fi
    cleanup_policy_build || cleanup_failed=true
    if [[ $cleanup_failed == true ]]; then
      printf 'D293_B5_INSTALL=FAIL reason=partial_install_cleanup_incomplete\n' >&2
    else
      printf 'D293_B5_INSTALL=FAIL reason=partial_install_rolled_back\n' >&2
    fi
  else
    cleanup_policy_build
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
  local caller=$1 head=$2 runtime created_shadow created_hook_parent hook_sha install_sha
  local policy_source_sha policy_fc_sha pending
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
  require_regular "$source_policy" source_policy_missing
  require_regular "$source_fc" source_fc_missing
  runtime=$(validate_d293_baseline)
  require_directory "$state_parent" state_parent_missing
  [[ ! -e $state && ! -L $state && ! -e $hook && ! -L $hook ]] || fail already_installed_or_collision
  validate_selinux_boundary

  install_cleanup_armed=true
  install_hook_copied=false
  install_policy_installed=false
  install_created_shadow_parent=false
  install_created_hook_parent=false
  install_pending=$state.pending.$$
  install_state=$state
  install_hook=$hook
  install_hook_parent=$hook_parent
  install_shadow_parent=$shadow_parent
  trap cleanup_partial_install EXIT

  build_policy
  install_policy
  if [[ $test_mode == true && ${D293_B5_TEST_FAIL_AFTER_POLICY:-false} == true ]]; then
    fail injected_failure_after_policy
  fi
  created_shadow=$(ensure_directory "$shadow_parent" 0755)
  install_created_shadow_parent=$created_shadow
  created_hook_parent=$(ensure_directory "$hook_parent" 0755)
  install_created_hook_parent=$created_hook_parent
  install -m 0755 -- "$source_hook" "$hook"
  install_hook_copied=true
  if [[ $test_mode != true ]]; then
    restorecon -F "$hook" || fail hook_relabel_failed
    matchpathcon -V "$hook" >/dev/null || fail hook_label_drift
    [[ $(stat -c %C "$hook") == system_u:object_r:$policy_type:s0 ]] || fail hook_label_drift
  fi

  hook_sha=$(digest "$hook")
  install_sha=$(digest "$here/install.sh")
  policy_source_sha=$(digest "$source_policy")
  policy_fc_sha=$(digest "$source_fc")
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
D293_B5_SELINUX_POLICY_RPM=$policy_rpm
D293_B5_POLICY_NAME=$policy_name
D293_B5_POLICY_PRIORITY=$policy_priority
D293_B5_POLICY_TYPE=$policy_type
D293_B5_POLICY_SOURCE_SHA256=$policy_source_sha
D293_B5_POLICY_FC_SHA256=$policy_fc_sha
D293_B5_POLICY_PACKAGE_SHA256=$policy_package_sha
D293_B5_POLICY_CIL_SHA256=$policy_cil_sha
D293_B5_PREVIOUS_HOOK_CONTEXT=system_u:object_r:shadow_t:s0
D293_B5_HOOK_CONTEXT=system_u:object_r:$policy_type:s0
EOF
  chmod 0600 "$pending"
  mv -- "$pending" "$state"
  install_cleanup_armed=false
  cleanup_policy_build
  trap - EXIT
  printf '%s\n' \
    'D293_B5_INSTALL=PASS' \
    "D293_B5_REPOSITORY_HEAD=$head" \
    "D293_B5_D293_RUNTIME=$runtime" \
    "D293_B5_SELINUX_POLICY=$policy_name" \
    "D293_B5_SELINUX_POLICY_PRIORITY=$policy_priority" \
    'D293_B5_SENSOR_ACCESS=0'
}

root_uninstall() {
  local caller=$1 expected_hook expected_install created_shadow created_hook_parent
  local expected_policy_source expected_policy_fc expected_policy_package expected_policy_cil
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
  expected_policy_source=$(state_value "$state" D293_B5_POLICY_SOURCE_SHA256) || fail state_invalid
  expected_policy_fc=$(state_value "$state" D293_B5_POLICY_FC_SHA256) || fail state_invalid
  expected_policy_package=$(state_value "$state" D293_B5_POLICY_PACKAGE_SHA256) || fail state_invalid
  expected_policy_cil=$(state_value "$state" D293_B5_POLICY_CIL_SHA256) || fail state_invalid
  [[ $(state_value "$state" D293_B5_SELINUX_POLICY_RPM) == "$policy_rpm" ]] || fail state_invalid
  [[ $(state_value "$state" D293_B5_POLICY_NAME) == "$policy_name" ]] || fail state_invalid
  [[ $(state_value "$state" D293_B5_POLICY_PRIORITY) == "$policy_priority" ]] || fail state_invalid
  [[ $(state_value "$state" D293_B5_POLICY_TYPE) == "$policy_type" ]] || fail state_invalid
  [[ $(state_value "$state" D293_B5_PREVIOUS_HOOK_CONTEXT) == system_u:object_r:shadow_t:s0 ]] || fail state_invalid
  [[ $(state_value "$state" D293_B5_HOOK_CONTEXT) == system_u:object_r:$policy_type:s0 ]] || fail state_invalid
  [[ $created_shadow == true || $created_shadow == false ]] || fail state_invalid
  [[ $created_hook_parent == true || $created_hook_parent == false ]] || fail state_invalid
  for value in "$expected_hook" "$expected_install" "$expected_policy_source" \
    "$expected_policy_fc" "$expected_policy_package" "$expected_policy_cil"; do
    is_sha256 "$value" || fail state_invalid
  done
  require_regular "$hook" hook_missing
  [[ $(digest "$hook") == "$expected_hook" ]] || fail hook_drift
  [[ $(digest "$here/install.sh") == "$expected_install" ]] || fail installer_drift
  [[ $(digest "$source_policy") == "$expected_policy_source" ]] || fail policy_source_drift
  [[ $(digest "$source_fc") == "$expected_policy_fc" ]] || fail policy_fc_drift
  policy_installed_exact "$expected_policy_cil"
  if [[ $test_mode != true ]]; then
    [[ $(rpm -q selinux-policy-targeted) == "$policy_rpm" ]] || fail unsupported_selinux_policy
    matchpathcon -V "$hook" >/dev/null || fail hook_label_drift
    [[ $(stat -c %C "$hook") == system_u:object_r:$policy_type:s0 ]] || fail hook_label_drift
  fi
  validate_d293_baseline >/dev/null
  if [[ $created_hook_parent == true ]]; then
    [[ $(find "$hook_parent" -mindepth 1 -maxdepth 1 -printf '%f\n') == 50-goodix-fprint-account-delete ]] ||
      fail hook_parent_gained_entries
  fi
  if [[ $created_shadow == true ]]; then
    [[ $(find "$shadow_parent" -mindepth 1 -maxdepth 1 -printf '%f\n') == userdel-pre.d ]] ||
      fail shadow_parent_gained_entries
  fi

  remove_policy
  rm -f -- "$hook"
  if [[ $created_hook_parent == true ]]; then rmdir -- "$hook_parent"; fi
  if [[ $created_shadow == true ]]; then rmdir -- "$shadow_parent"; fi
  rm -f -- "$state"
  printf '%s\n' \
    'D293_B5_ROLLBACK=PASS' \
    'D293_B5_SELINUX_POLICY_REMOVED=true' \
    'D293_B5_D293_BASELINE=PRESERVED' \
    'D293_B5_SENSOR_ACCESS=0'
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
    [[ $(rpm -q shadow-utils) == shadow-utils-4.19.0-7.fc44.x86_64 ]] || fail unsupported_shadow_utils
    [[ $(rpm -q selinux-policy-targeted) == "$policy_rpm" ]] || fail unsupported_selinux_policy
    [[ $(getenforce) == Enforcing ]] || fail selinux_not_enforcing
    caller=$(id -un)
    [[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || fail installer_invalid
    validate_d293_baseline >/dev/null
    sudo -- "$here/install.sh" --root-install "$caller" "$head"
    ;;
  *) fail invalid_arguments ;;
esac
