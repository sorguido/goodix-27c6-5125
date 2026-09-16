#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script_path="$script_dir/run-d291-01.sh"
root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
d282="$root/operator_kit/d282-01-fprintd-target/run-d282-01.sh"
d286="$root/operator_kit/d286-01-reboot-survival/run-d286-01.sh"
state=/etc/goodix-27c6-5125/d285-01.state
pam=/etc/pam.d/goodix-d285-01-sudo
candidate= backup= runtime= storage= old_template_relative= old_template_sha=
deployment_started=false service_was_active=false result= operator=

refuse () {
  echo D291_01_GATE_REFUSED=true >&2
  echo "D291_01_REFUSAL_REASON=$1" >&2
  exit 3
}

value () {
  local result_value
  result_value=$(sed -n "s/^$2=//p" "$1")
  [[ -n $result_value && $(grep -c "^$2=" "$1") -eq 1 ]] || return 1
  printf '%s\n' "$result_value"
}

is_sha256 () {
  [[ $1 =~ ^[0-9a-f]{64}$ ]]
}

cleanup_candidate () {
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -d $candidate &&
     ! -L $candidate ]] && find "$candidate" -xdev -depth -delete || true
}

restore_old_template () {
  [[ $storage == /var/lib/fprint/* &&
     $backup == /var/tmp/goodix-d291-01-backup.* &&
     -d $backup/fprint-user && ! -L $backup/fprint-user ]] || return 1
  if [[ -e $storage ]]; then
    [[ -d $storage && ! -L $storage ]] || return 1
    find "$storage" -mindepth 1 -xdev -depth -delete || return 1
    cp -a -- "$backup/fprint-user/." "$storage/" || return 1
  else
    cp -a -- "$backup/fprint-user" "$storage" || return 1
  fi
  restorecon -RF "$storage" || return 1
  [[ $(find "$storage" -type l | wc -l) -eq 0 &&
     $(find "$storage" -type f | wc -l) -eq 1 &&
     -f $storage/$old_template_relative &&
     $(sha256sum "$storage/$old_template_relative" | awk '{print $1}') == "$old_template_sha" ]]
}

rollback () {
  local exit_status=$? rollback_status=0
  [[ $deployment_started == true ]] || return "$exit_status"
  set +e
  systemctl stop fprintd.service || rollback_status=1
  restore_old_template || rollback_status=1
  install -m 0644 "$backup/libfprint-2.so.2.0.0" "$runtime/" || rollback_status=1
  install -m 0644 "$backup/artifacts.sha256" "$runtime/" || rollback_status=1
  install -m 0600 "$backup/d285-01.state" "$state" || rollback_status=1
  restorecon "$runtime/libfprint-2.so.2.0.0" "$runtime/artifacts.sha256" \
    "$state" || rollback_status=1
  (cd "$runtime" && sha256sum -c artifacts.sha256 >/dev/null) || rollback_status=1
  [[ $service_was_active != true ]] || systemctl start fprintd.service || rollback_status=1
  if [[ $rollback_status -eq 0 ]]; then
    find "$backup" -xdev -depth -delete || rollback_status=1
  fi
  deployment_started=false
  if [[ $rollback_status -eq 0 ]]; then
    echo D291_01_ROLLBACK=PASS_OLD_RUNTIME_AND_TEMPLATE_RESTORED >&2
    echo D291_01_LIVE_RESULT=FAIL_ROLLED_BACK >&2
  else
    echo D291_01_ROLLBACK=FAILED_HUMAN_RECOVERY_REQUIRED >&2
    echo D291_01_LIVE_RESULT=FAIL_RECOVERY_REQUIRED >&2
    return 1
  fi
  return "$exit_status"
}

write_updated_state () {
  local manifest=$1 template_relative=$2 template_sha=$3 baseline=$4 output=$5
  awk -v manifest="$manifest" -v template_relative="$template_relative" \
      -v template_sha="$template_sha" -v baseline="$baseline" '
    /^D285_01_MANIFEST_SHA256=/ {
      print "D285_01_MANIFEST_SHA256=" manifest; next
    }
    /^D285_01_TEMPLATE_RELATIVE_PATH=/ {
      print "D285_01_TEMPLATE_RELATIVE_PATH=" template_relative; next
    }
    /^D285_01_TEMPLATE_SHA256=/ {
      print "D285_01_TEMPLATE_SHA256=" template_sha; next
    }
    /^D291_01_DRIVER_BASELINE_SHA=/ { next }
    { print }
    END { print "D291_01_DRIVER_BASELINE_SHA=" baseline }
  ' "$state" >"$output"
}

current_cursor () {
  local cursor
  cursor=$(LC_ALL=C journalctl -u fprintd.service -n 0 --show-cursor --no-pager |
    sed -n 's/^-- cursor: //p')
  [[ -n $cursor ]] || return 1
  printf '%s\n' "$cursor"
}

collect_series () {
  local series=$1 cursor=$2 destination=$3 poll epoch_count outcome_count
  for poll in {1..50}; do
    LC_ALL=C journalctl -u fprintd.service --after-cursor "$cursor" --no-pager |
      sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT .*\)$/\1/p; s/^.*\(GOODIX_SIGFM_.*\)$/\1/p' \
      >"$destination"
    epoch_count=$(grep -c 'GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY' \
      "$destination" || true)
    outcome_count=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT event=outcome' \
      "$destination" || true)
    if [[ $epoch_count -ge 1 && $epoch_count -eq $outcome_count ]] &&
       grep -q 'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match' \
         "$destination"; then
      break
    fi
    sleep 0.1
  done
  grep -q 'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match' "$destination" ||
    refuse "SERIES_${series}_MATCH_AUDIT_MISSING"
}

run_verify_series () {
  local series=$1 mode=$2 cursor sudo_rc journal audit word1 word2 poll
  local -a epochs outcomes
  cursor=$(current_cursor) || refuse "SERIES_${series}_CURSOR_UNAVAILABLE"
  runuser -u "$operator" -- sudo -K ||
    refuse "SERIES_${series}_TIMESTAMP_INVALIDATION_FAILED"
  if [[ $mode == discrimination ]]; then
    echo "SERIE $series/4: primo contatto con un dito NON registrato; poi indice destro."
  else
    echo "SERIE $series/4: usa l'indice destro registrato in una normale posizione quotidiana."
  fi
  echo 'Sono consentiti al massimo tre prompt. Se compare la password, premere Ctrl-C.'
  printf "Digitare SERIE $series PRONTA: "
  read -r word1 word2
  [[ $word1 == SERIE && $word2 == "$series PRONTA" ]] ||
    refuse "SERIES_${series}_OPERATOR_CANCELLED"
  set +e
  timeout --signal=INT --kill-after=10s 155s \
    runuser -u "$operator" -- env -u SUDO_ASKPASS sudo -v
  sudo_rc=$?
  set -e
  runuser -u "$operator" -- sudo -K ||
    refuse "SERIES_${series}_FINAL_TIMESTAMP_INVALIDATION_FAILED"
  journal="$backup/series-$series.audit"
  collect_series "$series" "$cursor" "$journal"
  mapfile -t epochs < <(grep 'GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY' \
    "$journal" || true)
  mapfile -t outcomes < <(grep 'GOODIX_SIGFM_MATCH_AUDIT event=outcome' \
    "$journal" || true)
  [[ $sudo_rc -eq 0 && ${#epochs[@]} -ge 1 && ${#epochs[@]} -le 3 &&
     ${#outcomes[@]} -eq ${#epochs[@]} &&
     ${outcomes[-1]} == *result=match* ]] ||
    refuse "SERIES_${series}_NOT_MATCHED_WITHIN_THREE"
  if [[ $mode == discrimination ]]; then
    [[ ${#outcomes[@]} -ge 2 && ${outcomes[0]} == *result=no_match* ]] ||
      refuse SERIES_1_WRONG_FINGER_NOT_REJECTED
  fi
  audit='attempts=1 rejected=0 consumed=1 tls=1 first_image=1.*secure_retry=0 post_retry=0 reopen=[01] explicit_verify_reopen=[01] reset=0 clear_halt=0 persistent=0.*outstanding=0 drained=1 context_closed=1'
  [[ $(printf '%s\n' "${epochs[@]}" | grep -Ec "$audit") -eq ${#epochs[@]} &&
     ${epochs[0]} == *'reopen=0 explicit_verify_reopen=0'* &&
     ${epochs[0]} == *'sigfm_baseline_pinned=1 sigfm_baseline_reused=0'* ]] ||
    refuse "SERIES_${series}_EPOCH_AUDIT_FAILED"
  for ((poll = 1; poll < ${#epochs[@]}; poll++)); do
    [[ ${epochs[$poll]} == *'reopen=1 explicit_verify_reopen=1'* &&
       ${epochs[$poll]} == *'sigfm_baseline_pinned=0 sigfm_baseline_reused=1'* ]] ||
      refuse "SERIES_${series}_REOPEN_AUDIT_FAILED"
  done
  install -m 0600 "$journal" "$result/series-$series.audit.log"
  printf 'D291_01_SERIES_%s=PASS_MATCH_WITHIN_%s\n' "$series" "${#epochs[@]}" \
    >>"$result/summary.env"
}

root_run () {
  local source=$1 baseline=$2 manifest old_manifest new_template_relative
  local new_template_sha raw action_rc passed_count retry_count accepted_count
  local physical_count enroll_journal enroll_audit enroll_cursor name
  local audit_contacts audit_retries
  operator=${D291_OPERATOR_USER:-}
  [[ $EUID -eq 0 && $baseline =~ ^[0-9a-f]{40}$ &&
     $operator =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || refuse ROOT_ARGUMENT_INVALID
  candidate=$source
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -d $candidate &&
     ! -L $candidate ]] || refuse CANDIDATE_INVALID
  [[ $(runuser -u "$operator" -- git -C "$root" branch --show-current) == development &&
     $(runuser -u "$operator" -- git -C "$root" rev-parse HEAD) == "$baseline" &&
     $(runuser -u "$operator" -- git -C "$root" rev-parse origin/development) == "$baseline" &&
     -z $(runuser -u "$operator" -- git -C "$root" status --porcelain --untracked-files=all) ]] ||
    refuse REPOSITORY_PROVENANCE_DRIFT
  "$d286" --root-audit D291_PRE --user "$operator" >/dev/null ||
    refuse D285_ROOT_AUDIT_FAILED
  runtime=$(value "$state" D285_01_RUNTIME) || refuse D285_STATE_INVALID
  old_manifest=$(value "$state" D285_01_MANIFEST_SHA256) || refuse D285_STATE_INVALID
  old_template_relative=$(value "$state" D285_01_TEMPLATE_RELATIVE_PATH) ||
    refuse D285_STATE_INVALID
  old_template_sha=$(value "$state" D285_01_TEMPLATE_SHA256) ||
    refuse D285_STATE_INVALID
  storage=/var/lib/fprint/$operator
  is_sha256 "$old_template_sha" || refuse D285_TEMPLATE_HASH_INVALID
  [[ $runtime == /usr/local/lib64/goodix-27c6-5125/d285-01-* &&
     $(sha256sum "$runtime/artifacts.sha256" | awk '{print $1}') == "$old_manifest" &&
     $(sha256sum "$pam" | awk '{print $1}') == $(value "$state" D285_01_PAM_SHA256) &&
     $old_template_relative =~ ^[A-Za-z0-9_.:+-]+/[A-Za-z0-9_.:+-]+/[0-9a-f]$ &&
     -f $storage/$old_template_relative &&
     $(sha256sum "$storage/$old_template_relative" | awk '{print $1}') == "$old_template_sha" ]] ||
    refuse D285_STATE_OR_RUNTIME_DRIFT
  grep -Eq 'pam_fprintd\.so max-tries=3 timeout=45[[:space:]]*$' "$pam" ||
    refuse D285_PAM_NOT_BOUNDED_TO_THREE
  [[ $(grep -l '^27c6$' /sys/bus/usb/devices/*/idVendor 2>/dev/null |
       while read -r vendor; do [[ $(<"${vendor%/idVendor}/idProduct") == 5125 ]] && echo x; done |
       wc -l) -eq 1 ]] || refuse TARGET_CARDINALITY_NOT_ONE
  [[ $(value "$candidate/d282-01-candidate.state" D282_01_BASELINE_SHA) == "$baseline" &&
     $(sha256sum "$candidate/d282-01-artifacts.sha256" | awk '{print $1}') == $(value "$candidate/d282-01-candidate.state" D282_01_MANIFEST_SHA256) ]] ||
    refuse CANDIDATE_PROVENANCE_DRIFT
  (cd "$candidate" && sha256sum -c d282-01-artifacts.sha256 >/dev/null) ||
    refuse CANDIDATE_INTEGRITY_DRIFT
  for name in libgusb.so.2 libopencv_core.so.413 libopencv_features2d.so.413 \
      libopencv_flann.so.413 libopencv_imgproc.so.413; do
    [[ $(sha256sum "$candidate/$name" | awk '{print $1}') == $(sha256sum "$runtime/$name" | awk '{print $1}') ]] ||
      refuse NON_DRIVER_RUNTIME_DELTA
  done
  echo D291_01_HOST_RUNTIME_PREFLIGHT=PASS

  backup=$(mktemp -d /var/tmp/goodix-d291-01-backup.XXXXXX)
  chmod 0700 "$backup"
  install -m 0600 "$runtime/libfprint-2.so.2.0.0" "$runtime/artifacts.sha256" "$backup/"
  install -m 0600 "$state" "$backup/d285-01.state"
  cp -a -- "$storage" "$backup/fprint-user"
  [[ $(systemctl is-active fprintd.service || true) != active ]] || service_was_active=true
  deployment_started=true
  trap rollback EXIT
  trap 'exit 130' HUP INT TERM
  systemctl stop fprintd.service
  install -m 0644 "$candidate/libfprint-2.so.2.0.0" "$runtime/"
  install -m 0644 "$candidate/d282-01-artifacts.sha256" "$runtime/artifacts.sha256"
  manifest=$(sha256sum "$runtime/artifacts.sha256" | awk '{print $1}')
  write_updated_state "$manifest" "$old_template_relative" "$old_template_sha" \
    "$baseline" "$backup/state.deployed"
  install -m 0600 "$backup/state.deployed" "$state"
  restorecon "$runtime/libfprint-2.so.2.0.0" "$runtime/artifacts.sha256" "$state"
  "$d286" --root-audit D291_POST_DEPLOY --user "$operator" >/dev/null ||
    refuse DEPLOYED_RUNTIME_AUDIT_FAILED
  systemctl start fprintd.service
  grep -F "$runtime/libfprint-2.so.2.0.0" \
    "/proc/$(systemctl show -p MainPID --value fprintd.service)/maps" >/dev/null ||
    refuse DEPLOYED_RUNTIME_NOT_MAPPED

  echo 'RE-ENROLLMENT: il vecchio template host è protetto dal rollback.'
  echo 'Usare sempre l’indice destro, spostandolo fra centro, lati e punta.'
  echo 'I duplicati saranno rifiutati; sono ammessi al massimo 20 contatti fisici.'
  printf 'Digitare REENROLL DESTRO: '
  read -r raw action_rc
  [[ $raw == REENROLL && $action_rc == DESTRO ]] || refuse REENROLL_CANCELLED
  enroll_cursor=$(current_cursor) || refuse ENROLLMENT_CURSOR_UNAVAILABLE
  fprintd-delete "$operator" >"$backup/delete.raw" 2>&1 ||
    refuse OLD_TEMPLATE_DELETE_FAILED
  [[ $(find "$storage" -type f | wc -l) -eq 0 ]] ||
    refuse OLD_TEMPLATE_DELETE_INCOMPLETE
  raw="$backup/enroll.raw"
  set +e
  timeout --signal=INT --kill-after=20s 1060s stdbuf -oL -eL \
    fprintd-enroll -f right-index-finger "$operator" 2>&1 | tee "$raw"
  action_rc=${PIPESTATUS[0]}
  set -e
  passed_count=$(grep -c '^Enroll result: enroll-stage-passed$' "$raw" || true)
  retry_count=$(grep -c '^Enroll result: enroll-retry-' "$raw" || true)
  accepted_count=$((passed_count + $(grep -c '^Enroll result: enroll-completed$' "$raw" || true)))
  physical_count=$((accepted_count + retry_count))
  [[ $action_rc -eq 0 && $(grep -c '^Enroll result: enroll-completed$' "$raw") -eq 1 &&
     $accepted_count -ge 3 && $accepted_count -le 8 &&
     $physical_count -ge $accepted_count && $physical_count -le 20 &&
     $(find "$storage" -type l | wc -l) -eq 0 &&
     $(find "$storage" -type f | wc -l) -eq 1 ]] ||
    refuse DIVERSITY_ENROLLMENT_FAILED_OR_OUT_OF_BOUNDS
  new_template_relative=$(find "$storage" -type f -printf '%P\n')
  [[ $new_template_relative =~ ^[A-Za-z0-9_.:+-]+/[A-Za-z0-9_.:+-]+/[0-9a-f]$ &&
     $(head -c 3 "$storage/$new_template_relative") == FP3 ]] ||
    refuse NEW_TEMPLATE_FORMAT_OR_PATH_INVALID
  new_template_sha=$(sha256sum "$storage/$new_template_relative" | awk '{print $1}')
  is_sha256 "$new_template_sha" || refuse NEW_TEMPLATE_HASH_FAILED
  write_updated_state "$manifest" "$new_template_relative" "$new_template_sha" \
    "$baseline" "$backup/state.enrolled"
  install -m 0600 "$backup/state.enrolled" "$state"
  restorecon "$state" "$storage/$new_template_relative"
  systemctl restart fprintd.service
  "$d286" --root-audit D291_POST_REENROLL --user "$operator" >/dev/null ||
    refuse REENROLLED_STATE_AUDIT_FAILED

  enroll_journal="$backup/enroll.audit"
  LC_ALL=C journalctl -u fprintd.service --after-cursor "$enroll_cursor" --no-pager |
    sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_ENROLL .*\)$/\1/p' |
    tail -n 1 >"$enroll_journal"
  enroll_audit='attempts=1 rejected=0 consumed=1 tls=1.*enroll_stages=[3-8].*enroll_contacts=([3-9]|1[0-9]|20) enroll_retry_scans=([0-9]|1[0-7]).*secure_retry=0 post_retry=0.*reset=0 clear_halt=0 persistent=0.*outstanding=0 drained=1 context_closed=1'
  grep -Eq "$enroll_audit" "$enroll_journal" || refuse ENROLLMENT_EPOCH_AUDIT_FAILED
  audit_contacts=$(sed -n 's/^.* enroll_contacts=\([0-9][0-9]*\) .*$/\1/p' \
    "$enroll_journal")
  audit_retries=$(sed -n 's/^.* enroll_retry_scans=\([0-9][0-9]*\) .*$/\1/p' \
    "$enroll_journal")
  [[ $audit_contacts == "$physical_count" && $audit_retries == "$retry_count" ]] ||
    refuse ENROLLMENT_CONTACT_TELEMETRY_MISMATCH

  result=$(mktemp -d /tmp/goodix-d291-01-result.XXXXXX)
  chmod 0700 "$result"
  install -m 0600 "$enroll_journal" "$result/enrollment.audit.log"
  printf '%s\n' \
    D291_01_LIVE_RESULT=IN_PROGRESS \
    "D291_01_ENROLL_ACCEPTED_SAMPLE_COUNT=$accepted_count" \
    "D291_01_ENROLL_RETRY_COUNT=$retry_count" \
    "D291_01_ENROLL_PHYSICAL_CONTACT_COUNT=$physical_count" \
    D291_01_ENROLL_PHYSICAL_CONTACT_MAX=20 \
    D291_01_TEMPLATE_BYTES_EXPORTED=false >"$result/summary.env"

  run_verify_series 1 discrimination
  run_verify_series 2 registered
  run_verify_series 3 registered
  run_verify_series 4 registered

  sed -i 's/^D291_01_LIVE_RESULT=.*/D291_01_LIVE_RESULT=PASS_REENROLL_AND_4_MATCHED_SERIES/' \
    "$result/summary.env"
  printf '%s\n' D291_01_PAM_MAX_TRIES=3 D291_01_STOP_ON_FIRST_MATCH=true \
    D291_01_NO_FOURTH_ATTEMPT=true D291_01_HIDDEN_VERIFY_RETRY_COUNT=0 \
    D291_01_WRONG_FINGER_REJECTED=true D291_01_REGISTERED_SERIES_MATCHED=4 \
    TEMPLATE_INCLUDED=false >>"$result/summary.env"
  chown -R "$(id -u "$operator"):$(id -g "$operator")" "$result"
  find "$backup" -xdev -depth -delete
  deployment_started=false
  trap - EXIT HUP INT TERM
  echo D291_01_LIVE_RESULT=PASS_REENROLL_AND_4_MATCHED_SERIES
  echo "RESULT_DIRECTORY=$result"
}

