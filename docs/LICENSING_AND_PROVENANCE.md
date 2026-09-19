<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Licensing and provenance

Licensing is per file. No directory name changes the license or copyright of
the source it contains.

## Distributed components

| Component | Origin | Version or commit | License | Local use |
| --- | --- | --- | --- | --- |
| libfprint base | Fedora 44 source package / upstream libfprint | 1.94.100 | Per-file upstream terms, predominantly `LGPL-2.1-or-later` | Patched base and public ABI |
| Goodix driver sources | This project | current source tree | Per-file SPDX; predominantly `LGPL-2.1-or-later` | USB, TLS, image, lifecycle, enrollment, and matching integration |
| SIGFM | Rockytkg materialized libfprint fork | `7ebe0c809b4d1df3400e84299a4ec4acdea84590` | `LGPL-2.1-or-later` | Feature extraction and matching |
| R2 preprocessing | Adapted from Rockytkg `goodix_imgproc` | `227eba219fa9e3fbac5bd59aca79f624f67cd11b` | `GPL-2.0-or-later` | Image preprocessing |
| OpenCV | Fedora 44 packages | 4.13.0-1.fc44 | Fedora expression `BSD-3-Clause AND Apache-2.0 AND ISC` | Bundled runtime libraries |
| libgusb | Fedora 44 package | 0.4.9-5.fc44 | `LGPL-2.1-or-later` | Bundled runtime library |
| OpenSSL | Fedora 44 system library | host version | Apache-2.0 | TLS implementation |

The exact target-specific compilation units, licenses, origins, and SHA-256
digests are recorded in `production/source-files.tsv` and
`production/source-files.sha256`. The Fedora base provenance and source-package
digests are recorded in
`reference/libfprint-fedora44-1.94.100/PROVENANCE.md`.

Device-material acquisition, extraction, recovery and generation helpers are
not part of the distributed release surface. The runtime expects protected
material supplied separately by the user and the project does not distribute
OEM binaries, secrets, caches or captures.

## Combined binary

The Goodix-enabled `libfprint-2.so.2.0.0` statically incorporates the GPL R2
component and dynamically links Apache-2.0 components. The applicable “or
later” grants permit the combined binary to be conveyed under
`GPL-3.0-or-later`. This does not relicense individual files: every source file
retains its own notice and grant.

The prepared candidate includes the GPL-2.0-or-later,
LGPL-2.1-or-later, GPL-3.0-or-later, and Apache-2.0 license texts, the exact
OpenCV license corpus extracted from the pinned RPMs, third-party notices, and
an SPDX 2.3 JSON SBOM.

## Imported source details

The four SIGFM files in `Rockytkg/libfprint/libfprint/sigfm/` originate from
the Rockytkg materialized libfprint fork commit above. Their original notices
name Matthieu Charette, Natasha England-Elbro, Timur Mangliev, and other
contributors represented in the files.

`libfprint-driver/rockytkg-imgproc/goodix_imgproc.[ch]` is an adapted,
device-independent preprocessing subset of Rockytkg's
`src/goodix_imgproc.c` and `include/goodix_imgproc.h` at commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`. Sensor-reaching code, firmware,
environment overrides, and debug dumps are not included.

The libfprint integration forward-ports SIGFM print semantics and bounded image
actions onto Fedora's newer libfprint 1.94.100 core. These are downstream
changes, not upstream libfprint or Fedora behavior.

## Excluded material

No open-source grant in this repository covers OEM firmware or binaries,
device secrets, private captures, fingerprint images or templates, factory
data, or other protected material. None of those items belongs in the public
source tree or candidate.

This project records its compatibility determination and source provenance; it
does not provide legal advice for unrelated distributions or modifications.

## Private early-login candidate

`development/patches/login-early/fprintd.patch` modifies the preserved Fedora
fprintd 1.94.5 reference only in build staging. Provenance and source RPM hashes:
`development/reference/fprintd-fedora44-1.94.5/PROVENANCE.md`. Upstream
`src/device.c`, `src/manager.c`, `src/fprintd.h`, Device XML and `pam/pam_fprintd.c`
retain their existing notices and GPL-2.0-or-later terms. New login integration,
greeter barrier, build/deployment scripts and tests are GPL-2.0-or-later; driver
changes retain LGPL-2.1-or-later per-file terms. No upstream file is relicensed.
The snapshot is unchanged; the diff and its new include file are versioned.

Plasma source RPM 6.7.5-1.fc44 was inspected only for service and greeter lifecycle;
no Plasma source was copied into the candidate. Its hashes, exact paths and the
unchanged D293 loader source pins are recorded in the candidate IMPLEMENTATION.md.
PAM/polkit devel RPMs provide compile-time headers only (pinned hashes in
`headers.sha256`); they are not installed or included in the runtime payload.
This candidate is private; it does not alter the publication/export boundary.
