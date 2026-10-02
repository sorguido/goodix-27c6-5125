<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 5125 Material Builder

The Goodix 5125 Material Builder is a Python/Tkinter application that prepares
the optional legacy five-file device-material bundle for a Goodix USB fingerprint
reader `27c6:5125`. The Linux driver is self-contained and needs no bundle for a
fresh installation; this tool serves the legacy compatibility source only.

The supported workflow runs inside the qualified Windows VM and covers embedded
USBPcap acquisition, target and APP validation, CONFIG90/A2/CHIP82/A6 extraction,
DPAPI recovery, transport-material generation, manifest generation and final
five-file validation. The Linux installer/runtime independently validates the
resulting bundle and remains the final authority on bundle validity.

The application does **not** flash firmware, enter IAP, invoke ClearApp, write
OTP, replace or reprovision the PSK, change VID:PID, enroll a fingerprint, or
send maintenance commands to the reader. USBPcap observes the ordinary OEM
initialization performed inside the qualified Windows VM.

## What the application produces

A successful run creates exactly:

```text
goodix-5125-materials/
├── target-material-manifest.json
├── transport-material.bin
├── target-config-90.bin
├── gfusb.dll
└── fdt-cache.bin
```

Transfer that whole folder privately to Linux at:

```text
~/goodix-5125-materials
```

Do not include the raw USB capture or the original Windows source files in that
folder.

## Privacy and safety

The source files, raw USB capture and final bundle are private material.

- Use only material from your own reader inside its qualified Windows VM running
  the qualified Goodix OEM driver.
- Run the application as the original normal Windows user inside that VM. DPAPI
  recovery depends on that exact user/context.
- **DO NOT TOUCH THE SENSOR during acquisition.**
- Do not upload the capture, `Goodix_Cache.bin`, `goodix.dat`, `gfusb.dll`,
  the generated bundle, PSK material or reader-specific hashes.
- The application has no upload or telemetry feature.
- Do not substitute files from another reader or bypass a failed validation.

For the canonical material contract, see
[`docs/DEVICE_MATERIALS.md`](../../docs/DEVICE_MATERIALS.md).

## Requirements

Use the same physical Goodix reader inside the existing qualified Windows VM
with USB passthrough, the qualified Goodix OEM driver, and the original Windows
user/DPAPI context. Native or bare-metal Windows acquisition is outside the
supported workflow.

Current qualified OEM baseline:

```text
VID:PID      27c6:5125
APP          GF_ST411SEC_APP_12509
OEM driver   1.1.125.14
```

The application expects access to these three OEM source files, normally found
at:

```text
C:\ProgramData\Goodix\Goodix_Cache.bin
C:\ProgramData\Goodix\goodix.dat
C:\Windows\System32\drivers\UMDF\gfusb.dll
```

If `ProgramData` is hidden, type `C:\ProgramData\Goodix` directly into the
File Explorer address bar.

Other requirements:

- administrator/UAC access for USBPcap installation and capture lifecycle;
- 64-bit Python with Tkinter;
- the `cryptography` Python package;
- network access during initial Python dependency installation and, if needed,
  USBPcap installation.

The project recommends the validated **64-bit Python 3.10+ with Tkinter**
baseline. This is a recommendation, not a hard version gate: other Python 3
versions are not intentionally blocked, although they may not have been tested.

USBPcap **1.5.4.0** is project-pinned. The application can download the official
installer, verify its pinned SHA-256 and launch its normal interactive installer.

## First-time Python setup

Install Python for Windows before trying to launch the Material Builder.

1. Download Python from the official Windows page:
   <https://www.python.org/downloads/windows/>
2. Install it normally.
3. Close and reopen PowerShell.
4. Confirm that the Python launcher is available:

   ```powershell
   py --version
   ```

5. Prepare the application's private Python environment once and install its
   only non-standard Python dependency:

   ```powershell
   py -3 -m venv "$env:LOCALAPPDATA\Goodix5125BuilderPython"
   & "$env:LOCALAPPDATA\Goodix5125BuilderPython\Scripts\python.exe" -m pip install cryptography
   if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
   ```

## Download the project source

1. Open the project's GitHub page.
2. Select the `main` branch.
3. Choose **Code → Download ZIP**.
4. Extract the ZIP archive to a local folder.
5. Copy the full path of the extracted project folder.
6. When PowerShell later shows:

   ```text
   Full path to the updated Goodix source folder:
   ```

   paste that full folder path and press **Enter**.

Use the project root folder — the one containing `tools`, `docs` and the
other repository files — not the `tools\windows_material_builder` subfolder.

## Launch the Material Builder

Open a normal, unelevated PowerShell window and run:

```powershell
Set-Location -ErrorAction Stop -LiteralPath (Read-Host 'Full path to the updated Goodix source folder')
& "$env:LOCALAPPDATA\Goodix5125BuilderPython\Scripts\python.exe" -m tools.windows_material_builder
if ($LASTEXITCODE -ne 0) { throw 'STOP: builder exited with an error; report the safe diagnostic code.' }
```

The main GUI must remain unelevated. Windows will request elevation only for
operations that require it.

## Build the five-file bundle

### 1. Select the OEM source folder

Prepare a private folder containing unchanged copies of:

```text
Goodix_Cache.bin
goodix.dat
gfusb.dll
```

Select that folder in the application. The application validates the source
material before continuing.

### 2. Check prerequisites

