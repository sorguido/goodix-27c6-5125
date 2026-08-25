#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
git_root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_dir=$(mktemp -d /tmp/goodix-d272-sigfm.XXXXXX)

cleanup ()
{
  find "$build_dir" -maxdepth 1 -type f -delete
  rmdir "$build_dir"
}
trap cleanup EXIT HUP INT TERM

flatpak run --user --unshare=network \
  --filesystem="$git_root" --filesystem=/tmp \
  --command=sh org.freedesktop.Sdk//25.08 -c '
set -eu
git_root=$1
build_dir=$2
sigfm_dir="$git_root/Rockytkg/libfprint/libfprint/sigfm"
test_dir="$git_root/libfprint-driver/tests"
cflags="-std=c11 -O2 -g -Wall -Wextra -Werror -Wconversion"
cxxflags="-std=c++17 -O2 -g -Wall -Wextra -Werror -Wconversion -Wshadow -Wold-style-cast"
includes="-I$git_root/libfprint-driver -I$test_dir -I$test_dir/support -I$sigfm_dir"

gcc $cflags $includes -c "$git_root/libfprint-driver/goodix_u16_to_fpimage.c" -o "$build_dir/adapter.o"
g++ $cxxflags $includes -c "$git_root/libfprint-driver/goodix_sigfm_metrics.cpp" -o "$build_dir/metrics.o"
g++ $cxxflags $includes -c "$test_dir/support/sigfm_metric_test_double.cpp" -o "$build_dir/double.o"
g++ $cxxflags $includes -c "$test_dir/test_goodix_sigfm_metrics.cpp" -o "$build_dir/test.o"

if nm -u "$build_dir/metrics.o" | grep -E "(serialize|fopen|open|read|write|socket|libusb_|SSL_|gnutls_)"; then
  echo "forbidden persistence, I/O, USB, or TLS symbol" >&2
  exit 1
fi
echo "goodix_sigfm_metrics forbidden-symbol audit: PASS"
g++ "$build_dir/adapter.o" "$build_dir/metrics.o" "$build_dir/double.o" "$build_dir/test.o" -o "$build_dir/test"
"$build_dir/test"

san="-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined"
gcc $cflags $san $includes -c "$git_root/libfprint-driver/goodix_u16_to_fpimage.c" -o "$build_dir/adapter-san.o"
g++ $cxxflags $san $includes -c "$git_root/libfprint-driver/goodix_sigfm_metrics.cpp" -o "$build_dir/metrics-san.o"
g++ $cxxflags $san $includes -c "$test_dir/support/sigfm_metric_test_double.cpp" -o "$build_dir/double-san.o"
g++ $cxxflags $san $includes -c "$test_dir/test_goodix_sigfm_metrics.cpp" -o "$build_dir/test-san.o"
g++ $san "$build_dir/adapter-san.o" "$build_dir/metrics-san.o" "$build_dir/double-san.o" "$build_dir/test-san.o" -o "$build_dir/test-san"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$build_dir/test-san"

if pkg-config --exists opencv4; then
  echo "REAL_SIGFM_DEPENDENCY=AVAILABLE"
else
  echo "REAL_SIGFM_DEPENDENCY=BLOCKED_OPENCV4_DEV_UNAVAILABLE"
fi
' d272-sigfm "$git_root" "$build_dir"
