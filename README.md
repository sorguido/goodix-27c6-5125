<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 for Fedora KDE

A userspace fingerprint driver for the Goodix USB reader `27c6:5125` running
`GF_ST411SEC_APP_12509`. It connects a Goodix-enabled libfprint library to Fedora's
fprintd service and desktop authentication, preserving factory firmware, existing
keys and persistent reader state.

## Supported configuration

- Fedora 44 KDE, x86_64, with local user accounts.
- Goodix USB `27c6:5125`, firmware `GF_ST411SEC_APP_12509`.
- Fedora-provided fprintd, PAM, Plasma Login, KScreenLocker, sudo and PolicyKit.

Enrollment, verification, screen unlocking, ordinary sudo, PolicyKit and Plasma
fingerprint login have worked on the tested configuration. Evidence covers one
reader; see [validation and limitations](docs/VALIDATION.md). Physical installation
of the complete public installer still needs confirmation before a qualified release.

## Installation

**[Install using the single copy-paste block](docs/INSTALLATION.md).** The root
`install.sh` builds the runtime from this source tree, imports your materials,
and installs the login integration and removal commands. It requests normal
sudo authentication when needed. The reader stays connected throughout.

You need a working password login, administrative access, and your own valid
[five-file device-material bundle](docs/DEVICE_MATERIALS.md). If you do not
already have the bundle, that page contains the detailed acquisition reference
for deriving the five final files from the same reader and qualified OEM Windows
environment. Place the finished files in `$HOME/goodix-5125-materials/`, outside
the clone. The project does not distribute protected material or ship automated
acquisition/extraction tooling. Fedora prerequisites are included in the
installation guide's single block; separate build instructions are unnecessary.

## Using fingerprint authentication

Manage enrolled fingers through KDE's fingerprint settings. At Plasma Login,
a nonempty password uses ordinary password login immediately. Submitting an
empty password field explicitly selects fingerprint authentication, with at
most three attempts and a stop on the first match. Other consumers follow
Fedora's normal prompts where its current policy enables fingerprints; the
installer does not modify authselect or global PAM policy.

Keep password access available. Fingerprint login does not automatically unlock
a password-encrypted KWallet. No recognition accuracy or false-acceptance rate
is claimed for untested users or devices.

## Uninstall and emergency recovery

Run **`goodix-uninstall`** from a working desktop terminal. If graphical login
is unavailable, follow the [text-console emergency instructions](docs/UNINSTALL.md)
and run **`goodix-force-remove`**. Both commands request their own sudo
authentication, preserve materials and templates, and work after the clone is
removed. Leave the reader connected.

Removal exposes current Fedora configuration and finishes with a normal restart
instruction. It cannot repair an independently broken Fedora authentication stack.

## Device material and security

The installer copies the protected bundle into `/var/lib/goodix-5125-poc/`, sets
root-only permissions and applies the required SELinux labels. Keep materials,
fingerprint images, templates and raw USB captures out of source trees and
issue reports. [Security and privacy](docs/SECURITY.md) describes the boundary.

The supported path excludes flashing, firmware replacement, PSK provisioning,
OTP writes and persistent factory changes. Compatibility with every future Fedora
update, exhaustive Windows testing and broad independent hardware validation
remain unproven.

## Documentation

- [Installation and updates](docs/INSTALLATION.md)
- [Uninstall and emergency recovery](docs/UNINSTALL.md)
- [Technical architecture](TECHNICAL_MANUAL.md)
- [Device-specific material contract](docs/DEVICE_MATERIALS.md)
- [Security and privacy](docs/SECURITY.md)
- [Optional Fedora SELinux notification suppression](docs/SELINUX.md)
- [Validation scope and known limitations](docs/VALIDATION.md)
- [Licensing and provenance](docs/LICENSING_AND_PROVENANCE.md)
- [Upstream references](docs/REFERENCES.md)
- [Source build and offline checks](production/README.md)

## License and acknowledgements

Licensing is per file. The Goodix-enabled combined library is conveyed under
`GPL-3.0-or-later`; individual files retain their original notices and terms.
See [licensing and provenance](docs/LICENSING_AND_PROVENANCE.md) and
[acknowledgements](ACKNOWLEDGEMENTS.md).
