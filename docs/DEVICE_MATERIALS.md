<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Device-specific material contract

The Goodix `27c6:5125` runtime consumes a pre-existing five-file protected
material bundle:

```text
goodix-material/
├── target-material-manifest.json
├── transport-material.bin
├── target-config-90.bin
├── gfusb.dll
└── fdt-cache.bin
```

The reader-specific files must describe the same physical reader. `gfusb.dll`
is different: it is the qualified OEM implementation compatibility boundary,
not a reader-identity value.

## Supported scope

This project **does not provide or support acquisition, extraction, recovery or
generation of a fresh material bundle** from an OEM Windows installation,
DPAPI cache, USB capture, or other protected source.

Users are responsible for lawfully obtaining a valid bundle for their own
reader by means outside this release. Do not construct missing values by guess,
reuse another reader's material, generate a replacement PSK, or weaken runtime
validation to force a bundle through. If a valid bundle is not available, the
supported installation cannot proceed.

The repository does not distribute device secrets, OEM binaries, caches,
captures, fingerprint images, templates, or factory material.

## `target-material-manifest.json`

The production manifest uses schema:

```text
goodix-5125-device-materials-v1
```

It contains exactly ten required string fields:

```text
schema
vid
pid
app
transport_sha256
config90_sha256
fdt_cache_sha256
a2_response_sha256
chip82_response_sha256
otp_a6_response_sha256
```

The fixed compatibility identity is:

```text
vid = 27c6
pid = 5125
app = GF_ST411SEC_APP_12509
```

The six SHA-256 values are reader/bundle-specific. The runtime rejects missing,
duplicate or unknown keys, malformed separators, escapes, embedded NUL, invalid
digests, trailing data, an unsupported schema, or a wrong VID/PID/APP identity.
Development-reader hashes are not release acceptance criteria.

## `transport-material.bin`

The runtime transport record is exactly 88 bytes and uses the `G5125POC`
version-1 format. It carries the existing 32-byte reader PSK and its associated
validator material. The runtime validates the record header and manifest
digest, derives the expected E4 binding from the protected PSK and the qualified
OEM producer data, and fails closed on a mismatch.

This file is sensitive. The project does not provide a PSK extraction or
provisioning workflow.

## `target-config-90.bin`

The CONFIG90 body is exactly 224 bytes. The runtime checks its manifest digest,
recomputes the arithmetic finalizer, and verifies the fixed DAC register/layout
correlations while accepting the concrete per-reader DAC values from the
validated CONFIG90 itself.

The project does not provide a USB-capture extractor for this file.

## `gfusb.dll`

The qualified OEM compatibility input is:

```text
size:    5,771,496 bytes
SHA-256: 904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2
```

The Linux driver does not execute the DLL. A bounded parser reads the qualified
producer data required for the E4 binding. This fixed DLL identity qualifies the
producer implementation; it is not a per-reader identity pin.

The OEM DLL is not distributed by this project. Users must obtain it lawfully.

## `fdt-cache.bin`

The FDT cache is exactly 13,520 bytes. The runtime validates its manifest digest,
layout and CRC-32/MPEG-2. The first 64 bytes are bound to the manifest's OTP A6
response digest, and the FDT seed is read from the qualified cache layout.

## Live reader binding

The manifest also carries per-reader SHA-256 pins for the typed A2, chip82 and
OTP A6 responses. During the secure-session path, live typed responses are
checked against those pins. E4 and concrete DAC values are derived from the
validated bundle rather than fixed to the development reader.

These checks make the runtime device-dynamic without making material
acquisition part of the release.

## Protected filesystem contract

After import, runtime material is stored under:

```text
/var/lib/goodix-5125-poc/
```

The directory must be root-owned mode `0700`. Material entries must be regular,
root-owned mode-`0600` files; symlinks are rejected. The runtime checks metadata
and content fail-closed before using sensitive material.

Keep protected material out of Git repositories, cloud-synchronized folders,
bug reports, logs, screenshots and public archives.

## Import

When a complete valid five-file bundle is already available, import it with:

```bash
deployment/managed-install/manage.sh import-materials \
  /absolute/path/to/the/device-material-set
```

The supplied directory must contain exactly the five files listed above. The
managed importer copies them into protected root-only storage; runtime
validation remains authoritative and a mismatched or malformed bundle is
rejected.

## Safety boundary

Material handling does not authorize firmware flashing, IAP, ClearApp, OTP
writes, PSK replacement/provisioning, VID:PID changes, or any other persistent
device-state modification. The supported runtime remains factory-preserving and
expects the Windows factory path to remain usable.
