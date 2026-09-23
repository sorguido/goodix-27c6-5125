#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Human VM build only. No installation, real authentication, D-Bus or device I/O.
set -euo pipefail
trap 'printf "PLASMA_LOGIN_BUILD_STOP line=%s\n" "$LINENO" >&2' ERR
test "$EUID" -ne 0
systemd-detect-virt --vm --quiet
. /etc/os-release
test "$ID" = fedora
test "$VERSION_ID" = 44
test "$(uname -m)" = x86_64
test "$(getenforce)" = Enforcing
test -d /sys/bus/usb/devices
for entry in /sys/bus/usb/devices/*; do
    [[ -e $entry/idVendor ]] || continue
    test -r "$entry/idVendor"
    device_vendor=$(cat -- "$entry/idVendor")
    [[ $device_vendor =~ ^[[:xdigit:]]{4}$ ]]
    [[ ${device_vendor,,} == 27c6 ]] || continue
    test -r "$entry/idProduct"
    device_product=$(cat -- "$entry/idProduct")
    [[ $device_product =~ ^[[:xdigit:]]{4}$ ]]
    if [[ ${device_product,,} == 5125 ]]; then
        printf '%s\n' 'STOP: detach Goodix from the VM before building' >&2
        exit 1
    fi
done
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_root=$(git -C "$source_dir" rev-parse --show-toplevel)
test "$(git -C "$repo_root" branch --show-current)" = development
test -z "$(git -C "$repo_root" status --porcelain)"
source_commit=$(git -C "$repo_root" rev-parse HEAD)
rpm -q gcc pam pam-devel
command -v cc
command -v python3
build_out=$(mktemp -d "${TMPDIR:-/tmp}/goodix-login-build.XXXXXXXX")
printf 'BUILD_OUTPUT=%s\nSOURCE_COMMIT=%s\n' "$build_out" "$source_commit"
cd "$source_dir"
cc_flags=(-std=c11 -Wall -Wextra -Werror -O2)
cc "${cc_flags[@]}" -fPIC -shared pam_goodix_login_gate.c -lpam \
    -Wl,-z,relro,-z,now -Wl,--no-undefined -o "$build_out/pam_goodix_login_gate.so"
cc "${cc_flags[@]}" test_gate.c -o "$build_out/test_gate"
"$build_out/test_gate"
cc "${cc_flags[@]}" -fPIC -shared -DBUILD_MODULE test_dispatch.c -lpam \
    -o "$build_out/mock.so"
cc "${cc_flags[@]}" test_dispatch.c -lpam -o "$build_out/dispatch-test"
fixtures="$build_out/gate-fixtures"
cc "${cc_flags[@]}" -fPIC -shared -DGOODIX_GATE_TEST \
    "-DGOODIX_GATE_VENDOR_PATH=\"$fixtures/plasmalogin\"" \
    "-DGOODIX_GATE_PASSWORD_PATH=\"$fixtures/password-auth\"" \
    "-DGOODIX_GATE_POSTLOGIN_PATH=\"$fixtures/postlogin\"" \
    pam_goodix_login_gate.c -lpam -o "$build_out/gate-test.so"
python3 -I -B test_dispatch.py "$build_out/dispatch-test" \
    "$build_out/mock.so" plasmalogin.pam "$build_out/gate-test.so" "$fixtures"
python3 -I -B test_manage.py
test -z "$(git -C "$repo_root" status --porcelain)"
test "$(git -C "$repo_root" rev-parse HEAD)" = "$source_commit"
cp -- plasmalogin.pam manage.py "$build_out/"
printf '%s\n' "$source_commit" > "$build_out/SOURCE_COMMIT"
(
    cd "$build_out"
    sha256sum pam_goodix_login_gate.so plasmalogin.pam manage.py SOURCE_COMMIT > SHA256SUMS
)
printf 'PASS\n' > "$build_out/VM_TESTS_PASS"
printf 'PLASMA_LOGIN_VM_BUILD_TESTS=PASS\nBUILD_OUTPUT=%s\nINSTALLATION=NOT_PERFORMED\n' "$build_out"
