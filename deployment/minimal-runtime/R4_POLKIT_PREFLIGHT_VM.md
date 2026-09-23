<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: inspect the VM's stock PolicyKit authentication configuration

**Current HUMAN_REQUIRED — resolve the candidate's action, reader detached.**
The supplemental query completed once at reported checkout `d5e890b`, resolving
locally to `d5e890ba479ed35134742a7466ed4c13d2747ca3`. All three legacy policy
locations returned POLICY_FILES=0 and pkla-compat RPM verification returned 0.
The user reports collection of the rule bodies; this handoff contains their
summary, not all bodies for direct review. The stock wheel administrator rule
is corroborated without observed PKLA overrides. Actual dialog identity and
fresh authentication remain untested.

The available action-catalog copy loses its beginning. This is **incomplete
returned evidence, not a failed query**, and does not establish the absence of
program annotations. Do not repeat either completed block below. Final fprintd
active/running/PID 8053 is compatible with reader-absent sudo activation;
no retrospective stop or polling is required. Runtime/template remain retained.

## Current targeted read-only query

In an ordinary-user Bash terminal in the existing Fedora 44 KDE VM checkout,
as `guido`, keep the reader detached and authentication dialogs closed. Run
only this block once. No sudo is needed. It resolves `/usr/bin/true` without
executing it and reads registered action metadata through EnumerateActions.
The catalog is held in memory only; output is restricted to the default action
and path annotations relevant to the requested/resolved program. It does not
request authorization, invoke pkexec/helpers, clear cache or change services,
policy, PAM, SELinux, runtime or templates.

```bash
(
  set -euo pipefail
  trap 'printf "R4_POLKIT_TRUE_ACTION_STOP line=%s exit=%s\n" "$LINENO" "$?" >&2' ERR
  export LC_ALL=C
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  test "$(id -un)" = guido
  systemd-detect-virt --vm --quiet
  test "$(getenforce)" = Enforcing
  test -x /usr/bin/true
  python3 -B - <<'PY_ACTION'
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
requested = '/usr/bin/true'
resolved = str(Path(requested).resolve(strict=True))
print('CANDIDATE_PROGRAM=' + requested, 'RESOLVED_PROGRAM=' + resolved, sep='\n', flush=True)
reply = json.loads(subprocess.check_output([
    'busctl', '--system', '--json=short', '--no-pager',
    '--allow-interactive-authorization=no', '--timeout=25s', 'call',
    'org.freedesktop.PolicyKit1', '/org/freedesktop/PolicyKit1/Authority',
    'org.freedesktop.PolicyKit1.Authority', 'EnumerateActions', 's', ''
], text=True))
if reply.get('type') != 'a(ssssssuuua{ss})' or len(reply.get('data', [])) != 1:
    raise RuntimeError('Unexpected EnumerateActions response shape')
rows = reply['data'][0]
default = 'org.freedesktop.policykit.exec'
prefix = default + '.'
defaults = ['no', 'auth_self', 'auth_admin', 'auth_self_keep', 'auth_admin_keep', 'yes']
if not any(row[0] == default for row in rows):
    raise RuntimeError('Default exec action missing; no selection inferred')
eligible = []
for row in rows:
    action, annotations = row[0], row[9]
    path = annotations.get(prefix + 'path')
    if action != default and path not in (requested, resolved):
        continue
    no_args_match = path == resolved and prefix + 'argv1' not in annotations
    if no_args_match:
        eligible.append(action)
    print(json.dumps({'action': action,
        'defaults_any_inactive_active': [defaults[n] for n in row[6:9]],
        'exec_annotations': {k: v for k, v in annotations.items() if k.startswith(prefix)},
        'matches_resolved_path_with_no_arguments': no_args_match}, sort_keys=True))
print('ACTION_FOR_NO_ARGUMENTS=' + (eligible[0] if len(eligible) == 1 else
      default if not eligible else 'AMBIGUOUS:' + ','.join(eligible)))
d.no_sensor()
print('R4_POLKIT_TRUE_ACTION_COMPLETE SENSOR_CONNECTED=false')
PY_ACTION
)
```

