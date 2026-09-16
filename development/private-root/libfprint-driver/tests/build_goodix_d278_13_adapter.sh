#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

canonical_repo_root () {
  _dir=$1
  while [ "$_dir" != "/" ]; do
    if [ -e "$_dir/.git" ]; then
      printf '%s\n' "$_dir"
      return 0
    fi
    _dir=$(dirname "$_dir")
  done
  return 1
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(canonical_repo_root "$script_dir") || {
  echo "canonical_repo_root: no .git found above $script_dir" >&2
  exit 2
}
approved=${D278_13_BUILD_APPROVED_BASELINE_SHA:-UNAPPROVED_FOR_LIVE}

git_in () {
  _dir=$1
  shift
  git -C "$_dir" -c safe.directory="$_dir" "$@"
}
snapshot=
host_gusb=

live_critical_paths='operator_kit/d278-13-integrated-path-once.sh
libfprint-driver/tests/build_goodix_d278_13_adapter.sh
libfprint-driver/tests/build_goodix_d278_13_adapter_inner.sh
libfprint-driver/tests/support/generate_libfprint_enums.py
libfprint-driver/tests/support/config.h
libfprint-driver/tests/support/fpimage_link_stubs.c
libfprint-driver/tests/support/test_sigfm_control.h
libfprint-driver/tests/support/d277/gusb.h
libfprint-driver/goodix_u16_to_fpimage.c
libfprint-driver/goodix_u16_to_fpimage.h
libfprint-driver/goodix_fpimage_pipeline.c
libfprint-driver/goodix_fpimage_pipeline.h
libfprint-driver/goodix_usb_router.c
libfprint-driver/goodix_usb_router.h
libfprint-driver/goodix_a0_protocol.c
libfprint-driver/goodix_a0_protocol.h
libfprint-driver/goodix_d190_binder.c
libfprint-driver/goodix_d190_binder.h
libfprint-driver/goodix_target_material.c
libfprint-driver/goodix_target_material.h
libfprint-driver/goodix_runtime_inputs.c
libfprint-driver/goodix_runtime_inputs.h
libfprint-driver/goodix_runtime_material.c
libfprint-driver/goodix_runtime_material.h
libfprint-driver/goodix_secure_session.c
libfprint-driver/goodix_secure_session.h
libfprint-driver/goodix_image_decoder.c
libfprint-driver/goodix_image_decoder.h
libfprint-driver/goodix_fdt_irq_policy.c
libfprint-driver/goodix_fdt_irq_policy.h
libfprint-driver/goodix_post_tls_lifecycle.c
libfprint-driver/goodix_post_tls_lifecycle.h
libfprint-driver/goodix_fpimage_device.c
libfprint-driver/goodix_fpimage_device.h
libfprint-driver/goodix_tls_server.c
libfprint-driver/goodix_tls_server.h
libfprint-driver/goodix_fpi_usb_backend.c
libfprint-driver/goodix_fpi_usb_backend.h
tools/goodix_d190_pe.c
tools/goodix_d190_pe.h
tools/d278_integrated_path_once.c
Rockytkg/libfprint/libfprint/fp-device.c
Rockytkg/libfprint/libfprint/fpi-device.c
Rockytkg/libfprint/libfprint/fp-image-device.c
Rockytkg/libfprint/libfprint/fpi-image-device.c
Rockytkg/libfprint/libfprint/fp-image.c
Rockytkg/libfprint/libfprint/fp-print.c
Rockytkg/libfprint/libfprint/fpi-print.c
Rockytkg/libfprint/libfprint/fpi-usb-transfer.c'

guard_refused () {
  echo "LIVE_BASELINE_MATCH=$1" >&2
  echo "LIVE_CRITICAL_SET_CLEAN=$2" >&2
  echo APPROVED_LIVE_BUILD_REFUSED=true >&2
  echo "BASELINE_GUARD_REASON=$3" >&2
  return 1
}

verify_live_baseline () {
  guard_root=$1
  guard_approved=$2
  case "$guard_approved" in
    ????????????????????????????????????????)
      echo "$guard_approved" | grep -Eq '^[0-9a-fA-F]{40}$' || {
        guard_refused false unknown INVALID_APPROVED_SHA
        return 1
      }
      ;;
    *)
      guard_refused false unknown INVALID_APPROVED_SHA
      return 1
      ;;
  esac
  git_in "$guard_root" cat-file -e "$guard_approved^{commit}" 2>/dev/null || {
    guard_refused false unknown APPROVED_COMMIT_NOT_LOCAL
    return 1
  }
  resolved=$(git_in "$guard_root" rev-parse "$guard_approved^{commit}")
  head=$(git_in "$guard_root" rev-parse HEAD)
  if [ "$head" != "$resolved" ]; then
    guard_refused false unknown HEAD_MISMATCH
    return 1
  fi
  header_paths=$(git_in "$guard_root" ls-tree -r --name-only "$resolved" -- \
    Rockytkg/libfprint/libfprint | grep '\.h$' | grep -v '/tests/' || true)
  set -- $live_critical_paths $header_paths
  if [ -n "$(git_in "$guard_root" status --porcelain --untracked-files=all -- "$@")" ]; then
    guard_refused true false LIVE_CRITICAL_SOURCE_DIRTY
    return 1
  fi
  echo LIVE_BASELINE_MATCH=true
  echo LIVE_CRITICAL_SET_CLEAN=true
  echo APPROVED_LIVE_BUILD_REFUSED=false
  printf '%s\n' "$resolved"
}

