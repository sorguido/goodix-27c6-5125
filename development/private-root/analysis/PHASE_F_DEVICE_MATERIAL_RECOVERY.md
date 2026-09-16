# Phase F private recovery review: device-specific material

## Decision

```text
PROCEDURE_SEMANTICS=RECOVERED
ORIGINAL_WINDOWS_EXPORTER=RECOVERED
ORIGINAL_TRANSFER_RECORD_MODULE=RECOVERED
ORIGINAL_LINUX_FINALIZER=RECOVERED
NEW_EXPORTER_ARCHITECTURE_REQUIRED=false
REAL_SECRET_BYTES_READ_OR_PRINTED=false
PUBLIC_REPOSITORY_TOUCHED=false
```

The previously reported broad `HUMAN_REQUIRED` conclusion was incorrect. The
validated procedure and its source were recoverable from private local session
evidence. No real secret extraction or Windows/USB action was needed for this
review. A future live rerun remains an operator gate because it handles the
real DPAPI plaintext and a physical USB device.

## Evidence searched

- all reachable Git refs with `git log --all -S` and `-G` for
  `G5125XFR`, `G5125POC`, `Goodix_Cache.bin`, `CryptUnprotectData`,
  `PSKCacheSwitch`, and `transport-material.bin`;
- current ignored `red_tag/` analysis, captures, operator kits, source, and
  documentation, including D230 onward and specifically D236, D255, D261,
  D274, and D278;
- unreachable objects in the pre-orchestration private-repository backup;
- archived project workspaces and the protected-material backup, using only
  filenames, sizes, timestamps, and already-published digests for protected
  payloads;
- local Codex session transcripts for July and August 2026.

The decisive source is the 29 July session transcript at:

```text
/home/guido/.codex/sessions/2026/07/29/
rollout-2026-07-29T07-43-40-019fac66-698c-7362-9b50-96b4bc1bb1a6.jsonl
```

It contains the complete patch history for the original Windows exporter,
transfer-record module, and Linux finalizer, plus the execution/closure record.
The recovered source is archived at `red_tag/recovered/device-materials/`.

## Date reconciliation

The technical chain described in the corrective is supported, but the retained
evidence does not support 26 August 2026 as the execution date. The session
record and the existing protected file timestamp place the successful export,
transfer, finalization, and import on 29 July 2026. The subsequent live E4
evidence records `runtime_psk_e4_binding_status=match`.

The 26 August material in the private archive is associated with D274 native
multiframe qualification and baseline approval. It contains no
`G5125XFR`, `CryptUnprotectData`, or DPAPI-export evidence. D255, dated 22
August, captured a 332-byte `Goodix_Cache.bin` and 13,520-byte `goodix.dat`, but
explicitly records `psk_or_secret_exported=false`.

The statements that the Windows VM was fresh and that the cache was newly
created by that VM are preserved as operator-supplied historical facts. The
retained machine-readable evidence establishes a virtualized Windows/OEM
environment, canonical cache use, exact export semantics, successful import,
and later same-device E4 match, but it does not independently prove the VM or
cache creation timestamp.

## Answers to the required questions

### 1. Artifact generated or exposed by the Windows VM

The OEM stack exposed the canonical
`C:\ProgramData\Goodix\Goodix_Cache.bin`; the retained live record identifies
it as 332 bytes. The recovered exporter consumed that cache and wrote an
88-byte `G5125XFR` transfer record. The OEM stack also produced
`C:\ProgramData\Goodix\goodix.dat`, later copied as `fdt-cache.bin`.

The execution supported by retained evidence occurred on 29 July, not 26
August. No protected payload bytes were inspected during this review.

### 2. Exact DPAPI program and invocation

The program was:

```text
poc/goodix5125/windows/Export-Goodix5125TransportMaterial.ps1
```

The real-mode invocation was:

```powershell
.\Export-Goodix5125TransportMaterial.ps1 `
  -RealExport `
  -OutputPath <absolute-local-non-cloud-new-path> `
  -ConsentPhrase I_AUTHORIZE_D191_LOCAL_DPAPI_EXPORT
