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
tool_source="$snapshot_root/tools/d280_ephemeral_template_reuse.c"
build_library="$build_dir/libfprint/libfprint-2.so.2.0.0"
install_root="$output_dir/install-root"

export PKG_CONFIG_PATH=$pkgconfig_dir
export LDFLAGS=-Wl,--allow-shlib-undefined

grep -F '#define GOODIX_SIGFM_ENROLL_MAX_STAGES 8u' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.h" >/dev/null
grep -F '.required_stage_count = GOODIX_SIGFM_ENROLL_MAX_STAGES' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.c" >/dev/null
grep -F 'GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.c" >/dev/null
grep -F 'fpi_image_device_hold_enroll_completion' \
  "$source_root/libfprint/fpi-image-device.c" >/dev/null
grep -F '../../../../libfprint-driver/goodix_fdt_irq_policy.c' \
  "$source_root/libfprint/meson.build" >/dev/null

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
  goodix_device_context_stop_operator_epoch; do
  if nm "$build_library" | grep -F " $forbidden_test_symbol" >/dev/null; then
    echo "production library contains host-only seam: $forbidden_test_symbol" >&2
    exit 1
  fi
done

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
nm -D "$library" | grep -F ' fp_print_serialize' >/dev/null
nm -D "$library" | grep -F ' fp_print_deserialize' >/dev/null
nm -D "$library" | grep -F ' fp_device_identify_sync' >/dev/null

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0 gusb)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0 gusb)
cc -std=gnu11 -O2 -g \
  -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes \
  -Wmissing-prototypes -Wconversion \
  -DD280_01_APPROVED_BASELINE=\"$baseline\" \
  -I"$snapshot_root/libfprint-driver" \
  -I"$source_root" -I"$source_root/libfprint" \
  -I"$build_dir" -I"$build_dir/libfprint" \
  $cflags "$tool_source" "$library" $libs \
  -Wl,--allow-shlib-undefined \
  -Wl,-rpath,'$ORIGIN' \
  -o "$output_dir/d280_ephemeral_template_reuse.pending"
chmod 0600 "$output_dir/d280_ephemeral_template_reuse.pending"

cp "$library" "$output_dir/libfprint-2.so.2.0.0"
cp "$pkgconfig_dir/libgusb.so.2" "$output_dir/libgusb.so.2"
ln -s libfprint-2.so.2.0.0 "$output_dir/libfprint-2.so.2"
ln -s libfprint-2.so.2 "$output_dir/libfprint-2.so"

echo D280_01_EXACT_TARGET_LIBFPRINT=1.94.100
echo D280_01_EXTRACTOR=SIGFM_ROCKYTKG
echo D280_01_ACTION_SEQUENCE=ENROLL_FP3_CLOSE_OPEN_IDENTIFY
echo D280_01_TEMPLATE_POLICY=EPHEMERAL_TMPFS_ROOT_0700_FILE_0600_UNLINK_BEFORE_IDENTIFY
echo D280_01_PRODUCTION_ENROLLMENT_STAGE_COUNT=8
echo D280_01_PRODUCTION_IDENTIFY_PROFILE=SINGLE_ACQUISITION
echo HOST_ONLY_TRANSCRIPT_SEAMS_IN_PRODUCTION_LIBRARY=false
echo SANITIZED_PRODUCTION_AUDIT_ACCESSOR_EXPORTED=true
echo PRODUCTION_LIBRARY_BUILD_RPATH_PRESENT=false
echo REAL_USB_ENUMERATION_ATTEMPTED=false
echo LIVE_EXECUTION_PERFORMED=false
