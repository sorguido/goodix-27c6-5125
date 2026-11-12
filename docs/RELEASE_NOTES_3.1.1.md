<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix Manager 3.1.1 — Diagnostic Center (draft)

A new **Diagnostic Center** helps you understand the state of your installation
and prepare useful information when something goes wrong.

- Guided system checks explain the available findings and missing information.
- Focused reports include a privacy notice and a local preview before sharing.
- An optional reader test asks for separate consent and uses an enrolled finger.
- Improved icons make the checks and actions easier to recognize.
- **Report a bug** opens the guided GitHub bug report form.

This candidate also improves everyday diagnostics:

- Start a **New test** after a safely completed reader-test session, with fresh consent.
- Choose a custom period using a calendar and local hours and minutes.
- Get reports focused on the selected problem, with clear messages when useful evidence is missing.
- Open Home at a height suited to its content, while keeping your manual window size during use.
- See clearer messages when system settings cannot be read; new installations create the service settings folder with the intended access.

Diagnostics do not change the reader's normal operation. Reports stay local until
you choose to share them. The Manager does not repair your system automatically
or guarantee a successful fingerprint sign-in.

This is an unpublished draft prepared for maintainer retesting. The build
baseline is Fedora 44 x86_64. Offline checks do not establish real-device,
installation, login or Fedora 45 qualification for this replacement package.
Earlier candidate observations remain separate; see [validation](VALIDATION.md).

When a release is published, use the signed RPM and follow the
[installation and signature-verification guide](INSTALLATION.md). Installing the
Manager RPM alone does not activate the driver or change authentication settings.
