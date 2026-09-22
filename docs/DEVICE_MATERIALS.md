<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Device-specific material contract and acquisition reference

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

## Supported release scope

The supported release **validates and consumes** an already prepared bundle. It
does not ship acquisition, extraction, DPAPI-recovery, USBPcap parsing, or
manifest-generation tools.

The technical reference later in this document describes the formats,
source locations, protocol evidence and validation rules needed to derive the
five artifacts with independent tooling or automation. That acquisition
procedure is informational and outside the supported release surface: the
runtime and the managed importer remain the final authority on whether a bundle
is acceptable.

Use only material lawfully obtained from your own reader/OEM environment. Do
not guess missing values, reuse another reader's material, generate a
replacement PSK, weaken validation, flash firmware, enter IAP, invoke ClearApp,
write OTP, or change VID:PID.

The repository does not distribute device secrets, OEM binaries, caches,
captures, fingerprint images, templates, or factory material.

---

# Part I — Runtime contract

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

The six SHA-256 values are reader/bundle-specific. The manifest must be at most
4096 bytes. The runtime rejects missing, duplicate or unknown keys, malformed
separators, escapes, embedded NUL, invalid digests, trailing data, an unsupported
schema, or a wrong VID/PID/APP identity. Development-reader hashes are not
release acceptance criteria.

A canonical shape is:

```json
{
  "schema": "goodix-5125-device-materials-v1",
  "vid": "27c6",
  "pid": "5125",
  "app": "GF_ST411SEC_APP_12509",
  "transport_sha256": "<64 hex digits>",
  "config90_sha256": "<64 hex digits>",
  "fdt_cache_sha256": "<64 hex digits>",
  "a2_response_sha256": "<64 hex digits>",
  "chip82_response_sha256": "<64 hex digits>",
  "otp_a6_response_sha256": "<64 hex digits>"
}
```

Lowercase hexadecimal is recommended for reproducibility.

## `transport-material.bin`

The runtime transport record is exactly 88 bytes and uses `G5125POC` version 1.
It carries the existing 32-byte reader PSK plus a 32-byte validator derived
from that PSK and the qualified OEM producer data.

The byte layout is:

| Offset | Length | Meaning |
| ---: | ---: | --- |
| `0` | 8 | ASCII `G5125POC` |
| `8` | 2 | version `1`, little-endian |
| `10` | 2 | header length `24`, little-endian |
| `12` | 2 | VID `0x27c6`, little-endian |
| `14` | 2 | PID `0x5125`, little-endian |
| `16` | 2 | format/binding identifier `1` |
| `18` | 2 | PSK length `32` |
| `20` | 2 | validator length `32` |
| `22` | 2 | reserved `0` |
| `24` | 32 | existing reader PSK |
| `56` | 32 | derived validator |

The runtime validates this header, checks the file SHA-256 against the manifest,
and recomputes the expected E4 binding before accepting the PSK.

This file is sensitive.

## `target-config-90.bin`

The CONFIG90 body is exactly 224 bytes. The runtime checks its manifest digest,
recomputes the arithmetic finalizer, and verifies the fixed DAC register/layout
correlations while accepting the concrete per-reader DAC values from the
validated CONFIG90 itself.

The last two bytes are a little-endian 16-bit finalizer. Let the first 222 bytes
be interpreted as 111 little-endian 16-bit words. Then:

```text
sum = (word[0] + ... + word[110]) mod 65536
finalizer = (-0xa5a5 - sum) mod 65536
```

Bytes `222..223` must equal that finalizer in little-endian form.

## `gfusb.dll`

The qualified OEM compatibility input is:

```text
Goodix OEM driver package: 1.1.125.14
size:    5,771,496 bytes
SHA-256: 904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2
```

The qualified package installs the UMDF binary under the INF destination
`%12%\UMDF\gfusb.dll`. On a standard Windows installation the installed copy is
typically available as:

