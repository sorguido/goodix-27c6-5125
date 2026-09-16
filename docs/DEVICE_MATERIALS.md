<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Preparing the device-specific material set

The Goodix `27c6:5125` runtime needs five files from the same physical reader:

```text
goodix-material/
├── target-material-manifest.json
├── transport-material.bin
├── target-config-90.bin
├── gfusb.dll
└── fdt-cache.bin
```

The tools below recover existing OEM material and validate it. They do not
generate a new PSK, provision the reader, flash firmware, enter IAP, invoke
ClearApp, write OTP, or change the VID:PID. Keep every generated file and USB
capture outside the repository and outside cloud-synchronized folders.

The qualified OEM package uses Goodix driver `1.1.125.14`. Its `gfusb.dll` is
5,771,496 bytes with SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
That DLL is a release compatibility boundary, not a per-reader identity pin.

## Step 1 — Prepare Windows OEM

Use Windows with the OEM Goodix driver and the same physical fingerprint
reader that Linux will use. An existing Windows installation or a Windows VM
with USB passthrough is suitable.

Before starting, confirm the target identity in Windows:

```powershell
Get-PnpDevice -PresentOnly | Select-String 'VID_27C6&PID_5125'
```

If using a VM, start it without the reader, start the capture described in
Step 3, and attach the reader once. Allow the normal OEM stack to initialize
it. Do not use Goodix maintenance or provisioning functions.

## Step 2 — Collect the OEM files

Create a private working directory:

```powershell
New-Item -ItemType Directory -Force C:\GoodixMaterialWork
```

The OEM stack must already have created:

```text
C:\ProgramData\Goodix\Goodix_Cache.bin
C:\ProgramData\Goodix\goodix.dat
```

Copy `goodix.dat` unchanged and rename only the copy:

```powershell
Copy-Item 'C:\ProgramData\Goodix\goodix.dat' 'C:\GoodixMaterialWork\fdt-cache.bin'
```

`fdt-cache.bin` must be exactly 13,520 bytes. Leave `Goodix_Cache.bin` in its
canonical location: the exporter reads it there and Windows DPAPI decrypts it
in its original OEM environment.

Copy the qualified `gfusb.dll` from the same OEM driver package to:

```text
C:\GoodixMaterialWork\gfusb.dll
```

Do not download an arbitrary DLL or substitute files from another reader.

## Step 3 — Start the USBPcap capture

Install Wireshark/TShark with USBPcap support and list interfaces:

```powershell
tshark -D
```

Start capture on the USB controller before the OEM stack initializes or the VM
attaches the reader. After Windows has initialized the reader, stop capture and
save it as:

```text
C:\GoodixMaterialWork\oem-init.pcapng
```

The same capture is used in Steps 6 and 7. Keep it private. If the correct
USBPcap interface cannot be identified, capture the plausible interfaces and
select the target traffic offline; do not guess protocol bytes.

## Step 4 — Export transport material on Windows

Keep these public tool files together on Windows:

```text
tools\device-materials\Export-Goodix5125TransportMaterial.ps1
tools\device-materials\_Export-Goodix5125TransportMaterial.Core.ps1
```

Open PowerShell as Administrator in that directory and run:

```powershell
.\Export-Goodix5125TransportMaterial.ps1 -Preflight
.\Export-Goodix5125TransportMaterial.ps1 -SelfTest
.\Export-Goodix5125TransportMaterial.ps1 `
  -OutputPath C:\GoodixMaterialWork\transport-material.xfr
```

The result is an 88-byte `G5125XFR` staging record. It contains the existing
reader secret recovered through DPAPI. The exporter does not print the secret
or contact the USB reader. `transport-material.xfr` is sensitive and is not a
runtime file; do not rename it to `.bin`.

Transfer these private inputs to Linux:

```text
transport-material.xfr
gfusb.dll
fdt-cache.bin
oem-init.pcapng
```

## Step 5 — Finalize transport material on Linux

Create private directories outside Git:

```bash
mkdir -p "$HOME/goodix-material-work" "$HOME/goodix-material"
chmod 700 "$HOME/goodix-material-work" "$HOME/goodix-material"
chmod 600 "$HOME/goodix-material-work/transport-material.xfr"
```

The finalizer requires Fedora's `python3-cryptography` package. Install that
package through your normal system-administration process, then run:

```bash
python3 tools/device-materials/Finalize-Goodix5125TransportMaterial.py --self-test
python3 tools/device-materials/Finalize-Goodix5125TransportMaterial.py \
  --transfer "$HOME/goodix-material-work/transport-material.xfr" \
  --oem-pe "$HOME/goodix-material-work/gfusb.dll" \
  --output "$HOME/goodix-material/transport-material.bin"
```

The tool validates `G5125XFR`, parses the qualified DLL as inert bytes, derives
the E4 validator, and writes a new 88-byte mode-`0600` `G5125POC` record. It
does not execute the DLL or open the reader.

## Step 6 — Extract CONFIG90 from the capture

Run the synthetic self-test and then the offline extraction:

```bash
python3 tools/device-materials/Extract-Goodix5125Config90.py --self-test
python3 tools/device-materials/Extract-Goodix5125Config90.py \
  --pcap "$HOME/goodix-material-work/oem-init.pcapng" \
  --output "$HOME/goodix-material/target-config-90.bin"
