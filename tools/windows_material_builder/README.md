<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 5125 Material Builder — development candidate

This English-language Python/Tkinter application prepares private device material
inside the **original qualified Windows VM**, as the **original normal user**.
It is not a supported release: real Windows validation is still required.
USBPcap 1.5.4.0 is project-pinned. The operator has confirmed source validation,
installation/reboot, post-reboot prerequisites, UAC and capture startup on the
existing VM. The retained real capture also passed source/capture validation,
DPAPI recovery and the complete five-file bundle build with exit code zero.
Embedded capture shutdown remains unqualified. No generic support for all
64-bit Windows versions is claimed.
Use the [manual walkthrough](../../docs/learning/11_building_your_device_material_bundle.md)
as the independent acquisition reference. The Linux installer/runtime remains
the final authority on validity.

The app never sends Goodix commands, automates a hypervisor, enrolls a finger,
changes firmware or replaces a PSK. USBPcap observes ordinary OEM initialization.
**DO NOT TOUCH THE SENSOR during acquisition.** Captures can contain sensitive
material and stay private, on failure as well as success. No upload or telemetry.

## Current gate: one final full Windows acquisition

The remaining experiment is embedded USBPcap lifecycle management. At stop the
builder requests elevation for `%SystemRoot%\System32\taskkill.exe` with exactly
`/F /T /IM USBPcapCMD.exe`. It awaits completion, verifies that no USBPcapCMD.exe
remains, closes writer handles and flushes the retained raw before strict analysis.
This name-based scope is intentional for the **dedicated qualified VM**; every
USBPcapCMD.exe instance is in scope. There is no instance-count preflight, Job
Object requirement or console input stop. The GUI remains unelevated. See
[the stop contract](AUDIT.md#bounded-stop-contract).
Update only the Windows source to the delivered development commit. Preserve the
existing Python environment, installed USBPcap, OEM source folder and retained
runs. Do not reinstall USBPcap or create a new VM. Initially detach Goodix from
the guest and disable automatic attachment. Close fingerprint/enrollment settings.
Use the controller mapping already established in this qualified VM.

Before running the command below, obtain the project source folder:

1. Open the project's GitHub page.
2. Select the `main` branch.
3. Choose **Code → Download ZIP**.
4. Extract the ZIP archive to a local folder.
5. Copy the full path of the extracted project folder.
6. When PowerShell shows:

   ```text
   Full path to the updated Goodix source folder:
   ```

   paste that full folder path and press **Enter**.

Use the project root folder (the one containing `tools`, `docs`, and the other
repository files), not the `tools\windows_material_builder` subfolder.

From a normal, unelevated PowerShell session:

```powershell
Set-Location -ErrorAction Stop -LiteralPath (Read-Host 'Full path to the updated Goodix source folder')
& "$env:LOCALAPPDATA\Goodix5125BuilderPython\Scripts\python.exe" -m tools.windows_material_builder
if ($LASTEXITCODE -ne 0) { throw 'STOP: builder exited with an error; report the safe diagnostic code.' }
```

1. Select the existing three-file source folder and pass the usual preflight.
   With Goodix detached, press **Recheck**, then **Start capture**.
2. Accept USBPcap's UAC prompt. Keep Goodix detached during startup.
3. Only at **“Now attach the Goodix to this Windows VM”**, attach that reader
   manually. Attach no other device. **DO NOT TOUCH THE SENSOR.**
4. Wait for the normal **30-second** acquisition window, accept the additional
   **TASKKILL UAC** prompt, and wait for automatic analysis.
5. Expect **Diagnose and build**, with CONFIG90/A2/CHIP82/A6 valid and unambiguous.
   **Stop before pressing Build private bundle.** DPAPI/bundle construction is a
   path already proven separately; this gate checks only embedded capture.

The GUI needs no manual console stop, extra button or new timing choice. Partial
or ambiguous material remains a failure and is shown as **Capture incomplete**,
with no Build action. Cancel remains **CAPTURE_CANCELLED**, including cancellation
during shutdown; it never proceeds to material success.

Report the tested commit, Windows/Python versions, the GUI's four material results
and safe `diagnostics\lifecycle.txt` fields. Successful stop requires
`TASKKILL_EXIT=<value>`, `USBPCAP_ABSENT`, `CAPTURE_HANDLES_CLOSED`, `RAW_CLOSED`,
`WORKER_EXIT=0`, `EOF`, `RAW_FLUSHED` and `STOPPED`, without failure or timeout.
The TASKKILL exit code is diagnostic telemetry; verified `USBPCAP_ABSENT` is the
authoritative stop result after TASKKILL launches and completes within its bound.
The native USBPcap forced exit has no private marker and is accepted only after
explicit stop; an earlier exit fails even if the file parses. The GUI's
container/target/APP and four material results remain mandatory.

Keep raw and OEM inputs private. Do not share files, payloads, paths, hashes or
arbitrary stderr. Stop after this single attempt. If the embedded lifecycle
still fails, record **EMBEDDED_USBPCAPCMD_CAPTURE=REJECTED** and pivot to the
already-proven existing-capture input workflow. Do not request another equivalent
capture, extended retry or console/Job Object diagnostic pass. The general
procedure below remains a reference outside this final gate.
## Before a future Windows operator test

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

1. On Welcome, press **Show Windows/Python baseline** and record Windows product,
   version, build and Python version. An unavailable field is reported as UNKNOWN
   and does not reject the VM. Continue from Welcome. Select the three-file source folder. Expect the cache
   to be structurally valid, `goodix.dat` valid, and the DLL qualified. No secret
   or reader-specific digest is displayed.
2. Continue to prerequisites. The app checks the driver, CMD, pinned release,
   interfaces and reboot state. If absent, click **Install USBPcap**. The app
   downloads the pinned official installer, verifies its complete SHA-256, then
   opens the interactive UAC installer. Read and accept its licenses yourself.
   Use the official installer defaults and normal interactive choices. Its
   **Detect USB 3.0** option is not yet independently qualified by this project;
   record its actual setting and the guest controller at the Human Gate. No silent license acceptance occurs.
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
   allows the selected interval (30 seconds by default) for OEM initialization,
   then requests TASKKILL UAC, verifies termination and diagnoses the capture.
7. Review the individual CONFIG90/A2/chip82/A6 checks. **Build private bundle** is
   available only with complete evidence. It cross-checks A6/cache, uses Windows
   DPAPI in the original user context, derives the canonical transport binding,
   creates the exact manifest and validates all five files before publication.
   If target and APP identity are correct, CONFIG90 is present, and only A2/chip82/A6 evidence is missing,
   **Retry with extended initialization window** offers one explicit 60-second
   attempt. Detach Goodix manually, repeat preflight/controller selection and
   **Recheck**, then **Start capture** and wait for **Now attach…** again. The
   retry gets a new run; both captures remain. There is no automatic retry,
   re-attachment or third timing tier. If still incomplete, stop and report the
   code. Ambiguous evidence, identity/container errors and material/DPAPI/source
   failures require their specific correction path; they do not offer this option.
   **CONFIG90_MISSING means stop:** no timed retry is offered for that result.
   Retain the capture and report the code for provenance review.
8. Success lists exactly the five filenames. Open the bundle folder and transfer
   that whole `goodix-5125-materials` folder privately to Linux at
   `~/goodix-5125-materials`. Leave the raw capture outside it.

The 30-second settle allowance exceeds the under-eight-second typed-response
window in the read-only historical audit. It is an engineering bound, **not**
proof of initialization completeness: the historical audit reported incomplete
evidence. The current retained operator recording contains valid CONFIG90. The optional 60-second attempt for other missing classes doubles the observation window to test
possible late initialization without unbounded waiting. Historical evidence does
not establish that 60 seconds is necessary or sufficient, nor that CONFIG90 is
impossible during attach-only capture. All evidence gates remain mandatory. Attach timeout is 90 seconds;
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
facts, possible causes and actions. For CAPTURE_PROCESS_FAILED, the run
`diagnostics/lifecycle.txt` contains only bounded safe lifecycle facts: explicit
TASKKILL request/result, USBPcap absence, relay/helper exit, raw flush, EOF and failure/timeout
stages. Report those fields without the raw capture. A readable PCAP alone does
not prove verified process cleanup, and termination alone does not prove valid material.
TASKKILL gets a 15-second process wait and a five-second absence-verification
window; the capture helper gets a 90-second stop budget including UAC. On that
outer timeout only the Python helper is terminated: cleanup is unverified, raw
is retained, and no result is accepted. Denied UAC, a hung elevated process or a
late OS consent response can leave native activity unresolved; the app does not
claim cancellation of Windows consent or retry TASKKILL.
`CONFIG90_MISSING` is a legitimate negative
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

Report only the tested commit, Windows product/version/build, Python version,
USB3 installer option setting and guest controller, selected 30/60-second window,
PASS/FAIL, the diagnostic code and the point of failure. Never send the capture, caches, bundle, DLL, hashes
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
