#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
operation=D282_01_FPRINTD_TARGET_ENROLL_RESTART_VERIFY_SAME_DIFFERENT_DELETE
real_usb_enumeration_attempted=false
live_execution_performed=false
grant_consumed=false
d282_offline_work=
validated_grant_user=
validated_grant_sha=
validated_grant_owner=
validated_grant_mode=
grant_claim_root=
grant_claim=
validated_selinux_enforcement=Unavailable
live_critical=(libfprint-driver reference/libfprint-fedora44-1.94.100/source
  reference/fprintd-fedora44-1.94.5 Rockytkg analysis/D282
  operator_kit/d282-01-fprintd-target
  operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256)

refuse () {
  echo "D282_01_GATE_REFUSED=true" >&2
  echo "D282_01_REFUSAL_REASON=$1" >&2
  echo "GRANT_CONSUMED=$grant_consumed" >&2
  echo "RETRY_AUTHORIZED=false" >&2
  echo "REAL_USB_ENUMERATION_ATTEMPTED=$real_usb_enumeration_attempted" >&2
  echo "LIVE_EXECUTION_PERFORMED=$live_execution_performed" >&2
  exit 3
}

is_sha () { [[ ${1:-} =~ ^[0-9a-f]{40}$ ]]; }
cleanup_offline_work () {
  [[ -z $d282_offline_work ]] ||
    find "$d282_offline_work" -depth -delete 2>/dev/null || true
}
state_value () {
  local file=$1 key=$2 value
  value=$(sed -n "s/^${key}=//p" "$file")
  [[ -n $value && $(grep -c "^${key}=" "$file") -eq 1 ]] || return 1
  printf '%s\n' "$value"
}

verify_baseline () {
  local approved=$1
  is_sha "$approved" || refuse INVALID_BASELINE
  [[ $(git -C "$root" branch --show-current) == development ]] || refuse WRONG_BRANCH
  [[ $(git -C "$root" rev-parse HEAD) == "$approved" ]] || refuse HEAD_MISMATCH
  [[ $(git -C "$root" rev-parse origin/development) == "$approved" ]] ||
    refuse ORIGIN_DEVELOPMENT_MISMATCH
  [[ -z $(git -C "$root" status --porcelain --untracked-files=all -- \
    "${live_critical[@]}") ]] || refuse LIVE_CRITICAL_DIRTY
}

find_gusb () {
  local path
  for path in /usr/lib64/libgusb.so.2.0.10 /usr/lib64/libgusb.so.2 \
    /usr/lib/x86_64-linux-gnu/libgusb.so.2; do
    [[ -f $path ]] && { printf '%s\n' "$path"; return; }
  done
  return 1
}

build_candidate () {
  local source_root=$1 output=$2 rpm_dir=$3 build pkgconfig prefix package gusb component
  build="$output/build"
  pkgconfig="$output/pkgconfig"
  prefix="$output/opencv-prefix"
  [[ -d $rpm_dir && ! -L $rpm_dir ]] || refuse OPENCV_RPM_DIR_INVALID
  (cd "$rpm_dir" && sha256sum -c \
    "$source_root/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256")
  mkdir -p "$build" "$pkgconfig" "$prefix"
  for package in "$rpm_dir"/*.rpm; do
    (cd "$prefix" && rpm2cpio "$package" | cpio -idm --quiet)
  done
  gusb=$(find_gusb) || refuse HOST_GUSB_MISSING
  cp "$gusb" "$pkgconfig/libgusb.so.2"
  sed -e "s|@PREFIX@|$pkgconfig|g" \
      -e "s|@INCLUDEDIR@|$source_root/libfprint-driver/tests/support/d279|g" \
      "$source_root/libfprint-driver/tests/support/d279/gusb.pc.in" >"$pkgconfig/gusb.pc"
  sed -e "s|@PREFIX@|$prefix/usr|g" \
      "$source_root/libfprint-driver/tests/support/d279/opencv4.pc.in" >"$pkgconfig/opencv4.pc"
  flatpak run --user --unshare=network \
    --filesystem="$source_root:ro" --filesystem="$output" \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$source_root/operator_kit/d282-01-fprintd-target/build-inner.sh" \
    "$source_root" "$build" "$pkgconfig" "$output"
  cp "$pkgconfig/libgusb.so.2" "$output/libgusb.so.2"
  for component in core features2d flann imgproc; do
    cp -L "$prefix/usr/lib64/libopencv_${component}.so.4.13.0" \
      "$output/libopencv_${component}.so.413"
  done
  chmod 0600 "$output"/*.so.*
}

abi_preflight () {
  local candidate=$1 binary=/usr/libexec/fprintd required provided symbol
  [[ $(rpm -q fprintd) == fprintd-1.94.5-5.fc44.x86_64 ]] || refuse FPRINTD_NEVRA_DRIFT
  required=$(nm -D --undefined-only "$binary" |
    awk '$1=="U" && $2 ~ /@LIBFPRINT_2[.]0[.]0$/ {sub(/@.*/,"",$2); print $2}' | sort -u)
  provided=$(nm -D --defined-only "$candidate/libfprint-2.so.2.0.0" |
    awk '$3 ~ /@@LIBFPRINT_2[.]0[.]0$/ {sub(/@@.*/,"",$3); print $3}' | sort -u)
  for symbol in $required; do
    grep -Fx "$symbol" <<<"$provided" >/dev/null || refuse ABI_SYMBOL_MISSING
  done
  LD_LIBRARY_PATH="$candidate" ldd "$binary" >"$candidate/fprintd.ldd"
  grep -F "$candidate/libfprint-2.so.2" "$candidate/fprintd.ldd" >/dev/null ||
    refuse FPRINTD_LDD_NOT_STAGED
  ! grep -F 'not found' "$candidate/fprintd.ldd" >/dev/null || refuse RUNTIME_DEPENDENCY_MISSING
}

