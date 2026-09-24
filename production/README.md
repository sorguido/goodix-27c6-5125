<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Public source build

Ordinary users install and update through the root `install.sh` using the
[documented installation procedure](../docs/INSTALLATION.md). No separate build
command, payload selection or maintainer tooling is required.

## Build architecture

`build-public.py` resolves the source root from its own location and builds as
an ordinary user on Fedora 44 x86_64. It uses the public libfprint base, Goodix
driver and SIGFM sources together with the supported Fedora development packages.
It does not require Git history, a branch name, a particular clone directory or
pre-existing build output.

The generated payload contains the Goodix-enabled libfprint runtime, the required
OpenCV libraries, the Plasma Login selector and PAM entry, the offline material
checker, license notices and source/build provenance. Fedora supplies fprintd,
libgusb, OpenSSL, PAM, Plasma and the ordinary authentication consumers.

The builder verifies the library ABI, dependency resolution, payload inventory
and content hashes before installation. OpenCV notices come from installed Fedora
RPM license files. Build provenance records the source-content digest and package
versions rather than depending on Git objects.

The [source ledger](source-files.tsv) and [matching digests](source-files.sha256)
record the public driver sources and their provenance. See
[Licensing and provenance](../docs/LICENSING_AND_PROVENANCE.md) for the combined
library's terms.

## Validation boundary

The public installer performs the checks needed for the supported installation
path. Additional development and regression analysis is not part of the end-user
procedure and is not required to install, use, update or remove the driver.

A successful source build does not by itself prove hardware behavior or every
Fedora authentication/SELinux path. The current tested scope and remaining limits
are documented in [Validation](../docs/VALIDATION.md).
