#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Inside the network-isolated SDK. Compile only; link to Fedora libraries outside.
set -eu
out=$1
here=$2
mode=$3
driver=$4
export PKG_CONFIG_PATH="$out/deps/pc"
export CFLAGS="-I$out/deps/prefix/usr/include -ffile-prefix-map=$out=/usr/src/goodix-login -ffile-prefix-map=$driver=/usr/src/goodix-build"
export LIBRARY_PATH="$out/deps/lib"
export LDFLAGS="-L$out/deps/lib -Wl,--allow-shlib-undefined"
san=
[ "$mode" != sanitizer ] || san=-Db_sanitize=address,undefined
meson setup "$out/stack" "$out/fprintd" --prefix=/usr --libdir=lib64 \
  --localstatedir=/var --buildtype=release -Dman=false -Dgtk_doc=false -Dsystemd=false $san
ninja -C "$out/stack" src/libfprintd-private.a \
  src/fprintd.p/meson-generated_.._fprintd-enums.c.o \
  src/fprintd.p/meson-generated_.._fprintd-dbus.c.o \
  src/fprintd.p/file_storage.c.o src/fprintd.p/main.c.o \
  pam/pam_fprintd.so.p/pam_fprintd.c.o
flags=
[ "$mode" != sanitizer ] || flags='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer'
# shellcheck disable=SC2086
cc $flags -Wall -Wextra -Werror $(pkg-config --cflags gio-unix-2.0) \
  -ffile-prefix-map="$here"=/usr/src/goodix-login -c "$here/greeter.c" -o "$out/stack/greeter.o"
if [ "$mode" = sanitizer ]; then
  cp -L "$(cc -print-file-name=libasan.so)" "$out/deps/lib/libasan.so.8"
  cp -L "$(cc -print-file-name=libubsan.so)" "$out/deps/lib/libubsan.so.1"
fi