offline_preflight () {
  local rpm_dir=$1 work
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  bash -n "$script_dir/run-d282-01.sh"
  sh -n "$script_dir/build-inner.sh"
  (cd "$root" && python3 -m unittest -v analysis.D282.test_d282_01_offline_contract)
  (cd "$root" && python3 -m unittest -v analysis.D281.test_d281_01_fprintd_storage_integration)
  "$root/analysis/D281/d281_01_fprintd_storage_integration.sh"
  "$root/libfprint-driver/tests/run_goodix_d278_secure_session_test.sh"
  "$root/libfprint-driver/tests/run_goodix_fedora44_nbis_action_test.sh" "$rpm_dir"
  work=$(mktemp -d /tmp/goodix-d282-01-offline.XXXXXX)
  d282_offline_work=$work
  trap cleanup_offline_work EXIT
  build_candidate "$root" "$d282_offline_work" "$rpm_dir"
  abi_preflight "$d282_offline_work"
  echo D282_01_OFFLINE_PREFLIGHT=PASS
  echo D282_01_FPRINTD_EXACT_SOURCE_AUDIT=PASS
  echo D282_01_TEST_MATRIX_COUNT=30
  echo D282_01_NORMAL_AND_ASAN_UBSAN=PASS
  echo D282_01_REVERSIBLE_STAGING_MODEL=PASS
  echo D282_01_PREEXISTING_STORAGE_MODEL=PASS
  echo D282_01_GRANT_ORDERING_CORRECTIVE=PASS
  echo PRECONSUMPTION_REFUSALS_LEAVE_GRANT_UNUSED=true
  echo POSTCONSUMPTION_FAILURE_RETRY_AUTHORIZED=false
  echo CORRUPT_FP3_REJECTED=PASS_OFFLINE
  echo MISSING_FP3_REJECTED=PASS_OFFLINE
  echo WRONG_USER_FINGER_REJECTED=PASS_OFFLINE
  echo CURRENT_LIVE_AUTHORIZED=false
  echo CURRENT_PRIVILEGED_INSTALL_AUTHORIZED=false
  echo APPROVED_BASELINE=NONE
  echo GRANT_CREATED=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
  trap - EXIT
  cleanup_offline_work
  d282_offline_work=
}

