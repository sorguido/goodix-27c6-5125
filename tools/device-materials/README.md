<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Device-material helper tools

This directory contains the public helper tools used to recover and finalize the
existing transport material of a Goodix USB `27c6:5125` reader.

These tools do **not** provision a new PSK, write firmware, run IAP/ClearApp,
write OTP, or modify persistent reader state.

## Files

- `Export-Goodix5125TransportMaterial.ps1` — user-facing Windows wrapper.
- `_Export-Goodix5125TransportMaterial.Core.ps1` — recovered, reviewed DPAPI
  implementation used by the wrapper. Keep it beside the wrapper.
- `Finalize-Goodix5125TransportMaterial.py` — Linux finalizer that converts the
  temporary `G5125XFR` record into the runtime `G5125POC` file.

The Windows exporter reads only the canonical OEM cache:

```text
C:\ProgramData\Goodix\Goodix_Cache.bin
```

The Linux finalizer additionally reads the qualified OEM `gfusb.dll` as inert
bytes. It never loads or executes the DLL.

## Windows

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

## Linux

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

## Security notes

- Never commit `Goodix_Cache.bin`, `transport-material.xfr`, or
  `transport-material.bin`.
- Never paste the recovered 32-byte secret into a terminal, issue, chat, log,
  or documentation.
- Keep all generated material outside the repository and outside cloud-sync
  folders.
- The finalizer accepts only the pinned OEM `gfusb.dll` size and SHA-256 and
  parses it with bounded PE reads; it does not execute OEM code.