operator_run () {
  local rpm_dir=${1:-$root/GoodixArtifacts/opencv-4.13-rpms} baseline output confirm
  [[ $EUID -ne 0 && $(git -C "$root" branch --show-current) == development ]] ||
    refuse OPERATOR_OR_BRANCH_INVALID
  baseline=$(git -C "$root" rev-parse HEAD)
  [[ $(git -C "$root" rev-parse origin/development) == "$baseline" &&
     -z $(git -C "$root" status --porcelain --untracked-files=all) ]] ||
    refuse REPOSITORY_NOT_CLEAN_PUSHED_BASELINE
  output=$("$d282" --prepare-candidate "$baseline" "$rpm_dir")
  printf '%s\n' "$output"
  candidate=$(printf '%s\n' "$output" | sed -n 's/^CANDIDATE_DIRECTORY=//p')
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -d $candidate ]] ||
    refuse CANDIDATE_BUILD_FAILED
  trap cleanup_candidate EXIT
  trap 'exit 130' HUP INT TERM
  echo 'Questa run sostituisce il template host dell’indice destro dopo un backup root-only.'
  echo 'Un errore ripristina automaticamente runtime, state e vecchio template.'
  printf 'Digitare AGGIORNA D291: '
  read -r confirm
  [[ $confirm == 'AGGIORNA D291' ]] || refuse OPERATOR_CANCELLED
  pkexec env D291_OPERATOR_USER="$(id -un)" "$script_path" \
    --root-run "$candidate" "$baseline"
}

case ${1:-} in
  --operator-run|--root-run)
    echo D291_01_STATUS=HISTORICAL_CLOSED_DO_NOT_RERUN >&2
    echo D291_01_LIVE_RESULT=PASS_REENROLL_AND_4_MATCHED_SERIES >&2
    exit 4
    ;;
  *) echo "Uso: $0 --operator-run [directory-rpm-opencv]" >&2; exit 2 ;;
esac
