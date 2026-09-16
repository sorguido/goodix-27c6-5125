#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 4 ]; then
  echo "uso: $0 <source-dir> <build-dir> <pkgconfig-dir> <output-dir>" >&2
  exit 2
fi

source_dir=$1
build_dir=$2
pkgconfig_dir=$3
output_dir=$4
library=

export PKG_CONFIG_PATH=$pkgconfig_dir

grep -F 'D281_01_DISABLE_USB_CONTEXT' \
  "$source_dir/libfprint/fp-context.c" >/dev/null

meson setup "$build_dir" "$source_dir" \
  --prefix=/usr \
  --libdir=lib64 \
  -Ddrivers=virtual_image \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dgtk-examples=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled \
  -Dc_args=-DD281_01_DISABLE_USB_CONTEXT \
  --wrap-mode=nodownload
meson compile -C "$build_dir" fprint-2
meson install -C "$build_dir" --destdir "$output_dir/install" \
  --no-rebuild --tags runtime

library=$(find "$output_dir/install" -type f \
  -name 'libfprint-2.so.2.0.0' -print)
if [ -z "$library" ] || [ "$(printf '%s\n' "$library" | wc -l)" -ne 1 ]; then
  echo "ERRORE=Artefatto staging-probe libfprint non univoco" >&2
  exit 1
fi

grep -F -- '-DD281_01_DISABLE_USB_CONTEXT' \
  "$build_dir/compile_commands.json" >/dev/null
grep -F 'fpi_device_virtual_image_get_type' \
  "$build_dir/libfprint/fpi-drivers.c" >/dev/null
if grep -F 'goodix_27c6_5125' "$build_dir/libfprint/fpi-drivers.c" >/dev/null; then
  echo "ERRORE=Il driver Goodix è presente nella candidate staging-probe" >&2
  exit 1
fi
if nm -D "$library" | grep -Eq 'g_usb_context_(new|enumerate)'; then
  echo "ERRORE=La candidate staging-probe può creare o enumerare un contesto USB" >&2
  exit 1
fi
if nm "$library" | grep -Eq \
  'fpi_device_goodix_27c6_5125|get_tls_client_secret|goodix_secure'; then
  echo "ERRORE=La candidate staging-probe contiene Goodix/TLS" >&2
  exit 1
fi
readelf -d "$library" | grep -F '[libfprint-2.so.2]' >/dev/null
if readelf -d "$library" | grep -E '(RPATH|RUNPATH)' >/dev/null; then
  echo "ERRORE=La candidate staging-probe conserva un build path" >&2
  exit 1
fi

cp "$library" "$output_dir/libfprint-2.so.2.0.0"
ln -s libfprint-2.so.2.0.0 "$output_dir/libfprint-2.so.2"
ln -s libfprint-2.so.2 "$output_dir/libfprint-2.so"
chmod 0600 "$output_dir/libfprint-2.so.2.0.0"

echo D282_01_STAGING_PROBE_DRIVER=virtual_image
echo D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED=true
echo D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT=false
echo D282_01_STAGING_PROBE_USB_CONTEXT_SYMBOL_PRESENT=false
echo D282_01_STAGING_PROBE_GOODIX_TLS_SYMBOL_PRESENT=false
echo REAL_USB_ENUMERATION_ATTEMPTED=false
echo REAL_SENSOR_ACCESSED=false
echo LIVE_EXECUTION_PERFORMED=false
