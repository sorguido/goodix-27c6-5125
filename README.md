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

## Validation status

The software and intended fingerprint workflows have been demonstrated working
on the qualified development system. The source, build, lifecycle and managed
integration paths have been tested extensively, including clean-system testing,
but the public repository form has **not yet been exercised completely across
every acquisition, installation and recovery path on independent hardware**.

In particular, some public helper workflows used to prepare reader-specific
material are newer than the core driver qualification and currently include
synthetic/offline tests plus bounded development evidence rather than broad
field validation.

If you encounter a reproducible problem, please open a GitHub issue with the
software version/commit, Fedora version, hardware identity, command used and
non-secret error output. Do **not** attach device secrets, OEM cache files,
private USB captures, fingerprint images, templates or other protected
material to an issue.

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
python3 tools/device-materials/Finalize-Goodix5125TransportMaterial.py --self-test
python3 tools/device-materials/Extract-Goodix5125Config90.py --self-test
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

Device-specific runtime material is validated against a manifest generated for
the user's own reader; development-reader hashes are not release acceptance
criteria. See `docs/DEVICE_MATERIALS.md`.