```text
C:\Windows\System32\drivers\UMDF\gfusb.dll
```

A package copy may also be present below:

```text
C:\Windows\System32\DriverStore\FileRepository\<Goodix-driver-package>\...
```

The DriverStore subdirectory is package/version-specific and must not be
hardcoded. If more than one copy is found, use the one whose size and SHA-256
match the qualified values above.

The Linux driver does not execute the DLL. A bounded parser reads qualified
producer data required for the E4 binding. This fixed DLL identity qualifies the
producer implementation; it is not a per-reader identity pin.

The OEM DLL is not distributed by this project. Users must obtain it lawfully.

## `fdt-cache.bin`

The FDT cache is exactly 13,520 bytes. Its OEM source is normally:

```text
C:\ProgramData\Goodix\goodix.dat
```

Create `fdt-cache.bin` by copying those bytes unchanged.

The runtime validates its manifest digest, layout and CRC-32/MPEG-2. The last
four bytes contain the little-endian CRC value calculated over all preceding
bytes. The CRC parameters used by the project are:

```text
polynomial: 0x04c11db7
initial:    0xffffffff
reflected:  no
xor-out:    0x00000000
```

The first 64 bytes are bound to the manifest's OTP A6 response digest. The FDT
seed is read from the qualified cache layout after those OTP bytes.

## Live reader binding

The manifest also carries per-reader SHA-256 pins for the typed A2, chip82 and
OTP A6 responses. During the secure-session path, live typed responses are
checked against those pins. E4 and concrete DAC values are derived from the
validated bundle rather than fixed to the development reader.

These checks make the runtime device-dynamic without making acquisition tooling
part of the release.

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

---

# Part II — Informational acquisition reference

This section documents the acquisition procedure closely enough that an
independent implementation can be written from the formats and validation rules
recorded here. It is **not** an additional supported component of the release.

The recommended model is:

```text
same physical Goodix reader
        |
        +-- OEM Windows files ------------------------------+
        |                                                   |
        +-- USBPcap capture made during OEM initialization -+---> five files
```

All reader-specific inputs must come from the same physical unit.

## Step 1 — Prepare the OEM Windows environment

Use native Windows or a Windows VM with USB passthrough and the qualified Goodix
OEM driver. The target is:

```text
VID_27C6&PID_5125
GF_ST411SEC_APP_12509
```

If using a VM, a clean sequence is:

1. boot Windows without attaching the fingerprint reader;
2. start USBPcap capture on the relevant USB controller;
3. attach the reader once;
4. allow the ordinary OEM driver to initialize it;
5. stop the capture after initialization has completed.

Do not run Goodix maintenance/provisioning operations.

On Windows, the device identity can be checked with ordinary Device Manager or,
for example:

```powershell
Get-PnpDevice -PresentOnly | Select-String 'VID_27C6&PID_5125'
```

## Step 2 — Preserve the OEM inputs

The normally relevant OEM-side files are:

```text
C:\ProgramData\Goodix\Goodix_Cache.bin
C:\ProgramData\Goodix\goodix.dat
C:\Windows\System32\drivers\UMDF\gfusb.dll
OEM initialization USBPcap capture (.pcapng)
```

`C:\ProgramData\Goodix` is the location observed with the qualified OEM stack.
The DLL path is the normal installed location for the package's
`%12%\UMDF\gfusb.dll` INF destination. If the installed DLL is not present
there, search the matching Goodix package below
`C:\Windows\System32\DriverStore\FileRepository\` and verify the candidate by
size and SHA-256 rather than by directory name.

For example, an administrator can locate candidate copies with:

```powershell
Get-Item 'C:\Windows\System32\drivers\UMDF\gfusb.dll' -ErrorAction SilentlyContinue
Get-ChildItem 'C:\Windows\System32\DriverStore\FileRepository' `
  -Filter gfusb.dll -Recurse -ErrorAction SilentlyContinue
```

