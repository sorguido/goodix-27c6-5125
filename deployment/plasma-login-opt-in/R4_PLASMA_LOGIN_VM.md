<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: password first, then explicit fingerprint at Plasma Login

**COMPLETED — password login without forced fingerprint wait and first-contact
fingerprint login PASS, human-reported at checkout
`7d0e2d3bcd33dc1311f70cc26b0a72b6889acfbe`. Do not repeat this procedure.**
One empty Enter, RIGHT index, one VERIFY/MATCH, no password during B or second
series; usable desktop, drained/closed cleanup, fprintd inactive/MainPID 0 and
reader detached. Plasma Login = **SUPPORTED_ON_TESTED_BASELINE**. R4 is closed;
**R5 is not started and must not be prepared: wait for the user.**

Failure fallback B was **NOT_EXERCISED** on this first-contact MATCH. Do not
create a failure or rerun password/fingerprint to fill that untested branch.
Keep the integration, R3 runtime/template and saved inverse; no rollback on PASS.
Full evidence and review are in the [canonical manual](../../Goodix%2027c6%205125%20manuale%20tecnico.md#plasma-login--live-pass-closure-r4-e-stop-prima-di-r5).

## Completed procedure and original criteria

**Historical human gate — the instructions below record the completed test.**
Installation and file/default-label verification passed at guide checkout
`24c3018071e8d120687ff8fbd2f344cde620692d`. Keep that installation. This gate
qualifies real login through the stock greeter and helper; it does not repeat
build/install, R3 or other consumer tests, or qualify package updates.

## Retained candidate and prerequisites

Login source: `6fc6e640710885954d9e6fd603b3bc47b45d2ac6`.
Preserved VM output, relative to the private clone:
`development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja`.
The [completed installation and matching inverse](README.md) remain available.
Only `/etc/pam.d/plasmalogin` and the small support directory
`/usr/local/lib64/goodix-plasma-login/` belong to this integration.
The current Fedora PAM file was verified unchanged; no daemon, greeter, service
or authselect change is needed. Runtime R3 build
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, installation
`264cd7ff1ba77857e1985502f299e4375f9a0516`, and template stay preserved.

Use `guido`'s working Wayland desktop, known correct VM password, Enforcing,
and the same packages/configuration as the accepted installation. Save open
work; keep this guide accessible outside the guest because logout closes its
terminals. Close fingerprint settings and other authentication clients. Start
with USB detached. If an update/configuration change or desktop regression has
occurred since installation, STOP and report it before logout. No TTY session,
display-manager restart, reboot, policy change or additional recovery service
is part of this test.

From an ordinary Bash terminal in the VM clone, run once:

```bash
(
    set -euo pipefail
    trap 'printf "R4_LOGIN_PREPARATION_STOP line=%s exit=%s\n" "$LINENO" "$?" >&2' ERR
    cd "$(git rev-parse --show-toplevel)"
    test "$(git branch --show-current)" = development
    test -z "$(git status --porcelain)"
    git pull --ff-only origin development
    printf 'GUIDE_CHECKOUT=%s\n' "$(git rev-parse HEAD)"
    git diff --exit-code 6fc6e640710885954d9e6fd603b3bc47b45d2ac6 HEAD -- \
        deployment/plasma-login-opt-in/manage.py \
        deployment/plasma-login-opt-in/pam_goodix_login_gate.c \
        deployment/plasma-login-opt-in/plasmalogin.pam
    test "$(id -un)" = guido
    systemd-detect-virt --vm --quiet
    test "${XDG_SESSION_TYPE:-}" = wayland
    test "$(getenforce)" = Enforcing
    python3 -I -B - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location('runtime_deploy', 'deployment/minimal-runtime/deploy.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
d.no_sensor()
PY
    printf '%s\n' 'R4_LOGIN_PREPARATION=PASS SENSOR_CONNECTED=false'
)
```

These are provenance and absence checks, not a rebuild or another installation
verification. No authentication is invoked by this block. Keep its checkout SHA.

## A. Normal password login, reader absent

1. Use KDE's normal **Log Out** action. This must reach the real Plasma Login
   greeter, not Lock Screen or Switch User into an existing session.
2. Select `guido` and the usual Plasma Wayland session. Type the correct,
   **nonempty password before pressing Enter**, then submit once.
3. Confirm a usable desktop starts. Record whether authentication began normally
   without a fingerprint request or forced fingerprint timeout, and any unusual
   delay. Normal session startup time is distinct from waiting for fingerprint.

**Only continue to B if both `PASSWORD_LOGIN=PASS` and
`PASSWORD_LOGIN_NO_FORCED_FINGERPRINT_WAIT=true` are observed.** No password,
black screen, failed session start or unclear result means STOP before USB
attachment. Do not keep trying credentials or restart the display manager.
See the rollback limitation below if the desktop is unavailable.

## B. One explicit fingerprint series

After A PASS, open a new ordinary terminal in the same VM clone. With the reader
still detached, run this block once. The usual sudo password is expected; the
service is stopped only after that authentication. **Copy the printed UTC
timestamp outside the guest** for the later narrow telemetry query: shell
variables do not survive logout.

```bash
(
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"
    systemd-detect-virt --vm --quiet
    python3 -I -B - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location('runtime_deploy', 'deployment/minimal-runtime/deploy.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
d.no_sensor()
PY
    sudo -N -- systemctl stop fprintd.service
    test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
    test "$(systemctl show fprintd.service -p MainPID --value)" = 0
    date -u '+%Y-%m-%d %H:%M:%S.%6N UTC'
)
```

An error is STOP before B. Otherwise:

1. Log out normally again, **still with USB detached**. Once the normal greeter
   is ready for `guido`/Plasma Wayland, attach the reader to this VM only.
2. Ensure the password field is empty, focus it and press **Enter once**. This
   submission explicitly selects fingerprint. Do not submit again, select
   another user/session or type a password during the series.
3. Touch with the **RIGHT index**, then lift fully and wait for the result.
   The preserved template is labelled `left-index-finger`; do not use the left
   finger or change the template. The stock greeter may show no finger prompt:
   the first contact follows the explicit empty submission, not a promised
   fingerprint-specific message.
4. At most **three independent contacts**, stop on the first MATCH/desktop.
   Contact 2 or 3 is allowed only after a clearly identified NO_MATCH and a new
   native request in the same series. A generic “Login Failed”, absent/ambiguous
   feedback, processing/retry error, timeout or unexpected restart is STOP:
   lift and detach, with no additional contact or empty submission.
   If no clear result arrives within the current 30-second attempt, stop too;
   do not add a contact to find out whether capture has started.

The installed `pam_fprintd.so max-tries=3 timeout=30` enforces the series limit
and immediate return on MATCH. Timeout is **per attempt**, not per whole series;
three clean NO_MATCH can continue within this one PAM call. The unchanged driver
fences processing-error resubmission and MATCH. No fourth capture or second
biometric login is allowed in this gate. The final safety lines, not the screen
alone, establish which captures actually happened.

**Stock UI caveat:** a PAM error message, including an intermediate NO_MATCH,
can emit “Login Failed” and re-enable the field before the PAM call has ended.
Informational finger prompts are forwarded by the backend but have no display
handler in the audited stock QML. Do not equate an enabled field with a finished
series or use it to restart authentication. If the native UI cannot distinguish
NO_MATCH from a terminal error, stop rather than guessing further contacts.

On desktop arrival, lift and detach immediately. Confirm login completed without
a password; a later wallet-unlock prompt is a separate operation, to be handled
only after detach and reported separately. Do not perform sudo or another
authentication with the reader still attached.

### Password return after B failure or ambiguous feedback

Detach through the VM manager first. Do not press Enter again while empty.
Allow the outstanding PAM call to finish: wait **40 seconds after detach**
before the password submission. This is an operator margin around the configured
30-second verification timeout plus normal vendor rejection, not a new runtime
timeout or proof that a hung helper will recover.

Then, if the greeter is usable, type the correct **nonempty password** and submit
once. Its path skips fingerprint and includes the current Fedora stack. Confirm
the desktop returns without another fingerprint wait. If the field remains
disabled, the submission hangs/fails or the desktop does not start, STOP and
report a password/session blocker; do not loop or use TTY/distro repair.
Password fallback is **not** a fingerprint PASS. On first-contact MATCH this
failure branch is not exercised and must be reported as such; do not deliberately
create another series just to test failure.

## Cleanup and minimum safety evidence

After desktop return, with USB detached, use a new terminal in the VM clone.
Paste the previously saved **UTC timestamp alone** at the prompt. Do not substitute
`today` or a guessed time. This block performs one human sudo,
stops fprintd and reads only the existing safety lines in that interval; it does
not start an authentication test. If the timestamp was lost, press Enter at the
timestamp prompt: cleanup still runs, then the block stops without querying logs.
Report that missing evidence without broadening the query or repeating the live.

```bash
(
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"
    systemd-detect-virt --vm --quiet
    python3 -I -B - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location('runtime_deploy', 'deployment/minimal-runtime/deploy.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
d.no_sensor()
PY
    read -r -p 'Saved UTC timestamp: ' r4_login_since
    sudo -N -- /bin/bash -c '
        set -euo pipefail
        systemctl stop fprintd.service
        systemctl show fprintd.service -p ActiveState -p MainPID
        test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
        test "$(systemctl show fprintd.service -p MainPID --value)" = 0
        [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\ UTC$ ]] || {
            echo "R4_LOGIN_TELEMETRY_STOP: missing/invalid saved timestamp; cleanup completed" >&2
            exit 1
        }
        journalctl -b -u fprintd.service --since="$1" --until=now --no-pager -o cat \
            --grep="GOODIX_(STOCK_CAPTURE_(BEGIN|RESULT|REJECT)|PRODUCTION_EPOCH_AUDIT)"
    ' r4-plasma-cleanup "$r4_login_since"
)
```

Return all selected lines, including missing/error output. Expect 1–3 admitted
captures, one result per capture, final `outcome=MATCH terminal=1` for success,
VERIFY (or stock `any` selecting IDENTIFY), no ENROLL. Audits must be drained
and closed, with zero secure/post retry, reset, clear_halt, persistent families
and outstanding work. Clean NO_MATCH must complete release_tail/single_terminal
before the next explicit attempt; later explicit reopen counters may increase.
MATCH may disconnect PAM before release_tail, as on prior qualified consumers:
zero tail counters alone do not invalidate drained/closed cleanup or prove
device quiescence. A fourth BEGIN, new series, rejection or missing audit needs
review, never another live to replace the evidence.

**PASS_IF:** A passed without forced fingerprint wait; B started a usable desktop
with RIGHT index within three contacts and no login password, with consistent
safety telemetry; final sensor detached and fprintd inactive/MainPID 0.
**FAIL_IF:** authentication/session failure, three NO_MATCH, hidden/additional
capture, unsafe cleanup or regression. **STOP_IF:** prerequisite failure,
ambiguous feedback/evidence or unexpected behavior. Report any SELinux alert;
do not infer that a new alert is the previously documented nr_hugepages denial,
change policy/labels or run broad diagnostics.

Report guide checkout, A result/delay, B messages/contact count/MATCH contact,
whether any password was entered before desktop arrival, fallback result or
`NOT_EXERCISED`, safety lines, final service/USB/desktop/Enforcing state and
whether runtime/template were preserved. R4 remains open pending review; R5
must not start from an installation PASS or a driver MATCH alone.

## Rollback only on actual FAIL or regression

A PASS keeps the integration, R3 runtime and template. A prerequisite STOP or
incomplete evidence without an observed failure requires review, not automatic
uninstall. On actual login FAIL/regression, detach, reach the desktop with the
normal password if possible, and complete cleanup. Run the exact
[saved-candidate rollback block](README.md#owned-installation-and-inverse).
It invokes `sudo python3 -I -B "$r4_build/manage.py" uninstall`, verifies removal
of the owned PAM entry/support and reveals `/usr/lib/pam.d/plasmalogin` unchanged.
It does not uninstall R3, delete templates, replay Fedora files or restart login.

If password/desktop access is unavailable, that block cannot be run from the
desktop: report `ROLLBACK=PENDING_NO_DESKTOP` and the failure, then stop.
No alternate privileged access, recovery console, VM snapshot or successful
rollback is presumed. If the inverse refuses changed/foreign files, preserve
the error and stop rather than removing them manually. After successful rollback,
report its marker and usable desktop; no further login experiment is requested.
