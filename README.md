<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 for Fedora KDE

This project provides a source-built libfprint driver for the Goodix USB
fingerprint reader `27c6:5125` running firmware `GF_ST411SEC_APP_12509`. It
integrates with Fedora's standard `libfprint -> fprintd -> PAM/KDE` stack.

The supported configuration is intentionally narrow:

- Fedora 44 KDE on x86_64;
- Goodix USB `27c6:5125` / APP12509;
- local users and the Fedora-provided fprintd service;
- enrollment, verification, Plasma login, Plasma session unlock, `sudo`, and
  account-deletion protection.

Other Goodix devices, firmware revisions, distributions, desktop environments,
and network identities have not been qualified.

## Start here

1. Read [Installation](docs/INSTALLATION.md).
2. Read how the five [device-specific materials](docs/DEVICE_MATERIALS.md)
   originate and are validated.
3. Prepare the five pinned OpenCV RPMs used by the offline build.
4. Build a content-addressed candidate without privileges.
5. Import protected material that you legally obtained for the same physical
   reader.
6. Install the candidate through the managed installer.

The repository does not contain firmware, OEM DLLs, transport secrets,
fingerprint images, templates, private captures, or factory data. It does not
provide firmware flashing, IAP, ClearApp, OTP access, PSK provisioning, or a
cross-device material migration path.

## Documentation

- [Installation, update, rollback, and recovery](docs/INSTALLATION.md)
- [Device-specific material](docs/DEVICE_MATERIALS.md)
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
