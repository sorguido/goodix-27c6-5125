#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)

if [ "${GOODIX_D279_14_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  exec flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_D279_14_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0"
fi

build=$(mktemp -d /tmp/goodix-d279-14-events.XXXXXX)
trap 'find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true; rmdir "$build" 2>/dev/null || true' EXIT HUP INT TERM
cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0)
local_fp="$root/Rockytkg/libfprint/libfprint"
includes="-I$build -I$script_dir/support/d277 -I$script_dir/support -I$root/libfprint-driver -I$root/Rockytkg/libfprint -I$local_fp -I$local_fp/nbis/include -I$local_fp/nbis/libfprint-include"
strict="-std=gnu11 -O2 -g -DGOODIX_ENABLE_TEST_SEAMS -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
local_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter"

python3 "$script_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fpi --symbol-prefix fpi \
  --header-guard FPI_ENUMS_H --header-name fpi-enums.h \
  --output-header "$build/fpi-enums.h" --output-source "$build/fpi-enums.c" \
  "$local_fp/fpi-device.h" "$local_fp/fpi-image-device.h" \
  "$local_fp/fpi-print.h"
python3 "$script_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fp --symbol-prefix fp \
  --header-guard FP_ENUMS_H --header-name fp-enums.h \
  --output-header "$build/fp-enums.h" --output-source "$build/fp-enums.c" \
  "$local_fp/fp-device.h" "$local_fp/fp-print.h"

if grep -En '(goodix_a0_build|goodix_fpi_usb|fixed64_command|submit_out|g_usb_|libusb_)' \
    "$root/libfprint-driver/goodix_enrollment_post_tls_events.c" \
    "$root/libfprint-driver/goodix_enrollment_post_tls_events.h"; then
  echo "serializer or sender dependency in D279/14 inbound event binding" >&2
  exit 1
fi
echo D279_14_INBOUND_ONLY_SOURCE_AUDIT=PASS
if grep -En '(goodix_fpi_usb|submit_out|g_usb_|libusb_)' \
    "$root/libfprint-driver/goodix_enrollment_outbound_transaction.c" \
    "$root/libfprint-driver/goodix_enrollment_outbound_transaction.h"; then
  echo "real backend dependency in D279/17 transaction" >&2
  exit 1
fi
echo D279_17_SYNTHETIC_SINK_SOURCE_AUDIT=PASS

run_build () {
  suffix=$1
  extra=$2
  for source in \
    goodix_a0_protocol.c \
    goodix_image_decoder.c \
    goodix_u16_to_fpimage.c \
    goodix_fpimage_pipeline.c \
    goodix_enrollment_model.c \
    goodix_enrollment_pipeline.c \
    goodix_enrollment_command_plan.c \
    goodix_enrollment_command_body.c \
    goodix_enrollment_fdt_state.c \
    goodix_enrollment_lifecycle_adapter.c \
    goodix_enrollment_post_tls_events.c \
    goodix_enrollment_outbound_frame.c \
    goodix_enrollment_outbound_transaction.c \
    goodix_usb_router.c \
    goodix_fpi_usb_backend.c \
    goodix_enrollment_fpi_usb_binding.c; do
    # shellcheck disable=SC2086
    gcc $strict $extra $cflags $includes -c \
      "$root/libfprint-driver/$source" \
      -o "$build/${source%.c}_${suffix}.o"
  done
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c \
    "$script_dir/test_goodix_enrollment_post_tls_events.c" \
    -o "$build/test_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $local_flags $extra $cflags $includes -c "$local_fp/fp-image.c" \
    -o "$build/fp-image_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $local_flags $extra $cflags $includes -c \
    "$script_dir/support/fpimage_link_stubs.c" \
    -o "$build/fpimage_stubs_${suffix}.o"
  # The production transfer function aborts if reached; the test configures
  # only the asynchronous host seam before any OUT.
  # shellcheck disable=SC2086
  gcc $local_flags $extra $cflags $includes -c \
    "$script_dir/support/fpi_usb_transfer_compile_stub.c" \
    -o "$build/fpi_usb_transfer_stub_${suffix}.o"
  if nm -u "$build/goodix_enrollment_post_tls_events_${suffix}.o" | \
     grep -E '(^|[[:space:]])(g_usb_|libusb_|SSL_|mbedtls_|gnutls_|open|read|write|socket)'; then
    echo "forbidden I/O, USB or TLS symbol in D279/14 event binding" >&2
    exit 1
  fi
  # shellcheck disable=SC2086
  gcc $extra "$build"/*_"$suffix".o $libs -lm \
    -o "$build/events_${suffix}"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 timeout 30 "$build/events_${suffix}"
}

run_build normal ""
echo D279_14_NORMAL=PASS
run_build sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D279_14_ASAN_UBSAN=PASS
echo D279_15_B0_STREAM=PASS
echo D279_17_COMPLETION_GATED_SYNTHETIC_SUBMIT=PASS
echo D279_18_DORMANT_FPI_USB_BINDING_SEAM=PASS
echo D279_19_BINDING_CANCEL_AND_DRAIN=PASS
echo D279_22_ORDERED_CONTACT_CALLBACKS=PASS
echo D279_23_GRAPH_READY_AUTO_PROGRESSION=PASS
echo PRIMARY_B0_EXACT_PLAINTEXT_LENGTH=7693
echo AUXILIARY_B0_DECLARED_LENGTH_MAX=8192
echo AUXILIARY_B0_OPAQUE_CALLBACK=PASS
echo CONFIGURABLE_STAGE_PROFILES_2_3_21=PASS
echo ATTEMPT02_OBSERVED_STAGE_COUNT=21
echo OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
echo AUXILIARY_B0_APPLICATION_SEMANTICS=UNDETERMINED
echo INBOUND_LAYER_A0_FRAME_BUILD_COUNT=0
echo ATTEMPT02_PROFILE_SYNTHETIC_FIXED64_BUILD_COUNT=125
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
