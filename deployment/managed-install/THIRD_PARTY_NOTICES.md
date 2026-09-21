<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Third-party notices for the managed candidate

This notice describes the binary candidate produced by `prepare.sh`. It does
not replace the per-file notices or the canonical provenance ledger.

## Combined libfprint binary

`libfprint-2.so.2.0.0` starts from Fedora's libfprint 1.94.100 source and
contains project changes under their existing per-file terms. It statically
incorporates the project adaptation of Rockytkg's R2 preprocessing code under
`GPL-2.0-or-later` and links to Apache-2.0 components. The candidate therefore
conveys this combined binary under `GPL-3.0-or-later`; this selection is
permitted by the existing “or later” grants and does not relicense individual
source files. Complete corresponding source is the exact `SOURCE_COMMIT`
recorded in `MANIFEST`.

The R2 source was adapted from Rockytkg/goodix-linux-27c6-5125 commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`, paths
`src/goodix_imgproc.c` and `include/goodix_imgproc.h`. Copyright and license
notices are preserved in the source.

SIGFM is derived from the materialized libfprint fork commit
`7ebe0c809b4d1df3400e84299a4ec4acdea84590` and remains
`LGPL-2.1-or-later`. Its source notices identify Matthieu Charette and the
other contributors recorded in `docs/LICENSING_AND_PROVENANCE.md`.

## Bundled shared libraries

- `libgusb.so.2` is copied from Fedora 44 package `libgusb-0.4.9-5.fc44` and
  remains `LGPL-2.1-or-later`.
- The bundled OpenCV libraries come from the hash-pinned Fedora 44 packages
  `opencv-*-4.13.0-1.fc44`, whose RPM license expression is
  `BSD-3-Clause AND Apache-2.0 AND ISC`. The exact license and third-party
  notice files shipped by those RPMs are preserved in
  `OpenCV-LICENSES.txt`.

## Paired login components

The candidate includes fprintd 1.94.5 and its PAM module, built from the pinned
upstream source plus the reviewable project login patch. Original copyright
notices remain in the corresponding source; see `fprintd-AUTHORS` and
`fprintd-COPYING`. The source grant is GPL-2.0-or-later, with the daemon's paired
libfprint combined distribution using GPL-3.0-or-later. The small GIO greeter
parent is project GPL-2.0-or-later code and incorporates no Plasma source.

## System dependencies

GLib, OpenSSL 3, libusb, JSON-GLib, the C/C++ runtime and the remaining
libraries reported in `SBOM.spdx.json` are supplied by the Fedora 44 host and
are not copied into the candidate. OpenSSL 3 is Apache-2.0. The SPDX SBOM
records the exact Fedora packages resolved when the candidate is built.

The complete project licensing and provenance ledger is
`docs/LICENSING_AND_PROVENANCE.md`. No firmware, PSK, protected runtime
material, fingerprint template, real biometric sample or private capture is
covered by these open-source notices or included in the candidate.

## Polkit conversation bridge

`pam_goodix_polkit.so` is independently implemented project code under
GPL-2.0-or-later. It uses public libpam APIs and invokes the installed Fedora
pam_fprintd module in a separate PAM handle. No KDE, Polkit or Linux-PAM source
expression is incorporated. Their exact versions are recorded as host
integration dependencies in the SBOM. Corresponding source and build/deployment
provenance are in `production/polkit/` at the candidate's source commit.

## Sudo conversation bridge

`pam_goodix_sudo.so` is project code under GPL-2.0-or-later. It uses libpam and
Fedora's stock pam_fprintd in a separate handle. Sudo and Fedora PAM sources were
read for behavior verification; no third-party expression is copied into this
bridge. The candidate's ordinary-consumer retry correction retains fprintd's
GPL-2.0-or-later source license and the existing combined distribution boundary.

## Plasma Login daemon VT corrective

The additional `plasmalogin` executable is built from Fedora
plasma-login-manager 6.7.5-1.fc44 plus a local session VT allocation patch.
KDE/SDDM notices (including Abdurrahman AVCI, Pier Luigi Fiorini, Martin Bříza,
David Edmundson and other contributors) remain in the complete corresponding
source at `reference/plasma-login-manager-fedora44-6.7.5/`.
Per-file GPL-2.0-or-later / LGPL-2.1-or-later / CC0 notices are preserved;
this combined daemon uses applicable GPL-3.0-or-later terms. Local VT source,
patch, build and tests are GPL-2.0-or-later. Existing candidate license texts
and the SPDX SBOM cover this additional executable; no vendor helper is bundled
or replaced. See the reference PROVENANCE.md for exact source/package hashes.