if [ "${D278_13_BASELINE_GUARD_TEST_ONLY:-0}" = 1 ]; then
  test_root=${D278_13_BASELINE_GUARD_TEST_ROOT:?missing test root}
  test "$approved" != UNAPPROVED_FOR_LIVE
  verify_live_baseline "$test_root" "$approved" >/dev/null
  echo D278_13_BASELINE_GUARD_TEST_ONLY=PASS
  exit 0
fi

if [ -n "${D278_13_BUILD_DIR:-}" ]; then
  build=$D278_13_BUILD_DIR
  owned=0
else
  build=$(mktemp -d /tmp/goodix-d278-13-adapter.XXXXXX)
  owned=1
fi

cleanup () {
  if [ -n "$snapshot" ]; then
    find "$snapshot" -depth -delete 2>/dev/null || true
  fi
  if [ "$owned" = 0 ] || [ "${KEEP_BUILD:-0}" = 1 ]; then
    echo "D278_13_BUILD_DIR=$build"
    return
  fi
  find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true
  rmdir "$build" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

source_root=$root
if [ "$approved" != UNAPPROVED_FOR_LIVE ]; then
  guard_output=$(verify_live_baseline "$root" "$approved") || exit 1
  approved=$(printf '%s\n' "$guard_output" | tail -n 1)
  snapshot=$(mktemp -d /tmp/goodix-d278-13-approved-source.XXXXXX)
  git_in "$root" archive "$approved" -- \
    libfprint-driver tools operator_kit Rockytkg/libfprint/libfprint | \
    tar -x -C "$snapshot"
  source_root=$snapshot
fi
inner="$source_root/libfprint-driver/tests/build_goodix_d278_13_adapter_inner.sh"
if [ "$approved" = UNAPPROVED_FOR_LIVE ]; then
  test_reference=$(git_in "$root" rev-parse HEAD)
else
  test_reference=$approved
fi
test_other_reference=$(git_in "$root" rev-parse "$test_reference^")

for candidate in \
  /usr/lib64/libgusb.so.2.0.10 \
  /usr/lib64/libgusb.so.2 \
  /usr/lib/x86_64-linux-gnu/libgusb.so.2; do
  if [ -f "$candidate" ]; then
    host_gusb=$candidate
    break
  fi
done
test -n "$host_gusb" || {
  echo "BLOCKED_ENVIRONMENT: installed libgusb runtime not found" >&2
  exit 2
}
mkdir -p "$build"
cp "$host_gusb" "$build/libgusb.so.2"

if command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  flatpak run --user --unshare=network \
    --filesystem="$source_root":ro --filesystem=/tmp \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$source_root" "$build" "$build/libgusb.so.2" "$approved" \
    "$test_reference" "$test_other_reference"
else
  echo EXECUTION_ENVIRONMENT=HOST
  "$inner" "$source_root" "$build" "$build/libgusb.so.2" "$approved" \
    "$test_reference" "$test_other_reference"
fi

if [ "$approved" != UNAPPROVED_FOR_LIVE ]; then
  verify_live_baseline "$root" "$approved" >/dev/null
  test -x "$build/d278_integrated_path_once.pending"
  mv "$build/d278_integrated_path_once.pending" \
    "$build/d278_integrated_path_once"
fi

test -x "$build/d278_integrated_path_once"
ldd "$build/d278_integrated_path_once"
sha256sum "$build/d278_integrated_path_once"
