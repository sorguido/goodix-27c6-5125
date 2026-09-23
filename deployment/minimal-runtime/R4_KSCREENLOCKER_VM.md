<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: native stock KScreenLocker unlock in the VM

**COMPLETED — password unlock and first-contact fingerprint unlock PASS,
human-reported; cleanup closed/drained, sensor detached, fprintd inactive/MainPID 0.**
The physical RIGHT index matched the stored left-index-finger template, without
entering a password in the fingerprint session. **SUPPORTED on the tested
baseline**, with the non-fatal SELinux denial below documented. Preserve
runtime/template and do not repeat the test or its completed audit query.
The sudo configuration query has also passed; the next human gate is the
[ordinary stock sudo test](R4_SUDO_VM.md).

## Completed SELinux review

The user reports `R4_SELINUX_AUDIT_QUERY=PASS`: three AVCs in the target window,
all `fprintd`, denied `read` of `nr_hugepages`, target type `sysctl_vm_t`,
`permissive=0`, in Enforcing. Local times: **09:04:02, 09:04:32 and 09:06:14
CEST on 23 September 2026**. The last event coincided with the successful
first-contact unlock; password, desktop and cleanup also passed.

The read denial was **non-fatal for the tested KScreenLocker path**. This
supports consumer closure with a documented denial, not universal harmlessness
or a precise library callsite. Full raw events/source context/event IDs were
not supplied, and the AI did not inspect guest logs directly. The earlier
viewer lookup remains NOT_FOUND. No policy/label/sysctl change, permissive mode,
additional audit search, rollback or repeated live is warranted by this result.

## Completed audit query and original criteria

**Historical human gate — do not rerun the block below.** The query followed
the unsuccessful viewer lookup. Its original instructions are retained for
provenance; the returned summary and classification are recorded above.

The successful unlock was approximately **23 September 2026, 09:06 CEST
(Europe/Rome, UTC+2)**. Query only **09:01–09:11 CEST = 07:01–07:11 UTC**, a
five-minute margin on either side. Use the original VM and its existing audit
logs. Keep the reader detached, SELinux Enforcing, runtime and template intact.
Close other authentication clients. There is no new biometric test, lock/unlock,
service action, installation or rollback in this gate.

Run this block once in an ordinary-user VM terminal; no repository cwd is needed.
Sudo is expected only to read the configured audit logs; its normal password
prompt may appear. `LC_ALL=C` fixes the audit date format (`09/23/26`), and
`TZ=UTC` fixes interpretation independently of the VM's display timezone.

```bash
(
  systemd-detect-virt --vm --quiet || exit
  r4_audit_rc=0
  sudo env LC_ALL=C TZ=UTC ausearch --input-logs \
    -m AVC,USER_AVC,SELINUX_ERR \
    -ts 09/23/26 07:01:00 -te 09/23/26 07:11:00 --raw \
    || r4_audit_rc=$?
  printf 'R4_AUDIT_QUERY_EXIT=%s\n' "$r4_audit_rc"
  exit "$r4_audit_rc"
)
```

Return the complete output, including stderr and the exit marker. The selection
includes complete events matching the SELinux record types; accompanying PATH,
SYSCALL or other records with the same event ID can be relevant. Do not filter
by an assumed executable, truncate the events or apply advice found in logs.
It reads configured audit files, not just the current boot; no new audit rule
or checkpoint is created. No protected material/template contents are requested.

Exit 0 normally means matching events were found. Exit 1 can mean no matches,
a date/argument error or a file-access/read error: return the actual message,
not just the number. Missing events do not prove harmlessness or absence of a
denial; the time is approximate and log retention/notification delay remain
unknown. If the tool is absent or access fails, return that error. Do not
install tools, broaden the interval, change policy/labels, switch permissive,
run audit2allow, or reproduce the live to generate new evidence.

**PASS_IF (query only):** existing events in the stated window are returned for
review. **STOP_IF:** no matching event, query error, wrong VM or attached sensor;
return the observation without another query/live. Confirm that the sensor is
still detached and runtime/template/SELinux policy are unchanged. No rollback
is required for this diagnostic result. The retained installation/inverse below
remain available; a functional PASS is not rolled back for missing evidence.
That review is now complete. The next stock consumer's actual guest PAM route
was subsequently established by the completed sudo preflight; follow the current
stock sudo guide linked above.

## Completed live procedure and original criteria

