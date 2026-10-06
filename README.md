<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 for Fedora KDE

Fingerprint driver for the Goodix USB reader `27c6:5125` running
`GF_ST411SEC_APP_12509`. It connects a Goodix-enabled libfprint library to Fedora's
fprintd service and desktop authentication, initializing the reader by itself on
first use while preserving factory firmware and factory data.

## Supported configuration

- Fedora 44 KDE, x86_64, with local user accounts.
- Goodix USB `27c6:5125`, firmware `GF_ST411SEC_APP_12509`.
- Fedora-provided fprintd, PAM, Plasma Login, KScreenLocker, sudo and PolicyKit.

Within the supported Fedora 44 KDE scope, the project integrates enrollment,
verification, screen unlocking, ordinary sudo, PolicyKit, Plasma fingerprint
login and password fallback through Fedora's existing authentication stack.
Qualification is limited to the documented target and one reader; see
[validation and limitations](docs/VALIDATION.md).

## Installation

> [!WARNING]
> **Use only official releases or the `main` branch for installation.**

**[Install using the single copy-paste block](docs/INSTALLATION.md).** The root
`install.sh` automatically selects first installation (`FIRST_INSTALL`) or update
(`UPDATE`), builds the runtime from this source tree, and installs the login
integration and removal commands. It requests normal sudo authentication when
needed.

You need an administrative access. Git must be
available to run the bootstrap block.

After a successful installation, the repository clone may be removed.

## Using fingerprint authentication

The first fingerprint action initializes the reader by itself.

Manage enrolled fingers through KDE's fingerprint settings. At Plasma Login,
a nonempty password uses ordinary password login immediately. Submitting an
empty password field explicitly selects fingerprint authentication, with at
most three attempts and a stop on the first match. After selecting fingerprint,
allow roughly one second before touching the reader.

Keep password access available. Fingerprint login does not automatically unlock
a password-encrypted KWallet.

## Uninstall and emergency recovery

Run **`goodix-uninstall`** from a working desktop terminal. If graphical login
is unavailable, follow the [text-console emergency instructions](docs/UNINSTALL.md)
and run **`goodix-force-remove`**. Both commands request their own sudo
authentication, preserve host pairing state and templates, and work after
the clone is removed.

## Learn how it works

New to Linux fingerprint authentication? **[Goodix Behind the Scenes](docs/learning/README.md)**
is a beginner-friendly tour from the desktop prompt to the sensor, image,
template and final match decision. It uses diagrams and plain-language analogies;
the technical manual remains the canonical specification.

## Documentation

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
