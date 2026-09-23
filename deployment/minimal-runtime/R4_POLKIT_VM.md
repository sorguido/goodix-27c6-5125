<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: stock PolicyKit authentication through the KDE agent

**HUMAN_REQUIRED — human-only VM preparation, authentication and USB.**
All three [configuration queries](R4_POLKIT_PREFLIGHT_VM.md) are completed;
do not repeat them. At `0d8ccb7482fb10d7520f8830f59fb2e979c04380`, the guest
resolved `/usr/bin/true` to itself, with no competing path annotation:
the selected action is `org.freedesktop.policykit.exec`, whose three defaults
are auth_admin. No PKLA override or rule granting this action was reported.
The complete rule bodies are not reproduced in the handoff, so this is not an
independent exhaustive JavaScript audit. A visible fresh authentication in A,
then a fresh dialog and MATCH in B, are mandatory: exit 0 alone is not PASS.

Qualify only this native PolicyKit path for `guido`, using `/usr/bin/true`
without arguments. The command runs as root and changes no application data;
authentication/session logs are expected. **The authenticating identity must
be guido, distinct from the command's target user root.** No Discover/package
operation, login, update test or repeat of R3/KScreenLocker/sudo is included.

## Retained installation and preparation

Use the existing Fedora 44 KDE Wayland VM as `guido`, in an ordinary Bash
desktop terminal. Keep it open throughout. Reader detached, other authentication
dialogs and fingerprint settings closed, known working password available.
Do not proceed after a package/configuration change since the accepted queries;
report drift instead of changing the guest to match this procedure.

Accepted packages: polkit 127-2.fc44.2, polkit-kde 6.7.5-1.fc44,
fprintd/fprintd-pam 1.94.5-5.fc44, PAM 1.7.2-2.fc44,
authselect/authselect-libs 1.7.1-1.fc44, x86_64. Accepted profile:
local with-silent-lastlog with-mdns4 with-fingerprint. These identify the test,
not runtime version pins. PolicyKit, KDE agent, helper and PAM remain Fedora stock.

No new installation or configuration patch is needed. Retain runtime build
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, install
`264cd7ff1ba77857e1985502f299e4375f9a0516`, reconciled receipt, Enforcing and
the physical **RIGHT index** stored as `guido` / `left-index-finger`.
The existing [install.sh](install.sh) and the **installed saved inverse**
`/usr/local/lib64/goodix-27c6-5125/uninstall.sh` remain the installation/rollback
pair. Do not reinstall or replace that inverse with the current checkout.

Run this once inside the VM clone. An error means STOP before authentication.

```bash
(
  set -euo pipefail
  trap 'printf "R4_POLKIT_PREPARATION_STOP line=%s exit=%s\n" "$LINENO" "$?" >&2' ERR
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
PY
  pkcheck --revoke-temp
  r4_polkit_cached=$(pkcheck --list-temp)
  test -z "$r4_polkit_cached"
  printf 'R4_POLKIT_PREPARATION=PASS SENSOR_CONNECTED=false TEMP_AUTHORIZATIONS=0\n'
)
```

`pkcheck --revoke-temp` revokes **all temporary PolicyKit authorizations in
this desktop session**, without changing policy or passwords. Other privileged
applications may ask again. The following list must succeed and be empty.
This is distinct from sudo's timestamp. Revocation is repeated before B so A
cannot supply retained authorization, even if a rule changes the default.
No auth request or application other than this test should run between stages.

## A. Real PolicyKit password, reader absent

Keep the reader detached. Run once in the same terminal:

```bash
(
  r4_polkit_a_rc=0
  pkexec --disable-internal-agent --user root /usr/bin/true || r4_polkit_a_rc=$?
  printf 'R4_POLKIT_A_EXIT=%s\n' "$r4_polkit_a_rc"
  exit "$r4_polkit_a_rc"
)
```

