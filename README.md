<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 for Fedora KDE

Fingerprint driver for the Goodix USB reader `27c6:5125` running
`GF_ST411SEC_APP_12509` or `GF_ST411SEC_APP_12508`. It connects a Goodix-enabled
libfprint library to Fedora's fprintd service and desktop authentication,
initializing the reader by itself on first use while preserving factory firmware
and factory data.

<p align="center">
  <img src="https://n11scdn.akamaized.net/a1/375_535/11/58/59/10/IMG-8986381352341530689.webp" alt="Fingerprint reader and power-button flex assembly from a Huawei MateBook D15-family replacement part" width="50%">
</p>

## Supported configuration

- Fedora KDE on x86_64, release 44 or newer, with local user accounts (portable
  packaging candidate; tested biometric baseline remains Fedora 44).
- Goodix USB `27c6:5125`, recognized firmware `GF_ST411SEC_APP_12509` and
  `GF_ST411SEC_APP_12508`.
- Fedora-provided fprintd, PAM, Plasma Login, KScreenLocker, sudo and PolicyKit.

Within the supported Fedora 44 KDE scope, the project integrates enrollment,
verification, screen unlocking, ordinary sudo, PolicyKit, Plasma fingerprint
login and password fallback through Fedora's existing authentication stack.
An initial live functional check of the current driver passed on one APP12509
reader in a Fedora KDE VM, including enrollment, verification, authentication,
reboot, password fallback and bounded Windows coexistence. APP12508 has
contributor-reported evidence from the earlier driver on Ubuntu GNOME, not full
Fedora qualification for the current biometric engine. These observations do
not establish general recognition accuracy or cross-device compatibility. See
[validation and limitations](docs/VALIDATION.md).

## Installation

> [!WARNING]
> **Use only signed RPMs from official releases for installation.**

**[Install with the signed RPM and Goodix Manager](docs/INSTALLATION.md).**
Download the compatible RPM from the official releases, open it with **KDE Discover**,
then launch **Goodix Manager** and choose **Install**. The installation guide also
provides **optional signature-verification instructions** for users who want to
check the package before installing it.

You need administrative access. No Git checkout or local compilation is required.
After installing a newer RPM, reopen the Manager and choose **Apply Update** when
offered. Driver installation, update and removal use the local payload and work
offline once Fedora dependencies are installed.

Use a release explicitly labeled compatible with your Fedora version. The
existing published 3.0.0 RPM still requires Fedora 44; the portable 3.0.1
candidate is not published until its verification and VM tests pass.
Once qualified and published, install 3.0.1 on Fedora 44 before upgrading
to Fedora 45; no driver uninstall is needed. Existing 3.0.0 ChicagoHS
fingerprints do not need new enrollment for this update. See
[validation](docs/VALIDATION.md) for the RPM/Discover qualification boundary.

### Upgrading from an earlier release

Version 3.0.0 introduces the ChicagoHS biometric engine and a new stored
fingerprint format. For an intact, recognized 2.x installation, Goodix Manager
offers **Upgrade to 3.0.1** through the transactional installer, without a
preliminary uninstall. Host pairing state and existing fingerprint files are
preserved. **Previously enrolled fingers
must be enrolled again** because the old templates cannot be used by the new
engine. See [installation](docs/INSTALLATION.md) and
[validation](docs/VALIDATION.md). An optional return to an older version uses
a pinned historical release rather than the current `main` branch.

## Using fingerprint authentication

The first fingerprint action initializes the reader by itself. New enrollments
follow the current native twelve-stage policy; repositioning prompts may require
additional physical touches.

Manage enrolled fingers through KDE's fingerprint settings. At Plasma Login,
a nonempty password uses ordinary password login immediately. Submitting an
empty password field explicitly selects fingerprint authentication, with at
most three attempts and a stop on the first match. After selecting fingerprint,
allow roughly one second before touching the reader.

Keep password access available. Fingerprint login does not automatically unlock
a password-encrypted KWallet.

## Uninstall and emergency recovery

Choose **Remove** in Goodix Manager to remove the driver while keeping the
application available. The equivalent `goodix-uninstall` command remains
available from a working desktop terminal. Removing the Manager RPM itself
leaves an activated driver and its standalone recovery commands in place.
If graphical login is unavailable, follow the
[text-console emergency instructions](docs/UNINSTALL.md)
and run **`goodix-force-remove`**. Both commands request their own sudo
authentication, preserve host pairing state and templates, and work after
the clone is removed.

## Learn how it works

New to Linux fingerprint authentication? **[Goodix Behind the Scenes](docs/learning/README.md)**
is a beginner-friendly tour from the desktop prompt to the sensor, image,
template and final match decision. It uses diagrams and plain-language analogies;
the technical manual remains the canonical specification.

## Documentation

- [Contributing and pull-request policy](.github/CONTRIBUTING.md)
- [Beginner learning guide](docs/learning/README.md)
- [Installation and updates](docs/INSTALLATION.md)
- [Uninstall and emergency recovery](docs/UNINSTALL.md)
- [Technical architecture](TECHNICAL_MANUAL.md)
- [Security and privacy](docs/SECURITY.md)
- [Validation scope and known limitations](docs/VALIDATION.md)
- [Licensing and provenance](docs/LICENSING_AND_PROVENANCE.md)
- [Upstream references](docs/REFERENCES.md)
- [Source build and validation checks](production/README.md)

## License and acknowledgements

Licensing is per file. The Goodix-enabled combined library is conveyed under
`GPL-3.0-or-later`; individual files retain their original notices and terms.
See [licensing and provenance](docs/LICENSING_AND_PROVENANCE.md) and
[acknowledgements](ACKNOWLEDGEMENTS.md).