prepare_candidate () {
  local approved=$1 rpm_dir=$2 output snapshot manifest_sha
  [[ $EUID -ne 0 ]] || refuse PREPARE_MUST_BE_UNPRIVILEGED
  verify_baseline "$approved"
  output=$(mktemp -d /tmp/goodix-d282-01-candidate.XXXXXX)
  chmod 0700 "$output"
  snapshot="$output/snapshot"
  mkdir -m 0700 "$snapshot"
  git -C "$root" archive "$approved" -- "${live_critical[@]}" | tar -x -C "$snapshot"
  build_candidate "$snapshot" "$output" "$rpm_dir"
  abi_preflight "$output"
  (cd "$output" && sha256sum libfprint-2.so.2.0.0 libgusb.so.2 \
    libopencv_core.so.413 libopencv_features2d.so.413 \
    libopencv_flann.so.413 libopencv_imgproc.so.413 >d282-01-artifacts.sha256)
  manifest_sha=$(sha256sum "$output/d282-01-artifacts.sha256" | awk '{print $1}')
  {
    echo "D282_01_BASELINE_SHA=$approved"
    echo "D282_01_OPERATION=$operation"
    echo "D282_01_CANDIDATE_DIR=$output"
    echo "D282_01_MANIFEST_SHA256=$manifest_sha"
    echo "D282_01_EXPECTED_GRANT_ID=d28201-$approved"
  } >"$output/d282-01-candidate.state"
  chmod 0600 "$output/d282-01-candidate.state" "$output/d282-01-artifacts.sha256"
  echo D282_01_CANDIDATE_PREPARED=true
  echo "CANDIDATE_DIRECTORY=$output"
  echo "CANDIDATE_BASELINE=$approved"
  echo AUTHORIZATION_CREATED=false
  echo GRANT_CREATED=false
  echo LIVE_EXECUTION_PERFORMED=false
}

