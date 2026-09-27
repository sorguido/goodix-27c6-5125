#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd -P)
[ "$#" -eq 0 ] || exit 2
if [ "${GOODIX_ENROLLMENT_A0_IN_SDK:-0}" != 1 ] &&
   command -v flatpak >/dev/null 2>&1 &&
   flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
  exec flatpak run --user --unshare=network --nodevice=all \
    --filesystem="$root":ro --filesystem=/tmp \
    --env=GOODIX_ENROLLMENT_A0_IN_SDK=1 \
    --command=sh org.freedesktop.Sdk//25.08 "$0"
fi

build=$(mktemp -d /tmp/goodix-enrollment-a0.XXXXXX)
trap 'find "$build" -depth -delete 2>/dev/null || true' EXIT HUP INT TERM
local_fp="$root/reference/libfprint-fedora44-1.94.100/source/libfprint"
cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0)
includes="-I$build -I$script_dir/support -I$root/libfprint-driver -I$local_fp -I$local_fp/.. -I$local_fp/nbis/include -I$local_fp/nbis/libfprint-include -I$root/Rockytkg/libfprint/libfprint"
strict="-std=gnu11 -O2 -g -DGOODIX_ENABLE_TEST_SEAMS -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion"
python3 "$script_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fp --symbol-prefix fp --header-guard FP_ENUMS_H \
  --header-name fp-enums.h --output-header "$build/fp-enums.h" \
  --output-source "$build/fp-enums.c" "$local_fp/fp-device.h" "$local_fp/fp-print.h"
python3 "$script_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fpi --symbol-prefix fpi --header-guard FPI_ENUMS_H \
  --header-name fpi-enums.h --output-header "$build/fpi-enums.h" \
  --output-source "$build/fpi-enums.c" "$local_fp/fpi-device.h" \
  "$local_fp/fpi-image-device.h" "$local_fp/fpi-print.h"
cp "$script_dir/support/config.h" "$build/config.h"

run_build () {
  suffix=$1
  extra=$2
  for source in goodix_a0_protocol goodix_image_decoder goodix_u16_to_fpimage \
    goodix_fpimage_pipeline goodix_enrollment_model goodix_enrollment_pipeline \
    goodix_enrollment_command_plan goodix_enrollment_command_body \
    goodix_fdt_irq_policy goodix_enrollment_fdt_state \
    goodix_enrollment_lifecycle_adapter goodix_enrollment_post_tls_events \
    goodix_enrollment_outbound_frame goodix_enrollment_outbound_transaction \
    goodix_usb_router goodix_fpi_usb_backend goodix_enrollment_fpi_usb_binding; do
    # shellcheck disable=SC2086
    gcc $strict $extra $cflags $includes -c "$root/libfprint-driver/$source.c" \
      -o "$build/${source}_${suffix}.o"
  done
  # shellcheck disable=SC2086
  gcc $strict $extra $cflags $includes -c "$script_dir/test_goodix_enrollment_a0.c" \
    -o "$build/test_${suffix}.o"
  for source in "$local_fp/fp-image.c" "$script_dir/support/fpimage_link_stubs.c" \
    "$script_dir/support/fpi_usb_transfer_compile_stub.c"; do
    object=$(basename "$source" .c)
    # shellcheck disable=SC2086
    gcc -std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter \
      $extra $cflags $includes -c "$source" -o "$build/${object}_${suffix}.o"
  done
  # shellcheck disable=SC2086
  gcc $extra "$build"/*_"$suffix".o $libs -lm -o "$build/test_$suffix"
  # LeakSanitizer cannot inspect processes in the SDK sandbox; ASan and UBSan
  # remain enabled, as in the other host-only protocol runners.
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
    timeout 60 "$build/test_$suffix"
}

run_build normal ""
echo ENROLLMENT_A0_NORMAL=PASS
run_build sanitized "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo ENROLLMENT_A0_ASAN_UBSAN=PASS
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