Return this **short output in full**, including checkout SHA and final marker.
An absent `exec.argv1` matches a no-argument invocation; an annotation present
with an empty value does not. Path comparison uses the resolved program path
literally, as in [pkexec 127](https://raw.githubusercontent.com/polkit-org/polkit/127/src/programs/pkexec.c).
Multiple eligible actions are reported as ambiguous for review, not permission
to run any of them. Defaults are metadata, not a live authorization decision.

**PASS_IF (collection only):** the block completes with the reader absent and
returns the candidate path, relevant records and action-selection result.
**STOP_IF:** an error, sensor connection, password/PolicyKit dialog or ambiguous
selection; return output without retry or authentication. No installation or
rollback is needed. Keep the saved inverse
`/usr/local/lib64/goodix-27c6-5125/uninstall.sh` and RIGHT-index template labeled
left-index-finger. PolicyKit live remains **NOT READY** pending review, with
password first while detached, then at most three contacts in the first PAM
series, stop at MATCH and detach before fallback/restart. Do not run that live now.

## Completed supplemental query and original criteria

**Historical human gate — do not execute the block below again.**
The following records the completed request and its original rationale.

**Initial query COMPLETED — configuration PASS, human-reported at
`b674dd8842cf336e6d74ec81070498879b856330`. PolicyKit authentication is untested.**
The guest confirms stock polkit-1 → system-auth, pam_fprintd sufficient followed
by pam_unix; valid authselect with fingerprint enabled, KDE agent active,
stock authority/helper and polkit/polkit-kde RPM verification exit 0. The final
fprintd active/running/PID 6749 followed a real reader-absent sudo password prompt;
it is compatible with stock activation, not a failed biometric cleanup.
Do not repeat that full query or stop the daemon just to change this snapshot.

**Previous HUMAN_REQUIRED — complete the policy evidence, reader detached.**
The handoff contains a summary, not the complete 18 rule bodies requested by
the initial query. Package ownership alone does not establish their decisions.
In particular, `49-polkit-pkla-compat.rules` delegates to PKLA configuration:
`/etc/polkit-1/localauthority.conf.d/*.conf` may override administrator identities
before `50-default.rules`, and `.pkla` files under `/etc/polkit-1/localauthority/`
and `/var/lib/polkit-1/localauthority/` may override authorization, including
`yes` or retained authentication. These inputs were outside the original query.
Thus membership in wheel is known, but the effective administrator choice and
absence of automatic/cached authorization are not established yet.

The proposed harmless program is `/usr/bin/true`, executed as root with the
stock KDE agent. It changes no application data; authentication/session logs
are normal side effects. It remains a **candidate, not a live instruction**:
[pkexec 127](https://raw.githubusercontent.com/polkit-org/polkit/127/src/programs/pkexec.c)
resolves the program path and consults registered `exec.path`/`exec.argv1`
annotations before falling back to `org.freedesktop.policykit.exec`. Reading
only that default action does not prove which action will be selected.

### Completed supplemental read-only query

In an ordinary-user Bash terminal in the existing Fedora 44 KDE VM checkout,
as `guido`, keep the reader detached and all authentication dialogs closed.
Run only this block, once. It reads policy inputs and registered action metadata;
it does not invoke pkexec, request a PolicyKit authentication, run PKLA helpers,
clear authorizations, or change policy/services. One sudo password may be needed
for the protected configuration. Its normal activation of reader-absent fprintd
and logs are allowed; the final state is reported without polling or stopping it.
Runtime build `b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, install
`264cd7ff1ba77857e1985502f299e4375f9a0516` and the RIGHT-index template stored as
left-index-finger remain retained.

```bash
(
  set -euo pipefail
  trap 'printf "R4_POLKIT_POLICY_STOP line=%s exit=%s\n" "$LINENO" "$?" >&2' ERR
  export LC_ALL=C
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  test "$(id -un)" = guido
  systemd-detect-virt --vm --quiet
  test "$(getenforce)" = Enforcing
  python3 -B - <<'PY_SENSOR'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
print('R4_POLKIT_POLICY_START SENSOR_CONNECTED=false')
PY_SENSOR
  printf '\nCANDIDATE_PROGRAM\n'
  test -x /usr/bin/true
  readlink -f /usr/bin/true
  rpm -qf /usr/bin/true
  printf '\nREGISTERED_ACTIONS_WITH_ANNOTATIONS\n'
  pkaction --verbose
  sudo -N -- /bin/bash -eu -c '
    export LC_ALL=C
    shopt -s nullglob
    rpm -q polkit-pkla-compat
    for r4_dir in /etc/polkit-1/rules.d /usr/share/polkit-1/rules.d \
                  /etc/polkit-1/localauthority.conf.d \
                  /etc/polkit-1/localauthority /var/lib/polkit-1/localauthority; do
      printf "\nPOLICY_DIRECTORY=%s\n" "$r4_dir"
      if [[ ! -e "$r4_dir" && ! -L "$r4_dir" ]]; then
        printf "ABSENT\n"
        continue
      fi
      test -d "$r4_dir"
      test -r "$r4_dir"
      test -x "$r4_dir"
      case "$r4_dir" in
        */rules.d) r4_files=("$r4_dir"/*.rules) ;;
        */localauthority.conf.d) r4_files=("$r4_dir"/*.conf) ;;
        */localauthority)
          for r4_subdir in "$r4_dir"/*/; do
            test -r "$r4_subdir"
            test -x "$r4_subdir"
          done
          r4_files=("$r4_dir"/*/*.pkla) ;;
      esac
      printf "POLICY_FILES=%s\n" "${#r4_files[@]}"
      for r4_file in "${r4_files[@]}"; do
        printf "\nPOLICY_FILE=%s\n" "$r4_file"
        readlink -f "$r4_file"
        rpm -qf "$r4_file" || :
        cat "$r4_file"
      done
    done
    printf "\nPKLA_COMPAT_RPM_VERIFY\n"
    r4_rpm_rc=0
    rpm -V --noscript polkit-pkla-compat || r4_rpm_rc=$?
    printf "PKLA_COMPAT_RPM_VERIFY_EXIT=%s\n" "$r4_rpm_rc"
  '
  python3 -B - <<'PY_SENSOR'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
print(d.run('systemctl', 'show', 'fprintd.service', '--all',
            '--property=ActiveState', '--property=SubState', '--property=MainPID'))
print('R4_POLKIT_POLICY_COMPLETE SENSOR_CONNECTED=false')
PY_SENSOR
)
```

Return **complete output**, not just package ownership, rule names or a summary.
The registered action list is intentionally complete so another action's path
annotation is not omitted. The rule reread supplies the bodies missing from the
handoff; this does not repeat the PAM, agent or helper preflight. Empty/absent
legacy directories and RPM differences are observations, not repair requests.
No protected fingerprint material, keys or template contents are requested.

**PASS_IF (evidence collection only):** the block completes with the reader absent
and returns the rule bodies, legacy policy inputs and registered actions for
review. **STOP_IF:** any prerequisite/read/query error, unexpected password
identity, sensor connection or PolicyKit dialog. Return the partial output and
exact error; do not retry, install, change rules or proceed to authentication.
Confirm runtime/template/PAM/authselect/SELinux remain unchanged, no biometric
attempt, no PolicyKit authentication and no rollback. Keep Enforcing; the known
nr_hugepages warning alone needs no additional diagnostics.

After review, the native password/fingerprint procedure must fix the selected
action and `guido` authentication identity, handle cache explicitly and allow
only the first PAM series: up to three contacts, stop at MATCH, detach before
password fallback or any conversation restart/identity change. Those details
are not yet a runnable live handoff. No private bridge or configuration patch
is proposed. This query has no installation or changes to roll back; preserve
the installed saved inverse `/usr/local/lib64/goodix-27c6-5125/uninstall.sh`.

## Completed initial query and original criteria

**Historical human gate — do not execute the block below again.**
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
