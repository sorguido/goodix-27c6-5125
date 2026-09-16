#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <snapshot-root> <build-dir> <pkgconfig-dir> <output-dir>" >&2
  exit 2
fi

snapshot_root=$1
build_dir=$2
pkgconfig_dir=$3
output_dir=$4
source_root="$snapshot_root/reference/libfprint-fedora44-1.94.100/source"

export PKG_CONFIG_PATH=$pkgconfig_dir
meson setup "$build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled
meson compile -C "$build_dir" test-goodix-nbis-count-pipe

grep -F 'test_goodix_nbis_count_pipe.c' "$build_dir/compile_commands.json" >/dev/null
if grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)' \
     "$snapshot_root/libfprint-driver/tests/test_goodix_nbis_count_pipe.c"; then
  echo "NBIS helper contains a production/USB entry point" >&2
  exit 1
fi
helper="$build_dir/tests/test-goodix-nbis-count-pipe"
test -f "$helper" && test ! -L "$helper"

# The helper pulls the pinned NBIS implementation into the executable from the
# build tree's static archives. With the toolchain's default --as-needed
# behaviour, the shared libfprint object can legitimately disappear from
# DT_NEEDED, so an ldd dependency on libfprint-2.so is not a valid closure
# invariant. Verify the material dependency directly instead: the expected NBIS
# entry points/data must be defined in the helper and must not remain unresolved.
if nm -u "$helper" | grep -Eq '(^|[[:space:]])(get_minutiae|free_minutiae|g_lfsparms_V2)$'; then
  echo "NBIS helper leaves pinned NBIS symbols unresolved" >&2
  exit 1
fi
nm "$helper" | grep -Eq '[[:space:]][Tt][[:space:]]get_minutiae$'
nm "$helper" | grep -Eq '[[:space:]][Tt][[:space:]]free_minutiae$'
nm "$helper" | grep -Eq '[[:space:]][RrDdBb][[:space:]]g_lfsparms_V2$'

cp "$helper" "$output_dir/d279_nbis_count.pending"
chmod 0600 "$output_dir/d279_nbis_count.pending"

echo D279_35_EXACT_TARGET_LIBFPRINT=1.94.100
echo D279_35_NBIS_HELPER_BUILD=PASS
echo D279_35_PRODUCTION_USB_REACHED=false
echo LIVE_EXECUTION_PERFORMED=false
