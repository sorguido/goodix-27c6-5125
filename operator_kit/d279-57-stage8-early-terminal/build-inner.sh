#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 5 ]; then
  echo "usage: $0 <snapshot-root> <build-dir> <pkgconfig-dir> <output-dir> <baseline>" >&2
  exit 2
fi

snapshot_root=$1
build_dir=$2
pkgconfig_dir=$3
output_dir=$4
baseline=$5
source_root="$snapshot_root/reference/libfprint-fedora44-1.94.100/source"
tool_source="$snapshot_root/tools/d279_stage8_enroll.c"
build_library="$build_dir/libfprint/libfprint-2.so.2.0.0"
install_root="$output_dir/install-root"

export PKG_CONFIG_PATH=$pkgconfig_dir
export LDFLAGS=-Wl,--allow-shlib-undefined

grep -F '#define GOODIX_SIGFM_ENROLL_MAX_STAGES 8u' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.h" >/dev/null
grep -F '.required_stage_count = GOODIX_SIGFM_ENROLL_MAX_STAGES' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.c" >/dev/null
grep -F '.defer_intermediate_stage_delivery_until_release_ready = TRUE' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.c" >/dev/null
grep -F '.defer_terminal_stage_delivery_until_release_ready = TRUE' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.c" >/dev/null
grep -F 'fpi_image_device_hold_enroll_completion' \
  "$source_root/libfprint/fpi-image-device.c" >/dev/null
grep -F 'fpi_image_device_release_enroll_completion' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.c" >/dev/null
grep -F '../../../../libfprint-driver/goodix_fdt_irq_policy.c' \
  "$source_root/libfprint/meson.build" >/dev/null
grep -F 'GOODIX_FDT_FLAGS_FINGER_DOWN, &touch_flags, &raw' \
  "$snapshot_root/libfprint-driver/goodix_enrollment_post_tls_events.c" >/dev/null

meson setup "$build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled
meson compile -C "$build_dir" fprint-2

grep -F -- '-DGOODIX_LIBFPRINT_SIGFM' \
  "$build_dir/compile_commands.json" >/dev/null
nm "$build_library" | grep -F ' fpi_device_goodix_27c6_5125_get_type' >/dev/null
for forbidden_test_symbol in \
  goodix_fpi_usb_backend_set_submit_seam \
  goodix_fpi_usb_backend_set_async_submit_seam \
  goodix_fpimage_device_set_production_open_seams \
  goodix_device_context_set_usb_submit_seam \
  goodix_device_context_set_async_usb_submit_seam \
  goodix_device_context_complete_receive \
  goodix_device_context_begin_operator_epoch \
  goodix_device_context_set_pre_session_rx_sync_clock \
  goodix_device_context_stop_operator_epoch; do
  if nm "$build_library" | grep -F " $forbidden_test_symbol" >/dev/null; then
    echo "production library contains host-only seam: $forbidden_test_symbol" >&2
    exit 1
  fi
done

# Meson's in-build shared object retains a temporary dependency RPATH.  A
# DESTDIR staging install strips it without touching the host install tree.
meson install -C "$build_dir" --no-rebuild --tags runtime \
  --destdir "$install_root"
set -- $(find "$install_root" -type f -name 'libfprint-2.so.2.0.0')
if [ "$#" -ne 1 ]; then
  echo "staged production library not uniquely resolved" >&2
  exit 1
fi
library=$1
if readelf -d "$library" | grep -E '(RPATH|RUNPATH)' >/dev/null; then
  echo "staged production library retains a build path" >&2
  exit 1
fi
nm -D "$library" | grep -F \
  ' goodix_fpimage_device_get_production_enrollment_audit' >/dev/null

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0 gusb)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0 gusb)
cc -std=gnu11 -O2 -g \
  -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes \
  -Wmissing-prototypes -Wconversion \
  -DD279_57_APPROVED_BASELINE=\"$baseline\" \
  -I"$snapshot_root/libfprint-driver" \
  -I"$source_root" -I"$source_root/libfprint" \
  -I"$build_dir" -I"$build_dir/libfprint" \
  $cflags "$tool_source" "$library" $libs \
  -Wl,--allow-shlib-undefined \
  -Wl,-rpath,'$ORIGIN' \
  -o "$output_dir/d279_stage8_enroll.pending"
chmod 0600 "$output_dir/d279_stage8_enroll.pending"

cp "$library" "$output_dir/libfprint-2.so.2.0.0"
cp "$pkgconfig_dir/libgusb.so.2" "$output_dir/libgusb.so.2"
ln -s libfprint-2.so.2.0.0 "$output_dir/libfprint-2.so.2"
ln -s libfprint-2.so.2 "$output_dir/libfprint-2.so"

echo D279_57_EXACT_TARGET_LIBFPRINT=1.94.100
echo D279_57_EXTRACTOR=SIGFM_ROCKYTKG
echo D279_57_PRODUCTION_ENROLLMENT_STAGE_COUNT=8
echo D279_57_STAGE8_EARLY_TERMINAL_CANDIDATE=true
echo D279_57_INTERMEDIATE_DELIVERY_BOUNDARY=FINAL_ACK34_BEFORE_IRQ0200
echo D279_57_TERMINAL_DELIVERY_BOUNDARY=FINAL_ACK34_BEFORE_IRQ0200
echo D279_57_TERMINAL_COMPLETION_BOUNDARY=IRQ0200_AND_SIGFM_COMPLETE
echo D279_57_IRQ_FLAGS_POLICY=SIX_CHANNEL_CONTEXTUAL_FAIL_CLOSED
echo D279_57_PARTIAL_TOUCH_FDT_DERIVATION=OEM_BIT_AWARE
echo HOST_ONLY_TRANSCRIPT_SEAMS_IN_PRODUCTION_LIBRARY=false
echo SANITIZED_PRODUCTION_AUDIT_ACCESSOR_EXPORTED=true
echo PRODUCTION_LIBRARY_BUILD_RPATH_PRESENT=false
echo REAL_USB_ENUMERATION_ATTEMPTED=false
echo LIVE_EXECUTION_PERFORMED=false
