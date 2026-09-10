#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 4 ]; then
  echo "uso: $0 <snapshot-root> <build-dir> <pkgconfig-dir> <output-dir>" >&2
  exit 2
fi

snapshot_root=$1
build_dir=$2
pkgconfig_dir=$3
output_dir=$4
source_root="$snapshot_root/reference/libfprint-fedora44-1.94.100/source"
library=

export PKG_CONFIG_PATH=$pkgconfig_dir
export LDFLAGS=-Wl,--allow-shlib-undefined

grep -F 'fp_device_class->verify = fp_image_device_start_capture_action' \
  "$source_root/libfprint/fp-image-device.c" >/dev/null
grep -F 'fpi_device_get_verify_data' \
  "$source_root/libfprint/fpi-image-device.c" >/dev/null
grep -F 'fpi_print_sigfm_match' \
  "$source_root/libfprint/fpi-image-device.c" >/dev/null
grep -F 'FPI_DEVICE_ACTION_VERIFY) ?' \
  "$snapshot_root/libfprint-driver/goodix_fpimage_device.c" >/dev/null

meson setup "$build_dir" "$source_root" \
  --prefix=/usr \
  --libdir=lib64 \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled
meson compile -C "$build_dir" fprint-2
# Install only the runtime target.  Besides keeping the candidate surface to
# the one shared object required by the wrapper, this lets Meson apply the
# install-time RUNPATH removal without requiring unrelated generated metadata.
meson install -C "$build_dir" --destdir "$output_dir/install" \
  --no-rebuild --tags runtime
library=$(find "$output_dir/install" -type f -name 'libfprint-2.so.2.0.0' -print)
if [ -z "$library" ] || [ "$(printf '%s\n' "$library" | wc -l)" -ne 1 ]; then
  echo "ERRORE=Artefatto libfprint installato non univoco" >&2
  exit 1
fi

grep -F -- '-DGOODIX_LIBFPRINT_SIGFM' \
  "$build_dir/compile_commands.json" >/dev/null
nm "$library" | grep -F ' fpi_device_goodix_27c6_5125_get_type' >/dev/null
for forbidden_test_symbol in \
  goodix_fpi_usb_backend_set_submit_seam \
  goodix_fpi_usb_backend_set_async_submit_seam \
  goodix_fpimage_device_set_production_open_seams \
  goodix_device_context_set_usb_submit_seam \
  goodix_device_context_set_async_usb_submit_seam; do
  if nm "$library" | grep -F " $forbidden_test_symbol" >/dev/null; then
    echo "ERRORE=La libreria production contiene la seam $forbidden_test_symbol" >&2
    exit 1
  fi
done
if nm -u "$library" | grep -E \
  'g_usb_device_(reset|clear_halt)|libusb_(reset_device|clear_halt)|ClearApp|IAP|production_write_key'; then
  echo "ERRORE=Simbolo recovery/persistenza vietato nella libreria" >&2
  exit 1
fi
readelf -d "$library" | grep -F '[libfprint-2.so.2]' >/dev/null
if readelf -d "$library" | grep -E '(RPATH|RUNPATH)' >/dev/null; then
  echo "ERRORE=La libreria conserva un build path" >&2
  exit 1
fi
for symbol in fp_device_verify fp_device_verify_finish fp_print_serialize \
  fp_print_deserialize; do
  nm -D "$library" | grep -F " $symbol" >/dev/null
done

cp "$library" "$output_dir/libfprint-2.so.2.0.0"
ln -s libfprint-2.so.2.0.0 "$output_dir/libfprint-2.so.2"
ln -s libfprint-2.so.2 "$output_dir/libfprint-2.so"
chmod 0600 "$output_dir/libfprint-2.so.2.0.0"

echo D282_01_EXACT_LIBFPRINT=1.94.100
echo D282_01_GOODIX_VERIFY_BUILT=true
echo D282_01_SIGFM_VERIFY_BUILT=true
echo D282_01_PRODUCTION_BUILD_RPATH_PRESENT=false
echo D282_01_HOST_TEST_SEAMS_PRESENT=false
echo REAL_USB_ENUMERATION_ATTEMPTED=false
echo LIVE_EXECUTION_PERFORMED=false