validate_grant () {
  local grant=$1 baseline=$2 expected_id=$3 owner mode
  [[ -f $grant && ! -L $grant && $(wc -l <"$grant") -eq 4 ]] || refuse GRANT_FORMAT
  mode=$(stat -c %a "$grant") || refuse GRANT_STAT
  owner=$(stat -c %u "$grant") || refuse GRANT_STAT
  [[ $((8#$mode & 0177)) -eq 0 ]] || refuse GRANT_MODE
  [[ $owner -eq 0 || (${SUDO_UID:-x} =~ ^[0-9]+$ && $owner -eq $SUDO_UID) ]] || refuse GRANT_OWNER
  [[ $(state_value "$grant" D282_01_BASELINE_SHA) == "$baseline" ]] || refuse GRANT_BASELINE
  [[ $(state_value "$grant" D282_01_OPERATION) == "$operation" ]] || refuse GRANT_OPERATION
  [[ $(state_value "$grant" D282_01_GRANT_ID) == "$expected_id" ]] || refuse GRANT_ID
  validated_grant_user=$(state_value "$grant" D282_01_USER) || refuse GRANT_USER
  getent passwd "$validated_grant_user" >/dev/null || refuse GRANT_USER_UNKNOWN
  validated_grant_sha=$(sha256sum "$grant" | awk '{print $1}') || refuse GRANT_HASH
  validated_grant_owner=$owner
  validated_grant_mode=$mode
}

prepare_grant_claim () {
  local expected_id=$1 owner mode

  grant_claim_root=/var/tmp/goodix-d282-01-consumed-grants
  [[ ! -L $grant_claim_root ]] || refuse GRANT_CLAIM_ROOT_SYMLINK
  if [[ -e $grant_claim_root ]]; then
    [[ -d $grant_claim_root ]] || refuse GRANT_CLAIM_ROOT_UNSAFE
  else
    install -d -m 0700 "$grant_claim_root" || refuse GRANT_CLAIM_ROOT_CREATE
  fi
  owner=$(stat -c %u "$grant_claim_root") || refuse GRANT_CLAIM_ROOT_STAT
  mode=$(stat -c %a "$grant_claim_root") || refuse GRANT_CLAIM_ROOT_STAT
  [[ $owner -eq 0 && $mode == 700 ]] || refuse GRANT_CLAIM_ROOT_UNSAFE
  grant_claim="$grant_claim_root/$expected_id"
  [[ ! -e $grant_claim && ! -L $grant_claim ]] || refuse GRANT_ALREADY_CONSUMED
}

consume_validated_grant () {
  local grant=$1 owner mode current_sha

  [[ -f $grant && ! -L $grant ]] || refuse GRANT_CHANGED_AFTER_VALIDATION
  owner=$(stat -c %u "$grant") || refuse GRANT_CHANGED_AFTER_VALIDATION
  mode=$(stat -c %a "$grant") || refuse GRANT_CHANGED_AFTER_VALIDATION
  current_sha=$(sha256sum "$grant" | awk '{print $1}') || refuse GRANT_CHANGED_AFTER_VALIDATION
  [[ $owner == "$validated_grant_owner" && $mode == "$validated_grant_mode" &&
     $current_sha == "$validated_grant_sha" ]] || refuse GRANT_CHANGED_AFTER_VALIDATION
  mkdir -m 0700 "$grant_claim" 2>/dev/null || refuse GRANT_ALREADY_CONSUMED
  grant_consumed=true
  cp "$grant" "$grant_claim/consumed.state"
  chmod 0600 "$grant_claim/consumed.state"
}

validate_live_tooling () {
  local command_name

  for command_name in systemctl journalctl timeout tee fprintd-enroll \
    fprintd-verify fprintd-delete sha256sum stat getent sed cmp find \
    install readlink grep awk wc date head ls cp chmod mkdir rmdir rm \
    dirname ln; do
    command -v "$command_name" >/dev/null || refuse "HOST_TOOL_MISSING_${command_name}"
  done
  [[ -x $script_dir/d282_storage_inventory.py ]] || refuse STORAGE_INVENTORY_TOOL_INVALID
}

validate_selinux_preconditions () {
  local system_library=$1 storage_root=$2 enforcement reference label

  command -v getenforce >/dev/null || return 0
  enforcement=$(getenforce 2>/dev/null) || refuse SELINUX_STATE_UNREADABLE
  validated_selinux_enforcement=$enforcement
  case $enforcement in
    Disabled|Permissive) return 0 ;;
    Enforcing) ;;
    *) refuse SELINUX_STATE_UNRECOGNIZED ;;
  esac
  command -v chcon >/dev/null || refuse SELINUX_CHCON_MISSING
  command -v restorecon >/dev/null || refuse SELINUX_RESTORECON_MISSING
  reference=$storage_root
  [[ -e $reference ]] || reference=$(dirname "$storage_root")
  for reference in /usr/libexec/fprintd "$system_library" /run "$reference"; do
    label=$(ls -Zd -- "$reference" 2>/dev/null) || refuse SELINUX_REFERENCE_UNREADABLE
    [[ $label != \?* ]] || refuse SELINUX_REFERENCE_UNLABELED
  done
}

run_authorized_live () {
  local candidate=$1 grant=$2 state baseline manifest expected_id user stamp result private
  local runtime owned storage_root=/var/lib/fprint dropin=/run/systemd/system/fprintd.service.d/90-goodix-d282-01.conf
  local service_before unit_before unit_after daemon_pid raw audit_raw epoch_count enroll_count verify_count rc=1
  local system_library system_library_before system_library_after target_count since stored
  local observed_attempts consumed_action_count cleanup_epoch_count hidden_second_count
  local retry_count reopen_count reset_count clear_halt_count persistent_count
  local same_match_count different_no_match_count
  local storage_existed=false service_touched=false before_inventory_ready=false
  local unit_before_ready=false system_library_before_ready=false
  local staging_started=false
  [[ $EUID -eq 0 ]] || refuse LIVE_REQUIRES_ROOT
  state="$candidate/d282-01-candidate.state"
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -f $state && ! -L $candidate ]] || refuse CANDIDATE_INVALID
  baseline=$(state_value "$state" D282_01_BASELINE_SHA) || refuse CANDIDATE_STATE
  manifest=$(state_value "$state" D282_01_MANIFEST_SHA256) || refuse CANDIDATE_STATE
  expected_id=$(state_value "$state" D282_01_EXPECTED_GRANT_ID) || refuse CANDIDATE_STATE
  verify_baseline "$baseline"
  [[ $(sha256sum "$candidate/d282-01-artifacts.sha256" | awk '{print $1}') == "$manifest" ]] || refuse MANIFEST_DRIFT
  (cd "$candidate" && sha256sum -c d282-01-artifacts.sha256) || refuse ARTIFACT_DRIFT
  validate_grant "$grant" "$baseline" "$expected_id"
  user=$validated_grant_user
  validate_live_tooling
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  result="/var/tmp/goodix-d282-01-results/${stamp}-${baseline:0:12}"
  runtime="/run/goodix-d282-01/${stamp}-${baseline:0:12}"
  owned="$storage_root/.goodix-d282-01-${stamp}-${baseline:0:12}"
  [[ ! -e $runtime && ! -e $owned && ! -e $dropin ]] || refuse STAGING_COLLISION
  service_before=$(systemctl is-active fprintd.service 2>/dev/null || true)
  [[ $service_before == active || $service_before == inactive ]] || refuse FPRINTD_INITIAL_STATE_UNSAFE
  [[ -d $storage_root ]] && storage_existed=true
  system_library=$(readlink -f /usr/lib64/libfprint-2.so.2) || refuse SYSTEM_LIBFPRINT_MISSING
  [[ -f $system_library ]] || refuse SYSTEM_LIBFPRINT_MISSING
  system_library_before=$(sha256sum "$system_library" | awk '{print $1}') || refuse SYSTEM_LIBFPRINT_HASH_FAILED
  validate_selinux_preconditions "$system_library" "$storage_root"
  private="$result/private"
  install -d -m 0700 "$private" || refuse RESULT_DIRECTORY_CREATE_FAILED
  { echo D282_01_RESULT=FAIL_PENDING_AUDIT; echo "D282_01_BASELINE_SHA=$baseline"; } >"$result/summary.env" || refuse RESULT_SUMMARY_CREATE_FAILED
  chmod 0600 "$result/summary.env" || refuse RESULT_SUMMARY_MODE_FAILED
  cleanup_live () {
    local exit_status=$?
    local rollback=true service_rollback=true staging_rollback=true
    local storage_rollback=true unit_rollback=true library_rollback=true

    trap - EXIT INT TERM
    set +e
    if [[ $exit_status -ne 0 ]]; then
      rc=$exit_status
    fi
    if [[ $service_touched == true ]]; then
      systemctl stop fprintd.service >/dev/null 2>&1 || service_rollback=false
    fi
    if [[ $staging_started == true ]]; then
      if [[ -e $dropin || -L $dropin ]]; then
        rm -f -- "$dropin" || staging_rollback=false
      fi
      rmdir "$(dirname "$dropin")" 2>/dev/null || true
      if [[ $service_touched == true ]]; then
        systemctl daemon-reload >/dev/null 2>&1 || service_rollback=false
        if [[ $service_before == active ]]; then
          systemctl start fprintd.service >/dev/null 2>&1 || service_rollback=false
        fi
      fi
      if [[ -e $owned || -L $owned ]]; then
        find "$owned" -xdev -depth -delete 2>/dev/null || storage_rollback=false
      fi
      if [[ $storage_existed == false ]]; then
        rmdir "$storage_root" 2>/dev/null || storage_rollback=false
      fi
      if [[ -e $runtime || -L $runtime ]]; then
        find "$runtime" -xdev -depth -delete 2>/dev/null || staging_rollback=false
      fi
    fi
    if [[ $before_inventory_ready == true ]]; then
      "$script_dir/d282_storage_inventory.py" "$storage_root" "$private/storage.after.json" \
        --exclude-name "${owned##*/}" >"$private/storage.after.env" || storage_rollback=false
      cmp -s "$private/storage.before.json" "$private/storage.after.json" || storage_rollback=false
    fi
    if [[ $unit_before_ready == true ]]; then
      systemctl cat fprintd.service >"$private/unit.after" 2>/dev/null || unit_rollback=false
      unit_after=$(sha256sum "$private/unit.after" 2>/dev/null | awk '{print $1}')
      [[ $unit_after == "$unit_before" ]] || unit_rollback=false
    fi
    if [[ $system_library_before_ready == true ]]; then
      system_library_after=$(sha256sum "$system_library" 2>/dev/null | awk '{print $1}')
      [[ $system_library_after == "$system_library_before" ]] || library_rollback=false
    fi
    [[ $service_rollback == true && $staging_rollback == true &&
       $storage_rollback == true && $unit_rollback == true &&
       $library_rollback == true ]] || rollback=false
    if [[ $rollback != true ]]; then
      sed -i 's/^D282_01_RESULT=.*/D282_01_RESULT=FAIL_ROLLBACK/' \
        "$result/summary.env"
    elif [[ $rc -ne 0 ]]; then
      sed -i 's/^D282_01_RESULT=.*/D282_01_RESULT=FAIL_ACTION_OR_AUDIT/' \
        "$result/summary.env"
    fi
    echo "SERVICE_STATE_RESTORED=$service_rollback" >>"$result/summary.env"
    echo "STAGING_REMOVED=$staging_rollback" >>"$result/summary.env"
    echo "SYSTEM_LIBFPRINT_UNCHANGED=$library_rollback" >>"$result/summary.env"
    echo "RUN_RETURN_CODE=$rc" >>"$result/summary.env"
    echo "GRANT_CONSUMED=$grant_consumed" >>"$result/summary.env"
    echo "RETRY_AUTHORIZED=false" >>"$result/summary.env"
    echo "ROLLBACK_COMPLETE=$rollback" >>"$result/summary.env"
    echo "PREEXISTING_STORAGE_UNCHANGED=$storage_rollback" >>"$result/summary.env"
    echo "REAL_USB_ENUMERATION_ATTEMPTED=$real_usb_enumeration_attempted" >>"$result/summary.env"
    echo "LIVE_EXECUTION_PERFORMED=$live_execution_performed" >>"$result/summary.env"
    [[ $rollback == true ]] || echo "RECOVERY_REQUIRED=Non eseguire altre action; ripristinare fprintd e conservare private/." >&2
  }
  trap cleanup_live EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  since=$(date --iso-8601=seconds) || refuse HOST_CLOCK_FAILED
  systemctl cat fprintd.service >"$private/unit.before" || refuse UNIT_SNAPSHOT_FAILED
  unit_before=$(sha256sum "$private/unit.before" | awk '{print $1}') || refuse UNIT_SNAPSHOT_HASH_FAILED
  unit_before_ready=true
  "$script_dir/d282_storage_inventory.py" "$storage_root" "$private/storage.before.json" \
    --exclude-name "${owned##*/}" >"$private/storage.before.env" || refuse STORAGE_INVENTORY_FAILED
  before_inventory_ready=true
  system_library_before_ready=true
  prepare_grant_claim "$expected_id"
  consume_validated_grant "$grant"
  staging_started=true
  install -d -m 0700 "$runtime" "$owned" "$(dirname "$dropin")"
  install -m 0600 "$candidate/libfprint-2.so.2.0.0" \
    "$candidate/libgusb.so.2" \
    "$candidate/libopencv_core.so.413" \
    "$candidate/libopencv_features2d.so.413" \
    "$candidate/libopencv_flann.so.413" \
    "$candidate/libopencv_imgproc.so.413" "$runtime/"
  ln -s libfprint-2.so.2.0.0 "$runtime/libfprint-2.so.2"
  ln -s libfprint-2.so.2 "$runtime/libfprint-2.so"
  printf '#!/bin/sh\nexport LD_LIBRARY_PATH=%s\nexport STATE_DIRECTORY=%s\nexport FP_DRIVERS_ALLOWLIST=goodix_27c6_5125\nexec /usr/libexec/fprintd\n' \
    "$runtime" "$owned" >"$runtime/launch-fprintd"
  chmod 0700 "$runtime/launch-fprintd"
  if [[ $validated_selinux_enforcement == Enforcing ]]; then
    chcon --reference=/usr/libexec/fprintd "$runtime/launch-fprintd"
    for raw in "$runtime"/*.so.*; do chcon --reference=/usr/lib64/libfprint-2.so.2 "$raw"; done
    restorecon -RF "$owned"
  fi
  printf '[Service]\nExecStart=\nExecStart=%s/launch-fprintd\n' "$runtime" >"$dropin"
  chmod 0600 "$dropin"
  service_touched=true
  systemctl stop fprintd.service
  systemctl daemon-reload
  real_usb_enumeration_attempted=true
  live_execution_performed=true
  systemctl start fprintd.service
  target_count=0
  for raw in /sys/bus/usb/devices/*/idVendor; do
    [[ -f $raw && $(<"$raw") == 27c6 && -f ${raw%/idVendor}/idProduct && $(<"${raw%/idVendor}/idProduct") == 5125 ]] && ((target_count+=1))
  done
  [[ $target_count -eq 1 ]] || refuse TARGET_CARDINALITY_NOT_ONE
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse DAEMON_PID_INVALID
  grep -F "$runtime/libfprint-2.so.2.0.0" "/proc/$daemon_pid/maps" >"$private/maps"
  [[ $(readlink "/proc/$daemon_pid/exe") == /usr/libexec/fprintd ]] || refuse DAEMON_EXE_DRIFT
  echo EXACT_LIBRARY_MAP_VERIFIED=true >"$result/operator.log"
  echo "PHASE_A=Enrollment indice destro: otto contatti, nessuna ripetizione extra."
  raw="$private/enroll.raw"
  set +e; timeout --signal=INT --kill-after=20s 1060s fprintd-enroll -f right-index-finger "$user" 2>&1 | tee "$raw"; rc=${PIPESTATUS[0]}; set -e
  [[ $rc -eq 0 && $(grep -c '^Enroll result: enroll-completed$' "$raw") -eq 1 ]] || return 1
  [[ $(find "$owned" -type l | wc -l) -eq 0 ]] || return 1
  [[ $(find "$owned" -type f | wc -l) -eq 1 ]] || return 1
  stored=$(find "$owned" -type f -print)
  [[ $(head -c 3 "$stored") == FP3 ]] || return 1
  systemctl restart fprintd.service
  echo DAEMON_RESTART_COUNT=1 >>"$result/operator.log"
  echo "PHASE_A=Verify stesso indice destro: un solo contatto."
  raw="$private/verify-same.raw"
  set +e; timeout --signal=INT --kill-after=20s 180s fprintd-verify "$user" 2>&1 | tee "$raw"; rc=${PIPESTATUS[0]}; set -e
  [[ $rc -eq 0 && $(grep -c '^Verify result: verify-match (done)$' "$raw") -eq 1 ]] || return 1
  journalctl -u fprintd.service --since "$since" --no-pager >"$private/phase-a-journal.raw"
  grep 'GOODIX_D282_EPOCH_AUDIT' "$private/phase-a-journal.raw" >"$private/phase-a-audit.raw"
  [[ $(wc -l <"$private/phase-a-audit.raw") -eq 2 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_ENROLL.*attempts=1 rejected=0 consumed=1 tls=1' "$private/phase-a-audit.raw") -eq 1 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_VERIFY.*attempts=1 rejected=0 consumed=1 tls=1.*first_image=1 release_tail=1 single_terminal=1 rearm32=0' "$private/phase-a-audit.raw") -eq 1 ]] || return 1
  echo "PHASE_B=Verify dito diverso (indice sinistro): un solo contatto; atteso no-match."
  raw="$private/verify-different.raw"
  set +e; timeout --signal=INT --kill-after=20s 180s fprintd-verify "$user" 2>&1 | tee "$raw"; rc=${PIPESTATUS[0]}; set -e
  [[ $rc -eq 1 && $(grep -c '^Verify result: verify-no-match (done)$' "$raw") -eq 1 ]] || return 1
  journalctl -u fprintd.service --since "$since" --no-pager >"$private/phase-b-journal.raw"
  grep 'GOODIX_D282_EPOCH_AUDIT' "$private/phase-b-journal.raw" >"$private/phase-b-audit.raw"
  [[ $(wc -l <"$private/phase-b-audit.raw") -eq 3 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_VERIFY.*attempts=1 rejected=0 consumed=1 tls=1.*first_image=1 release_tail=1 single_terminal=1 rearm32=0' "$private/phase-b-audit.raw") -eq 2 ]] || return 1
  echo "PHASE_C=Delete del solo storage D282 isolato."
  fprintd-delete "$user" >"$private/delete.raw" 2>&1
  [[ $(find "$owned" -type f | wc -l) -eq 0 ]] || return 1
  journalctl -u fprintd.service --since "$since" --no-pager >"$private/journal.raw"
  grep 'GOODIX_D282_EPOCH_AUDIT' "$private/journal.raw" >"$private/audit.raw"
  epoch_count=$(wc -l <"$private/audit.raw")
  enroll_count=$(grep -c 'action=FPI_DEVICE_ACTION_ENROLL' "$private/audit.raw")
  verify_count=$(grep -c 'action=FPI_DEVICE_ACTION_VERIFY' "$private/audit.raw")
  cleanup_epoch_count=$(grep -c 'action=FPI_DEVICE_ACTION_NONE.*attempts=0 rejected=0 consumed=0 tls=0' "$private/audit.raw")
  consumed_action_count=$(grep -c 'consumed=1' "$private/audit.raw")
  observed_attempts=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^attempts=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$private/audit.raw")
  hidden_second_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^rejected=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$private/audit.raw")
  retry_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^(secure_retry|post_retry)=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$private/audit.raw")
  reopen_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^reopen=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$private/audit.raw")
  reset_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^reset=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$private/audit.raw")
  clear_halt_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^clear_halt=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$private/audit.raw")
  persistent_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^persistent=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$private/audit.raw")
  same_match_count=$(grep -c '^Verify result: verify-match (done)$' "$private/verify-same.raw")
  different_no_match_count=$(grep -c '^Verify result: verify-no-match (done)$' "$private/verify-different.raw")
  [[ $epoch_count -eq 4 && $enroll_count -eq 1 && $verify_count -eq 2 &&
     $cleanup_epoch_count -eq 1 && $consumed_action_count -eq 3 &&
     $observed_attempts -eq 3 && $hidden_second_count -eq 0 &&
     $retry_count -eq 0 && $reopen_count -eq 0 && $reset_count -eq 0 &&
     $clear_halt_count -eq 0 && $persistent_count -eq 0 &&
     $same_match_count -eq 1 && $different_no_match_count -eq 1 ]] || return 1
  [[ $(grep -c 'attempts=1 rejected=0 consumed=1 tls=1' "$private/audit.raw") -eq 3 ]] || return 1
  [[ $(grep -c 'secure_retry=0 post_retry=0 reopen=0 reset=0 clear_halt=0' "$private/audit.raw") -eq 4 ]] || return 1
  [[ $(grep -c 'persistent=0' "$private/audit.raw") -eq 4 ]] || return 1
  [[ $(grep -c 'outstanding=0 drained=1 context_closed=1' "$private/audit.raw") -eq 4 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_VERIFY.*first_image=1 release_tail=1 single_terminal=1 rearm32=0' "$private/audit.raw") -eq 2 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_ENROLL.*enroll_stages=8 enroll_rearm32=7 enroll_terminal=1' "$private/audit.raw") -eq 1 ]] || return 1
  sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" "$private"/*.raw >>"$result/operator.log"
  {
    echo D282_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
    echo "D282_01_BASELINE_SHA=$baseline"
    echo AUTHORIZED_BIOMETRIC_ACTION_MAX=3
    echo "OPEN_EPOCH_COUNT=$epoch_count"
    echo "ACTION_ATTEMPT_COUNT=$observed_attempts"
    echo "CONSUMED_BIOMETRIC_ACTION_COUNT=$consumed_action_count"
    echo "HOST_ONLY_DELETE_OPEN_EPOCH_COUNT=$cleanup_epoch_count"
    echo "ENROLL_ACTION_COUNT=$enroll_count"
    echo "VERIFY_ACTION_COUNT=$verify_count"
    echo "SECOND_SENSOR_REACHING_ACTION_COUNT=$hidden_second_count"
    echo RETRY_AUTHORIZED=false
    echo "OBSERVED_RETRY_COUNT=$retry_count"
    echo "HIDDEN_REOPEN_COUNT=$reopen_count"
    echo "RESET_COUNT=$reset_count"
    echo "CLEAR_HALT_COUNT=$clear_halt_count"
    echo "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=$persistent_count"
    echo "SAME_FINGER_MATCH_COUNT=$same_match_count"
    echo "DIFFERENT_FINGER_NO_MATCH_COUNT=$different_no_match_count"
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
    echo PAM_IN_SCOPE=false
  } >"$result/summary.env"
  chmod 0600 "$result/operator.log" "$result/summary.env"
  rc=0
  echo "RISULTATI=$result"
  echo GRANT_CONSUMED=true
  echo RETRY_AUTHORIZED=false
  return 0
}