Copy the required inputs into a private working location. Do not place them in
the repository.

`goodix.dat` becomes `fdt-cache.bin` by copying the bytes unchanged. Before
using it, require:

```text
size = 13,520 bytes
CRC-32/MPEG-2 over bytes 0..13515 == little-endian uint32 at bytes 13516..13519
```

Require the qualified DLL size and SHA-256 listed earlier.

## Step 3 — Capture the OEM initialization traffic

Use Wireshark/TShark with USBPcap support. Capture must begin before the reader
is initialized so that CONFIG90 and the typed A2/82/A6 responses are present.

The extraction logic uses USBPcap link type `249` and bulk endpoints:

```text
host -> device : endpoint 0x01
 device -> host: endpoint 0x81
```

USB bulk payloads can be fragmented across packets. Reassemble frames per
`(USB bus, USB device, endpoint, direction)`; do not concatenate traffic from
different physical USB devices. A single material bundle must be derived from
one reader stream.

### Goodix A0 framing reference

For the frames needed here:

```text
offset 0      : 0xa0
offsets 1..2 : outer payload length, little-endian
offset 3      : outer tag
offset 4      : wire control
offsets 5..6 : inner length, little-endian
offset 7..   : body
last byte     : inner checksum
```

Validation rules:

```text
frame_length = 4 + outer_payload_length
outer_tag = (0xa0 + low(payload_length) + high(payload_length)) mod 256
logical_control = wire_control & 0xfe
inner_length = body_length + 1
logical_control + body_length + 1 + sum(body) + checksum == 0xaa (mod 256)
```

Ignore candidates that fail any framing, length or checksum rule.

## Step 4 — Recover `target-config-90.bin`

Search only the target reader's **host-to-device** bulk stream on endpoint
`0x01`.

The required frame is:

```text
Goodix outer type: A0
logical control:   0x90
qualified wire control: 0x91
body length:       224 bytes
```

Accept the body only if its CONFIG90 arithmetic finalizer is valid as described
in Part I.

If the capture contains repeated byte-identical valid CONFIG90 bodies, they are
consistent duplicates. If it contains two distinct valid CONFIG90 bodies for
the same acquisition, treat the capture as ambiguous instead of choosing the
first one.

Save the 224-byte **body only** as:

```text
target-config-90.bin
```

## Step 5 — Recover the A2 / chip82 / OTP A6 response pins

From the **same reader stream and same capture**, inspect device-to-host bulk
traffic on endpoint `0x81`.

Require valid Goodix A0 frames with exact typed controls and body lengths:

| Response | wire/logical control | Body length | Manifest value |
| --- | ---: | ---: | --- |
| A2 | `0xa2` | 3 bytes | SHA-256(body) |
| chip82 | `0x82` | 4 bytes | SHA-256(body) |
| OTP A6 | `0xa6` | 64 bytes | SHA-256(body) |

For these typed responses the wire control is the exact even control shown in
the table, unlike the odd wire variant used by host commands such as CONFIG90.

Require at least one valid candidate for every class. Repeated byte-identical
bodies are acceptable; differing valid bodies in one class make the capture
ambiguous and should not be silently resolved.

Record only these three digests for manifest construction. As an additional
cross-material check:

```text
SHA256(OTP_A6_body) == SHA256(fdt-cache.bin[0:64])
```

If that fails, the cache and capture do not describe the same qualified state.

## Step 6 — Recover the existing 32-byte PSK from `Goodix_Cache.bin`

Use the cache from the same Windows OEM environment:

```text
C:\ProgramData\Goodix\Goodix_Cache.bin
```

The file structure used for recovery is:

```text
Goodix_Cache.bin = DPAPI_blob || trailer[8]
```

Require a regular file larger than eight bytes and reject obviously implausible
or unbounded inputs. The final 8-byte trailer must not be all zero.

Derive DPAPI optional entropy as follows:

