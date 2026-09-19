#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
driver=$1 here=$2 work=$3 mode=$4
build=$driver/login
root=$(CDPATH= cd -- "$here/../.." && pwd -P)
flags=
[ "$mode" != sanitizer ] || flags='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer'
# Compile actual staged daemon handlers; mock only device operations in the test.
cc $flags -Wall -Wextra -Wno-unused-parameter \
  -I"$build/fprintd/src" -I"$build/fprintd" -I"$build/stack" -I"$build/stack/src" \
  -I"$build/deps/prefix/usr/include/polkit-1" \
  -I"$root/reference/libfprint-fedora44-1.94.100/source/libfprint" \
  -I"$root/production/build-support" -I"$driver/build/libfprint" \
  $(pkg-config --cflags gio-unix-2.0) -c "$here/test_daemon.c" -o "$work/test-daemon-$mode.o"
cc $flags -Wall -Wextra -Werror $(pkg-config --cflags gio-unix-2.0) \
  "-DGOODIX_GREETER_EXEC=\"$here/test-greeter-child.sh\"" \
  -c "$here/greeter.c" -o "$work/test-greeter-$mode.o"
