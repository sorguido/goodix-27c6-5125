#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

die() {
    printf 'D281_01_OFFLINE_INTEGRATION=FAIL reason=%s\n' "$1" >&2
    exit 1
}

repo_root=$(git rev-parse --show-toplevel)
[[ $(git -C "$repo_root" branch --show-current) == development ]] || die wrong_branch

for command_name in flatpak patch nm readelf dbus-run-session gdbus rpm; do
    command -v "$command_name" >/dev/null || die "missing_${command_name}"
done
for path in \
    /usr/libexec/fprintd \
    /usr/bin/fprintd-enroll \
    /usr/bin/fprintd-list \
    /usr/bin/fprintd-verify \
    /usr/bin/fprintd-delete \
    /usr/lib64/libgusb.so.2.0.10; do
    [[ -e "$path" ]] || die "missing_$(basename "$path")"
done
flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null || die missing_flatpak_sdk_25_08

probe_root=$(mktemp -d /tmp/goodix-d281-01.XXXXXX)
source_root="$probe_root/snapshot/reference/libfprint-fedora44-1.94.100/source"
build_root="$probe_root/build"
deps_root="$probe_root/deps"
mkdir -p "$(dirname "$source_root")" "$deps_root"
cp -a "$repo_root/reference/libfprint-fedora44-1.94.100/source" "$source_root"
ln -s "$repo_root/libfprint-driver" "$probe_root/snapshot/libfprint-driver"
ln -s "$repo_root/Rockytkg" "$probe_root/snapshot/Rockytkg"
patch -p1 -d "$source_root" < "$repo_root/analysis/D281/d281_01_disable_usb_context.patch"

cp /usr/lib64/libgusb.so.2.0.10 "$deps_root/libgusb.so.2"
sed -e "s|@PREFIX@|$deps_root|g" \
    -e "s|@INCLUDEDIR@|$repo_root/libfprint-driver/tests/support/d277|g" \
    "$repo_root/libfprint-driver/tests/support/d279/gusb.pc.in" > "$deps_root/gusb.pc"

flatpak run --user --unshare=network \
    --filesystem=/tmp \
    --filesystem="$repo_root:ro" \
    --command=sh org.freedesktop.Sdk//25.08 -lc \
    "export PKG_CONFIG_PATH='$deps_root'; \
     meson setup '$build_root' '$source_root' \
       -Ddrivers=virtual_image \
       -Dudev_rules=disabled \
       -Dudev_hwdb=disabled \
       -Dgtk-examples=false \
       -Ddoc=false \
       -Dinstalled-tests=false \
       -Dintrospection=true \
       -Dc_args=-DD281_01_DISABLE_USB_CONTEXT \
       --wrap-mode=nodownload; \
     ninja -C '$build_root' libfprint/libfprint-2.so.2.0.0" \
    >"$probe_root/build.log" 2>&1

lib_dir="$build_root/libfprint"
lib_path="$lib_dir/libfprint-2.so.2.0.0"
[[ -x "$lib_path" ]] || die custom_libfprint_not_built
grep -F -- '-DD281_01_DISABLE_USB_CONTEXT' "$build_root/compile_commands.json" >/dev/null || die compile_guard_missing
grep -F 'fpi_device_virtual_image_get_type' "$build_root/libfprint/fpi-drivers.c" >/dev/null || die virtual_driver_missing
if grep -F 'goodix_27c6_5125' "$build_root/libfprint/fpi-drivers.c" >/dev/null; then
    die goodix_driver_present
fi
if nm -D "$lib_path" | grep -Eq 'g_usb_context_(new|enumerate)'; then
    die usb_context_symbol_present
fi
[[ $(readelf -d "$lib_path" | awk '/SONAME/ {print $NF}') == '[libfprint-2.so.2]' ]] || die wrong_soname
LD_LIBRARY_PATH="$lib_dir:$deps_root" ldd /usr/libexec/fprintd \
    >"$probe_root/fprintd-ldd.out"
grep -F "$lib_dir/libfprint-2.so.2" "$probe_root/fprintd-ldd.out" >/dev/null || die fprintd_wrong_libfprint

export D281_01_PROBE_ROOT="$probe_root"
export D281_01_REPO_ROOT="$repo_root"
export D281_01_LIB_DIR="$lib_dir"
export D281_01_GUSB_DIR="$deps_root"
dbus-run-session -- "$repo_root/analysis/D281/d281_01_private_bus_flow.sh" \
    | tee "$probe_root/summary.env"

printf 'D281_01_OFFLINE_INTEGRATION=PASS\n'
printf 'D281_01_PROBE_DIRECTORY=%s\n' "$probe_root"
printf 'D281_01_BUILD_NETWORK_SHARED=false\n'
printf 'D281_01_GOODIX_DRIVER_PRESENT=false\n'
printf 'D281_01_USB_CONTEXT_SYMBOL_PRESENT=false\n'
printf 'D281_01_CUSTOM_LIBFPRINT_SHA256=%s\n' "$(sha256sum "$lib_path" | awk '{print $1}')"
