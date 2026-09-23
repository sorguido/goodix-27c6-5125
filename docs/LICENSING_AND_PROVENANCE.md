<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Licensing and provenance

Licensing is per file. A directory name or a combined binary's license does not
change the original copyright or grant of any source file.

## Components

| Component | Source/version | License and use |
| --- | --- | --- |
| libfprint base | Fedora libfprint 1.94.100 | Upstream per-file terms, predominantly LGPL-2.1-or-later; public library ABI and core |
| Goodix driver | Project source | Per-file SPDX, predominantly LGPL-2.1-or-later; device, transport, secure session and image integration |
| SIGFM | Rockytkg's materialized libfprint fork, commit `7ebe0c809b4d1df3400e84299a4ec4acdea84590` | LGPL-2.1-or-later; feature extraction and matching |
| Image preprocessing | Adapted from Rockytkg, commit `227eba219fa9e3fbac5bd59aca79f624f67cd11b` | GPL-2.0-or-later; device-independent preprocessing subset |
| OpenCV | Fedora 4.13.0-1.fc44 packages | Fedora expression `BSD-3-Clause AND Apache-2.0 AND ISC`; required runtime libraries |
| libgusb | Fedora system library | LGPL-2.1-or-later; USB dependency, not privately bundled |
| OpenSSL | Fedora system library | Apache-2.0; TLS dependency |
| Lifecycle and Plasma selector tools | Project source | GPL-2.0-or-later; ordinary Linux-PAM APIs, Python standard library and Fedora tools |

Fedora supplies fprintd, its PAM module, Plasma, sudo and PolicyKit. Their
implementations are not copied into private replacement consumers by this
architecture. Each separately supplied package retains its own license.

## Combined library and notices

The Goodix-enabled libfprint incorporates GPL-2.0-or-later preprocessing and
links Apache-2.0 components. Applicable later-version grants allow the combined
library to be conveyed under GPL-3.0-or-later. Individual source files retain
their own notices and licenses; GPL code is not relabelled as LGPL.

Library build outputs include the applicable license texts, OpenCV's license
corpus extracted from the pinned packages, source manifests and build provenance.
Final public package notices must reflect the actual payload; no finished public
package or complete package SBOM is asserted here.

## Source provenance

The exact target-specific source paths, licenses and origins are recorded in
[`production/source-files.tsv`](../production/source-files.tsv), with digests in
[`production/source-files.sha256`](../production/source-files.sha256).
The [Fedora libfprint provenance record](../reference/libfprint-fedora44-1.94.100/PROVENANCE.md)
identifies the original archive/source-package hashes and downstream changes.

The four SIGFM files are `sigfm.cpp`, `sigfm.h`, `binary.hpp` and `img-info.hpp`
under `Rockytkg/libfprint/libfprint/sigfm/`. Their notices identify Matthieu
Charette, Natasha England-Elbro, Timur Mangliev and other credited contributors.
The preprocessing files `libfprint-driver/rockytkg-imgproc/goodix_imgproc.c`
and `.h` derive from Rockytkg's `src/goodix_imgproc.c` and
`include/goodix_imgproc.h` at the commit above. Firmware, provisioning, USB
control and debug-dump behavior are not incorporated with that subset.

Local lifecycle and recovery code uses this project's ownership/receipt formats;
no new external implementation or license boundary is introduced by the removal
tools. The Plasma selector uses public Linux-PAM interfaces without copying
PAM, fprintd or Plasma source into a private replacement component.

## Excluded material

Open-source licenses in this tree do not grant rights to distribute OEM firmware
or binaries, reader secrets, private captures, factory data, fingerprint images
or templates. Those items are excluded from public source and software payloads.
The runtime consumes a separately supplied legitimate device-material bundle.

The [publication manifest](../PUBLICATION_MANIFEST.md) defines eligible source
and documentation. Preserve original notices and corresponding source when
redistributing components. [References](REFERENCES.md) and
[acknowledgements](../ACKNOWLEDGEMENTS.md) identify the upstream projects.
