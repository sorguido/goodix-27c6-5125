#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Host-only, reproducible build/test harness for the REAL local SIGFM
# implementation (Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp) linked against
# a real OpenCV4-dev install via pkg-config.
#
# Safety invariants (host-only, no device, no secret, no network at runtime):
#   - no USB access / no libfprint device glue;
#   - no fprintd mutation;
#   - no secret materialization;
#   - no package installation;
#   - no system modification;
#   - no OpenCV vendoring;
#   - does not change production thresholds / keypoint gate / match policy.
#
# Behavior matrix (fail-closed on missing dependency, never a fake PASS):
#   REAL_SIGFM_DEPENDENCY=BLOCKED_OPENCV4_DEV_UNAVAILABLE  -> exit 0 (SKIP)
#   build/link/runtime failure                              -> exit 1 (FAIL)
#   all stages PASS                                        -> exit 0 (PASS)
set -u

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
git_root=$(git -C "$script_dir" rev-parse --show-toplevel)
sigfm_dir="$git_root/Rockytkg/libfprint/libfprint/sigfm"
drv_dir="$git_root/libfprint-driver"
test_dir="$git_root/libfprint-driver/tests"

build_dir=$(mktemp -d /tmp/goodix-sigfm-real-host.XXXXXX)
cleanup ()
{
  rm -rf "$build_dir"
}
trap cleanup EXIT HUP INT TERM

if ! command -v pkg-config >/dev/null 2>&1; then
  echo "REAL_SIGFM_EXECUTABLE_CLOSURE=BLOCKED_ENVIRONMENT"
  echo "REAL_SIGFM_DEPENDENCY=BLOCKED_ENVIRONMENT (pkg-config missing)"
  exit 77
fi

if ! pkg-config --exists opencv4; then
  echo "REAL_SIGFM_EXECUTABLE_CLOSURE=BLOCKED_ENVIRONMENT"
  echo "REAL_SIGFM_DEPENDENCY=BLOCKED_OPENCV4_DEV_UNAVAILABLE"
  exit 77
fi

ocv_cflags=$(pkg-config --cflags opencv4)
ocv_libs=$(pkg-config --libs opencv4)

# Differentiated warning policy (Phase D):
#   project code (adapter, metrics wrapper, real test) -> full -Werror set
#   third-party reference SIGFM (Rockytkg/libfprint/sigfm) -> relaxed (-Wall -Wextra),
#   headers included via -isystem so project warnings stay visible.
cflags="-std=c11 -O2 -g -Wall -Wextra -Werror -Wconversion"
cxxflags="-std=c++17 -O2 -g -Wall -Wextra -Werror -Wconversion -Wshadow -Wold-style-cast"
tp_includes="-isystem$sigfm_dir"
drv_includes="-I$drv_dir"

echo "REAL_SIGFM_DEPENDENCY=AVAILABLE"
echo "OPENCV4_VERSION=$(pkg-config --modversion opencv4)"

# --- normal real build ---
gcc $cflags $drv_includes -c "$drv_dir/goodix_u16_to_fpimage.c" -o "$build_dir/adapter.o" || {
  echo "REAL_SIGFM_BUILD=FAIL adapter"; exit 1; }
g++ $cxxflags $drv_includes $tp_includes $ocv_cflags -c "$drv_dir/goodix_sigfm_metrics.cpp" -o "$build_dir/metrics.o" || {
  echo "REAL_SIGFM_BUILD=FAIL metrics"; exit 1; }
g++ -std=c++17 -O2 -g -Wall -Wextra $tp_includes $ocv_cflags -c "$sigfm_dir/sigfm.cpp" -o "$build_dir/sigfm.o" || {
  echo "REAL_SIGFM_BUILD=FAIL sigfm"; exit 1; }
g++ $cxxflags $drv_includes $tp_includes -I"$test_dir" -c "$test_dir/test_goodix_sigfm_metrics_real.cpp" -o "$build_dir/test.o" || {
  echo "REAL_SIGFM_BUILD=FAIL test"; exit 1; }

echo "REAL_SIGFM_BUILD=PASS_HOST_ONLY_WITH_REAL_OPENCV4"

# forbidden-symbol audit: our wrapper must not pull device/secret/TLS I/O
if nm -u "$build_dir/metrics.o" | grep -E "(libusb_|SSL_|gnutls_|socket|fopen|open|write|read)"; then
  echo "forbidden-symbol audit: FAIL"; exit 1
fi
echo "forbidden-symbol audit: PASS"

g++ "$build_dir/adapter.o" "$build_dir/metrics.o" "$build_dir/sigfm.o" "$build_dir/test.o" $ocv_libs -o "$build_dir/test-goodix-sigfm-real" || {
  echo "REAL_SIGFM_LINK=FAIL"; exit 1; }
echo "REAL_SIGFM_LINK=PASS"

"$build_dir/test-goodix-sigfm-real" || {
  echo "REAL_SIGFM_SYNTHETIC_RUNTIME=FAIL"; exit 1; }
echo "REAL_SIGFM_SYNTHETIC_RUNTIME=PASS"
echo "REAL_SIGFM_EXECUTABLE_CLOSURE=PASS_HOST_ONLY"

# --- sanitizer pass (classified separately; env incompatibility is not a FAIL) ---
san="-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined"
sb=$(mktemp -d /tmp/goodix-sigfm-real-san.XXXXXX)
gcc $cflags $san $drv_includes -c "$drv_dir/goodix_u16_to_fpimage.c" -o "$sb/adapter.o" && \
g++ $cxxflags $san $drv_includes $tp_includes $ocv_cflags -c "$drv_dir/goodix_sigfm_metrics.cpp" -o "$sb/metrics.o" && \
g++ -std=c++17 -O2 -g -Wall -Wextra $san $tp_includes $ocv_cflags -c "$sigfm_dir/sigfm.cpp" -o "$sb/sigfm.o" && \
g++ $cxxflags $san $drv_includes $tp_includes -I"$test_dir" -c "$test_dir/test_goodix_sigfm_metrics_real.cpp" -o "$sb/test.o" && \
g++ $san "$sb/adapter.o" "$sb/metrics.o" "$sb/sigfm.o" "$sb/test.o" $ocv_libs -o "$sb/test-san"
san_status="ENVIRONMENT_INCOMPATIBLE"
if [ $? -eq 0 ]; then
  if ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$sb/test-san" >/dev/null 2>&1; then
    san_status="PASS"
  else
    san_status="RUNTIME_FOUND_ISSUE"
  fi
fi
echo "REAL_SIGFM_SANITIZER_STATUS=$san_status"
echo "REAL_SIGFM_ASAN_UBSAN_STATUS=$san_status"
echo "LEAK_DETECTION=DISABLED"
echo "MEMORY_SAFETY_SCOPE=ASAN_UBSAN_RUNTIME_NO_DETECTED_ADDRESS_OR_UB_ERRORS_LEAKS_NOT_ASSESSED"
rm -rf "$sb"

exit 0
