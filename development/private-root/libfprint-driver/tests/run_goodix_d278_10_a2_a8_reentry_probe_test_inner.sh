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

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gio-unix-2.0 gobject-2.0)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gio-unix-2.0 gobject-2.0)
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion -ffunction-sections -fdata-sections"
includes="-I$test_dir/support/d277 -I$root/libfprint-driver -I$root/tools"

build_run_tests () {
  name=$1
  extra=$2
  gcc $strict $extra $cflags $includes \
    "$root/libfprint-driver/goodix_a0_protocol.c" \
    "$root/tools/goodix_d278_a2_a8_reentry_probe.c" \
    "$test_dir/test_goodix_d278_10_a2_a8_reentry_probe.c" \
    $libs -Wl,--gc-sections -o "$build/$name"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build/$name"
}

build_run_tests d278_10_tests ""
build_run_tests d278_10_tests_repeat ""
echo D278_10_NORMAL_DETERMINISM_RUNS=2_PASS
build_run_tests d278_10_tests_sanitized \
  "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D278_10_ASAN_UBSAN=PASS

test -f "$host_gusb"
gcc $strict -DD278_10_LIVE_BINDING \
  -DD278_10_APPROVED_BASELINE='"UNAPPROVED_FOR_LIVE"' \
  $cflags $includes \
  "$root/libfprint-driver/goodix_a0_protocol.c" \
  "$root/tools/goodix_d278_a2_a8_reentry_probe.c" \
  "$root/tools/d278_a2_a8_reentry_observe_once.c" \
  -L"$build" -Wl,-rpath-link,"$build" -l:libgusb.so.2 $libs \
  -Wl,--gc-sections -o "$build/d278_a2_a8_reentry_observe_once"

self_test_output=$(LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  timeout 30 "$build/d278_a2_a8_reentry_observe_once" --self-test)
echo "$self_test_output"
echo "$self_test_output" | grep -F '"goodix_command_count":2' >/dev/null
echo "$self_test_output" | grep -F '"out_submit_count":2' >/dev/null
echo "$self_test_output" | grep -F '"a2_sensor_only_submit_count":1' >/dev/null
echo "$self_test_output" | grep -F '"a2_ack_count":1' >/dev/null
echo "$self_test_output" | grep -F '"a2_typed_response_count":1' >/dev/null
echo "$self_test_output" | grep -F '"a8_submit_count":1' >/dev/null
echo "$self_test_output" | grep -F '"a8_ack_count":1' >/dev/null
echo "$self_test_output" | grep -F '"a8_typed_response_count":1' >/dev/null
echo "$self_test_output" | grep -F '"a8_app12509_pin_match":true' >/dev/null
echo "$self_test_output" | grep -F '"physical_in_submit_count":4' >/dev/null
echo "$self_test_output" | grep -F '"physical_in_completion_count":4' >/dev/null
echo "$self_test_output" | grep -F '"retry_count":0' >/dev/null
echo "$self_test_output" | grep -F '"tls_handshake_count":0' >/dev/null
echo "$self_test_output" | grep -F '"backend_drained":true' >/dev/null
echo "$self_test_output" | grep -F '"cleanup_completed":true' >/dev/null

set +e
LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  timeout 30 "$build/d278_a2_a8_reentry_observe_once" \
  --live-same-session-a2-a8-observe-once >"$build/live_gate.stdout" \
  2>"$build/live_gate.stderr"
live_gate_rc=$?
set -e
test "$live_gate_rc" -eq 3
grep -F 'LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED' \
  "$build/live_gate.stderr" >/dev/null

core="$root/tools/goodix_d278_a2_a8_reentry_probe.c"
runtime_sources="$core $root/tools/d278_a2_a8_reentry_observe_once.c"
grep -F 'goodix_a0_build_frame (0xa2, 0xa2, body, sizeof body, error)' \
  "$core" >/dev/null
grep -F 'goodix_a0_build_frame (0xa8, 0xa8, body, sizeof body, error)' \
  "$core" >/dev/null
if grep -En '0xe4|0x70|0x80|0x90|0xd1|0xe0|0xa4|0xf0|0xf4' "$core"; then
  echo FORBIDDEN_COMMAND_CONTROL_SOURCE_AUDIT=FAIL >&2
  exit 1
fi
if grep -En 'goodix_secure_session|GoodixSecureSession|SSL_|g_usb_device_reset|g_usb_device_clear_halt|control_transfer' $runtime_sources; then
  echo FORBIDDEN_CALL_OR_CONTROL_SOURCE_AUDIT=FAIL >&2
  exit 1
fi
if nm -u "$build/d278_a2_a8_reentry_observe_once" | \
   grep -E '(SSL_|goodix_secure_session|g_usb_device_reset|clear_halt|control_transfer)'; then
  echo FORBIDDEN_SYMBOL_AUDIT=FAIL >&2
  exit 1
fi

echo D278_10_FOCAL_TEST_COUNT=14
echo D278_10_LIVE_CAPABLE_LAUNCHER_BUILD=PASS
echo D278_10_LIVE_CAPABLE_LAUNCHER_EXECUTED=false
echo D278_10_UNAPPROVED_LIVE_GATE=PASS_BEFORE_USB_CONTEXT
echo GOODIX_COMMAND_SUBMIT_MAX=2
echo GOODIX_BULK_OUT_SUBMIT_MAX=2
echo A2_SENSOR_ONLY_SUBMIT_MAX=1
echo A8_SUBMIT_MAX=1
echo PHYSICAL_BULK_IN_SUBMIT_MAX=4
echo PHYSICAL_BULK_IN_COMPLETION_MAX=4
echo E4_SUBMIT_MAX=0
echo A2_MCU_ONLY_SUBMIT_MAX=0
echo TLS_HANDSHAKE_COUNT=0
echo RETRY_COUNT=0
echo REOPEN_COUNT=0
echo DEVICE_RESET_COUNT=0
echo CLEAR_HALT_COUNT=0
echo PERSISTENT_DEVICE_WRITE_COUNT=0
echo FORBIDDEN_SYMBOL_AND_CALL_AUDIT=PASS
echo REAL_USB_ACCESS=false
echo LIVE_EXECUTION_PERFORMED=false
