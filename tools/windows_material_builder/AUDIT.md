<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Windows Material Builder — technical audit and provenance

This document records the stable technical, provenance and safety properties of
the Goodix 5125 Windows Material Builder.

The builder has been validated end-to-end on the qualified Windows environment:
embedded USBPcap acquisition, target and APP validation, CONFIG90/A2/CHIP82/A6
extraction, A6/FDT binding, DPAPI recovery, transport-material generation,
manifest generation and final five-file validation all completed successfully.

A five-file bundle produced by the application was subsequently accepted by a
clean Fedora installation of the driver. The Linux installer/runtime remains the
final authority on bundle validity.

## Contract and reuse

The five-file contract is defined by
[`docs/DEVICE_MATERIALS.md`](../../docs/DEVICE_MATERIALS.md) and enforced by the
Linux-side material loaders and validators.

The application preserves that contract:

- canonical ten-field manifest;
- qualified OEM `gfusb.dll`;
- 224-byte CONFIG90 material and finalizer checks;
- FDT cache structure and CRC validation;
- A2/CHIP82/A6 typed evidence;
- A6/FDT same-reader binding;
- existing PSK recovery through Windows DPAPI;
- transport-material binding compatible with the Linux runtime.

The builder reuses project-authored parsing and transport-binding logic where
appropriate and adds the Windows acquisition, DPAPI, prerequisite, diagnostic
and Tkinter integration required to create the same canonical material bundle.

No alternate bundle format or relaxed Linux acceptance path is introduced.

## Official USBPcap pin

The project pins:

```text
USBPcap 1.5.4.0
installer: USBPcapSetup-1.5.4.0.exe
size:      195040 bytes
SHA-256:   87a7edf9bbbcf07b5f4373d9a192a6770d2ff3add7aa1e276e82e38582ccb622
```

The installer is obtained from the official USBPcap release and its complete
SHA-256 is checked before execution.

The upstream installer remains interactive and presents its own licenses and
normal choices. The Material Builder does not silently accept licenses.

The application uses USBPcap only to observe ordinary OEM reader initialization.
It does not use USBPcap to send Goodix maintenance commands.

## Capture invocation

The builder uses the pinned `USBPcapCMD.exe` capture path with:

- explicit selected capture controller;
- capture of newly attached devices;
- snap length 65535;
- raw capture output only;
- no interactive console stop dependency.

The application starts capture while the Goodix reader is detached and instructs
the operator when to attach the reader.

If multiple USB capture controllers exist, controller selection must be resolved
explicitly. The application does not assume that the first controller is the
correct one.

## Bounded stop contract

The normal USBPcap stop is:

```text
%SystemRoot%\System32\taskkill.exe /F /T /IM USBPcapCMD.exe
```

It is launched elevated through native Windows `ShellExecuteExW` with the
`runas` verb while the main GUI remains unelevated.

The numeric TASKKILL exit code is diagnostic telemetry. It is **not** the
authoritative success condition.

After TASKKILL completes, the helper enumerates running processes and requires:

```text
USBPCAP_ABSENT
```

Verified absence of `USBPcapCMD.exe` is the authoritative postcondition.

The accepted lifecycle is therefore:

```text
capture
→ bounded acquisition window
→ elevated TASKKILL
→ verify USBPcapCMD.exe absent
→ close process/writer handles
→ flush and close raw capture
→ verify bounded file stability
→ strict capture analysis
→ Diagnose and build
```

No console `q` injection, console-sharing dependency, Job Object requirement,
`TerminateJobObject` fallback or TASKKILL exit-code allowlist is part of the
accepted design.

An early native process exit remains a failure even if the retained capture can
be parsed.

Cancellation uses the same bounded cleanup path but remains a cancellation; it
cannot become material success.

## Capture identity and material validation

The parser accepts the observed USB enumeration transition in which the initial
descriptor request can use device address `255` and the completion uses the
newly assigned device address. Subsequent identity is bound to that assigned
device.

Target identity remains strict:

```text
VID:PID = 27c6:5125
APP     = GF_ST411SEC_APP_12509
```

CONFIG90 acceptance uses logical control `0x90`, with the existing framing,
length, checksum/finalizer, DAC-layout and ambiguity checks preserved.

A valid acquisition requires all of:

```text
CONFIG90
A2
CHIP82
A6
```

to be valid and unambiguous.

The A6 body is cross-bound to the FDT cache before final material publication.

A missing or ambiguous required material class does not produce a valid bundle.

## DPAPI and transport material

`Goodix_Cache.bin` is opened only in the original qualified Windows user
context through Windows DPAPI.

The recovered existing 32-byte PSK is not displayed or written as a loose key
file.

The application combines that existing PSK with the qualified OEM producer
material from `gfusb.dll` to build the canonical
`transport-material.bin`.

The application does not generate, replace, reprovision or write a new PSK to
the reader.

## Final publication contract

The application publishes only after complete validation and creates exactly:

```text
target-material-manifest.json
transport-material.bin
target-config-90.bin
gfusb.dll
fdt-cache.bin
```

The final directory is created under the run directory as
`goodix-5125-materials`.

Existing final bundles are not silently overwritten. Raw captures remain outside
the final bundle.

The Linux installer independently validates the transferred bundle before
installation.

## Privacy boundaries

The following remain private and must not be committed or published:

- raw USB captures;
- `Goodix_Cache.bin`;
- `goodix.dat`;
- `gfusb.dll`;
- generated five-file bundles;
- PSK material;
- reader-specific hashes and identity material.

The application has no upload or telemetry path.

Diagnostics are intentionally bounded to safe lifecycle and validation facts and
must not expose arbitrary raw capture data or secret material.

## Factory-preserving boundary

The Material Builder does not:

- flash firmware;
- enter IAP;
- invoke ClearApp;
- write OTP;
- replace or reprovision the PSK;
- change VID:PID;
- enroll a fingerprint;
- modify persistent reader state.

Its role is limited to observing ordinary OEM Windows initialization and
constructing the private material bundle required by the Linux driver.

## Qualification scope

The validated path covers the tested qualified Windows environment and the
Goodix `27c6:5125` / `GF_ST411SEC_APP_12509` target with the qualified OEM
driver and DLL.

The project does not claim generic qualification for every Windows version,
Goodix firmware revision, OEM package or physical reader variant.

Material success on Windows does not bypass Linux-side validation. The Linux
installer/runtime remains authoritative.

## References

- [Material Builder usage](README.md)
- [Device-material contract](../../docs/DEVICE_MATERIALS.md)
- [Manual acquisition reference](../../docs/learning/11_building_your_device_material_bundle.md)
- [Installation](../../docs/INSTALLATION.md)
