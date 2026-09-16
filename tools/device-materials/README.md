<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Device-material helper tools

This directory contains the public helper tools used to recover and prepare the
device-specific runtime material of a Goodix USB `27c6:5125` reader.

These tools do **not** provision a new PSK, write firmware, run IAP/ClearApp,
write OTP, or modify persistent reader state.

## Files

- `Export-Goodix5125TransportMaterial.ps1` — user-facing Windows wrapper.
- `_Export-Goodix5125TransportMaterial.Core.ps1` — recovered, reviewed DPAPI
  implementation used by the wrapper. Keep it beside the wrapper.
- `Finalize-Goodix5125TransportMaterial.py` — Linux finalizer that converts the
  temporary `G5125XFR` record into the runtime `G5125POC` file.
- `Extract-Goodix5125Config90.py` — offline Linux extractor that reads a Windows
  USBPcap `.pcapng` capture and writes the validated 224-byte
  `target-config-90.bin` body.
- `Generate-Goodix5125MaterialManifest.py` — validates the three reader-specific
  files and creates their integrity/binding manifest.

## Transport material: Windows

The Windows exporter reads only the canonical OEM cache:

```text
C:\ProgramData\Goodix\Goodix_Cache.bin
```

Open **PowerShell as Administrator**, enter this directory, and run:

```powershell
.\Export-Goodix5125TransportMaterial.ps1 -Preflight
.\Export-Goodix5125TransportMaterial.ps1 -SelfTest
.\Export-Goodix5125TransportMaterial.ps1 `
  -OutputPath C:\GoodixMaterialWork\transport-material.xfr
```

The final command creates an 88-byte `G5125XFR` staging record. That file
contains the recovered device secret and must be kept private. It is not yet the
runtime `transport-material.bin`.

## Transport material: Linux finalization

Install the Python crypto dependency once:

```bash
sudo dnf5 install python3-cryptography
```

Run the secret-free synthetic self-test:

```bash
python3 tools/device-materials/Finalize-Goodix5125TransportMaterial.py --self-test
```

Then finalize the Windows staging record. Use absolute paths:

```bash
python3 tools/device-materials/Finalize-Goodix5125TransportMaterial.py \
  --transfer /home/you/goodix-material-work/transport-material.xfr \
  --oem-pe /home/you/goodix-material-work/gfusb.dll \
  --output /home/you/goodix-material/transport-material.bin
```

Success prints:

```text
GOODIX_TRANSPORT_FINALIZER=PASS
size=88
```

The output file is mode `0600`. The temporary `.xfr` file can be removed after
successful finalization and backup according to `docs/DEVICE_MATERIALS.md`.

## CONFIG90 extraction from a Windows USB capture

Create the USB capture on Windows with Wireshark/TShark and USBPcap, starting
the capture **before** the OEM stack initializes the same physical reader.
Keep the resulting `.pcapng` private and transfer it to Linux.

First run the extractor's synthetic self-test:

```bash
python3 tools/device-materials/Extract-Goodix5125Config90.py --self-test
```

Expected result:

```text
GOODIX_CONFIG90_SELFTEST=PASS
```

Then extract the CONFIG90 body:

```bash
python3 tools/device-materials/Extract-Goodix5125Config90.py \
  --pcap /home/you/goodix-material-work/oem-init.pcapng \
  --output /home/you/goodix-material/target-config-90.bin
```

The extractor works offline. It parses pcapng/USBPcap directly with the Python
standard library, reconstructs host-to-device Goodix A0 frames, selects logical
control `0x90`, requires a 224-byte body, validates A0 framing/checksum and the
CONFIG90 finalizer, and fails closed if more than one distinct valid CONFIG90
body is present. It never opens or writes the USB reader.

On success it prints:

```text
GOODIX_CONFIG90_EXTRACTION=PASS
size=224
sha256=<captured CONFIG90 SHA-256>
```

The output is written atomically with mode `0600` and an existing output file is
never overwritten.

The printed digest identifies *your* extracted CONFIG90. It is recorded in the
bundle manifest; it is not compared with a development-reader digest.

## Generate the per-reader manifest

After obtaining the three response bodies (A2: 3 bytes, chip82: 4 bytes, OTP
A6: 64 bytes) from the same OEM initialization trace, run:

```bash
python3 tools/device-materials/Generate-Goodix5125MaterialManifest.py \
  --transport /home/you/goodix-material/transport-material.bin \
  --config90 /home/you/goodix-material/target-config-90.bin \
  --fdt-cache /home/you/goodix-material/fdt-cache.bin \
  --a2-response-hex <6-hex-digits> \
  --chip82-response-hex <8-hex-digits> \
  --otp-a6-response-hex <128-hex-digits> \
  --output /home/you/goodix-material/target-material-manifest.json
```

The generator checks record headers, sizes, CONFIG90 finalizer, cache CRC, and
OTP/cache agreement, then hashes the user's actual files. The repository does
not yet include a supported semantic extractor for the three inbound response
bodies; obtain them with a reviewed protocol decoder. Do not guess them. This
is an explicit remaining acquisition limitation, not a reason to reuse the
development reader's values.

Self-test it with
`python3 tools/device-materials/Generate-Goodix5125MaterialManifest.py --self-test`.

## Validation status

The driver and intended fingerprint workflows have been demonstrated working on
the qualified development system. The public source/release path has been tested
extensively offline and in part end-to-end, but not every public acquisition and
installation path has been exercised on independent hardware.

`Extract-Goodix5125Config90.py` currently has a passing synthetic self-test for
fragmented USBPcap frames, repeated identical CONFIG90 frames, ambiguous
distinct frames, invalid CONFIG90 finalizers, and atomic mode-`0600` output. A
real historical capture exists in the private development archive, but the
public extractor has not yet been independently exercised against a second
reader's fresh capture.

If you encounter a reproducible problem, open a GitHub issue with the tool
version, command used, non-secret error output, OS details and relevant hardware
identity. **Do not attach captures, caches, secrets, fingerprint images or other
protected material to an issue.**

## Security notes

- Never commit `Goodix_Cache.bin`, `transport-material.xfr`,
  `transport-material.bin`, `.pcapng` captures or `target-config-90.bin`.
- Never paste the recovered 32-byte secret into a terminal, issue, chat, log,
  or documentation.
- Keep all generated material outside the repository and outside cloud-sync
  folders.
- The transport finalizer accepts only the pinned OEM `gfusb.dll` size and
  SHA-256 and parses it with bounded PE reads; it does not execute OEM code.
- The CONFIG90 extractor is offline-only and contains no USB/device access.
