#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 6 ]; then
  echo "usage: $0 <source-root> <build-dir> <host-libgusb> <approved-sha-or-unapproved> <synthetic-existing-ref> <other-existing-ref>" >&2
  exit 2
fi
root=$1
build=$2
host_gusb=$3
approved=$4
test_reference=$5
test_other_reference=$6
test_dir="$root/libfprint-driver/tests"
local_fp="$root/Rockytkg/libfprint/libfprint"

case "$approved" in
  UNAPPROVED_FOR_LIVE) ;;
  ????????????????????????????????????????)
    echo "$approved" | grep -Eq '^[0-9a-fA-F]{40}$' || exit 2 ;;
  *) echo "invalid approved baseline" >&2; exit 2 ;;
esac

cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0 openssl)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0 openssl)
includes="-I$test_dir/support/d277 -I$test_dir/support -I$build -I$root/libfprint-driver -I$root/tools -I$root/Rockytkg/libfprint -I$local_fp -I$local_fp/nbis/include -I$local_fp/nbis/libfprint-include"
strict="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion -ffunction-sections -fdata-sections"
local_flags="-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter -Wno-missing-prototypes -Wno-discarded-qualifiers -Wno-sign-compare -Wno-cast-function-type -Wno-enum-conversion -Wno-maybe-uninitialized -ffunction-sections -fdata-sections"
approved_define="-DD278_13_APPROVED_BASELINE=\"$approved\""
if [ "$approved" = UNAPPROVED_FOR_LIVE ]; then
  binary="$build/d278_integrated_path_once"
else
  binary="$build/d278_integrated_path_once.pending"
fi

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

compile_local () { gcc $local_flags $cflags $includes -c "$1" -o "$2"; }
compile_strict () { gcc $strict -DGOODIX_ENABLE_TEST_SEAMS -DD278_13_LIVE_BINDING $approved_define $cflags $includes -c "$1" -o "$2"; }

compile_local "$local_fp/fp-device.c" "$build/fp-device.o"
compile_local "$local_fp/fpi-device.c" "$build/fpi-device.o"
compile_local "$local_fp/fp-image-device.c" "$build/fp-image-device.o"
compile_local "$local_fp/fpi-image-device.c" "$build/fpi-image-device.o"
compile_local "$local_fp/fp-image.c" "$build/fp-image.o"
compile_local "$local_fp/fp-print.c" "$build/fp-print.o"
compile_local "$local_fp/fpi-print.c" "$build/fpi-print.o"
compile_local "$local_fp/fpi-usb-transfer.c" "$build/fpi-usb-transfer.o"
compile_local "$build/fp-enums.c" "$build/fp-enums.o"
compile_local "$build/fpi-enums.c" "$build/fpi-enums.o"
compile_local "$test_dir/support/fpimage_link_stubs.c" "$build/fpimage_link_stubs.o"

for source in \
  goodix_u16_to_fpimage goodix_fpimage_pipeline goodix_usb_router \
  goodix_a0_protocol goodix_d190_binder goodix_target_material \
  goodix_runtime_inputs goodix_runtime_material \
  goodix_secure_session goodix_image_decoder goodix_post_tls_lifecycle \
  goodix_fpimage_device goodix_tls_server goodix_fpi_usb_backend; do
  compile_strict "$root/libfprint-driver/$source.c" "$build/$source.o"
done
compile_strict "$root/tools/goodix_d190_pe.c" "$build/goodix_d190_pe.o"
compile_strict "$root/tools/d278_integrated_path_once.c" \
  "$build/d278_integrated_path_once.o"

gcc -Wl,--gc-sections \
  "$build/fp-device.o" "$build/fpi-device.o" \
  "$build/fp-image-device.o" "$build/fpi-image-device.o" \
  "$build/fp-image.o" "$build/fp-print.o" "$build/fpi-print.o" \
  "$build/fpi-usb-transfer.o" "$build/fp-enums.o" "$build/fpi-enums.o" \
  "$build/goodix_u16_to_fpimage.o" "$build/goodix_fpimage_pipeline.o" \
  "$build/goodix_usb_router.o" "$build/goodix_a0_protocol.o" \
  "$build/goodix_d190_binder.o" "$build/goodix_target_material.o" \
  "$build/goodix_runtime_inputs.o" "$build/goodix_runtime_material.o" \
  "$build/goodix_secure_session.o" "$build/goodix_image_decoder.o" \
  "$build/goodix_post_tls_lifecycle.o" "$build/goodix_fpimage_device.o" \
  "$build/goodix_tls_server.o" "$build/goodix_fpi_usb_backend.o" \
  "$build/goodix_d190_pe.o" "$build/d278_integrated_path_once.o" \
  "$build/fpimage_link_stubs.o" \
  -L"$build" -Wl,-rpath-link,"$build" -l:libgusb.so.2 $libs -lm \
  -o "$binary"

