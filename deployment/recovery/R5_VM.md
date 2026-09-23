<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R5 VM: normal removal, end-user reinstall and emergency removal

**HUMAN_REQUIRED — prepared, not executed.** Run this once in the existing Fedora
44 KDE VM after the R5 handoff, never on the physical Fedora host. R4 remains
closed. This qualifies the removal/reinstall path; it does not repeat enrollment,
the full R3/R4 consumer matrix, or a Fedora update matrix. R6 is not started.

Keep this page and [the four emergency steps](../../docs/UNINSTALL.md) accessible
outside the VM. Use the known correct VM username/password and working KDE
desktop; save open work. SELinux remains Enforcing. Detach the reader from the
VM except for the single functional check in step 5. Close authentication dialogs
and fingerprint settings before each lifecycle operation. Do not change or move
Fedora vendor files to create failures; those cases are covered synthetically.

The qualified original outputs must still exist as listed in
[the end-user install procedure](../../docs/R5_INSTALL.md). The current checkout
must be the clean `development` commit delivered in the R5 handoff. Record its
full SHA below; this records provenance and is not another authorization step.
Missing build output, unexpected changes since R4 PASS, nonworking password,
missing preserved material/template, or any failed command is **STOP_IF**.

## 1. Snapshot and add the removal commands

Use the VM manager to take a snapshot of the current **R4-PASS** state before
changing software. Record the snapshot name. It is a laboratory fallback; neither
removal command restores it or depends on it.

From an ordinary Bash terminal inside the VM clone, with the reader detached:

```bash
(
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"
    test "$(git branch --show-current)" = development
    test -z "$(git status --porcelain)"
    git pull --ff-only origin development
    printf 'R5_CHECKOUT=%s\n' "$(git rev-parse HEAD)"
    systemd-detect-virt --vm --quiet
    test "$(getenforce)" = Enforcing
    test -d /home/guido/goodix-r3-20260922-111144/runtime
    test -d development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja
    ./deployment/recovery/install.sh
    test "$(command -v goodix-uninstall)" = /usr/local/bin/goodix-uninstall
    test "$(command -v goodix-force-remove)" = /usr/local/bin/goodix-force-remove
    printf '%s\n' 'R5_TOOLS_READY=PASS'
)
```

The installer asks for normal sudo authentication and adds only the two standalone
commands and their receipt; it does not replace the qualified R3/R4 runtime.
Expect `GOODIX_RECOVERY_INSTALL=PASS` and `R5_TOOLS_READY=PASS`.

Record this metadata-only inventory before removal, without opening any material
or template. Keep it locally for comparison after both removals:

```bash
sudo find /var/lib/goodix-5125-poc /var/lib/fprint -xdev -type f \
    -printf '%p | inode=%i bytes=%s mode=%m owner=%U:%G mtime=%T@\n'
```

The five material files and existing template files must be present. Compare
file paths, inode, size, mode, owner and mtime at the checkpoints below. This
does not read or print file contents and is not a cryptographic byte-equality
claim. Content preservation is additionally covered by source review and
synthetic tests; the reinstall's successful match checks the retained template.

## 2. Normal removal from the graphical session

In the same ordinary graphical terminal, type only:

```text
goodix-uninstall
```

Enter the normal password if asked. Expect `GOODIX_REMOVAL=PASS` with preserved
material/template reporting. The command removes the login entry first, stops
fprintd, removes its own runtime/drop-in/material mapping, reloads systemd and
removes recovery tools last. Follow its final instruction to restart normally
and log in with your **nonempty password**, with the reader still detached.
Do not use a snapshot restore or TTY for this normal lifecycle step.

## 3. Check current Fedora and preserved data

Confirm the normal password reached a usable desktop, with no project fingerprint
requirement. In a new terminal, paste this block. It checks only removal results
and existing file metadata; it does not start a fingerprint test:

```bash
(
    set -euo pipefail
    for r5_path in \
        /etc/pam.d/plasmalogin \
        /usr/local/lib64/goodix-plasma-login \
        /usr/local/lib64/goodix-27c6-5125 \
        /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf \
        /usr/local/bin/goodix-uninstall \
        /usr/local/bin/goodix-force-remove \
        /usr/local/share/goodix-recovery; do
        test ! -e "$r5_path"
        test ! -L "$r5_path"
    done
    r5_environment=$(systemctl show fprintd.service -p Environment --value)
    [[ $r5_environment != *goodix-27c6-5125* ]]
    systemctl show fprintd.service -p ExecStart -p Environment
    sudo test -d /var/lib/goodix-5125-poc
    sudo test -d /var/lib/fprint
    sudo find /var/lib/goodix-5125-poc /var/lib/fprint -xdev -type f \
        -printf '%p | inode=%i bytes=%s mode=%m owner=%U:%G mtime=%T@\n'
    printf '%s\n' 'R5_REMOVAL_FILES=PASS'
)
```

Expect Fedora's `/usr/libexec/fprintd` and no project library environment. Compare
the printed file metadata with step 1; **all existing material/template files
must remain unchanged in those fields**. Material SELinux labels may have returned
to current Fedora defaults. The command's success also requires cleanup of its
owned mapping. A missing/moved Fedora vendor PAM file never prevents project
removal; this unmodified baseline should still permit its normal password login.

## 4. Reinstall using the end-user procedure

Follow [Install the qualified driver and removal commands](../../docs/R5_INSTALL.md)
**exactly**, including its original-output checks and final activation checks.
Use the same checkout recorded in step 1; do not pull another revision midway,
rebuild, re-enroll or substitute a laboratory-only installation path. Continue
only after `R5_INSTALL=PASS` and a working desktop. This is the R5 end-user
installation qualification; final public packaging remains outside R5.

