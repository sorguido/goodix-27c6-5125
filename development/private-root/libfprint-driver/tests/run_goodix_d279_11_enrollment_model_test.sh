#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)

if [ "${GOODIX_D279_11_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  exec flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_D279_11_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0"
fi

build=$(mktemp -d /tmp/goodix-d279-11-enrollment.XXXXXX)
trap 'find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true; rmdir "$build" 2>/dev/null || true' EXIT HUP INT TERM

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0)
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
sources="
$root/libfprint-driver/goodix_enrollment_model.c
$script_dir/test_goodix_enrollment_model.c
"

if grep -En '(Rockytkg|core/|goodix_fpi_usb|g_usb_|libusb_|control_transfer|submit_out)' \
  "$root/libfprint-driver/goodix_enrollment_model.c" \
  "$root/libfprint-driver/goodix_enrollment_model.h" \
  "$root/libfprint-driver/goodix_enrollment_pipeline.c" \
  "$root/libfprint-driver/goodix_enrollment_pipeline.h" \
  "$root/libfprint-driver/goodix_enrollment_command_plan.c" \
  "$root/libfprint-driver/goodix_enrollment_command_plan.h" \
  "$root/libfprint-driver/goodix_enrollment_command_body.c" \
  "$root/libfprint-driver/goodix_enrollment_command_body.h"; then
  echo "forbidden provenance or sensor-reaching symbol in D279/11 model" >&2
  exit 1
fi
echo D279_11_SOURCE_AND_ZERO_SENDER_AUDIT=PASS

build_run () {
  name=$1
  extra=$2
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags -I"$root/libfprint-driver" $sources $libs \
    -o "$build/$name"
  if nm -u "$build/$name" | \
     grep -E '(^|[[:space:]])(g_usb_|libusb_|SSL_|mbedtls_|gnutls_)'; then
    echo "forbidden USB/TLS symbol in D279/11 model" >&2
    exit 1
  fi
  # LeakSanitizer cannot attach under the Flatpak/bwrap test boundary; ASan
  # and UBSan remain fail-fast, matching the established C suites here.
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build/$name"
}

build_run d279_11_normal ""
echo D279_11_NORMAL=PASS
build_run d279_11_sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D279_11_ASAN_UBSAN=PASS

local_fp="$root/Rockytkg/libfprint/libfprint"
includes="-I$script_dir/support -I$root/libfprint-driver -I$root/Rockytkg/libfprint -I$local_fp -I$local_fp/nbis/include -I$local_fp/nbis/libfprint-include"
local_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter"

build_pipeline_run () {
  suffix=$1
  extra=$2
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c \
    "$root/libfprint-driver/goodix_u16_to_fpimage.c" \
    -o "$build/u16_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c \
    "$root/libfprint-driver/goodix_fpimage_pipeline.c" \
    -o "$build/fpimage_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c \
    "$root/libfprint-driver/goodix_enrollment_model.c" \
    -o "$build/model_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c \
    "$root/libfprint-driver/goodix_enrollment_pipeline.c" \
    -o "$build/enrollment_pipeline_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c \
    "$script_dir/test_goodix_enrollment_pipeline.c" \
    -o "$build/test_pipeline_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $local_flags $extra $cflags $includes -c "$local_fp/fp-image.c" \
    -o "$build/fp-image_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $local_flags $extra $cflags $includes -c \
    "$script_dir/support/fpimage_link_stubs.c" \
    -o "$build/fpimage_stubs_${suffix}.o"

  if nm -u "$build/enrollment_pipeline_${suffix}.o" | \
     grep -E '(^|[[:space:]])(g_usb_|libusb_|SSL_|mbedtls_|gnutls_|open|read|write|socket)'; then
    echo "forbidden I/O, USB or TLS symbol in D279/11 image pipeline" >&2
    exit 1
  fi
  # shellcheck disable=SC2086
  gcc $extra "$build/u16_${suffix}.o" "$build/fpimage_${suffix}.o" \
    "$build/model_${suffix}.o" "$build/enrollment_pipeline_${suffix}.o" \
    "$build/test_pipeline_${suffix}.o" "$build/fp-image_${suffix}.o" \
    "$build/fpimage_stubs_${suffix}.o" $libs -lm \
    -o "$build/pipeline_${suffix}"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build/pipeline_${suffix}"
}

