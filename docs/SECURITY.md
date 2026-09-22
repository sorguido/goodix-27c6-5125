<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Security and privacy

> **Current release boundary — 22 September 2026.** The device/privacy
> constraints below remain applicable. Managed installation, saved PAM copies
> and account-deletion hooks describe the **HISTORICAL_ONLY /
> REJECTED_ARCHITECTURE** candidate, not the active release. Follow the
> [distro-decoupled roadmap](../ROADMAP_DISTRO_DECOUPLED_RELEASE.md).
> The private workspace contains protected historical material and must never
> be published as a source export; the source-only claim below concerns the
> intended audited public surface.

## Device preservation

The supported runtime is designed to preserve factory firmware and persistent
state. It excludes firmware flashing, IAP, ClearApp, OTP access, PSK
provisioning, factory-data writes, and unknown command families. Unexpected
protocol states, unrecognized responses, and unbounded retries fail closed.

## Protected material

Transport material is device-specific and secret. It is stored only under
`/var/lib/goodix-5125-poc` as root-owned mode-0600 regular files inside a
root-owned mode-0700 directory. The loader rejects symlinks, metadata drift,
wrong sizes, and wrong hashes. Sensitive intermediate buffers are cleansed.

The source repository and release candidate contain no real transport secret,
OEM DLL, firmware, fingerprint sample, biometric template, factory data, or
private USB capture. Debug output must never include these values.

## Biometric data

Decoded images exist only in process memory during an action. Enrollment
templates are serialized through libfprint and stored by fprintd in its normal
root-owned data directory. The managed installer neither exports nor purges
them. Delete enrolled fingers through KDE or fprintd before deleting an
account; the installed account-deletion hook blocks removal while that user's
fingerprint namespace is non-empty.

## Host integration

The installer uses narrow root transactions, validates all candidate hashes,
and records the active source commit. It does not overwrite Fedora's vendor
`plasmalogin` file. PAM recovery copies and runtime versions are hash-pinned.
SELinux policy is installed only for the account-deletion hook.

## Reporting a problem

Share source version, exact error text, sanitized service status, and a
redacted journal excerpt. Do not share protected-material directories,
fingerprint storage, raw USB traffic, OEM binaries, firmware, images, or
templates.
