#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -eEuo pipefail
umask 077

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
repo=$(git -C "$here" rev-parse --show-toplevel 2>/dev/null || true)
private=/run/goodix-d293-04
public=/run/goodix-d293-04-public
mountpoint_path=$public/repo
capture_base=/var/tmp/goodix-d293-04-captures
dropin=/run/systemd/system/fprintd.service.d/99-goodix-d293-04.conf
unit=goodix-d293-04-supervisor.service
test_user=d293-phase-b-test
fail() { printf 'D293_04_ROOT_HELPER=FAIL reason=%s\n' "$1" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail root_required

one_from_file() {
  local key=$1 file=$2 values
  [[ -f $file && ! -L $file ]] || return 1
  values=$(sed -n "s/^${key}=//p" "$file")
  [[ $(printf '%s\n' "$values" | sed '/^$/d' | wc -l) -eq 1 && -n $values ]] ||
    return 1
  printf '%s\n' "$values"
}

state_value() { one_from_file "$1" "$private/state.env"; }

atomic_from_stdin() {
  local destination=$1 mode=$2 directory temporary
  directory=$(dirname -- "$destination")
  [[ -d $directory && ! -L $directory ]] || return 1
  temporary=$(mktemp "$directory/.d293-04.XXXXXX") || return 1
  cat >"$temporary" || { rm -f -- "$temporary"; return 1; }
  chmod "$mode" "$temporary" || { rm -f -- "$temporary"; return 1; }
  mv -f -- "$temporary" "$destination"
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
  ! mountpoint -q "$path" || return 1
  find "$path" -xdev -depth -delete
}

write_public() {
  local phase=$1 rollback=$2
  local run_id capture_root
  run_id=$(state_value RUN_ID)
  capture_root=$(state_value CAPTURE_ROOT)
  install -d -m 0755 -o root -g root "$public"
  {
    printf 'D293_04_PHASE=%s\n' "$phase"
    printf 'D293_04_PRODUCTION_HEAD=%s\n' "$(state_value PRODUCTION_HEAD)"
    printf 'D293_04_LIBRARY_SHA256=%s\n' "$(state_value LIBRARY_SHA256)"
    printf 'D293_04_RUNTIME_ROLLBACK=%s\n' "$rollback"
    printf 'D293_04_TEST_USER=%s\n' "$test_user"
    printf 'D293_04_RUN_ID=%s\n' "$run_id"
    printf 'D293_04_CAPTURE_ROOT=%s\n' "$capture_root"
    printf 'D293_04_SERVICE_OVERRIDE_VERIFIED=true\n'
    printf 'D293_04_DAEMON_QUIESCENT_BEFORE_READY=true\n'
    printf 'D293_04_PRIVATE_MATERIAL_INACCESSIBLE=true\n'
    printf 'D293_04_PUBLIC_PATH_ACCESS=PASS\n'
  } | atomic_from_stdin "$public/public.env" 0444
}

write_control_ack() {
  local request=$1
  {
    printf 'D293_04_CONTROL=%s\n' "$request"
    printf 'D293_04_CONTROL_RESULT=PASS\n'
  } | atomic_from_stdin "$public/results/$request.env" 0444
}

audit_d285() {
  local phase=$1 original=$2 output
  output=$("$repo/operator_kit/d286-01-reboot-survival/run-d286-01.sh" \
    --root-audit "$phase" --user "$original") || return 1
  grep -Fx D286_01_STATE_COHERENCE=PASS_ROOT_ONLY <<<"$output" >/dev/null &&
    grep -Fx D286_01_RUNTIME_INTEGRITY=PASS <<<"$output" >/dev/null &&
    grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES <<<"$output" >/dev/null
}

journal_cursor() {
  local output cursor
  output=$(LC_ALL=C journalctl -b -n 0 --show-cursor --no-pager) || return 1
  cursor=$(sed -n 's/^-- cursor: //p' <<<"$output")
  [[ $(printf '%s\n' "$cursor" | sed '/^$/d' | wc -l) -eq 1 && -n $cursor ]] ||
    return 1
  printf '%s\n' "$cursor"
}

collect_epoch_journal() {
  local step=$1 cursor=$2 raw normalized destination
  [[ $step == enroll || $step =~ ^verify-[123]$ ]] || return 1
  raw=$(mktemp "$private/.journal-raw.XXXXXX") || return 1
  normalized=$(mktemp "$private/.journal-normalized.XXXXXX") || {
    rm -f -- "$raw"; return 1;
  }
  if ! LC_ALL=C journalctl -b -u fprintd.service --after-cursor "$cursor" \
      --no-pager -o cat --grep='GOODIX_PRODUCTION_EPOCH_AUDIT ' >"$raw"; then
    rm -f -- "$raw" "$normalized"
    return 1
  fi
  if ! "$private/normalize-journal.sh" <"$raw" >"$normalized"; then
    rm -f -- "$raw" "$normalized"
    return 1
  fi
  rm -f -- "$raw"
  destination=$public/results/$step-journal.log
  atomic_from_stdin "$destination" 0444 <"$normalized"
  rm -f -- "$normalized"
}

rollback_runtime() {
  local original before now service_before result=PASS d286=PASS storage=PASS prior
  [[ -f $private/state.env && ! -L $private/state.env ]] || {
    if [[ -f $public/rollback.env && ! -L $public/rollback.env ]]; then
      prior=$(one_from_file D293_04_RUNTIME_ROLLBACK "$public/rollback.env") || return 1
      [[ $prior == PASS ]]
      return
    fi
    return 0
  }
  exec 9>"$private/rollback.lock"
  flock 9
  if [[ -f $private/rollback.complete && ! -L $private/rollback.complete ]]; then
    prior=$(one_from_file D293_04_RUNTIME_ROLLBACK "$private/rollback.complete") || return 1
    write_public RUNTIME_ROLLED_BACK "$prior" || return 1
    cp -- "$private/rollback.complete" "$public/rollback.env" || return 1
    chmod 0444 "$public/rollback.env"
    [[ $prior == PASS ]]
    return
  fi
  original=$(state_value ORIGINAL_USER)
  before=$(state_value ORIGINAL_PRINCIPAL_DIGEST)
  service_before=$(state_value SERVICE_BEFORE)
  systemctl stop fprintd.service >/dev/null 2>&1 || result=FAIL
  ! systemctl is-active --quiet fprintd.service || result=FAIL
  if [[ -f $dropin && ! -L $dropin ]]; then rm -f -- "$dropin" || result=FAIL; fi
  [[ ! -e $dropin && ! -L $dropin ]] || result=FAIL
  if [[ -f $private/wrapper && ! -L $private/wrapper ]]; then rm -f -- "$private/wrapper" || result=FAIL; fi
  if [[ -d $private/runtime && ! -L $private/runtime ]]; then
    remove_tree "$private/runtime" "$private/runtime" || result=FAIL
  fi
  systemctl daemon-reload || result=FAIL
  case $service_before in
    active) systemctl start fprintd.service || result=FAIL ;;
    inactive) systemctl stop fprintd.service || result=FAIL ;;
    *) result=FAIL ;;
  esac
  now=$(principal_digest "$original") || { now=ERROR; result=FAIL; }
  [[ $now == "$before" ]] || result=FAIL
  if [[ -d /var/lib/fprint/$test_user ]] &&
     find "/var/lib/fprint/$test_user" -type f -print -quit | grep -q .; then
    storage=REMAINS
    result=FAIL
  fi
  audit_d285 D293_04_POST_ROLLBACK "$original" || { d286=FAIL; result=FAIL; }
  {
    printf 'D293_04_RUNTIME_ROLLBACK=%s\n' "$result"
    if [[ $now == "$before" ]]; then
      printf 'D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=true\n'
    else
      printf 'D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=false\n'
    fi
    printf 'D293_04_TEST_STORAGE=%s\n' "$storage"
    printf 'D293_04_D285_D286_POST_ROLLBACK=%s\n' "$d286"
  } | atomic_from_stdin "$private/rollback.complete" 0444 || return 1
  write_public RUNTIME_ROLLED_BACK "$result" || return 1
  cp -- "$private/rollback.complete" "$public/rollback.env" || return 1
  chmod 0444 "$public/rollback.env"
  [[ $result == PASS ]]
}

