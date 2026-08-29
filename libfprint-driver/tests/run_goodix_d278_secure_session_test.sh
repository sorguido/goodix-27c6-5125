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
    --command=sh org.freedesktop.Sdk//25.08 "$0"
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
includes="-I$build -I$root/libfprint-driver -I$local_fp -I$root/Rockytkg/libfprint -I$script_dir/support"
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"

build_run () {
  name=$1
  extra=$2
  gcc $strict $extra $cflags $includes \
    "$root/libfprint-driver/goodix_a0_protocol.c" \
    "$root/libfprint-driver/goodix_secure_session.c" \
    "$root/libfprint-driver/goodix_tls_server.c" \
    "$root/libfprint-driver/goodix_usb_router.c" \
    "$root/libfprint-driver/goodix_fpi_usb_backend.c" \
    "$script_dir/test_goodix_d278_secure_session.c" \
    "$script_dir/support/fpi_usb_transfer_compile_stub.c" \
    $libs -o "$build/$name"
  # LeakSanitizer is unavailable under the Flatpak/bwrap ptrace boundary;
  # ASAN address checks and UBSAN remain fully enabled.
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 90 "$build/$name"
}

build_run d278-normal ""
echo NORMAL_TEST_RUN=PASS
build_run d278-sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
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
