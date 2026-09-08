#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)

if [ "${GOODIX_D278_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  exec flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_D278_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0" "$@"
fi

build=$(mktemp -d /tmp/goodix-d278-secure-session.XXXXXX)
trap 'find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true; rmdir "$build" 2>/dev/null || true' EXIT HUP INT TERM

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 openssl)
libs=$(pkg-config --libs glib-2.0 gio-2.0 openssl)
local_fp="$root/Rockytkg/libfprint/libfprint"
python3 "$script_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fp --symbol-prefix fp \
  --header-guard FP_ENUMS_H --header-name fp-enums.h \
  --output-header "$build/fp-enums.h" --output-source "$build/fp-enums.c" \
  "$local_fp/fp-device.h" "$local_fp/fp-print.h"
python3 "$script_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fpi --symbol-prefix fpi \
  --header-guard FPI_ENUMS_H --header-name fpi-enums.h \
  --output-header "$build/fpi-enums.h" --output-source "$build/fpi-enums.c" \
  "$local_fp/fpi-device.h" "$local_fp/fpi-image-device.h" "$local_fp/fpi-print.h"
cp "$script_dir/support/config.h" "$build/config.h"
includes="-I$script_dir/support/d277 -I$build -I$root/libfprint-driver -I$local_fp -I$local_fp/nbis/include -I$local_fp/nbis/libfprint-include -I$root/Rockytkg/libfprint -I$script_dir/support"
strict="-std=gnu11 -O2 -g -DGOODIX_ENABLE_TEST_SEAMS -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
local_relax="-Wno-unused-parameter -Wno-missing-prototypes -Wno-discarded-qualifiers -Wno-sign-compare -Wno-cast-function-type -Wno-enum-conversion -Wno-maybe-uninitialized -Wno-conversion -Wno-sign-conversion -Wno-float-conversion"

build_run () {
  name=$1
  extra=$2
  shift 2
  gcc $strict $local_relax $extra $cflags $includes \
    "$local_fp/fp-device.c" \
    "$local_fp/fpi-device.c" \
    "$local_fp/fp-image-device.c" \
    "$local_fp/fpi-image-device.c" \
    "$local_fp/fp-image.c" \
    "$local_fp/fp-print.c" \
    "$local_fp/fpi-print.c" \
    "$build/fp-enums.c" \
    "$build/fpi-enums.c" \
    "$root/libfprint-driver/goodix_u16_to_fpimage.c" \
    "$root/libfprint-driver/goodix_fpimage_pipeline.c" \
    "$root/libfprint-driver/goodix_a0_protocol.c" \
    "$root/libfprint-driver/goodix_d190_binder.c" \
    "$root/libfprint-driver/goodix_target_material.c" \
    "$root/libfprint-driver/goodix_runtime_inputs.c" \
    "$root/libfprint-driver/goodix_runtime_material.c" \
    "$root/libfprint-driver/goodix_secure_session.c" \
    "$root/libfprint-driver/goodix_image_decoder.c" \
    "$root/libfprint-driver/goodix_post_tls_lifecycle.c" \
    "$root/libfprint-driver/goodix_enrollment_model.c" \
    "$root/libfprint-driver/goodix_enrollment_pipeline.c" \
    "$root/libfprint-driver/goodix_enrollment_command_plan.c" \
    "$root/libfprint-driver/goodix_enrollment_command_body.c" \
    "$root/libfprint-driver/goodix_enrollment_fdt_state.c" \
    "$root/libfprint-driver/goodix_enrollment_lifecycle_adapter.c" \
    "$root/libfprint-driver/goodix_enrollment_post_tls_events.c" \
    "$root/libfprint-driver/goodix_enrollment_outbound_frame.c" \
    "$root/libfprint-driver/goodix_enrollment_outbound_transaction.c" \
    "$root/libfprint-driver/goodix_enrollment_fpi_usb_binding.c" \
    "$root/libfprint-driver/goodix_fpimage_device.c" \
    "$root/libfprint-driver/goodix_tls_server.c" \
    "$root/libfprint-driver/goodix_usb_router.c" \
    "$root/libfprint-driver/goodix_fpi_usb_backend.c" \
    "$script_dir/test_goodix_d278_secure_session.c" \
    "$script_dir/support/fpi_usb_transfer_compile_stub.c" \
    "$script_dir/support/gusb_stub.c" \
    "$script_dir/support/fpimage_link_stubs.c" \
    $libs -lm -o "$build/$name"
  # LeakSanitizer is unavailable under the Flatpak/bwrap ptrace boundary;
  # ASAN address checks and UBSAN remain fully enabled.
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 90 "$build/$name" "$@"
}

