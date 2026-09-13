#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
repo=$(git -C "$here" rev-parse --show-toplevel 2>/dev/null || true)
private=/run/goodix-d293-04
public=/run/goodix-d293-04-public
mountpoint_path=$public/repo
capture_root=/var/tmp/goodix-d293-04-captures
dropin=/run/systemd/system/fprintd.service.d/99-goodix-d293-04.conf
unit=goodix-d293-04-supervisor.service
test_user=d293-phase-b-test
fail() { printf 'D293_04_ROOT_HELPER=FAIL reason=%s\n' "$1" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail root_required

state_value() {
  local key=$1 value
  value=$(sed -n "s/^${key}=//p" "$private/state.env")
  [[ $(sed -n "s/^${key}=//p" "$private/state.env" | wc -l) -eq 1 && -n $value ]] || return 1
  printf '%s\n' "$value"
}
principal_digest() {
  local user=$1 path=/var/lib/fprint/$1
  if [[ ! -e $path ]]; then printf 'ABSENT\n'; return; fi
  [[ -d $path && ! -L $path ]] || return 1
  {
    find "$path" -xdev -printf 'META|%P|%y|%m|%U|%G|%s|%T@\n' | LC_ALL=C sort
    while IFS= read -r -d '' file; do
      printf 'CONTENT|%s|' "${file#"$path"/}"
      sha256sum "$file" | awk '{print $1}'
    done < <(find "$path" -xdev -type f -print0 | LC_ALL=C sort -z)
  } | sha256sum | awk '{print $1}'
}
remove_tree() {
  local path=$1 expected=$2
  [[ $path == "$expected" && -d $path && ! -L $path ]] || return 1
  find "$path" -xdev -depth -delete
}
write_public() {
  local phase=$1 rollback=$2
  mkdir -p "$public"
  chmod 0755 "$public"
  cat >"$public/public.env" <<EOF
D293_04_PHASE=$phase
D293_04_PRODUCTION_HEAD=$(state_value PRODUCTION_HEAD)
D293_04_LIBRARY_SHA256=$(state_value LIBRARY_SHA256)
D293_04_RUNTIME_ROLLBACK=$rollback
D293_04_TEST_USER=$test_user
EOF
  chmod 0444 "$public/public.env"
}
audit_d285() {
  local phase=$1 original=$2 output
  output=$("$repo/operator_kit/d286-01-reboot-survival/run-d286-01.sh" \
    --root-audit "$phase" --user "$original") || return 1
  grep -Fx D286_01_STATE_COHERENCE=PASS_ROOT_ONLY <<<"$output" >/dev/null &&
    grep -Fx D286_01_RUNTIME_INTEGRITY=PASS <<<"$output" >/dev/null &&
    grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES <<<"$output" >/dev/null
}
rollback_runtime() {
  local original before now service_before result=PASS d286=PASS storage=PASS
  [[ -f $private/state.env && ! -L $private/state.env ]] || return 0
  original=$(state_value ORIGINAL_USER); before=$(state_value ORIGINAL_PRINCIPAL_DIGEST)
  service_before=$(state_value SERVICE_BEFORE)
  systemctl stop fprintd.service >/dev/null 2>&1 || true
  if [[ -f $dropin && ! -L $dropin ]]; then rm -f -- "$dropin"; fi
  if [[ -f $private/wrapper && ! -L $private/wrapper ]]; then rm -f -- "$private/wrapper"; fi
  if [[ -d $private/runtime && ! -L $private/runtime ]]; then remove_tree "$private/runtime" "$private/runtime" || result=FAIL; fi
  systemctl daemon-reload || result=FAIL
  case $service_before in active) systemctl start fprintd.service || result=FAIL ;; inactive) systemctl stop fprintd.service || result=FAIL ;; *) result=FAIL ;; esac
  now=$(principal_digest "$original") || result=FAIL
  [[ $now == "$before" ]] || result=FAIL
  if [[ -d /var/lib/fprint/$test_user ]] && find "/var/lib/fprint/$test_user" -type f -print -quit | grep -q .; then
    storage=REMAINS; result=FAIL
  fi
  audit_d285 D293_04_POST_ROLLBACK "$original" || { d286=FAIL; result=FAIL; }
  cat >"$private/rollback.env" <<EOF