## 5. One minimal functional check of the reinstall

This one native Plasma fingerprint login establishes that the reinstall restored
both the runtime and login integration. It is not a rerun of the full R4 matrix.
With the reader detached, stop fprintd and copy the printed UTC time outside the
guest for the existing safety telemetry after login:

```bash
(
    set -euo pipefail
    sudo -N -- systemctl stop fprintd.service
    test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
    test "$(systemctl show fprintd.service -p MainPID --value)" = 0
    date -u '+%Y-%m-%d %H:%M:%S.%6N UTC'
)
```

After the stop succeeds, log out normally. At the normal greeter for `guido` and
Plasma Wayland, attach the reader to the VM. Focus the **empty** password field,
press **Enter once**, and touch with the **RIGHT index**. Its retained template
is labelled `left-index-finger`; do not change or re-enroll it.

Lift fully after each contact. Stop on first MATCH/desktop, with at most **three
independent contacts in this one series**. Contact 2 or 3 requires an unambiguous
native NO_MATCH and new request. A generic “Login Failed”, absent/ambiguous
feedback, processing/retry error, timeout or restart is STOP: detach, no additional
contact or empty submission. Stock `pam_fprintd max-tries=3 timeout=30` bounds the
series; a fourth contact or second biometric series is not allowed. Informational
finger prompts may not appear, and a re-enabled field does not prove PAM ended.

On desktop arrival, detach immediately, before any other authentication. If this
fails, detach, allow **40 seconds** for the outstanding PAM call to finish, then
try the normal **nonempty password once** if the greeter is usable. A password
return is not a fingerprint PASS. On failure, follow the rollback section below;
do not repeat this check or deliberately provoke another failure.

After desktop return, with the reader detached, collect only existing safety
lines for that one series. Paste the recorded time at the prompt:

```bash
(
    set -euo pipefail
    read -r -p 'Saved UTC timestamp: ' r5_since
    sudo -N -- /bin/bash -c '
        set -euo pipefail
        systemctl stop fprintd.service
        systemctl show fprintd.service -p ActiveState -p MainPID
        test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
        test "$(systemctl show fprintd.service -p MainPID --value)" = 0
        [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\ UTC$ ]] || exit 1
        journalctl -b -u fprintd.service --since="$1" --until=now --no-pager -o cat \
            --grep="GOODIX_(STOCK_CAPTURE_(BEGIN|RESULT|REJECT)|PRODUCTION_EPOCH_AUDIT)"
    ' r5-reinstall-cleanup "$r5_since"
)
```

Expect a terminal MATCH, 1–3 admitted contacts, closed/drained audit, zero
outstanding, persistent writes, processing retries, reset or clear_halt; no
enrollment. A clean NO_MATCH must finish its cleanup before another explicit
contact. On MATCH the stock PAM may return before release_tail/single_terminal:
zero values alone do not invalidate closed/drained cleanup. Missing/ambiguous
evidence, extra capture or a new rejection is STOP for review, never a retry.
If the timestamp was lost, leave it empty: cleanup runs, then no log query runs.

## 6–8. TTY, one-command emergency removal, password verification

After reinstall functionality PASS, save work and keep the reader detached.
Follow the same [emergency procedure users will read](../../docs/UNINSTALL.md):

1. Press **Ctrl+Alt+F3** inside the VM (send the key combination to the guest).
2. Log in with the normal username and password.
3. Type **`goodix-force-remove`** and press Enter; enter the normal password if asked.
4. Follow the final instruction: restart the VM normally.

Do not change directory, locate the clone, pass arguments, prefix sudo or run
additional recovery commands. After normal restart, with the reader detached,
log in graphically with the correct **nonempty password**. Confirm the desktop
is usable and run the **same step 3 check** from its normal terminal. Compare
the material/template metadata again. Current Fedora owns login/password and
the Goodix artifacts and commands are absent. Leave this final removed state;
do not reinstall again or restore the snapshot after PASS.

## Results, failure and rollback

**PASS_IF:** normal removal succeeds from the desktop, current Fedora password
login/desktop work, original materials/templates remain, the exact end-user
installation succeeds, its one functional login matches within the bound, TTY
force removal works with one typed command, and final password/desktop and removal
checks pass. R5 closes only after review of the human-reported result.

**FAIL_IF:** removal/install failure, changed/lost preserved files, extra capture,
unclean telemetry, or password/desktop regression. **STOP_IF:** any prerequisite,
unclear result or unexpected file collision. Preserve the error and stop the
sequence at that step. No manual vendor edits, policy fixes, hidden retries or
deliberate distro damage.

Before the first full removal, a tools-only preparation failure can be undone
with `./deployment/recovery/uninstall.sh` from the clone; that inverse keeps R3/R4.
After a reinstall failure/regression, use `goodix-uninstall` from a working
desktop. If the desktop cannot be reached, use the four emergency steps. A
normal uninstall refusal must be reported; do not silently replace the normal
qualification with a forced PASS. If emergency removal itself fails, report its
exact message and final instruction; retained tooling is available for a reviewed
correction. The saved snapshot is an external fallback, never a substitute for
a successful removal result.

Return: full `R5_CHECKOUT`, snapshot name, normal and emergency command results,
password/desktop observations after each removal, metadata preservation result,
end-user install result, functional check contact count/no-password result and
the selected safety lines, final reader/service state, and any failure's exact
message/step. No protected material, hashes of secrets, templates or images.
Stop after this R5 result; R6 needs a separate decision.
