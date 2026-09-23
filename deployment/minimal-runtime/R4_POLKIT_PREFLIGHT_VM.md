<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: inspect the VM's stock PolicyKit authentication configuration

**HUMAN_REQUIRED — one configuration query in the VM, reader detached.**
Ordinary sudo is SUPPORTED on the tested baseline: password with reader absent,
then first-contact fingerprint MATCH without a password, exit 0 and closed/drained
cleanup. The [sudo procedure](R4_SUDO_VM.md) is completed; do not rerun it.
`sudo -i` shares the observed auth include, but its login shell/session is not
live-qualified. No additional sudo variant test is needed for this R4 biometric
boundary on current evidence. Keep runtime and the RIGHT-index template labeled
left-index-finger.

The next consumer is stock PolicyKit with the KDE authentication agent. Read
the guest's actual PAM route, agent/helper configuration, administrative identity
rules and candidate action defaults before choosing a native test. The physical
host's polkit-1 file and the historical private bridge are not guest evidence.
No configuration patch or PolicyKit authentication test is prepared here.

## One read-only block

Use an ordinary-user Bash terminal in the existing Fedora 44 KDE VM checkout
as `guido`. Keep the sensor disconnected and close authentication dialogs and
fingerprint settings. Runtime build
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226` and install
`264cd7ff1ba77857e1985502f299e4375f9a0516` are retained; the block separately
records the updated documentation checkout.

One sudo invocation reads administrator-owned rules and verifies the PolicyKit
packages. Its ordinary password may be needed; `-N` does not refresh cached
sudo credentials. This may activate fprintd without a reader, so both observed
service states are reported without polling/stopping it. Normal logs may be
written. `pkaction` lists one registered action's metadata; it does not request
authorization or execute a privileged program. It may activate the stock
PolicyKit authority through D-Bus. No agent/helper is started by a service command.

```bash
(
  set -euo pipefail
  trap 'printf "R4_POLKIT_QUERY_STOP line=%s exit=%s\n" "$LINENO" "$?" >&2' ERR
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
d.no_sensor()
print(d.run('systemctl', 'show', 'fprintd.service', '--all',
            '--property=ActiveState', '--property=SubState', '--property=MainPID'))
print('R4_POLKIT_QUERY_START SENSOR_CONNECTED=false')
PY
  printf 'DESKTOP=%s SESSION_TYPE=%s\n' "${XDG_CURRENT_DESKTOP:-unset}" "${XDG_SESSION_TYPE:-unset}"
  cat /etc/os-release
  id
  rpm -q polkit polkit-kde fprintd fprintd-pam pam authselect authselect-libs
  authselect current --raw
  authselect check
  for r4_name in polkit-1 system-auth password-auth fingerprint-auth postlogin; do
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
  printf '\nKDE_AGENT_STATE\n'
  systemctl --user show plasma-polkit-agent.service \
    -p LoadState -p ActiveState -p SubState -p MainPID \
    -p FragmentPath -p DropInPaths -p ExecStart
  systemctl --user cat plasma-polkit-agent.service
  printf '\nPOLKIT_AUTHORITY_AND_HELPER_UNITS\n'
  systemctl cat polkit.service polkit-agent-helper@.service polkit-agent-helper.socket
  printf '\nPOLKIT_EXEC_ACTION_METADATA\n'
  pkaction --action-id org.freedesktop.policykit.exec --verbose
  sudo -N -- /bin/bash -eu -c '
    export LC_ALL=C
    shopt -s nullglob
    for r4_rules_dir in /etc/polkit-1/rules.d /usr/share/polkit-1/rules.d; do
      printf "\nPOLKIT_RULES_DIRECTORY=%s\n" "$r4_rules_dir"
      test -d "$r4_rules_dir"
      r4_rule_files=("$r4_rules_dir"/*.rules)
      printf "RULE_FILES=%s\n" "${#r4_rule_files[@]}"
      for r4_rule in "${r4_rule_files[@]}"; do
        printf "\nPOLKIT_RULE=%s\n" "$r4_rule"
        readlink -f "$r4_rule"
        rpm -qf "$r4_rule" || :
        cat "$r4_rule"
      done
    done
    printf "\nPOLKIT_RPM_VERIFY\n"
    r4_rpm_rc=0
    rpm -V --noscript polkit polkit-kde || r4_rpm_rc=$?
    printf "POLKIT_RPM_VERIFY_EXIT=%s\n" "$r4_rpm_rc"
  '
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
print(d.run('systemctl', 'show', 'fprintd.service', '--all',
            '--property=ActiveState', '--property=SubState', '--property=MainPID'))
print('R4_POLKIT_QUERY_COMPLETE SENSOR_CONNECTED=false')
PY
)
```

Both PAM locations expose a possible local override. Rule files are read in
full because a global or group rule can affect the proposed action without
naming it; they are not executed by this block. A rule file without an RPM
owner or an RPM verification difference is evidence for review, not permission
to remove or repair it. Empty rule directories are reported as such. The agent
unit status alone does not prove registration or a working authentication dialog;
action defaults alone do not prove the decision for `guido` under local rules.

**PASS_IF (query only):** complete output identifies guest versions, profile,
PAM files, agent/helper setup and action/rules with the reader absent. It does
not qualify password or fingerprint PolicyKit authentication.
**STOP_IF:** failed prerequisite/read/query, wrong VM/user, attached sensor,
missing package/unit/tool or unexpected password identity. Return the partial
output and exact error without installing, retrying or changing anything.
RPM differences and active final fprintd are reported, not silently corrected.

Return the complete output and confirm no sensor connection, biometric attempt,
PolicyKit authentication dialog, runtime/template/PAM/authselect/SELinux change
or rollback. Do not run pkexec/pkcheck authentication tests, clear authorization
caches, start/stop agents, change rules, or reproduce the known nr_hugepages
denial. The next review will select the native workflow, identity, cache handling,
attempt limits and password fallback before a new live gate.

## Installation and rollback

This read-only query installs no patch and needs no new inverse. Keep the
[existing installation](install.sh) and the installed, saved
`/usr/local/lib64/goodix-27c6-5125/uninstall.sh`. A successful sudo test or this
query is not a reason to uninstall. No protected material/template contents
are read or changed; the existing runtime and its recovery remain intact.
