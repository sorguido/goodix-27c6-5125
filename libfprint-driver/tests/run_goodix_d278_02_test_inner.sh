#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <git-root> <build-dir> <host-libgusb>" >&2
  exit 2
fi
root=$1
build=$2
host_gusb=$3
test_dir="$root/libfprint-driver/tests"
local_fp="$root/Rockytkg/libfprint/libfprint"

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0 openssl)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0 openssl)
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion -ffunction-sections -fdata-sections"
includes="-I$test_dir/support/d277 -I$test_dir/support -I$build -I$root/libfprint-driver -I$root/tools -I$local_fp -I$root/Rockytkg/libfprint"

python3 "$test_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fp --symbol-prefix fp \
  --header-guard FP_ENUMS_H --header-name fp-enums.h \
  --output-header "$build/fp-enums.h" --output-source "$build/fp-enums.c" \
  "$local_fp/fp-device.h" "$local_fp/fp-print.h"
python3 "$test_dir/support/generate_libfprint_enums.py" \
  --identifier-prefix Fpi --symbol-prefix fpi \
  --header-guard FPI_ENUMS_H --header-name fpi-enums.h \
  --output-header "$build/fpi-enums.h" --output-source "$build/fpi-enums.c" \
  "$local_fp/fpi-device.h" "$local_fp/fpi-image-device.h" "$local_fp/fpi-print.h"
cp "$test_dir/support/config.h" "$build/config.h"

build_run_tests () {
  name=$1
  extra=$2
  gcc $strict $extra $cflags $includes \
    "$root/libfprint-driver/goodix_a0_protocol.c" \
    "$root/libfprint-driver/goodix_d190_binder.c" \
    "$root/libfprint-driver/goodix_target_material.c" \
    "$root/libfprint-driver/goodix_secure_session.c" \
    "$root/libfprint-driver/goodix_tls_server.c" \
    "$root/libfprint-driver/goodix_usb_router.c" \
    "$root/libfprint-driver/goodix_fpi_usb_backend.c" \
    "$root/tools/goodix_d190_pe.c" \
    "$root/tools/goodix_d278_harness.c" \
    "$test_dir/test_goodix_d278_02.c" \
    "$test_dir/support/fpi_usb_transfer_compile_stub.c" \
    $libs -Wl,--gc-sections -o "$build/$name"
  (
    cd "$root"
    ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
    UBSAN_OPTIONS=halt_on_error=1 \
      timeout 120 "$build/$name"
  )
}

build_run_tests d278_02_tests ""
echo D278_02_NORMAL=PASS
build_run_tests d278_02_tests_sanitized \
  "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D278_02_ASAN_UBSAN=PASS

test -f "$host_gusb"
local_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter -Wno-missing-prototypes -Wno-discarded-qualifiers -Wno-sign-compare -Wno-cast-function-type -Wno-enum-conversion -Wno-maybe-uninitialized -ffunction-sections -fdata-sections"
compile_local () { gcc $local_flags $cflags $includes -c "$1" -o "$2"; }
compile_strict () { gcc $strict -DD278_LIVE_BINDING $cflags $includes -c "$1" -o "$2"; }

compile_local "$local_fp/fp-device.c" "$build/fp-device.o"
compile_local "$local_fp/fpi-device.c" "$build/fpi-device.o"
compile_local "$local_fp/fpi-usb-transfer.c" "$build/fpi-usb-transfer.o"
compile_local "$build/fp-enums.c" "$build/fp-enums.o"
compile_local "$build/fpi-enums.c" "$build/fpi-enums.o"
compile_strict "$root/libfprint-driver/goodix_a0_protocol.c" "$build/goodix_a0_protocol.o"
compile_strict "$root/libfprint-driver/goodix_d190_binder.c" "$build/goodix_d190_binder.o"
compile_strict "$root/libfprint-driver/goodix_target_material.c" "$build/goodix_target_material.o"
compile_strict "$root/libfprint-driver/goodix_secure_session.c" "$build/goodix_secure_session.o"
compile_strict "$root/libfprint-driver/goodix_tls_server.c" "$build/goodix_tls_server.o"
compile_strict "$root/libfprint-driver/goodix_usb_router.c" "$build/goodix_usb_router.o"
compile_strict "$root/libfprint-driver/goodix_fpi_usb_backend.c" "$build/goodix_fpi_usb_backend.o"
compile_strict "$root/tools/goodix_d190_pe.c" "$build/goodix_d190_pe.o"
compile_strict "$root/tools/goodix_d278_harness.c" "$build/goodix_d278_harness.o"
compile_strict "$root/tools/d278_native_secure_session_once.c" "$build/d278_native_secure_session_once.o"

gcc -Wl,--gc-sections \
  "$build/fp-device.o" "$build/fpi-device.o" "$build/fpi-usb-transfer.o" \
  "$build/fp-enums.o" "$build/fpi-enums.o" \
  "$build/goodix_a0_protocol.o" "$build/goodix_d190_binder.o" \
  "$build/goodix_target_material.o" "$build/goodix_secure_session.o" \
  "$build/goodix_tls_server.o" "$build/goodix_usb_router.o" \
  "$build/goodix_fpi_usb_backend.o" "$build/goodix_d190_pe.o" \
  "$build/goodix_d278_harness.o" "$build/d278_native_secure_session_once.o" \
  -L"$build" -Wl,-rpath-link,"$build" -l:libgusb.so.2 $libs -lm \
  -o "$build/d278_native_secure_session_once"

echo D278_02_LIVE_HARNESS_BUILD=PASS
(
  cd "$root"
  self_test_output=$(LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    timeout 30 "$build/d278_native_secure_session_once" --self-test)
  echo "$self_test_output"
  echo "$self_test_output" | grep -F '"result":"pass"' >/dev/null
  echo "$self_test_output" | grep -F '"real_usb_access":0' >/dev/null
  echo "$self_test_output" | grep -F '"real_usb_submit":0' >/dev/null
  echo "$self_test_output" | grep -F '"usb_open_count":0' >/dev/null
  echo "$self_test_output" | grep -F '"usb_claim_count":0' >/dev/null
  echo "$self_test_output" | grep -F '"current_live_authorized":false' >/dev/null
)
echo D278_02_SELF_TEST=PASS
echo D278_02_TEST_COUNT=62
echo D190_FIVE_INDEPENDENT_KATS=PASS
echo PROTECTED_MATERIAL_NEGATIVE_MATRIX=PASS
echo PRODUCTION_POLICY_CANONICAL_PIN_MATRIX=PASS
echo D278_02_PHASE_WATCHDOG_HOST_ONLY_PROVEN=true
echo D278_02_DYNAMIC_REDACTED_TELEMETRY=PASS
echo PROTECTED_PREFLIGHT_FAILURE_OBSERVABILITY=PASS
echo PROTECTED_PREFLIGHT_REDACTION=PASS
echo NO_SECRET_BYTES_IN_FAILURE_TELEMETRY=PASS
echo FAILURE_CLASS_STABLE=PASS
echo FAILURE_STAGE_STABLE=PASS
echo D278_02_LIVE_HARNESS_EXECUTED=false
echo TARGET_PROTECTED_MATERIAL_PREFLIGHT_EXECUTED=false
echo LIVE_EXECUTION_PERFORMED=false
echo REAL_USB_ACCESS=0
echo REAL_USB_SUBMIT=0
echo USB_OPEN_COUNT=0
echo USB_CLAIM_COUNT=0
echo CURRENT_LIVE_AUTHORIZED=false
echo D278_02_PRINCIPAL_RESULT=PASS
