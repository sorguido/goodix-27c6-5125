<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R5 corrective: lifecycle with the integrated reader present

**HUMAN_REQUIRED — internal VM procedure, not public installation instructions.**
Use the existing Fedora KDE VM only. Keep the reader connected/assigned to the
VM from start to finish. Do not unplug, unbind, disable or hide it. R6 is not
started. Save work; keep this page accessible outside the VM. Close fingerprint
settings and other authentication dialogs. During this procedure do not touch the
reader: stock sudo/TTY may offer fingerprint first; wait for the password prompt.
There is no promise of an immediate password selector or a fixed timeout for an
unknown PAM configuration. Do not repeat an unsuccessful authentication.

The previous normal removal, password/desktop, metadata preservation, reinstall
and one-contact Plasma MATCH are accepted from the user report. They are not
rerun as biometric tests. Force removal with the reader present was reported
working but lacks exact final evidence. The new failure was a recovery-tool
presence gate, before runtime installation; this corrective removes that class
of gate and controls fprintd entirely on the host side.

## 1. Establish the reported removed state

Optionally take a snapshot of the current VM state before changes; it is not an
uninstall mechanism. From the VM clone in a working graphical terminal:

```bash
(
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"
    test "$(git branch --show-current)" = development
    test -z "$(git status --porcelain)"
    git pull --ff-only origin development
    printf 'CORRECTIVE_CHECKOUT=%s\n' "$(git rev-parse HEAD)"
    systemd-detect-virt --vm --quiet
    test "$(getenforce)" = Enforcing
    printf '%s\n' 'CHECKOUT_READY=true'
)
```

Then run this **removed-state check**. Reuse this exact block after each removal;
it contains no checkout update or device action.

```bash
(
    set -euo pipefail
    for p in /etc/pam.d/plasmalogin \
        /usr/local/lib64/goodix-plasma-login \
        /usr/local/lib64/goodix-27c6-5125 \
        /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf \
        /usr/local/bin/goodix-uninstall /usr/local/bin/goodix-force-remove \
        /usr/local/share/goodix-recovery; do
        test ! -e "$p"
        test ! -L "$p"
    done
    test "$(systemctl show fprintd.service -p LoadState --value)" = loaded
    test ! -e /run/systemd/system/fprintd.service
    test ! -L /run/systemd/system/fprintd.service
    systemctl show fprintd.service -p ExecStart -p Environment -p LoadState
    sudo find /var/lib/goodix-5125-poc /var/lib/fprint -xdev -type f \
        -printf '%p | inode=%i bytes=%s mode=%m owner=%U:%G mtime=%T@\n'
    printf '%s\n' 'PROJECT_PATHS=ABSENT SERVICE_UNMASKED=true'
)
```

Expect stock `/usr/libexec/fprintd`, empty `Environment`, `LoadState=loaded`,
the same five materials and existing template. Compare the metadata to your
previous preserved output; do not report protected contents or secret hashes.
If any project path remains, stop and report that precise path; do not silently
force-clean it. This records the missing final observation of the prior run.

## 2. Install with the reader still present

Follow [the internal qualified-output install](../../docs/R5_INSTALL.md) exactly,
using the current corrected repository manager and the original binary outputs.
Keep the same checkout throughout. No build, enrollment, verify, new fingerprint
login or material conversion is needed. Expect `GOODIX_RECOVERY_INSTALL=PASS`,
`R3_INSTALL=PASS`, `PLASMA_LOGIN_INSTALL=PASS`, and final `R5_INSTALL=PASS`.
The runtime must be inactive/MainPID 0, and no temporary fprintd mask should
remain. Report any service-state refusal; do not bypass it by detaching USB.

## 3. Normal removal, then reinstall

From the working desktop terminal, type:

```text
goodix-uninstall
```

Expect `GOODIX_REMOVAL=PASS`. Follow its normal restart instruction, with the
reader continuously present, and sign in graphically using the nonempty password.
Run the exact **removed-state check** block in step 1 again to verify removal
and preservation.
Do not treat a missing command after success as failure: the tools remove
themselves last.

Then follow the **same step 2 install procedure once more**. This is the required
remove/reinstall update path with the integrated reader present; there is no
separate new update engine. No additional fingerprint functional test is needed.

## 4. TTY emergency removal

In virt-manager use **Send Key → Ctrl+Alt+F3** to reach the guest TTY. Log in with
your normal account. If fingerprint is offered first, leave the reader untouched
and wait for the normal password prompt; enter the password once. Once signed
in, the entire technical recovery command is:

```text
goodix-force-remove
```

Use its normal sudo password prompt if requested. Save the exact result and final
instruction. Expect `GOODIX_REMOVAL=PASS` with
`GOODIX_PROJECT_IN_CRITICAL_AUTH_PATH=false FEDORA_CURRENT_STATE_EXPOSED=true`.
Restart normally as instructed. Do not add recovery arguments, prefix sudo,
locate the repository, change PAM, or restart the display manager manually.

## 5. Password fallback with project fingerprint support unavailable

After that restart, keep the reader connected. Use **Send Key → Ctrl+Alt+F3**
and sign in with the ordinary username/password, without touching the reader.
Report whether fingerprint was offered first, whether a password prompt appeared,
and whether the password reached the shell. This is the smallest fallback test
with the Goodix runtime absent; no artificial hardware failure is injected.
The retained Fedora libfprint source explicitly lists `27c6:5125` as unsupported
and has no driver entry for it, but the
actual password outcome must be observed, not inferred from that table.

Return to the graphical login/session through the normal VM UI and verify a
nonempty password reaches a usable KDE desktop. Repeat the exact **removed-state check**
block in step 1. Leave the project removed.

**PASS_IF:** both corrected installations succeed with the reader continuously
present; normal and one-command TTY removal succeed; current Fedora daemon and
password/desktop work after removal; TTY password fallback works without the
project runtime; materials/template metadata unchanged; no unwanted fingerprint
authentication or automatic service restart is observed.

**FAIL_IF / STOP_IF:** any failed command, remaining project artifact, changed
preserved metadata, service that does not quiesce, unexpected capture, missing
password fallback or desktop regression. Stop at the precise step and keep the
error. Do not retry the biometric workflow, edit vendor files, mask a failure as
PASS, or detach the device. A failure at the same point leads to inspection of
its specific host service state, not another identical live run.

**Rollback:** before any runtime change, the current
`./deployment/recovery/uninstall.sh` removes only the recovery-tool patch. After
partial install or instability, use `goodix-uninstall` from the desktop. If its
strict checks refuse an incomplete installation, report that refusal; emergency
`goodix-force-remove` remains available from TTY and tolerates partial state.
An unsuccessful removal retains recovery tooling and may retain runtime files;
report the final error rather than deleting them manually. A snapshot restore
is an external fallback and never evidence of successful uninstall.

Return only the full checkout SHA, each stage's PASS/error, exact force-remove
result, reader continuously-present confirmation, password/desktop and TTY
fallback observations, preserved metadata comparison, and final service output.
No new biometric logs are requested unless an actual unexpected action occurs.
Stop here for review; do not start R6.