**Historical human gate — do not rerun the procedure below.**
The [configuration query](R4_KSCREENLOCKER_PREFLIGHT_VM.md) passed at
`90a3c46beeead6b50e13426870e3d30f496c67f9`: Fedora 44 KDE/Wayland, Enforcing,
stock `kde` → password-auth without pam_fprintd; `kde-fingerprint` →
fingerprint-auth with pam_fprintd. Authselect already has `with-fingerprint`.
This establishes configuration, not a working unlock. **No configuration or
runtime installation is needed.** Keep the R3 runtime and template.

This test qualifies one normal password unlock with the reader absent, then
one native fingerprint unlock. It does not test login, sudo, PolicyKit, updates,
wrong-finger rejection or exhaustive failure isolation. Do not run the completed
R3 CLI tests, a standalone test greeter or any historical PAM overlay.

## Baseline and preparation

Use the existing Fedora 44 KDE Wayland VM session as `guido`, with the sensor
detached. Close fingerprint settings and other authentication clients; finish
any package update before this gate and report version/configuration drift
instead of proceeding. Keep the usual lock-screen theme/configuration. Save
open work and have the known working VM account password available.

Retained build: `b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`; install:
`264cd7ff1ba77857e1985502f299e4375f9a0516`. The installation/inverse pair is
[install.sh](install.sh) and the **installed, saved**
`/usr/local/lib64/goodix-27c6-5125/uninstall.sh`. The [completed deployment](README.md)
records the manifest/receipt and ownership. Do not rebuild, reinstall or replace
that inverse. R4 adds no files to the VM's runtime or authentication configuration.

In an ordinary-user Bash terminal in the VM checkout, run this once; any failure
means STOP. This records the new documentation checkout and checks the additional
stock UI package (`plasma-desktop`), absent from the previous package query.

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
  test "${XDG_SESSION_TYPE:-}" = wayland
  test "$(getenforce)" = Enforcing
  test "$(rpm -q plasma-desktop)" = plasma-desktop-6.7.5-1.fc44.x86_64
  rpm -q kscreenlocker plasma-workspace plasma-desktop fprintd fprintd-pam
  rpm -V --noscript plasma-desktop
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.require_stopped()
print('R4_NATIVE_READY SENSOR_CONNECTED=false')
PY
)
```

Expected remaining versions are kscreenlocker/plasma-workspace 6.7.5-1.fc44
and fprintd/fprintd-pam 1.94.5-5.fc44, all x86_64. These are test provenance,
not runtime version pins. A version difference, RPM output, changed PAM/theme,
active daemon or missing prerequisite goes back to review; do not repair it here.

## A. Password with the reader absent

Keep USB detached. Use KDE's normal **Lock Screen** action in the VM. Reveal
the password prompt and unlock with `guido`'s password. Confirm the actual
locked screen required authentication and the desktop is usable afterward.
If it merely dismissed an unlocked screen, the observation is inconclusive.
If password unlock fails, STOP before connecting the reader and report the
visible error. No TTY, forced unlock or distro repair is part of this test.

Only after password PASS, in the same checkout, stop any daemon activated by
the reader-absent authentication. The sudo password prompt is expected here.
Stop if this block fails; it sets the session time only after all checks pass.

```bash
r4_since=$(
  set -euo pipefail
  cd "$(git rev-parse --show-toplevel)"
  systemd-detect-virt --vm --quiet
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
PY
  sudo systemctl stop fprintd.service
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  date -u '+%Y-%m-%d %H:%M:%S.%6N UTC'
)
```

## B. One native fingerprint session

Attach the Goodix reader to this VM only. Do not invoke sudo, settings or any
other authentication client while it is attached. Use **Lock Screen** once
and reveal the prompt with the mouse. Leave the password field empty: do not
press Enter, submit a password, switch user, suspend or start a second lock.
If the screen dismisses before a fingerprint attempt, STOP: that is not proof
of fingerprint unlock.

When fingerprint is requested, use the **RIGHT index**. The stored label and
prompt may say **left-index-finger**; the known anatomical mismatch is preserved
for this R4 phase by the user's decision. Do not change the slot or enroll again.

Use at most **three independent contacts**, lifting fully between them. After
the first or second explicit “Failed to match fingerprint” message, wait for
the next native fingerprint request before the next contact. Stop on the first
successful unlock, the third NO_MATCH, any retry/processing error, timeout or
unexpected restart. If the result is unclear or the prompt never appears, stop;
do not add contacts to investigate. No fourth attempt or new lock session.

The unchanged pam_fprintd default enforces three attempts in one PAM call and
a 30-second verification timeout per attempt. The reviewed KScreenLocker 6.7.5
authenticator does not restart PAM solely on fingerprint failure. A password
failure or a new authentication session can restart it, which is why neither
belongs to this fingerprint series. The driver permits only a clean NO_MATCH
reopen and fences processing-error resubmission before new sensor work. See
[the canonical review](../../Goodix%2027c6%205125%20manuale%20tecnico.md).

On success, lift the finger, confirm the desktop returned **without entering a
password**, and detach USB. On failure/STOP, lift and detach USB via the VM
manager **before typing the password**; then use the normal password prompt
to return to the desktop. Report whether that fallback worked. If password or
desktop is impaired, stop all further tests: it is a blocker, not a permissible
fingerprint limitation. No timeout-driven relock/retry or automatic recovery.

## Cleanup, evidence and outcome

With the reader detached, use the same terminal. This stops fprintd once and
reads only existing safety telemetry for this session. One sudo invocation
avoids another privilege prompt between service stop and final state query.

```bash
sudo bash -c '
  set -euo pipefail
  systemd-detect-virt --vm --quiet
  systemctl stop fprintd.service
  systemctl show fprintd.service -p ActiveState -p MainPID
  journalctl -u fprintd.service --since="$1" --until=now --no-pager -o cat -n 40 \
    --grep="GOODIX_(STOCK_CAPTURE_(BEGIN|RESULT|REJECT)|PRODUCTION_EPOCH_AUDIT)"
