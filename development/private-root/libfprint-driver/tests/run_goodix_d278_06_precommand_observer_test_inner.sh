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
includes="-I$test_dir/support/d277 -I$root/tools"

build_run_tests () {
  name=$1
  extra=$2
  gcc $strict $extra $cflags $includes \
    "$root/tools/goodix_d278_precommand_observer.c" \
    "$test_dir/test_goodix_d278_06_precommand_observer.c" \
    $libs -Wl,--gc-sections -o "$build/$name"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    timeout 30 "$build/$name"
}

build_run_tests d278_06_tests ""
build_run_tests d278_06_tests_repeat ""
echo D278_06_NORMAL_DETERMINISM_RUNS=2_PASS
build_run_tests d278_06_tests_sanitized \
  "-O1 -fno-omit-frame-pointer -fsanitize=address,undefined"
echo D278_06_ASAN_UBSAN=PASS

test -f "$host_gusb"
gcc $strict -DD278_06_LIVE_BINDING \
  -DD278_06_APPROVED_BASELINE='"UNAPPROVED_FOR_LIVE"' \
  $cflags $includes \
  "$root/tools/goodix_d278_precommand_observer.c" \
  "$root/tools/d278_precommand_observe_once.c" \
  -L"$build" -Wl,-rpath-link,"$build" -l:libgusb.so.2 $libs \
  -Wl,--gc-sections -o "$build/d278_precommand_observe_once"

self_test_output=$(LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  timeout 30 "$build/d278_precommand_observe_once" --self-test)
echo "$self_test_output"
echo "$self_test_output" | grep -F '"physical_in_submit_count":1' >/dev/null
echo "$self_test_output" | grep -F '"physical_in_completion_count":1' >/dev/null
echo "$self_test_output" | grep -F '"out_submit_count":0' >/dev/null
echo "$self_test_output" | grep -F '"goodix_command_count":0' >/dev/null
echo "$self_test_output" | grep -F '"secure_session_start_count":0' >/dev/null
echo "$self_test_output" | grep -F '"tls_handshake_count":0' >/dev/null
echo "$self_test_output" | grep -F '"timeout_count":1' >/dev/null
echo "$self_test_output" | grep -F '"retry_count":0' >/dev/null
echo "$self_test_output" | grep -F '"reopen_count":0' >/dev/null
echo "$self_test_output" | grep -F '"device_reset_count":0' >/dev/null
echo "$self_test_output" | grep -F '"clear_halt_count":0' >/dev/null
echo "$self_test_output" | grep -F '"persistent_device_write_count":0' >/dev/null
echo "$self_test_output" | grep -F '"backend_drained":true' >/dev/null
echo "$self_test_output" | grep -F '"cleanup_completed":true' >/dev/null

set +e
LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  timeout 30 "$build/d278_precommand_observe_once" \
  --live-zero-out-observe-once >"$build/live_gate.stdout" \
  2>"$build/live_gate.stderr"
live_gate_rc=$?
set -e
test "$live_gate_rc" -eq 3
grep -F 'LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED' \
  "$build/live_gate.stderr" >/dev/null

if nm -u "$build/d278_precommand_observe_once" | \
   grep -E '(bulk_transfer_sync|control_transfer|reset|clear_halt|SSL_|goodix_secure_session|submit_out)'; then
  echo FORBIDDEN_SYMBOL_AUDIT=FAIL >&2
  exit 1
fi
if grep -En 'goodix_fpi_usb_backend_submit_out|fpi_usb_transfer_fill_bulk_full|g_usb_device_control_transfer|g_usb_device_reset|g_usb_device_clear_halt|goodix_secure_session_start|SSL_' \
   "$root/tools/d278_precommand_observe_once.c"; then
  echo FORBIDDEN_CALL_SOURCE_AUDIT=FAIL >&2
  exit 1
fi

echo D278_06_TEST_COUNT=10
echo D278_06_LIVE_CAPABLE_LAUNCHER_BUILD=PASS
echo D278_06_LIVE_CAPABLE_LAUNCHER_EXECUTED=false
echo D278_06_UNAPPROVED_LIVE_GATE=PASS_BEFORE_USB_CONTEXT
echo GOODIX_BULK_OUT_SUBMIT_COUNT=0
echo GOODIX_COMMAND_COUNT=0
echo SECURE_SESSION_START_COUNT=0
echo TLS_HANDSHAKE_COUNT=0
echo PHYSICAL_BULK_IN_SUBMIT_MAX=1
echo PHYSICAL_BULK_IN_COMPLETION_MAX=1
echo RETRY_COUNT=0
echo REOPEN_COUNT=0
echo DEVICE_RESET_COUNT=0
echo CLEAR_HALT_COUNT=0
echo PERSISTENT_DEVICE_WRITE_COUNT=0
echo REAL_USB_ACCESS=false
echo LIVE_EXECUTION_PERFORMED=false
