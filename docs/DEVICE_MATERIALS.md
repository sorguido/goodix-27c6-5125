<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Device-specific material

The Goodix `27c6:5125` runtime needs a five-file material set tied to the
same physical reader that will be used on Linux. These files are not firmware
and the driver does not write them to the device. They are protected inputs
obtained from, or derived from, the OEM Windows environment for that reader.

The repository does not distribute the files. Obtain and use them only when
you are entitled to use the corresponding OEM software and device. Never
substitute material from another reader.

## Required files and provenance

| File | Origin | Transformation | Runtime validation | Format | Reproducibility |
| --- | --- | --- | --- | --- | --- |
| `target-material-manifest.json` | Project-derived metadata for the qualified reader and evidence set | Generated from validated device responses and the other pinned inputs; it is not copied from Windows | Regular file, exact 2,305-byte length and pinned SHA-256; response hashes and DAC values are checked by the loader | UTF-8 JSON | Rebuildable from qualified evidence and deterministic generator logic |
| `transport-material.bin` | The 32-byte device secret recovered by Windows DPAPI from `C:\ProgramData\Goodix\Goodix_Cache.bin` | The Windows exporter creates an integrity-checked `G5125XFR` staging record; the Linux finalizer combines the secret with producer data derived from the matching OEM DLL and writes the `G5125POC` runtime record | Root-owned mode-0600 regular file, exact 88-byte length and pinned SHA-256; the derived E4 binding must match the reader | `G5125POC` version 1 | Recoverable again for the same reader through the OEM Windows cache path; live extraction is an operator-controlled action |
| `target-config-90.bin` | A USB capture made while the OEM Windows stack initialized the same reader | The single outbound Goodix A0 control-`0x90` body is extracted from the capture | Exact 224-byte length, pinned SHA-256, fixed finalizer bytes, and pinned DAC fields | Raw control-`0x90` body | Re-extractable from the qualified capture; a new capture requires the same bounded selection and validation |
| `gfusb.dll` | OEM Goodix driver package, qualified version `1.1.125.14` | Copied as-is; never loaded or executed by the Linux driver. A bounded PE parser reads two producer seeds | Root-owned mode-0600 regular file, exact 5,771,496-byte length and pinned SHA-256 | OEM PE/DLL | Re-obtainable from the exact, lawfully acquired OEM package |
| `fdt-cache.bin` | `C:\ProgramData\Goodix\goodix.dat` produced by the OEM stack for the same reader | Copied and renamed without content changes | Root-owned mode-0600 regular file, exact 13,520-byte length and pinned SHA-256; layout, CRC-32/MPEG-2, OTP binding, and FDT seed are checked | OEM cache: 64-byte OTP, 12-byte FDT, 3,200-byte navigation data, 10,240-byte image data, 4-byte CRC | Re-obtainable after the OEM stack has initialized the same reader |

The pinned digests in the current runtime are:

```text
target-material-manifest.json  1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15
transport-material.bin         eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75
target-config-90.bin           e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82
gfusb.dll                      904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2
fdt-cache.bin                  9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2
```

These hashes identify the single qualified material set. A file from a
different driver release or reader is not accepted merely because its name or
length matches.

## Transport-record conversion

The staging and runtime records are both 88 bytes, but they are not
interchangeable.

`G5125XFR` is a temporary Windows-to-Linux transfer envelope. Its 24-byte
little-endian header contains the magic, version, flags, VID, PID, bounded
secret length, reserved field, and payload length. It is followed by the
32-byte DPAPI plaintext and a SHA-256 digest of the header and plaintext. The
digest detects transfer damage; it does not encrypt the secret.

`G5125POC` is the runtime format used as `transport-material.bin`. Its
24-byte header identifies version 1, the target VID/PID, material kind, and
the 32-byte secret and validator lengths. The payload contains the secret and
the 32-byte validator derived with the producer data from the pinned OEM DLL.
The conversion exists so that the runtime can validate device binding before
using the secret for TLS.

The validated Windows exporter reads the canonical cache once through a
non-reparse-point handle, separates its eight-byte trailer, derives the fixed
48-byte optional-entropy value, and calls Windows `CryptUnprotectData` on the
remaining DPAPI blob. It accepts only an exactly 32-byte, nonzero plaintext,
writes the transfer record atomically to a new local non-cloud path with a
restricted ACL, and clears temporary buffers. The Linux finalizer validates
the transfer envelope and exact OEM DLL, creates `G5125POC`, imports it into a
root-only store, reopens the stored file for byte-exact verification, and can
delete the staging record only after success.

This is an acquisition and conversion path, not PSK provisioning: it does not
invent, replace, or write factory material and it does not support migration
between different readers.

## Preparing an import set

Material extraction touches a real secret and Windows/USB state, so it remains
an explicit operator-controlled operation. The acquisition utilities used to
qualify this reader are not distributed with this release. Do not reproduce
the binary formats by hand or use an unreviewed replacement script.

After lawful acquisition, place exactly the five files above in a new local
directory outside this repository. Keep the directory private and do not use
a cloud-synchronized location. Confirm the filenames, lengths, and SHA-256
digests before import. The managed importer then applies root ownership and
mode 0600 without changing the source set:

```bash
deployment/managed-install/manage.sh import-materials \
  /absolute/path/to/the/device-material-set
```

Success is `GOODIX_MANAGED_MATERIAL_IMPORT=PASS`. The runtime independently
checks all pinned content and device-binding invariants before a secure
session can start.

## Handling rules

- Do not commit, upload, print, or attach any of the five files to a report.
- Treat the transfer envelope as plaintext secret material even though it has
  an integrity digest.
- Keep staging and import directories accessible only to their owner; use the
  managed importer for the final root-only store.
- Never log buffer contents, the DPAPI plaintext, producer seeds, FDT seed, or
  derived TLS material.
- A backup is useful only for the same physical reader. Store it encrypted and
  test recovery without weakening file permissions.
- If any size, digest, CRC, manifest, E4 binding, ownership, or mode check
  fails, stop. Do not patch around the check.
