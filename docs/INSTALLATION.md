<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Installation and updates

## Availability

**There is no finished public installer or supported update package in this
source tree yet.** The driver and its authentication integration have been
exercised on the supported configuration, but complete public packaging and
reader-present lifecycle qualification are still pending. Do not treat a
component build script as an end-user installer.

This page is the stable entry point for installation instructions. Exact package
names, acquisition links and installation/update commands will be added when a
reviewed release provides them. No unpublished build directory, workstation path
or laboratory procedure is required by a future public installation contract.

## Required configuration

- Fedora 44 KDE on x86_64, Goodix USB `27c6:5125`, firmware
  `GF_ST411SEC_APP_12509`, and a local user account.
- Fedora's fprintd, PAM, Plasma Login and normal authentication components.
- Working password login and ordinary administrative access.
- An existing valid [five-file device-material bundle](DEVICE_MATERIALS.md)
  belonging to the reader, with permission to use its OEM input.

Acquiring or constructing protected material is outside this project's supported
installation scope. Do not substitute material from another reader or generate
replacement keys. The project will not distribute those files.

## Reader-present operation

**Leave the reader connected and visible to the operating system.** Installation,
updates, normal removal, emergency removal and recovery-tool management must
work with an integrated reader. Unplugging, disabling, unbinding, blacklisting
or hiding the reader is not a supported prerequisite.

Close fingerprint settings and finish any authentication dialog before changing
software. Host lifecycle controls stop and quiesce fprintd when runtime files
must change. Lifecycle operations do not initiate fingerprint capture merely
because the reader is present and do not start fprintd as an installation test.
If the service cannot be safely quiesced, report the precise error; do not change
hardware visibility to bypass it.

## Installation and update expectations

The intended installation owns the Goodix library directory, one fprintd
library-environment drop-in, the minimal Plasma Login selector where needed,
and its removal tools. Fedora retains its daemon, greeter, password stack and
normal consumers. Existing templates and device material remain separate.

A public update must follow the same reader-present lifecycle and retain normal
password access. A complete public update command and package migration path
have not been delivered; none is implied by the presence of source components.
See [validation](VALIDATION.md) for what has actually been demonstrated.

## Existing installations

Installations that already include the removal tools can use
[`goodix-uninstall` or emergency recovery](UNINSTALL.md). These commands preserve
material and templates, and do not restore historical Fedora files. If a command
is absent, it has not been installed or was removed after successful cleanup;
this page does not offer a substitute download or unverified installation command.
