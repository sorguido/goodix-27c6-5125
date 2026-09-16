#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
cd "$root"
operation=D279_37_ONE_OFFLINE_PROTECTED_SPATIAL_RESIZE_EVALUATION
capture_relative=captures/D279_10/D27910_20260905_ATTEMPT02/raw/wire.pcapng
d279_37_cleanup_root=

git_root () { git -C "$root" -c safe.directory="$root" "$@"; }
is_full_sha () { [[ ${1:-} =~ ^[0-9a-f]{40}$ ]]; }

usage ()
{
  echo "Uso:" >&2
  echo "  $0 --offline-preflight" >&2
  echo "  $0 --prepare-approved-analysis <SHA_COMPLETO_APPROVATO>" >&2
  echo "  $0 --write-grant <SHA_COMPLETO_APPROVATO> <FILE_GRANT>" >&2
  echo "  sudo $0 --run-approved-analysis <BUILD_PREPARATO> --grant <FILE_GRANT>" >&2
  exit 2
}

refuse ()
{
  echo "PROTECTED_GATE_REFUSED=true" >&2
  echo "PROTECTED_GATE_REFUSAL_REASON=$1" >&2
  echo "TARGET_PSK_ACCESSED=false" >&2
  echo "LIVE_OR_USB_ACTION_COUNT=0" >&2
  exit 3
}

