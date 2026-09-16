<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Technical manual

## Product boundary

The driver supports one qualified target: Goodix USB `27c6:5125` with
`GF_ST411SEC_APP_12509`, on Fedora 44 KDE x86_64. The runtime replaces only the
libfprint library used by Fedora's existing fprintd daemon. Applications and
PAM consumers continue to use standard fprintd interfaces.

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
SDK. `deployment/managed-install/` prepares, installs, updates, rolls back, and
removes immutable runtime versions.

## Runtime lifecycle

The fprintd systemd drop-in starts a small wrapper. The wrapper validates the
active runtime link and root-only protected-material set, then launches Fedora's
`/usr/libexec/fprintd` with an `LD_LIBRARY_PATH` limited to the selected runtime
and `FP_DRIVERS_ALLOWLIST=goodix_27c6_5125`.

The driver uses bounded asynchronous USB transfers through libfprint. It owns a
single action at a time, prevents implicit sensor-reaching retries, and releases
the device on cancellation or terminal completion. Verification permits up to
three physical attempts at the PAM/KDE layer and stops on the first match.

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

They must belong to the same physical device and be obtained lawfully from its
OEM Windows environment. The repository never embeds or logs their contents.
The loader requires a root-owned mode-0700 directory and regular mode-0600
files, rejects symlinks, and validates fixed sizes and digests before use.
Their individual origins, transformations, formats, and handling rules are
documented in [Device-specific material](docs/DEVICE_MATERIALS.md).

The public helper tools under `tools/device-materials/` cover the Windows DPAPI
transport export, Linux `G5125XFR` → `G5125POC` finalization, and offline
CONFIG90 extraction from a user-supplied USBPcap `.pcapng` capture. These tools
never provision a new PSK and the CONFIG90 extractor has no USB/device access.

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
  from the verified vendor file; `/usr/lib/pam.d/plasmalogin` is unchanged.
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
/var/lib/goodix-27c6-5125-managed/            state and PAM recovery copies
/var/lib/goodix-5125-poc/                     protected device material
```

The installer retains at most one previous runtime for rollback. Uninstall
restores the Fedora fprintd and PAM configuration while deliberately preserving
protected material and fprintd templates.

## Safety invariants

The supported path does not flash firmware, enter IAP, invoke ClearApp, read or
write OTP, provision a PSK, replace factory data, or intentionally change a
persistent device mode. Unknown commands and unexpected protocol states fail
closed. The Windows factory path is expected to remain usable.

## Known limitations

- Only the target configuration listed above is supported.
- The repository ships helper tooling for preparing transport material and for
  extracting CONFIG90 from a local OEM USB capture, but it does not ship OEM
  binaries, caches, captures, secrets or factory material. Users must lawfully
  obtain those inputs from their own reader/environment.
- The public repository form is substantially tested but has not yet been
  exercised completely across every acquisition, installation and recovery
  path on independent hardware. In particular, reader-to-reader portability of
  newly extracted CONFIG90 material remains a separate qualification boundary.
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
fixed. See `docs/DEVICE_MATERIAL_PIN_AUDIT.md`.
