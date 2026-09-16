#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

die() { printf 'D293_03_INTEGRATION=FAIL reason=%s\n' "$1" >&2; exit 1; }
root=$(git rev-parse --show-toplevel)
[[ $(git -C "$root" branch --show-current) == development ]] || die wrong_branch
for command_name in flatpak patch nm readelf dbus-run-session gdbus rpm; do
  command -v "$command_name" >/dev/null || die "missing_${command_name}"
done
[[ $(rpm -q fprintd) == fprintd-1.94.5-5.fc44.x86_64 ]] || die wrong_fprintd_package
[[ $(rpm -q libfprint) == libfprint-1.94.100-1.fc44.x86_64 ]] || die wrong_libfprint_package

probe=$(mktemp -d /tmp/goodix-d293-03.XXXXXX)
source_root="$probe/snapshot/reference/libfprint-fedora44-1.94.100/source"
build_root="$probe/build"
deps="$probe/deps"
mkdir -p "$(dirname "$source_root")" "$deps"
cp -a "$root/reference/libfprint-fedora44-1.94.100/source" "$source_root"
ln -s "$root/libfprint-driver" "$probe/snapshot/libfprint-driver"
ln -s "$root/Rockytkg" "$probe/snapshot/Rockytkg"
patch -p1 -d "$source_root" <"$root/analysis/D281/d281_01_disable_usb_context.patch"
cp /usr/lib64/libgusb.so.2.0.10 "$deps/libgusb.so.2"
sed -e "s|@PREFIX@|$deps|g" \
    -e "s|@INCLUDEDIR@|$root/libfprint-driver/tests/support/d277|g" \
    "$root/libfprint-driver/tests/support/d279/gusb.pc.in" >"$deps/gusb.pc"

flatpak run --user --unshare=network --filesystem=/tmp \
  --filesystem="$root:ro" --command=sh org.freedesktop.Sdk//25.08 -lc \
  "export PKG_CONFIG_PATH='$deps'; meson setup '$build_root' '$source_root' \
     -Ddrivers=virtual_image -Dudev_rules=disabled -Dudev_hwdb=disabled \
     -Dgtk-examples=false -Ddoc=false -Dinstalled-tests=false \
     -Dintrospection=true -Dc_args=-DD281_01_DISABLE_USB_CONTEXT \
     --wrap-mode=nodownload; ninja -C '$build_root' \
     libfprint/libfprint-2.so.2.0.0" >"$probe/build.log" 2>&1

lib_dir="$build_root/libfprint"
library="$lib_dir/libfprint-2.so.2.0.0"
[[ -x "$library" ]] || die library_missing
grep -F 'fpi_device_virtual_image_get_type' "$build_root/libfprint/fpi-drivers.c" >/dev/null || die virtual_driver_missing
! grep -F 'goodix_27c6_5125' "$build_root/libfprint/fpi-drivers.c" >/dev/null || die goodix_driver_present
! nm -D "$library" | grep -Eq 'g_usb_context_(new|enumerate)' || die usb_context_symbol_present
[[ $(readelf -d "$library" | awk '/SONAME/ {print $NF}') == '[libfprint-2.so.2]' ]] || die wrong_soname

export D293_03_PROBE_ROOT="$probe"
export D293_03_REPO_ROOT="$root"
export D293_03_LIB_DIR="$lib_dir"
export D293_03_GUSB_DIR="$deps"
dbus-run-session -- "$root/analysis/D293/d293_03_private_bus_flow.sh" |
  tee "$probe/summary.env"

printf 'D293_03_INTEGRATION=PASS\n'
printf 'D293_03_PROBE_DIRECTORY=%s\n' "$probe"
printf 'D293_03_BUILD_NETWORK_SHARED=false\n'
printf 'D293_03_GOODIX_DRIVER_PRESENT=false\n'
printf 'D293_03_USB_CONTEXT_SYMBOL_PRESENT=false\n'
printf 'D293_03_LIBRARY_SHA256=%s\n' "$(sha256sum "$library" | awk '{print $1}')"
