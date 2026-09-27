<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 5125 Material Builder — development candidate

This English-language Python/Tkinter application prepares private device material
inside the **original qualified Windows VM**, as the **original normal user**.
It is not a supported release: real Windows validation is still required.
Use the [manual walkthrough](../../docs/learning/11_building_your_device_material_bundle.md)
as the independent acquisition reference. The Linux installer/runtime remains
the final authority on validity.

The app never sends Goodix commands, automates a hypervisor, enrolls a finger,
changes firmware or replaces a PSK. USBPcap observes ordinary OEM initialization.
**DO NOT TOUCH THE SENSOR during acquisition.** Captures can contain sensitive
material and stay private, on failure as well as success. No upload or telemetry.

## Before the Windows operator test

Use the exact development commit delivered with the operator report, copied
privately or checked out in a separate Windows source copy. Do not merge or
modify `main`. Keep OEM files outside that source copy. No executable packaging
or privileged application installation is required.

Starting VM state:

- The existing qualified Windows VM and OEM driver package 1.1.125.14 are intact.
- The original Windows user is signed in normally; the app must not be elevated.
- Goodix is detached from the guest and automatic USB attachment is disabled.
- Fingerprint/enrollment settings are closed; no finger contact is permitted.
- A private local source folder contains `Goodix_Cache.bin`, `goodix.dat`,
  `gfusb.dll`, copied unchanged from this qualified context.
- 64-bit Python 3.10+ with Tkinter is available. `cryptography` is the only
  non-standard-library Python dependency. Do not install Wireshark or TShark.

From a normal PowerShell window in the source root, prepare a virtual environment
once (this explicit dependency setup downloads Python packages):

```powershell
py -3 -m venv "$env:LOCALAPPDATA\Goodix5125BuilderPython"
& "$env:LOCALAPPDATA\Goodix5125BuilderPython\Scripts\python.exe" -m pip install cryptography
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
```

Then launch, also from the source root:

```powershell
& "$env:LOCALAPPDATA\Goodix5125BuilderPython\Scripts\python.exe" -m tools.windows_material_builder
```

## One operator procedure

1. Continue from Welcome. Select the three-file source folder. Expect the cache
   to be structurally valid, `goodix.dat` valid, and the DLL qualified. No secret
   or reader-specific digest is displayed.
2. Continue to prerequisites. The app checks the driver, CMD, pinned release,
   interfaces and reboot state. If absent, click **Install USBPcap**. The app
   downloads the pinned official installer, verifies its complete SHA-256, then
   opens the interactive UAC installer. Read and accept its licenses yourself.
   Keep **USBPcap Driver** and **USBPcapCMD** selected; leave the optional
   **Detect USB 3.0** component unchecked. No silent license acceptance occurs.
3. Reboot the Windows VM after installation. Relaunch normally and select the
   source folder again. The app retains the reboot requirement across launches
   and always returns through preflight. It does not automatically run at boot.
4. If multiple capture controllers exist, use the mapping procedure in the
   manual guide: match the exact reader's Device Manager connection/controller
   with the USBPcap tree while it is attached, then detach it through the
   hypervisor. Select that observed controller and confirm the mapping. The app
   never selects the first of multiple controllers. Stop if mapping is unclear.
5. Press **Recheck** while Goodix is detached. Then **Start capture**. USBPcap may
   request its own UAC prompt; the GUI and DPAPI remain unelevated. Do not attach
   Goodix while startup or UAC is pending.
6. **Only when the app says “Now attach the Goodix to this Windows VM”**, attach
   that one reader manually through the hypervisor's USB menu. Attach no other
   devices. **DO NOT TOUCH THE SENSOR.** The app observes exact target appearance,
   allows 30 seconds for OEM initialization, then stops and diagnoses the capture.
7. Review the individual CONFIG90/A2/chip82/A6 checks. **Build private bundle** is
   available only with complete evidence. It cross-checks A6/cache, uses Windows
   DPAPI in the original user context, derives the canonical transport binding,
   creates the exact manifest and validates all five files before publication.
8. Success lists exactly the five filenames. Open the bundle folder and transfer
   that whole `goodix-5125-materials` folder privately to Linux at
   `~/goodix-5125-materials`. Leave the raw capture outside it.

The 30-second settle allowance exceeds the under-eight-second typed-response
window in the read-only historical audit. It is an engineering bound, **not**
proof of initialization completeness: that historical capture still lacks
CONFIG90. All evidence gates remain mandatory. Attach timeout is 90 seconds;
capture startup timeout is 60 seconds and the independent worker has a
240-second ceiling. No repeated initialization or hidden attach retry occurs.

## Results, retention and rollback

Each explicit attempt gets a new private UUID directory under the Windows Local
AppData known folder:

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

The final folder appears only after validation and no-replace directory rename.
A failed write can leave a private `.incomplete-*` directory, never a final
bundle name. Existing bundles and raw captures are never overwritten or deleted.
ACLs restrict app-created directories to the current user and SYSTEM. Python
cleans mutable/native temporary buffers; it cannot guarantee erasure of every
immutable copy inside Python/cryptography memory.

**PASS_IF:** all source/evidence checks pass; the five-file bundle is validated;
the separate original capture remains; subsequent Linux installer validation
accepts it. The latter is a separate operator action, not performed by this app.

**FAIL_IF:** startup/stop fails, evidence is missing/ambiguous, material binding
fails, or the final bundle cannot be published. Diagnostics distinguish observed
facts, possible causes and actions. `CONFIG90_MISSING` is a legitimate negative
result; never reuse a different reader's file to bypass it.

**STOP_IF:** unexpected device identity, a request to modify reader factory state,
unclear controller mapping, unexpected reboot behavior or inability to preserve
the capture. Do not repeatedly attach the reader to try to force a success.

On failure, cancel/close the app and manually detach Goodix from the guest if
needed. Keep the raw capture and OEM inputs private. No Goodix driver or factory
state was modified by the app. If USBPcap was newly installed solely for this
test and must be rolled back, use Windows **Installed apps → USBPcap → Uninstall**
and reboot the VM; do not remove a pre-existing installation. The Python virtual
environment/source copy can be removed separately after exit; preserve Local
AppData runs. There is no automatic deletion of evidence or protected material.

Report only the tested commit, Windows/Python versions, PASS/FAIL, the diagnostic
code and the point of failure. Never send the capture, caches, bundle, DLL, hashes
or screenshots containing protected values.

## Offline development verification

From the source root, without Windows, USB or protected inputs:

```sh
python -m unittest tools.windows_material_builder.test_builder -v
```

The existing `deployment/test_material_native.c` loader can also validate the
builder's synthetic output via `GOODIX_MATERIAL_TEST_NATIVE`; see its build
comment. No production DLL pin is relaxed outside test mocks.

For a locally retained capture, a read-only diagnostic command prints safe facts
and codes only; it neither calls DPAPI nor builds a bundle:

```powershell
& "$env:LOCALAPPDATA\Goodix5125BuilderPython\Scripts\python.exe" -m tools.windows_material_builder --diagnose 'C:\private\oem-init.pcap'
```

No `.exe` packager is introduced. After Windows functional qualification, a
separate packaging review may consider an ordinary source archive plus a launch
shortcut before considering any executable bundler.

See [the audit and provenance note](AUDIT.md) for exact reuse and upstream pins.
