#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -ne 5 ]; then
  echo "usage: $0 <source-root> <build-dir> <pkgconfig-dir> <output-dir> <mode>" >&2
  exit 2
fi

source_root=$1
build_dir=$2
pkgconfig_dir=$3
output_dir=$4
mode=$5
support_dir=$(CDPATH= cd -- "$(dirname -- "$0")/build-support" && pwd)
source_parent=$(CDPATH= cd -- "$source_root/../../.." && pwd -P)
relative_source_parent=$(realpath --relative-to="$build_dir" "$source_parent")
sanitize_args=
c_args="-DGOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE"

case "$mode" in
  normal) ;;
  sanitizer)
    c_args="$c_args -fno-omit-frame-pointer"
    sanitize_args=-Db_sanitize=address,undefined
    ;;
  *) echo "invalid build mode: $mode" >&2; exit 2 ;;
esac

export PKG_CONFIG_PATH=$pkgconfig_dir
opencv_include=$(pkg-config --variable=includedir opencv4)
opencv_libdir=$(pkg-config --variable=libdir opencv4)
relative_opencv=$(realpath --relative-to="$build_dir" "$(dirname "$(dirname "$opencv_include")")")
export LIBRARY_PATH="$pkgconfig_dir:$opencv_libdir"
export LDFLAGS=-Wl,--allow-shlib-undefined
c_args="$c_args -ffile-prefix-map=$source_parent=/usr/src/goodix-production"
c_args="$c_args -ffile-prefix-map=$relative_source_parent=/usr/src/goodix-production"
c_args="$c_args -ffile-prefix-map=$build_dir=/usr/src/goodix-build"
c_args="$c_args -ffile-prefix-map=$opencv_include=/usr/include/opencv4"
c_args="$c_args -ffile-prefix-map=$relative_opencv=/usr"
c_args="$c_args -ffile-prefix-map=$support_dir=/usr/src/goodix-build-support"

meson setup "$build_dir" "$source_root" \
  --prefix=/usr --libdir=lib64 --buildtype=release \
  -Ddrivers=goodix_27c6_5125 -Dintrospection=true -Ddoc=false \
  -Dinstalled-tests=false -Dudev_rules=disabled -Dudev_hwdb=disabled \
  -Dgoodix_production_minimal=true \
  -Dc_args="$c_args" -Dcpp_args="$c_args" $sanitize_args
meson compile -C "$build_dir" fprint-2
meson install -C "$build_dir" --destdir "$output_dir/install" \
  --no-rebuild --tags runtime

library=$(find "$output_dir/install" -type f -name libfprint-2.so.2.0.0 -print)
if [ -z "$library" ] || [ "$(printf '%s\n' "$library" | wc -l)" -ne 1 ]; then
  echo "production library is not unique" >&2
  exit 1
fi
cp "$library" "$output_dir/libfprint-2.so.2.0.0"
ln -s libfprint-2.so.2.0.0 "$output_dir/libfprint-2.so.2"
ln -s libfprint-2.so.2 "$output_dir/libfprint-2.so"

grep -F -- -DGOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE \
  "$build_dir/compile_commands.json" >/dev/null
legacy_policy=GOODIX_D
legacy_policy="${legacy_policy}282_DIRECT_ENROLL_PROFILE"
if grep -F "$legacy_policy" "$build_dir/compile_commands.json" >/dev/null; then
  echo "historical Dxxx policy leaked into canonical compile commands" >&2
  exit 1
fi

echo "PRODUCTION_BUILD_MODE=$mode"
echo PRODUCTION_NETWORK_SHARED=false
echo PRODUCTION_USB_ENUMERATION=false
echo PRODUCTION_MATERIAL_LOADER_EXECUTED=false
