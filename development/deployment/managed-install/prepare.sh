#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

fail() { printf 'GOODIX_MANAGED_PREPARE=FAIL reason=%s\n' "$1" >&2; exit 1; }
[[ $# -eq 1 ]] || fail usage_prepare_absolute_empty_output
[[ $EUID -ne 0 ]] || fail build_must_be_unprivileged

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
output=$1
[[ $output == /* && $output != / && ! -L $output ]] || fail unsafe_output
if [[ -e $output ]]; then
  [[ -d $output && -O $output && -z $(find "$output" -mindepth 1 -maxdepth 1 -print -quit) ]] ||
    fail output_not_empty_or_not_owned
else
  mkdir -m 0700 -- "$output"
fi

[[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
head=$(git -C "$root" rev-parse HEAD)
[[ $head =~ ^[0-9a-f]{40}$ ]] || fail invalid_source_commit
for command in git sha256sum flatpak rpm2cpio cpio nm readelf python3 ldd rpm; do
  command -v "$command" >/dev/null || fail "missing_command_$command"
done

build=$output/build
candidate=$output/candidate
mkdir -m 0700 -- "$build" "$candidate"
"$root/production/build.sh" normal "$build"

install -m 0644 "$build/libfprint-2.so.2.0.0" "$candidate/libfprint-2.so.2.0.0"
install -m 0644 "$build/libgusb.so.2" "$candidate/libgusb.so.2"
for component in core features2d flann imgproc; do
  install -m 0644 "$build/libopencv_${component}.so.413" \
    "$candidate/libopencv_${component}.so.413"
done
for component in fprintd greeter; do
  install -m 0755 "$build/$component" "$candidate/$component"
done
"$root/production/sudo/build.sh" "$build/sudo"
install -m 0644 "$build/sudo/pam_goodix_sudo.so" "$candidate/pam_goodix_sudo.so"
install -m 0644 "$root/production/sudo/source.sha256" "$candidate/sudo-source.sha256"
"$root/production/polkit/build.sh" "$build/polkit"
install -m 0644 "$build/polkit/pam_goodix_polkit.so" "$candidate/pam_goodix_polkit.so"
install -m 0644 "$root/production/polkit/source.sha256" "$candidate/polkit-source.sha256"
install -m 0644 "$build/pam_fprintd.so" "$candidate/pam_fprintd.so"
python3 -B "$root/production/plasma-vt/build.py" "$build/plasma-vt"
install -m 0755 "$build/plasma-vt/plasmalogin" "$candidate/plasmalogin"
install -m 0755 "$root/production/plasma-vt/plasma-vt-preflight" "$candidate/plasma-vt-preflight"
install -m 0644 "$root/production/plasma-vt/source.sha256" "$candidate/plasma-vt-source.sha256"
install -m 0644 "$here/99-goodix-plasma-vt.conf" "$candidate/99-goodix-plasma-vt.conf"
install -m 0644 "$here/99-goodix-login-greeter.conf" "$candidate/99-goodix-login-greeter.conf"
install -m 0644 "$root/production/source-files.sha256" "$candidate/production-source.sha256"
install -m 0644 "$root/reference/fprintd-fedora44-1.94.5/SOURCE_SHA256SUMS" "$candidate/fprintd-source.sha256"
install -m 0644 "$root/production/login/source.sha256" "$candidate/login-source.sha256"
install -m 0644 "$root/reference/fprintd-fedora44-1.94.5/source/COPYING" "$candidate/fprintd-COPYING"
install -m 0644 "$root/reference/fprintd-fedora44-1.94.5/source/AUTHORS" "$candidate/fprintd-AUTHORS"
install -m 0755 "$here/fprintd-wrapper" "$candidate/fprintd-wrapper"
install -m 0755 "$here/50-goodix-fprint-account-delete" \
  "$candidate/50-goodix-fprint-account-delete"
install -m 0644 "$here/goodix_fprint_account_delete.te" \
  "$candidate/goodix_fprint_account_delete.te"
install -m 0644 "$here/goodix_fprint_account_delete.fc" \
  "$candidate/goodix_fprint_account_delete.fc"
install -m 0644 "$here/99-goodix-27c6-5125-managed.conf" \
  "$candidate/99-goodix-27c6-5125-managed.conf"
install -m 0644 "$here/plasmalogin-pam.rule" "$candidate/plasmalogin-pam.rule"
install -m 0644 "$here/kde-fingerprint-pam.rule" "$candidate/kde-fingerprint-pam.rule"
install -m 0644 "$root/LICENSE" "$candidate/LICENSE"
install -m 0644 "$root/LICENSES/GPL-2.0-or-later.txt" \
  "$candidate/GPL-2.0-or-later.txt"
install -m 0644 "$root/LICENSES/LGPL-2.1-or-later.txt" \
  "$candidate/LGPL-2.1-or-later.txt"
install -m 0644 "$root/LICENSES/GPL-3.0-or-later.txt" \
  "$candidate/GPL-3.0-or-later.txt"
install -m 0644 "$root/LICENSES/Apache-2.0.txt" \
  "$candidate/Apache-2.0.txt"
install -m 0644 "$build/OpenCV-LICENSES.txt" \
  "$candidate/OpenCV-LICENSES.txt"
install -m 0644 "$here/THIRD_PARTY_NOTICES.md" \
  "$candidate/THIRD_PARTY_NOTICES.md"

printf '%s\n' \
  'GOODIX_MANAGED_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL' \
  'RPM_OFFICIAL_DISTRIBUTION=false' \
  "SOURCE_COMMIT=$head" \
  'TARGET_OS=Fedora-44-KDE-x86_64' \
  'PROTECTED_MATERIAL_INCLUDED=false' \
  'PAM_FILES_INCLUDED=true' \
  'SUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1' \
  'POLKIT_INTEGRATION=INTERRUPTIBLE_SERVICE_LOCAL_V1' \
  'PAM_INTEGRATION=MANAGED_ETC_OVERRIDE_FROM_VENDOR' \
  'KSCREENLOCKER_PAM_INTEGRATION=MANAGED_PACKAGE_CONFIG_TRANSFORM' \
  'EARLY_LOGIN_INTEGRATION=PAIRED_FPRINTD_PAM_GREETER_V1' \
  'PLASMA_VT_INTEGRATION=QUALIFIED_SESSION_VT_V1' \
  'SBOM_FORMAT=SPDX-2.3-JSON' \
  'COMBINED_BINARY_LICENSE=GPL-3.0-or-later' \
  'FAR_FRR_CLAIM=NOT_MADE' \
  >"$candidate/MANIFEST"
python3 "$here/generate-sbom.py" --candidate "$candidate" --repo "$root" \
  --commit "$head" --output "$candidate/SBOM.spdx.json"
(cd "$candidate" && find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%P\n' | \
  LC_ALL=C sort | xargs -r sha256sum >SHA256SUMS)
(cd "$candidate" && sha256sum -c SHA256SUMS >/dev/null) || fail candidate_digest_failure

printf '%s\n' \
  'GOODIX_MANAGED_PREPARE=PASS' \
  "SOURCE_COMMIT=$head" \
  "CANDIDATE_DIRECTORY=$candidate" \
  "RELEASE_CANDIDATE_SHA256=$(sha256sum "$candidate/SHA256SUMS" | awk '{print $1}')" \
  'SBOM=SBOM.spdx.json' \
  'PROTECTED_MATERIAL_INCLUDED=false' \
  'REAL_USB_ENUMERATION_ATTEMPTED=false' \
  'LIVE_EXECUTION_PERFORMED=false'
