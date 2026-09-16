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
helper_source="$repo_root/libfprint-driver/tests/test_goodix_nbis_resize_count_pipe.c"
evaluator_module="$repo_root/analysis/D279/d279_37_spatial_resize_evaluator.py"

export PKG_CONFIG_PATH=$pkgconfig_dir

run_zero_frames ()
{
  helper=$1
  output=$(python3 -c '
import struct, sys
for factor in (1, 2, 3):
    sys.stdout.buffer.write(struct.pack("<4sHHII", b"NBR1", 80, 64, 5120, factor))
    sys.stdout.buffer.write(bytes(5120))
' | "$helper")
  test "$output" = "NBISR 1 0
NBISR 2 0
NBISR 3 0"
}

run_python_adapter ()
{
  helper=$1
  python3 -c '
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("d279_37_pipe_integration", sys.argv[1])
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
with module.ExactLibfprintResizeNbisPipe(pathlib.Path(sys.argv[2])) as runner:
    for factor in module.SPATIAL_FACTORS:
        assert runner.count(bytearray(5120), 80, 64, factor) == 0
' "$evaluator_module" "$helper"
}

configure ()
{
  directory=$1
  shift
  # aes3500 is included only to activate the pinned tree's existing pixman
  # feature switch. The helper links no driver and has no USB entry point.
  meson setup "$directory" "$source_root" \
    -Ddrivers=goodix_27c6_5125,aes3500 \
    -Dintrospection=true \
    -Ddoc=false \
    -Dinstalled-tests=false \
    -Dudev_rules=disabled \
    -Dudev_hwdb=disabled "$@"
}

configure "$build_dir"
meson compile -C "$build_dir" test-goodix-nbis-resize-count-pipe
grep -F 'test_goodix_nbis_resize_count_pipe.c' "$build_dir/compile_commands.json" >/dev/null
if grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)' \
     "$helper_source"; then
  echo "resize/NBIS pipe unexpectedly contains a production/USB entry point" >&2
  exit 1
fi
run_zero_frames "$build_dir/tests/test-goodix-nbis-resize-count-pipe"
if nm "$build_dir/tests/test-goodix-nbis-resize-count-pipe" |
   grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)'; then
  echo "resize/NBIS binary unexpectedly links a production/USB entry point" >&2
  exit 1
fi
run_python_adapter "$build_dir/tests/test-goodix-nbis-resize-count-pipe"

sanitized_build_dir="$build_dir-sanitized"
configure "$sanitized_build_dir" -Db_sanitize=address,undefined
meson compile -C "$sanitized_build_dir" test-goodix-nbis-resize-count-pipe
if nm "$sanitized_build_dir/tests/test-goodix-nbis-resize-count-pipe" |
   grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)'; then
  echo "sanitized resize/NBIS binary unexpectedly links a production/USB entry point" >&2
  exit 1
fi
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  run_zero_frames "$sanitized_build_dir/tests/test-goodix-nbis-resize-count-pipe"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  run_python_adapter "$sanitized_build_dir/tests/test-goodix-nbis-resize-count-pipe"

echo D279_37_EXACT_TARGET_LIBFPRINT=1.94.100
echo D279_37_RESIZE=FPI_IMAGE_RESIZE_PIXMAN_BILINEAR_FACTORS_2_3
echo D279_37_FACTOR_1_CONTROL=D279_34_EXACT_NBIS_PATH
echo D279_37_NORMAL_AND_ASAN_UBSAN=PASS
echo D279_37_IMAGE_PATH_INPUT=false
echo D279_37_PRODUCTION_USB_REACHED=false
echo REAL_USB_ENUMERATION_COUNT=0
echo REAL_USB_OPEN_COUNT=0
echo REAL_USB_CLAIM_COUNT=0
echo REAL_USB_SUBMIT=0
echo LIVE_EXECUTION_PERFORMED=false
