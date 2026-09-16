<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Upstream references

## libfprint and fprintd

- libfprint: <https://gitlab.freedesktop.org/libfprint/libfprint>
- fprintd: <https://gitlab.freedesktop.org/libfprint/fprintd>
- Integrated libfprint version: 1.94.100
- Qualified Fedora fprintd version: 1.94.5-5.fc44

The repository contains the Fedora 44 libfprint source base needed to build the
downstream driver. fprintd remains supplied by Fedora and is not vendored.

## Rockytkg implementation reference

- Repository: <https://github.com/Rockytkg/goodix-linux-27c6-5125>
- Audited source commit: `227eba219fa9e3fbac5bd59aca79f624f67cd11b`
- Materialized libfprint fork commit used for SIGFM:
  `7ebe0c809b4d1df3400e84299a4ec4acdea84590`

Only the qualified SIGFM files and the adapted R2 preprocessing subset are
distributed here. The upstream firmware, provisioning, OTP, PSK, USB runtime,
and update paths are not part of this product.

## Standards and formats

- RFC 5246, TLS 1.2
- RFC 5487, TLS PSK cipher suites
- RFC 5288, AES-GCM cipher suites for TLS
- SPDX 2.3 JSON
- CRC-32/MPEG-2: polynomial `0x04c11db7`, init `0xffffffff`, non-reflected,
  xorout zero

## Fedora packaging

The build targets Fedora 44 packages and ABI. Package names, versions, and file
relationships in a prepared candidate are recorded by its SPDX SBOM. Pinned
OpenCV RPM names and SHA-256 values are in
`production/build-support/opencv-rpms.sha256`.
