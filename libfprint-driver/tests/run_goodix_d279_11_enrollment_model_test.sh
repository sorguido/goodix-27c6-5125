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

cflags=$(pkg-config --cflags glib-2.0)
libs=$(pkg-config --libs glib-2.0)
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
sources="
$root/libfprint-driver/goodix_enrollment_model.c
$script_dir/test_goodix_enrollment_model.c
"

if grep -En '(Rockytkg|core/|goodix_fpi_usb|g_usb_|libusb_|control_transfer|submit_out)' \
  "$root/libfprint-driver/goodix_enrollment_model.c" \
  "$root/libfprint-driver/goodix_enrollment_model.h"; then
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
echo CONFIGURABLE_STAGE_PROFILES_2_3_21=PASS
echo ATTEMPT02_OBSERVED_STAGE_COUNT=21
echo OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
echo AUXILIARY_B0_APPLICATION_SEMANTICS=UNDETERMINED
echo LIBFPRINT_STAGE_EVENTS_FROM_PRIMARY_B0_ONLY=PASS
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
