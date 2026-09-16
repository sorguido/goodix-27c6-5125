#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077
unset PYTHONHOME PYTHONOPTIMIZE PYTHONPATH

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
operation=D279_56_AUTHORIZED_OFFLINE_DYNAMIC_ENROLLMENT_REPLAY
capture_relative=captures/D279_10/D27910_20260905_ATTEMPT02/raw/wire.pcapng
cleanup_root=

git_root () { git -C "$root" -c safe.directory="$root" "$@"; }
is_full_sha () { [[ ${1:-} =~ ^[0-9a-f]{40}$ ]]; }

usage ()
{
  echo "Uso:" >&2
  echo "  $0 --offline-preflight" >&2
  echo "  $0 --prepare-authorized-study <SHA_COMPLETO>" >&2
  echo "  sudo $0 --run-authorized-study <DIRECTORY_PREPARATA>" >&2
  exit 2
}

refuse ()
{
  echo PROTECTED_STUDY_REFUSED=true >&2
  echo "PROTECTED_STUDY_REFUSAL_REASON=$1" >&2
  echo TARGET_PSK_ACCESSED=false >&2
  echo LIVE_OR_USB_ACTION_COUNT=0 >&2
  exit 3
}

cleanup_temp ()
{
  if [[ ${cleanup_root:-} == /tmp/goodix-d279-56-offline.* ||
        ${cleanup_root:-} == /tmp/goodix-d279-56-authorized.* ]]; then
    find "$cleanup_root" -depth -delete 2>/dev/null || true
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
  analysis/D279/d279_56_dynamic_enrollment_policy.py
  analysis/D279/d279_56_r2_pipe.c
  analysis/D279/test_d279_56_dynamic_enrollment_policy.py
  core/post_d4.py
  src/goodix5125_cleanroom.py
  libfprint-driver/goodix_u16_to_fpimage.h
  libfprint-driver/goodix_sigfm_preprocess.c
  libfprint-driver/goodix_sigfm_preprocess.h
  libfprint-driver/rockytkg-imgproc/goodix_imgproc.c
  libfprint-driver/rockytkg-imgproc/goodix_imgproc.h
  libfprint-driver/tests/test_goodix_sigfm_preprocess.c
  Rockytkg/PROVENANCE.md
  Rockytkg/src/goodixgf.c
  operator_kit/d279-35-offline-protected-evaluation/d279_35_protected_attempt02_eval.py
  operator_kit/d279-56-offline-protected-dynamic-enrollment
  "$capture_relative"
)

verify_baseline ()
{
  local approved=$1 head origin_head dirty
  is_full_sha "$approved" || refuse INVALID_BASELINE_SHA
  [[ $(git_root branch --show-current) == development ]] || refuse BRANCH_NOT_DEVELOPMENT
  git_root cat-file -e "$approved^{commit}" 2>/dev/null || refuse BASELINE_NOT_LOCAL
  head=$(git_root rev-parse HEAD)
  [[ $head == "$approved" ]] || refuse HEAD_MISMATCH
  origin_head=$(git_root rev-parse origin/development 2>/dev/null) ||
    refuse ORIGIN_DEVELOPMENT_UNAVAILABLE
  [[ $origin_head == "$approved" ]] || refuse ORIGIN_DEVELOPMENT_MISMATCH
  dirty=$(git_root status --porcelain --untracked-files=all -- "${critical_paths[@]}")
  [[ -z $dirty ]] || refuse CRITICAL_SOURCE_DIRTY
}

