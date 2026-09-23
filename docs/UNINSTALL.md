<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Uninstall and emergency recovery

## Emergency: the graphical login is unavailable

1. Press **Ctrl+Alt+F3**.
2. Log in with your normal username and password.
3. Type **`goodix-force-remove`** and press Enter. Enter your normal password if asked.
4. Follow the one final instruction displayed, if any.

The command is installed in your normal command search path. You do not need
the repository, a build directory, a commit, or additional arguments. It removes
the Goodix project's influence on authentication and exposes the **current
Fedora configuration**. It does not repair a Fedora installation independently
broken by another cause. If text-console login or the normal sudo password
authentication itself is unavailable, this command cannot grant access; report
that failure instead of repeatedly trying credentials.

Save this page somewhere you can read without the VM desktop. The command must
have been installed before the emergency; existing R4 installations receive it
through the [R5 VM procedure](../deployment/recovery/R5_VM.md).

## Normal uninstall from a working desktop

Close fingerprint settings and authentication dialogs, detach the Goodix reader
from the VM, then open a terminal and run:

```text
goodix-uninstall
```

Enter your usual password when requested. The command checks the project's
receipts, ownership and file hashes before removal. A changed or unrecognized
project file causes a clear refusal. It does **not** require Fedora's vendor PAM
file to exist or match an old version. On a refusal, keep the error and report it;
do not work around the check by deleting individual files.

A successful removal needs no repository or build output. The recovery commands
remove themselves last, after the software removal succeeds. A second invocation
can therefore say “command not found”; that alone is not a removal failure.
The [installation procedure](R5_INSTALL.md) reinstalls the commands with the
driver when needed.

## What is removed and preserved

Both commands remove the qualified R3/R4 software and its project-owned effects:

| Project-owned item | Removal effect |
| --- | --- |
| `/etc/pam.d/plasmalogin` | Removes the project's login entry first; Fedora's current PAM becomes responsible again |
| `/usr/local/lib64/goodix-plasma-login/` | Removes the selector module, saved manager and receipt |
| `/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf` | Removes the private library setting and reloads systemd configuration |
| `/usr/local/lib64/goodix-27c6-5125/` | Removes the private libfprint/OpenCV runtime, links, notices, saved inverse and receipt |
| Project material SELinux mapping | Removes the owned exact mapping and returns the explicit material paths to the current policy's default labels |
| `/usr/local/bin/goodix-uninstall`, `/usr/local/bin/goodix-force-remove`, `/usr/local/share/goodix-recovery/receipt.json` | Removes recovery commands and their receipt last after successful cleanup |

The commands stop fprintd; they do not restart the display manager or start a
fingerprint authentication. They never restore saved Fedora files, replace
package-owned binaries, or roll back Fedora to an old snapshot.

These are deliberately **preserved**:

- `/var/lib/goodix-5125-poc/` and the five device-specific material files;
- fingerprint templates under `/var/lib/fprint/`;
- sensor firmware, keys, factory state and persistent device configuration;
- the repository and saved build outputs.

Material **labels** may change back to the current Fedora policy; material
contents, ownership and permissions are preserved. Template contents and labels
are not changed. Normal uninstall retains a compatible mapping recorded as
pre-existing/unowned. Emergency removal does not trust a receipt: it removes the
exact known project mapping if present, but never removes broader or unrelated
SELinux rules.

Emergency removal deliberately tolerates missing receipts, missing vendor files
and partial installations. It acts on a fixed, reviewed list of project paths;
it does not search for files to delete or execute saved installation code. It
keeps recovery tooling if cleanup reports errors, so those errors can be reported
and the removal completed. Unexpected files outside the known installation set
are not an invitation to delete more broadly.

## Qualification and rollback

This is the current **R5 VM candidate**, pending human qualification of normal
removal, reinstall and TTY emergency removal. The physical Fedora host is not a
runtime test target. The complete sequence and observable criteria are in
[R5 VM qualification](../deployment/recovery/R5_VM.md); no deliberate Fedora
corruption or package update is required.

To undo only the initial addition of the two recovery commands while keeping
the previously qualified R3/R4 installation, run from the repository root:

```bash
./deployment/recovery/uninstall.sh
```

This inverse asks for the usual sudo password itself and removes only the recovery tools, never the driver or login
integration. Use it only when abandoning the tools-only preparation before
testing full removal. After a driver install failure or a runtime regression,
use the normal full uninstall above; emergency removal remains available when
graphical login is unavailable. Report the command result, exact error and
failure point. Do not attach protected material or biometric templates.
