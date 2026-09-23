<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: inspect the VM's stock KScreenLocker configuration

**COMPLETED — query/preflight PASS, human-reported at
`90a3c46beeead6b50e13426870e3d30f496c67f9`. Do not repeat this query.**
The canonical manual records the guest evidence and its limits: valid authselect
with fingerprint already enabled, separate stock password/fingerprint substacks,
and two RPM digest checks not performed. No authentication was tested.
The current human gate is [native stock KScreenLocker unlock](R4_KSCREENLOCKER_VM.md),
with the retained RIGHT-index template still labeled left-index-finger by the
user's decision for R4. No configuration patch is needed.

## Completed query and original criteria

**HUMAN_REQUIRED — original read-only query in the VM, with the sensor detached.**
R3 is closed at the biometric boundary: stock enrollment and stock verification
passed, the latter at the first attempt with clean release/drain/close. Keep the
qualified runtime and template. Do not repeat either biometric test.

The first R4 target is stock KScreenLocker. Before choosing its native test and
any reversible stock configuration step, we need the VM's effective PAM files,
authselect profile/features and package versions. These are not established by
the R3 result. The physical workstation's configuration and historical managed
KDE tests are not evidence of the guest's current configuration.

Source review shows why this matters: Fedora's `kde` password path and
`kde-fingerprint` path use different substacks. In the inspected stock authselect
local profile, `with-fingerprint` changes both `fingerprint-auth` and
`system-auth`. It is not a KScreenLocker-only switch. No PAM overlay, private
consumer, replacement module, authselect change or new package is prepared here.

The laboratory template belongs to `guido`, is labeled `left-index-finger`,
and contains the **RIGHT index** according to the user. Its successful MATCH
does not repair the label. Preserve this known mismatch during this query;
review its handling before ordinary consumer use. No template contents are read.

## One read-only block

Use an ordinary-user terminal in the existing Fedora 44 KDE VM clone as `guido`.
Keep the sensor disconnected and close fingerprint settings/other biometric
clients. Do not lock/log out, invoke authentication tests, or start/stop fprintd.
No sudo is required. If any file/query is inaccessible, return that error;
do not escalate or repair the configuration in this step.

```bash
(
  set -euo pipefail
  export LC_ALL=C
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  test "$(id -un)" = guido
  systemd-detect-virt --vm --quiet
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.require_stopped()  # Reader absent and fprintd inactive/MainPID 0; read-only
print('R4_QUERY_START SENSOR_CONNECTED=false')
PY
  printf 'DESKTOP=%s SESSION_TYPE=%s\n' "${XDG_CURRENT_DESKTOP:-unset}" "${XDG_SESSION_TYPE:-unset}"
  cat /etc/os-release
  uname -m
  getenforce
  rpm -q kscreenlocker plasma-workspace fprintd fprintd-pam libfprint pam authselect authselect-libs || :
  authselect current --raw || :
  authselect check || :
  rpm -V --noscript kscreenlocker plasma-workspace fprintd fprintd-pam pam authselect authselect-libs || :
  for r4_name in kde kde-fingerprint fingerprint-auth password-auth system-auth postlogin; do
    for r4_base in /etc/pam.d /usr/lib/pam.d; do
      r4_path="$r4_base/$r4_name"
      if [[ -e "$r4_path" || -L "$r4_path" ]]; then
        printf '\nPAM_PATH=%s\n' "$r4_path"
        readlink -f "$r4_path"
        rpm -qf "$r4_path" || :
        cat "$r4_path"
      fi
    done
  done
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.require_stopped()
print('R4_QUERY_COMPLETE SENSOR_CONNECTED=false FPRINTD_INACTIVE=true')
PY
)
```

Missing packages, RPM differences, unowned generated files and invalid authselect
state are reported as evidence; the `|| :` clauses permit the remaining read-only
queries to print. They do not declare success or approve configuration changes.
An absent path is not created. Both PAM locations are shown to expose any local
file shadowing the vendor path. Do not copy files between them.

**PASS_IF (query only):** output identifies the VM/session, packages, current
profile/features and the relevant PAM files, with the reader absent and fprintd
inactive at both ends. This does not qualify password or fingerprint unlock.
**STOP_IF:** wrong environment/user, connected sensor, active daemon, command or
read failure. Return partial output and the exact error; do not retry live or
make a configuration correction. A missing package/configuration is a review
input, not a driver failure.

Return this block's output and confirm no sensor connection, authentication test,
template change, runtime change or rollback occurred. The next review will choose
the smallest stock-only consumer test and, if configuration is needed, prepare
its exact install/rollback delta before a new human gate.

## Installation and rollback

No runtime/configuration patch is installed, so this query needs no uninstall
or configuration rollback. Keep the R3 baseline. Its existing
[installation](install.sh) and saved
`/usr/local/lib64/goodix-27c6-5125/uninstall.sh` remain recoverable; do not run
the inverse merely to collect this output. No protected material, template,
vendor file, service configuration or authselect setting is changed.