Require the normal **KDE graphical authentication dialog**, showing guido as
the authenticating identity and `/usr/bin/true` as the program. Open Details
to confirm ID `org.freedesktop.policykit.exec`. Enter guido's correct password
once at the password request. Require successful dialog closure and exit 0.
The internal terminal-agent fallback is disabled; a terminal prompt is STOP.
No dialog, automatic success, wrong identity/action, rejected password, restart
or an error means STOP before B. Do not switch identities to make the test pass.
Successful password entry proves this invocation was not automatically granted.

## Prepare B while still detached

Only after A visibly authenticated by password and exited 0, run this in the
same terminal. A normal **sudo** password prompt may occur solely for service
preparation; it is not another sudo qualification or the PolicyKit password test.
This stops fprintd once, without disabling/masking it; stock D-Bus activation
remains available. It is preparation for B, not a repair of historical PID 8053.

```bash
unset r4_polkit_since
r4_polkit_since=$(
  set -euo pipefail
  trap 'printf "R4_POLKIT_B_PREPARATION_STOP line=%s exit=%s\n" "$LINENO" "$?" >&2' ERR
  cd "$(git rev-parse --show-toplevel)"
  systemd-detect-virt --vm --quiet
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
PY
  sudo -N -- /usr/bin/systemctl stop fprintd.service
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  pkcheck --revoke-temp
  r4_polkit_cached=$(pkcheck --list-temp)
  test -z "$r4_polkit_cached"
  date -u '+%Y-%m-%d %H:%M:%S.%6N UTC'
)
```

Any error means STOP. This timestamp scopes the existing safety telemetry;
it is not an authorization token. Do not open other authentication clients.

## B. First native PAM fingerprint series only

Attach the reader to this VM only, then run this once. Keep hands off the
reader until the expected dialog and identity are visible. **Do not type a
password, press Enter/OK, switch identity or restart the dialog while attached.**

```bash
(
  test -n "${r4_polkit_since:?Missing preparation; STOP}" || exit
  r4_polkit_b_rc=0
  pkexec --disable-internal-agent --user root /usr/bin/true || r4_polkit_b_rc=$?
  printf 'R4_POLKIT_B_EXIT=%s\n' "$r4_polkit_b_rc"
  exit "$r4_polkit_b_rc"
)
```

Confirm the KDE dialog, guido identity and same program/action as A. The
visible password field alone does not mean fallback: leave it empty while
the fingerprint instruction is shown. Present the **RIGHT index**, even if
the instruction calls the saved slot left-index-finger. Lift fully between
contacts. After an explicit NO_MATCH 1 or 2, wait for the next native scan
request. Allow at most **three contacts in this first PAM series** and stop
at the first MATCH. No wrong-finger test, fourth contact or second biometric
invocation. A processing/retry error, timeout or unclear prompt ends the series.

On success, lift and detach USB immediately. Require dialog closure and exit 0
with **no password or empty response submitted in B**, corroborated by MATCH
telemetry. If there is no dialog or no biometric evidence, do not call it PASS.

After NO_MATCH 3, timeout/error, unexpected identity/restart or password fallback,
**detach USB before any password entry, Enter/OK, identity change or further
conversation**. The observed PAM stack limits one fingerprint call to three
tries (30 seconds per verification); exhausted/failed fingerprint falls through
to pam_unix, whose password read blocks until a response. With no submitted
input, normal fingerprint exhaustion therefore does not complete the whole PAM
conversation or start another series. This is not a global KDE limit: KDE can
recreate a conversation after whole-stack failure or an identity change.
Never submit even an empty response while attached. Unexpected behavior is STOP,
not permission to use another series; detach first and report it.

With USB detached, enter the correct password once if B is waiting for it;
report fallback separately. If the dialog already exited, run the command from
A once, still detached, solely to establish password access after the failure.
Do not loop or guess passwords. Exit 0 after password fallback is **not** a
fingerprint PASS. Password failure or desktop loss is a blocker; stop testing.

## Cleanup and evidence after B or STOP

