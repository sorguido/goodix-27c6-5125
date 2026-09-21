#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 1 && $EUID != 0 ]] || exit 2
build=$(realpath "$1")
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
work=$(mktemp -d /tmp/goodix-vt-test.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
cp "$here/test_session_vt.cpp" "$work/test.cpp"
flatpak run --user --unshare=network --filesystem="$build:ro" --filesystem="$work" \
  --command=g++ org.freedesktop.Sdk//25.08 -std=c++20 -O0 -g -fPIC \
  -I"$build/source/src/daemon" -I"$build/deps/usr/include/qt6" \
  -I"$build/deps/usr/include/qt6/QtCore" -I"$build/deps/usr/include/qt6/QtDBus" \
  -c "$work/test.cpp" -o "$work/test.o"
gcc -Wl,--wrap=open,--wrap=close,--wrap=ioctl -o "$work/test" "$work/test.o" "$build/16.o" \
  /usr/lib64/libQt6Core.so.6 /usr/lib64/libQt6DBus.so.6 /usr/lib64/libstdc++.so.6
dbus-run-session -- sh -c 'export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"; exec python3 -B "$1" "$2"' sh "$here/test_bus.py" "$work/test"
