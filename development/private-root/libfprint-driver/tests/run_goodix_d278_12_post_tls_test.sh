#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
experiment=${1:-}
[ "$#" -le 1 ] && { [ -z "$experiment" ] || [ "$experiment" = --same-action ]; } || exit 2

if [ "${GOODIX_D278_12_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  exec flatpak run --user --unshare=network \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_D278_12_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0" "$@"
fi

build=$(mktemp -d /tmp/goodix-d278-12-post-tls.XXXXXX)
trap 'find "$build" -depth -delete 2>/dev/null || true' EXIT HUP INT TERM

cflags=$(pkg-config --cflags glib-2.0 gio-2.0)
libs=$(pkg-config --libs glib-2.0 gio-2.0)
local_fp="$root/reference/libfprint-fedora44-1.94.100/source/libfprint"
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
includes="-I$build -I$root/libfprint-driver -I$local_fp -I$local_fp/.. -I$script_dir/support"
strict="-std=gnu11 -O2 -g -DGOODIX_ENABLE_TEST_SEAMS -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
post_tls_source="$root/libfprint-driver/goodix_post_tls_lifecycle.c"
if [ "$experiment" = --same-action ]; then
  mkdir "$build/libfprint-driver"
  cp "$post_tls_source" "$build/libfprint-driver/"
  patch --batch --fuzz=0 -d "$build" -p1 <"$root/development/patches/login-same-action/same-action.patch"
  post_tls_source="$build/libfprint-driver/goodix_post_tls_lifecycle.c"
  strict="$strict -DGOODIX_SAME_ACTION_TEST"
fi
sources="
$root/libfprint-driver/goodix_a0_protocol.c
$root/libfprint-driver/goodix_image_decoder.c
$root/libfprint-driver/goodix_fdt_irq_policy.c
$post_tls_source
$root/libfprint-driver/goodix_usb_router.c
$root/libfprint-driver/goodix_fpi_usb_backend.c
$script_dir/test_goodix_post_tls_lifecycle.c
$script_dir/support/fpi_usb_transfer_compile_stub.c
"

if grep -En '(Rockytkg|core/|src/goodix5125_cleanroom|g_usb_device_reset|g_usb_device_clear_halt|control_transfer)' \
  "$root/libfprint-driver/goodix_image_decoder.c" \
  "$post_tls_source"; then
  echo "forbidden provenance or unsafe symbol in D278/12 LGPL sources" >&2
  exit 1
fi
echo D278_12_SOURCE_AUDIT=PASS

build_run () {
  name=$1
  extra=$2
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes $sources $libs -o "$build/$name"
  if nm -u "$build/$name" | \
     grep -E '(^|[[:space:]])(g_usb_device_reset|g_usb_device_clear_halt|libusb_reset_device|libusb_clear_halt|SSL_|mbedtls_|gnutls_)'; then
    echo "forbidden USB recovery or independent TLS symbol in D278/12 lifecycle" >&2
    exit 1
  fi
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 90 "$build/$name"
}

build_run d278_12_normal ""
echo D278_12_FORBIDDEN_SYMBOL_AUDIT=PASS
echo D278_12_NORMAL=PASS
build_run d278_12_sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D278_12_ASAN_UBSAN=PASS
echo REENTRY_SECURE_SESSION_TO_TWO_ACQUISITION_HOST_ONLY=PASS
echo D279_21_FIRST_ARM_BACKEND_HANDOFF=PASS
echo D279_21_HANDOFF_REAL_USB_SUBMIT=0
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
echo CURRENT_LIVE_AUTHORIZED=false
echo READY_FOR_LIVE=false