```text
trailer = last 8 bytes of Goodix_Cache.bin
h1 = SHA256(trailer)

mix = 04 e0 b0 f3 f5 59 84 17 dd e2 98 e4 67 c7 95 f7
entropy_input = h1[0:16] || mix
h2 = SHA256(entropy_input)

entropy = h1[16:32] || h2[0:32]
```

`entropy` is therefore 48 bytes.

The DPAPI ciphertext is every byte of `Goodix_Cache.bin` except the final
8-byte trailer. Pass that blob and the 48-byte optional entropy to Windows
`CryptUnprotectData`. The recovered plaintext must be exactly 32 bytes and must
not be all zero. Those 32 bytes are the existing reader PSK.

Do not print the PSK, place it on a command line, or persist it separately unless
absolutely necessary. An independent implementation should cleanse temporary
buffers and protect any output file from other users.

## Step 7 — Obtain the two qualified OEM producer seeds

The validator stored in `transport-material.bin` is not merely a hash of the
PSK. It binds the reader PSK to producer data from the exact qualified
`gfusb.dll`.

Use the qualified DLL copied from the installed UMDF location or the matching
DriverStore package, verify the size and SHA-256 from Part I, then parse it as a
PE file without executing it.

The qualified producer locations are:

```text
seed A RVA:               0x56f030, 6 file-backed bytes
seed B instruction RVA:   0x69d0, 14 file-backed bytes
```

For seed B, the 14-byte instruction must satisfy the qualified shape:

```text
bytes 0..2  = c7 45 9f
bytes 7..9  = c7 45 a3
```

The producer instruction pattern used for qualification must be unique in the
DLL. Build the 6-byte second seed as:

```text
seed_B = instruction[3:7] || instruction[10:12]
```

Reject missing, zero, ambiguous, out-of-range, or non-file-backed seed data.

## Step 8 — Derive the 32-byte transport validator

The canonical binding implementation is in the source tree:

```text
libfprint-driver/goodix_d190_binder.c
function: goodix_d190_bind_validator()
```

An independent material-preparation implementation should reproduce that
function byte-for-byte rather than inventing a different derivation. Its inputs
are:

```text
PSK       : 32 bytes recovered in Step 6
seed A    : 6 bytes from Step 7
seed B    : 6 bytes from Step 7
```

and its output is the 32-byte validator.

The implementation uses the documented D190 SHA-256/HMAC/AES derivation and is
already compiled into the runtime, which recomputes the result when the material
is loaded. Consequently, an incorrectly constructed validator will fail closed
at runtime.

## Step 9 — Build `transport-material.bin`

Construct the 88-byte `G5125POC` v1 record using the layout in Part I:

```text
header[24] || PSK[32] || validator[32]
```

The exact 24-byte header is the little-endian encoding of:

```text
magic             = "G5125POC"
version           = 1
header_length     = 24
vid               = 0x27c6
pid               = 0x5125
format_identifier = 1
psk_length        = 32
validator_length  = 32
reserved          = 0
```

Save the resulting 88 bytes as:

```text
transport-material.bin
```

## Step 10 — Build `target-material-manifest.json`

Compute:

```text
transport_sha256  = SHA256(transport-material.bin)
config90_sha256   = SHA256(target-config-90.bin)
fdt_cache_sha256  = SHA256(fdt-cache.bin)
a2_response_sha256
chip82_response_sha256
otp_a6_response_sha256
```

The final three values are the body digests recovered in Step 5.

Write exactly the ten-field JSON object described in Part I. Do not add comments,
extra metadata, occurrence counts, source paths, or unknown keys: the production
parser intentionally rejects them.

Before accepting the manifest, independently verify:

```text
transport size/header        = valid G5125POC v1, 88 bytes
CONFIG90 size/finalizer      = valid, 224 bytes
FDT cache size/CRC           = valid, 13,520 bytes
OTP A6 digest                = SHA256(fdt-cache.bin[0:64])
gfusb.dll size/SHA-256       = qualified values
all per-reader evidence      = same physical reader
```

