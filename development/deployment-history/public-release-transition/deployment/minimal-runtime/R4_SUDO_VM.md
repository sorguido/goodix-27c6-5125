<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: ordinary stock sudo authentication in the VM

**COMPLETED — ordinary sudo SUPPORTED on the tested baseline, human-reported.**
Preparation and reader-absent password passed; `sudo -k -- /usr/bin/true` then
exited 0 after a first-contact RIGHT-index MATCH with no password during B.
One VERIFY/epoch, zero retry/reopen/reset/persistent families, closed/drained
resources, fprintd inactive/MainPID 0 and reader detached. The observed
release_tail=0/single_terminal=0 fit the early PAM MATCH return described below.
The canonical manual preserves full telemetry and provenance: reported checkout
`f5a4430`, locally resolved to `f5a4430b50a24dc7247b455701ba35ffc582713c`.
The known nr_hugepages warning recurred during success; no new raw AVC or event
timestamp was supplied. No policy change, rollback or repeat live is needed.

`sudo -i` authentication is configuration-covered by the observed auth include
and ordinary PASS; its login shell/session remains untested, without an extended
SUPPORTED claim. The next human gate is the
[read-only VM login configuration query](R4_LOGIN_PREFLIGHT_VM.md), reader detached and desktop open.
Keep runtime/template and the known RIGHT-index/left-index-finger label mismatch.

## Completed procedure and original criteria

**Historical human gate — do not rerun the procedure below.**
**HUMAN_REQUIRED — human-only VM preparation, USB and authentication.**
The [configuration query](R4_SUDO_PREFLIGHT_VM.md) passed at
`168469b79565cf401f2cb256448c184f3a803d8c`: sudo uses system-auth, with
`pam_fprintd.so` sufficient before `pam_unix.so`. A fingerprint success can
complete authentication without a password; otherwise the stack reaches the
password module. No PAM/authselect/sudoers or runtime patch is needed.

Qualify ordinary `sudo` for `guido`, using `/usr/bin/true`, which exits without
changing files. `sudo -i`, PolicyKit, login, wrong-finger rejection and updates
are outside this test. Keep the physical RIGHT-index template labeled
`left-index-finger`. Do not repeat enrollment, CLI verify, KScreenLocker or
the completed configuration/audit queries.

## Retained baseline and prerequisites

Use the existing Fedora 44 KDE VM as `guido`, with the sensor detached and
other authentication clients closed. Finish any package update first; report
configuration/version drift instead of repairing it here. Keep the known
working password and an ordinary desktop terminal available throughout.

Retained build: `b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`; install:
`264cd7ff1ba77857e1985502f299e4375f9a0516`. Runtime/template, manifest/receipt and
SELinux Enforcing remain unchanged. The existing [install.sh](install.sh) and
the **installed, saved** `/usr/local/lib64/goodix-27c6-5125/uninstall.sh` remain
the installation/inverse pair. Do not reinstall or replace the inverse.

In an ordinary Bash terminal inside the VM clone, run this preparation check.
Any error or changed version/profile means STOP before USB attachment.

```bash
(
  set -euo pipefail
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  test "$(id -un)" = guido
  systemd-detect-virt --vm --quiet
  test "$(getenforce)" = Enforcing
  rpm -q sudo fprintd fprintd-pam pam authselect authselect-libs
  test "$(rpm -q sudo)" = sudo-1.9.17-8.p2.fc44.x86_64
  test "$(rpm -q fprintd)" = fprintd-1.94.5-5.fc44.x86_64
  test "$(rpm -q fprintd-pam)" = fprintd-pam-1.94.5-5.fc44.x86_64
  test "$(authselect current --raw)" = 'local with-silent-lastlog with-mdns4 with-fingerprint'
  authselect check
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
print(d.run('systemctl', 'show', 'fprintd.service', '--all',
            '--property=ActiveState', '--property=SubState', '--property=MainPID'))
print('R4_SUDO_PREPARATION_CHECK=PASS SENSOR_CONNECTED=false')
PY
)
```

The accepted remaining versions are pam 1.7.2-2.fc44 and authselect/authselect-libs
1.7.1-1.fc44, x86_64. These checks bind this experiment, not system accessibility
or a permanent version pin. An active fprintd at this point is allowed: the
completed query ended active/running/PID 3802 after password authentication.
Stock fprintd has a 30-second idle timer; the immediate snapshot alone is not
a failure and does not demonstrate that it later exited.

## A. Password first, reader absent; prepare a clean service boundary

The preflight already observed a successful sudo password prompt with the
reader absent. The necessary service preparation below also uses password
authentication, explicitly ignoring cached credentials. Enter `guido`'s correct
password once. Confirm a real password prompt occurred and the block succeeded;
an error, unexpected user, missing prompt or rejected password means STOP before B.

Run in the same terminal/checkout. This stops fprintd once, without disabling
or masking it. Normal D-Bus activation remains available for B; no start command
or installation rollback is needed to undo the temporary stop. This prepares
the new test, not a correction of the previous active-state evidence.

```bash
unset r4_sudo_since
r4_sudo_since=$(
  set -euo pipefail
  cd "$(git rev-parse --show-toplevel)"
  systemd-detect-virt --vm --quiet
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
PY
  sudo -k -- /usr/bin/systemctl stop fprintd.service
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  date -u '+%Y-%m-%d %H:%M:%S.%6N UTC'
)
```

`-k` with a command ignores existing cached credentials and does not refresh
them. It is used again for B, so the password used in A cannot produce a cached
success in B. No authentication cache file is inspected or edited.

