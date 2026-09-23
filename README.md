<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 for Fedora KDE

**Removal and emergency recovery:** [Uninstall Goodix](docs/UNINSTALL.md).
If the desktop is inaccessible: **Ctrl+Alt+F3 → sign in → `goodix-force-remove`**.
The command requests sudo itself. Recovery commands must first be installed
as part of the current candidate; older R4 installations need the R5 bridge below.

**Current phase: R5 — Removal & Emergency Recovery Qualification.** R3 and R4
are closed on the tested Fedora VM baseline, including native Plasma fingerprint
login. Offline removal qualification and the [R5 VM procedure](deployment/recovery/R5_VM.md)
are the current work; live removal/reinstallation remains pending human execution.
R6 is not authorized and this is not a public release.

- [Current candidate installation](docs/R5_INSTALL.md)
- [Normal uninstall and one-command emergency removal](docs/UNINSTALL.md)
- [VM qualification and initial R4 recovery-tools bridge](deployment/recovery/R5_VM.md)
- [Canonical roadmap](ROADMAP_DISTRO_DECOUPLED_RELEASE.md)

The physical Fedora host remains the stock safety baseline. Installation and
runtime validation are VM-only. Device materials and fingerprint templates are
preserved by removal; current Fedora files are never restored from old copies.

## Historical product description

The following managed-candidate description and its installation links are
**HISTORICAL_ONLY / REJECTED_ARCHITECTURE**. They remain evidence, not the active
installation path. Use the current links above. Private fprintd/PAM, Plasma
binaries/greeter and custom sudo/PolicyKit integrations are excluded from R5.

This project provides a source-built libfprint driver for the Goodix USB
fingerprint reader `27c6:5125` running firmware `GF_ST411SEC_APP_12509`. It
integrates with Fedora's standard `libfprint -> fprintd -> PAM/KDE` stack.

The supported configuration is intentionally narrow:

- Fedora 44 KDE on x86_64;
- Goodix USB `27c6:5125` / APP12509;
- local users and the Fedora fprintd service with a source-built paired daemon/PAM extension;
- enrollment, verification, Plasma login, Plasma session unlock and
  account-deletion protection;
- service-local Polkit fingerprint integration prepared and checked offline, pending live validation.

Other Goodix devices, firmware revisions, distributions, desktop environments,
and network identities have not been qualified.

## Validation status

The early-login architecture was tested on the qualified target through the
prototype at `9671e02e19504e20e0097f598fa960f2c13e7a1e`: the user reported
successful cold login with immediate finger placement after Enter, password
login, sudo fingerprint authentication, and temporary-overlay rollback. No
deliberate delay was used; no sub-second timing measurement is claimed.

That behavior is now integrated into the canonical source/build/managed
candidate. This promotion is validated offline; the promoted managed candidate
has not been installed or exercised live as part of this task. Independent
hardware, full release migration/recovery qualification and publication remain
separate project boundaries. The clean managed candidate now owns service-local
sudo/sudo-i and Polkit fingerprint paths, validated offline and awaiting native
live acceptance. It uses no D285 dependency or global fingerprint change; the
development PC still uses its separate, untouched D285 PAM/sudoers path. See [Validation](docs/VALIDATION.md).

If you encounter a reproducible problem, please open a GitHub issue with the
software version/commit, Fedora version, hardware identity, command used and
non-secret error output. Do **not** attach device secrets, OEM cache files,
private USB captures, fingerprint images, templates or other protected
material to an issue.

## Start here

1. Read [Installation](docs/INSTALLATION.md).
2. Read the contract for the five [device-specific materials](docs/DEVICE_MATERIALS.md).
3. Prepare the pinned OpenCV and PAM/polkit header RPMs used by the offline build.
4. Build a content-addressed candidate without privileges.
5. Import a valid protected-material bundle that you legally obtained for the
   same physical reader.
6. Install the candidate through the managed installer.

The repository does not contain firmware, OEM DLLs, transport secrets,
fingerprint images, templates, private captures, or factory data. It does not
provide firmware flashing, IAP, ClearApp, OTP access, PSK provisioning, or a
cross-device material migration path.

**Device-material acquisition is outside the supported release scope.** The
project validates and consumes a pre-existing reader-specific five-file bundle,
but does not provide tooling for recovering OEM secrets, extracting USB
captures, or constructing a fresh bundle from a Windows installation. If you
do not already have a valid bundle for your reader, the supported installation
cannot proceed.

## Documentation

- [Installation, update, rollback, and recovery](docs/INSTALLATION.md)
- [Device-specific material contract](docs/DEVICE_MATERIALS.md)
- [Technical manual](TECHNICAL_MANUAL.md)
- [Security and privacy](docs/SECURITY.md)
- [Validation scope](docs/VALIDATION.md)
- [Licensing and provenance](docs/LICENSING_AND_PROVENANCE.md)
- [Upstream references](docs/REFERENCES.md)
- [Acknowledgements and development-tool disclosure](ACKNOWLEDGEMENTS.md)
- [Reproducible build](production/README.md)

## Build and test

The supported checks do not access USB hardware:

```bash
production/check-source.sh
python3 deployment/managed-install/test_offline.py
```

Build a candidate from a clean committed checkout:

```bash
deployment/managed-install/manage.sh prepare "$HOME/goodix-candidate"
```

See the installation guide before running any command that invokes `sudo` or
starts the real fprintd service.

## License

Licensing is per file. The distributed Goodix-enabled libfprint binary combines
GPL-compatible components and is conveyed under `GPL-3.0-or-later`; individual
source files keep their stated licenses. See the licensing and provenance
document and the texts in `LICENSES/`.

Device-specific runtime material is validated against a manifest for the
user's own reader; development-reader hashes are not release acceptance
criteria. See `docs/DEVICE_MATERIALS.md`.
