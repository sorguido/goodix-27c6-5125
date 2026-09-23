<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Security and privacy

## Factory-preserving design

The supported path preserves factory firmware, the existing reader PSK and
persistent device state. It excludes flashing, IAP, ClearApp, OTP writes,
key provisioning/replacement, factory-data writes and persistent VID:PID or
mode changes. Unknown command families and unsafe protocol states fail closed.
These design constraints do not claim exhaustive factory readback or universal
Windows compatibility testing.

An integrated reader remains present for installation, update, removal and
recovery. Lifecycle tools use host service controls to quiesce fprintd, do not
send USB commands, and do not initiate capture because a reader is connected.
Recovery-tool management does not access the sensor. A successful source review
or synthetic test does not by itself establish every real-system failure path.

## Protected input and biometric data

Stage your five protected files in `$HOME/goodix-5125-materials/`, outside the
clone. The installer imports them into a root-only runtime directory without
printing their contents. Installed device material is validated before use according to
[the material contract](DEVICE_MATERIALS.md). The transport record contains an
existing secret; the project neither generates nor distributes it. The OEM DLL
is parsed for validated data, not loaded as executable code. The C runtime material loader and
secure-session implementation cleanse their sensitive buffers.

Fingerprint images are processed in memory. Fedora fprintd stores enrolled
templates in `/var/lib/fprint/`. Removal preserves templates and device material;
it does not export or purge them. Manage enrolled fingers using KDE or fprintd,
including before deleting an account where cleanup is needed. This architecture
does not install an account-deletion hook or promise automatic template deletion.

## Host authentication boundary

Fedora owns fprintd, Plasma, PAM, sudo and PolicyKit. The project adds a private
library directory, a narrow service environment drop-in and a minimal
Plasma Login selector. It does not ship a replacement daemon/greeter or freeze
Fedora's vendor authentication files. SELinux uses a narrow material label
mapping, without a custom permission-granting policy module.

Password access must remain available. A future incompatible Fedora PAM layout
can affect the selector; compatibility across all future updates has not been
proven. [Removal](UNINSTALL.md) exposes the current Fedora configuration without
restoring an old copy. Emergency removal still requires working console and
administrative authentication; it cannot bypass them or repair unrelated damage.

## Reporting a problem

Report the software version, Fedora version, reader identity, exact command,
observed behavior and non-secret error text. Share only relevant redacted logs
when needed. Never attach device-material directories, firmware, OEM binaries,
raw USB captures, fingerprint images or templates.

The [validation page](VALIDATION.md) describes the current support limits.
