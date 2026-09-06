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
tool_source="$snapshot_root/tools/d279_one_shot_enroll.c"
build_library="$build_dir/libfprint/libfprint-2.so.2.0.0"
install_root="$output_dir/install-root"

export PKG_CONFIG_PATH=$pkgconfig_dir

meson setup "$build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled
meson compile -C "$build_dir" fprint-2

grep -F -- '-DGOODIX_LIBFPRINT_1_94_100_NBIS' \
  "$build_dir/compile_commands.json" >/dev/null
nm "$build_library" | grep -F ' fpi_device_goodix_27c6_5125_get_type' >/dev/null
for forbidden_test_symbol in \
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

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0 gusb)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0 gusb)
cc -std=gnu11 -O2 -g \
  -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes \
  -Wmissing-prototypes -Wconversion \
  -DD279_29_APPROVED_BASELINE=\"$baseline\" \
  -I"$source_root" -I"$source_root/libfprint" \
  -I"$build_dir" -I"$build_dir/libfprint" \
  $cflags "$tool_source" "$library" $libs \
  -Wl,-rpath,'$ORIGIN' \
  -o "$output_dir/d279_one_shot_enroll.pending"
chmod 0600 "$output_dir/d279_one_shot_enroll.pending"

cp "$library" "$output_dir/libfprint-2.so.2.0.0"
cp "$pkgconfig_dir/libgusb.so.2" "$output_dir/libgusb.so.2"
ln -s libfprint-2.so.2.0.0 "$output_dir/libfprint-2.so.2"
ln -s libfprint-2.so.2 "$output_dir/libfprint-2.so"

echo D279_29_EXACT_TARGET_LIBFPRINT=1.94.100
echo D279_29_EXTRACTOR=NBIS_NATIVE
echo HOST_ONLY_TRANSCRIPT_SEAMS_IN_PRODUCTION_LIBRARY=false
echo PRODUCTION_LIBRARY_BUILD_RPATH_PRESENT=false
echo REAL_USB_ENUMERATION_ATTEMPTED=false
echo LIVE_EXECUTION_PERFORMED=false