```

The extractor reconstructs host-to-device USBPcap bulk traffic, accepts only a
valid Goodix A0 logical `0x90` command with a 224-byte body and valid arithmetic
finalizer, and fails if distinct valid candidates are present. Identical
duplicates are allowed. Output is atomic, mode `0600`, and never overwrites an
existing file.

## Step 7 — Extract A2, chip82, and OTP A6 response pins

Use the same private capture:

```bash
python3 tools/device-materials/Extract-Goodix5125DeviceResponses.py --self-test
python3 tools/device-materials/Extract-Goodix5125DeviceResponses.py \
  --pcap "$HOME/goodix-material-work/oem-init.pcapng" \
  --output "$HOME/goodix-material-work/device-response-pins.json"
```

This offline tool reconstructs device-to-host bulk traffic and requires valid
Goodix A0 frames with exact typed controls and body lengths:

| Response | Control | Body length |
| --- | --- | ---: |
| A2 | `0xa2` | 3 bytes |
| chip82 | `0x82` | 4 bytes |
| OTP A6 | `0xa6` | 64 bytes |

Zero candidates fail. Repeated byte-identical bodies are accepted; differing
valid bodies in any class fail as ambiguous. Raw bodies are not printed or
stored. The output contains only SHA-256 digests and occurrence counts.

`device-response-pins.json` is an intermediate mode-`0600` file. It is
**not a sixth file in the runtime bundle**. Keep it in the work directory, not
in `goodix-material/`.

## Step 8 — Generate the per-reader manifest

Copy the unchanged qualified DLL and cache into the final staging directory:

```bash
cp "$HOME/goodix-material-work/gfusb.dll" "$HOME/goodix-material/gfusb.dll"
cp "$HOME/goodix-material-work/fdt-cache.bin" "$HOME/goodix-material/fdt-cache.bin"
chmod 600 "$HOME/goodix-material/gfusb.dll" "$HOME/goodix-material/fdt-cache.bin"
```

Generate the manifest directly from the final files and response-pin output:

```bash
python3 tools/device-materials/Generate-Goodix5125MaterialManifest.py --self-test
python3 tools/device-materials/Generate-Goodix5125MaterialManifest.py \
  --transport "$HOME/goodix-material/transport-material.bin" \
  --config90 "$HOME/goodix-material/target-config-90.bin" \
  --fdt-cache "$HOME/goodix-material/fdt-cache.bin" \
  --response-pins "$HOME/goodix-material-work/device-response-pins.json" \
  --output "$HOME/goodix-material/target-material-manifest.json"
```

The generator validates sizes, transport header, CONFIG90 finalizer, FDT cache
CRC, and OTP-response digest against the first 64 cache bytes. It computes the
transport, CONFIG90, and cache digests from the user's actual files. The output
is atomically created with mode `0600`; an existing manifest is never replaced.

Legacy manual `--a2-response-hex`, `--chip82-response-hex`, and
`--otp-a6-response-hex` arguments remain available for reviewed workflows, but
all three are required together and cannot be mixed with `--response-pins`.

## Step 9 — Verify the final five-file package

The final directory must contain exactly:

```text
goodix-material/
├── target-material-manifest.json
├── transport-material.bin
├── target-config-90.bin
├── gfusb.dll
└── fdt-cache.bin
```

Check names, sizes, modes, and local digests:

```bash
find "$HOME/goodix-material" -maxdepth 1 -type f -printf '%f %s bytes mode=%m\n' | sort
sha256sum "$HOME/goodix-material"/*
```

Expected protocol sizes include transport 88 bytes, CONFIG90 224 bytes, and
FDT cache 13,520 bytes. The digest values are specific to this bundle; they do
not need to match the development reader.

## Step 10 — Import and install

Follow [Installation](INSTALLATION.md). The material import command is:

```bash
deployment/managed-install/manage.sh import-materials \
  "$HOME/goodix-material"
```

The importer applies root ownership and required modes. The runtime then
revalidates format, manifest-to-file integrity, protected filesystem metadata,
OTP/cache binding, the derived E4 validator, and live A2/chip82/OTP responses.
Do not weaken validation to force a mismatched bundle through.

## Cleanup and private retention

After successful import:

- keep an encrypted recovery copy of the five files only if needed for the
  same physical reader;
- remove `transport-material.xfr`, `device-response-pins.json`, and the capture
  when no longer needed, or archive them privately;
- never publish `Goodix_Cache.bin`, the staging record, captures, OEM material,
  secrets, fingerprint images, or templates;
- never reuse another reader's bundle.

## Troubleshooting

### OEM cache files are absent

The OEM driver has not initialized the reader in this Windows environment.
Confirm Device Manager and the exact `VID_27C6&PID_5125` device. Do not create
placeholder files.

### No valid CONFIG90 or response candidates were found

Confirm that capture began before OEM initialization and includes bulk traffic
for the target reader. A host-to-device frame cannot satisfy the response
extractor, and a device-to-host response cannot satisfy CONFIG90 extraction.
Do not cut bytes manually from Wireshark.

### Multiple distinct candidates were found

The capture is ambiguous. Repeat one clean, bounded OEM initialization capture
instead of selecting the first occurrence.

### The finalizer rejects `gfusb.dll`

Use the exact qualified DLL listed at the start of this guide. Do not bypass
the DLL compatibility boundary.

### OTP/cache binding fails

The capture and `fdt-cache.bin` do not describe the same initialization/device,
or one input is corrupt. Recollect them from the same physical reader.

### Can I generate a random PSK or run ClearApp?

No. The supported workflow recovers existing factory-preserving material and
never provisions or changes device state.

## Transport record reference

`G5125XFR` is the temporary 88-byte Windows transfer envelope containing the
DPAPI-recovered 32-byte secret and an integrity digest. `G5125POC` is the final
88-byte runtime record containing the same secret and the validator derived
from the qualified DLL producer data. Neither format provisions the reader.