build_pipeline_run normal ""
echo D279_11_FPIMAGE_PIPELINE_NORMAL=PASS
build_pipeline_run sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D279_11_FPIMAGE_PIPELINE_ASAN_UBSAN=PASS

build_command_plan_run () {
  suffix=$1
  extra=$2
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c \
    "$root/libfprint-driver/goodix_enrollment_command_plan.c" \
    -o "$build/command_plan_${suffix}.o"
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c \
    "$script_dir/test_goodix_enrollment_command_plan.c" \
    -o "$build/test_command_plan_${suffix}.o"
  if nm -u "$build/command_plan_${suffix}.o" | \
     grep -E '(^|[[:space:]])(g_usb_|libusb_|SSL_|mbedtls_|gnutls_|open|read|write|socket)'; then
    echo "forbidden I/O, USB or TLS symbol in D279/11 command plan" >&2
    exit 1
  fi
  if grep -En '(goodix_fpi_usb|goodix_a0_build|fixed64_command)' \
      "$root/libfprint-driver/goodix_enrollment_command_plan.c"; then
    echo "serialization or sender dependency in D279/11 command plan" >&2
    exit 1
  fi
  # shellcheck disable=SC2086
  gcc $extra "$build/u16_${suffix}.o" "$build/fpimage_${suffix}.o" \
    "$build/model_${suffix}.o" "$build/enrollment_pipeline_${suffix}.o" \
    "$build/command_plan_${suffix}.o" \
    "$build/test_command_plan_${suffix}.o" "$build/fp-image_${suffix}.o" \
    "$build/fpimage_stubs_${suffix}.o" $libs -lm \
    -o "$build/command_plan_${suffix}"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build/command_plan_${suffix}"
}

build_command_plan_run normal ""
echo D279_11_COMMAND_PLAN_NORMAL=PASS
build_command_plan_run sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D279_11_COMMAND_PLAN_ASAN_UBSAN=PASS

build_command_body_run () {
  suffix=$1
  extra=$2
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes \
    "$root/libfprint-driver/goodix_enrollment_command_body.c" \
    "$script_dir/test_goodix_enrollment_command_body.c" $libs \
    -o "$build/command_body_${suffix}"
  if nm -u "$build/command_body_${suffix}" | \
     grep -E '(^|[[:space:]])(g_usb_|libusb_|SSL_|mbedtls_|gnutls_|open|read|write|socket)'; then
    echo "forbidden I/O, USB or TLS symbol in D279/11 command body" >&2
    exit 1
  fi
  if grep -En '(goodix_fpi_usb|goodix_a0_build|fixed64_command)' \
      "$root/libfprint-driver/goodix_enrollment_command_body.c"; then
    echo "wire-frame serializer or sender dependency in D279/11 command body" >&2
    exit 1
  fi
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build/command_body_${suffix}"
}

build_command_body_run normal ""
echo D279_11_COMMAND_BODY_NORMAL=PASS
build_command_body_run sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D279_11_COMMAND_BODY_ASAN_UBSAN=PASS
echo CONFIGURABLE_STAGE_PROFILES_2_3_21=PASS
echo ATTEMPT02_OBSERVED_STAGE_COUNT=21
echo OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
echo AUXILIARY_B0_APPLICATION_SEMANTICS=UNDETERMINED
echo LIBFPRINT_STAGE_EVENTS_FROM_PRIMARY_B0_ONLY=PASS
echo PRIMARY_FPIMAGE_DELIVERY_PROFILES_2_3_21=PASS
echo AUXILIARY_B0_FPIMAGE_DELIVERY_COUNT=0
echo COMMAND_PLAN_SERIALIZED_COMMAND_COUNT=0
echo COMMAND_PLAN_REAL_SUBMIT_COUNT=0
echo COMMAND_BODY_A0_FRAME_BUILD_COUNT=0
echo COMMAND_BODY_REAL_SUBMIT_COUNT=0
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