supervisor_exit() {
  local rc=$?
  trap - EXIT INT TERM
  rollback_runtime || rc=1
  exit "$rc"
}

supervisor_signal() {
  trap - INT TERM
  exit 143
}

supervise() {
  trap supervisor_exit EXIT
  trap supervisor_signal INT TERM
  local deadline=$((SECONDS + 900)) uid gid original original_uid run_id run_root capture_root
  local expected=arm-enroll armed_cursor= request= next=
  repo=$(state_value REPO_ROOT)
  original=$(state_value ORIGINAL_USER)
  original_uid=$(id -u "$original")
  run_id=$(state_value RUN_ID)
  run_root=$capture_base/$run_id
  capture_root=$(state_value CAPTURE_ROOT)
  while (( SECONDS < deadline )); do
    getent passwd "$test_user" >/dev/null && break
    sleep 1
  done
  getent passwd "$test_user" >/dev/null || fail test_account_not_created
  uid=$(id -u "$test_user")
  gid=$(id -g "$test_user")
  [[ $uid -ge 1000 && $(getent passwd "$test_user" | cut -d: -f6) == /home/$test_user ]] ||
    fail test_account_invalid
  deadline=$((SECONDS + 300))
  while pgrep -u "$original_uid" -x systemsettings >/dev/null && (( SECONDS < deadline )); do sleep 1; done
  ! pgrep -u "$original_uid" -x systemsettings >/dev/null || fail original_kcm_still_running
  systemctl stop fprintd.service >/dev/null 2>&1 || fail fprintd_stop_before_ready
  ! systemctl is-active --quiet fprintd.service || fail fprintd_not_quiescent_before_ready
  [[ ! -e $run_root && ! -L $run_root ]] || fail run_capture_collision
  install -d -m 0711 -o root -g root "$capture_base" "$run_root"
  install -d -m 0700 -o "$uid" -g "$gid" "$capture_root"
  {
    printf 'D293_04_RUN_ID=%s\n' "$run_id"
    printf 'D293_04_TEST_USER=%s\n' "$test_user"
    printf 'D293_04_TEST_UID=%s\n' "$uid"
    printf 'D293_04_TEST_GID=%s\n' "$gid"
    printf 'D293_04_TEST_HOME=/home/%s\n' "$test_user"
    printf 'D293_04_ORIGINAL_USER=%s\n' "$original"
    printf 'D293_04_ORIGINAL_UID=%s\n' "$original_uid"
    printf 'D293_04_ORIGINAL_GID=%s\n' "$(id -g "$original")"
    printf 'D293_04_PRODUCTION_HEAD=%s\n' "$(state_value PRODUCTION_HEAD)"
    printf 'D293_04_ORIGINAL_PRINCIPAL_DIGEST=%s\n' "$(state_value ORIGINAL_PRINCIPAL_DIGEST)"
  } | atomic_from_stdin "$run_root/run.env" 0400
  install -d -m 0755 -o root -g root "$public" "$public/results" "$mountpoint_path"
  install -d -m 0700 -o "$uid" -g "$gid" "$public/control"
  mount --bind "$(state_value REPO_ROOT)" "$mountpoint_path"
  mount -o remount,bind,ro,nodev,nosuid "$mountpoint_path"
  runuser -u "$test_user" -- test -r "$mountpoint_path/.git/HEAD" || fail public_git_metadata_unreadable
  runuser -u "$test_user" -- test -x "$mountpoint_path/operator_kit/live_probe/run.sh" || fail public_launcher_unreadable
  runuser -u "$test_user" -- test ! -r "$private/state.env" || fail private_state_readable_by_test_user
  runuser -u "$test_user" -- test ! -r "$private/runtime/artifacts.sha256" || fail private_runtime_readable_by_test_user
  write_public READY_FOR_NEW_USER RUNNING
  deadline=$((SECONDS + 7200))
  while (( SECONDS < deadline )); do
    if [[ -e $public/control/release ]]; then
      [[ -f $public/control/release && ! -L $public/control/release ]] || fail release_control_invalid
      rm -f -- "$public/control/release"
      trap - EXIT INT TERM
      rollback_runtime
      exit 0
    fi
    if [[ -n $(find "$public/control" -mindepth 1 -maxdepth 1 ! -type f -print -quit) ]]; then
      fail control_special_entry
    fi
    mapfile -t requests < <(find "$public/control" -mindepth 1 -maxdepth 1 -type f \
      ! -name release -printf '%f\n' | LC_ALL=C sort)
    if (( ${#requests[@]} > 1 )); then fail concurrent_control_requests; fi
    if (( ${#requests[@]} == 1 )); then
      request=${requests[0]}
      if [[ $request == complete-verify && $expected =~ ^(arm-verify-[23]|complete-verify)$ ]]; then
        rm -f -- "$public/control/$request"
        write_control_ack "$request"
        expected=complete
      elif [[ $request == "$expected" && $request =~ ^arm-(enroll|verify-[123])$ ]]; then
        armed_cursor=$(journal_cursor) || fail journal_cursor_failed
        rm -f -- "$public/control/$request"
        write_control_ack "$request"
        expected=${request/arm-/finish-}
      elif [[ $request == "$expected" && $request =~ ^finish-(enroll|verify-[123])$ ]]; then
        next=${request#finish-}
        collect_epoch_journal "$next" "$armed_cursor" || fail journal_collection_failed
        rm -f -- "$public/control/$request"
        write_control_ack "$request"
        case $next in
          enroll) expected=arm-verify-1 ;;
          verify-1) expected=arm-verify-2 ;;
          verify-2) expected=arm-verify-3 ;;
          verify-3) expected=complete-verify ;;
        esac
      else
        fail "unexpected_control_${request}_expected_${expected}"
      fi
    fi
    sleep 0.1
  done
  fail supervisor_timeout
}

deploy() {
  [[ $# -eq 4 ]] || fail deploy_arguments
  local candidate=$1 head=$2 original=$3 run_id=$4 caller=${PKEXEC_UID:-} lib_sha
  local capture_root=$capture_base/$run_id/capture
  [[ $head =~ ^[0-9a-f]{40}$ && $original =~ ^[a-z_][a-z0-9_-]*$ &&
     $run_id =~ ^d293-04-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] || fail deploy_identity
  [[ $caller =~ ^[1-9][0-9]*$ && $(stat -c %u "$candidate") == "$caller" ]] || fail candidate_owner
  [[ $(id -u "$original") == "$caller" ]] || fail original_user_caller_mismatch
  [[ -d $candidate && ! -L $candidate && -f $candidate/deploy.sha256 && ! -L $candidate/deploy.sha256 ]] ||
    fail candidate_type
  [[ ! -e $private && ! -e $public && ! -e $dropin &&
     ! -e $capture_base/$run_id && ! -L $capture_base/$run_id ]] || fail deployment_collision
  getent passwd "$test_user" >/dev/null && fail test_account_exists_before_deploy
  repo=$(git -C "$here" rev-parse --show-toplevel)
  [[ $(git -C "$repo" rev-parse HEAD) == "$head" ]] || fail head_mismatch
  audit_d285 D293_04_PRE_DEPLOY "$original" || fail d285_d286_preflight
  local service_before=inactive
  systemctl is-active --quiet fprintd.service && service_before=active
  mkdir -m 0700 "$private"
  install -d -m 0755 -o root -g root "$(dirname "$dropin")"
  mkdir -m 0700 "$private/runtime"
  lib_sha=$(sha256sum "$candidate/libfprint-2.so.2.0.0" | awk '{print $1}')
  cat >"$private/state.env" <<EOF
PRODUCTION_HEAD=$head
LIBRARY_SHA256=$lib_sha
ORIGINAL_USER=$original
ORIGINAL_PRINCIPAL_DIGEST=$(principal_digest "$original")
SERVICE_BEFORE=$service_before
REPO_ROOT=$repo
RUN_ID=$run_id
CAPTURE_ROOT=$capture_root
EOF
  chmod 0600 "$private/state.env"
  deploy_failure_cleanup() {
    local rollback_rc=0
    systemctl stop "$unit" >/dev/null 2>&1 || true
    rollback_runtime || rollback_rc=$?
    if [[ $rollback_rc -eq 0 ]]; then
      if [[ -d $public && ! -L $public ]] && ! mountpoint -q "$mountpoint_path"; then
        remove_tree "$public" "$public" || true
      fi
      if [[ -d $private && ! -L $private ]]; then remove_tree "$private" "$private" || true; fi
    fi
  }
  trap deploy_failure_cleanup EXIT
  trap 'exit 1' INT TERM
  local name
  for name in libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
      libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413; do
    [[ -f $candidate/$name && ! -L $candidate/$name ]] || fail "candidate_$name"
    install -m 0644 "$candidate/$name" "$private/runtime/$name"
  done
  install -m 0600 "$candidate/deploy.sha256" "$private/runtime/artifacts.sha256"
  (cd "$private/runtime" && sha256sum -c artifacts.sha256 >/dev/null) || fail candidate_digest
  ln -s libfprint-2.so.2.0.0 "$private/runtime/libfprint-2.so.2"
  [[ $(sha256sum "$private/runtime/libfprint-2.so.2.0.0" | awk '{print $1}') == "$lib_sha" ]] ||
    fail copied_library_digest
  install -d -m 0755 -o root -g root "$public" "$public/results"
  cat >"$private/wrapper" <<EOF
#!/usr/bin/env bash
set -euo pipefail
runtime=/run/goodix-d293-04/runtime
results=/run/goodix-d293-04-public/results
(cd "\$runtime" && sha256sum -c artifacts.sha256 >/dev/null)
temporary=\$(mktemp "\$results/.runtime-audit.XXXXXX")
printf '%s\n' 'D293_04_RUNTIME_AUDIT head=$head library_sha=$lib_sha manifest=pass run_id=$run_id' >"\$temporary"
chmod 0444 "\$temporary"
mv -f -- "\$temporary" "\$results/runtime-audit.env"
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
  install -m 0700 "$here/normalize-journal.sh" "$private/normalize-journal.sh"
  systemctl daemon-reload
  systemctl cat fprintd.service | grep -Fx 'ExecStart=/run/goodix-d293-04/wrapper' >/dev/null ||
    fail transient_dropin_not_loaded
  systemctl stop fprintd.service >/dev/null 2>&1 || true
  systemd-run --unit="${unit%.service}" --collect --property=Type=exec \
    --property=RuntimeMaxSec=7500 "$private/supervisor.sh" --supervise >/dev/null
  systemctl is-active --quiet "$unit" || fail supervisor_not_active
  trap - EXIT INT TERM
  echo D293_04_ROOT_DEPLOY=PASS
}

resolve_incomplete_run() {
  local caller_uid=$1 file uid recovery count=0 selected=
  [[ -d $capture_base && ! -L $capture_base ]] || return 1
  while IFS= read -r -d '' file; do
    [[ $(stat -c %u "$file") -eq 0 && $(stat -c %a "$file") == 400 ]] || continue
    uid=$(one_from_file D293_04_ORIGINAL_UID "$file") || continue
    [[ $uid == "$caller_uid" ]] || continue
    recovery=$(dirname -- "$file")/recovery.env
    if [[ -f $recovery && ! -L $recovery ]] &&
       grep -Fx D293_04_FINAL_RECOVERY=PASS "$recovery" >/dev/null; then
      continue
    fi
    selected=$file
    count=$((count + 1))
  done < <(find "$capture_base" -mindepth 2 -maxdepth 2 -name run.env -type f -print0)
  [[ $count -eq 1 ]] || return "$((count == 0 ? 1 : 2))"
  printf '%s\n' "$selected"
}

recover() {
  local caller=${PKEXEC_UID:-} result=PASS rollback_rc=0 supervisor_rc=0
  local metadata= original original_uid original_gid uid gid run_id run_root capture_root before now
  local removal_intent
  [[ $caller =~ ^[1-9][0-9]*$ ]] || fail recovery_caller_missing
  original=$(getent passwd "$caller" | cut -d: -f1)
  [[ $original =~ ^[a-z_][a-z0-9_-]*$ && $original != "$test_user" ]] || fail recovery_caller_invalid
  original_uid=$(id -u "$original")
  original_gid=$(id -g "$original")

  if systemctl is-active --quiet "$unit"; then
    systemctl kill --signal=TERM "$unit" || supervisor_rc=1
    for _ in $(seq 1 300); do
      ! systemctl is-active --quiet "$unit" && break
      sleep 0.1
    done
    ! systemctl is-active --quiet "$unit" || supervisor_rc=1
  fi
  [[ $supervisor_rc -eq 0 ]] || result=FAIL
  if [[ $supervisor_rc -eq 0 ]]; then rollback_runtime || rollback_rc=$?; else rollback_rc=1; fi
  [[ $rollback_rc -eq 0 ]] || result=FAIL

  set +e
  metadata=$(resolve_incomplete_run "$caller")
  resolve_rc=$?
  set -e
  if [[ $resolve_rc -ne 0 ]]; then
    if [[ $resolve_rc -eq 2 ]]; then fail multiple_incomplete_runs; fi
    getent passwd "$test_user" >/dev/null && fail test_account_without_attributed_run
    audit_d285 D293_04_FINAL_RECOVERY_IDEMPOTENT "$original" || result=FAIL
    printf 'D293_04_CAPTURE_RETAINED=%s\n' "$capture_base"
    printf 'D293_04_FINAL_RECOVERY=%s\n' "$result"
    [[ $result == PASS ]]
    return
  fi

  run_root=$(dirname -- "$metadata")
  run_id=$(one_from_file D293_04_RUN_ID "$metadata") || fail recovery_run_id_missing
  [[ $run_root == "$capture_base/$run_id" && ! -L $run_root ]] || fail recovery_run_path_invalid
  [[ $(one_from_file D293_04_ORIGINAL_UID "$metadata") == "$caller" &&
     $(one_from_file D293_04_ORIGINAL_USER "$metadata") == "$original" ]] ||
    fail recovery_original_identity_mismatch
  [[ $(one_from_file D293_04_TEST_USER "$metadata") == "$test_user" ]] || fail recovery_test_name_mismatch
  uid=$(one_from_file D293_04_TEST_UID "$metadata") || fail recovery_test_uid_missing
  gid=$(one_from_file D293_04_TEST_GID "$metadata") || fail recovery_test_gid_missing
  capture_root=$run_root/capture
  removal_intent=$run_root/account-removal.intent
  before=$(one_from_file D293_04_ORIGINAL_PRINCIPAL_DIGEST "$metadata") || fail recovery_digest_missing

  if mountpoint -q "$mountpoint_path"; then
    umount "$mountpoint_path" || result=FAIL
  fi
  mountpoint -q "$mountpoint_path" && result=FAIL
  if [[ $result == PASS ]] && getent passwd "$test_user" >/dev/null; then
    [[ $(id -u "$test_user") == "$uid" && $(id -g "$test_user") == "$gid" &&
       $(getent passwd "$test_user" | cut -d: -f6) == /home/$test_user ]] ||
      fail test_account_identity_drift
    ! pgrep -u "$uid" >/dev/null || fail test_user_still_logged_in
    [[ ! -d /var/lib/fprint/$test_user ]] ||
      ! find "/var/lib/fprint/$test_user" -type f -print -quit | grep -q . ||
      fail test_storage_remains_use_kcm
    [[ -d $capture_root && ! -L $capture_root ]] || fail capture_root_invalid
    [[ -z $(find "$capture_root" -xdev ! -type d ! -type f -print -quit) ]] || fail capture_special_file
    if [[ -f $removal_intent && ! -L $removal_intent ]]; then
      [[ $(one_from_file D293_04_RUN_ID "$removal_intent") == "$run_id" &&
         $(one_from_file D293_04_TEST_UID "$removal_intent") == "$uid" ]] ||
        fail account_removal_intent_invalid
      [[ -z $(find "$capture_root" -xdev ! -user "$original" -print -quit) ]] ||
        fail capture_owner_after_intent_drift
    else
      [[ ! -e $removal_intent && ! -L $removal_intent ]] || fail account_removal_intent_invalid
      [[ -z $(find "$capture_root" -xdev ! -user "$test_user" -print -quit) ]] || fail capture_owner_drift
      chown -R "$original:$original_gid" "$capture_root" || result=FAIL
      if [[ $result == PASS ]]; then
        {
          printf 'D293_04_RUN_ID=%s\n' "$run_id"
          printf 'D293_04_TEST_UID=%s\n' "$uid"
          printf 'D293_04_ACCOUNT_REMOVAL=INTENT_RECORDED\n'
        } | atomic_from_stdin "$removal_intent" 0400 || result=FAIL
      fi
    fi
    if [[ $result == PASS ]]; then userdel -r "$test_user" || result=FAIL; fi
  elif [[ $result == PASS ]]; then
    [[ -f $removal_intent && ! -L $removal_intent ]] || fail attributed_test_account_missing
    [[ $(one_from_file D293_04_RUN_ID "$removal_intent") == "$run_id" &&
       $(one_from_file D293_04_TEST_UID "$removal_intent") == "$uid" ]] ||
      fail account_removal_intent_invalid
    [[ -d $capture_root && ! -L $capture_root &&
       -z $(find "$capture_root" -xdev ! -user "$original" -print -quit) ]] ||
      fail retained_capture_invalid_after_account_removal
  fi
  now=$(principal_digest "$original") || { now=ERROR; result=FAIL; }
  [[ $now == "$before" ]] || result=FAIL
  audit_d285 D293_04_FINAL_RECOVERY "$original" || result=FAIL

  if [[ $result == PASS ]]; then
    {
      printf 'D293_04_RUN_ID=%s\n' "$run_id"
      printf 'D293_04_FINAL_RECOVERY=PASS\n'
      printf 'D293_04_CAPTURE_RETAINED=%s\n' "$capture_root"
    } | atomic_from_stdin "$run_root/recovery.env" 0444 || result=FAIL
  fi
  if [[ $result == PASS && -d $public && ! -L $public ]]; then
    ! mountpoint -q "$mountpoint_path" || fail public_mount_still_active
    remove_tree "$public" "$public" || result=FAIL
  fi
  if [[ $result == PASS && -d $private && ! -L $private ]]; then
    remove_tree "$private" "$private" || result=FAIL
  fi
  systemctl reset-failed "$unit" >/dev/null 2>&1 || true
  printf 'D293_04_CAPTURE_RETAINED=%s\n' "$capture_root"
  printf 'D293_04_FINAL_RECOVERY=%s\n' "$result"
  [[ $result == PASS ]]
}

case ${1:-} in
  --deploy) fail deployment_blocked_r7_gui_session_budget ;;
  --supervise) [[ $# -eq 1 ]]; supervise ;;
  --recover) [[ $# -eq 1 ]]; recover ;;
  *) fail arguments ;;
esac