' r4-cleanup "${r4_since:?Missing session start; STOP and report}"
```

Return the complete safety lines, not just MATCH. Expect one to three BEGINs
with increasing attempt numbers, one result per admitted capture and drained,
closed epoch audits. PAM requests `any`: a single selected template uses VERIFY;
multiple templates can use IDENTIFY. Neither permits ENROLL here. Require
`attempts=1 rejected=0 consumed=1 tls=1 first_image=1` in each completed epoch,
`secure_retry=0 post_retry=0 reset=0 clear_halt=0 persistent=0 outstanding=0
drained=1 context_closed=1`, no enrollment/rearm work or unexplained rejection.
After clean NO_MATCH, `release_tail=1 single_terminal=1` must precede reuse;
explicit VERIFY/IDENTIFY reopen counters on subsequent epochs are expected
and are not hidden retries. MATCH is terminal; stock PAM may disconnect before
the release tail, so zero tail counters at MATCH alone do not negate closed,
drained cleanup or prove clean device quiescence. A fourth BEGIN, duplicate
series, missing/unmatched lines or reaching the 40-line limit requires review,
never another live run to replace evidence.

**PASS_IF:** A passed; B unlocked the real session with the physical RIGHT index
within three contacts and without a password; `outcome=MATCH terminal=1` and
consistent, clean safety telemetry are present;
desktop usable, sensor detached, fprintd inactive/MainPID 0. This supports
`SUPPORTED` for this consumer on the tested baseline after review, not all R4/R5.
**FAIL_IF:** three NO_MATCH, live error, failed unlock, instability or bad cleanup.
**STOP_IF:** precondition failure, ambiguous result or unexpected behavior.
A driver MATCH with failed consumer unlock and safe password/desktop is a
candidate `KNOWN_LIMITATION / UPSTREAM_BUG`, subject to failure review. A failure
alone does not locate a bug in KDE or justify private consumer changes.

Return checkout SHA/package output, A password outcome, B visible messages,
number of contacts and which contact unlocked, physical RIGHT index/stored left
label confirmation, whether a password was entered in B, safety lines, final
service/USB/desktop state and whether runtime/template were retained. Additional
targeted consumer logs are requested only if a real failure needs explanation.

## Rollback on live FAIL or instability

After detaching USB and reaching the desktop, use the **saved inverse**, then
check the vendor service and absence of project runtime/drop-in. A STOP before
live needs no uninstall; a PASS keeps runtime and template. For inconclusive
evidence without an observed failure, stop for review rather than rerun the live.

```bash
sudo /usr/local/lib64/goodix-27c6-5125/uninstall.sh
systemctl show fprintd.service -p FragmentPath -p ExecStart -p Environment -p ActiveState -p MainPID
rpm -V --noscript fprintd libfprint
test ! -e /usr/local/lib64/goodix-27c6-5125
test ! -e /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
```

The saved inverse removes project libraries/drop-in and its owned material
mapping, restores current Fedora default labels, reloads the unit and restores
its recorded pre-install service state. Expected: vendor `/usr/libexec/fprintd`,
no project library environment, clean RPM checks. Materials, converted manifest
and all templates are preserved. It does not modify PAM/authselect or repair
KDE. On inverse error, report it and retain the state; do not force removal or
substitute the checkout inverse. Any password/desktop failure blocks advancement
even if removing the driver succeeds. R5 remains required.