export_results () {
  local result=$1 export name source_sha copy_sha
  [[ $EUID -eq 0 && ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]] || refuse EXPORT_CALLER
  [[ $result == /var/tmp/goodix-d282-01-results/* && -d $result/private ]] || refuse EXPORT_SOURCE
  export=$(mktemp -d /tmp/goodix-d282-01-export.XXXXXX); chmod 0700 "$export"
  for name in operator.log summary.env; do
    source_sha=$(sha256sum "$result/$name" | awk '{print $1}')
    install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" "$result/$name" "$export/$name"
    copy_sha=$(sha256sum "$export/$name" | awk '{print $1}')
    [[ $source_sha == "$copy_sha" ]] || refuse EXPORT_HASH
    echo "${name}_SHA256=$source_sha"
  done
  chown "$SUDO_UID:$SUDO_GID" "$export"
  echo D282_01_RESULTS_EXPORT=PASS_BYTE_IDENTICAL
  echo "EXPORT_DIRECTORY=$export"
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
}

case ${1:-} in
  --offline-preflight) [[ $# -eq 2 ]] || refuse USAGE; offline_preflight "$2" ;;
  --prepare-candidate) [[ $# -eq 3 ]] || refuse USAGE; prepare_candidate "$2" "$3" ;;
  --run-authorized-live) [[ $# -eq 4 && $3 == --grant ]] || refuse USAGE; run_authorized_live "$2" "$4" ;;
  --export-results) [[ $# -eq 2 ]] || refuse USAGE; export_results "$2" ;;
  *) echo "Uso: $0 --offline-preflight <opencv-rpm-dir> | --prepare-candidate <SHA> <opencv-rpm-dir> | --run-authorized-live <candidate> --grant <grant> | --export-results <results>" >&2; exit 2 ;;
esac
