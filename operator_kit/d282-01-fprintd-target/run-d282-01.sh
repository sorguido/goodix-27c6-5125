#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
operation=D282_01_FPRINTD_TARGET_ENROLL_RESTART_VERIFY_SAME_DIFFERENT_DELETE
staging_probe_operation=D282_01_PRIVILEGED_SYSTEMD_SELINUX_STAGING_PROBE
real_usb_enumeration_attempted=false
real_sensor_accessed=false
live_execution_performed=false
staging_probe_execution_performed=false
staging_probe_mode=false
grant_consumed=false
target_preconsumption_match_count=UNSET
d282_offline_work=
validated_grant_user=
validated_grant_sha=
validated_grant_owner=
validated_grant_mode=
grant_claim_root=
grant_claim=
validated_selinux_enforcement=Unavailable
live_result=
live_private=
live_runtime=
live_owned=
live_storage_root=/var/lib/fprint
live_dropin=/run/systemd/system/fprintd.service.d/90-goodix-d282-01.conf
live_service_before=unknown
live_unit_before=
live_system_library=
live_system_library_before=
live_storage_existed=false
live_before_inventory_ready=false
live_unit_before_ready=false
live_system_library_before_ready=false
live_staging_started=false
live_service_touched=false
live_cleanup_armed=false
live_cleanup_test_mode=false
live_run_return_code=1
live_critical=(libfprint-driver reference/libfprint-fedora44-1.94.100/source
  reference/fprintd-fedora44-1.94.5 Rockytkg analysis/D282
  operator_kit/d282-01-fprintd-target
  operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256)
staging_probe_critical=(reference/libfprint-fedora44-1.94.100/source
  reference/fprintd-fedora44-1.94.5
  analysis/D281/d281_01_disable_usb_context.patch analysis/D282
  libfprint-driver Rockytkg
  operator_kit/d282-01-fprintd-target)

