#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <repository-root> <build-dir> <pkgconfig-dir>" >&2
  exit 2
fi

repo_root=$1
build_dir=$2
pkgconfig_dir=$3
source_root="$repo_root/reference/libfprint-fedora44-1.94.100/source"

export PKG_CONFIG_PATH=$pkgconfig_dir

meson setup "$build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled

# The two production-relevant targets do not require the optional GUsb GIR,
# which is unavailable when only the Fedora runtime package is installed.
meson compile -C "$build_dir" fprint-2 fprint-list-supported-devices

registry="$build_dir/libfprint/fpi-drivers.c"
library="$build_dir/libfprint/libfprint-2.so.2.0.0"
list_tool="$build_dir/libfprint/fprint-list-supported-devices"

grep -F 'extern GType (fpi_device_goodix_27c6_5125_get_type) (void);' \
  "$registry" >/dev/null
grep -F 't = fpi_device_goodix_27c6_5125_get_type ();' "$registry" >/dev/null
grep -F -- '-DGOODIX_LIBFPRINT_1_94_100_NBIS' \
  "$build_dir/compile_commands.json" >/dev/null
nm "$library" | grep -F ' fpi_device_goodix_27c6_5125_get_type' >/dev/null
for forbidden_test_symbol in \
  goodix_fpimage_device_set_production_open_seams \
  goodix_device_context_set_usb_submit_seam \
  goodix_device_context_set_async_usb_submit_seam \
  goodix_device_context_complete_receive \
  goodix_device_context_begin_operator_epoch \
  goodix_device_context_set_pre_session_rx_sync_clock \
  goodix_device_context_stop_operator_epoch; do
  if nm "$library" | grep -F " $forbidden_test_symbol" >/dev/null; then
    echo "production library contains host-only seam: $forbidden_test_symbol" >&2
    exit 1
  fi
done

supported=$(LD_LIBRARY_PATH="$build_dir/libfprint:$pkgconfig_dir" "$list_tool")
printf '%s\n' "$supported"
printf '%s\n' "$supported" | \
  grep -F '27c6:5125 | Goodix 27c6:5125 Fingerprint Sensor' >/dev/null
test "$(printf '%s\n' "$supported" | grep -c '^27c6:5125 |')" -eq 1

# fprint-list-supported-devices only walks registered class metadata.  Keep an
# explicit source gate so this offline closure cannot silently start USB
# enumeration in a later target revision.
if grep -E 'g_usb_|fp_context_(new|enumerate)' \
     "$source_root/libfprint/fprint-list-supported-devices.c"; then
  echo "registry list tool unexpectedly reaches USB enumeration" >&2
  exit 1
fi

echo D279_03_FEDORA44_LIBFPRINT_1_94_100_BUILD=PASS
echo D279_03_STANDARD_DRIVER_REGISTRY=PASS
echo PRODUCTION_USB_ID_27C6_5125_REGISTERED=true
echo EXTRACTOR_DECISION=NBIS
echo FPIMAGE_PPMM_ASSIGNED=false
echo HOST_ONLY_TRANSCRIPT_SEAMS_IN_PRODUCTION_LIBRARY=false
echo REAL_USB_ENUMERATION_COUNT=0
echo REAL_USB_OPEN_COUNT=0
echo REAL_USB_CLAIM_COUNT=0
echo REAL_USB_SUBMIT=0
echo LIVE_EXECUTION_PERFORMED=false