Detach USB and close any remaining authentication dialog. In the same terminal
and checkout, run the block below. It checks absence before sudo, stops fprintd
once and reads only this series' existing safety lines. A normal sudo password
prompt may occur. A missing timestamp stops the broadening of the log query.

```bash
(
  set -euo pipefail
  cd "$(git rev-parse --show-toplevel)"
  systemd-detect-virt --vm --quiet
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
PY
  sudo -N -- /bin/bash -c '
    set -euo pipefail
    systemctl stop fprintd.service
    systemctl show fprintd.service -p ActiveState -p MainPID
    test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
    test "$(systemctl show fprintd.service -p MainPID --value)" = 0
    test -n "$1" || { echo "Missing series start; report without broader log query" >&2; exit 1; }
    journalctl -u fprintd.service --since="$1" --until=now --no-pager -o cat \
      --grep="GOODIX_(STOCK_CAPTURE_(BEGIN|RESULT|REJECT)|PRODUCTION_EPOCH_AUDIT)"
  ' r4-polkit-cleanup "${r4_polkit_since:-}"
)
```

Return the complete safety lines: expect 1–3 admitted captures, one result per
capture, VERIFY for the single template (stock `any` may use IDENTIFY with
multiple templates), no ENROLL, and closed/drained epochs. Require zero
secure/post retry, reset, clear_halt, persistent families and outstanding;
drained=1/context_closed=1. Clean NO_MATCH has completed release_tail and
single_terminal before reuse; the next explicit attempt may increment reopen
counters. MATCH may let PAM disconnect before the release tail, as in the
accepted sudo/KScreenLocker runs; zero tail counters alone do not invalidate
closed/drained cleanup or prove device quiescence. A fourth BEGIN, new series,
rejection or missing audit requires review, not another live.

**PASS_IF:** A password with reader absent passed; B used the KDE agent and
matched within three contacts without a submitted response, exited 0, safety
telemetry is consistent, desktop usable, sensor detached and fprintd
inactive/MainPID 0. PolicyKit is then eligible for SUPPORTED on this baseline
after review. **FAIL_IF:** actual authentication failure, three NO_MATCH,
error, unsafe cleanup or instability. Password-safe fingerprint failure is a
candidate KNOWN_LIMITATION/UPSTREAM_BUG after diagnosis, not authorization for
a private bridge. A driver failure is not automatically a KDE bug.
**STOP_IF:** failed prerequisite, no real authentication, identity/action drift,
unexpected conversation or ambiguous evidence. No new policy/label/PAM/agent
patch or SELinux diagnostics: the known nr_hugepages warning alone is not FAIL.

Report checkout SHA, A dialog identity/action/password result, B messages and
exit code, contact count/MATCH contact, any submitted input or fallback/restart,
safety lines and final service/USB/desktop/runtime/template state. Confirm no
configuration change; do not provide credentials or biometric contents.

## Rollback only after actual FAIL, instability or regression

A PASS retains runtime/template. A prerequisite STOP or missing evidence without
observed failure does not require uninstall. After actual live FAIL, detach USB,
complete cleanup, then use the installed saved inverse if password sudo works:

```bash
sudo /usr/local/lib64/goodix-27c6-5125/uninstall.sh
systemctl show fprintd.service -p FragmentPath -p ExecStart -p Environment -p ActiveState -p MainPID
rpm -V --noscript fprintd libfprint
test ! -e /usr/local/lib64/goodix-27c6-5125
test ! -e /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
```

The saved inverse removes its libraries/environment drop-in and owned material
mapping, restores current Fedora default labels, reloads the unit and restores
the recorded pre-install service state. Expect stock `/usr/libexec/fprintd`,
no private library environment and clean vendor verification. Materials,
converted manifest and templates are preserved; no PAM/authselect/PolicyKit
policy is changed. Revoked temporary authorizations are not recreated: later
privileged actions can authenticate normally. No service was disabled/masked.
If password sudo is unavailable or the inverse fails, stop and report; do not
force removal or attempt TTY/distro repair. R5 remains unqualified.
