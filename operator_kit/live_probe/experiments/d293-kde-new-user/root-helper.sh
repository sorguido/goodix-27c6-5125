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
capture_base_owner=0:0
proc_root=/proc
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

validate_capture_base() {
  [[ -d $capture_base && ! -L $capture_base ]] || return 1
  [[ $(stat -c '%u:%g:%a' "$capture_base") == "$capture_base_owner:711" ]] || return 1
  [[ $(readlink -e -- "$capture_base") == "$capture_base" ]]
}

prepare_capture_base() {
  if [[ ! -e $capture_base && ! -L $capture_base ]]; then
    mkdir -m 0711 -- "$capture_base" || true
  fi
  validate_capture_base
}

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

write_runtime_wrapper() {
  local head=$1 lib_sha=$2 run_id=$3 daemon=$4
  [[ $head =~ ^[0-9a-f]{40}$ && $lib_sha =~ ^[0-9a-f]{64}$ &&
     $run_id =~ ^d293-04-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ &&
     $daemon == /* ]] || return 1
  cat >"$private/wrapper" <<EOF
#!/usr/bin/env bash
set -euo pipefail
runtime=$private/runtime
(cd "\$runtime" && sha256sum -c artifacts.sha256 >/dev/null)
printf '%s\n' 'D293_04_RUNTIME_AUDIT head=$head library_sha=$lib_sha manifest=pass run_id=$run_id'
exec env LD_LIBRARY_PATH="\$runtime" FP_DRIVERS_ALLOWLIST=goodix_27c6_5125 "$daemon"
EOF
  chmod 0755 "$private/wrapper"
}

publish_runtime_audit() {
  local cursor=$1 raw filtered expected destination daemon pid pid_after executable candidate
  local -a mapped_libraries=()
  destination=$public/results/runtime-audit.env
  expected="D293_04_RUNTIME_AUDIT head=$(state_value PRODUCTION_HEAD) library_sha=$(state_value LIBRARY_SHA256) manifest=pass run_id=$(state_value RUN_ID)"
  if [[ -f $destination && ! -L $destination ]]; then
    [[ $(grep -Fxc "$expected" "$destination") -eq 1 &&
       $(wc -l <"$destination") -eq 1 ]]
    return
  fi
  [[ ! -e $destination && ! -L $destination ]] || return 1
  raw=$(mktemp "$private/.runtime-journal.XXXXXX") || return 1
  filtered=$(mktemp "$private/.runtime-filtered.XXXXXX") || {
    rm -f -- "$raw"; return 1;
  }
  if ! LC_ALL=C journalctl -b -u fprintd.service --after-cursor "$cursor" \
      --no-pager -o cat >"$raw"; then
    rm -f -- "$raw" "$filtered"
    return 1
  fi
  awk 'index($0, "D293_04_RUNTIME_AUDIT ") { print }' "$raw" >"$filtered"
  rm -f -- "$raw"
  if [[ ! -s $filtered ]]; then
    rm -f -- "$filtered"
    return 3
  fi
  if [[ $(grep -Fxc "$expected" "$filtered") -ne 1 ||
        $(wc -l <"$filtered") -ne 1 ]]; then
    rm -f -- "$filtered"
    return 1
  fi
  if ! systemctl is-active --quiet fprintd.service; then
    rm -f -- "$filtered"
    return 3
  fi
  daemon=$(state_value DAEMON_PATH) || { rm -f -- "$filtered"; return 1; }
  [[ $daemon == /* && $daemon != *$'\n'* ]] || { rm -f -- "$filtered"; return 1; }
  pid=$(systemctl show --property=MainPID --value fprintd.service) || {
    rm -f -- "$filtered"; return 3;
  }
  [[ $pid =~ ^[1-9][0-9]*$ ]] || { rm -f -- "$filtered"; return 3; }
  [[ -d $proc_root/$pid && ! -L $proc_root/$pid ]] || {
    rm -f -- "$filtered"; return 3;
  }
  executable=$(readlink -- "$proc_root/$pid/exe") || {
    rm -f -- "$filtered"; return 3;
  }
  [[ $executable == "$daemon" ]] || { rm -f -- "$filtered"; return 1; }
  [[ -f $proc_root/$pid/maps && ! -L $proc_root/$pid/maps ]] || {
    rm -f -- "$filtered"; return 3;
  }
  candidate=$private/runtime/libfprint-2.so.2.0.0
  [[ -f $candidate && ! -L $candidate &&
     $(sha256sum "$candidate" | awk '{print $1}') == "$(state_value LIBRARY_SHA256)" ]] || {
    rm -f -- "$filtered"; return 1;
  }
  mapfile -t mapped_libraries < <(
    awk '$NF ~ /(^|\/)libfprint-2\.so(\.[0-9]+)*$/ { print $NF }' \
      "$proc_root/$pid/maps" | LC_ALL=C sort -u
  )
  [[ ${#mapped_libraries[@]} -eq 1 && ${mapped_libraries[0]} == "$candidate" ]] || {
    rm -f -- "$filtered"; return 1;
  }
  pid_after=$(systemctl show --property=MainPID --value fprintd.service) || {
    rm -f -- "$filtered"; return 3;
  }
  [[ $pid_after == "$pid" ]] && systemctl is-active --quiet fprintd.service || {
    rm -f -- "$filtered"; return 3;
  }
  atomic_from_stdin "$destination" 0444 <"$filtered"
  local rc=$?
  rm -f -- "$filtered"
  return "$rc"
}

collect_epoch_journal() {
  local step=$1 cursor=$2 raw selected normalized destination
  [[ $step == enroll || $step == delete || $step =~ ^verify-[123]$ ]] || return 1
  raw=$(mktemp "$private/.journal-raw.XXXXXX") || return 1
  selected=$(mktemp "$private/.journal-selected.XXXXXX") || {
    rm -f -- "$raw"; return 1;
  }
  normalized=$(mktemp "$private/.journal-normalized.XXXXXX") || {
    rm -f -- "$raw" "$selected"; return 1;
  }
  if ! LC_ALL=C journalctl -b -u fprintd.service --after-cursor "$cursor" \
      --no-pager -o cat >"$raw"; then
    rm -f -- "$raw" "$selected" "$normalized"
    return 1
  fi
  awk 'index($0, "GOODIX_PRODUCTION_EPOCH_AUDIT ") { print }' "$raw" >"$selected"
  rm -f -- "$raw"
  if [[ $step == delete && ! -s $selected ]]; then
    : >"$normalized"
  elif ! "$private/normalize-journal.sh" <"$selected" >"$normalized"; then
    rm -f -- "$selected" "$normalized"
    return 1
  fi
  rm -f -- "$selected"
  destination=$public/results/$step-journal.log
  atomic_from_stdin "$destination" 0444 <"$normalized"
  local rc=$?
  rm -f -- "$normalized"
  return "$rc"
}

append_rollback_history() {
  local record=$1 run_id run_root history attempt
  run_id=$(state_value RUN_ID) || return 1
  run_root=$capture_base/$run_id
  [[ -d $run_root && ! -L $run_root ]] || return 0
  history=$run_root/rollback-history.log
  [[ ! -e $history || (-f $history && ! -L $history) ]] || return 1
  attempt=1
  [[ ! -f $history ]] ||
    attempt=$(( $(grep -c '^D293_04_ROLLBACK_ATTEMPT=' "$history" || true) + 1 ))
  {
    printf 'D293_04_ROLLBACK_ATTEMPT=%s\n' "$attempt"
    cat "$record"
    printf 'D293_04_ROLLBACK_ATTEMPT_END=%s\n' "$attempt"
  } >>"$history" || return 1
  chmod 0600 "$history"
}

publish_rollback_record() {
  local record=$1 result=$2 record_history=${3:-true}
  [[ $record_history != true ]] || append_rollback_history "$record" || return 1
  atomic_from_stdin "$private/rollback.latest" 0444 <"$record" || return 1
  if [[ $result == PASS ]]; then
    atomic_from_stdin "$private/rollback.complete" 0444 <"$record" || return 1
  fi
  write_public RUNTIME_ROLLED_BACK "$result" || return 1
  cp -- "$private/rollback.latest" "$public/rollback.env" || return 1
  chmod 0444 "$public/rollback.env"
}

rollback_runtime() {
  local original before now service_before result=PASS d286=PASS storage=PASS prior
  local runtime=PASS cleanup_required=false integrity=false latest legacy_imported
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
    if [[ $prior == PASS ]]; then
      write_public RUNTIME_ROLLED_BACK PASS || return 1
      cp -- "$private/rollback.complete" "$public/rollback.env" || return 1
      chmod 0444 "$public/rollback.env"
      return 0
    fi
    legacy_imported=$private/legacy-rollback-failure-imported
    if [[ ! -e $legacy_imported && ! -L $legacy_imported ]]; then
      append_rollback_history "$private/rollback.complete" || return 1
      printf 'D293_04_LEGACY_ROLLBACK_FAILURE_IMPORTED=true\n' |
        atomic_from_stdin "$legacy_imported" 0400 || return 1
    fi
    if grep -Fx D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=false \
        "$private/rollback.complete" >/dev/null; then
      if [[ ! -f $private/rollback.integrity-failure ]]; then
        {
          cat "$private/rollback.complete"
          printf 'D293_04_INTEGRITY_FAILURE=true\n'
        } | atomic_from_stdin "$private/rollback.integrity-failure" 0400 || return 1
      fi
    fi
  fi
  if [[ -f $private/rollback.integrity-failure && ! -L $private/rollback.integrity-failure ]]; then
    publish_rollback_record "$private/rollback.integrity-failure" FAIL false || return 1
    return 1
  fi

  original=$(state_value ORIGINAL_USER)
  before=$(state_value ORIGINAL_PRINCIPAL_DIGEST)
  service_before=$(state_value SERVICE_BEFORE)
  if [[ -e $private/runtime-restored || -L $private/runtime-restored ]]; then
    [[ -f $private/runtime-restored && ! -L $private/runtime-restored &&
       $(grep -Fxc D293_04_RUNTIME_RESTORED=true "$private/runtime-restored") -eq 1 &&
       $(wc -l <"$private/runtime-restored") -eq 1 &&
       ! -e $dropin && ! -L $dropin &&
       ! -e $private/wrapper && ! -L $private/wrapper &&
       ! -e $private/runtime && ! -L $private/runtime ]] || return 1
    case $service_before in
      active)
        if ! systemctl is-active --quiet fprintd.service; then
          systemctl start fprintd.service || runtime=FAIL
        fi
        systemctl is-active --quiet fprintd.service || runtime=FAIL
        ;;
      inactive)
        if systemctl is-active --quiet fprintd.service; then
          systemctl stop fprintd.service || runtime=FAIL
        fi
        ! systemctl is-active --quiet fprintd.service || runtime=FAIL
        ;;
      *) runtime=FAIL ;;
    esac
  else
    systemctl stop fprintd.service >/dev/null 2>&1 || runtime=FAIL
    ! systemctl is-active --quiet fprintd.service || runtime=FAIL
    if [[ $runtime == PASS ]]; then
      [[ ! -e $dropin || (-f $dropin && ! -L $dropin) ]] || runtime=FAIL
      [[ ! -e $private/wrapper || (-f $private/wrapper && ! -L $private/wrapper) ]] || runtime=FAIL
      [[ ! -e $private/runtime || (-d $private/runtime && ! -L $private/runtime) ]] || runtime=FAIL
    fi
    if [[ $runtime == PASS ]]; then
      [[ ! -f $dropin ]] || rm -f -- "$dropin" || runtime=FAIL
      [[ ! -f $private/wrapper ]] || rm -f -- "$private/wrapper" || runtime=FAIL
      [[ ! -d $private/runtime ]] || remove_tree "$private/runtime" "$private/runtime" || runtime=FAIL
    fi
    if [[ $runtime == PASS ]]; then systemctl daemon-reload || runtime=FAIL; fi
    if [[ $runtime == PASS ]]; then
      case $service_before in
        active)
          systemctl start fprintd.service || runtime=FAIL
          systemctl is-active --quiet fprintd.service || runtime=FAIL
          ;;
        inactive)
          ! systemctl is-active --quiet fprintd.service || runtime=FAIL
          ;;
        *) runtime=FAIL ;;
      esac
    fi
    if [[ $runtime == PASS ]]; then
      printf 'D293_04_RUNTIME_RESTORED=true\n' |
        atomic_from_stdin "$private/runtime-restored" 0400 || runtime=FAIL
    fi
  fi
  [[ $runtime == PASS ]] || result=FAIL

  now=$(principal_digest "$original") || { now=ERROR; integrity=true; result=FAIL; }
  if [[ $now != "$before" ]]; then integrity=true; result=FAIL; fi
  if [[ -d /var/lib/fprint/$test_user ]] &&
     find "/var/lib/fprint/$test_user" -type f -print -quit | grep -q .; then
    storage=REMAINS
    cleanup_required=true
    result=FAIL
  fi
  audit_d285 D293_04_POST_ROLLBACK "$original" || { d286=FAIL; result=FAIL; }
  latest=$(mktemp "$private/.rollback-result.XXXXXX") || return 1
  {
    printf 'D293_04_RUNTIME_ROLLBACK=%s\n' "$result"
    printf 'D293_04_RUNTIME_RESTORED=%s\n' "$([[ $runtime == PASS ]] && echo true || echo false)"
    printf 'D293_04_CLEANUP_REQUIRED=%s\n' "$cleanup_required"
    printf 'D293_04_INTEGRITY_FAILURE=%s\n' "$integrity"
    printf 'D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=%s\n' \
      "$([[ $now == "$before" ]] && echo true || echo false)"
    printf 'D293_04_TEST_STORAGE=%s\n' "$storage"
    printf 'D293_04_D285_D286_POST_ROLLBACK=%s\n' "$d286"
  } >"$latest"
  if [[ $integrity == true ]]; then
    atomic_from_stdin "$private/rollback.integrity-failure" 0400 <"$latest" || {
      rm -f -- "$latest"; return 1;
    }
  fi
  publish_rollback_record "$latest" "$result" || { rm -f -- "$latest"; return 1; }
  rm -f -- "$latest"
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
  local expected=arm-enroll armed_cursor= request= next= runtime_cursor runtime_rc
  repo=$(state_value REPO_ROOT)
  original=$(state_value ORIGINAL_USER)
  original_uid=$(id -u "$original")
  run_id=$(state_value RUN_ID)
  run_root=$capture_base/$run_id
  capture_root=$(state_value CAPTURE_ROOT)
  validate_capture_base || fail capture_base_integrity
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
  install -d -m 0711 -o root -g root "$run_root"
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
  runtime_cursor=$(journal_cursor) || fail runtime_journal_cursor_failed
  write_public READY_FOR_NEW_USER RUNNING
  deadline=$((SECONDS + 7200))
  while (( SECONDS < deadline )); do
    if [[ ! -f $public/results/runtime-audit.env ]]; then
      if publish_runtime_audit "$runtime_cursor"; then
        :
      else
        runtime_rc=$?
        [[ $runtime_rc -eq 3 ]] || fail runtime_audit_publication_failed
      fi
    fi
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
        expected=arm-delete
      elif [[ $request == "$expected" && $request =~ ^arm-(enroll|verify-[123]|delete)$ ]]; then
        armed_cursor=$(journal_cursor) || fail journal_cursor_failed
        rm -f -- "$public/control/$request"
        write_control_ack "$request"
        expected=${request/arm-/finish-}
      elif [[ $request == "$expected" && $request =~ ^finish-(enroll|verify-[123]|delete)$ ]]; then
        next=${request#finish-}
        collect_epoch_journal "$next" "$armed_cursor" || fail journal_collection_failed
        rm -f -- "$public/control/$request"
        write_control_ack "$request"
        case $next in
          enroll) expected=arm-verify-1 ;;
          verify-1) expected=arm-verify-2 ;;
          verify-2) expected=arm-verify-3 ;;
          verify-3) expected=complete-verify ;;
          delete) expected=complete ;;
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
  prepare_capture_base || fail capture_base_integrity
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
DAEMON_PATH=/usr/libexec/fprintd
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
  write_runtime_wrapper "$head" "$lib_sha" "$run_id" /usr/libexec/fprintd ||
    fail wrapper_generation_failed
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
  local caller_uid=$1 file uid recovery run_id residual_run_id= count=0 selected=
  [[ -e $capture_base || -L $capture_base ]] || return 1
  validate_capture_base || return 3
  if [[ -f $private/state.env && ! -L $private/state.env ]]; then
    residual_run_id=$(state_value RUN_ID) || return 2
  elif [[ -f $public/public.env && ! -L $public/public.env ]]; then
    residual_run_id=$(one_from_file D293_04_RUN_ID "$public/public.env") || return 2
  fi
  while IFS= read -r -d '' file; do
    [[ $(stat -c %u "$file") -eq $EUID && $(stat -c %a "$file") == 400 ]] || continue
    uid=$(one_from_file D293_04_ORIGINAL_UID "$file") || continue
    [[ $uid == "$caller_uid" ]] || continue
    run_id=$(one_from_file D293_04_RUN_ID "$file") || continue
    recovery=$(dirname -- "$file")/recovery.env
    if [[ -f $recovery && ! -L $recovery ]] &&
       grep -Fx D293_04_FINAL_RECOVERY=PASS "$recovery" >/dev/null &&
       [[ $run_id != "$residual_run_id" ]]; then
      continue
    fi
    selected=$file
    count=$((count + 1))
  done < <(find "$capture_base" -mindepth 2 -maxdepth 2 -name run.env -type f -print0)
  [[ $count -eq 1 ]] || return "$((count == 0 ? 1 : 2))"
  printf '%s\n' "$selected"
}

record_recovery_integrity_failure() {
  local run_root=$1 run_id=$2 reason=$3 marker=$run_root/recovery-integrity-failure.env
  [[ $run_root == "$capture_base/$run_id" && -d $run_root && ! -L $run_root &&
     $reason =~ ^[a-z0-9_]+$ ]] || return 1
  if [[ -f $marker && ! -L $marker ]]; then
    [[ $(one_from_file D293_04_RUN_ID "$marker") == "$run_id" &&
       $(one_from_file D293_04_RECOVERY_INTEGRITY_FAILURE "$marker") == true ]]
    return
  fi
  [[ ! -e $marker && ! -L $marker ]] || return 1
  {
    printf 'D293_04_RUN_ID=%s\n' "$run_id"
    printf 'D293_04_RECOVERY_INTEGRITY_FAILURE=true\n'
    printf 'D293_04_RECOVERY_INTEGRITY_REASON=%s\n' "$reason"
  } | atomic_from_stdin "$marker" 0400
}

stop_recovery_integrity() {
  local run_root=$1 run_id=$2 capture_root=$3 reason=$4
  record_recovery_integrity_failure "$run_root" "$run_id" "$reason" ||
    fail recovery_integrity_record_failed
  printf 'D293_04_ROOT_HELPER=FAIL reason=%s\n' "$reason" >&2
  printf 'D293_04_CAPTURE_RETAINED=%s\n' "$capture_root"
  printf 'D293_04_FINAL_RECOVERY=FAIL\n'
}

recover() {
  local caller=${PKEXEC_UID:-} result=PASS rollback_rc=0 supervisor_rc=0
  local metadata= original original_uid original_gid recorded_original_gid uid gid run_id run_root capture_root before now
  local removal_intent intent_state
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
    if [[ $resolve_rc -eq 3 ]]; then fail capture_base_integrity; fi
    getent passwd "$test_user" >/dev/null && fail test_account_without_attributed_run
    audit_d285 D293_04_FINAL_RECOVERY_IDEMPOTENT "$original" || result=FAIL
    mountpoint -q "$mountpoint_path" && result=FAIL
    if [[ $result == PASS && -d $public && ! -L $public ]]; then
      remove_tree "$public" "$public" || result=FAIL
    fi
    if [[ $result == PASS && -d $private && ! -L $private ]]; then
      remove_tree "$private" "$private" || result=FAIL
    fi
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
    printf 'D293_04_CAPTURE_RETAINED=%s\n' "$capture_base"
    printf 'D293_04_FINAL_RECOVERY=%s\n' "$result"
    [[ $result == PASS ]]
    return
  fi

  run_root=$(dirname -- "$metadata")
  run_id=$(one_from_file D293_04_RUN_ID "$metadata") || fail recovery_run_id_missing
  [[ $run_root == "$capture_base/$run_id" && ! -L $run_root ]] || fail recovery_run_path_invalid
  if mountpoint -q "$mountpoint_path"; then
    umount "$mountpoint_path" || result=FAIL
  fi
  mountpoint -q "$mountpoint_path" && result=FAIL
  if [[ $(one_from_file D293_04_ORIGINAL_UID "$metadata") != "$caller" ||
        $(one_from_file D293_04_ORIGINAL_USER "$metadata") != "$original" ]]; then
    stop_recovery_integrity "$run_root" "$run_id" "$run_root/capture" \
      recovery_original_identity_mismatch
    return 1
  fi
  if [[ $(one_from_file D293_04_TEST_USER "$metadata") != "$test_user" ]]; then
    stop_recovery_integrity "$run_root" "$run_id" "$run_root/capture" recovery_test_name_mismatch
    return 1
  fi
  if [[ -f $run_root/recovery-integrity-failure.env &&
        ! -L $run_root/recovery-integrity-failure.env ]]; then
    [[ $(one_from_file D293_04_RUN_ID "$run_root/recovery-integrity-failure.env") == "$run_id" &&
       $(one_from_file D293_04_RECOVERY_INTEGRITY_FAILURE "$run_root/recovery-integrity-failure.env") == true ]] ||
      fail recovery_integrity_marker_invalid
    printf 'D293_04_CAPTURE_RETAINED=%s\n' "$run_root/capture"
    printf 'D293_04_FINAL_RECOVERY=FAIL\n'
    return 1
  fi
  uid=$(one_from_file D293_04_TEST_UID "$metadata") ||
    { record_recovery_integrity_failure "$run_root" "$run_id" recovery_test_uid_missing || fail recovery_integrity_record_failed;
      fail recovery_test_uid_missing; }
  gid=$(one_from_file D293_04_TEST_GID "$metadata") ||
    { record_recovery_integrity_failure "$run_root" "$run_id" recovery_test_gid_missing || fail recovery_integrity_record_failed;
      fail recovery_test_gid_missing; }
  if [[ ! $uid =~ ^[1-9][0-9]*$ || ! $gid =~ ^[0-9]+$ ]]; then
    stop_recovery_integrity "$run_root" "$run_id" "$run_root/capture" recovery_test_identity_malformed
    return 1
  fi
  recorded_original_gid=$(one_from_file D293_04_ORIGINAL_GID "$metadata") || {
    stop_recovery_integrity "$run_root" "$run_id" "$run_root/capture" recovery_original_gid_missing
    return 1
  }
  if [[ ! $recorded_original_gid =~ ^[0-9]+$ || $recorded_original_gid != "$original_gid" ]]; then
    stop_recovery_integrity "$run_root" "$run_id" "$run_root/capture" recovery_original_gid_mismatch
    return 1
  fi
  capture_root=$run_root/capture
  removal_intent=$run_root/account-removal.intent
  before=$(one_from_file D293_04_ORIGINAL_PRINCIPAL_DIGEST "$metadata") || {
    stop_recovery_integrity "$run_root" "$run_id" "$capture_root" recovery_digest_missing
    return 1
  }
  if [[ $before != ABSENT && ! $before =~ ^[0-9a-f]{64}$ ]]; then
    stop_recovery_integrity "$run_root" "$run_id" "$capture_root" recovery_digest_malformed
    return 1
  fi
  now=$(principal_digest "$original") || now=ERROR
  if [[ $now != "$before" ]]; then
    record_recovery_integrity_failure "$run_root" "$run_id" principal_digest_mismatch ||
      fail recovery_integrity_record_failed
    printf 'D293_04_CAPTURE_RETAINED=%s\n' "$capture_root"
    printf 'D293_04_FINAL_RECOVERY=FAIL\n'
    return 1
  fi

  if [[ $result == PASS ]] && getent passwd "$test_user" >/dev/null; then
    if [[ $(id -u "$test_user") != "$uid" || $(id -g "$test_user") != "$gid" ||
          $(getent passwd "$test_user" | cut -d: -f6) != /home/$test_user ]]; then
      stop_recovery_integrity "$run_root" "$run_id" "$capture_root" test_account_identity_drift
      return 1
    fi
    ! pgrep -u "$uid" >/dev/null || fail test_user_still_logged_in
    [[ ! -d /var/lib/fprint/$test_user ]] ||
      ! find "/var/lib/fprint/$test_user" -type f -print -quit | grep -q . ||
      fail test_storage_remains_use_kcm
    [[ -d $capture_root && ! -L $capture_root ]] ||
      { record_recovery_integrity_failure "$run_root" "$run_id" capture_root_invalid || fail recovery_integrity_record_failed;
        fail capture_root_invalid; }
    [[ -z $(find "$capture_root" -xdev ! -type d ! -type f -print -quit) ]] ||
      { record_recovery_integrity_failure "$run_root" "$run_id" capture_special_file || fail recovery_integrity_record_failed;
        fail capture_special_file; }
    if [[ -f $removal_intent && ! -L $removal_intent ]]; then
      [[ $(one_from_file D293_04_RUN_ID "$removal_intent") == "$run_id" &&
         $(one_from_file D293_04_TEST_UID "$removal_intent") == "$uid" ]] ||
        { record_recovery_integrity_failure "$run_root" "$run_id" account_removal_intent_invalid || fail recovery_integrity_record_failed;
          fail account_removal_intent_invalid; }
      intent_state=$(one_from_file D293_04_ACCOUNT_REMOVAL_STATE "$removal_intent" 2>/dev/null || true)
      if [[ -z $intent_state ]] &&
         grep -Fx D293_04_ACCOUNT_REMOVAL=INTENT_RECORDED "$removal_intent" >/dev/null; then
        intent_state=COMPLETE
      fi
      [[ $intent_state == PENDING || $intent_state == COMPLETE ]] ||
        { record_recovery_integrity_failure "$run_root" "$run_id" account_removal_intent_invalid || fail recovery_integrity_record_failed;
          fail account_removal_intent_invalid; }
    else
      [[ ! -e $removal_intent && ! -L $removal_intent ]] ||
        { record_recovery_integrity_failure "$run_root" "$run_id" account_removal_intent_invalid || fail recovery_integrity_record_failed;
          fail account_removal_intent_invalid; }
      [[ -z $(find "$capture_root" -xdev ! -user "$test_user" -print -quit) ]] ||
        { record_recovery_integrity_failure "$run_root" "$run_id" capture_owner_drift || fail recovery_integrity_record_failed;
          fail capture_owner_drift; }
      {
        printf 'D293_04_RUN_ID=%s\n' "$run_id"
        printf 'D293_04_TEST_UID=%s\n' "$uid"
        printf 'D293_04_ACCOUNT_REMOVAL_STATE=PENDING\n'
      } | atomic_from_stdin "$removal_intent" 0400 || result=FAIL
      intent_state=PENDING
    fi
    if [[ $result == PASS && $intent_state == PENDING ]]; then
      [[ -z $(find "$capture_root" -xdev \
        ! \( -user "$test_user" -o -user "$original" \) -print -quit) ]] ||
        { record_recovery_integrity_failure "$run_root" "$run_id" capture_owner_during_transfer_drift || fail recovery_integrity_record_failed;
          fail capture_owner_during_transfer_drift; }
      chown -R "$original:$original_gid" "$capture_root" || result=FAIL
      if [[ $result == PASS ]]; then
        [[ -z $(find "$capture_root" -xdev ! -user "$original" -print -quit) ]] ||
          { record_recovery_integrity_failure "$run_root" "$run_id" capture_owner_after_transfer_drift || fail recovery_integrity_record_failed;
            fail capture_owner_after_transfer_drift; }
        {
          printf 'D293_04_RUN_ID=%s\n' "$run_id"
          printf 'D293_04_TEST_UID=%s\n' "$uid"
          printf 'D293_04_ACCOUNT_REMOVAL_STATE=COMPLETE\n'
        } | atomic_from_stdin "$removal_intent" 0400 || result=FAIL
      fi
    fi
    if [[ $result == PASS && $intent_state == COMPLETE ]]; then
      [[ -z $(find "$capture_root" -xdev ! -user "$original" -print -quit) ]] ||
        { record_recovery_integrity_failure "$run_root" "$run_id" capture_owner_after_intent_drift || fail recovery_integrity_record_failed;
          fail capture_owner_after_intent_drift; }
    fi
    if [[ $result == PASS ]]; then userdel -r "$test_user" || result=FAIL; fi
  elif [[ $result == PASS ]]; then
    [[ -f $removal_intent && ! -L $removal_intent ]] || fail attributed_test_account_missing
    [[ $(one_from_file D293_04_RUN_ID "$removal_intent") == "$run_id" &&
       $(one_from_file D293_04_TEST_UID "$removal_intent") == "$uid" ]] ||
      { record_recovery_integrity_failure "$run_root" "$run_id" account_removal_intent_invalid || fail recovery_integrity_record_failed;
        fail account_removal_intent_invalid; }
    intent_state=$(one_from_file D293_04_ACCOUNT_REMOVAL_STATE "$removal_intent" 2>/dev/null || true)
    if [[ -z $intent_state ]] &&
       grep -Fx D293_04_ACCOUNT_REMOVAL=INTENT_RECORDED "$removal_intent" >/dev/null; then
      intent_state=COMPLETE
    fi
    [[ $intent_state == COMPLETE ]] ||
      { record_recovery_integrity_failure "$run_root" "$run_id" account_removal_intent_incomplete || fail recovery_integrity_record_failed;
        fail account_removal_intent_incomplete; }
    [[ -d $capture_root && ! -L $capture_root &&
       -z $(find "$capture_root" -xdev ! -user "$original" -print -quit) ]] ||
      { record_recovery_integrity_failure "$run_root" "$run_id" retained_capture_invalid_after_account_removal || fail recovery_integrity_record_failed;
        fail retained_capture_invalid_after_account_removal; }
  fi
  now=$(principal_digest "$original") || { now=ERROR; result=FAIL; }
  if [[ $now != "$before" ]]; then
    record_recovery_integrity_failure "$run_root" "$run_id" principal_digest_mismatch ||
      fail recovery_integrity_record_failed
    result=FAIL
  fi
  audit_d285 D293_04_FINAL_RECOVERY "$original" || result=FAIL

  if [[ $result == PASS && -d $public && ! -L $public ]]; then
    ! mountpoint -q "$mountpoint_path" || fail public_mount_still_active
    remove_tree "$public" "$public" || result=FAIL
  fi
  if [[ $result == PASS && -d $private && ! -L $private ]]; then
    remove_tree "$private" "$private" || result=FAIL
  fi
  systemctl reset-failed "$unit" >/dev/null 2>&1 || true
  if [[ $result == PASS ]]; then
    [[ ! -f $run_root/rollback-history.log ]] || chmod 0400 "$run_root/rollback-history.log" || result=FAIL
  fi
  if [[ $result == PASS ]]; then
    {
      printf 'D293_04_RUN_ID=%s\n' "$run_id"
      printf 'D293_04_FINAL_RECOVERY=PASS\n'
      printf 'D293_04_CAPTURE_RETAINED=%s\n' "$capture_root"
    } | atomic_from_stdin "$run_root/recovery.env" 0444 || result=FAIL
  fi
  printf 'D293_04_CAPTURE_RETAINED=%s\n' "$capture_root"
  printf 'D293_04_FINAL_RECOVERY=%s\n' "$result"
  [[ $result == PASS ]]
}

case ${1:-} in
  --deploy) shift; deploy "$@" ;;
  --supervise) [[ $# -eq 1 ]]; supervise ;;
  --recover) [[ $# -eq 1 ]]; recover ;;
  *) fail arguments ;;
esac
