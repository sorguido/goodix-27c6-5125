#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
repo=$(git -C "$here" rev-parse --show-toplevel)
test_root=${GOODIX_MANAGED_TEST_ROOT:-}
if [[ -n $test_root ]]; then
  [[ $test_root == /tmp/goodix-managed-test.* && -d $test_root && -O $test_root && ! -L $test_root ]] || {
    echo 'PHASE_C_TRANSACTION=FAIL reason=unsafe_test_root' >&2; exit 1;
  }
fi
p() { printf '%s%s\n' "$test_root" "$1"; }

state_dir=$(p /var/lib/goodix-27c6-5125-managed)
state=$state_dir/state
runtime_root=$(p /usr/lib64/goodix-27c6-5125)
current_link=$runtime_root/current
wrapper=$(p /usr/libexec/goodix-27c6-5125/fprintd-wrapper)
dropin=$(p /etc/systemd/system/fprintd.service.d/99-goodix-27c6-5125-managed.conf)
hook=$(p /etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete)
material=$(p /var/lib/goodix-5125-poc)
policy_name=goodix_fprint_account_delete
policy_priority=400
required_candidate=(
  MANIFEST SHA256SUMS LICENSE GPL-2.0-or-later.txt LGPL-2.1-or-later.txt
  libfprint-2.so.2.0.0 libgusb.so.2
  libopencv_core.so.413 libopencv_features2d.so.413 libopencv_flann.so.413
  libopencv_imgproc.so.413 fprintd-wrapper 50-goodix-fprint-account-delete
  goodix_fprint_account_delete.te goodix_fprint_account_delete.fc
  99-goodix-27c6-5125-managed.conf
)
required_material=(target-material-manifest.json transport-material.bin target-config-90.bin gfusb.dll fdt-cache.bin)

