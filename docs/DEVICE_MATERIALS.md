<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Device-specific material contract

The runtime requires a pre-existing protected bundle for the same physical
Goodix `27c6:5125` reader. The project validates and consumes it; acquisition,
extraction, key recovery and generation are not supported installation features.
No protected bundle or OEM binary is distributed with the project.

Use only material you are entitled to use. Never substitute another reader's
keys, guess missing values or generate a replacement PSK. A mismatch must be
resolved without flashing, provisioning or changing the reader's persistent state.

## Staging directory

Place exactly the five files below in `$HOME/goodix-5125-materials/`, outside
the repository. Do not rename them, share them or commit them. The public
`install.sh` imports them automatically; no manual root copy is required.
An optional `--materials /some/other/path` selects a different staging location.
The source directory and ordinary files must belong to the installing user,
without symlinks or hard links. Shared write permissions and executable files
are rejected. Keep the source folder private. See [Installation](INSTALLATION.md).

## Required files

| File | Contract |
| --- | --- |
| `target-material-manifest.json` | Reader identity and six SHA-256 bindings; exact schema below, at most 4,096 bytes |
| `transport-material.bin` | 88-byte `G5125POC` version-1 record containing the existing 32-byte PSK and a 32-byte validator |
| `target-config-90.bin` | 224-byte configuration body with validated layout, digest and arithmetic finalizer |
| `gfusb.dll` | Qualified OEM compatibility input; parsed for data, never executed by the Linux driver |
| `fdt-cache.bin` | 13,520-byte cache with validated layout, digest and CRC-32/MPEG-2 |

The manifest, transport, configuration and cache describe one reader. The DLL
identifies the qualified OEM producer implementation rather than an individual
reader. Its compatibility identity is OEM package `1.1.125.14`, size 5,771,496
bytes, SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
The project does not grant redistribution rights to that binary.

## Manifest

The schema is `goodix-5125-device-materials-v1`. Exactly these ten string fields
are required:

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

The fixed identity values are `vid=27c6`, `pid=5125` and
`app=GF_ST411SEC_APP_12509`. Each digest is a SHA-256 value for the actual reader
or supplied file; example or reference-reader digests are not substitutes.
The parser rejects missing, duplicate and unknown keys, unsupported identities,
escapes, embedded NUL, malformed separators, invalid digests and trailing data.

The transport/configuration/cache hashes bind the files to the manifest. The
A2, chip82 and OTP A6 hashes bind typed responses to that reader during runtime.
The E4 validator and concrete DAC values derive from the validated bundle.
No lifecycle installer needs to open USB merely to observe that the reader is
present.

## Validation and storage

The transport header has fixed magic, version, lengths and VID/PID fields.
The configuration finalizer is a 16-bit arithmetic check over its first 222
bytes. The cache uses CRC-32/MPEG-2: polynomial `0x04c11db7`, initial value
`0xffffffff`, non-reflected, xor-out zero. Format checks complement SHA-256
bindings; they do not replace them.

Material is stored under `/var/lib/goodix-5125-poc/`, root-owned mode `0700`,
with regular root-owned mode-`0600` files. Symlinks and invalid metadata are
rejected. The SELinux mapping uses `fprintd_var_lib_t` for the material tree.
The installer validates the complete source bundle before publishing a new
material directory. It rejects missing/extra entries and unsafe metadata and
sets restrictive destination modes for accepted source files, including files
whose source mode is `0644`. A valid
installed set is preserved; it is not silently replaced by a different bundle.
The installer checks each reader's own supplied file bindings, without requiring
equality with a reference reader. Typed response bindings remain runtime checks
because they require that reader. No USB access is used for bundle import.

Normal removal and emergency recovery retain these files. Removing a project
SELinux mapping may change their labels back to current policy defaults, but
not their contents or Unix ownership/mode. Fingerprint templates are separate
and remain under `/var/lib/fprint/`.

Treat the entire bundle as protected. Keep it out of source archives, public
issue reports, cloud-synchronized folders, screenshots and logs. See
[Security and privacy](SECURITY.md).