D293_04_RUNTIME_ROLLBACK=$result
D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=$([[ $now == "$before" ]] && echo true || echo false)
D293_04_TEST_STORAGE=$storage
D293_04_D285_D286_POST_ROLLBACK=$d286
EOF
  chmod 0444 "$private/rollback.env"
  write_public RUNTIME_ROLLED_BACK "$result"
  cp "$private/rollback.env" "$public/rollback.env"
  chmod 0444 "$public/rollback.env"
  [[ $result == PASS ]]
}
supervisor_signal() {
  trap - EXIT INT TERM
  rollback_runtime || true
  exit 143
}
supervise() {
  trap 'rollback_runtime || true' EXIT
  trap supervisor_signal INT TERM
  local deadline=$((SECONDS + 900)) uid gid original original_uid
  repo=$(state_value REPO_ROOT)
  original=$(state_value ORIGINAL_USER)
  original_uid=$(id -u "$original")
  while (( SECONDS < deadline )); do
    if getent passwd "$test_user" >/dev/null; then break; fi
    sleep 1
  done
  getent passwd "$test_user" >/dev/null || fail test_account_not_created
  uid=$(id -u "$test_user")
  gid=$(id -g "$test_user")
  [[ $uid -ge 1000 && $(getent passwd "$test_user" | cut -d: -f6) == /home/$test_user ]] || fail test_account_invalid
  deadline=$((SECONDS + 300))
  while pgrep -u "$original_uid" -x systemsettings >/dev/null && (( SECONDS < deadline )); do sleep 1; done
  ! pgrep -u "$original_uid" -x systemsettings >/dev/null || fail original_kcm_still_running
  systemctl stop fprintd.service >/dev/null 2>&1 || true
  ! systemctl is-active --quiet fprintd.service || fail fprintd_not_quiescent_before_ready
  [[ ! -e $capture_root && ! -L $capture_root ]] || fail capture_root_collision
  install -d -m 0700 -o "$uid" -g "$gid" "$capture_root"
  mkdir -p "$public/control" "$mountpoint_path"
  chown "$uid:$gid" "$public/control"; chmod 0700 "$public/control"
  chmod 0755 "$mountpoint_path"
  mount --bind "$(state_value REPO_ROOT)" "$mountpoint_path"
  mount -o remount,bind,ro,nodev,nosuid "$mountpoint_path"
  write_public READY_FOR_NEW_USER RUNNING
  deadline=$((SECONDS + 7200))
  while (( SECONDS < deadline )); do
    [[ ! -e $public/control/release ]] || { rollback_runtime; trap - EXIT INT TERM; exit 0; }
    sleep 1
  done
  fail supervisor_timeout
}
deploy() {
  [[ $# -eq 3 ]] || fail deploy_arguments
  local candidate=$1 head=$2 original=$3 caller=${PKEXEC_UID:-} lib_sha
  [[ $head =~ ^[0-9a-f]{40}$ && $original =~ ^[a-z_][a-z0-9_-]*$ ]] || fail deploy_identity
  [[ $caller =~ ^[1-9][0-9]*$ && $(stat -c %u "$candidate") == "$caller" ]] || fail candidate_owner
  [[ $(id -u "$original") == "$caller" ]] || fail original_user_caller_mismatch
  [[ -d $candidate && ! -L $candidate && -f $candidate/deploy.sha256 && ! -L $candidate/deploy.sha256 ]] || fail candidate_type
  [[ ! -e $private && ! -e $public && ! -e $dropin &&
     ! -e $capture_root && ! -L $capture_root ]] ||
    fail deployment_collision
  getent passwd "$test_user" >/dev/null && fail test_account_exists_before_deploy
  repo=$(git -C "$here" rev-parse --show-toplevel)
  [[ $(git -C "$repo" rev-parse HEAD) == "$head" ]] || fail head_mismatch
  audit_d285 D293_04_PRE_DEPLOY "$original" || fail d285_d286_preflight
  local service_before=inactive
  systemctl is-active --quiet fprintd.service && service_before=active
  mkdir -m 0700 "$private"; mkdir -p "$(dirname "$dropin")" "$private/runtime"
  lib_sha=$(sha256sum "$candidate/libfprint-2.so.2.0.0" | awk '{print $1}')
  cat >"$private/state.env" <<EOF
PRODUCTION_HEAD=$head
LIBRARY_SHA256=$lib_sha
ORIGINAL_USER=$original
ORIGINAL_PRINCIPAL_DIGEST=$(principal_digest "$original")
SERVICE_BEFORE=$service_before
REPO_ROOT=$repo
EOF
  chmod 0600 "$private/state.env"
  deploy_failure_cleanup() {
    systemctl stop "$unit" >/dev/null 2>&1 || true
    rollback_runtime || true
    if [[ -d $public && ! -L $public ]]; then remove_tree "$public" "$public" || true; fi
    if [[ -d $private && ! -L $private ]]; then remove_tree "$private" "$private" || true; fi
  }
  trap deploy_failure_cleanup EXIT
  trap 'deploy_failure_cleanup; exit 1' INT TERM
  local name
  for name in libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
      libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413; do
    [[ -f $candidate/$name && ! -L $candidate/$name ]] || fail "candidate_$name"
    install -m 0644 "$candidate/$name" "$private/runtime/$name"
  done
  install -m 0600 "$candidate/deploy.sha256" "$private/runtime/artifacts.sha256"
  (cd "$private/runtime" && sha256sum -c artifacts.sha256 >/dev/null) || fail candidate_digest
  ln -s libfprint-2.so.2.0.0 "$private/runtime/libfprint-2.so.2"
  [[ $(sha256sum "$private/runtime/libfprint-2.so.2.0.0" | awk '{print $1}') == "$lib_sha" ]] || fail copied_library_digest
  cat >"$private/wrapper" <<EOF
#!/usr/bin/env bash
set -euo pipefail
runtime=/run/goodix-d293-04/runtime
(cd "\$runtime" && sha256sum -c artifacts.sha256 >/dev/null)
echo 'D293_04_RUNTIME_AUDIT head=$head library_sha=$lib_sha manifest=pass'
exec env LD_LIBRARY_PATH="\$runtime" FP_DRIVERS_ALLOWLIST=goodix_27c6_5125 /usr/libexec/fprintd
EOF
  chmod 0755 "$private/wrapper"
  cat >"$dropin" <<EOF
[Service]
ExecStart=
ExecStart=/run/goodix-d293-04/wrapper
EOF
  chmod 0644 "$dropin"
  install -m 0700 "$here/root-helper.sh" "$private/supervisor.sh"
  systemctl daemon-reload
  systemctl stop fprintd.service >/dev/null 2>&1 || true
  systemd-run --unit="${unit%.service}" --collect --property=Type=exec \
    --property=RuntimeMaxSec=7500 "$private/supervisor.sh" --supervise >/dev/null
  systemctl is-active --quiet "$unit" || fail supervisor_not_active
  trap - EXIT INT TERM
  echo D293_04_ROOT_DEPLOY=PASS
}
recover() {
  if systemctl is-active --quiet "$unit"; then
    systemctl kill --signal=TERM "$unit" || true
    for _ in $(seq 1 100); do [[ ! -f $private/wrapper ]] && break; sleep 0.1; done
  fi
  rollback_runtime || true
  local original= original_gid= result=PASS uid capture_retained=ABSENT caller=${PKEXEC_UID:-}
  if [[ -f $private/state.env ]]; then
    original=$(state_value ORIGINAL_USER)
  elif [[ $caller =~ ^[1-9][0-9]*$ ]]; then
    original=$(getent passwd "$caller" | cut -d: -f1)
    [[ $original =~ ^[a-z_][a-z0-9_-]*$ && $original != "$test_user" ]] ||
      fail recovery_caller_invalid
  else
    fail recovery_caller_missing
  fi
  original_gid=$(id -g "$original") || fail recovery_original_group_missing
  if mountpoint -q "$mountpoint_path"; then umount "$mountpoint_path" || result=FAIL; fi
  if getent passwd "$test_user" >/dev/null; then
    uid=$(id -u "$test_user")
    ! pgrep -u "$uid" >/dev/null || fail test_user_still_logged_in
    [[ ! -d /var/lib/fprint/$test_user ]] || ! find "/var/lib/fprint/$test_user" -type f -print -quit | grep -q . || fail test_storage_remains_use_kcm
    [[ $(getent passwd "$test_user" | cut -d: -f6) == /home/$test_user ]] || fail test_home_unexpected
    if [[ -e $capture_root || -L $capture_root ]]; then
      [[ -d $capture_root && ! -L $capture_root ]] || fail capture_root_invalid
      [[ -z $(find "$capture_root" -xdev ! -type d ! -type f -print -quit) ]] ||
        fail capture_special_file
      [[ -z $(find "$capture_root" -xdev ! -user "$test_user" -print -quit) ]] ||
        fail capture_owner_drift
      chown -R "$original:$original_gid" "$capture_root"
      capture_retained=$capture_root
    fi
    userdel -r "$test_user"
  elif [[ -e $capture_root || -L $capture_root ]]; then
    fail capture_without_test_account
  fi
  if [[ -n $original ]]; then audit_d285 D293_04_FINAL_RECOVERY "$original" || result=FAIL; fi
  if [[ -d $public && ! -L $public ]]; then remove_tree "$public" "$public" || result=FAIL; fi
  if [[ -d $private && ! -L $private ]]; then remove_tree "$private" "$private" || result=FAIL; fi
  systemctl reset-failed "$unit" >/dev/null 2>&1 || true
  echo "D293_04_CAPTURE_RETAINED=$capture_retained"
  echo "D293_04_FINAL_RECOVERY=$result"
  [[ $result == PASS ]]
}

case ${1:-} in
  --deploy) shift; deploy "$@" ;;
  --supervise) [[ $# -eq 1 ]]; supervise ;;
  --recover) [[ $# -eq 1 ]]; recover ;;
  *) fail arguments ;;
esac
