#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077
unset PYTHONHOME PYTHONOPTIMIZE PYTHONPATH

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
cd "$root"
operation=D279_48_ONE_OFFLINE_PROTECTED_ROCKY_NBIS_SIGFM_COMPARISON
capture_relative=captures/D279_10/D27910_20260905_ATTEMPT02/raw/wire.pcapng
r0_relative=captures/D279_46/D27946_20260906_USER_SUPPLIED/sanitized/summary.json
cleanup_root=

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
  echo PROTECTED_GATE_REFUSED=true >&2
  echo "PROTECTED_GATE_REFUSAL_REASON=$1" >&2
  echo TARGET_PSK_ACCESSED=false >&2
  echo LIVE_OR_USB_ACTION_COUNT=0 >&2
  exit 3
}

cleanup_temp ()
{
  if [[ ${cleanup_root:-} == /tmp/goodix-d279-48-offline.* ]]; then
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
  analysis/D279/d279_39_nbis_quality_evaluator.py
  analysis/D279/d279_48_rocky_imgproc_noenv.h
  analysis/D279/d279_48_rocky_imgproc_pipe.c
  analysis/D279/d279_48_rocky_nbis_sigfm_evaluator.py
  analysis/D279/test_d279_48_rocky_nbis_sigfm_evaluator.py
  core/post_d4.py
  libfprint-driver
  reference/libfprint-fedora44-1.94.100/source
  Rockytkg/PROVENANCE.md
  Rockytkg/include/goodix.h
  Rockytkg/include/goodix_imgproc.h
  Rockytkg/src/goodix_imgproc.c
  Rockytkg/libfprint/libfprint/sigfm
  operator_kit/d279-35-offline-protected-evaluation/d279_35_protected_attempt02_eval.py
  operator_kit/d279-48-offline-protected-rocky-nbis-sigfm
  "$capture_relative"
  "$r0_relative"
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

find_host_library ()
{
  local name=$1 candidate
  for candidate in /usr/lib64/"$name" /usr/lib/x86_64-linux-gnu/"$name"; do
    [[ -f $candidate ]] && { printf '%s\n' "$candidate"; return 0; }
  done
  return 1
}

verify_host_sigfm_runtime ()
{
  [[ $(rpm -q tbb) == tbb-2022.3.0-3.fc44.x86_64 ]] || refuse HOST_TBB_PACKAGE_DRIFT
  [[ $(rpm -q flexiblas) == flexiblas-3.5.0-2.fc44.x86_64 ]] ||
    refuse HOST_FLEXIBLAS_PACKAGE_DRIFT
  [[ $(rpm -q flexiblas-netlib) == flexiblas-netlib-3.5.0-2.fc44.x86_64 ]] ||
    refuse HOST_FLEXIBLAS_BACKEND_DRIFT
  [[ $(rpm -q libstdc++.x86_64) == libstdc++-16.2.1-2.fc44.x86_64 ]] ||
    refuse HOST_LIBSTDCXX_PACKAGE_DRIFT
}

download_and_extract_opencv ()
{
  local snapshot=$1 work=$2 rpms prefix package
  rpms="$work/opencv-rpms"
  prefix="$work/opencv-prefix"
  mkdir -p "$rpms" "$prefix" "$work/dnf-log"
  command -v dnf >/dev/null 2>&1 || refuse DNF_NOT_FOUND
  command -v rpm2cpio >/dev/null 2>&1 || refuse RPM2CPIO_NOT_FOUND
  command -v cpio >/dev/null 2>&1 || refuse CPIO_NOT_FOUND
  dnf --setopt="logdir=$work/dnf-log" download --destdir="$rpms" \
    opencv-core-4.13.0-1.fc44.x86_64 \
    opencv-devel-4.13.0-1.fc44.x86_64 \
    opencv-features2d-4.13.0-1.fc44.x86_64 \
    opencv-flann-4.13.0-1.fc44.x86_64 \
    opencv-imgproc-4.13.0-1.fc44.x86_64
  (cd "$rpms" && sha256sum -c \
    "$snapshot/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256")
  for package in "$rpms"/*.rpm; do
    (cd "$prefix" && rpm2cpio "$package" | cpio -idm --quiet)
  done
}

build_snapshot_helpers ()
{
  local snapshot=$1 work=$2 kit inner host_gusb host_tbb host_flexi opencv
  kit="$snapshot/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm"
  inner="$kit/build-inner.sh"
  download_and_extract_opencv "$snapshot" "$work"
  mkdir -p "$work/pkgconfig" "$work/runtime"
  host_gusb=$(find_host_library libgusb.so.2) || refuse HOST_GUSB_RUNTIME_NOT_FOUND
  host_tbb=$(find_host_library libtbb.so.12) || refuse HOST_TBB_RUNTIME_NOT_FOUND
  host_flexi=$(find_host_library libflexiblas.so.3) || refuse HOST_FLEXIBLAS_RUNTIME_NOT_FOUND
  cp -L "$host_gusb" "$work/pkgconfig/libgusb.so.2"
  verify_host_sigfm_runtime
  sed -e "s|@PREFIX@|$work/pkgconfig|g" \
      -e "s|@INCLUDEDIR@|$snapshot/libfprint-driver/tests/support/d279|g" \
      "$snapshot/libfprint-driver/tests/support/d279/gusb.pc.in" \
      >"$work/pkgconfig/gusb.pc"
  command -v flatpak >/dev/null 2>&1 || refuse FLATPAK_NOT_FOUND
  flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1 ||
    refuse FREEDESKTOP_SDK_NOT_FOUND
  flatpak run --user --unshare=network \
    --filesystem="$snapshot":ro \
    --filesystem="$work" \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$snapshot" "$work" "$work/opencv-prefix" "$work/pkgconfig"

  for opencv in core features2d flann imgproc; do
    cp -L "$work/opencv-prefix/usr/lib64/libopencv_${opencv}.so.4.13.0" \
      "$work/runtime/libopencv_${opencv}.so.413"
  done
  command -v gcc >/dev/null 2>&1 || refuse HOST_GCC_LINK_DRIVER_NOT_FOUND
  gcc "$work/objects/sigfm.o" "$work/objects/sigfm-pipe.o" \
    -Wl,--gc-sections -Wl,--no-undefined '-Wl,-rpath,$ORIGIN/runtime' \
    "$work/runtime/libopencv_features2d.so.413" \
    "$work/runtime/libopencv_flann.so.413" \
    "$work/runtime/libopencv_imgproc.so.413" \
    "$work/runtime/libopencv_core.so.413" \
    "$host_tbb" "$host_flexi" \
    /usr/lib64/libstdc++.so.6 -lm -o "$work/d279_sigfm_pair.pending"

  mv "$work/d279_rocky_imgproc.pending" "$work/d279_rocky_imgproc"
  mv "$work/d279_nbis_pair.pending" "$work/d279_nbis_pair"
  mv "$work/d279_sigfm_pair.pending" "$work/d279_sigfm_pair"
  chmod 0700 "$work/d279_rocky_imgproc" "$work/d279_nbis_pair" "$work/d279_sigfm_pair"
  chmod 0600 "$work/runtime"/*

  for opencv in core features2d flann imgproc; do
    LD_LIBRARY_PATH="$work/runtime" ldd "$work/d279_sigfm_pair" |
      grep -F "$work/runtime/libopencv_${opencv}.so.413" >/dev/null ||
      refuse OPENCV_RUNTIME_NOT_PINNED
  done
  LD_LIBRARY_PATH="$work/runtime" ldd "$work/d279_sigfm_pair" |
    grep -F 'libtbb.so.12 => /lib64/libtbb.so.12' >/dev/null || refuse HOST_TBB_NOT_RESOLVED
  LD_LIBRARY_PATH="$work/runtime" ldd "$work/d279_sigfm_pair" |
    grep -F 'libflexiblas.so.3 => /lib64/libflexiblas.so.3' >/dev/null ||
    refuse HOST_FLEXIBLAS_NOT_RESOLVED
  if nm -D --undefined-only "$work/d279_rocky_imgproc" |
     grep -Eq '(^|[[:space:]])(getenv|open|openat|fopen|socket|g_usb_|libusb_)'; then
    refuse ROCKY_IMGPROC_FORBIDDEN_HOST_SEAM
  fi
  if nm "$work/d279_nbis_pair" "$work/d279_sigfm_pair" |
     grep -Eq 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)|libusb_'; then
    refuse EXTRACTOR_HELPER_USB_SEAM
  fi
  if readelf -d "$work/d279_rocky_imgproc" "$work/d279_nbis_pair" "$work/d279_sigfm_pair" |
     grep -Eqi 'libusb|libgusb|libssl|libcrypto'; then
    refuse HELPER_FORBIDDEN_RUNTIME_DEPENDENCY
  fi
  [[ $(sha256sum "$snapshot/Rockytkg/src/goodix_imgproc.c" | awk '{print $1}') == \
    177113b3e4e7d71b567850ea5f6ca02738987a2f11a793aa0ae303a585510043 ]] ||
    refuse ROCKY_IMGPROC_SOURCE_DRIFT
  [[ $(sha256sum "$snapshot/Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp" | awk '{print $1}') == \
    95ba50258d68a145841e3f51c4f9927ed5ec518e86f09b1222d725281f56c9c5 ]] ||
    refuse SIGFM_SOURCE_DRIFT
}

run_synthetic_kat ()
{
  local snapshot=$1 work=$2
  LD_LIBRARY_PATH="$work/runtime" PYTHONPATH="$snapshot/analysis/D279" python3 -B - \
    "$work/d279_rocky_imgproc" "$work/d279_nbis_pair" "$work/d279_sigfm_pair" <<'PY'
import hashlib
import sys
from pathlib import Path
from d279_48_rocky_nbis_sigfm_evaluator import (
    CHECKPOINTS, NbisPairPipe, RockyPreprocessPipe, SigfmPairPipe,
    evaluate_target_attempt,
)
pre_path, nbis_path, sigfm_path = map(Path, sys.argv[1:])
baseline = [1500 + ((x * 17 + y * 29 + (x * y) % 31) % 700)
            for y in range(64) for x in range(80)]
frame = [max(0, min(4095, value + (((index * 43 + index // 80 * 11) % 401) - 200)))
         for index, value in enumerate(baseline)]
expected = {
    CHECKPOINTS[0]: "2b586d2f2615f3eff4a2ed20570dace02956b26705edff509a92d6ccc0012b45",
    CHECKPOINTS[1]: "2ff834cdef0316b3280d86a46fa75881c50bff3f4240e03dc31c24f6fc4153b3",
}
with RockyPreprocessPipe(pre_path) as pipe:
    for checkpoint in CHECKPOINTS:
        output = pipe.preprocess(frame, baseline, checkpoint)
        assert hashlib.sha256(output).hexdigest() == expected[checkpoint]

checker = bytearray(255 if ((x // 20 + y // 20) & 1) else 0
                    for y in range(64) for x in range(80))
with SigfmPairPipe(sigfm_path) as pipe:
    first = pipe.extract(checker)
    second = pipe.extract(checker)
    assert first.keypoints == second.keypoints == 33
    assert pipe.match(first, second).score == pipe.match(second, first).score == 36

synthetic_baseline = [1800 + ((x * 3 + y * 5) % 37)
                      for y in range(64) for x in range(80)]
rasters = [synthetic_baseline]
for frame_index in range(42):
    raster = []
    for y in range(64):
        for x in range(80):
            delta = 240 if ((x // 20 + y // 20) & 1) else -240
            value = synthetic_baseline[y * 80 + x] + delta + (frame_index % 3 - 1) * 5
            raster.append(max(0, min(4095, value)))
    rasters.append(raster)
with RockyPreprocessPipe(pre_path) as preprocess, \
     NbisPairPipe(nbis_path) as nbis, SigfmPairPipe(sigfm_path) as sigfm:
    result = evaluate_target_attempt(rasters, preprocess, nbis, sigfm)
assert result["checkpoint_count"] == 2
assert all(item["same_preprocessed_raster_delivered_to_both_extractors"]
           for item in result["checkpoints"])
assert result["rasters_exported"] is False
assert result["templates_exported"] is False
PY
  echo D279_48_SYNTHETIC_END_TO_END=PASS
}

offline_preflight ()
{
  local work
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_REQUIRES_NORMAL_USER
  python3 -B -m unittest -q \
    analysis/D279/test_d279_31_attempt02_tls_reconstruction_feasibility.py \
    analysis/D279/test_d279_32_tls12_psk_decrypt.py \
    analysis/D279/test_d279_33_attempt02_in_memory_composer.py \
    analysis/D279/test_d279_39_nbis_quality_evaluator.py \
    analysis/D279/test_d279_48_rocky_nbis_sigfm_evaluator.py \
    operator_kit/d279-35-offline-protected-evaluation/test_d279_35_protected_attempt02_eval.py \
    operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/test_d279_48_protected_runner.py
  work=$(mktemp -d /tmp/goodix-d279-48-offline.XXXXXX)
  cleanup_root=$work
  trap cleanup_temp EXIT HUP INT TERM
  build_snapshot_helpers "$root" "$work"
  run_synthetic_kat "$root" "$work"
  echo D279_48_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
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
  (cd "$prepared" && sha256sum d279_rocky_imgproc d279_nbis_pair d279_sigfm_pair \
    runtime/*) >"$prepared/artifacts.sha256"
}

prepare_approved_analysis ()
{
  local approved=$1 prepared snapshot state snapshot_hash artifacts_hash capture_hash r0_hash
  [[ $EUID -ne 0 ]] || refuse PREPARE_REQUIRES_NORMAL_USER
  verify_approved_baseline "$approved"
  prepared=$(mktemp -d /tmp/goodix-d279-48-approved.XXXXXX)
  chmod 0700 "$prepared"
  snapshot="$prepared/snapshot"
  mkdir -m 0700 "$snapshot"
  git_root archive "$approved" -- "${critical_paths[@]}" | tar -x -C "$snapshot"
  build_snapshot_helpers "$snapshot" "$prepared"
  run_synthetic_kat "$snapshot" "$prepared"
  verify_approved_baseline "$approved"
  find "$prepared/nbis-build" "$prepared/objects" "$prepared/opencv-prefix" \
    "$prepared/opencv-rpms" "$prepared/dnf-log" "$prepared/include" \
    "$prepared/pkgconfig" -depth -delete
  write_manifests "$prepared"
  snapshot_hash=$(sha256sum "$prepared/snapshot.sha256" | awk '{print $1}')
  artifacts_hash=$(sha256sum "$prepared/artifacts.sha256" | awk '{print $1}')
  capture_hash=$(sha256sum "$snapshot/$capture_relative" | awk '{print $1}')
  r0_hash=$(sha256sum "$snapshot/$r0_relative" | awk '{print $1}')
  [[ $capture_hash == 3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab ]] ||
    refuse CAPTURE_HASH
  [[ $r0_hash == 7dfb2feab05a11b01830903c773211d811f5b9a55aac35bd478fd57e4707f90b ]] ||
    refuse R0_SUMMARY_HASH
  state="$prepared/d279-48-prepared.state"
  {
    echo "D279_48_BASELINE_SHA=$approved"
    echo "D279_48_OPERATION=$operation"
    echo "D279_48_PREPARED_DIR=$prepared"
    echo "D279_48_SNAPSHOT_MANIFEST_SHA256=$snapshot_hash"
    echo "D279_48_ARTIFACT_MANIFEST_SHA256=$artifacts_hash"
    echo "D279_48_CAPTURE_SHA256=$capture_hash"
    echo "D279_48_R0_SUMMARY_SHA256=$r0_hash"
    echo "D279_48_GRANT_ID=d27948-$approved"
  } >"$state"
  chmod 0600 "$state" "$prepared/snapshot.sha256" "$prepared/artifacts.sha256"
  echo APPROVED_ANALYSIS_PREPARED=true
  echo "APPROVED_BASELINE_SHA=$approved"
  echo "PREPARED_BUILD_DIR=$prepared"
  echo "SNAPSHOT_MANIFEST_SHA256=$snapshot_hash"
  echo "ARTIFACT_MANIFEST_SHA256=$artifacts_hash"
  echo "EXPECTED_GRANT_ID=d27948-$approved"
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
      echo "D279_48_BASELINE_SHA=$approved"
      echo "D279_48_OPERATION=$operation"
      echo "D279_48_GRANT_ID=d27948-$approved"
      echo D279_48_GRANT_STATE=UNCONSUMED
    } >"$grant"
  ) || refuse GRANT_OUTPUT_COLLISION
  chmod 0600 "$grant"
  echo GRANT_WRITTEN=true
  echo "GRANT_ID=d27948-$approved"
  echo TARGET_PSK_ACCESSED=false
}

verify_manifests ()
{
  local prepared=$1 state=$2 snapshot_count expected_count artifact_count expected_artifact_count
  [[ $(sha256sum "$prepared/snapshot.sha256" | awk '{print $1}') == \
    $(state_value "$state" D279_48_SNAPSHOT_MANIFEST_SHA256) ]] || refuse SNAPSHOT_MANIFEST_HASH
  [[ $(sha256sum "$prepared/artifacts.sha256" | awk '{print $1}') == \
    $(state_value "$state" D279_48_ARTIFACT_MANIFEST_SHA256) ]] || refuse ARTIFACT_MANIFEST_HASH
  (cd "$prepared/snapshot" && sha256sum -c "$prepared/snapshot.sha256" >/dev/null) ||
    refuse SNAPSHOT_CONTENT_HASH
  (cd "$prepared" && sha256sum -c artifacts.sha256 >/dev/null) ||
    refuse ARTIFACT_CONTENT_HASH
  snapshot_count=$(find "$prepared/snapshot" -mindepth 1 ! -type d | wc -l)
  expected_count=$(wc -l <"$prepared/snapshot.sha256")
  [[ $snapshot_count -eq $expected_count ]] || refuse SNAPSHOT_EXTRA_OR_MISSING_FILE
  artifact_count=$((3 + $(find "$prepared/runtime" -mindepth 1 ! -type d | wc -l)))
  expected_artifact_count=$(wc -l <"$prepared/artifacts.sha256")
  [[ $artifact_count -eq $expected_artifact_count ]] ||
    refuse ARTIFACT_EXTRA_OR_MISSING_FILE
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
  state="$prepared/d279-48-prepared.state"
  [[ -f $state && ! -L $state && $(stat -c '%u:%a' "$state") == "$operator_uid:600" ]] ||
    refuse PREPARED_STATE_INVALID
  approved=$(state_value "$state" D279_48_BASELINE_SHA) || refuse STATE_BASELINE
  verify_approved_baseline "$approved"
  [[ $(state_value "$state" D279_48_OPERATION) == "$operation" ]] || refuse STATE_OPERATION
  [[ $(state_value "$state" D279_48_PREPARED_DIR) == "$prepared" ]] || refuse STATE_DIRECTORY
  grant_id=$(state_value "$state" D279_48_GRANT_ID) || refuse STATE_GRANT_ID
  [[ -f $grant && ! -L $grant && $(stat -c '%u:%a' "$grant") == "$operator_uid:600" ]] ||
    refuse GRANT_FILE_INVALID
  [[ $(state_value "$grant" D279_48_BASELINE_SHA) == "$approved" ]] || refuse GRANT_BASELINE
  [[ $(state_value "$grant" D279_48_OPERATION) == "$operation" ]] || refuse GRANT_OPERATION
  [[ $(state_value "$grant" D279_48_GRANT_ID) == "$grant_id" ]] || refuse GRANT_ID
  [[ $(state_value "$grant" D279_48_GRANT_STATE) == UNCONSUMED ]] || refuse GRANT_STATE
  verify_manifests "$prepared" "$state"
  verify_host_sigfm_runtime
  LD_LIBRARY_PATH="$prepared/runtime" ldd "$prepared/d279_sigfm_pair" |
    grep -F 'libtbb.so.12 => /lib64/libtbb.so.12' >/dev/null || refuse HOST_TBB_NOT_RESOLVED
  LD_LIBRARY_PATH="$prepared/runtime" ldd "$prepared/d279_sigfm_pair" |
    grep -F 'libflexiblas.so.3 => /lib64/libflexiblas.so.3' >/dev/null ||
    refuse HOST_FLEXIBLAS_NOT_RESOLVED
  [[ $(state_value "$state" D279_48_CAPTURE_SHA256) == \
    3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab ]] ||
    refuse STATE_CAPTURE_HASH
  [[ $(state_value "$state" D279_48_R0_SUMMARY_SHA256) == \
    7dfb2feab05a11b01830903c773211d811f5b9a55aac35bd478fd57e4707f90b ]] ||
    refuse STATE_R0_HASH
  command -v timeout >/dev/null 2>&1 || refuse HOST_TIMEOUT_NOT_FOUND

  marker_root=/var/tmp/goodix-d279-48-consumed-grants
  if [[ ! -e $marker_root && ! -L $marker_root ]]; then mkdir -m 0700 "$marker_root"; fi
  require_private_directory "$marker_root" 0
  marker="$marker_root/$grant_id"
  mkdir -m 0700 "$marker" 2>/dev/null || refuse GRANT_ALREADY_CONSUMED

  result_root=/var/tmp/goodix-d279-48-results
  if [[ ! -e $result_root && ! -L $result_root ]]; then mkdir -m 0700 "$result_root"; fi
  require_private_directory "$result_root" 0
  result_dir="$result_root/$(date -u +%Y%m%dT%H%M%SZ)-${approved:0:12}"
  mkdir -m 0700 "$result_dir"
  log="$result_dir/operator.log"
  output="$result_dir/summary.json"
  set +e
  cd "$prepared/snapshot"
  env -u PYTHONPATH -u PYTHONHOME -u PYTHONOPTIMIZE \
    PYTHONNOUSERSITE=1 \
    D279_48_AUTHORIZED_OPERATION="$operation" \
    D279_48_AUTHORIZED_SHA="$approved" \
    LD_LIBRARY_PATH="$prepared/runtime" \
    timeout --signal=TERM --kill-after=10s 20m \
    python3 -B operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/d279_48_protected_rocky_nbis_sigfm_eval.py \
      --baseline "$approved" \
      --capture "$prepared/snapshot/$capture_relative" \
      --r0-summary "$prepared/snapshot/$r0_relative" \
      --preprocess-helper "$prepared/d279_rocky_imgproc" \
      --nbis-helper "$prepared/d279_nbis_pair" \
      --sigfm-helper "$prepared/d279_sigfm_pair" \
      --output "$output" >"$log" 2>&1
  status=$?
  cd "$root"
  set -e
  chmod 0600 "$log"
  if [[ $status -eq 0 && -f $output && ! -L $output ]]; then
    if env -u PYTHONOPTIMIZE PYTHONNOUSERSITE=1 python3 -B \
      "$prepared/snapshot/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/d279_48_validate_summary.py" \
      "$output" "$approved"; then
      chmod 0600 "$output"
    else
      status=4
      echo OUTPUT_VALIDATION=FAIL_CLOSED >>"$log"
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
