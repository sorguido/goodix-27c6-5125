<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Uninstall and emergency recovery

## Emergency: graphical login is unavailable

1. Press **Ctrl+Alt+F3**.
2. Log in with your normal username.
3. If Fedora asks for a fingerprint first, **do not touch the reader**.
4. Wait about **30 seconds** for the fingerprint attempt to time out.
5. Enter your normal password when Fedora offers the password prompt.
6. Run **`goodix-force-remove`**.
7. Enter your normal sudo password if requested. If fingerprint is offered first,
   leave the reader untouched and wait for the password prompt again.
8. Follow the final restart instruction.

**Removal does not access the reader; it may stay connected or be absent.** Save
this page where you can read it without your desktop. The command is installed by
[the installer](INSTALLATION.md), is available in the normal command search path,
and needs no clone, build directory or extra arguments.

Fingerprint-first prompts in the console or sudo are stock Fedora behavior.
The expected wait for password is about 30 seconds, depending on the current
Fedora authentication policy. There is no immediate password-method selector.
If the password prompt does not appear after the expected timeout, or password
authentication fails, **stop and seek Fedora recovery/support**.
`goodix-force-remove` cannot bypass a broken authentication stack.

## Normal uninstall from a working desktop

Finish authentication dialogs and close fingerprint settings. Keep your finger
off the reader. In a normal terminal, run:

```text
goodix-uninstall
```

The command requests ordinary sudo authentication itself. It checks the project's
software ownership, receipts and hashes. Missing or changed Fedora vendor files
do not block removal of project-owned files. Unrecognized project changes produce
a clear refusal; retain the error and report it, or use the documented emergency
removal when you need to remove a partial or damaged project installation.

Success prints **`GOODIX_REMOVAL=PASS`** and:

> Restart the computer normally to close any old authentication sessions.

Follow that instruction, then log in using your password. Recovery tools remove
themselves last after successful cleanup, so a later invocation may report
“command not found”. If removal reports an error, keep the error text and do not
assume that cleanup completed.

## Removal scope

| Project-owned item | Effect |
| --- | --- |
| `/etc/pam.d/plasmalogin` | Removes the project's login entry first and exposes current Fedora PAM |
| `/usr/local/lib64/goodix-plasma-login/` | Removes the selector and installation metadata |
| `/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf` | Removes the private library environment and reloads service configuration |
| `/usr/local/lib64/goodix-27c6-5125/` | Removes private libfprint/OpenCV, links, notices and installation metadata |
| Project-owned SELinux huge-page `dontaudit` module | Removes the project module and restores Fedora's normal audit visibility |
| `/usr/local/bin/goodix-uninstall`, `/usr/local/bin/goodix-force-remove`, `/usr/local/share/goodix-recovery/` | Removes recovery tools last after successful cleanup |

Removal stops and quiesces fprintd before removing runtime files. It does not
start authentication, directly access USB, restart the display manager,
overwrite Fedora-owned files or replay saved Fedora configuration. On incomplete
cleanup, remaining recovery tooling is retained where possible.

Emergency removal uses fixed project-owned paths and tolerates missing receipts
or partial software. It does not depend on Fedora vendor layout or version.
An installation error that reports incomplete rollback can be cleaned up with
this same command while password and administrative access remain available.

## Preserved data

Both commands preserve:

- `/var/lib/fprint/goodix-5125-state-v2/` and its host pairing state;
- fingerprint templates under `/var/lib/fprint/`;
- firmware, factory data and the reader's current pairing; neither command writes
  to the reader;
- your source clone.

Preserved directory contents, Unix ownership and permissions remain unchanged;
SELinux labels return to the current Fedora policy. Template contents and labels
are not modified. Emergency removal deletes only the exact known project SELinux
module, even without its receipt; unrelated SELinux rules are untouched.

Report the result, exact error, failure point and whether password login and the
desktop work. Do not send protected files, templates or fingerprint images.
[Validation scope](VALIDATION.md) records the current evidence and limitations.
