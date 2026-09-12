#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

echo "D291_01_STATUS=HISTORICAL_ONLY_DO_NOT_RERUN" >&2
echo "D291_01_REFUSAL_REASON=BIOMETRIC_ROOT_CAUSE_NOT_IDENTIFIED" >&2
exit 4

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script_path="$script_dir/run-d291-01.sh"
root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
d282="$root/operator_kit/d282-01-fprintd-target/run-d282-01.sh"
d286="$root/operator_kit/d286-01-reboot-survival/run-d286-01.sh"
state=/etc/goodix-27c6-5125/d285-01.state
pam=/etc/pam.d/goodix-d285-01-sudo
candidate= backup= runtime= deployment_started=false service_was_active=false

refuse () {
  echo D291_01_GATE_REFUSED=true >&2
  echo "D291_01_REFUSAL_REASON=$1" >&2
  exit 3
}

value () {
  local result
  result=$(sed -n "s/^$2=//p" "$1")
  [[ -n $result && $(grep -c "^$2=" "$1") -eq 1 ]] || return 1
  printf '%s\n' "$result"
}

cleanup_candidate () {
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -d $candidate &&
     ! -L $candidate ]] && find "$candidate" -xdev -depth -delete || true
}

rollback () {
  local exit_status=$? rollback_status=0
  [[ $deployment_started == true ]] || return "$exit_status"
  set +e
  systemctl stop fprintd.service || rollback_status=1
  install -m 0644 "$backup/libfprint-2.so.2.0.0" "$runtime/" || rollback_status=1
  install -m 0644 "$backup/artifacts.sha256" "$runtime/" || rollback_status=1
  install -m 0600 "$backup/d285-01.state" "$state" || rollback_status=1
  restorecon "$runtime/libfprint-2.so.2.0.0" "$runtime/artifacts.sha256" "$state" ||
    rollback_status=1
  (cd "$runtime" && sha256sum -c artifacts.sha256 >/dev/null) || rollback_status=1
  [[ $service_was_active != true ]] || systemctl start fprintd.service || rollback_status=1
  [[ $rollback_status -ne 0 ]] || find "$backup" -xdev -depth -delete || rollback_status=1
  deployment_started=false
  if [[ $rollback_status -eq 0 ]]; then
    echo D291_01_ROLLBACK=PASS_OLD_RUNTIME_RESTORED >&2
    echo D291_01_LIVE_RESULT=FAIL_ROLLED_BACK >&2
  else
    echo D291_01_ROLLBACK=FAILED_HUMAN_RECOVERY_REQUIRED >&2
    echo D291_01_LIVE_RESULT=FAIL_RECOVERY_REQUIRED >&2
    return 1
  fi
  return "$exit_status"
}

