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

## Pairing state and biometric data

The only secret the project persists is the Linux pairing key it generates
locally on first use. It is stored with its authenticated receipt in two
crash-safe root-only generations under
`/var/lib/fprint/goodix-5125-state-v2/`; removal preserves this directory. The
key is never printed by the normal tools, never leaves the host, and never enters
the repository, the clone or build output. The C runtime state loader and
secure-session implementation cleanse their sensitive buffers.

Discovery, enumeration, ordinary open, boot and an uninitialized login do not
read pairing state or claim USB. Only an explicit libfprint action may
request runtime resources, and it first runs a bounded read-only preflight that
binds identity, application, chip profile, OTP, generated CONFIG90 and the live
validator. An action that cannot bind that evidence fails closed. The runtime
coordinator itself exposes no pairing write: the single `E0` is reachable only
through the separately bounded activation graph, which refuses a second write for
the same transaction and fails closed on an ambiguous post-write state.

Fingerprint images are processed in memory. Fedora fprintd stores enrolled
templates in `/var/lib/fprint/`. Removal preserves templates and host pairing
state; it does not export or purge them. Manage enrolled fingers using KDE or
fprintd, including before deleting an account where cleanup is needed. This
architecture does not install an account-deletion hook or promise automatic
template deletion.

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

The runtime ships no telemetry and performs no network access; its TLS traffic
terminates on the reader over USB through in-memory buffers. The only network use
in the documented flow is the Fedora package manager during installation, plus
the public `git clone`/`pull` that the bootstrap block runs as your normal user.
Normal-level journal messages can contain biometric-derived metadata such as
keypoint counts and per-sample match outcomes, so treat journal exports as
sensitive and redact them to the minimum a report needs.

Report the software version, Fedora version, reader identity, exact command,
observed behavior and non-secret error text. Share only relevant redacted logs
when needed. Never attach the host pairing state directory, firmware, raw USB
captures, fingerprint images or templates.

The [validation page](VALIDATION.md) describes the current support limits.
