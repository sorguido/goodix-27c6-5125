<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 for Fedora KDE

A userspace fingerprint driver for the Goodix USB reader `27c6:5125` running
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

**[Install using the single copy-paste block](docs/INSTALLATION.md).** The root
`install.sh` automatically selects first installation (`FIRST_INSTALL`), update
(`UPDATE`) or reinstall (`REINSTALL`), builds the runtime from this source tree,
and installs the login integration and removal commands. It requests normal
sudo authentication when needed. The reader may be absent throughout these
host lifecycle operations.

You need a working password login and administrative access. A fresh installation
needs no Windows machine, no capture tooling and no private material bundle: it
creates the empty, root-only state-v2 location without opening USB, and the
reader may be absent. Fedora prerequisites are included in the installation flow;
separate build instructions are unnecessary. Git must be available to run the
bootstrap block.

An existing [five-file device-material bundle](docs/DEVICE_MATERIALS.md) remains
an optional compatibility source. If you supply one, stage it in
`$HOME/goodix-5125-materials/`, outside the clone. Its supported acquisition
environment is a qualified Windows VM with USB passthrough, the qualified Goodix
OEM driver, and the original Windows user/DPAPI context for that VM; the
recommended tool is the
[Goodix 5125 Material Builder](tools/windows_material_builder/README.md), and
native or bare-metal Windows acquisition is outside the supported workflow. The
manual acquisition reference remains available for audit and troubleshooting of
the same VM workflow. The project does not distribute protected material.

After a successful installation, the repository clone may be removed; a later run
of the same bootstrap block clones it again automatically. Ordinary updates and
reinstalls preserve `/var/lib/fprint/goodix-5125-state-v2/` and any validated
legacy set in `/var/lib/goodix-5125-poc/`, so the Home staging folder is not
technically required. Keep an independent secure backup of a legacy bundle while
that compatibility source is in use.

## Using fingerprint authentication

The first fingerprint action initializes the reader by itself. It confirms the
target identity, derives the configuration from the reader's own OTP, stores a
locally generated pairing key in root-only state-v2 and records it with a single
bounded pairing write. Ordinary later use reuses that stored key and writes
nothing to the reader.

Manage enrolled fingers through KDE's fingerprint settings. At Plasma Login,
a nonempty password uses ordinary password login immediately. Submitting an
empty password field explicitly selects fingerprint authentication, with at
most three attempts and a stop on the first match. After selecting fingerprint,
allow roughly one second before touching the reader. Other consumers follow
Fedora's normal prompts where its current policy enables fingerprints; the
installer does not modify authselect or global PAM policy.

Keep password access available. Fingerprint login does not automatically unlock
a password-encrypted KWallet. No recognition accuracy or false-acceptance rate
is claimed for untested users or devices.

## Learn how it works

New to Linux fingerprint authentication? **[Goodix Behind the Scenes](docs/learning/README.md)**
is a beginner-friendly tour from the desktop prompt to the sensor, image,
template and final match decision. It uses diagrams and plain-language analogies;
the technical manual remains the canonical specification.

## Uninstall and emergency recovery

Run **`goodix-uninstall`** from a working desktop terminal. If graphical login
is unavailable, follow the [text-console emergency instructions](docs/UNINSTALL.md)
and run **`goodix-force-remove`**. Both commands request their own sudo
authentication, preserve pairing state, materials and templates, and work after
the clone is removed. Removal does not access the reader, which may stay
connected or be absent.

Removal exposes current Fedora configuration and finishes with a normal restart
instruction. It cannot repair an independently broken Fedora authentication stack.

## Device material and security

The installer always creates or preserves root-only state-v2 under
`/var/lib/fprint/goodix-5125-state-v2/`. If a legacy bundle is supplied, it is
copied into `/var/lib/goodix-5125-poc/`, protected and retained side by side.
Subsequent runs validate and preserve an installed legacy set; invalid
installed material stops the operation without falling back to a Home copy. Keep materials,
fingerprint images, templates and raw USB captures out of source trees and
issue reports. [Security and privacy](docs/SECURITY.md) describes the boundary.

Discovery, enumeration, ordinary open, boot and an uninitialized login read no
protected material and claim no USB; only an explicit fingerprint action does,
and it runs a bounded read-only preflight before the secure session starts.

The supported path never flashes firmware, replaces the reader application,
writes OTP or factory data, or persistently changes VID:PID or mode. Its single
persistent reader mutation is the one host-pairing write above, which preserves
the reader's current `BB010002` byte-for-byte and is proven by readback and TLS
before use. Windows keeps working alongside Linux: when Windows replaces the
pairing, Linux restores the same stored key with one qualified write instead of
generating a new one. Compatibility with future Fedora releases, other Windows
VM/OEM configurations, and broader hardware remains outside the qualified scope.

## Documentation

- [Beginner learning guide](docs/learning/README.md)
- [Installation and updates](docs/INSTALLATION.md)
- [Uninstall and emergency recovery](docs/UNINSTALL.md)
- [Technical architecture](TECHNICAL_MANUAL.md)
- [Device-specific material contract](docs/DEVICE_MATERIALS.md)
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
