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
runtime_dir="$output_dir/runtime"
include_dir="$output_dir/include/pixman-1"

export PKG_CONFIG_PATH=$pkgconfig_dir
pixman_version=$(pkg-config --modversion pixman-1)
pixman_libdir=$(pkg-config --variable=libdir pixman-1)
pixman_includedir=$(pkg-config --variable=includedir pixman-1)/pixman-1
test -f "$pixman_libdir/libpixman-1.so.0"
test -f "$pixman_includedir/pixman.h"
mkdir -p "$runtime_dir" "$include_dir"
cp -L "$pixman_libdir/libpixman-1.so.0" "$runtime_dir/libpixman-1.so"
cp -L "$pixman_libdir/libpixman-1.so.0" "$runtime_dir/libpixman-1.so.0"
cp -R "$pixman_includedir/." "$include_dir/"
chmod 0600 "$runtime_dir/libpixman-1.so" "$runtime_dir/libpixman-1.so.0"
sed -e "s|@PREFIX@|$runtime_dir|g" \
    -e "s|@INCLUDEDIR@|$include_dir|g" \
    -e "s|@VERSION@|$pixman_version|g" \
    "$snapshot_root/operator_kit/d279-39-offline-protected-nbis-quality/pixman-1.pc.in" \
    >"$pkgconfig_dir/pixman-1.pc"

export LD_LIBRARY_PATH=$runtime_dir
meson setup "$build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125,aes3500 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled
meson compile -C "$build_dir" test-goodix-nbis-resize-quality-pipe

grep -F 'test_goodix_nbis_resize_quality_pipe.c' \
  "$build_dir/compile_commands.json" >/dev/null
helper_source="$snapshot_root/libfprint-driver/tests/test_goodix_nbis_resize_quality_pipe.c"
if grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)' \
     "$helper_source"; then
  echo "L'helper resize/NBIS contiene un entry point production/USB" >&2
  exit 1
fi
helper="$build_dir/tests/test-goodix-nbis-resize-quality-pipe"
test -f "$helper" && test ! -L "$helper"
if nm "$helper" |
   grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)'; then
  echo "Il binario resize/NBIS collega un entry point production/USB" >&2
  exit 1
fi

if nm -u "$helper" | grep -Eq \
  '(^|[[:space:]])(get_minutiae|free_minutiae|g_lfsparms_V2|fpi_image_resize)$'; then
  echo "L'helper lascia irrisolti simboli NBIS/resize pinned" >&2
  exit 1
fi
nm "$helper" | grep -Eq '[[:space:]][Tt][[:space:]]get_minutiae$'
nm "$helper" | grep -Eq '[[:space:]][Tt][[:space:]]free_minutiae$'
nm "$helper" | grep -Eq '[[:space:]][RrDdBb][[:space:]]g_lfsparms_V2$'
nm "$helper" | grep -Eq '[[:space:]][Tt][[:space:]]fpi_image_resize$'
LD_LIBRARY_PATH=$runtime_dir ldd "$helper" | grep -F "$runtime_dir/libpixman-1.so.0" >/dev/null

python3 -c '
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("d279_39_build_check", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
with module.ExactLibfprintResizeNbisQualityPipe(pathlib.Path(sys.argv[2])) as runner:
    for factor in module.SPATIAL_FACTORS:
        metrics = runner.measure(bytearray(5120), 80, 64, factor)
        values = metrics.as_aggregate_inputs()
        assert metrics.minutiae_total == 0
        assert metrics.quality_levels[0] == values["quality_blocks_total"]
' "$snapshot_root/analysis/D279/d279_39_nbis_quality_evaluator.py" "$helper"

cp "$helper" "$output_dir/d279_resize_nbis_quality.pending"
chmod 0600 "$output_dir/d279_resize_nbis_quality.pending"

echo D279_39_EXACT_TARGET_LIBFPRINT=1.94.100
echo "D279_39_PINNED_PIXMAN=$pixman_version"
echo D279_39_EXACT_RESIZE=PIXMAN_BILINEAR_FACTORS_2_3
echo D279_39_FACTOR_1_CONTROL=D279_34_EXACT_NBIS_PATH
echo D279_39_NBIS_QUALITY_HELPER_BUILD=PASS
echo D279_39_PRODUCTION_USB_REACHED=false
echo LIVE_EXECUTION_PERFORMED=false
