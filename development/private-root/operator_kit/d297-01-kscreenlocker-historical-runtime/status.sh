#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

target=/etc/pam.d/kde-fingerprint
vendor=8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437
managed=858713e5b3b7ecf58a91f6fe5b736f344aa6c5b9c207318e6ac552a1a3ffb3d1
digest() { sha256sum "$1" | awk '{print $1}'; }
fail() { printf 'D297_01_KSCREENLOCKER_STATUS=FAIL reason=%s\n' "$1" >&2; exit 1; }
[[ $# -eq 0 ]] || fail usage_status
[[ -f $target && ! -L $target ]] || fail kde_fingerprint_missing
if [[ -f /var/lib/goodix-27c6-5125-managed/state || -L /usr/lib64/goodix-27c6-5125/current ]]; then
  deployment=MANAGED_CANDIDATE
elif [[ -f /etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf && \
        -f /usr/local/sbin/goodix-d293-native-fprintd ]]; then
  deployment=HISTORICAL_D293_RUNTIME
else
  deployment=UNKNOWN
fi
case $(digest "$target") in
  "$vendor") pam_status=VENDOR_UNPATCHED ;;
  "$managed") pam_status=TRANSIENT_CORRECTIVE_ACTIVE ;;
  *) fail kde_fingerprint_content_unknown ;;
esac
printf '%s\n' 'D297_01_KSCREENLOCKER_STATUS=PASS' \
  "ACTIVE_HOST_DEPLOYMENT_MODE=$deployment" \
  "KSCREENLOCKER_PAM_STATUS=$pam_status" \
  "KDE_FINGERPRINT_SHA256=$(digest "$target")" \
  "FINGERPRINT_AUTH_SHA256=$(digest /etc/pam.d/fingerprint-auth)"