root_run () {
  local source=$1 baseline=$2 operator=${D291_OPERATOR_USER:-} manifest old_manifest
  local cursor journal audit first second result sudo_rc poll name epoch_count outcome_count matched_attempt
  local -a epochs outcomes
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
  [[ $runtime == /usr/local/lib64/goodix-27c6-5125/d285-01-* &&
     $(sha256sum "$runtime/artifacts.sha256" | awk '{print $1}') == "$old_manifest" &&
     $(sha256sum "$pam" | awk '{print $1}') == $(value "$state" D285_01_PAM_SHA256) ]] ||
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
  [[ $(systemctl is-active fprintd.service || true) != active ]] || service_was_active=true
  deployment_started=true
  trap rollback EXIT
  trap 'exit 130' HUP INT TERM
  systemctl stop fprintd.service
  install -m 0644 "$candidate/libfprint-2.so.2.0.0" "$runtime/"
  install -m 0644 "$candidate/d282-01-artifacts.sha256" "$runtime/artifacts.sha256"
  manifest=$(sha256sum "$runtime/artifacts.sha256" | awk '{print $1}')
  awk -v manifest="$manifest" -v baseline="$baseline" '
    /^D285_01_MANIFEST_SHA256=/ { print "D285_01_MANIFEST_SHA256=" manifest; next }
    /^D291_01_DRIVER_BASELINE_SHA=/ { next }
    { print }
    END { print "D291_01_DRIVER_BASELINE_SHA=" baseline }
  ' "$state" >"$backup/state.updated"
  install -m 0600 "$backup/state.updated" "$state"
  restorecon "$runtime/libfprint-2.so.2.0.0" "$runtime/artifacts.sha256" "$state"
  "$d286" --root-audit D291_POST --user "$operator" >/dev/null ||
    refuse DEPLOYED_RUNTIME_AUDIT_FAILED
  systemctl start fprintd.service
  grep -F "$runtime/libfprint-2.so.2.0.0" \
    "/proc/$(systemctl show -p MainPID --value fprintd.service)/maps" >/dev/null ||
    refuse DEPLOYED_RUNTIME_NOT_MAPPED

  cursor=$(LC_ALL=C journalctl -u fprintd.service -n 0 --show-cursor --no-pager |
    sed -n 's/^-- cursor: //p')
  [[ -n $cursor ]] || refuse JOURNAL_CURSOR_UNAVAILABLE
  runuser -u "$operator" -- sudo -k
  echo 'Tentativo 1: dito errato. Tentativo 2: indice destro registrato.'
  echo 'Se compare la password, premere Ctrl-C senza digitarla.'
  printf 'Digitare D291 PRONTO: '
  read -r first second
  [[ $first == D291 && $second == PRONTO ]] || refuse OPERATOR_CANCELLED
  set +e
  runuser -u "$operator" -- env -u SUDO_ASKPASS sudo ls
  sudo_rc=$?
  set -e
  runuser -u "$operator" -- sudo -k
  journal="$backup/journal.filtered"
  for poll in {1..50}; do
    LC_ALL=C journalctl -u fprintd.service --after-cursor "$cursor" --no-pager |
      sed -n 's/^.*\(GOODIX_D282_EPOCH_AUDIT .*\)$/\1/p; s/^.*\(GOODIX_SIGFM_.*\)$/\1/p' \
      >"$journal"
    epoch_count=$(grep -c GOODIX_D282_EPOCH_AUDIT "$journal" || true)
    outcome_count=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT event=outcome' "$journal" || true)
    if [[ $epoch_count -eq 3 && $outcome_count -eq 3 ]] ||
       [[ $epoch_count -ge 2 && $epoch_count -eq $outcome_count ]] &&
       grep -q 'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match' "$journal"; then
      break
    fi
    sleep 0.1
  done
  mapfile -t epochs < <(grep 'GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY' "$journal" || true)
  mapfile -t outcomes < <(grep 'GOODIX_SIGFM_MATCH_AUDIT event=outcome' "$journal" || true)
  [[ $sudo_rc -eq 0 && ${#epochs[@]} -ge 2 && ${#epochs[@]} -le 3 &&
     ${#outcomes[@]} -eq ${#epochs[@]} &&
     ${outcomes[0]} == *result=no_match* &&
     ${outcomes[-1]} == *result=match* ]] ||
    refuse LIVE_OUTCOME_NOT_NO_MATCH_THEN_MATCH
  if [[ ${#outcomes[@]} -eq 3 ]]; then
    [[ ${outcomes[1]} == *result=no_match* ]] ||
      refuse THIRD_ATTEMPT_WITHOUT_SECOND_NO_MATCH
    matched_attempt=3
  else
    matched_attempt=2
  fi
  audit='attempts=1 rejected=0 consumed=1 tls=1 first_image=1.*secure_retry=0 post_retry=0 reopen=[01] explicit_verify_reopen=[01] reset=0 clear_halt=0 persistent=0.*outstanding=0 drained=1 context_closed=1'
  [[ $(printf '%s\n' "${epochs[@]}" | grep -Ec "$audit") -eq ${#epochs[@]} &&
     ${epochs[0]} == *'reopen=0 explicit_verify_reopen=0'* &&
     ${epochs[0]} == *'sigfm_baseline_pinned=1 sigfm_baseline_reused=0'* ]] ||
    refuse LIVE_EPOCH_AUDIT_FAILED
  for ((poll = 1; poll < ${#epochs[@]}; poll++)); do
    [[ ${epochs[$poll]} == *'reopen=1 explicit_verify_reopen=1'* &&
       ${epochs[$poll]} == *'sigfm_baseline_pinned=0 sigfm_baseline_reused=1'* ]] ||
      refuse LIVE_REOPEN_BASELINE_CONTINUITY_AUDIT_FAILED
  done

  result=$(mktemp -d /tmp/goodix-d291-01-result.XXXXXX)
  install -m 0600 -o "$(id -u "$operator")" -g "$(id -g "$operator")" "$journal" "$result/audit.log"
  printf '%s\n' D291_01_LIVE_RESULT=PASS_NO_MATCH_THEN_MATCH \
    "D291_01_VERIFY_EPOCH_COUNT=${#epochs[@]}" \
    "D291_01_MATCHED_ATTEMPT=$matched_attempt" \
    "D291_01_EXPLICIT_REOPEN_COUNT=$((${#epochs[@]} - 1))" \
    D291_01_HIDDEN_RETRY_COUNT=0 D291_01_NO_FOURTH_ATTEMPT=true \
    D291_01_SIGFM_BASELINE_CONTINUITY=PASS \
    TEMPLATE_INCLUDED=false >"$result/summary.env"
  chown -R "$(id -u "$operator"):$(id -g "$operator")" "$result"
  chmod 0700 "$result"
  find "$backup" -xdev -depth -delete
  deployment_started=false
  trap - EXIT HUP INT TERM
  echo D291_01_LIVE_RESULT=PASS_NO_MATCH_THEN_MATCH
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
  printf 'Digitare AGGIORNA D291 per il Human Gate: '
  read -r confirm
  [[ $confirm == 'AGGIORNA D291' ]] || refuse OPERATOR_CANCELLED
  pkexec env D291_OPERATOR_USER="$(id -un)" "$script_path" --root-run "$candidate" "$baseline"
}

case ${1:-} in
  --operator-run) [[ $# -le 2 ]] || refuse USAGE; operator_run "${2:-}" ;;
  --root-run) [[ $# -eq 3 ]] || refuse USAGE; root_run "$2" "$3" ;;
  *) echo "Uso: $0 --operator-run [directory-rpm-opencv]" >&2; exit 2 ;;
esac