build_and_test ()
{
  local source_root=$1 work=$2 helper actual
  helper="$work/d279_56_r2_pipe"
  command -v cc >/dev/null 2>&1 || refuse CC_NOT_FOUND
  command -v nm >/dev/null 2>&1 || refuse NM_NOT_FOUND
  PYTHONPATH="$source_root/analysis/D279" PYTHONNOUSERSITE=1 \
    python3 -B "$source_root/analysis/D279/test_d279_56_dynamic_enrollment_policy.py" -q
  PYTHONPATH="$source_root/analysis/D279" PYTHONNOUSERSITE=1 \
    python3 -B "$source_root/operator_kit/d279-56-offline-protected-dynamic-enrollment/test_d279_56_protected_runner.py" -q
  cc -std=c11 -O2 -g -Wall -Wextra -Werror -Wconversion -Wshadow \
    -I"$source_root/libfprint-driver" \
    -I"$source_root/libfprint-driver/rockytkg-imgproc" \
    "$source_root/libfprint-driver/rockytkg-imgproc/goodix_imgproc.c" \
    "$source_root/libfprint-driver/goodix_sigfm_preprocess.c" \
    "$source_root/analysis/D279/d279_56_r2_pipe.c" -lm -o "$helper"
  chmod 0700 "$helper"
  if nm -u "$helper" | awk '{print $NF}' |
     grep -E '^(getenv|fopen|open|openat|read|write|socket|libusb_.*|g_usb_.*|SSL_.*|gnutls_.*)$'; then
    refuse R2_HELPER_FORBIDDEN_SYMBOL
  fi
  PYTHONPATH="$source_root/analysis/D279" PYTHONNOUSERSITE=1 python3 -B - \
    "$helper" <<'PY'
import hashlib
import sys
from pathlib import Path
from d279_56_dynamic_enrollment_policy import R2Pipe

baseline = [1500 + ((x * 17 + y * 29 + (x * y) % 31) % 700)
            for y in range(64) for x in range(80)]
frame = [max(0, min(4095, value + (((index * 43 + index // 80 * 11) % 401) - 200)))
         for index, value in enumerate(baseline)]
with R2Pipe(Path(sys.argv[1])) as pipe:
    output = pipe.preprocess(baseline, frame)
assert hashlib.sha256(output).hexdigest() == \
    "2ff834cdef0316b3280d86a46fa75881c50bff3f4240e03dc31c24f6fc4153b3"
output[:] = b"\x00" * len(output)
PY
  actual=$(sha256sum "$source_root/Rockytkg/src/goodixgf.c" | awk '{print $1}')
  [[ $actual == cb2fffe7539bac17e70a7d2ed8c01dd5fe4a275a02a430805b6ed6aa5b4fbacd ]] ||
    refuse ROCKYTKG_POLICY_SOURCE_DRIFT
  echo D279_56_POLICY_UNIT_TESTS=PASS
  echo D279_56_R2_PRODUCTION_KAT=PASS
  echo D279_56_HELPER_FORBIDDEN_SYMBOL_AUDIT=PASS
}

verify_python_closure ()
{
  local snapshot=$1
  (
    cd "$snapshot"
    env -u PYTHONPATH -u PYTHONHOME -u PYTHONOPTIMIZE PYTHONNOUSERSITE=1 \
      python3 -B - <<'PY'
import importlib.util
import sys
from pathlib import Path

root = Path.cwd()
def load(name, relative):
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{relative}_NOT_REGULAR")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{relative}_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

load("d279_56_closure_d33", "analysis/D279/d279_33_attempt02_in_memory_composer.py")
load("d279_56_closure_d35", "operator_kit/d279-35-offline-protected-evaluation/d279_35_protected_attempt02_eval.py")
load("d279_56_closure_policy", "analysis/D279/d279_56_dynamic_enrollment_policy.py")
load("d279_56_closure_protected", "operator_kit/d279-56-offline-protected-dynamic-enrollment/d279_56_protected_replay.py")
print("D279_56_SNAPSHOT_PYTHON_CLOSURE=PASS")
PY
  ) || refuse SNAPSHOT_PYTHON_DEPENDENCY_CLOSURE
}

offline_preflight ()
{
  local work
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_REQUIRES_NORMAL_USER
  work=$(mktemp -d /tmp/goodix-d279-56-offline.XXXXXX)
  cleanup_root=$work
  trap cleanup_temp EXIT HUP INT TERM
  build_and_test "$root" "$work"
  echo D279_56_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
  echo TARGET_PSK_ACCESSED=false
  echo REAL_RASTER_EVALUATED_COUNT=0
  echo LIVE_OR_USB_ACTION_COUNT=0
  cleanup_temp
  cleanup_root=
  trap - EXIT HUP INT TERM
}

write_manifests ()
{
  local prepared=$1
  (cd "$prepared/snapshot" && find . -type f -print0 | sort -z |
    xargs -0 sha256sum) >"$prepared/snapshot.sha256"
  (cd "$prepared" && sha256sum d279_56_r2_pipe) >"$prepared/artifacts.sha256"
}

prepare_authorized_study ()
{
  local approved=$1 prepared snapshot state snapshot_hash artifact_hash capture_hash
  [[ $EUID -ne 0 ]] || refuse PREPARE_REQUIRES_NORMAL_USER
  verify_baseline "$approved"
  prepared=$(mktemp -d /tmp/goodix-d279-56-authorized.XXXXXX)
  chmod 0700 "$prepared"
  cleanup_root=$prepared
  trap cleanup_temp EXIT HUP INT TERM
  snapshot="$prepared/snapshot"
  mkdir -m 0700 "$snapshot"
  git_root archive "$approved" -- "${critical_paths[@]}" | tar -x -C "$snapshot"
  verify_python_closure "$snapshot"
  build_and_test "$snapshot" "$prepared"
  verify_baseline "$approved"
  write_manifests "$prepared"
  snapshot_hash=$(sha256sum "$prepared/snapshot.sha256" | awk '{print $1}')
  artifact_hash=$(sha256sum "$prepared/artifacts.sha256" | awk '{print $1}')
  capture_hash=$(sha256sum "$snapshot/$capture_relative" | awk '{print $1}')
  [[ $capture_hash == 3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab ]] ||
    refuse CAPTURE_HASH
  state="$prepared/d279-56-prepared.state"
  {
    echo "D279_56_BASELINE_SHA=$approved"
    echo "D279_56_OPERATION=$operation"
    echo "D279_56_PREPARED_DIR=$prepared"
    echo "D279_56_SNAPSHOT_MANIFEST_SHA256=$snapshot_hash"
    echo "D279_56_ARTIFACT_MANIFEST_SHA256=$artifact_hash"
    echo "D279_56_CAPTURE_SHA256=$capture_hash"
    echo "D279_56_AUTHORITY_SOURCE_SHA256=9b93693a27eaa6456b1d72a13d0d61e9bd01a3cd0842ae6f9e5c530ec9c631f6"
  } >"$state"
  chmod 0600 "$state" "$prepared/snapshot.sha256" "$prepared/artifacts.sha256"
  echo AUTHORIZED_STUDY_PREPARED=true
  echo "BASELINE_SHA=$approved"
  echo "PREPARED_DIRECTORY=$prepared"
  echo "NEXT_COMMAND=sudo $0 --run-authorized-study $prepared"
  echo TARGET_PSK_ACCESSED=false
  echo LIVE_OR_USB_ACTION_COUNT=0
  cleanup_root=
  trap - EXIT HUP INT TERM
}

verify_manifests ()
{
  local prepared=$1 state=$2 snapshot_count expected_count
  [[ $(sha256sum "$prepared/snapshot.sha256" | awk '{print $1}') == \
    $(state_value "$state" D279_56_SNAPSHOT_MANIFEST_SHA256) ]] ||
    refuse SNAPSHOT_MANIFEST_HASH
  [[ $(sha256sum "$prepared/artifacts.sha256" | awk '{print $1}') == \
    $(state_value "$state" D279_56_ARTIFACT_MANIFEST_SHA256) ]] ||
    refuse ARTIFACT_MANIFEST_HASH
  (cd "$prepared/snapshot" && sha256sum -c "$prepared/snapshot.sha256" >/dev/null) ||
    refuse SNAPSHOT_CONTENT_HASH
  (cd "$prepared" && sha256sum -c artifacts.sha256 >/dev/null) ||
    refuse ARTIFACT_CONTENT_HASH
  snapshot_count=$(find "$prepared/snapshot" -mindepth 1 ! -type d | wc -l)
  expected_count=$(wc -l <"$prepared/snapshot.sha256")
  [[ $snapshot_count -eq $expected_count ]] || refuse SNAPSHOT_EXTRA_OR_MISSING_FILE
}

run_authorized_study ()
{
  local prepared=$1 state approved result_root result_dir output log status export_dir
  local operator_uid operator_gid
  [[ $EUID -eq 0 ]] || refuse RUN_REQUIRES_ROOT
  [[ -n ${SUDO_UID:-} && -n ${SUDO_GID:-} && $SUDO_UID != 0 ]] ||
    refuse RUN_REQUIRES_VISIBLE_SUDO_OPERATOR
  operator_uid=$SUDO_UID
  operator_gid=$SUDO_GID
  require_private_directory "$prepared" "$operator_uid"
  state="$prepared/d279-56-prepared.state"
  [[ -f $state && ! -L $state && $(stat -c '%u:%a' "$state") == "$operator_uid:600" ]] ||
    refuse PREPARED_STATE_INVALID
  approved=$(state_value "$state" D279_56_BASELINE_SHA) || refuse STATE_BASELINE
  verify_baseline "$approved"
  [[ $(state_value "$state" D279_56_OPERATION) == "$operation" ]] || refuse STATE_OPERATION
  [[ $(state_value "$state" D279_56_PREPARED_DIR) == "$prepared" ]] || refuse STATE_DIRECTORY
  [[ $(state_value "$state" D279_56_CAPTURE_SHA256) == \
    3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab ]] ||
    refuse STATE_CAPTURE_HASH
  [[ $(state_value "$state" D279_56_AUTHORITY_SOURCE_SHA256) == \
    9b93693a27eaa6456b1d72a13d0d61e9bd01a3cd0842ae6f9e5c530ec9c631f6 ]] ||
    refuse STATE_AUTHORITY_HASH
  verify_manifests "$prepared" "$state"
  command -v timeout >/dev/null 2>&1 || refuse HOST_TIMEOUT_NOT_FOUND

  result_root=/var/tmp/goodix-d279-56-results
  if [[ ! -e $result_root && ! -L $result_root ]]; then
    mkdir -m 0700 "$result_root"
  fi
  require_private_directory "$result_root" 0
  result_dir="$result_root/$(date -u +%Y%m%dT%H%M%SZ)-${approved:0:12}"
  mkdir -m 0700 "$result_dir"
  output="$result_dir/summary.json"
  log="$result_dir/operator.log"
  set +e
  cd "$prepared/snapshot"
  env -u PYTHONPATH -u PYTHONHOME -u PYTHONOPTIMIZE PYTHONNOUSERSITE=1 \
    D279_56_AUTHORIZED_OPERATION="$operation" \
    D279_56_AUTHORIZED_SHA="$approved" \
    timeout --signal=TERM --kill-after=10s 5m \
    python3 -B operator_kit/d279-56-offline-protected-dynamic-enrollment/d279_56_protected_replay.py \
      --baseline "$approved" \
      --capture "$prepared/snapshot/$capture_relative" \
      --helper "$prepared/d279_56_r2_pipe" \
      --output "$output" >"$log" 2>&1
  status=$?
  cd "$root"
  set -e
  chmod 0600 "$log"
  if [[ $status -eq 0 && -f $output && ! -L $output ]]; then
    if env -u PYTHONOPTIMIZE PYTHONNOUSERSITE=1 python3 -B \
      "$prepared/snapshot/operator_kit/d279-56-offline-protected-dynamic-enrollment/d279_56_validate_summary.py" \
      "$output" "$approved"; then
      chmod 0600 "$output"
    else
      status=4
      echo OUTPUT_VALIDATION=FAIL_CLOSED >>"$log"
    fi
  fi
  chown -R "$operator_uid:$operator_gid" "$result_dir"
  if [[ $status -eq 0 ]]; then
    export_dir=$(mktemp -d /tmp/goodix-d279-56-export.XXXXXX)
    chmod 0700 "$export_dir"
    cp "$output" "$export_dir/summary.json"
    cp "$log" "$export_dir/operator.log"
    chmod 0600 "$export_dir/summary.json" "$export_dir/operator.log"
    chown -R "$operator_uid:$operator_gid" "$export_dir"
    echo "EXPORT_DIRECTORY=$export_dir"
  fi
  echo "RESULT_DIRECTORY=$result_dir"
  echo "RUN_EXIT_STATUS=$status"
  echo RETRY_WITHIN_AUTHORIZED_STUDY=true
  echo NEW_USER_AUTHORIZATION_REQUIRED=false
  echo LIVE_OR_USB_ACTION_COUNT=0
  [[ $status -eq 0 ]] || exit "$status"
}

case ${1:-} in
  --offline-preflight)
    [[ $# -eq 1 ]] || usage
    offline_preflight
    ;;
  --prepare-authorized-study)
    [[ $# -eq 2 ]] || usage
    prepare_authorized_study "$2"
    ;;
  --run-authorized-study)
    [[ $# -eq 2 ]] || usage
    run_authorized_study "$2"
    ;;
  *) usage ;;
esac
