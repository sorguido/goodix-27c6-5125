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
helper_source="$repo_root/libfprint-driver/tests/test_goodix_nbis_count_pipe.c"
evaluator_module="$repo_root/analysis/D279/d279_34_exact_nbis_variant_evaluator.py"

export PKG_CONFIG_PATH=$pkgconfig_dir

run_zero_frame ()
{
  helper=$1
  d279_34_output=$(python3 -c \
    'import struct,sys; sys.stdout.buffer.write(struct.pack("<4sHHI", b"NBS1", 80, 64, 5120) + bytes(5120))' \
    | "$helper")
  test "$d279_34_output" = "NBIS1 0"
}

run_python_adapter ()
{
  helper=$1
  python3 -c '
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("d279_34_pipe_integration", sys.argv[1])
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
with module.ExactNbisPipe(pathlib.Path(sys.argv[2])) as runner:
    assert runner.count(bytearray(5120), 80, 64) == 0
' "$evaluator_module" "$helper"
}

meson setup "$build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled
meson compile -C "$build_dir" test-goodix-nbis-count-pipe

compile_db="$build_dir/compile_commands.json"
grep -F 'test_goodix_nbis_count_pipe.c' "$compile_db" >/dev/null
if grep -E 'goodix_fpimage_device_new_for_usb|g_usb_|fp_context_(new|enumerate)' \
     "$helper_source"; then
  echo "NBIS pipe unexpectedly contains a production/USB entry point" >&2
  exit 1
fi
run_zero_frame "$build_dir/tests/test-goodix-nbis-count-pipe"
run_python_adapter "$build_dir/tests/test-goodix-nbis-count-pipe"

sanitized_build_dir="$build_dir-sanitized"
meson setup "$sanitized_build_dir" "$source_root" \
  -Ddrivers=goodix_27c6_5125 \
  -Dintrospection=true \
  -Ddoc=false \
  -Dinstalled-tests=false \
  -Dudev_rules=disabled \
  -Dudev_hwdb=disabled \
  -Db_sanitize=address,undefined
meson compile -C "$sanitized_build_dir" test-goodix-nbis-count-pipe
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  run_zero_frame "$sanitized_build_dir/tests/test-goodix-nbis-count-pipe"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  run_python_adapter "$sanitized_build_dir/tests/test-goodix-nbis-count-pipe"

echo D279_34_EXACT_TARGET_LIBFPRINT=1.94.100
echo D279_34_EXTRACTOR=NBIS_NATIVE_G_LFSPARMS_V2_PPMM_0_FLAGS_0
echo D279_34_NORMAL_AND_ASAN_UBSAN=PASS
echo D279_34_SYNTHETIC_ZERO_FRAME_COUNT=0
echo D279_34_IMAGE_PATH_INPUT=false
echo D279_34_PRODUCTION_USB_REACHED=false
echo REAL_USB_ENUMERATION_COUNT=0
echo REAL_USB_OPEN_COUNT=0
echo REAL_USB_CLAIM_COUNT=0
echo REAL_USB_SUBMIT=0
echo LIVE_EXECUTION_PERFORMED=false