Continue to prerequisites.

If USBPcap is not installed, use **Install USBPcap**. The application downloads
the pinned official installer, verifies it, and opens the normal interactive UAC
installer. Accept the upstream licenses and normal installer choices yourself.

Reboot Windows after USBPcap installation, then relaunch the Material Builder
normally and select the source folder again.

### 3. Identify the capture controller

If more than one USBPcap capture controller is available, identify the one that
contains the Goodix reader. Do not simply select the first controller.

The manual acquisition guide contains additional controller-mapping guidance:
[Building your device-material bundle](../../docs/learning/11_building_your_device_material_bundle.md).

### 4. Start with Goodix detached

Detach the Goodix reader from the Windows VM guest and disable automatic
reattachment if your hypervisor provides that feature.

Close Windows fingerprint/enrollment settings.

Press **Recheck**, then **Start capture**.

USBPcap may display a UAC prompt. Accept it and keep the reader detached while
capture startup is pending.

### 5. Attach only when instructed

Only when the application displays:

```text
Now attach the Goodix to this Windows VM
```

attach that one reader.

Attach no other USB device during the acquisition and **DO NOT TOUCH THE
SENSOR**.

The normal acquisition window is 30 seconds.

### 6. Allow the application to stop and analyze capture

At the end of the capture window, Windows requests UAC for the bounded
`taskkill.exe` stop used by the application.

Accept the prompt and wait for automatic analysis.

A valid acquisition reaches **Diagnose and build** with:

```text
Capture container, target identity and APP12509 — valid
CONFIG90 — valid and unambiguous
A2       — valid and unambiguous
CHIP82   — valid and unambiguous
A6       — valid and unambiguous
```

### 7. Build the private bundle

When all required evidence is valid, press:

```text
Build private bundle
```

The application then:

- cross-checks A6 against the FDT cache;
- recovers the existing PSK through Windows DPAPI in the original user context inside the qualified VM;
- derives the canonical transport binding;
- creates `transport-material.bin`;
- creates the canonical ten-field manifest;
- copies the qualified OEM inputs into their final canonical names;
- validates the complete five-file bundle before publication.

Success is shown as **Private bundle validated** and lists exactly the five
canonical filenames.

### 8. Optional bounded retry

If target/APP and CONFIG90 are valid but only A2/CHIP82/A6 evidence is missing,
the application may offer **Retry with extended initialization window**.

That is one explicit 60-second retry. Detach the reader, repeat the preflight and
controller selection, press **Recheck**, start a new capture and attach only at
the prompt.

There is no automatic retry or third timing tier.

`CONFIG90_MISSING` does **not** use this retry path. Stop and investigate the
capture/environment instead.

## Transfer to Fedora

Open the generated `goodix-5125-materials` folder and transfer the whole folder
privately to the Linux user's home directory as:

```text
~/goodix-5125-materials
```

Leave the raw capture outside the bundle.

Then continue with [Installation](../../docs/INSTALLATION.md). The Linux
installer independently validates the bundle before importing it.

## Run storage and retention

Each explicit acquisition gets its own private run directory:

```text
%LOCALAPPDATA%\Goodix5125MaterialBuilder\runs\run-<unique-id>\
  raw\oem-init.pcap
  diagnostics\
  goodix-5125-materials\
    target-material-manifest.json
    transport-material.bin
    target-config-90.bin
    gfusb.dll
    fdt-cache.bin
```

The final bundle directory appears only after successful validation. Existing
bundles and captures are not overwritten.

Application-created run directories are restricted to the current user and
SYSTEM.

Keep a private backup of the final five-file bundle if you want to reinstall the
same reader later. It is not portable to another physical reader and does not
contain enrolled fingerprint templates.

## If something fails

The application fails closed. Missing, ambiguous or inconsistent evidence does
not produce a valid final bundle.

Important examples:

- unexpected reader or APP identity → stop;
- ambiguous material → stop;
- source/DPAPI/material binding failure → correct the specific source/context
  problem;
- `CONFIG90_MISSING` → retain the capture and investigate; do not substitute a
  file from another reader;
- unclear USB controller mapping → stop and resolve the mapping;
- denied or failed capture-stop UAC → cleanup is not accepted as successful.

On failure, close the application and manually detach the Goodix reader if
necessary. Keep private evidence only as long as needed for troubleshooting.

If USBPcap was installed solely for this workflow and you want to remove it, use
Windows **Installed apps → USBPcap → Uninstall** and reboot. Do not remove a
pre-existing USBPcap installation merely because the Material Builder no longer
needs it.

For troubleshooting, share only non-secret diagnostic codes and bounded
lifecycle facts. Never publish the capture, caches, DLL, bundle, PSK or
reader-specific hashes.

## Read-only capture diagnosis

A retained local capture can be analyzed without DPAPI recovery or bundle
construction:

```powershell
& "$env:LOCALAPPDATA\Goodix5125BuilderPython\Scripts\python.exe" -m tools.windows_material_builder --diagnose 'C:\private\oem-init.pcap'
```

The diagnostic path prints only bounded safe facts and diagnostic codes.

## Technical references

- [Device-material contract](../../docs/DEVICE_MATERIALS.md)
- [Manual acquisition reference](../../docs/learning/11_building_your_device_material_bundle.md)
- [Installation](../../docs/INSTALLATION.md)
- [Technical audit and provenance](AUDIT.md)
