<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Uninstall and emergency recovery

## Emergency: graphical login is unavailable

1. Press **Ctrl+Alt+F3** to open a text console.
2. Sign in with your normal username. If Fedora offers fingerprint first, keep
   your finger off the reader and wait for its password prompt, then enter your
   password.
3. Type **`goodix-force-remove`** and press Enter. Complete the normal sudo
   authentication if requested; it may also offer fingerprint before password.
4. Follow the one final instruction displayed, if any.

**Leave the integrated reader connected.** Do not unplug, disable or hide it.
The command is installed in the normal command search path and needs no source
tree, build directory or extra arguments. Save this page where you can read it
without your desktop.

Fedora determines console and sudo authentication prompts. There may be a wait
before password is offered; there is no promised immediate method selector or
universal fixed delay. Password fallback when biometrics are unavailable still
needs confirmation on the tested console configuration. If no password prompt
appears or correct password authentication fails, stop and report that failure.
The removal command cannot bypass authentication or repair an independently
broken Fedora installation.

The command must already be installed. A finished public installation package
is [not yet available](INSTALLATION.md); this guide does not imply that an
uninstalled command can be downloaded or run automatically during an emergency.

## Normal uninstall from a working desktop

Finish authentication dialogs and close fingerprint settings. Keep the reader
connected, with your finger off it. In a normal terminal, run:

```text
goodix-uninstall
```

The command requests ordinary sudo authentication itself. It checks only the
project's software ownership, receipts and hashes before removal. Missing or
changed Fedora vendor files do not block removal of project-owned files.
Unrecognized project changes produce a clear refusal; retain the message and
report it instead of deleting individual files manually.

A successful removal prints its result and asks for a normal restart to close
old authentication sessions. Follow that instruction, then use your password to
log in. Recovery tools remove themselves last after successful cleanup, so a
second invocation may report “command not found”.

## Removal scope

| Project-owned item | Effect |
| --- | --- |
| `/etc/pam.d/plasmalogin` | Removes the project's login entry first and exposes current Fedora PAM |
| `/usr/local/lib64/goodix-plasma-login/` | Removes the selector, saved manager and receipt |
| `/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf` | Removes the private library environment and reloads service configuration |
| `/usr/local/lib64/goodix-27c6-5125/` | Removes private libfprint/OpenCV, links, notices and installation metadata |
| Exact project material SELinux mapping | Removes an owned mapping and reapplies current policy labels to explicit material paths |
| `/usr/local/bin/goodix-uninstall`, `/usr/local/bin/goodix-force-remove`, `/usr/local/share/goodix-recovery/` | Removes recovery tools last after successful cleanup |

Removal quiesces fprintd before removing runtime files. It does not start an
authentication, directly access USB, restart the display manager, overwrite
Fedora-owned files or replay saved Fedora configuration. An error leaves the
remaining recovery tooling available where possible and reports unfinished work.

Emergency removal uses fixed project-owned paths, tolerates missing receipts or
partial software and does not depend on Fedora vendor layout or version. It
removes the project's influence; it does not diagnose or repair Fedora.

## Preserved data

Both commands preserve:

- `/var/lib/goodix-5125-poc/` and all five device-specific material files;
- fingerprint templates under `/var/lib/fprint/`;
- firmware, existing keys, factory state and persistent device configuration;
- source checkouts and saved build outputs.

Material labels can return to the **current** Fedora policy; material contents,
Unix ownership and permissions remain unchanged. Template contents and labels
are not modified. Normal removal preserves a compatible mapping recorded as
pre-existing/unowned. Emergency removal removes only the exact known project
mapping, even if its receipt is missing; unrelated SELinux rules are untouched.

Report the command's result, exact error, failure point and whether password
login/desktop work. Do not send protected files, templates or raw fingerprint
images. [Validation scope](VALIDATION.md) records the remaining recovery checks.