refuse () {
  echo "D282_01_GATE_REFUSED=true" >&2
  echo "D282_01_REFUSAL_REASON=$1" >&2
  echo "GRANT_CONSUMED=$grant_consumed" >&2
  echo "RETRY_AUTHORIZED=false" >&2
  echo "TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count" >&2
  echo "REAL_USB_ENUMERATION_ATTEMPTED=$real_usb_enumeration_attempted" >&2
  echo "REAL_SENSOR_ACCESSED=$real_sensor_accessed" >&2
  echo "LIVE_EXECUTION_PERFORMED=$live_execution_performed" >&2
  echo "STAGING_PROBE_EXECUTION_PERFORMED=$staging_probe_execution_performed" >&2
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

cleanup_live () {
  local exit_status=$?
  local rollback=true service_rollback=true service_state_restored=true
  local staging_rollback=true
  local storage_rollback=true unit_rollback=true library_rollback=true
  local recovery_required=false service_final_state=$live_service_before
  local unit_after= system_library_after=

  trap - EXIT INT TERM
  set +e
  if [[ $live_cleanup_armed != true ]]; then
    return 0
  fi
  live_cleanup_armed=false
  if [[ $exit_status -ne 0 ]]; then
    live_run_return_code=$exit_status
  fi
  if [[ $live_service_touched == true ]]; then
    systemctl stop fprintd.service >/dev/null 2>&1 || service_rollback=false
  fi
  if [[ $live_staging_started == true ]]; then
    if [[ -e $live_dropin || -L $live_dropin ]]; then
      rm -f -- "$live_dropin" || staging_rollback=false
    fi
    rmdir "$(dirname "$live_dropin")" 2>/dev/null || true
    if [[ $live_service_touched == true ]]; then
      systemctl daemon-reload >/dev/null 2>&1 || service_rollback=false
      if [[ $live_service_before == active ]]; then
        systemctl start fprintd.service >/dev/null 2>&1 || service_rollback=false
      fi
    fi
    if [[ -e $live_owned || -L $live_owned ]]; then
      find "$live_owned" -xdev -depth -delete 2>/dev/null || storage_rollback=false
    fi
    if [[ $live_storage_existed == false ]]; then
      rmdir "$live_storage_root" 2>/dev/null || storage_rollback=false
    fi
    if [[ -e $live_runtime || -L $live_runtime ]]; then
      find "$live_runtime" -xdev -depth -delete 2>/dev/null || staging_rollback=false
    fi
  fi
  if [[ $live_before_inventory_ready == true ]]; then
    "$script_dir/d282_storage_inventory.py" "$live_storage_root" \
      "$live_private/storage.after.json" \
      --exclude-name "${live_owned##*/}" >"$live_private/storage.after.env" ||
      storage_rollback=false
    cmp -s "$live_private/storage.before.json" \
      "$live_private/storage.after.json" || storage_rollback=false
  fi
  if [[ $live_unit_before_ready == true ]]; then
    systemctl cat fprintd.service >"$live_private/unit.after" 2>/dev/null ||
      unit_rollback=false
    unit_after=$(sha256sum "$live_private/unit.after" 2>/dev/null | awk '{print $1}')
    [[ $unit_after == "$live_unit_before" ]] || unit_rollback=false
  fi
  if [[ $live_system_library_before_ready == true ]]; then
    system_library_after=$(sha256sum "$live_system_library" 2>/dev/null |
      awk '{print $1}')
    [[ $system_library_after == "$live_system_library_before" ]] ||
      library_rollback=false
  fi
  if [[ $staging_probe_mode == true ]]; then
    service_final_state=$(systemctl is-active fprintd.service 2>/dev/null || true)
    [[ $service_final_state == active || $service_final_state == inactive ]] ||
      service_state_restored=false
    [[ $service_final_state == "$live_service_before" ]] ||
      service_state_restored=false
  fi
  [[ $service_rollback == true && $staging_rollback == true &&
     $storage_rollback == true && $unit_rollback == true &&
     $library_rollback == true ]] || rollback=false
  if [[ $staging_probe_mode == true && $service_state_restored != true ]]; then
    rollback=false
  fi
  [[ $rollback == true ]] || recovery_required=true
  if [[ $rollback != true ]]; then
    sed -i 's/^D282_01_RESULT=.*/D282_01_RESULT=FAIL_ROLLBACK/' \
      "$live_result/summary.env"
  elif [[ $live_run_return_code -ne 0 ]]; then
    sed -i 's/^D282_01_RESULT=.*/D282_01_RESULT=FAIL_ACTION_OR_AUDIT/' \
      "$live_result/summary.env"
  elif [[ $staging_probe_execution_performed == true ]]; then
    sed -i 's/^D282_01_RESULT=.*/D282_01_RESULT=PASS_STAGING_PROBE/' \
      "$live_result/summary.env"
  fi
  if [[ $staging_probe_mode == true ]]; then
    echo "SERVICE_CLEANUP_COMMANDS_SUCCEEDED=$service_rollback" >>"$live_result/summary.env"
    echo "SERVICE_STATE_RESTORED=$service_state_restored" >>"$live_result/summary.env"
    echo "SERVICE_INITIAL_STATE=$live_service_before" >>"$live_result/summary.env"
    echo "SERVICE_FINAL_STATE=$service_final_state" >>"$live_result/summary.env"
  else
    echo "SERVICE_STATE_RESTORED=$service_rollback" >>"$live_result/summary.env"
  fi
  echo "STAGING_REMOVED=$staging_rollback" >>"$live_result/summary.env"
  echo "SYSTEM_LIBFPRINT_UNCHANGED=$library_rollback" >>"$live_result/summary.env"
  echo "RUN_RETURN_CODE=$live_run_return_code" >>"$live_result/summary.env"
  echo "GRANT_CONSUMED=$grant_consumed" >>"$live_result/summary.env"
  echo "RETRY_AUTHORIZED=false" >>"$live_result/summary.env"
  echo "ROLLBACK_COMPLETE=$rollback" >>"$live_result/summary.env"
  echo "PREEXISTING_STORAGE_UNCHANGED=$storage_rollback" >>"$live_result/summary.env"
  echo "REAL_USB_ENUMERATION_ATTEMPTED=$real_usb_enumeration_attempted" >>"$live_result/summary.env"
  echo "REAL_SENSOR_ACCESSED=$real_sensor_accessed" >>"$live_result/summary.env"
  echo "LIVE_EXECUTION_PERFORMED=$live_execution_performed" >>"$live_result/summary.env"
  echo "STAGING_PROBE_EXECUTION_PERFORMED=$staging_probe_execution_performed" >>"$live_result/summary.env"
  if [[ $staging_probe_mode == true ]]; then
    echo "RECOVERY_REQUIRED=$recovery_required" >>"$live_result/summary.env"
  fi
  if [[ $rollback != true ]]; then
    echo "RECOVERY_REQUIRED=Non eseguire altre action; ripristinare fprintd e conservare private/." >&2
  fi
  if [[ $live_cleanup_test_mode == true ]]; then
    echo EXIT_TRAP_LOCAL_SCOPE_REGRESSION=PASS
    echo UNBOUND_VARIABLE_DURING_CLEANUP=false
    echo "ROLLBACK_COMPLETE=$rollback"
  fi
  return 0
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

verify_staging_probe_baseline () {
  local approved=$1
  is_sha "$approved" || refuse INVALID_BASELINE
  [[ $(git -C "$root" branch --show-current) == development ]] ||
    refuse WRONG_BRANCH
  [[ $(git -C "$root" rev-parse HEAD) == "$approved" ]] ||
    refuse HEAD_MISMATCH
  [[ $(git -C "$root" rev-parse origin/development) == "$approved" ]] ||
    refuse ORIGIN_DEVELOPMENT_MISMATCH
  [[ -z $(git -C "$root" status --porcelain --untracked-files=all -- \
    "${staging_probe_critical[@]}") ]] || refuse STAGING_PROBE_CRITICAL_DIRTY
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

build_staging_probe_candidate () {
  local source_root=$1 output=$2 input source_copy build pkgconfig gusb
  input="$output/input"
  source_copy="$input/reference/libfprint-fedora44-1.94.100/source"
  build="$output/build"
  pkgconfig="$output/pkgconfig"
  install -d -m 0700 "$output" "$pkgconfig" "$(dirname "$source_copy")"
  cp -a "$source_root/reference/libfprint-fedora44-1.94.100/source" \
    "$source_copy"
  ln -s "$source_root/libfprint-driver" "$input/libfprint-driver"
  ln -s "$source_root/Rockytkg" "$input/Rockytkg"
  patch -p1 -d "$source_copy" < \
    "$source_root/analysis/D281/d281_01_disable_usb_context.patch"
  gusb=$(find_gusb) || refuse HOST_GUSB_MISSING
  cp "$gusb" "$pkgconfig/libgusb.so.2"
  sed -e "s|@PREFIX@|$pkgconfig|g" \
      -e "s|@INCLUDEDIR@|$source_root/libfprint-driver/tests/support/d277|g" \
      "$source_root/libfprint-driver/tests/support/d279/gusb.pc.in" \
      >"$pkgconfig/gusb.pc"
  flatpak run --user --unshare=network \
    --filesystem="$source_root:ro" --filesystem="$output" \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$source_root/operator_kit/d282-01-fprintd-target/build-staging-probe-inner.sh" \
    "$source_copy" "$build" "$pkgconfig" "$output" \
    >"$output/staging-probe-build.env"
  cp "$pkgconfig/libgusb.so.2" "$output/libgusb.so.2"
  chmod 0600 "$output/libgusb.so.2" "$output/staging-probe-build.env"
  find "$input" "$build" "$output/install" "$pkgconfig" -depth -delete
}

audit_staging_probe_candidate () {
  local candidate=$1 library
  library="$candidate/libfprint-2.so.2.0.0"

  [[ -f $library && ! -L $library ]] || refuse STAGING_PROBE_LIBRARY_INVALID
  grep -Fx 'D282_01_STAGING_PROBE_DRIVER=virtual_image' \
    "$candidate/staging-probe-build.env" >/dev/null ||
    refuse STAGING_PROBE_DRIVER_INVALID
  grep -Fx 'D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED=true' \
    "$candidate/staging-probe-build.env" >/dev/null ||
    refuse STAGING_PROBE_USB_NOT_DISABLED
  grep -Fx 'D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT=false' \
    "$candidate/staging-probe-build.env" >/dev/null ||
    refuse STAGING_PROBE_GOODIX_PRESENT
  if nm -D "$library" | grep -Eq 'g_usb_context_(new|enumerate)'; then
    refuse STAGING_PROBE_USB_CONTEXT_SYMBOL_PRESENT
  fi
  if nm "$library" | grep -Eq \
    'fpi_device_goodix_27c6_5125|get_tls_client_secret|goodix_secure'; then
    refuse STAGING_PROBE_GOODIX_TLS_SYMBOL_PRESENT
  fi
  if strings "$library" | grep -F 'goodix_27c6_5125' >/dev/null; then
    refuse STAGING_PROBE_GOODIX_DRIVER_PRESENT
  fi
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
  sh -n "$script_dir/build-staging-probe-inner.sh"
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
  build_staging_probe_candidate "$root" "$d282_offline_work/staging-probe"
  abi_preflight "$d282_offline_work/staging-probe"
  audit_staging_probe_candidate "$d282_offline_work/staging-probe"
  echo D282_01_OFFLINE_PREFLIGHT=PASS
  echo D282_01_FPRINTD_EXACT_SOURCE_AUDIT=PASS
  echo D282_01_TEST_MATRIX_COUNT=58
  echo D282_01_NORMAL_AND_ASAN_UBSAN=PASS
  echo D282_01_REVERSIBLE_STAGING_MODEL=PASS
  echo D282_01_PREEXISTING_STORAGE_MODEL=PASS
  echo D282_01_GRANT_ORDERING_CORRECTIVE=PASS
  echo D282_01_TARGET_CARDINALITY_PRECONSUMPTION_GATE=PASS
  echo D282_01_TARGET_ABSENT_PRECONSUMPTION_REFUSAL=PASS
  echo D282_01_TARGET_MULTIPLE_PRECONSUMPTION_REFUSAL=PASS
  echo D282_01_TARGET_EXACT_ONE_PRECONSUMPTION_ACCEPTED=PASS
  echo D282_01_ENROLLMENT_IMPLICIT_RETRY_FENCE=PASS
  echo ENROLLMENT_EXTRACTION_FAILURE=TERMINAL_FAIL_CLOSED
  echo PRECONSUMPTION_REFUSALS_LEAVE_GRANT_UNUSED=true
  echo POSTCONSUMPTION_FAILURE_RETRY_AUTHORIZED=false
  echo EXTRA_ENROLLMENT_CONTACT_REQUESTED=false
  echo EXTRA_ENROLLMENT_REARM_COUNT=0
  echo ENROLLMENT_RETRY_CALLBACK_COUNT=0
  echo CORRUPT_FP3_REJECTED=PASS_OFFLINE
  echo MISSING_FP3_REJECTED=PASS_OFFLINE
  echo WRONG_USER_FINGER_REJECTED=PASS_OFFLINE
  echo D282_01_ATTEMPT_01=FAIL_HOST_STAGING_CLOSED
  echo D282_01_ATTEMPT_01_GRANT_CONSUMED=true
  echo D282_01_ATTEMPT_01_RETRY_AUTHORIZED=false
  echo D282_01_EXIT_TRAP_SCOPE_CORRECTIVE=PASS
  echo EXIT_TRAP_LOCAL_SCOPE_REGRESSION=PASS
  echo UNBOUND_VARIABLE_DURING_CLEANUP=false
  echo D282_01_SYSTEMD_DIRECT_EXEC_DESIGN=PASS_OFFLINE_STATIC_AND_SYSTEMD_PARSER
  echo D282_01_SYSTEMD_SELINUX_STAGING_CORRECTIVE=IMPLEMENTED_PENDING_PRIVILEGED_HOST_TEST
  echo FPRINTD_SYSTEMD_STAGING_START=NOT_RUN
  echo SELINUX_EXEC_DENIAL=NOT_PROVEN_CORRECTED
  echo EXEC_MAIN_STATUS=NOT_OBSERVED_FOR_CORRECTIVE
  echo EXACT_LIBRARY_MAP_VERIFIED=NOT_OBSERVED_FOR_CORRECTIVE
  echo D282_01_PRIVILEGED_STAGING_PROBE_READY=true
  echo D282_01_PRIVILEGED_STAGING_PROBE_EXECUTED=false
  echo D282_01_PRIVILEGED_STAGING_PROBE_AUTHORIZED=false
  echo D282_01_PRIVILEGED_STAGING_PROBE_SERVICE_STATE_CORRECTIVE=PASS
  echo MANUAL_PRESTOP_REQUIRED=false
  echo PROBE_INITIAL_ACTIVE_ACCEPTED=true
  echo PROBE_INITIAL_INACTIVE_ACCEPTED=true
  echo ACTIVE_SUCCESS_FINAL_ACTIVE=PASS
  echo ACTIVE_FAILURE_FINAL_ACTIVE=PASS
  echo INACTIVE_SUCCESS_FINAL_INACTIVE=PASS
  echo INACTIVE_FAILURE_FINAL_INACTIVE=PASS
  echo D282_01_STAGING_PROBE_OPERATION="$staging_probe_operation"
  echo D282_01_STAGING_PROBE_DRIVER=virtual_image
  echo D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED=true
  echo D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT=false
  echo REAL_SENSOR_ACCESSED=false
  echo D282_01_HUMAN_GATE_READINESS=NOT_READY
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

prepare_staging_probe_candidate () {
  local approved=$1 output snapshot manifest_sha
  [[ $EUID -ne 0 ]] || refuse PREPARE_MUST_BE_UNPRIVILEGED
  verify_staging_probe_baseline "$approved"
  output=$(mktemp -d /tmp/goodix-d282-01-staging-probe-candidate.XXXXXX)
  chmod 0700 "$output"
  snapshot="$output/snapshot"
  mkdir -m 0700 "$snapshot"
  git -C "$root" archive "$approved" -- "${staging_probe_critical[@]}" |
    tar -x -C "$snapshot"
  build_staging_probe_candidate "$snapshot" "$output"
  abi_preflight "$output"
  audit_staging_probe_candidate "$output"
  (cd "$output" && sha256sum libfprint-2.so.2.0.0 libgusb.so.2 \
    staging-probe-build.env >d282-01-staging-probe-artifacts.sha256)
  manifest_sha=$(sha256sum \
    "$output/d282-01-staging-probe-artifacts.sha256" | awk '{print $1}')
  {
    echo "D282_01_STAGING_PROBE_BASELINE_SHA=$approved"
    echo "D282_01_STAGING_PROBE_OPERATION=$staging_probe_operation"
    echo "D282_01_STAGING_PROBE_CANDIDATE_DIR=$output"
    echo "D282_01_STAGING_PROBE_MANIFEST_SHA256=$manifest_sha"
    echo "D282_01_STAGING_PROBE_EXPECTED_GRANT_ID=d28201-staging-probe-$approved"
    echo D282_01_STAGING_PROBE_DRIVER=virtual_image
    echo D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED=true
    echo D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT=false
  } >"$output/d282-01-staging-probe-candidate.state"
  chmod 0600 "$output/d282-01-staging-probe-candidate.state" \
    "$output/d282-01-staging-probe-artifacts.sha256"
  echo D282_01_STAGING_PROBE_CANDIDATE_PREPARED=true
  echo "STAGING_PROBE_CANDIDATE_DIRECTORY=$output"
  echo "STAGING_PROBE_CANDIDATE_BASELINE=$approved"
  echo "D282_01_STAGING_PROBE_OPERATION=$staging_probe_operation"
  echo AUTHORIZATION_CREATED=false
  echo GRANT_CREATED=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo LIVE_EXECUTION_PERFORMED=false
}

count_goodix_targets () {
  local sysfs_root=$1 vendor_file product_file count=0

  for vendor_file in "$sysfs_root"/*/idVendor; do
    product_file=${vendor_file%/idVendor}/idProduct
    if [[ -f $vendor_file && -f $product_file &&
          $(<"$vendor_file") == 27c6 && $(<"$product_file") == 5125 ]]; then
      ((count+=1))
    fi
  done
  printf '%u\n' "$count"
}

validate_grant () {
  local grant=$1 baseline=$2 expected_id=$3 expected_operation=$4 owner mode
  [[ -f $grant && ! -L $grant && $(wc -l <"$grant") -eq 4 ]] || refuse GRANT_FORMAT
  mode=$(stat -c %a "$grant") || refuse GRANT_STAT
  owner=$(stat -c %u "$grant") || refuse GRANT_STAT
  [[ $((8#$mode & 0177)) -eq 0 ]] || refuse GRANT_MODE
  [[ $owner -eq 0 || (${SUDO_UID:-x} =~ ^[0-9]+$ && $owner -eq $SUDO_UID) ]] || refuse GRANT_OWNER
  [[ $(state_value "$grant" D282_01_BASELINE_SHA) == "$baseline" ]] || refuse GRANT_BASELINE
  [[ $(state_value "$grant" D282_01_OPERATION) == "$expected_operation" ]] ||
    refuse GRANT_OPERATION
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

validate_staging_probe_tooling () {
  local command_name

  for command_name in systemctl journalctl sha256sum stat getent sed cmp find \
    install readlink grep awk wc date ls cp chmod mkdir rmdir rm dirname ln \
    nm strings sort tr; do
    command -v "$command_name" >/dev/null ||
      refuse "HOST_TOOL_MISSING_${command_name}"
  done
  [[ -x $script_dir/d282_storage_inventory.py ]] ||
    refuse STORAGE_INVENTORY_TOOL_INVALID
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

write_systemd_dropin () {
  local runtime=$1 owned=$2 dropin=$3 profile=$4 relative_state allowlist

  [[ $runtime == /run/goodix-d282-01/* ]] || refuse RUNTIME_PATH_UNSAFE
  [[ $owned == /var/lib/fprint/.goodix-d282-01-* ]] ||
    refuse STORAGE_PATH_UNSAFE
  relative_state=${owned#/var/lib/}
  case $profile in
    live) allowlist=goodix_27c6_5125 ;;
    staging-probe) allowlist=virtual_image ;;
    *) refuse SYSTEMD_DROPIN_PROFILE_INVALID ;;
  esac
  printf '[Service]\nEnvironment="LD_LIBRARY_PATH=%s"\nEnvironment="FP_DRIVERS_ALLOWLIST=%s"\nStateDirectory=\nStateDirectory=%s\nStateDirectoryMode=0700\nExecStart=\nExecStart=/usr/libexec/fprintd\n' \
    "$runtime" "$allowlist" "$relative_state" >"$dropin"
  if [[ $profile == staging-probe ]]; then
    printf 'UnsetEnvironment=FP_VIRTUAL_IMAGE\nDeviceAllow=\nDevicePolicy=closed\nPrivateDevices=yes\nReadWritePaths=\n' \
      >>"$dropin"
  fi
}

exit_trap_scope_regression () {
  local work=$1

  [[ $EUID -ne 0 ]] || refuse EXIT_TRAP_TEST_MUST_BE_UNPRIVILEGED
  [[ $work == /tmp/goodix-d282-exit-trap-test.* && -d $work &&
     ! -L $work ]] || refuse EXIT_TRAP_TEST_ROOT_UNSAFE
  live_result="$work/result"
  live_private="$live_result/private"
  live_runtime="$work/runtime"
  live_storage_root="$work/storage-root"
  live_owned="$live_storage_root/.goodix-d282-01-test"
  live_dropin="$work/systemd/fprintd.service.d/90-goodix-d282-01.conf"
  live_service_before=inactive
  live_storage_existed=true
  live_before_inventory_ready=false
  live_unit_before_ready=false
  live_system_library_before_ready=false
  live_staging_started=true
  live_service_touched=false
  live_cleanup_test_mode=true
  live_run_return_code=1
  install -d -m 0700 "$live_private" "$live_runtime" "$live_owned" \
    "$(dirname "$live_dropin")" "$live_storage_root"
  printf 'D282_01_RESULT=FAIL_PENDING_AUDIT\n' >"$live_result/summary.env"
  printf 'staged\n' >"$live_runtime/artifact"
  printf 'synthetic\n' >"$live_owned/non-biometric-sentinel"
  printf '[Service]\n' >"$live_dropin"
  live_cleanup_armed=true
  trap cleanup_live EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  echo "EXIT_TRAP_TEST_ROOT=$work"

  exit_trap_failure_inside_function () {
    local deliberately_out_of_scope=armed
    [[ $deliberately_out_of_scope == armed ]]
    return 41
  }
  exit_trap_failure_inside_function
}

run_authorized_staging_probe () {
  local candidate=$1 grant=$2 state baseline manifest expected_id stamp since
  local candidate_operation candidate_driver candidate_usb_disabled
  local candidate_goodix_present
  local daemon_pid daemon_exe exec_status active_state sub_state unit_result
  local private_devices device_policy raw fd_target usb_fd_count=0
  local mapped_libfprint
  local system_library_current

  live_result=
  live_private=
  live_runtime=
  live_owned=
  live_storage_root=/var/lib/fprint
  live_dropin=/run/systemd/system/fprintd.service.d/90-goodix-d282-01.conf
  live_service_before=unknown
  live_unit_before=
  live_system_library=
  live_system_library_before=
  live_storage_existed=false
  live_before_inventory_ready=false
  live_unit_before_ready=false
  live_system_library_before_ready=false
  live_staging_started=false
  live_service_touched=false
  live_cleanup_armed=false
  live_cleanup_test_mode=false
  live_run_return_code=1
  real_usb_enumeration_attempted=false
  real_sensor_accessed=false
  live_execution_performed=false
  staging_probe_execution_performed=false
  staging_probe_mode=true

  [[ $EUID -eq 0 ]] || refuse STAGING_PROBE_REQUIRES_ROOT
  state="$candidate/d282-01-staging-probe-candidate.state"
  [[ $candidate == /tmp/goodix-d282-01-staging-probe-candidate.* &&
     -f $state && ! -L $candidate ]] ||
    refuse STAGING_PROBE_CANDIDATE_INVALID
  baseline=$(state_value "$state" D282_01_STAGING_PROBE_BASELINE_SHA) ||
    refuse STAGING_PROBE_CANDIDATE_STATE
  manifest=$(state_value "$state" D282_01_STAGING_PROBE_MANIFEST_SHA256) ||
    refuse STAGING_PROBE_CANDIDATE_STATE
  expected_id=$(state_value "$state" D282_01_STAGING_PROBE_EXPECTED_GRANT_ID) ||
    refuse STAGING_PROBE_CANDIDATE_STATE
  candidate_operation=$(state_value \
    "$state" D282_01_STAGING_PROBE_OPERATION) ||
    refuse STAGING_PROBE_CANDIDATE_STATE
  candidate_driver=$(state_value "$state" D282_01_STAGING_PROBE_DRIVER) ||
    refuse STAGING_PROBE_CANDIDATE_STATE
  candidate_usb_disabled=$(state_value \
    "$state" D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED) ||
    refuse STAGING_PROBE_CANDIDATE_STATE
  candidate_goodix_present=$(state_value \
    "$state" D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT) ||
    refuse STAGING_PROBE_CANDIDATE_STATE
  [[ $candidate_operation == "$staging_probe_operation" ]] ||
    refuse STAGING_PROBE_OPERATION_DRIFT
  [[ $candidate_driver == virtual_image && $candidate_usb_disabled == true &&
     $candidate_goodix_present == false ]] ||
    refuse STAGING_PROBE_CANDIDATE_STATE
  verify_staging_probe_baseline "$baseline"
  [[ $(sha256sum "$candidate/d282-01-staging-probe-artifacts.sha256" |
    awk '{print $1}') == "$manifest" ]] || refuse MANIFEST_DRIFT
  (cd "$candidate" && sha256sum -c \
    d282-01-staging-probe-artifacts.sha256) || refuse ARTIFACT_DRIFT
  validate_staging_probe_tooling
  audit_staging_probe_candidate "$candidate"
  abi_preflight "$candidate"
  validate_grant "$grant" "$baseline" "$expected_id" \
    "$staging_probe_operation"

  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  live_result="/var/tmp/goodix-d282-01-staging-probe-results/${stamp}-${baseline:0:12}"
  live_runtime="/run/goodix-d282-01/staging-probe-${stamp}-${baseline:0:12}"
  live_owned="$live_storage_root/.goodix-d282-01-staging-probe-${stamp}-${baseline:0:12}"
  [[ ! -e $live_runtime && ! -e $live_owned && ! -e $live_dropin ]] ||
    refuse STAGING_COLLISION
  live_service_before=$(systemctl is-active fprintd.service 2>/dev/null || true)
  [[ $live_service_before == active || $live_service_before == inactive ]] ||
    refuse STAGING_PROBE_FPRINTD_INITIAL_STATE_UNSAFE
  [[ -d $live_storage_root ]] && live_storage_existed=true
  live_system_library=$(readlink -f /usr/lib64/libfprint-2.so.2) ||
    refuse SYSTEM_LIBFPRINT_MISSING
  [[ -f $live_system_library ]] || refuse SYSTEM_LIBFPRINT_MISSING
  live_system_library_before=$(sha256sum "$live_system_library" |
    awk '{print $1}') || refuse SYSTEM_LIBFPRINT_HASH_FAILED
  validate_selinux_preconditions "$live_system_library" "$live_storage_root"
  [[ $validated_selinux_enforcement == Enforcing ]] ||
    refuse STAGING_PROBE_SELINUX_NOT_ENFORCING

  live_private="$live_result/private"
  install -d -m 0700 "$live_private" || refuse RESULT_DIRECTORY_CREATE_FAILED
  {
    echo D282_01_RESULT=FAIL_PENDING_AUDIT
    echo "D282_01_STAGING_PROBE_BASELINE_SHA=$baseline"
    echo "D282_01_OPERATION=$staging_probe_operation"
    echo D282_01_STAGING_PROBE_DRIVER=virtual_image
    echo D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED=true
    echo D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT=false
    echo REAL_USB_ENUMERATION_ATTEMPTED=false
    echo REAL_SENSOR_ACCESSED=false
    echo BIOMETRIC_ACTION_COUNT=0
    echo FINGER_CONTACT_COUNT=0
    echo LIVE_EXECUTION_PERFORMED=false
  } >"$live_result/summary.env" || refuse RESULT_SUMMARY_CREATE_FAILED
  chmod 0600 "$live_result/summary.env" || refuse RESULT_SUMMARY_MODE_FAILED
  live_cleanup_armed=true
  trap cleanup_live EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  since=$(date --iso-8601=seconds) || refuse HOST_CLOCK_FAILED
  systemctl cat fprintd.service >"$live_private/unit.before" ||
    refuse UNIT_SNAPSHOT_FAILED
  live_unit_before=$(sha256sum "$live_private/unit.before" |
    awk '{print $1}') || refuse UNIT_SNAPSHOT_HASH_FAILED
  live_unit_before_ready=true
  "$script_dir/d282_storage_inventory.py" "$live_storage_root" \
    "$live_private/storage.before.json" --exclude-name "${live_owned##*/}" \
    >"$live_private/storage.before.env" || refuse STORAGE_INVENTORY_FAILED
  live_before_inventory_ready=true
  live_system_library_before_ready=true

  prepare_grant_claim "$expected_id"
  consume_validated_grant "$grant"
  live_staging_started=true
  install -d -m 0700 "$live_runtime" "$live_owned" \
    "$(dirname "$live_dropin")"
  install -m 0600 "$candidate/libfprint-2.so.2.0.0" \
    "$candidate/libgusb.so.2" "$live_runtime/"
  ln -s libfprint-2.so.2.0.0 "$live_runtime/libfprint-2.so.2"
  ln -s libfprint-2.so.2 "$live_runtime/libfprint-2.so"
  for raw in "$live_runtime"/*.so.*; do
    chcon --reference=/usr/lib64/libfprint-2.so.2 "$raw"
  done
  restorecon -RF "$live_owned"
  write_systemd_dropin "$live_runtime" "$live_owned" "$live_dropin" \
    staging-probe
  chmod 0600 "$live_dropin"
  live_service_touched=true
  if [[ $live_service_before == active ]]; then
    systemctl stop fprintd.service
  fi
  systemctl daemon-reload
  staging_probe_execution_performed=true
  systemctl start fprintd.service

  active_state=$(systemctl show -p ActiveState --value fprintd.service)
  sub_state=$(systemctl show -p SubState --value fprintd.service)
  unit_result=$(systemctl show -p Result --value fprintd.service)
  exec_status=$(systemctl show -p ExecMainStatus --value fprintd.service)
  private_devices=$(systemctl show -p PrivateDevices --value fprintd.service)
  device_policy=$(systemctl show -p DevicePolicy --value fprintd.service)
  [[ $active_state == active && $sub_state == running &&
     $unit_result == success && $exec_status == 0 ]] ||
    refuse STAGING_PROBE_DAEMON_START_FAILED
  [[ $private_devices == yes && $device_policy == closed ]] ||
    refuse STAGING_PROBE_USB_DEVICE_SANDBOX_INACTIVE
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse DAEMON_PID_INVALID
  daemon_exe=$(readlink -f "/proc/$daemon_pid/exe") ||
    refuse DAEMON_EXE_UNREADABLE
  [[ $daemon_exe == /usr/libexec/fprintd ]] || refuse DAEMON_EXE_DRIFT
  grep -F "$live_runtime/libfprint-2.so.2.0.0" "/proc/$daemon_pid/maps" \
    >/dev/null || refuse DAEMON_LIBRARY_MAP_MISSING
  cp "/proc/$daemon_pid/maps" "$live_private/maps" ||
    refuse DAEMON_MAPS_UNREADABLE
  mapped_libfprint=$(awk '$NF ~ /libfprint-2[.]so/ {print $NF}' \
    "$live_private/maps" | sort -u)
  [[ $mapped_libfprint == "$live_runtime/libfprint-2.so.2.0.0" ]] ||
    refuse DAEMON_LIBRARY_MAP_NOT_EXACT
  tr '\0' '\n' <"/proc/$daemon_pid/environ" >"$live_private/environ" ||
    refuse DAEMON_ENVIRONMENT_UNREADABLE
  grep -Fx "LD_LIBRARY_PATH=$live_runtime" "$live_private/environ" >/dev/null ||
    refuse DAEMON_LD_LIBRARY_PATH_DRIFT
  grep -Fx 'FP_DRIVERS_ALLOWLIST=virtual_image' \
    "$live_private/environ" >/dev/null || refuse DAEMON_DRIVER_ALLOWLIST_DRIFT
  grep -Fx "STATE_DIRECTORY=$live_owned" "$live_private/environ" >/dev/null ||
    refuse DAEMON_STATE_DIRECTORY_DRIFT
  ! grep -q '^FP_VIRTUAL_IMAGE=' "$live_private/environ" ||
    refuse STAGING_PROBE_VIRTUAL_ENDPOINT_PRESENT
  for raw in "/proc/$daemon_pid/fd"/*; do
    fd_target=$(readlink "$raw" 2>/dev/null || true)
    [[ $fd_target == /dev/bus/usb/* ]] && ((usb_fd_count+=1))
  done
  [[ $usb_fd_count -eq 0 ]] || refuse STAGING_PROBE_USB_FD_OBSERVED
  [[ $(find "$live_owned" -mindepth 1 | wc -l) -eq 0 ]] ||
    refuse STAGING_PROBE_STORAGE_NOT_EMPTY
  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$live_private/journal.raw"
  if grep -Eiq 'permission denied|status=126|avc:.*denied' \
    "$live_private/journal.raw"; then
    refuse STAGING_PROBE_SELINUX_EXEC_DENIAL
  fi
  system_library_current=$(sha256sum "$live_system_library" |
    awk '{print $1}') || refuse SYSTEM_LIBFPRINT_HASH_FAILED
  [[ $system_library_current == "$live_system_library_before" ]] ||
    refuse SYSTEM_LIBFPRINT_DRIFT

  {
    echo D282_01_RESULT=PASS_STAGING_PROBE_PENDING_ROLLBACK
    echo "D282_01_STAGING_PROBE_BASELINE_SHA=$baseline"
    echo "D282_01_OPERATION=$staging_probe_operation"
    echo FPRINTD_SYSTEMD_STAGING_START=PASS
    echo SELINUX_ENFORCING=true
    echo SELINUX_EXEC_DENIAL=false
    echo EXEC_MAIN_STATUS=0
    echo "DAEMON_EXE=$daemon_exe"
    echo EXACT_LIBRARY_MAP_VERIFIED=true
    echo CUSTOM_LIBFPRINT_LOADED=true
    echo EXACT_STATE_DIRECTORY_VERIFIED=true
    echo D282_01_STAGING_PROBE_DRIVER=virtual_image
    echo D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED=true
    echo D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT=false
    echo PRIVATE_DEVICES=true
    echo DEVICE_POLICY=closed
    echo USB_DEVICE_FD_COUNT=0
    echo REAL_USB_ENUMERATION_ATTEMPTED=false
    echo REAL_SENSOR_ACCESSED=false
    echo BIOMETRIC_ACTION_COUNT=0
    echo FINGER_CONTACT_COUNT=0
    echo LIVE_EXECUTION_PERFORMED=false
    echo RETRY_AUTHORIZED=false
    echo PAM_IN_SCOPE=false
  } >"$live_result/summary.env"
  {
    echo "DAEMON_EXE=$daemon_exe"
    echo "CUSTOM_LIBFPRINT=$live_runtime/libfprint-2.so.2.0.0"
    echo "USB_DEVICE_FD_COUNT=$usb_fd_count"
    echo "PRIVATE_DEVICES=$private_devices"
    echo "DEVICE_POLICY=$device_policy"
  } >"$live_result/operator.log"
  chmod 0600 "$live_result/operator.log" "$live_result/summary.env"
  live_run_return_code=0
  echo "RISULTATI_STAGING_PROBE=$live_result"
  echo GRANT_CONSUMED=true
  echo RETRY_AUTHORIZED=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo BIOMETRIC_ACTION_COUNT=0
  echo FINGER_CONTACT_COUNT=0
  echo LIVE_EXECUTION_PERFORMED=false
  return 0
}

run_authorized_live () {
  local candidate=$1 grant=$2 state baseline manifest expected_id user stamp
  local daemon_pid raw epoch_count enroll_count verify_count action_rc=1
  local target_count since stored
  local observed_attempts consumed_action_count cleanup_epoch_count hidden_second_count
  local retry_count reopen_count reset_count clear_halt_count persistent_count
  local same_match_count different_no_match_count enroll_retry_count

  live_result=
  live_private=
  live_runtime=
  live_owned=
  live_storage_root=/var/lib/fprint
  live_dropin=/run/systemd/system/fprintd.service.d/90-goodix-d282-01.conf
  live_service_before=unknown
  live_unit_before=
  live_system_library=
  live_system_library_before=
  live_storage_existed=false
  live_before_inventory_ready=false
  live_unit_before_ready=false
  live_system_library_before_ready=false
  live_staging_started=false
  live_service_touched=false
  live_cleanup_armed=false
  live_cleanup_test_mode=false
  live_run_return_code=1
  real_sensor_accessed=false
  staging_probe_execution_performed=false
  staging_probe_mode=false
  [[ $EUID -eq 0 ]] || refuse LIVE_REQUIRES_ROOT
  state="$candidate/d282-01-candidate.state"
  [[ $candidate == /tmp/goodix-d282-01-candidate.* && -f $state && ! -L $candidate ]] || refuse CANDIDATE_INVALID
  baseline=$(state_value "$state" D282_01_BASELINE_SHA) || refuse CANDIDATE_STATE
  manifest=$(state_value "$state" D282_01_MANIFEST_SHA256) || refuse CANDIDATE_STATE
  expected_id=$(state_value "$state" D282_01_EXPECTED_GRANT_ID) || refuse CANDIDATE_STATE
  verify_baseline "$baseline"
  [[ $(sha256sum "$candidate/d282-01-artifacts.sha256" | awk '{print $1}') == "$manifest" ]] || refuse MANIFEST_DRIFT
  (cd "$candidate" && sha256sum -c d282-01-artifacts.sha256) || refuse ARTIFACT_DRIFT
  validate_grant "$grant" "$baseline" "$expected_id" "$operation"
  user=$validated_grant_user
  validate_live_tooling
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  live_result="/var/tmp/goodix-d282-01-results/${stamp}-${baseline:0:12}"
  live_runtime="/run/goodix-d282-01/${stamp}-${baseline:0:12}"
  live_owned="$live_storage_root/.goodix-d282-01-${stamp}-${baseline:0:12}"
  [[ ! -e $live_runtime && ! -e $live_owned && ! -e $live_dropin ]] ||
    refuse STAGING_COLLISION
  live_service_before=$(systemctl is-active fprintd.service 2>/dev/null || true)
  [[ $live_service_before == active || $live_service_before == inactive ]] ||
    refuse FPRINTD_INITIAL_STATE_UNSAFE
  [[ -d $live_storage_root ]] && live_storage_existed=true
  live_system_library=$(readlink -f /usr/lib64/libfprint-2.so.2) ||
    refuse SYSTEM_LIBFPRINT_MISSING
  [[ -f $live_system_library ]] || refuse SYSTEM_LIBFPRINT_MISSING
  live_system_library_before=$(sha256sum "$live_system_library" |
    awk '{print $1}') || refuse SYSTEM_LIBFPRINT_HASH_FAILED
  validate_selinux_preconditions "$live_system_library" "$live_storage_root"
  live_private="$live_result/private"
  install -d -m 0700 "$live_private" || refuse RESULT_DIRECTORY_CREATE_FAILED
  { echo D282_01_RESULT=FAIL_PENDING_AUDIT; echo "D282_01_BASELINE_SHA=$baseline"; } \
    >"$live_result/summary.env" || refuse RESULT_SUMMARY_CREATE_FAILED
  chmod 0600 "$live_result/summary.env" || refuse RESULT_SUMMARY_MODE_FAILED
  live_cleanup_armed=true
  trap cleanup_live EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  since=$(date --iso-8601=seconds) || refuse HOST_CLOCK_FAILED
  systemctl cat fprintd.service >"$live_private/unit.before" ||
    refuse UNIT_SNAPSHOT_FAILED
  live_unit_before=$(sha256sum "$live_private/unit.before" |
    awk '{print $1}') || refuse UNIT_SNAPSHOT_HASH_FAILED
  live_unit_before_ready=true
  "$script_dir/d282_storage_inventory.py" "$live_storage_root" \
    "$live_private/storage.before.json" --exclude-name "${live_owned##*/}" \
    >"$live_private/storage.before.env" || refuse STORAGE_INVENTORY_FAILED
  live_before_inventory_ready=true
  live_system_library_before_ready=true
  target_preconsumption_match_count=$(count_goodix_targets /sys/bus/usb/devices)
  echo "TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count" \
    >>"$live_result/summary.env"
  [[ $target_preconsumption_match_count -eq 1 ]] || refuse TARGET_CARDINALITY_NOT_ONE
  prepare_grant_claim "$expected_id"
  consume_validated_grant "$grant"
  live_staging_started=true
  install -d -m 0700 "$live_runtime" "$live_owned" \
    "$(dirname "$live_dropin")"
  install -m 0600 "$candidate/libfprint-2.so.2.0.0" \
    "$candidate/libgusb.so.2" \
    "$candidate/libopencv_core.so.413" \
    "$candidate/libopencv_features2d.so.413" \
    "$candidate/libopencv_flann.so.413" \
    "$candidate/libopencv_imgproc.so.413" "$live_runtime/"
  ln -s libfprint-2.so.2.0.0 "$live_runtime/libfprint-2.so.2"
  ln -s libfprint-2.so.2 "$live_runtime/libfprint-2.so"
  if [[ $validated_selinux_enforcement == Enforcing ]]; then
    for raw in "$live_runtime"/*.so.*; do
      chcon --reference=/usr/lib64/libfprint-2.so.2 "$raw"
    done
    restorecon -RF "$live_owned"
  fi
  write_systemd_dropin "$live_runtime" "$live_owned" "$live_dropin" live
  chmod 0600 "$live_dropin"
  live_service_touched=true
  systemctl stop fprintd.service
  systemctl daemon-reload
  real_usb_enumeration_attempted=true
  real_sensor_accessed=true
  live_execution_performed=true
  systemctl start fprintd.service
  target_count=$(count_goodix_targets /sys/bus/usb/devices)
  [[ $target_count -eq 1 ]] || refuse TARGET_CARDINALITY_NOT_ONE
  daemon_pid=$(systemctl show -p MainPID --value fprintd.service)
  [[ $daemon_pid =~ ^[1-9][0-9]*$ ]] || refuse DAEMON_PID_INVALID
  grep -F "$live_runtime/libfprint-2.so.2.0.0" "/proc/$daemon_pid/maps" \
    >"$live_private/maps" || refuse DAEMON_LIBRARY_MAP_MISSING
  [[ $(readlink -f "/proc/$daemon_pid/exe") == /usr/libexec/fprintd ]] ||
    refuse DAEMON_EXE_DRIFT
  echo EXACT_LIBRARY_MAP_VERIFIED=true >"$live_result/operator.log"
  echo "PHASE_A=Enrollment indice destro: otto contatti, nessuna ripetizione extra."
  raw="$live_private/enroll.raw"
  set +e; timeout --signal=INT --kill-after=20s 1060s fprintd-enroll -f right-index-finger "$user" 2>&1 | tee "$raw"; action_rc=${PIPESTATUS[0]}; set -e
  [[ $action_rc -eq 0 && $(grep -c '^Enroll result: enroll-completed$' "$raw") -eq 1 ]] || return 1
  enroll_retry_count=$(grep -c 'enroll-retry-' "$raw" || true)
  [[ $enroll_retry_count -eq 0 ]] || refuse ENROLLMENT_RETRY_MARKER_OBSERVED
  [[ $(find "$live_owned" -type l | wc -l) -eq 0 ]] || return 1
  [[ $(find "$live_owned" -type f | wc -l) -eq 1 ]] || return 1
  stored=$(find "$live_owned" -type f -print)
  [[ $(head -c 3 "$stored") == FP3 ]] || return 1
  systemctl restart fprintd.service
  echo DAEMON_RESTART_COUNT=1 >>"$live_result/operator.log"
  echo "PHASE_A=Verify stesso indice destro: un solo contatto."
  raw="$live_private/verify-same.raw"
  set +e; timeout --signal=INT --kill-after=20s 180s fprintd-verify "$user" 2>&1 | tee "$raw"; action_rc=${PIPESTATUS[0]}; set -e
  [[ $action_rc -eq 0 && $(grep -c '^Verify result: verify-match (done)$' "$raw") -eq 1 ]] || return 1
  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$live_private/phase-a-journal.raw"
  grep 'GOODIX_D282_EPOCH_AUDIT' "$live_private/phase-a-journal.raw" \
    >"$live_private/phase-a-audit.raw"
  [[ $(wc -l <"$live_private/phase-a-audit.raw") -eq 2 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_ENROLL.*attempts=1 rejected=0 consumed=1 tls=1' "$live_private/phase-a-audit.raw") -eq 1 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_VERIFY.*attempts=1 rejected=0 consumed=1 tls=1.*first_image=1 release_tail=1 single_terminal=1 rearm32=0' "$live_private/phase-a-audit.raw") -eq 1 ]] || return 1
  echo "PHASE_B=Verify dito diverso (indice sinistro): un solo contatto; atteso no-match."
  raw="$live_private/verify-different.raw"
  set +e; timeout --signal=INT --kill-after=20s 180s fprintd-verify "$user" 2>&1 | tee "$raw"; action_rc=${PIPESTATUS[0]}; set -e
  [[ $action_rc -eq 1 && $(grep -c '^Verify result: verify-no-match (done)$' "$raw") -eq 1 ]] || return 1
  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$live_private/phase-b-journal.raw"
  grep 'GOODIX_D282_EPOCH_AUDIT' "$live_private/phase-b-journal.raw" \
    >"$live_private/phase-b-audit.raw"
  [[ $(wc -l <"$live_private/phase-b-audit.raw") -eq 3 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_VERIFY.*attempts=1 rejected=0 consumed=1 tls=1.*first_image=1 release_tail=1 single_terminal=1 rearm32=0' "$live_private/phase-b-audit.raw") -eq 2 ]] || return 1
  echo "PHASE_C=Delete del solo storage D282 isolato."
  fprintd-delete "$user" >"$live_private/delete.raw" 2>&1
  [[ $(find "$live_owned" -type f | wc -l) -eq 0 ]] || return 1
  journalctl -u fprintd.service --since "$since" --no-pager \
    >"$live_private/journal.raw"
  grep 'GOODIX_D282_EPOCH_AUDIT' "$live_private/journal.raw" \
    >"$live_private/audit.raw"
  epoch_count=$(wc -l <"$live_private/audit.raw")
  enroll_count=$(grep -c 'action=FPI_DEVICE_ACTION_ENROLL' "$live_private/audit.raw")
  verify_count=$(grep -c 'action=FPI_DEVICE_ACTION_VERIFY' "$live_private/audit.raw")
  cleanup_epoch_count=$(grep -c 'action=FPI_DEVICE_ACTION_NONE.*attempts=0 rejected=0 consumed=0 tls=0' "$live_private/audit.raw")
  consumed_action_count=$(grep -c 'consumed=1' "$live_private/audit.raw")
  observed_attempts=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^attempts=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$live_private/audit.raw")
  hidden_second_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^rejected=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$live_private/audit.raw")
  retry_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^(secure_retry|post_retry)=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$live_private/audit.raw")
  reopen_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^reopen=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$live_private/audit.raw")
  reset_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^reset=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$live_private/audit.raw")
  clear_halt_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^clear_halt=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$live_private/audit.raw")
  persistent_count=$(awk '{for (i=1; i<=NF; i++) if ($i ~ /^persistent=/) {split($i,a,"="); sum+=a[2]}} END {print sum+0}' "$live_private/audit.raw")
  same_match_count=$(grep -c '^Verify result: verify-match (done)$' "$live_private/verify-same.raw")
  different_no_match_count=$(grep -c '^Verify result: verify-no-match (done)$' "$live_private/verify-different.raw")
  [[ $epoch_count -eq 4 && $enroll_count -eq 1 && $verify_count -eq 2 &&
     $cleanup_epoch_count -eq 1 && $consumed_action_count -eq 3 &&
     $observed_attempts -eq 3 && $hidden_second_count -eq 0 &&
     $retry_count -eq 0 && $reopen_count -eq 0 && $reset_count -eq 0 &&
     $clear_halt_count -eq 0 && $persistent_count -eq 0 &&
     $same_match_count -eq 1 && $different_no_match_count -eq 1 ]] || return 1
  [[ $(grep -c 'attempts=1 rejected=0 consumed=1 tls=1' "$live_private/audit.raw") -eq 3 ]] || return 1
  [[ $(grep -c 'secure_retry=0 post_retry=0 reopen=0 reset=0 clear_halt=0' "$live_private/audit.raw") -eq 4 ]] || return 1
  [[ $(grep -c 'persistent=0' "$live_private/audit.raw") -eq 4 ]] || return 1
  [[ $(grep -c 'outstanding=0 drained=1 context_closed=1' "$live_private/audit.raw") -eq 4 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_VERIFY.*first_image=1 release_tail=1 single_terminal=1 rearm32=0' "$live_private/audit.raw") -eq 2 ]] || return 1
  [[ $(grep -c 'action=FPI_DEVICE_ACTION_ENROLL.*enroll_stages=8 enroll_rearm32=7 enroll_terminal=1' "$live_private/audit.raw") -eq 1 ]] || return 1
  sed "s/$user/<USER>/g; s/${baseline}/<BASELINE>/g; s/${stamp}/<RUN>/g" \
    "$live_private"/*.raw >>"$live_result/operator.log"
  {
    echo D282_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW
    echo "D282_01_BASELINE_SHA=$baseline"
    echo AUTHORIZED_BIOMETRIC_ACTION_MAX=3
    echo "OPEN_EPOCH_COUNT=$epoch_count"
    echo "ACTION_ATTEMPT_COUNT=$observed_attempts"
    echo "CONSUMED_BIOMETRIC_ACTION_COUNT=$consumed_action_count"
    echo "HOST_ONLY_DELETE_OPEN_EPOCH_COUNT=$cleanup_epoch_count"
    echo "ENROLL_ACTION_COUNT=$enroll_count"
    echo "ENROLLMENT_RETRY_CALLBACK_COUNT=$enroll_retry_count"
    echo EXTRA_ENROLLMENT_CONTACT_REQUESTED=false
    echo EXTRA_ENROLLMENT_REARM_COUNT=0
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
  } >"$live_result/summary.env"
  chmod 0600 "$live_result/operator.log" "$live_result/summary.env"
  live_run_return_code=0
  echo "RISULTATI=$live_result"
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

export_staging_probe_results () {
  local result=$1 export name source_sha copy_sha
  [[ $EUID -eq 0 && ${SUDO_UID:-} =~ ^[0-9]+$ &&
     ${SUDO_GID:-} =~ ^[0-9]+$ ]] || refuse EXPORT_CALLER
  [[ $result == /var/tmp/goodix-d282-01-staging-probe-results/* &&
     -d $result/private ]] || refuse EXPORT_SOURCE
  export=$(mktemp -d /tmp/goodix-d282-01-staging-probe-export.XXXXXX)
  chmod 0700 "$export"
  for name in operator.log summary.env; do
    source_sha=$(sha256sum "$result/$name" | awk '{print $1}')
    install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" \
      "$result/$name" "$export/$name"
    copy_sha=$(sha256sum "$export/$name" | awk '{print $1}')
    [[ $source_sha == "$copy_sha" ]] || refuse EXPORT_HASH
    echo "${name}_SHA256=$source_sha"
  done
  chown "$SUDO_UID:$SUDO_GID" "$export"
  echo D282_01_STAGING_PROBE_RESULTS_EXPORT=PASS_BYTE_IDENTICAL
  echo "EXPORT_DIRECTORY=$export"
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
  echo BIOMETRIC_ACTION_COUNT=0
  echo REAL_SENSOR_ACCESSED=false
}

case ${1:-} in
  --offline-preflight) [[ $# -eq 2 ]] || refuse USAGE; offline_preflight "$2" ;;
  --prepare-candidate) [[ $# -eq 3 ]] || refuse USAGE; prepare_candidate "$2" "$3" ;;
  --prepare-staging-probe-candidate) [[ $# -eq 2 ]] || refuse USAGE; prepare_staging_probe_candidate "$2" ;;
  --run-authorized-live) [[ $# -eq 4 && $3 == --grant ]] || refuse USAGE; run_authorized_live "$2" "$4" ;;
  --run-authorized-staging-probe) [[ $# -eq 4 && $3 == --grant ]] || refuse USAGE; run_authorized_staging_probe "$2" "$4" ;;
  --export-results) [[ $# -eq 2 ]] || refuse USAGE; export_results "$2" ;;
  --export-staging-probe-results) [[ $# -eq 2 ]] || refuse USAGE; export_staging_probe_results "$2" ;;
  --self-test-exit-trap) [[ $# -eq 2 ]] || refuse USAGE; exit_trap_scope_regression "$2" ;;
  *) echo "Uso: $0 --offline-preflight <opencv-rpm-dir> | --prepare-staging-probe-candidate <SHA> | --run-authorized-staging-probe <candidate> --grant <grant> | --export-staging-probe-results <results> | --prepare-candidate <SHA> <opencv-rpm-dir> | --run-authorized-live <candidate> --grant <grant> | --export-results <results>" >&2; exit 2 ;;
esac
