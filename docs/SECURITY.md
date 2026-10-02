<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Security and privacy

## Factory-preserving design

The supported path preserves factory firmware, factory data and the reader's
existing `BB010002` record byte-for-byte. It excludes flashing, IAP, ClearApp,
OTP writes, factory-data writes, factory key replacement and persistent VID:PID
or mode changes. Unknown command families and unsafe protocol states fail closed.
These design constraints do not claim exhaustive factory readback or universal
Windows compatibility testing.

The single persistent reader mutation is one bounded host-pairing write. The
driver generates a Linux PSK locally, journals it root-only, records it with
exactly one logical `E0`, and proves the result by reading back the unchanged
`BB010002` and the new validator and by completing a TLS 1.2 handshake before the
key is used. There is no automatic `E0` retry, ordinary same-OS reopens write
nothing, and the Linux PSK is never shared with or exported to Windows.

Installation, update, removal and recovery do not access the reader, whether or
not it is connected. Lifecycle tools use host service controls to quiesce fprintd,
do not send USB commands, and do not initiate capture because a reader is
connected. Recovery-tool management does not access the sensor. A successful
source review or synthetic test does not by itself establish every real-system
failure path.

## Protected input and biometric data

If using the legacy migration path, stage your five protected files in
`$HOME/goodix-5125-materials/`, outside the clone. The installer imports them into a root-only runtime directory without
printing their contents. Installed device material is validated before use according to
[the material contract](DEVICE_MATERIALS.md). A legacy transport record contains
an already existing secret, which the project neither extracts from the reader
nor distributes. The OEM DLL
is parsed for validated data, not loaded as executable code. The C runtime material loader and
secure-session implementation cleanse their sensitive buffers. State-v2 stores
its PSK and authenticated receipt in two crash-safe root-only generations under
`/var/lib/fprint/goodix-5125-state-v2/`; removal preserves this directory.

Discovery, enumeration, ordinary open, boot and an uninitialized login do not
read protected material or claim USB. Only an explicit libfprint action may
request runtime resources, and it first runs a bounded read-only preflight that
binds identity, application, chip profile, OTP, generated CONFIG90 and the live
validator. An action that cannot bind that evidence fails closed. The runtime
coordinator itself exposes no pairing write: the single `E0` is reachable only
through the separately bounded activation graph, which refuses a second write for
the same transaction and fails closed on an ambiguous post-write state.

Fingerprint images are processed in memory. Fedora fprintd stores enrolled
templates in `/var/lib/fprint/`. Removal preserves templates, host pairing state
and any legacy device material; it does not export or purge them. Manage enrolled fingers using KDE or fprintd,
including before deleting an account where cleanup is needed. This architecture
does not install an account-deletion hook or promise automatic template deletion.

## Host authentication boundary

Fedora owns fprintd, Plasma, PAM, sudo and PolicyKit. The project adds a private
library directory, a narrow service environment drop-in and a minimal
Plasma Login selector. It does not ship a replacement daemon/greeter or freeze
Fedora's vendor authentication files.
SELinux remains Enforcing. On Fedora, the installer also adds one project-owned
`dontaudit` rule for the known non-fatal oneTBB `nr_hugepages` read probe. The
rule grants no access: it only suppresses audit notifications for denied
`fprintd_t -> sysctl_vm_t:file read` events. Because SELinux policy is type-based,
the same suppression can also cover other denied reads with that exact tuple.
`goodix-uninstall` and `goodix-force-remove` remove the project module and restore
Fedora's normal audit behavior.

Password access must remain available. A future incompatible Fedora PAM layout
can affect the selector; compatibility across all future updates has not been
proven. [Removal](UNINSTALL.md) exposes the current Fedora configuration without
restoring an old copy. Emergency removal still requires working console and
administrative authentication; it cannot bypass them or repair unrelated damage.

## Reporting a problem

The optional legacy
[Windows Material Builder](../tools/windows_material_builder/README.md)
runs inside the qualified Windows VM and keeps the raw USB capture on success,
failure and retry, outside the five-file bundle. The GUI and DPAPI recovery run
as the original unelevated Windows user inside that VM; only the official
USBPcap installer and USBPcap's capture worker request UAC. There is no telemetry
or upload. Explicit Install USBPcap downloads one pinned, SHA-256-checked official
installer. Opening the guide opens a public page in the user's browser.
Python cannot guarantee erasure of all immutable secret copies in memory.
The read-only baseline display reports only Windows product/version/build and
Python version; it does not collect account identifiers or send a report.
An eligible missing-A2/chip82/A6 result with CONFIG90 present can offer one
explicit 60-second retry after the default 30-second attempt; each requires
fresh manual attachment to the VM and retains its own recording. No retry is
automatic. CONFIG90_MISSING requires a stop for capture-evidence review.
Lifecycle diagnostics contain only allowlisted process/status facts; arbitrary
child output and exception strings are not retained. Legacy device-material
acquisition is supported only through the qualified Windows VM; native or
bare-metal Windows acquisition is outside the supported workflow.

Report the software version, Fedora version, reader identity, exact command,
observed behavior and non-secret error text. Share only relevant redacted logs
when needed. Never attach device-material directories, firmware, OEM binaries,
raw USB captures, fingerprint images or templates.

The [validation page](VALIDATION.md) describes the current support limits.
