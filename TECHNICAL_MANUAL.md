<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Technical manual

## Product boundary

The driver supports one qualified target: Goodix USB `27c6:5125` with
`GF_ST411SEC_APP_12509`, on Fedora 44 KDE x86_64. The runtime supplies a paired libfprint, fprintd and Plasma-login PAM module.
Fedora's service, D-Bus policy, storage and ordinary consumer interfaces remain
in use; the greeter/login pair additionally uses private PrepareLogin and
ClaimLogin methods.

```text
KDE / PAM / sudo
        |
     fprintd
        |
patched libfprint 1.94.100
        |
Goodix APP12509 driver
        |
     USB reader
```

## Source and runtime composition

`reference/libfprint-fedora44-1.94.100/source/` contains the Fedora 44
libfprint base with the bounded integration changes required by this driver.
`libfprint-driver/` contains the target-specific transport, secure-session,
image, enrollment, and lifecycle implementation. The four SIGFM source files
under `Rockytkg/libfprint/libfprint/sigfm/` provide the qualified matcher.

`production/` is the build authority. It verifies the hash-pinned 62-file
target-specific source set and builds the library in a network-isolated Flatpak
SDK. It also stages the pinned upstream fprintd 1.94.5 source, applies the
reviewable `production/login/fprintd.patch`, cleanup correction and
`fprintd-attempts.patch`, then builds the daemon, PAM module
and greeter parent. Those sources are independent of private history and
development overlays. `deployment/managed-install/` prepares, installs, updates, rolls back, and
removes immutable runtime versions.

## Runtime lifecycle

The fprintd systemd drop-in starts a small wrapper. The wrapper validates the
active runtime link and root-only protected-material set, then launches the paired
`current/fprintd` with an `LD_LIBRARY_PATH` limited to the selected runtime
and `FP_DRIVERS_ALLOWLIST=goodix_27c6_5125`.

The driver uses bounded asynchronous USB transfers through libfprint. It owns a
single action at a time, prevents implicit sensor-reaching retries, and releases
the device on cancellation or terminal completion. Ordinary verification permits up to
three physical attempts at the PAM/KDE layer and stops on the first match.
Prepared login permits up to three physical attempts under one ClaimLogin,
with an 8-second PAM bound per attempt and immediate stop on MATCH. Only a
clean NO MATCH plus complete finger release permits another explicit VerifyStart;
errors/timeouts stop immediately. Three NO MATCH results end fingerprint and
leave password fallback. This extension is validated offline, pending live confirmation. No automatic re-preparation.


## Preparation before interactive login

The user service `plasma-login.service` starts the small GIO parent instead of
starting the Qt greeter directly. It requests PrepareLogin and retains its
D-Bus connection while the unchanged vendor greeter runs. Only the Fedora
`plasmalogin` UID may prepare; root PAM uses ClaimLogin with the ordinary
username/PolicyKit checks. Login preparation opens the reader once and executes
the existing secure/TLS/FDT sequence. READY requires decoded baseline `20` and
the first acknowledged `0x32`, with the receiver and session still alive.

After Enter, Verify/Identify attaches to that same session without another
bootstrap, calibration or reopen. Image command `0x22`, feature extraction and
matching remain behind the explicit authentication action. A contact before
Verify invalidates readiness without an image. Preparation is bounded to 10 s,
READY to 120 s; the helper waits at most 2 s for device lookup plus 12 s for
preparation before exposing password login. Timeout, cancellation, suspend,
removal and greeter exit drain/close the preparation. Daemon restart, resume
and hotplug do not silently prepare again.

Ordinary Claim (including sudo) remains separate and can run once the previous
open is closed, even during Plasma's delayed greeter exit. Enrollment remains
on its ordinary path; ClaimLogin cannot enroll. KScreenLocker continues to use
Fedora's ordinary PAM module and the existing managed three-attempt rule.

The architecture was physically validated in the historical prototype; the
canonical candidate is validated offline here. Loader policy remains the
canonical per-reader manifest contract, not the prototype's old fixed loader.
Unchanged prototype hashes cover the greeter and base fprintd patch. The
three-attempt driver/lifecycle delta and separate fprintd-attempts patch are
pinned as current sources, without claiming prototype byte equivalence. A separately reviewable two-line guard prevents preparation
from starting after suspend/abandon while an asynchronous open was pending;
the private-bus regression fails on the prototype and passes with this guard.
The successful READY-to-Verify path is unchanged; it is not a byte-identity claim for the complete runtime.

## Secure session and protected material

The reader uses a TLS 1.2 PSK session carried in Goodix B0 frames. The host is
the TLS server; the reader is the client. The qualified cipher suite is
`PSK-AES128-GCM-SHA256` and the client identity is `Client_identity`.

The runtime requires five root-owned files in `/var/lib/goodix-5125-poc/`:

