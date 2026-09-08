#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

export CCACHE_DISABLE=1

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
git_root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_dir=$(mktemp -d /tmp/goodix-sigfm-preprocess.XXXXXX)
expected=2ff834cdef0316b3280d86a46fa75881c50bff3f4240e03dc31c24f6fc4153b3

cleanup ()
{
  find "$build_dir" -maxdepth 1 -type f -delete
  rmdir "$build_dir"
}
trap cleanup EXIT HUP INT TERM

cflags="-std=c11 -O2 -g -Wall -Wextra -Werror -Wconversion -Wshadow"
includes="-I$git_root/libfprint-driver -I$git_root/libfprint-driver/rockytkg-imgproc"

cc $cflags $includes -c \
  "$git_root/libfprint-driver/rockytkg-imgproc/goodix_imgproc.c" \
  -o "$build_dir/imgproc.o"
cc $cflags $includes -c \
  "$git_root/libfprint-driver/goodix_sigfm_preprocess.c" \
  -o "$build_dir/preprocess.o"
cc $cflags $includes -c \
  "$git_root/libfprint-driver/tests/test_goodix_sigfm_preprocess.c" \
  -o "$build_dir/test.o"

if nm -u "$build_dir/imgproc.o" "$build_dir/preprocess.o" |
   awk '{print $NF}' |
   grep -E '^(getenv|fopen|open|read|write|socket|libusb_.*|g_usb_.*|SSL_.*|gnutls_.*|gx_(state|transport|usb|send|tls|psk|mcu|fw|device|capture).*)$'; then
  echo "GOODIX_SIGFM_PREPROCESS_FORBIDDEN_SYMBOL_AUDIT=FAIL" >&2
  exit 1
fi
echo "GOODIX_SIGFM_PREPROCESS_FORBIDDEN_SYMBOL_AUDIT=PASS"

cc "$build_dir/imgproc.o" "$build_dir/preprocess.o" "$build_dir/test.o" \
  -lm -o "$build_dir/test"
"$build_dir/test" >"$build_dir/output.bin"
actual=$(sha256sum "$build_dir/output.bin" | awk '{print $1}')
test "$actual" = "$expected"
echo "GOODIX_SIGFM_PREPROCESS_R2_ROCKY_KAT=PASS"

asan_runtime=$(cc -print-file-name=libasan.so.8)
if [ "$asan_runtime" != libasan.so.8 ] && [ -e "$asan_runtime" ]; then
  san="-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined"
  cc $cflags $san $includes \
    "$git_root/libfprint-driver/rockytkg-imgproc/goodix_imgproc.c" \
    "$git_root/libfprint-driver/goodix_sigfm_preprocess.c" \
    "$git_root/libfprint-driver/tests/test_goodix_sigfm_preprocess.c" \
    -lm -o "$build_dir/test-san"
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
    "$build_dir/test-san" >"$build_dir/output-san.bin"
  actual=$(sha256sum "$build_dir/output-san.bin" | awk '{print $1}')
  test "$actual" = "$expected"
  echo "GOODIX_SIGFM_PREPROCESS_ASAN_UBSAN=PASS"
else
  echo "GOODIX_SIGFM_PREPROCESS_ASAN_UBSAN=BLOCKED_ENVIRONMENT_LIBASAN_ABSENT"
fi
echo "GOODIX_SIGFM_PREPROCESS_EXECUTABLE_CLOSURE=PASS_HOST_ONLY"
