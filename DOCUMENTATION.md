<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Documentation index

This page is the complete thematic index for the Goodix `27c6:5125` Fedora KDE
project.

## Quick access

| I want to... | Go to |
| --- | --- |
| Understand what this project supports | [Project overview](README.md) |
| Install, update, or reinstall the driver | [Installation and updates](docs/INSTALLATION.md) |
| Understand what the driver writes to the reader | [Security and privacy](docs/SECURITY.md#factory-preserving-design) |
| Share the reader with Windows | [Using the reader with Windows](docs/INSTALLATION.md#using-the-reader-with-windows) |
| Remove the driver normally | [Uninstall and emergency recovery](docs/UNINSTALL.md#normal-uninstall-from-a-working-desktop) |
| Recover when graphical login is unavailable | [Emergency recovery](docs/UNINSTALL.md#emergency-graphical-login-is-unavailable) |
| Learn how the whole system works without reading source code | [Goodix Behind the Scenes](docs/learning/README.md) |
| Review the implementation in technical detail | [Technical manual](TECHNICAL_MANUAL.md) |
| Check tested behavior and limitations | [Validation scope and known limitations](docs/VALIDATION.md) |
| Review security and privacy boundaries | [Security and privacy](docs/SECURITY.md) |
| Review licensing, origins, and upstream references | [Licensing and provenance](docs/LICENSING_AND_PROVENANCE.md) |

---

## 1. Getting started, installation, and daily use

- **[Project overview](README.md)** — Supported hardware and software, installation
  entry point, authentication behavior, removal, security boundaries, and links to
  the main documentation.
- **[Installation and updates](docs/INSTALLATION.md)** — Supported installation,
  update, and reinstall procedure, prerequisites, first-use initialization,
  installer behavior, and Windows coexistence.
- **[Login, lock screen, sudo, and PolicyKit](docs/learning/08_desktop_authentication.md)** —
  User-facing explanation of how the same fingerprint stack appears in Plasma
  Login, KScreenLocker, `sudo`, PolicyKit, and KDE enrollment settings.
- **[What is stored, and where](docs/learning/09_what_is_stored.md)** — Where
  persistent reader state, host pairing state, and enrolled fingerprint
  templates live.

## 2. Removal, recovery, and troubleshooting

- **[Uninstall and emergency recovery](docs/UNINSTALL.md)** — Normal removal,
  text-console emergency recovery, preserved data, removal scope, and restart
  requirements.
- **[Standalone removal commands](deployment/recovery/README.md)** — Technical
  overview of the installed `goodix-uninstall` and `goodix-force-remove`
  commands, their ownership model, and their offline tests.
- **[Technical manual — troubleshooting and diagnostic principles](TECHNICAL_MANUAL.md#20-troubleshooting-and-diagnostic-principles)** —
  Diagnostic boundaries and implementation-level troubleshooting guidance.
- **[Validation scope and known limitations](docs/VALIDATION.md)** — Known
  limitations and qualification boundaries that should be checked before
  treating unexpected behavior as a defect.
- **[Security and privacy](docs/SECURITY.md)** — Includes the supported problem
  reporting boundary and what private material must never be attached to reports.

## 3. Goodix Behind the Scenes — beginner learning guide

**[Goodix Behind the Scenes](docs/learning/README.md)** is the guided,
plain-language learning path. It is educational documentation, not the canonical
technical specification.

1. **[A two-minute tour](docs/learning/01_what_are_we_building.md)** — The complete
   fingerprint journey on one page.
2. **[From Fedora to the sensor](docs/learning/02_from_fedora_to_the_sensor.md)** —
   KDE, PAM, D-Bus, fprintd, libfprint, the driver, USB, and the physical reader.
3. **[Preparing a tiny computer](docs/learning/03_preparing_the_sensor.md)** —
   Device preparation, identity checks, first-use pairing, runtime setup, TLS,
   and finger detection.
4. **[From finger detection to image](docs/learning/04_from_finger_to_image.md)** —
   Finger detection, capture, TLS-protected image transport, decoding, and release.
5. **[From image to fingerprint template](docs/learning/05_from_image_to_template.md)** —
   Image preprocessing, SIGFM features, descriptors, and template samples.
6. **[Enrollment](docs/learning/06_enrollment.md)** — Multiple contacts,
   fixed-21 acceptance, quality retries, diversity diagnostics, and host-side
   template creation.
7. **[Verification and matching](docs/learning/07_verification_and_matching.md)** —
   MATCH, NO MATCH, retry, cancellation, and comparison behavior.
8. **[Login, lock screen, sudo, and PolicyKit](docs/learning/08_desktop_authentication.md)** —
   How different Fedora/KDE authentication consumers use the same fingerprint stack.
9. **[What is stored, and where](docs/learning/09_what_is_stored.md)** — Reader
   state, host pairing state, and Fedora fingerprint templates.
10. **[Safety and factory preservation](docs/learning/10_safety_and_factory_preservation.md)** —
    Why Linux support does not require flashing, reprovisioning, or persistent
    factory changes.
11. **[Glossary](docs/learning/glossary.md)** — Plain-English definitions of the
    main Linux, USB, Goodix, security, and biometric terms.

### Optional protocol deep dive

- **[Appendix — The real Goodix conversation](docs/learning/appendix_real_goodix_conversation.md)** —
  Plain-English explanation of the `A8`, `E4`, `A2`, `82`, `A6`, `D1`, `D4`,
  `AF`, FDT, and related protocol phases.

## 4. Canonical technical reference

**[Goodix USB 27c6:5125 technical manual](TECHNICAL_MANUAL.md)** is the
authoritative public technical reference for the current implementation.

### Hardware, architecture, and protocol

- [Purpose and support scope](TECHNICAL_MANUAL.md#1-purpose-and-support-scope)
- [Hardware and device identity](TECHNICAL_MANUAL.md#2-hardware-and-device-identity)
- [System architecture and ownership](TECHNICAL_MANUAL.md#3-system-architecture-and-ownership)
- [libfprint driver architecture](TECHNICAL_MANUAL.md#4-libfprint-driver-architecture)
- [Host pairing state and secure transport](TECHNICAL_MANUAL.md#5-host-pairing-state-and-secure-transport)
- [Device initialization and secure-session lifecycle](TECHNICAL_MANUAL.md#6-device-initialization-and-secure-session-lifecycle)

### Capture and biometrics

- [Finger detection, capture, release, and cancellation](TECHNICAL_MANUAL.md#7-finger-detection-capture-release-and-cancellation)
- [Image decoding and preprocessing](TECHNICAL_MANUAL.md#8-image-decoding-and-preprocessing)
- [SIGFM extraction, serialization, and matching](TECHNICAL_MANUAL.md#9-sigfm-extraction-serialization-and-matching)
- [Enrollment, verification, and identification](TECHNICAL_MANUAL.md#10-enrollment-verification-and-identification)
- [Templates, storage, and multi-user behavior](TECHNICAL_MANUAL.md#11-templates-storage-and-multi-user-behavior)

### Fedora integration

- [fprintd integration](TECHNICAL_MANUAL.md#12-fprintd-integration)
- [Authentication consumers](TECHNICAL_MANUAL.md#13-authentication-consumers)
- [SELinux and host integration](TECHNICAL_MANUAL.md#14-selinux-and-host-integration)
- [Build and runtime dependencies](TECHNICAL_MANUAL.md#15-build-and-runtime-dependencies)

### Lifecycle, safety, and maintenance

- [Installation, update, and rollback](TECHNICAL_MANUAL.md#16-installation-update-and-rollback)
- [Removal and emergency recovery](TECHNICAL_MANUAL.md#17-removal-and-emergency-recovery)
- [Factory preservation, security, and privacy](TECHNICAL_MANUAL.md#18-factory-preservation-security-and-privacy)
- [Qualification and known limitations](TECHNICAL_MANUAL.md#19-qualification-and-known-limitations)
- [Troubleshooting and diagnostic principles](TECHNICAL_MANUAL.md#20-troubleshooting-and-diagnostic-principles)
- [Developer invariants, licensing, and references](TECHNICAL_MANUAL.md#21-developer-invariants-licensing-and-references)

## 5. Security, qualification, and compatibility boundaries

- **[Security and privacy](docs/SECURITY.md)** — Factory-preserving design,
  protected inputs, biometric data, host authentication boundary, SELinux
  considerations, privacy, and reporting rules.
- **[Validation scope and known limitations](docs/VALIDATION.md)** — Tested
  configuration, live and offline evidence, qualification boundary, and known
  limitations.
- **[Safety and factory preservation](docs/learning/10_safety_and_factory_preservation.md)** —
  Beginner-oriented explanation of the same design principles.

## 6. Implementation and maintainer documentation

These pages document individual implementation components. Ordinary users do
not need them for installation or daily use.

- **[Goodix libfprint driver sources](libfprint-driver/README.md)** — Scope of
  the target-specific driver source, USB/TLS/pairing-state/image/enrollment pieces,
  licensing notes, and synthetic test entry points.
- **[Plasma Login fingerprint selection](deployment/plasma-login-opt-in/README.md)** —
  Minimal PAM selector used by Plasma Login and its synthetic dispatch tests.
- **[Standalone removal commands](deployment/recovery/README.md)** — Implementation
  and test boundary of the installed normal and emergency removal tools.
- **[Public source build](production/README.md)** — Build architecture, payload
  composition, source ledger, validation boundary, and maintainer checks.

### Source and build provenance

- **[Source ledger](production/source-files.tsv)** — Production source paths,
  licenses, and origins.
- **[Source-file digests](production/source-files.sha256)** — Matching hashes for
  the production source ledger.
- **[Fedora 44 libfprint source provenance](reference/libfprint-fedora44-1.94.100/PROVENANCE.md)** —
  Fedora source RPM and upstream archive hashes plus the downstream modification
  boundary.

## 7. Licensing, provenance, acknowledgements, and external references

- **[Licensing and provenance](docs/LICENSING_AND_PROVENANCE.md)** — Component
  origins, per-file licensing, combined-library terms, source provenance, and
  excluded private material.
- **[Upstream references](docs/REFERENCES.md)** — libfprint, fprintd, Linux-PAM,
  Plasma Login, Rockytkg, TLS RFCs, OpenCV, and related upstream references.
- **[Acknowledgements](ACKNOWLEDGEMENTS.md)** — Upstream projects, contributors,
  references, and development-tool acknowledgement.
- **[Repository license](LICENSE)** — Repository-level licensing notice.
- **[`LICENSES/`](LICENSES/)** — Full license texts distributed with the source.

## 8. Vendored upstream reference documentation

The following Markdown files are part of the vendored libfprint source reference.
They are **upstream documentation**, not project-specific Goodix instructions.
They are listed here for completeness and should not be confused with the
canonical documentation above.

- **[Upstream libfprint README](reference/libfprint-fedora44-1.94.100/source/README.md)**
- **[Upstream libfprint HACKING guide](reference/libfprint-fedora44-1.94.100/source/HACKING.md)**
- **[Upstream libfprint code of conduct](reference/libfprint-fedora44-1.94.100/source/code-of-conduct.md)**

---

## Documentation roles at a glance

| Document | Role |
| --- | --- |
| [`README.md`](README.md) | Guided project entry point |
| [`DOCUMENTATION.md`](DOCUMENTATION.md) | Complete thematic navigation index |
| [`docs/learning/README.md`](docs/learning/README.md) | Beginner learning path |
| [`TECHNICAL_MANUAL.md`](TECHNICAL_MANUAL.md) | Canonical technical specification |
| [`docs/INSTALLATION.md`](docs/INSTALLATION.md) | Canonical installation/update procedure |
| [`docs/UNINSTALL.md`](docs/UNINSTALL.md) | Canonical removal/recovery procedure |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Security and privacy boundary |
| [`docs/VALIDATION.md`](docs/VALIDATION.md) | Qualification evidence and limitations |
| [`docs/LICENSING_AND_PROVENANCE.md`](docs/LICENSING_AND_PROVENANCE.md) | Licensing and source provenance |
