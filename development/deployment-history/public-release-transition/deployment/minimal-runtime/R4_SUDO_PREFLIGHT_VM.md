<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: inspect the VM's stock sudo configuration

**COMPLETED — configuration/policy query PASS, human-reported at
`168469b79565cf401f2cb256448c184f3a803d8c`, sensor detached. Do not rerun.**
The guest confirms stock sudo → system-auth, pam_fprintd sufficient followed by
pam_unix; valid authselect with fingerprint enabled, no custom PAM selector or
NOPASSWD observed, sudo RPM verification exit 0. The password query completed.
The immediate final fprintd active/running/PID 3802 is compatible with stock
D-Bus activation and its idle timer; it is not a failed biometric cleanup.
The recurring nr_hugepages denial now has a supplied raw AVC with that PID,
non-fatal for the completed query; keep Enforcing. The subsequent
[ordinary stock sudo test](R4_SUDO_VM.md) passed: password with reader absent,
first-contact MATCH without a password, exit 0 and closed/drained cleanup;
sudo is SUPPORTED on the tested baseline. Its final inactive/MainPID 0 supersedes
this preflight's immediate snapshot. The current human gate is the
[read-only VM login configuration query](R4_LOGIN_PREFLIGHT_VM.md), reader detached and desktop open.

## Completed query and original criteria

**Historical human gate — do not execute the block below again.**
KScreenLocker is **SUPPORTED on the tested baseline**: password unlock and
first-contact fingerprint unlock passed. The three reported SELinux denials
of a `nr_hugepages` read were non-fatal for that test; keep Enforcing and the
runtime/template. The [completed KScreenLocker procedure](R4_KSCREENLOCKER_VM.md)
and its audit query must not be repeated.

The next consumer is ordinary stock sudo for `guido`, without `-i`. Before a
live test, identify its PAM route and authentication policy in the guest.
`system-auth` containing pam_fprintd does not establish that sudo uses it;
`pam_service`, authentication-user overrides, NOPASSWD and command-specific
Defaults can change the result. This query lists policy for `/usr/bin/true`
without executing that command. It does not qualify sudo authentication.

## One query block

Use an ordinary-user Bash terminal inside the existing VM checkout. Keep the
sensor detached and close other authentication clients. No package/configuration
change is needed. The retained runtime was built at
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226` and installed at
`264cd7ff1ba77857e1985502f299e4375f9a0516`; the block records the documentation
checkout separately. Keep the RIGHT-index template labeled left-index-finger.

One outer sudo invocation reads administrator-owned configuration and lists
policy. Its ordinary password prompt may appear; `-N` avoids refreshing cached
credentials. The inner sudo is a noninteractive policy listing for `guido`, not
a command execution. Normal authentication/audit logging may occur. Password
authentication with the reader absent may activate fprintd; the final state is
reported without polling or a service action. Do not reconnect the sensor.

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
  test "$(getenforce)" = Enforcing
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.require_stopped()
print('R4_SUDO_QUERY_START SENSOR_CONNECTED=false')
PY
  cat /etc/os-release
  rpm -q sudo fprintd fprintd-pam pam authselect authselect-libs
  authselect current --raw
  authselect check
  for r4_name in sudo sudo-i system-auth password-auth fingerprint-auth postlogin; do
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
  printf '\nNSS_CONFIGURATION\n'
  cat /etc/nsswitch.conf
  sudo -N -- /bin/sh -eu -c '
    export LC_ALL=C
    printf "\nSUDO_CONFIGURATION\n"
    if [ -e /etc/sudo.conf ] || [ -L /etc/sudo.conf ]; then
      cat /etc/sudo.conf
    else
      printf "SUDO_CONF_ABSENT\n"
    fi
    printf "\nSUDO_DEFAULTS_WITH_INCLUDES\n"
    cvtsudoers -c /dev/null -f sudoers -e -s privileges /etc/sudoers
    printf "\nSUDO_POLICY_FOR_GUIDO_TRUE\n"
    sudo -n -ll -U guido -u root -- /usr/bin/true
    printf "\nSUDO_RPM_VERIFY\n"
    r4_rpm_rc=0
    rpm -V --noscript sudo || r4_rpm_rc=$?
    printf "SUDO_RPM_VERIFY_EXIT=%s\n" "$r4_rpm_rc"
  '
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
print(d.run('systemctl', 'show', 'fprintd.service', '--all',
            '--property=ActiveState', '--property=SubState', '--property=MainPID'))
print('R4_SUDO_QUERY_COMPLETE SENSOR_CONNECTED=false')
PY
)
```

The native `cvtsudoers` parser follows local includes and expands aliases; only
Defaults are printed. It does not install a converted policy. The listing shows
the rule for the proposed harmless command. `sudo.conf` and NSS evidence must
confirm that the local sudoers input actually describes the active policy;
custom plugins, alternate paths, remote policy or extra PAM includes require
review. The configuration of the physical workstation is not guest evidence.

**PASS_IF (query only):** complete output identifies stock policy, PAM files,
profile/features and versions; the sensor remains absent. This is evidence
for review, not automatic authorization or a claim that sudo supports fingerprint.
**STOP_IF:** failed prerequisite/read/query, unexpected password user, missing
tool, dirty/wrong checkout, wrong environment or connected sensor. Return the
partial output and exact error; do not retry, repair or install anything.
RPM differences are printed for review, not accepted or repaired automatically.
An active final fprintd with the reader still absent is reported as observed;
do not stop it in this query or interpret the completion marker as inactive.

Return the whole output and confirm no biometric attempt, sensor connection,
runtime/template/SELinux/authentication-configuration change or rollback.
The review is now complete; the native test and its limits are in the current
guide linked above. No sudo live was performed by this query.

## Installation and rollback

No runtime/configuration patch is installed, so this query has no new inverse.
Retain the existing [installation](install.sh) and the installed, saved
`/usr/local/lib64/goodix-27c6-5125/uninstall.sh`. Do not run that inverse for a
successful read-only query or for the accepted KScreenLocker result. The query
does not change policy, PAM, service configuration, runtime, sensor state or
template contents.