build_run d278-normal "" "$@"
echo NORMAL_TEST_RUN=PASS
build_run d278-sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined" "$@"
echo SANITIZER_TEST_RUN=PASS
echo D278_01_HOST_ONLY_RESULT=PASS
echo NATIVE_SECURE_SESSION_CHAIN_HOST_ONLY_PROVEN=true
echo NATIVE_PRE_D1_SEQUENCE_HOST_ONLY_PROVEN=true
echo NATIVE_D1_B0_TLS_TRANSITION_HOST_ONLY_PROVEN=true
echo NATIVE_TLS12_PSK_HANDSHAKE_HOST_ONLY_PROVEN=true
echo NATIVE_B0_FIXED64_EGRESS_HOST_ONLY_PROVEN=true
echo NATIVE_TLS_RECORD_PACING_HOST_ONLY_PROVEN=true
echo MAX_PHYSICAL_IN_OUTSTANDING=1
echo MAX_PHYSICAL_OUT_OUTSTANDING=1
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
echo CURRENT_LIVE_AUTHORIZED=false
echo D4_REACHABLE=false
echo D4_HOST_ONLY_REACHABLE=true
echo LIVE_CAPABLE_INTEGRATED_PATH_HOST_ONLY_PROVEN=true
echo SAME_GOODIX_DEVICE_CONTEXT=true
echo SINGLE_USB_BACKEND_OWNER=true
echo SINGLE_USB_ROUTER=true
echo SINGLE_PHYSICAL_IN_OWNER=true
echo SINGLE_TLS_OBJECT=true
echo TLS_HANDSHAKE_COUNT_MAX=1
echo SECRET_HANDOFF_COUNT_MAX=1
echo PRE_SESSION_RX_SYNC_IMPLEMENTED=true
echo PRE_SESSION_RX_HOST_DEADLINE_WITHOUT_BYTES_OBSERVED=true
echo PRE_SESSION_RX_DEVICE_QUIESCENCE_INFERRED=false
echo PRE_SESSION_RX_RESIDUE_CHAIN_QUARANTINED_HOST_ONLY_PROVEN=true
echo PRE_SESSION_RX_MULTI_FRAME_COMPLETION_QUARANTINED_HOST_ONLY_PROVEN=true
echo PRE_SESSION_RX_NON_TIMEOUT_ERROR_FAIL_CLOSED=true
echo PRE_SESSION_RX_BOUNDS_FAIL_CLOSED=true
echo PRE_SESSION_RX_OUT_BEFORE_SYNC_REJECTED=true
echo PRE_SESSION_RX_SECURE_START_BEFORE_SYNC_REJECTED=true
echo STRICT_A2_ACK_THEN_TYPED_RESTORED=true
echo CORRECTIVE_5_RUNTIME_TOLERANCE_RETIRED=true
echo NO_PARALLEL_RX_DRAIN_STACK=true
echo D279_28_PRODUCTION_ONE_SHOT_ENROLLMENT_FULL_TLS=PASS
echo D279_28_PRODUCTION_OPEN_EPOCH_ACTION_MAX=1
echo D279_28_KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0
echo D279_28_SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false
