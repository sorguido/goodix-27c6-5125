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
includes="-I$script_dir/support -I$root/libfprint-driver -I$root/Rockytkg/libfprint -I$local_fp -I$local_fp/nbis/include -I$local_fp/nbis/libfprint-include"
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
local_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter"

if grep -En '(goodix_a0_build|goodix_fpi_usb|fixed64_command|submit_out|g_usb_|libusb_)' \
    "$root/libfprint-driver/goodix_enrollment_post_tls_events.c" \
    "$root/libfprint-driver/goodix_enrollment_post_tls_events.h"; then
  echo "serializer or sender dependency in D279/14 inbound event binding" >&2
  exit 1
fi
echo D279_14_INBOUND_ONLY_SOURCE_AUDIT=PASS

run_build () {
  suffix=$1
  extra=$2
  for source in \
    goodix_a0_protocol.c \
    goodix_u16_to_fpimage.c \
    goodix_fpimage_pipeline.c \
    goodix_enrollment_model.c \
    goodix_enrollment_pipeline.c \
    goodix_enrollment_command_plan.c \
    goodix_enrollment_command_body.c \
    goodix_enrollment_fdt_state.c \
    goodix_enrollment_lifecycle_adapter.c \
    goodix_enrollment_post_tls_events.c; do
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
echo CONFIGURABLE_STAGE_PROFILES_2_3_21=PASS
echo ATTEMPT02_OBSERVED_STAGE_COUNT=21
echo OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
echo AUXILIARY_B0_APPLICATION_SEMANTICS=UNDETERMINED
echo A0_FRAME_BUILD_COUNT=0
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