cleanup_offline_tree ()
{
  if [[ ${d279_37_cleanup_root:-} == /tmp/goodix-d279-37-offline.* ]]; then
    find "$d279_37_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

state_value ()
{
  local file=$1 key=$2 value
  value=$(sed -n "s/^${key}=//p" "$file")
  [[ -n $value && $(grep -c "^${key}=" "$file") -eq 1 ]] || return 1
  printf '%s\n' "$value"
}

require_private_directory ()
{
  local path=$1 expected_uid=$2 metadata
  [[ -d $path && ! -L $path ]] || refuse PRIVATE_DIRECTORY_INVALID
  metadata=$(stat -c '%u:%a' "$path") || refuse PRIVATE_DIRECTORY_STAT
  [[ $metadata == "$expected_uid:700" ]] || refuse PRIVATE_DIRECTORY_METADATA
}

critical_paths=(
  analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py
  analysis/D279/d279_31_attempt02_tls_reconstruction_feasibility.py
  analysis/D279/d279_32_tls12_psk_decrypt.py
  analysis/D279/d279_33_attempt02_in_memory_composer.py
  analysis/D279/d279_34_exact_nbis_variant_evaluator.py
  analysis/D279/d279_37_spatial_resize_evaluator.py
  analysis/D279/test_d279_31_attempt02_tls_reconstruction_feasibility.py
  analysis/D279/test_d279_32_tls12_psk_decrypt.py
  analysis/D279/test_d279_33_attempt02_in_memory_composer.py
  analysis/D279/test_d279_34_exact_nbis_variant_evaluator.py
  analysis/D279/test_d279_37_spatial_resize_evaluator.py
  core/post_d4.py
  src/goodix5125_cleanroom.py
  libfprint-driver
  reference/libfprint-fedora44-1.94.100/source
  operator_kit/d279-35-offline-protected-evaluation/d279_35_protected_attempt02_eval.py
  operator_kit/d279-35-offline-protected-evaluation/test_d279_35_protected_attempt02_eval.py
  operator_kit/d279-37-offline-protected-spatial-resize
  "$capture_relative"
)

verify_approved_baseline ()
{
  local approved=$1 head origin_head dirty
  is_full_sha "$approved" || refuse INVALID_APPROVED_SHA
  [[ $(git_root branch --show-current) == development ]] || refuse BRANCH_NOT_DEVELOPMENT
  git_root cat-file -e "$approved^{commit}" 2>/dev/null || refuse APPROVED_COMMIT_NOT_LOCAL
  head=$(git_root rev-parse HEAD)
  [[ $head == "$approved" ]] || refuse HEAD_MISMATCH
  origin_head=$(git_root rev-parse origin/development 2>/dev/null) ||
    refuse ORIGIN_DEVELOPMENT_UNAVAILABLE
  [[ $origin_head == "$approved" ]] || refuse ORIGIN_DEVELOPMENT_MISMATCH
  dirty=$(git_root status --porcelain --untracked-files=all -- "${critical_paths[@]}")
  [[ -z $dirty ]] || refuse CRITICAL_SOURCE_DIRTY
}

find_host_gusb ()
{
  local candidate
  for candidate in \
    /usr/lib64/libgusb.so.2.0.10 \
    /usr/lib64/libgusb.so.2 \
    /usr/lib/x86_64-linux-gnu/libgusb.so.2; do
    [[ -f $candidate ]] && { printf '%s\n' "$candidate"; return 0; }
  done
  return 1
}

build_snapshot_helper ()
{
  local snapshot=$1 prepared=$2 build_dir pkgconfig_dir
  local host_gusb inner
  build_dir="$prepared/build"
  pkgconfig_dir="$prepared/pkgconfig"
  inner="$snapshot/operator_kit/d279-37-offline-protected-spatial-resize/build-inner.sh"
  host_gusb=$(find_host_gusb) || refuse HOST_GUSB_RUNTIME_NOT_FOUND
  mkdir -p "$build_dir" "$pkgconfig_dir"
  cp "$host_gusb" "$pkgconfig_dir/libgusb.so.2"
  sed -e "s|@PREFIX@|$pkgconfig_dir|g" \
      -e "s|@INCLUDEDIR@|$snapshot/libfprint-driver/tests/support/d279|g" \
      "$snapshot/libfprint-driver/tests/support/d279/gusb.pc.in" \
      >"$pkgconfig_dir/gusb.pc"
  command -v flatpak >/dev/null 2>&1 || refuse FLATPAK_NOT_FOUND
  flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1 ||
    refuse FREEDESKTOP_SDK_NOT_FOUND
  flatpak run --user --unshare=network \
    --filesystem="$snapshot":ro \
    --filesystem="$prepared" \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$snapshot" "$build_dir" "$pkgconfig_dir" "$prepared"
}

offline_preflight ()
{
  local work helper
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_REQUIRES_NORMAL_USER
  python3 -B -m unittest -q \
    analysis/D279/test_d279_31_attempt02_tls_reconstruction_feasibility.py \
    analysis/D279/test_d279_32_tls12_psk_decrypt.py \
    analysis/D279/test_d279_33_attempt02_in_memory_composer.py \
    analysis/D279/test_d279_34_exact_nbis_variant_evaluator.py \
    analysis/D279/test_d279_37_spatial_resize_evaluator.py \
    operator_kit/d279-35-offline-protected-evaluation/test_d279_35_protected_attempt02_eval.py \
    operator_kit/d279-37-offline-protected-spatial-resize/test_d279_37_protected_spatial_resize_eval.py
  "$root/libfprint-driver/tests/run_goodix_exact_nbis_resize_count_pipe_test.sh"
  work=$(mktemp -d /tmp/goodix-d279-37-offline.XXXXXX)
  d279_37_cleanup_root=$work
  trap cleanup_offline_tree EXIT HUP INT TERM
  build_snapshot_helper "$root" "$work"
  helper="$work/d279_resize_nbis_count.pending"
  [[ -f $helper && ! -L $helper ]] || refuse OFFLINE_HELPER_MISSING
  mv "$helper" "$work/d279_resize_nbis_count"
  helper="$work/d279_resize_nbis_count"
  chmod 0700 "$helper"
  LD_LIBRARY_PATH="$work/runtime" python3 -B -c '
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("d279_37_pipe_preflight", sys.argv[1])
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
with module.ExactLibfprintResizeNbisPipe(pathlib.Path(sys.argv[2])) as runner:
    for factor in module.SPATIAL_FACTORS:
        assert runner.count(bytearray(5120), 80, 64, factor) == 0
' "$root/analysis/D279/d279_37_spatial_resize_evaluator.py" "$helper"
  echo D279_37_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
  echo TARGET_PSK_ACCESSED=false
  echo REAL_RASTER_EVALUATED_COUNT=0
  echo LIVE_OR_USB_ACTION_COUNT=0
  cleanup_offline_tree
  d279_37_cleanup_root=
  trap - EXIT HUP INT TERM
}

prepare_approved_analysis ()
{
  local approved=$1 prepared snapshot helper state
  local helper_hash pixman_hash gusb_hash capture_hash runner_hash
  local d274_hash d31_hash d32_hash d33_hash d34_hash d35_hash d37_hash
  local post_d4_hash cleanroom_hash
  [[ $EUID -ne 0 ]] || refuse PREPARE_REQUIRES_NORMAL_USER
  verify_approved_baseline "$approved"
  prepared=$(mktemp -d /tmp/goodix-d279-37-approved.XXXXXX)
  chmod 0700 "$prepared"
  snapshot="$prepared/snapshot"
  mkdir -m 0700 "$snapshot"
  git_root archive "$approved" -- "${critical_paths[@]}" | tar -x -C "$snapshot"
  build_snapshot_helper "$snapshot" "$prepared"
  verify_approved_baseline "$approved"
  helper="$prepared/d279_resize_nbis_count.pending"
  [[ -f $helper && ! -L $helper ]] || refuse PREPARED_HELPER_MISSING
  mv "$helper" "$prepared/d279_resize_nbis_count"
  helper="$prepared/d279_resize_nbis_count"
  chmod 0700 "$helper"

  helper_hash=$(sha256sum "$helper" | awk '{print $1}')
  pixman_hash=$(sha256sum "$prepared/runtime/libpixman-1.so.0" | awk '{print $1}')
  gusb_hash=$(sha256sum "$prepared/pkgconfig/libgusb.so.2" | awk '{print $1}')
  capture_hash=$(sha256sum "$snapshot/$capture_relative" | awk '{print $1}')
  runner_hash=$(sha256sum "$snapshot/operator_kit/d279-37-offline-protected-spatial-resize/d279_37_protected_spatial_resize_eval.py" | awk '{print $1}')
  d274_hash=$(sha256sum "$snapshot/analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py" | awk '{print $1}')
  d31_hash=$(sha256sum "$snapshot/analysis/D279/d279_31_attempt02_tls_reconstruction_feasibility.py" | awk '{print $1}')
  d32_hash=$(sha256sum "$snapshot/analysis/D279/d279_32_tls12_psk_decrypt.py" | awk '{print $1}')
  d33_hash=$(sha256sum "$snapshot/analysis/D279/d279_33_attempt02_in_memory_composer.py" | awk '{print $1}')
  d34_hash=$(sha256sum "$snapshot/analysis/D279/d279_34_exact_nbis_variant_evaluator.py" | awk '{print $1}')
  d35_hash=$(sha256sum "$snapshot/operator_kit/d279-35-offline-protected-evaluation/d279_35_protected_attempt02_eval.py" | awk '{print $1}')
  d37_hash=$(sha256sum "$snapshot/analysis/D279/d279_37_spatial_resize_evaluator.py" | awk '{print $1}')
  post_d4_hash=$(sha256sum "$snapshot/core/post_d4.py" | awk '{print $1}')
  cleanroom_hash=$(sha256sum "$snapshot/src/goodix5125_cleanroom.py" | awk '{print $1}')
  state="$prepared/d279-37-prepared.state"
  {
    echo "D279_37_BASELINE_SHA=$approved"
    echo "D279_37_OPERATION=$operation"
    echo "D279_37_PREPARED_DIR=$prepared"
    echo "D279_37_HELPER_SHA256=$helper_hash"
    echo "D279_37_PIXMAN_SHA256=$pixman_hash"
    echo "D279_37_GUSB_SHA256=$gusb_hash"
    echo "D279_37_CAPTURE_SHA256=$capture_hash"
    echo "D279_37_RUNNER_SHA256=$runner_hash"
    echo "D279_37_D274_SHA256=$d274_hash"
    echo "D279_37_D31_SHA256=$d31_hash"
    echo "D279_37_D32_SHA256=$d32_hash"
    echo "D279_37_D33_SHA256=$d33_hash"
    echo "D279_37_D34_SHA256=$d34_hash"
    echo "D279_37_D35_SHA256=$d35_hash"
    echo "D279_37_EVALUATOR_SHA256=$d37_hash"
    echo "D279_37_POST_D4_SHA256=$post_d4_hash"
    echo "D279_37_CLEANROOM_SHA256=$cleanroom_hash"
    echo "D279_37_GRANT_ID=d27937-$approved"
  } >"$state"
  chmod 0600 "$state"
  echo APPROVED_ANALYSIS_PREPARED=true
  echo "APPROVED_BASELINE_SHA=$approved"
  echo "PREPARED_BUILD_DIR=$prepared"
  echo "RESIZE_NBIS_HELPER_SHA256=$helper_hash"
  echo "PIXMAN_RUNTIME_SHA256=$pixman_hash"
  echo "CAPTURE_SHA256=$capture_hash"
  echo "EXPECTED_GRANT_ID=d27937-$approved"
  echo TARGET_PSK_ACCESSED=false
  echo LIVE_OR_USB_ACTION_COUNT=0
}

write_grant ()
{
  local approved=$1 grant=$2 parent
  [[ $EUID -ne 0 ]] || refuse GRANT_CREATION_REQUIRES_NORMAL_USER
  verify_approved_baseline "$approved"
  [[ ! -e $grant && ! -L $grant ]] || refuse GRANT_OUTPUT_COLLISION
  parent=$(dirname -- "$grant")
  require_private_directory "$parent" "$EUID"
  (
    set -o noclobber
    {
      echo "D279_37_BASELINE_SHA=$approved"
      echo "D279_37_OPERATION=$operation"
      echo "D279_37_GRANT_ID=d27937-$approved"
      echo "D279_37_GRANT_STATE=UNCONSUMED"
    } >"$grant"
  ) || refuse GRANT_OUTPUT_COLLISION
  chmod 0600 "$grant"
  echo GRANT_WRITTEN=true
  echo "GRANT_ID=d27937-$approved"
  echo TARGET_PSK_ACCESSED=false
}

verify_hash ()
{
  local file=$1 expected=$2
  [[ -f $file && ! -L $file ]] || refuse PREPARED_FILE_INVALID
  [[ $(sha256sum "$file" | awk '{print $1}') == "$expected" ]] ||
    refuse PREPARED_FILE_HASH_MISMATCH
}

run_approved_analysis ()
{
  local prepared=$1 grant=$2 state approved grant_id marker_root marker
  local result_root result_dir log output status operator_uid operator_gid
  [[ $EUID -eq 0 ]] || refuse RUN_REQUIRES_ROOT
  [[ -n ${SUDO_UID:-} && -n ${SUDO_GID:-} && $SUDO_UID != 0 ]] ||
    refuse RUN_REQUIRES_VISIBLE_SUDO_OPERATOR
  operator_uid=$SUDO_UID
  operator_gid=$SUDO_GID
  require_private_directory "$prepared" "$operator_uid"
  state="$prepared/d279-37-prepared.state"
  [[ -f $state && ! -L $state ]] || refuse PREPARED_STATE_INVALID
  approved=$(state_value "$state" D279_37_BASELINE_SHA) || refuse STATE_BASELINE
  verify_approved_baseline "$approved"
  [[ $(state_value "$state" D279_37_OPERATION) == "$operation" ]] || refuse STATE_OPERATION
  [[ $(state_value "$state" D279_37_PREPARED_DIR) == "$prepared" ]] || refuse STATE_DIRECTORY
  grant_id=$(state_value "$state" D279_37_GRANT_ID) || refuse STATE_GRANT_ID

  [[ -f $grant && ! -L $grant ]] || refuse GRANT_FILE_INVALID
  [[ $(stat -c '%u:%a' "$grant") == "$operator_uid:600" ]] || refuse GRANT_FILE_METADATA
  [[ $(state_value "$grant" D279_37_BASELINE_SHA) == "$approved" ]] || refuse GRANT_BASELINE
  [[ $(state_value "$grant" D279_37_OPERATION) == "$operation" ]] || refuse GRANT_OPERATION
  [[ $(state_value "$grant" D279_37_GRANT_ID) == "$grant_id" ]] || refuse GRANT_ID
  [[ $(state_value "$grant" D279_37_GRANT_STATE) == UNCONSUMED ]] || refuse GRANT_STATE

  verify_hash "$prepared/d279_resize_nbis_count" "$(state_value "$state" D279_37_HELPER_SHA256)"
  verify_hash "$prepared/runtime/libpixman-1.so.0" "$(state_value "$state" D279_37_PIXMAN_SHA256)"
  verify_hash "$prepared/pkgconfig/libgusb.so.2" "$(state_value "$state" D279_37_GUSB_SHA256)"
  verify_hash "$prepared/snapshot/$capture_relative" "$(state_value "$state" D279_37_CAPTURE_SHA256)"
  verify_hash "$prepared/snapshot/operator_kit/d279-37-offline-protected-spatial-resize/d279_37_protected_spatial_resize_eval.py" "$(state_value "$state" D279_37_RUNNER_SHA256)"
  verify_hash "$prepared/snapshot/analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py" "$(state_value "$state" D279_37_D274_SHA256)"
  verify_hash "$prepared/snapshot/analysis/D279/d279_31_attempt02_tls_reconstruction_feasibility.py" "$(state_value "$state" D279_37_D31_SHA256)"
  verify_hash "$prepared/snapshot/analysis/D279/d279_32_tls12_psk_decrypt.py" "$(state_value "$state" D279_37_D32_SHA256)"
  verify_hash "$prepared/snapshot/analysis/D279/d279_33_attempt02_in_memory_composer.py" "$(state_value "$state" D279_37_D33_SHA256)"
  verify_hash "$prepared/snapshot/analysis/D279/d279_34_exact_nbis_variant_evaluator.py" "$(state_value "$state" D279_37_D34_SHA256)"
  verify_hash "$prepared/snapshot/operator_kit/d279-35-offline-protected-evaluation/d279_35_protected_attempt02_eval.py" "$(state_value "$state" D279_37_D35_SHA256)"
  verify_hash "$prepared/snapshot/analysis/D279/d279_37_spatial_resize_evaluator.py" "$(state_value "$state" D279_37_EVALUATOR_SHA256)"
  verify_hash "$prepared/snapshot/core/post_d4.py" "$(state_value "$state" D279_37_POST_D4_SHA256)"
  verify_hash "$prepared/snapshot/src/goodix5125_cleanroom.py" "$(state_value "$state" D279_37_CLEANROOM_SHA256)"
  LD_LIBRARY_PATH="$prepared/runtime" ldd "$prepared/d279_resize_nbis_count" |
    grep -F "$prepared/runtime/libpixman-1.so.0" >/dev/null || refuse PIXMAN_RUNTIME_NOT_PINNED

  marker_root=/var/tmp/goodix-d279-37-consumed-grants
  if [[ ! -e $marker_root && ! -L $marker_root ]]; then
    mkdir -m 0700 "$marker_root"
  fi
  require_private_directory "$marker_root" 0
  marker="$marker_root/$grant_id"
  mkdir -m 0700 "$marker" 2>/dev/null || refuse GRANT_ALREADY_CONSUMED

  result_root=/var/tmp/goodix-d279-37-results
  if [[ ! -e $result_root && ! -L $result_root ]]; then
    mkdir -m 0700 "$result_root"
  fi
  require_private_directory "$result_root" 0
  result_dir="$result_root/$(date -u +%Y%m%dT%H%M%SZ)-${approved:0:12}"
  mkdir -m 0700 "$result_dir"
  log="$result_dir/operator.log"
  output="$result_dir/summary.json"
  set +e
  D279_37_AUTHORIZED_OPERATION=$operation \
  D279_37_AUTHORIZED_SHA=$approved \
  LD_LIBRARY_PATH="$prepared/runtime" \
    python3 -B "$prepared/snapshot/operator_kit/d279-37-offline-protected-spatial-resize/d279_37_protected_spatial_resize_eval.py" \
      --baseline "$approved" \
      --capture "$prepared/snapshot/$capture_relative" \
      --nbis-helper "$prepared/d279_resize_nbis_count" \
      --output "$output" >"$log" 2>&1
  status=$?
  set -e
  chmod 0600 "$log"
  if [[ $status -eq 0 && -f $output && ! -L $output ]]; then
    if python3 -B -c '
import json, sys
document = json.load(open(sys.argv[1], encoding="utf-8"))
assert document["outcome"] == "AUTHENTIC_SPATIAL_RESIZE_AGGREGATE_READY"
assert document["baseline_sha"] == sys.argv[2]
assert document["operation"] == "D279_37_ONE_OFFLINE_PROTECTED_SPATIAL_RESIZE_EVALUATION"
assert document["transport_or_psk_exported"] is False
assert document["plaintext_or_raster_exported"] is False
assert document["template_exported"] is False
assert document["live_or_usb_action_count"] == 0
aggregate = document["aggregate"]
assert aggregate["variant_count"] == 9 and len(aggregate["variants"]) == 9
assert aggregate["frame_roles"] == {"baseline": 1, "primary": 21, "auxiliary": 21}
assert aggregate["per_frame_counts_exported"] is False
assert aggregate["raster_exported"] is False and aggregate["template_exported"] is False
assert {v["spatial_factor"] for v in aggregate["variants"]} == {1, 2, 3}
assert {v["orientation"] for v in aggregate["variants"]} == {"identity"}
assert {v["polarity"] for v in aggregate["variants"]} == {"normal"}
allowed = {"frame_count", "frames_with_minutiae", "frames_with_at_least_10_minutiae", "minimum", "median", "maximum"}
for variant in aggregate["variants"]:
    assert set(variant["groups"]) == {"baseline", "primary", "auxiliary"}
    assert all(set(group) == allowed for group in variant["groups"].values())
' "$output" "$approved"; then
      chmod 0600 "$output"
    else
      status=4
      echo "OUTPUT_VALIDATION=FAIL_CLOSED" >>"$log"
    fi
  fi
  chown -R "$operator_uid:$operator_gid" "$result_dir"
  echo GRANT_CONSUMED=true
  echo "RESULT_DIRECTORY=$result_dir"
  echo "RUN_EXIT_STATUS=$status"
  echo RETRY_AUTHORIZED=false
  echo LIVE_OR_USB_ACTION_COUNT=0
  [[ $status -eq 0 ]] || exit "$status"
}

case ${1:-} in
  --offline-preflight)
    [[ $# -eq 1 ]] || usage
    offline_preflight
    ;;
  --prepare-approved-analysis)
    [[ $# -eq 2 ]] || usage
    prepare_approved_analysis "$2"
    ;;
  --write-grant)
    [[ $# -eq 3 ]] || usage
    write_grant "$2" "$3"
    ;;
  --run-approved-analysis)
    [[ $# -eq 4 && $3 == --grant ]] || usage
    run_approved_analysis "$2" "$4"
    ;;
  *) usage ;;
esac
