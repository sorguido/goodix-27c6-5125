<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 for Fedora KDE

A userspace fingerprint driver for the Goodix USB reader `27c6:5125` running
`GF_ST411SEC_APP_12509`. It connects a Goodix-enabled libfprint library to
Fedora's own fprintd service and normal desktop authentication consumers.
The design preserves the reader's factory firmware, keys and persistent state.

## Supported configuration

- Fedora 44 KDE, x86_64, with local user accounts.
- Goodix USB `27c6:5125`, firmware `GF_ST411SEC_APP_12509`.
- Fedora-provided fprintd, PAM, Plasma Login, KScreenLocker, sudo and PolicyKit.
- A small optional Plasma Login integration for explicit fingerprint selection.

Enrollment, verification, screen unlocking, ordinary sudo, PolicyKit and Plasma
fingerprint login have worked on the tested configuration. Normal removal and
reinstallation have also been demonstrated. This is limited hardware evidence,
not certification for other readers, firmware, distributions or network accounts.
See [validation and limitations](docs/VALIDATION.md).

## Installation

**A finished public installer and supported update package are not available
in this source tree yet.** Read [installation status and prerequisites](docs/INSTALLATION.md)
before attempting deployment. The source implementation and its tests do not
constitute a complete public installation procedure.

You need an existing, valid [five-file device-material bundle](docs/DEVICE_MATERIALS.md)
for your own reader, a working password login and normal administrative access.
The project does not supply or create that protected bundle.

The reader stays connected and visible to the operating system during
installation, update, removal and recovery. Lifecycle tools must control
service activity in software; unplugging, disabling or hiding an integrated
reader is not part of the installation contract. The corrected lifecycle still
needs its remaining on-system validation before a public release.

## Using fingerprint authentication

Once a supported installation is available, enroll and manage fingerprints
through KDE or the standard fprintd tools. Follow the consumer's prompts and
stop on success. The Plasma Login integration uses a nonempty password for
ordinary password login; submitting an empty field explicitly selects a
fingerprint series with at most three attempts.

Password authentication remains a required fallback. Fingerprint login does
not unlock a password-encrypted KWallet automatically. No recognition accuracy
or false-acceptance rate is claimed for untested users or devices.

## Uninstall and emergency recovery

From a working desktop terminal, run `goodix-uninstall`. If graphical login is
unavailable, [the emergency instructions](docs/UNINSTALL.md) explain how to reach
a text console and run `goodix-force-remove`. Both commands request their own
normal sudo authentication and preserve device material and fingerprint templates.
They must already be installed; neither needs the source tree or build output.

Removal exposes the current Fedora configuration. It does not restore old Fedora
files or repair an independently broken operating system. The reader remains
connected. The console or sudo may offer fingerprint before a password prompt;
the recovery guide explains this stock behavior without promising an immediate
password selector.

## Device material and security

The runtime reads a reader-specific protected bundle from
`/var/lib/goodix-5125-poc/`. Do not attach that directory, fingerprint templates,
images, firmware, OEM binaries or raw USB captures to issue reports.

The implementation excludes flashing, firmware replacement, PSK provisioning,
OTP writes and persistent factory changes. [Security and privacy](docs/SECURITY.md)
describes the boundary and its limits. Compatibility with every future Fedora
update, complete Windows compatibility testing and broad independent hardware
validation are not established.

## Documentation

- [Installation and update availability](docs/INSTALLATION.md)
- [Uninstall and emergency recovery](docs/UNINSTALL.md)
- [Technical architecture](TECHNICAL_MANUAL.md)
- [Device-specific material contract](docs/DEVICE_MATERIALS.md)
- [Security and privacy](docs/SECURITY.md)
- [Validation scope and known limitations](docs/VALIDATION.md)
- [Licensing and provenance](docs/LICENSING_AND_PROVENANCE.md)
- [Upstream references](docs/REFERENCES.md)
- [Build and offline checks](production/README.md)
- [Source publication boundary](PUBLICATION_MANIFEST.md)

## License and acknowledgements

Licensing is per file. The Goodix-enabled combined library is distributed under
`GPL-3.0-or-later`; individual files retain their original notices and terms.
See [licensing and provenance](docs/LICENSING_AND_PROVENANCE.md) and
[acknowledgements](ACKNOWLEDGEMENTS.md).
