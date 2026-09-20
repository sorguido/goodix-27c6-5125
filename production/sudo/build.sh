#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 1 && $EUID != 0 && $1 == /* && ! -e $1 ]] || {
  echo 'usage: build.sh ABSOLUTE_NEW_OUTPUT (unprivileged)' >&2; exit 2;
}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(CDPATH= cd -- "$here/../.." && pwd -P)
mkdir -m 0700 "$1"
output=$(realpath "$1")
rpm_dir=${GOODIX_HEADER_RPMS:-$root/GoodixArtifacts/login-header-rpms}
mkdir "$output/headers"
awk '$2 == "pam-devel-1.7.2-2.fc44.x86_64.rpm"' "$root/production/login/headers.sha256" >"$output/header.sha256"
(cd "$rpm_dir" && sha256sum -c "$output/header.sha256")
rpm2cpio "$rpm_dir/pam-devel-1.7.2-2.fc44.x86_64.rpm" >"$output/headers.cpio"
cpio -idm --quiet -D "$output/headers" <"$output/headers.cpio"
rm "$output/headers.cpio"
gcc -std=gnu11 -fPIC -shared -O2 -Wall -Wextra -Werror -Wl,--no-undefined \
  -fstack-protector-strong -D_FORTIFY_SOURCE=3 -Wl,-z,relro,-z,now \
  -ffile-prefix-map="$root"=/usr/src/goodix \
  -I"$output/headers/usr/include" "$here/pam_goodix_sudo.c" \
  /usr/lib64/libpam.so.0 -o "$output/pam_goodix_sudo.so"
nm -D --defined-only "$output/pam_goodix_sudo.so" >"$output/symbols"
[[ $(awk '{print $3}' "$output/symbols" | LC_ALL=C sort | tr '\n' ' ') == 'pam_sm_authenticate pam_sm_setcred ' ]]
readelf -d "$output/pam_goodix_sudo.so" >"$output/dynamic"
! grep -E 'RPATH|RUNPATH' "$output/dynamic"
! strings "$output/pam_goodix_sudo.so" | grep -F GOODIX_SUDO_TEST_
echo SUDO_PAM_BUILD=PASS
