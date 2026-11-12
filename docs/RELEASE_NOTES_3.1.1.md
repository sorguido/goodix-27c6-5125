<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix Manager 3.1.1 — Diagnostic Center (draft)

A new **Diagnostic Center** helps you understand the state of your installation
and prepare useful information when something goes wrong.

- Guided system checks explain the available findings and missing information.
- Focused reports include a privacy notice and a local preview before sharing.
- An optional reader test asks for separate consent and uses an enrolled finger.
- Improved icons make the checks and actions easier to recognize.
- **Report a bug** opens the guided GitHub bug report form.

Diagnostics do not change the reader's normal operation. Reports stay local until
you choose to share them. The Manager does not repair your system automatically
or guarantee a successful fingerprint sign-in.

This is an unpublished draft prepared for maintainer evaluation. The build
baseline is Fedora 44 x86_64. Offline checks do not establish real-device,
installation, login or Fedora 45 qualification for this revision. Earlier-version
functional observations remain separate; see [validation](VALIDATION.md).

When a release is published, use the signed RPM and follow the
[installation and signature-verification guide](INSTALLATION.md). Installing the
Manager RPM alone does not activate the driver or change authentication settings.