fail() { printf 'PHASE_C_TRANSACTION=FAIL reason=%s\n' "$1" >&2; exit 1; }
digest() { sha256sum "$1" | awk '{print $1}'; }
is_sha() { [[ ${1:-} =~ ^[0-9a-f]{64}$ ]]; }
is_commit() { [[ ${1:-} =~ ^[0-9a-f]{40}$ ]]; }
state_value() {
  local key=$1 count
  count=$(awk -F= -v key="$key" '$1 == key { n++ } END { print n + 0 }' "$state")
  [[ $count -eq 1 ]] || return 1
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print }' "$state"
}
manifest_value() {
  local candidate=$1 key=$2 count
  count=$(awk -F= -v key="$key" '$1 == key { n++ } END { print n + 0 }' "$candidate/MANIFEST")
  [[ $count -eq 1 ]] || return 1
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print }' "$candidate/MANIFEST"
}
material_ready() {
  [[ -d $material && ! -L $material ]] || return 1
  [[ $(stat -c '%u:%g:%a' "$material") == 0:0:700 || -n $test_root ]] || return 1
  local name
  for name in "${required_material[@]}"; do
    [[ -f $material/$name && ! -L $material/$name ]] || return 1
    [[ -n $test_root || $(stat -c '%u:%g:%a' "$material/$name") == 0:0:600 ]] || return 1
  done
}
host_action() {
  [[ -n $test_root ]] && return 0
  "$@"
}
service_state() {
  if [[ -n $test_root ]]; then printf 'inactive\n'; else systemctl is-active fprintd.service || true; fi
}
verify_repo_provenance() {
  local expected=$1
  [[ -n $test_root || $EUID -eq 0 ]] || fail root_required
  if [[ -n $test_root ]]; then
    is_commit "$expected" || fail source_head_invalid
    return
  fi
  [[ $(git -C "$repo" branch --show-current) == development ]] || fail wrong_branch
  [[ $(git -C "$repo" rev-parse HEAD) == "$expected" ]] || fail source_head_mismatch
  [[ $(git -C "$repo" rev-parse origin/development) == "$expected" ]] || fail origin_head_mismatch
  [[ -z $(git -C "$repo" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
}
verify_candidate() {
  local candidate=$1 caller=$2 frozen=${3:-false} name commit count
  [[ $candidate == /* && -d $candidate && ! -L $candidate ]] || fail candidate_invalid
  if [[ $frozen == true ]]; then
    [[ -n $test_root || $(stat -c %U "$candidate") == root ]] || fail frozen_candidate_owner_invalid
  else
    [[ -n $test_root || $(stat -c %U "$candidate") == "$caller" ]] || fail candidate_owner_invalid
  fi
  for name in "${required_candidate[@]}"; do
    [[ -f $candidate/$name && ! -L $candidate/$name ]] || fail "candidate_${name}_invalid"
  done
  count=$(find "$candidate" -mindepth 1 -maxdepth 1 -type f -printf '%f\n' | wc -l)
  [[ $count -eq ${#required_candidate[@]} ]] || fail candidate_file_set_invalid
  [[ -z $(find "$candidate" -mindepth 1 -maxdepth 1 ! -type f -print -quit) ]] || fail candidate_nonregular_entry
  (cd "$candidate" && sha256sum -c SHA256SUMS >/dev/null) || fail candidate_digest_mismatch
  [[ $(manifest_value "$candidate" PHASE_C_DISTRIBUTION_MODEL) == SOURCE_FIRST_MANAGED_INSTALL ]] || fail distribution_model_invalid
  [[ $(manifest_value "$candidate" RPM_OFFICIAL_DISTRIBUTION) == false ]] || fail rpm_policy_invalid
  [[ $(manifest_value "$candidate" PROTECTED_MATERIAL_INCLUDED) == false ]] || fail candidate_contains_material
  commit=$(manifest_value "$candidate" SOURCE_COMMIT) || fail candidate_commit_missing
  is_commit "$commit" || fail candidate_commit_invalid
  verify_repo_provenance "$commit"
  printf '%s\n' "$commit"
}
freeze_candidate() {
  local source=$1 caller=$2 freeze name
  [[ $source == /* && -d $source && ! -L $source ]] || fail candidate_invalid
  [[ -n $test_root || $(stat -c %U "$source") == "$caller" ]] || fail candidate_owner_invalid
  for name in "${required_candidate[@]}"; do
    [[ -f $source/$name && ! -L $source/$name ]] || fail "candidate_${name}_invalid"
  done
  if [[ -n $test_root ]]; then
    freeze=$(mktemp -d "$test_root/goodix-managed-candidate.XXXXXX")
  else
    freeze=$(mktemp -d /var/tmp/goodix-managed-candidate.XXXXXX)
  fi
  chmod 0700 "$freeze"
  for name in "${required_candidate[@]}"; do install -m 0600 "$source/$name" "$freeze/$name"; done
  printf '%s\n' "$freeze"
}
remove_frozen_candidate() {
  local freeze=${1:-}
  [[ -n $freeze && -d $freeze && ! -L $freeze ]] || return 0
  if [[ -n $test_root ]]; then
    [[ $freeze == "$test_root"/goodix-managed-candidate.* ]] || return 1
  else
    [[ $freeze == /var/tmp/goodix-managed-candidate.* ]] || return 1
  fi
  find "$freeze" -xdev -depth -delete
}
install_runtime_tree() {
  local candidate=$1 commit=$2 destination=$runtime_root/$commit library
  [[ ! -e $destination && ! -L $destination ]] || fail runtime_commit_collision
  mkdir -p -- "$runtime_root"
  install -d -m 0755 -- "$destination"
  for library in libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
    libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413; do
    install -m 0644 -- "$candidate/$library" "$destination/$library"
  done
  ln -s libfprint-2.so.2.0.0 "$destination/libfprint-2.so.2"
  ln -s libfprint-2.so.2 "$destination/libfprint-2.so"
}
tree_digest() {
  local directory=$1
  (cd "$directory" && find . -maxdepth 1 -type f -printf '%P\n' | LC_ALL=C sort | xargs -r sha256sum) |
    sha256sum | awk '{print $1}'
}
install_policy() {
  [[ -n $test_root ]] && { install -D -m 0600 /dev/null "$state_dir/policy.test"; return; }
  local work mod package
  work=$(mktemp -d /tmp/goodix-managed-policy.XXXXXX)
  trap 'find "$work" -xdev -depth -delete' RETURN
  mod=$work/$policy_name.mod
  package=$work/$policy_name.pp
  checkmodule -M -m -E -o "$mod" "$1/goodix_fprint_account_delete.te"
  semodule_package -o "$package" -m "$mod" -f "$1/goodix_fprint_account_delete.fc"
  [[ -z $(semodule -lfull | awk -v name="$policy_name" '$2 == name { print }') ]] || fail policy_collision
  semodule -X "$policy_priority" -i "$package"
  find "$work" -xdev -depth -delete
  trap - RETURN
}
remove_policy() {
  if [[ -n $test_root ]]; then rm -f -- "$state_dir/policy.test"; else semodule -X "$policy_priority" -r "$policy_name"; fi
}
write_state() {
  local current=$1 previous=$2 installer=$3 service_before=$4 current_digest=$5 previous_digest=$6
  local pending=$state.pending.$$
  {
    echo PHASE_C_STATUS=ACTIVE
    echo PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL
    echo RPM_OFFICIAL_DISTRIBUTION=false
    echo "CURRENT_COMMIT=$current"
    echo "PREVIOUS_COMMIT=$previous"
    echo "INSTALLER=$installer"
    echo "SERVICE_BEFORE=$service_before"
    echo "CURRENT_TREE_SHA256=$current_digest"
    echo "PREVIOUS_TREE_SHA256=$previous_digest"
    echo "WRAPPER_SHA256=$(digest "$wrapper")"
    echo "DROPIN_SHA256=$(digest "$dropin")"
    echo "HOOK_SHA256=$(digest "$hook")"
  } >"$pending"
  chmod 0644 "$pending"
  mv -f -- "$pending" "$state"
}
verify_active() {
  [[ -f $state && ! -L $state ]] || fail state_missing
  [[ $(state_value PHASE_C_STATUS) == ACTIVE ]] || fail state_inactive
  local current previous expected
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
  is_commit "$current" || fail current_commit_invalid
  [[ $previous == NONE ]] || is_commit "$previous" || fail previous_commit_invalid
  [[ -L $current_link && $(readlink "$current_link") == "$current" ]] || fail current_link_drift
  [[ $(tree_digest "$runtime_root/$current") == $(state_value CURRENT_TREE_SHA256) ]] || fail current_tree_drift
  if [[ $previous != NONE ]]; then
    [[ -d $runtime_root/$previous && ! -L $runtime_root/$previous ]] || fail previous_tree_missing
    [[ $(tree_digest "$runtime_root/$previous") == $(state_value PREVIOUS_TREE_SHA256) ]] || fail previous_tree_drift
  fi
  for pair in "$wrapper:WRAPPER_SHA256" "$dropin:DROPIN_SHA256" "$hook:HOOK_SHA256"; do
    expected=$(state_value "${pair#*:}")
    is_sha "$expected" || fail state_hash_invalid
    [[ -f ${pair%%:*} && ! -L ${pair%%:*} && $(digest "${pair%%:*}") == "$expected" ]] || fail managed_file_drift
  done
}

root_install_or_update() {
  local mode=$1 caller=$2 source_candidate=$3 candidate commit current previous service_before
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  candidate=$(freeze_candidate "$source_candidate" "$caller")
  cleanup_kind=none
  cleanup_runtime=
  cleanup_policy=false
  cleanup_old_current=
  cleanup_link_switched=false
  cleanup_service_before=inactive
  cleanup_transaction() {
    local rc=$?
    set +e
    if [[ $rc -ne 0 && $cleanup_kind == update ]]; then
      if [[ $cleanup_link_switched == true && -n $cleanup_old_current ]]; then
        ln -s "$cleanup_old_current" "$runtime_root/current.recovery"
        mv -Tf -- "$runtime_root/current.recovery" "$current_link"
      fi
      [[ -z $cleanup_runtime || ! -d $cleanup_runtime ]] || find "$cleanup_runtime" -xdev -depth -delete
      host_action systemctl daemon-reload
      [[ $cleanup_service_before != active ]] || host_action systemctl start fprintd.service
    elif [[ $rc -ne 0 && $cleanup_kind == fresh ]]; then
      rm -f -- "$current_link" "$wrapper" "$dropin" "$hook" "$state"
      [[ -z $cleanup_runtime || ! -d $cleanup_runtime ]] || find "$cleanup_runtime" -xdev -depth -delete
      rmdir -- "$runtime_root" 2>/dev/null
      [[ $cleanup_policy != true ]] || remove_policy
      rmdir -- "$state_dir" 2>/dev/null
      host_action systemctl daemon-reload
      [[ $cleanup_service_before != active ]] || host_action systemctl start fprintd.service
    fi
    remove_frozen_candidate "$candidate"
    exit "$rc"
  }
  trap cleanup_transaction EXIT
  commit=$(verify_candidate "$candidate" "$caller" true)
  if [[ -f $state ]]; then
    verify_active
    current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
    if [[ $commit == "$current" ]]; then
      printf '%s\n' 'PHASE_C_INSTALL=PASS_ALREADY_CURRENT' "CURRENT_COMMIT=$current"
      remove_frozen_candidate "$candidate"; trap - EXIT; return
    fi
    [[ $mode == update ]] || fail active_install_requires_update
    [[ $previous == NONE ]] || fail rollback_slot_occupied
    [[ $(digest "$candidate/fprintd-wrapper") == $(state_value WRAPPER_SHA256) && \
       $(digest "$candidate/99-goodix-27c6-5125-managed.conf") == $(state_value DROPIN_SHA256) && \
       $(digest "$candidate/50-goodix-fprint-account-delete") == $(state_value HOOK_SHA256) ]] ||
      fail managed_host_assets_changed_requires_fresh_install
    cleanup_kind=update
    cleanup_runtime=$runtime_root/$commit
    cleanup_old_current=$current
    cleanup_service_before=$(state_value SERVICE_BEFORE)
    install_runtime_tree "$candidate" "$commit"
    ln -s "$commit" "$runtime_root/current.next"
    mv -Tf -- "$runtime_root/current.next" "$current_link"
    cleanup_link_switched=true
    host_action systemctl restart fprintd.service
    write_state "$commit" "$current" "$(state_value INSTALLER)" "$cleanup_service_before" \
      "$(tree_digest "$runtime_root/$commit")" "$(tree_digest "$runtime_root/$current")"
    cleanup_kind=none
    printf '%s\n' 'PHASE_C_UPDATE=PASS' "CURRENT_COMMIT=$commit" "ROLLBACK_COMMIT=$current"
    remove_frozen_candidate "$candidate"; trap - EXIT; return
  fi
  [[ $mode == install ]] || fail no_active_install_for_update
  [[ ! -e $runtime_root && ! -L $runtime_root && ! -e $wrapper && ! -L $wrapper && \
     ! -e $dropin && ! -L $dropin && ! -e $hook && ! -L $hook && ! -e $state_dir && ! -L $state_dir ]] ||
    fail managed_path_collision
  service_before=$(service_state)
  [[ $service_before == active || $service_before == inactive ]] || fail unsupported_service_state
  cleanup_kind=fresh
  cleanup_runtime=$runtime_root/$commit
  cleanup_service_before=$service_before
  host_action systemctl stop fprintd.service
  install -d -m 0755 "$state_dir" "$(dirname "$wrapper")" "$(dirname "$dropin")" "$(dirname "$hook")"
  install_policy "$candidate"
  cleanup_policy=true
  if [[ ${GOODIX_MANAGED_TEST_FAIL_AFTER_POLICY:-false} == true ]]; then fail injected_failure_after_policy; fi
  install -m 0755 "$candidate/fprintd-wrapper" "$wrapper"
  install -m 0755 "$candidate/50-goodix-fprint-account-delete" "$hook"
  install -m 0644 "$candidate/99-goodix-27c6-5125-managed.conf" "$dropin"
  host_action restorecon -F "$hook"
  install_runtime_tree "$candidate" "$commit"
  ln -s "$commit" "$current_link"
  write_state "$commit" NONE "$caller" "$service_before" "$(tree_digest "$runtime_root/$commit")" NONE
  host_action systemctl daemon-reload
  if material_ready && [[ $service_before == active ]]; then host_action systemctl start fprintd.service; fi
  cleanup_kind=none
  printf '%s\n' 'PHASE_C_INSTALL=PASS' "CURRENT_COMMIT=$commit" \
    "PROTECTED_MATERIAL_READY=$(material_ready && echo true || echo false)" \
    'PAM_CONFIGURATION_CHANGED=false'
  remove_frozen_candidate "$candidate"
  trap - EXIT
}

root_rollback() {
  local caller=$1 current previous current_digest previous_digest
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  verify_active
  [[ $(state_value INSTALLER) == "$caller" ]] || fail installer_mismatch
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
  [[ $previous != NONE ]] || fail no_update_to_rollback
  current_digest=$(state_value CURRENT_TREE_SHA256); previous_digest=$(state_value PREVIOUS_TREE_SHA256)
  host_action systemctl stop fprintd.service
  ln -s "$previous" "$runtime_root/current.next"
  mv -Tf -- "$runtime_root/current.next" "$current_link"
  write_state "$previous" "$current" "$caller" "$(state_value SERVICE_BEFORE)" "$previous_digest" "$current_digest"
  host_action systemctl daemon-reload
  if material_ready && [[ $(state_value SERVICE_BEFORE) == active ]]; then host_action systemctl start fprintd.service; fi
  printf '%s\n' 'PHASE_C_ROLLBACK=PASS' "CURRENT_COMMIT=$previous" "ROLLBACK_COMMIT=$current"
}

root_uninstall() {
  local caller=$1 current previous service_before
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  verify_active
  [[ $(state_value INSTALLER) == "$caller" ]] || fail installer_mismatch
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT); service_before=$(state_value SERVICE_BEFORE)
  host_action systemctl stop fprintd.service
  remove_policy
  rm -f -- "$current_link" "$wrapper" "$dropin" "$hook"
  find "$runtime_root/$current" -xdev -depth -delete
  if [[ $previous != NONE ]]; then find "$runtime_root/$previous" -xdev -depth -delete; fi
  rmdir -- "$runtime_root" 2>/dev/null || true
  rm -f -- "$state"
  rmdir -- "$state_dir" 2>/dev/null || true
  host_action systemctl daemon-reload
  [[ $service_before != active ]] || host_action systemctl start fprintd.service
  printf '%s\n' 'PHASE_C_UNINSTALL=PASS' 'PROTECTED_MATERIAL_PRESERVED=true' 'FEDORA_FPRINTD_BASELINE=RESTORED'
}

root_import_materials() {
  local caller=$1 source=$2 name staging
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  [[ $source == /* && -d $source && ! -L $source ]] || fail material_source_invalid
  [[ -n $test_root || $(stat -c %U "$source") == "$caller" ]] || fail material_source_owner_invalid
  for name in "${required_material[@]}"; do
    [[ -f $source/$name && ! -L $source/$name ]] || fail "material_source_${name}_invalid"
  done
  [[ ! -e $material && ! -L $material ]] || fail material_destination_collision
  staging=$material.pending.$$
  install -d -m 0700 "$staging"
  for name in "${required_material[@]}"; do install -m 0600 "$source/$name" "$staging/$name"; done
  if [[ -z $test_root ]]; then chown -R root:root "$staging"; fi
  mv -- "$staging" "$material"
  printf '%s\n' 'PHASE_C_MATERIAL_IMPORT=PASS' 'MATERIAL_CONTENT_LOGGED=false' 'SOURCE_FILES_PRESERVED=true'
}

case ${1:-} in
  --root-install|--root-update)
    [[ $# -eq 3 ]] || fail root_install_usage
    root_install_or_update "${1#--root-}" "$2" "$3"
    ;;
  --root-rollback|--root-uninstall)
    [[ $# -eq 2 ]] || fail root_remove_usage
    if [[ $1 == --root-rollback ]]; then root_rollback "$2"; else root_uninstall "$2"; fi
    ;;
  --root-import-materials)
    [[ $# -eq 3 ]] || fail root_import_usage
    root_import_materials "$2" "$3"
    ;;
  --status)
    [[ $# -eq 1 ]] || fail status_usage
    verify_active
    printf '%s\n' 'PHASE_C_STATUS=ACTIVE' "CURRENT_COMMIT=$(state_value CURRENT_COMMIT)" \
      "PREVIOUS_COMMIT=$(state_value PREVIOUS_COMMIT)" \
      "PROTECTED_MATERIAL_READY=$(material_ready && echo true || echo false)" \
      'RPM_OFFICIAL_DISTRIBUTION=false'
    ;;
  *) fail internal_usage ;;
esac