## B. One native fingerprint series

Only after A succeeds, attach the reader to this VM only. Do not use settings,
other authentication clients or another sudo command while it is attached.
Run this once in the same terminal; do not type a password or an empty Enter.

```bash
(
  test -n "${r4_sudo_since:?Missing preparation; STOP}" || exit
  r4_sudo_b_rc=0
  sudo -k -- /usr/bin/true || r4_sudo_b_rc=$?
  printf 'R4_SUDO_B_EXIT=%s\n' "$r4_sudo_b_rc"
  exit "$r4_sudo_b_rc"
)
```

Present the **RIGHT index** when requested, even if the prompt names the stored
left-index-finger. Maximum **three independent contacts**, lifting fully between
them. After explicit NO_MATCH 1 or 2, wait for the next native fingerprint
request. Stop on the first success, NO_MATCH 3, processing/retry error, timeout,
unexpected password prompt/restart or ambiguous behavior. No fourth contact,
second sudo invocation, `sudo -i`, or password entry while USB is attached.

The unchanged PAM module limits one PAM call to three tries, with a 30-second
timeout per verification. Clean NO_MATCH permits its next explicit VerifyStart;
MATCH ends authentication. **This is not a global sudo limit:** sudo's password
retry loop can call PAM again after a failed whole stack. In the observed stack,
fingerprint failure reaches the blocking password prompt. Detach USB before
responding, so a password failure cannot start a new sensor series. The driver
also rejects processing-error resubmission before new sensor resources; it
does not impose a cumulative cap on explicit clean-NO_MATCH actions.

On success, lift and detach USB immediately. Expect exit 0 with **no password
entered in B**, corroborated by MATCH telemetry. Exit 0 alone is insufficient.
If B falls back to a password, first detach via the VM manager, then enter the
correct password once at that prompt. Record fallback success separately:
exit 0 after a password does not mean fingerprint PASS. If B has already exited,
with USB detached use `sudo -k -- /usr/bin/true` once to check password access.
Cancel an unexpected remaining prompt after an error; no password-guessing loop.
A password-path failure blocks further tests even if the desktop is still usable.

## Cleanup and evidence

With USB detached, run this in the same checkout/terminal after B or a STOP.
It checks sensor absence before sudo, stops the daemon once and reads the existing
session safety lines. The normal password prompt may appear. No new capture or
diagnostic live is permitted. If the session time was lost, it stops the daemon
and reports that error without reading a broader log window.

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
    test -n "$1" || { echo "Missing session start; report without broader log query" >&2; exit 1; }
    journalctl -u fprintd.service --since="$1" --until=now --no-pager -o cat \
      --grep="GOODIX_(STOCK_CAPTURE_(BEGIN|RESULT|REJECT)|PRODUCTION_EPOCH_AUDIT)"
  ' r4-sudo-cleanup "${r4_sudo_since:-}"
)
```

Return the complete safety lines. Expect 1–3 admitted captures with increasing
attempt numbers, one result per capture and closed/drained epochs. VERIFY is
expected with the single selected template; stock `any` can use IDENTIFY with
multiple templates. No ENROLL. Require zero secure/post retry, reset, clear_halt,
persistent families and outstanding transfers; drained=1/context_closed=1.
After clean NO_MATCH, release_tail=1/single_terminal=1 precede reuse; explicit
reopen counters for the next stock attempt are expected. On MATCH, PAM can
disconnect before the release tail: zero tail counters alone do not negate
closed/drained cleanup or prove device quiescence. A fourth BEGIN, a new series,
rejection, missing audit or unexpected retry requires review, never a rerun.

**PASS_IF:** A authenticated by password with the reader absent; B exited 0
after MATCH within three contacts without a password; safety telemetry is
consistent, desktop usable, reader detached, fprintd inactive/MainPID 0.
**FAIL_IF:** actual authentication failure, three NO_MATCH, error, unsafe cleanup
or instability. Password-safe fingerprint failure may become KNOWN_LIMITATION
after review; a MATCH followed by consumer failure does not alone prove an
upstream bug. **STOP_IF:** any failed prerequisite, drift or ambiguous result.
The documented nr_hugepages SELinux denial alone is not a new failure and needs
no policy change, alert lookup or additional audit query.

Report checkout/package output, A password result, B messages/exit code, number
of contacts, MATCH contact, whether/when a password was entered, any fallback
result, safety lines and final service/USB/desktop/runtime/template state.
No credentials or biometric contents are requested.

## Rollback only for actual FAIL, instability or regression

A PASS retains runtime/template. A prerequisite STOP or incomplete evidence
without observed failure does not require uninstall. For an actual live FAIL,
detach USB, complete cleanup, then use the saved inverse if password sudo works:

```bash
sudo /usr/local/lib64/goodix-27c6-5125/uninstall.sh
systemctl show fprintd.service -p FragmentPath -p ExecStart -p Environment -p ActiveState -p MainPID
rpm -V --noscript fprintd libfprint
test ! -e /usr/local/lib64/goodix-27c6-5125
test ! -e /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
```

The saved inverse removes its libraries/environment drop-in and owned material
mapping, restores current Fedora default labels, reloads the unit and restores
the recorded pre-install service state. Expected: stock `/usr/libexec/fprintd`,
no private library environment, clean vendor verification. It preserves materials,
the converted manifest and templates, and does not change PAM/authselect/sudoers.
If password sudo is unavailable or the inverse fails, stop and report the exact
failure; retain state, do not force removal or attempt TTY/distro repair. This
is a blocker, not an acceptable fingerprint limitation. R5 remains unqualified.