- `target-material-manifest.json`;
- `transport-material.bin`;
- `target-config-90.bin`;
- `gfusb.dll`;
- `fdt-cache.bin`.

The reader-specific values must describe the same physical device, and the OEM
DLL must match the qualified compatibility boundary. The repository never
embeds or logs protected material. The loader requires a root-owned mode-0700
directory and regular mode-0600 files, rejects symlinks, and validates format,
fixed sizes, digests and cross-material bindings before use. The material
contract is documented in [Device-specific material](docs/DEVICE_MATERIALS.md).

Acquisition, extraction, recovery and generation of a fresh five-file material
bundle are outside the supported release scope. The public source consumes a
pre-existing valid bundle; it does not provide tooling for recovering OEM
secrets or deriving the bundle from Windows caches or USB captures.

## Image and biometric pipeline

An acquisition yields a 7,684-byte image record: 7,680 bytes of packed 12-bit
samples plus a CRC-32/MPEG-2 trailer. Decoding produces an owned 80x64 raster.
The pipeline applies the qualified R2 preprocessing stage and uses SIGFM for
feature extraction, enrollment template construction, serialization, and
matching.

Enrollment is bounded to eight accepted physical samples. Samples that do not
add sufficient diversity are rejected without advancing the template. A
successful final sample is not reported complete until the terminal finger-up
event is observed. Verification performs one acquisition per explicit action;
the consumer decides whether another physical attempt is permitted.

Templates are stored by fprintd in its normal root-owned storage. They are not
placed in the source tree or build candidate. Removing the managed runtime does
not delete templates or protected material.

## Desktop and PAM integration

The installer preserves Fedora package ownership and password fallback:

- Plasma Login Manager receives an `/etc/pam.d/plasmalogin` override generated
  from the verified vendor file, using the paired absolute-path PAM module; `/usr/lib/pam.d/plasmalogin` is unchanged.
- `/etc/pam.d/kde-fingerprint`, a `plasma-workspace` configuration file, is
  transformed by replacing only its authentication substack with a bounded
  `pam_fprintd` rule.
- authselect and the global `fingerprint-auth` stack are not modified.

Original and managed PAM files are hash-pinned in the install state. Package
drift, local edits, `.rpmnew`, `.rpmsave`, collisions, or unexpected metadata
cause the transaction to fail closed.

## Managed filesystem layout

```text
/usr/lib64/goodix-27c6-5125/<source-commit>/   immutable runtime
/usr/lib64/goodix-27c6-5125/current           active symlink
/usr/libexec/goodix-27c6-5125/fprintd-wrapper
/etc/systemd/system/fprintd.service.d/99-goodix-27c6-5125-managed.conf
/etc/systemd/user/plasma-login.service.d/99-goodix-login-greeter.conf
/var/lib/goodix-27c6-5125-managed/            state and PAM recovery copies
/var/lib/goodix-5125-poc/                     protected device material
```

Each runtime version includes the driver libraries, fprintd, PAM and greeter.
SELinux labels of the new daemon, greeter and PAM are copied from their Fedora
equivalents. The existing owned SELinux module also records these exact
versioned-path labels so a full relabel preserves them; no new permission
grants are introduced. The existing
account-delete hook/policy remains included. The installer retains at most one
previous runtime for rollback. Uninstall
restores the Fedora fprintd and PAM configuration while deliberately preserving
protected material and fprintd templates.

## Safety invariants

The supported path does not flash firmware, enter IAP, invoke ClearApp, read or
write OTP, provision a PSK, replace factory data, or intentionally change a
persistent device mode. Unknown commands and unexpected protocol states fail
closed. The Windows factory path is expected to remain usable.

## Known limitations

- Only the target configuration listed above is supported.
- A valid five-file protected-material bundle is a prerequisite. Acquisition or
  construction of that bundle is not provided or supported by this release.
- Reader-to-reader portability of independently prepared valid bundles remains
  a qualification boundary; the runtime is device-dynamic but broad field
  validation on independent hardware has not been completed.
- No universal FAR or FRR claim is made.
- Passwordless biometric login does not unlock a password-encrypted KWallet;
  a separate wallet prompt can therefore be expected.
- Fedora package changes to PAM layout or pinned build dependencies require a
  reviewed update rather than an automatic bypass.

## Per-reader material portability

Production material policy is device-dynamic. The protected v1 manifest binds
the user's transport, CONFIG90 and FDT cache digests plus A2/chip82/OTP response
digests. E4 and DAC values are derived from the validated bundle. Universal
format, finalizer, CRC, OEM-DLL compatibility and filesystem controls remain
fixed. The v1 parser accepts only the ten required string fields, rejects
unknown or duplicate keys, embedded NUL, malformed separators, missing fields
and trailing data. See `docs/DEVICE_MATERIAL_PIN_AUDIT.md`.
