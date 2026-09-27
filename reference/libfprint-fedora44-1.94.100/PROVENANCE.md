<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Fedora 44 libfprint source provenance

This directory is based on the source for Fedora package
`libfprint-1.94.100-1.fc44.x86_64`:

- source RPM: `libfprint-1.94.100-1.fc44.src.rpm`
- source RPM SHA-256:
  `5daf6e5b492a2b493e36d0513bea0be324235a1452d69a791b28c6157df7963e`
- upstream archive: `libfprint-v1.94.100.tar.gz`
- archive SHA-256:
  `edc90e02f330a7595ceaf37f2c6ec32ed43541347fe936d3273b0bb2524fd19c`

The Fedora spec uses the upstream libfprint v1.94.100 archive and has no active
patch directives. `source/` includes downstream changes for the
`goodix_27c6_5125` driver, SIGFM print semantics, bounded enrollment and
verification, and the production-minimal Meson option. It is therefore not
byte-identical to the upstream archive.

Upstream and Fedora source files retain their original per-file copyright and
license notices. The downstream Goodix integration and imported components are
described in [Licensing and provenance](../../docs/LICENSING_AND_PROVENANCE.md).