test -f "$host_gusb"
echo D278_13_LIVE_ADAPTER_BUILD=PASS
(
  cd "$root"
  output=$(LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    timeout 30 "$binary" --physical-constructor-host-only)
  echo "$output"
  echo "$output" | grep -F \
    'FPDEVICE_USB_BINDING_CONSTRUCTION_HOST_ONLY=PASS' >/dev/null
  echo "$output" | grep -F 'FPDEVICE_TRANSPORT_TYPE=USB' >/dev/null
  echo "$output" | grep -F 'NON_NULL_GUSBDEVICE_BOUND=true' >/dev/null
  echo "$output" | grep -F \
    'NON_NULL_GUSBDEVICE_FPDEVICE_BINDING_HOST_ONLY_PROVEN=true' >/dev/null
  echo "$output" | grep -F 'SINGLE_GOODIX_DEVICE_CONTEXT=true' >/dev/null
  echo "$output" | grep -F 'SINGLE_USB_BACKEND_OWNER=true' >/dev/null
  echo "$output" | grep -F 'SINGLE_USB_ROUTER=true' >/dev/null
  echo "$output" | grep -F 'REAL_USB_ENUMERATION_COUNT=0' >/dev/null
  echo "$output" | grep -F 'REAL_USB_OPEN_COUNT=0' >/dev/null
  echo "$output" | grep -F 'REAL_USB_CLAIM_COUNT=0' >/dev/null
  echo "$output" | grep -F 'REAL_USB_ACCESS=false' >/dev/null
  echo "$output" | grep -F 'REAL_USB_SUBMIT=0' >/dev/null
  echo "$output" | grep -F 'REAL_PRODUCTION_SECRET_READ=false' >/dev/null
)
tool_source="$root/tools/d278_integrated_path_once.c"
constructor_line=$(grep -n \
  'device = goodix_fpimage_device_new_for_usb (target);' "$tool_source" | \
  cut -d: -f1)
open_line=$(grep -n 'if (!g_usb_device_open (target' "$tool_source" | \
  cut -d: -f1)
claim_line=$(grep -n 'if (!g_usb_device_claim_interface (target' \
  "$tool_source" | cut -d: -f1)
test -n "$constructor_line" && test -n "$open_line" && test -n "$claim_line"
test "$constructor_line" -lt "$open_line"
test "$open_line" -lt "$claim_line"
echo PHYSICAL_CONSTRUCTOR_BEFORE_USB_OPEN_CLAIM=true
(
  cd "$root"
  output=$(env -u D278_13_APPROVED_LIVE_BASELINE_SHA \
    -u D278_13_OPERATOR_AUTHORIZATION -u D278_13_OPERATION \
    -u D278_13_AUTHORIZATION_TICKET \
    LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    timeout 30 "$binary" \
      --authorization-gate-self-test)
  echo "$output"
  echo "$output" | grep -F 'EXECUTABLE_CLOSURE=PASS_HOST_ONLY' >/dev/null
  echo "$output" | grep -F 'REAL_USB_ACCESS=false' >/dev/null
  echo "$output" | grep -F 'REAL_PRODUCTION_SECRET_READ=false' >/dev/null
)
if [ "$approved" = UNAPPROVED_FOR_LIVE ]; then
  (
    cd "$root"
    set +e
    output=$(LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
      timeout 30 "$binary" \
        --live-integrated-once 2>&1)
    rc=$?
    set -e
    test "$rc" -eq 3
    echo "$output" | grep -F \
      'LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED' >/dev/null
    echo "$output" | grep -F 'LIVE_AUTHORIZATION_CONSUMED=false' >/dev/null
    echo "$output" | grep -F 'REAL_PRODUCTION_SECRET_READ=false' >/dev/null
    echo "$output" | grep -F 'REAL_USB_ACCESS=false' >/dev/null
    echo "$output" | grep -F 'REAL_USB_SUBMIT=0' >/dev/null
  )
  echo D278_13_GATE_BEFORE_SECRET_CACHE_OR_USB=PASS
fi

LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$test_dir/test_goodix_d278_13_live_guards.sh" \
  --ticket-only "$binary" "$test_reference" "$test_other_reference" "$build"

runtime_sources="$root/libfprint-driver/goodix_fpimage_device.c $root/libfprint-driver/goodix_secure_session.c $root/libfprint-driver/goodix_post_tls_lifecycle.c $root/tools/d278_integrated_path_once.c"
if grep -En '0x[eE]0|0x[aA]4|production_write_key|ClearApp|IAP|firmware[ _-]*update|g_usb_device_reset|g_usb_device_clear_halt|libusb_reset_device|libusb_clear_halt' $runtime_sources; then
  echo D278_13_FORBIDDEN_PERSISTENT_RECOVERY_SOURCE_AUDIT=FAIL >&2
  exit 1
fi
if nm -u "$binary" | \
   grep -E 'g_usb_device_(reset|clear_halt)|libusb_(reset_device|clear_halt)|production_write_key|ClearApp|IAP|firmware[ _-]*update'; then
  echo D278_13_FORBIDDEN_PERSISTENT_RECOVERY_SYMBOL_AUDIT=FAIL >&2
  exit 1
fi
echo D278_13_FORBIDDEN_PERSISTENT_RECOVERY_SOURCE_AUDIT=PASS
echo D278_13_FORBIDDEN_PERSISTENT_RECOVERY_SYMBOL_AUDIT=PASS
if grep -En 'goodix_(secure_session|tls_server|post_tls_lifecycle|fpi_usb_backend|usb_router)_new' \
     "$root/tools/d278_integrated_path_once.c"; then
  echo D278_13_DUPLICATE_STACK_SOURCE_AUDIT=FAIL >&2
  exit 1
fi
if nm "$binary" | grep -F 'goodix_d278_harness_' ; then
  echo D278_13_LEGACY_HARNESS_FALLBACK_AUDIT=FAIL >&2
  exit 1
fi
echo D278_13_DUPLICATE_STACK_SOURCE_AUDIT=PASS
echo D278_13_LEGACY_HARNESS_FALLBACK_AUDIT=PASS
echo REAL_USB_ACCESS=false
echo REAL_USB_SUBMIT=0
echo REAL_PRODUCTION_SECRET_READ=false
echo LIVE_EXECUTION_PERFORMED=false
echo CURRENT_LIVE_AUTHORIZED=false
echo READY_FOR_LIVE=false
echo RETRY_AUTHORIZED=false