## Step 11 — Assemble and retain the final bundle

The final directory must contain exactly:

```text
goodix-material/
├── target-material-manifest.json
├── transport-material.bin
├── target-config-90.bin
├── gfusb.dll
└── fdt-cache.bin
```

Recommended local checks include:

```bash
find ./goodix-material -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
sha256sum ./goodix-material/*
```

Keep a private external backup if you need disaster recovery for the same
physical reader. The bundle contains material that must not be published.

Intermediate Windows cache files and USB captures are not required by the Linux
runtime once the five-file bundle exists.

---

# Historical import and installation

> **HISTORICAL_ONLY / REJECTED_ARCHITECTURE.** The managed importer below is
> preserved for provenance and recovery. Do not use it for the new VM runtime.
> The [distro-decoupled roadmap](../ROADMAP_DISTRO_DECOUPLED_RELEASE.md) requires
> materials to stay separate from software; transfer/access remains a Human
> Gate. The five-file format is unchanged.

When a complete valid five-file bundle is available, import it with:

```bash
deployment/managed-install/manage.sh import-materials \
  /absolute/path/to/the/device-material-set
```

The supplied directory must contain exactly the five files listed above. The
managed importer copies them into protected root-only storage; runtime
validation remains authoritative and a mismatched or malformed bundle is
rejected.

Follow [Installation](INSTALLATION.md) for candidate preparation, installation,
enrollment and lifecycle operations.

# Troubleshooting the acquisition reference

## OEM cache files are absent

The OEM driver may not have initialized the reader in that Windows environment.
Check:

```text
C:\ProgramData\Goodix\Goodix_Cache.bin
C:\ProgramData\Goodix\goodix.dat
```

Confirm the exact `VID_27C6&PID_5125` device and the qualified OEM stack. Do not
create placeholder files.

## CONFIG90 cannot be identified

Confirm that the capture began before OEM initialization and contains the target
reader's endpoint-`0x01` host-to-device bulk traffic. Require a valid A0/0x90
frame, 224-byte body and valid CONFIG90 finalizer; do not cut an arbitrary
224-byte window from Wireshark.

## A2 / 82 / A6 responses cannot be identified

Confirm endpoint-`0x81` device-to-host traffic and valid A0 framing. Required
body lengths are exactly 3, 4 and 64 bytes respectively. Do not mix candidates
from different USB bus/device identities.

## Multiple distinct valid candidates exist

Treat the capture as ambiguous. Prefer a new bounded OEM-initialization capture
rather than selecting the first candidate.

## DPAPI recovery fails

Verify that `Goodix_Cache.bin` came from the OEM environment being used for
recovery, that the last 8 bytes were treated as the entropy trailer rather than
part of the DPAPI blob, and that the optional entropy was derived exactly as
shown. Do not substitute a random PSK.

## `gfusb.dll` cannot be found or does not match

Check the normal installed path first:

```text
C:\Windows\System32\drivers\UMDF\gfusb.dll
```

If it is absent, locate `gfusb.dll` under the matching Goodix package in
`C:\Windows\System32\DriverStore\FileRepository\`. Do not select by filename
alone: require the qualified size and SHA-256 from Part I.

Do not bypass the compatibility boundary. The qualified producer offsets and
binding are defined for the exact DLL size/hash listed in this document.

## OTP/cache binding fails

The capture and `fdt-cache.bin` are inconsistent, corrupt, or were collected
from different reader states/devices. Recollect from the same physical reader.

# Safety boundary

Nothing in this acquisition reference authorizes firmware flashing, IAP,
ClearApp, OTP writes, PSK replacement/provisioning, VID:PID changes, or any other
persistent device-state modification. The supported runtime remains
factory-preserving and expects the Windows factory path to remain usable.