```

Windows PowerShell used an embedded C# P/Invoke declaration for
`CryptUnprotectData`. The cache was opened once with
`FILE_FLAG_OPEN_REPARSE_POINT`, bounded to `(8, 1 MiB]`, and split into the
encrypted blob plus its final eight-byte trailer. Optional entropy was:

```text
H1 = SHA256(trailer)
H2 = SHA256(H1[0:16] || fixed-16-byte-mix)
entropy = H1[16:32] || H2
```

The unprotected result had to be exactly 32 bytes and nonzero.

### 3. Retention status of the utility

The original source is not present in the current reachable Git tree or the
pre-orchestration Git-object backup. It was created and amended in the private
workspace and executed, and its complete patch stream survived in the local
Codex session archive. It has now been reconstructed under the ignored private
`red_tag/` boundary. It was therefore retained as session-level source
evidence, not as a reachable repository commit.

### 4. Historical `G5125XFR` wrapping

The 88-byte record consists of:

```text
offset  length  meaning
0       24      little-endian <8sHHHHHHI> header
24      32      DPAPI plaintext device secret
56      32      SHA256(record[0:56])
```

Header values are magic `G5125XFR`, version 1, flags 0, VID `0x27c6`, PID
`0x5125`, secret length 32, reserved 0, and payload length 32. The final digest
provides integrity only; the record is plaintext secret material.

### 5. Relationship and migration to `G5125POC`

There was no silent byte-for-byte rename. `G5125XFR` was designed as a
short-lived Windows-to-Linux envelope. The Linux finalizer parsed it, extracted
the exact 32-byte secret, derived the device validator from the hash-pinned OEM
DLL producer seeds, and built the distinct runtime record:

```text
offset  length  meaning
0       24      G5125POC v1 header
24      32      device secret
56      32      derived device validator
```

The `G5125POC` header encodes magic, version, 24-byte header length, VID, PID,
material kind 1, 32-byte secret length, 32-byte validator length, and reserved
0. The conversion and root-only import occurred as part of the same 29 July
transfer procedure. `G5125XFR` was never the production runtime format; the
validator-bearing record exists to permit same-device E4 binding validation
before TLS use.

### 6. Origins of the other four files

`gfusb.dll` and `fdt-cache.bin` are direct OEM artifacts: the former is copied
unchanged from the exact Goodix driver package and the latter is a renamed,
content-identical copy of `C:\ProgramData\Goodix\goodix.dat`.

`target-config-90.bin` is project-extracted, not a standalone Windows file. It
is the unique 224-byte body of the outbound A0 control-`0x90` message selected
from the canonical OEM USB capture.

`target-material-manifest.json` is project-generated metadata built from the
qualified evidence, hashes, response validators, and DAC values. It is not an
OEM Windows artifact.

### 7. Exactness of reconstruction

Yes. The exporter, transfer parser, record layouts, consent string, canonical
cache path, entropy derivation, DPAPI call, validation bounds, ACL/atomic-write
behavior, finalizer, and successful import sequence are recovered exactly
enough to document the validated method without inventing steps.

One implementation boundary remains relevant only if the tools are to be
redistributed: the historical finalizer imports the old `bind` API and old
root importer, while the retained current binding helper and managed importer
have different interfaces. This does not make the procedure unknowable and
does not justify a new architecture. It requires a focused compatibility and
licensing review before publishing runnable acquisition tooling.

## Five-file provenance table

| File | Origin | Source artifact/input | Transformation | Tool/script | Validation | Current format | Historical format | Reproducible from current evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `target-material-manifest.json` | Project-generated | Qualified target responses, hashes, DAC tuples, and material metadata | Deterministic JSON generation | Retained project manifest/finalization logic | 2,305 bytes; SHA-256 `1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15`; loader checks embedded invariants | JSON manifest | Same purpose | yes |
| `transport-material.bin` | Project-generated from OEM secret | DPAPI blob in `Goodix_Cache.bin`, cache trailer, and producer seeds from exact `gfusb.dll` | Windows DPAPI unprotect to 32-byte secret; `G5125XFR` staging; Linux binding/finalization to runtime record | Recovered exporter, `transfer_record.py`, `finalize_transfer.py`, historical binder/importer | 88 bytes; SHA-256 `eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75`; transfer digest; root-store byte comparison; E4 binding match | `G5125POC` v1 | `G5125XFR` v1 was transient staging, not runtime | yes, for the same reader with an operator-controlled Windows run |
| `target-config-90.bin` | Project-extracted | Canonical OEM USB capture | Select exactly one outbound A0 control-`0x90` body | Retained USBPCap parser/extraction logic | 224 bytes; SHA-256 `e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82`; finalizer and DAC checks | Raw control body | Same | yes |
| `gfusb.dll` | OEM | Goodix driver package version `1.1.125.14` | Copy as-is | File copy; bounded inert PE parser at runtime | 5,771,496 bytes; SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`; bounded producer-seed extraction | OEM PE/DLL | Same | yes, from the exact lawfully obtained package |
| `fdt-cache.bin` | OEM | `C:\ProgramData\Goodix\goodix.dat` | Copy and rename only | File copy; bounded cache parser at runtime | 13,520 bytes; SHA-256 `9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2`; layout, CRC, OTP hash, FDT checks | OEM cache renamed for runtime | `goodix.dat` | yes, for the same reader after OEM initialization |

## Cause of the earlier false negative

The earlier review treated absence from the current publishable tree and
reachable Git history as absence from the project. It also relied too heavily
on D255, which deliberately captured cache evidence with
`psk_or_secret_exported=false`. The decisive pre-D230 implementation survived
in the local session archive rather than Git or the later `red_tag/` snapshot.

The corrected public documentation is `docs/DEVICE_MATERIALS.md`. It presents
the current product state without private milestone chronology and does not
depend on this private report or on any file under `red_tag/`.

