<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Licensing and provenance

Licensing is per file. No directory name changes the license or copyright of
the source it contains.

## Distributed components

| Component | Origin | Version or commit | License | Local use |
| --- | --- | --- | --- | --- |
| libfprint base | Fedora 44 source package / upstream libfprint | 1.94.100 | Per-file upstream terms, predominantly `LGPL-2.1-or-later` | Patched base and public ABI |
| Goodix driver sources | This project | current source tree | Per-file SPDX; predominantly `LGPL-2.1-or-later` | USB, TLS, image, lifecycle, enrollment, and matching integration |
| Device-material exporter wrapper, finalizer and CONFIG90 extractor | This project | current source tree | `GPL-2.0-or-later` | Local DPAPI export orchestration, offline `G5125XFR` → `G5125POC` finalization, and offline USBPcap CONFIG90 extraction |
| Device-material exporter core | Historical project-authored D191 source recovered from preserved project/Codex development material | historical pre-D246 source | `BSD-2-Clause` | Windows DPAPI/entropy implementation used by the public wrapper |
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

## Device-material helper details

`tools/device-materials/Export-Goodix5125TransportMaterial.ps1` is a new
user-facing GPL-2.0-or-later wrapper. Its sibling
`_Export-Goodix5125TransportMaterial.Core.ps1` is the byte-preserved recovered
Windows exporter implementation previously kept under private historical
material. Because that source belongs to the historical pre-D246 project
revisions, its existing BSD-2-Clause grant is retained; the adjacent `.license`
file records that license explicitly.

The recovered core contains the project's local DPAPI/entropy logic and
fail-closed file handling. It does not embed the target secret, an OEM payload,
or a private capture, and it performs no USB/device write operation.

`tools/device-materials/Finalize-Goodix5125TransportMaterial.py` is a current,
GPL-2.0-or-later self-contained project adaptation of the recovered transfer
parser/finalizer and D190 binding reference. The adapted historical reference
material was available under the project's BSD-2-Clause grant; that provenance
and prior grant are not revoked by the current GPL distribution of the new
combined tool.

The finalizer carries the current bounded `gfusb.dll` parser policy and writes
only the caller's final local runtime material. The OEM DLL is supplied by the
user at runtime, parsed as inert bytes, and is neither shipped nor executed by
the helper.

`tools/device-materials/Extract-Goodix5125Config90.py` is current
GPL-2.0-or-later project code. It is based on neutral protocol facts and
project-authored pcapng/USBPcap parsing and Goodix A0 framing knowledge already
recorded in the private development evidence and the current clean-room A0
codec. It ships no capture bytes and performs no USB/device access. Its only
runtime input is a user-supplied local `.pcapng` file and its only persistent
output is the caller-selected 224-byte `target-config-90.bin` file.

No generated `Goodix_Cache.bin`, `G5125XFR`, `G5125POC`, OEM DLL, secret,
`target-config-90.bin` or capture belongs in the public repository.

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
