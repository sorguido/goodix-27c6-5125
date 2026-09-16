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
helper_source="$repo_root/libfprint-driver/tests/test_goodix_nbis_resize_quality_pipe.c"
evaluator_module="$repo_root/analysis/D279/d279_39_nbis_quality_evaluator.py"

export PKG_CONFIG_PATH=$pkgconfig_dir

run_python_adapter ()
{
  helper=$1
  python3 -c '
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("d279_39_pipe_integration", sys.argv[1])
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
with module.ExactLibfprintResizeNbisQualityPipe(pathlib.Path(sys.argv[2])) as runner:
    for factor in module.SPATIAL_FACTORS:
        metrics = runner.measure(bytearray(5120), 80, 64, factor)
        values = metrics.as_aggregate_inputs()
        assert metrics.minutiae_total == 0
        assert metrics.quality_levels[0] == values["quality_blocks_total"]
        assert values["quality_blocks_ab"] == 0
' "$evaluator_module" "$helper"
}

configure ()
{
  directory=$1
  shift
  # AES3500 only activates the pinned tree's existing pixman feature switch.
  meson setup "$directory" "$source_root" \
    -Ddrivers=goodix_27c6_5125,aes3500 \
    -Dintrospection=true \
    -Ddoc=false \
    -Dinstalled-tests=false \
    -Dudev_rules=disabled \
    -Dudev_hwdb=disabled "$@"
}

configure "$build_dir"
meson compile -C "$build_dir" test-goodix-nbis-resize-quality-pipe
grep -F 'test_goodix_nbis_resize_quality_pipe.c' \
  "$build_dir/compile_commands.json" >/dev/null
if grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)' \
     "$helper_source"; then
  echo "resize/quality helper unexpectedly contains a production/USB entry point" >&2
  exit 1
fi
helper="$build_dir/tests/test-goodix-nbis-resize-quality-pipe"
if nm "$helper" |
   grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)'; then
  echo "resize/quality binary unexpectedly links a production/USB entry point" >&2
  exit 1
fi
for symbol in get_minutiae free_minutiae g_lfsparms_V2 fpi_image_resize; do
  if nm -u "$helper" | grep -Eq "(^|[[:space:]])${symbol}$"; then
    echo "resize/quality helper leaves pinned symbol unresolved: $symbol" >&2
    exit 1
  fi
done
run_python_adapter "$helper"

sanitized_build_dir="$build_dir-sanitized"
configure "$sanitized_build_dir" -Db_sanitize=address,undefined
meson compile -C "$sanitized_build_dir" test-goodix-nbis-resize-quality-pipe
if nm "$sanitized_build_dir/tests/test-goodix-nbis-resize-quality-pipe" |
   grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)'; then
  echo "sanitized resize/quality binary unexpectedly links production/USB" >&2
  exit 1
fi
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  run_python_adapter "$sanitized_build_dir/tests/test-goodix-nbis-resize-quality-pipe"

echo D279_39_EXACT_TARGET_LIBFPRINT=1.94.100
echo D279_39_RESIZE=FPI_IMAGE_RESIZE_PIXMAN_BILINEAR_FACTORS_2_3
echo D279_39_QUALITY=NBIS_QUALITY_MAP_AND_PPMM_0_RELIABILITY_TIERS
echo D279_39_NORMAL_AND_ASAN_UBSAN=PASS
echo D279_39_IMAGE_PATH_INPUT=false
echo D279_39_PRODUCTION_USB_REACHED=false
echo REAL_USB_ENUMERATION_COUNT=0
echo REAL_USB_OPEN_COUNT=0
echo REAL_USB_CLAIM_COUNT=0
echo REAL_USB_SUBMIT=0
echo LIVE_EXECUTION_PERFORMED=false
