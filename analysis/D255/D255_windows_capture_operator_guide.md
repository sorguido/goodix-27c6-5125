# D255 Windows APP12509 evidence capture operator guide

## Status and authority

This guide describes a future, single Windows OEM evidence capture.  D255 only
prepared and tested the kit offline.  AI-PM review is not authorization, and no
earlier authorization applies.

```text
D255_OPERATOR_AUTHORIZATION_REQUIRED=true
D255_AUTHORIZATION_CONSUMED_ON_START=true
D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true
```

The future run must use the factory Windows path.  It must not perform
enrollment, provisioning, firmware update, IAP, PSK replacement, reset, or any
other maintenance action.  Raw USB, OEM logs, and cache copies remain in an
operator-selected local directory outside the repository.

## Historical reconstruction

Observed local evidence:

- `analysis/D230/work/GoodixExport/rilevamento.pcapng` is a USBPcap-linktype
  pcapng, SHA-256
  `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`;
- the manual and evidence index classify it as a Windows OEM cold-attach
  capture and identify a second independent cold-attach capture, now absent;
- `GoodixExport.zip`, supplied by the operator and recovered in D230, contained
  the surviving capture, `gfusb.dll`, the OEM INF/catalog, and related DLLs;
- the repository does not retain the exact USBPcap/Wireshark command, tool
  version, hypervisor, VM attach command, or WBDI log path used for that run.

Therefore the artifact proves USBPcap format and the cold-attach boundary, but
does not prove whether the capture process was launched in the Windows guest or
by another layer of the old VM setup.  D255 reuses the proved format and
boundary, and makes all missing selectors and timestamps explicit.

```text
PREVIOUS_CAPTURE_METHOD=WINDOWS_OEM_COLD_ATTACH_CAPTURE; EXACT_LAUNCH_PROCEDURE_NOT_RETAINED
PREVIOUS_CAPTURE_TOOL=USBPCAP_PCAPNG_FORMAT; WIRESHARK_TSHARK_VERSION_UNKNOWN
PREVIOUS_CAPTURE_BOUNDARY=BEFORE_USB_ENUMERATION_THROUGH_OEM_INIT_AND_IMAGE_CYCLES; NO_EXPLICIT_CANCEL_WINDOW
RECOMMENDED_D255_CAPTURE_METHOD=TSHARK_WITH_USBPCAP_IN_WINDOWS_VM_STARTED_BEFORE_REVIEWED_GUI_USB_ATTACH
WHY=REUSES_THE_PRIMARY_CAPTURE_FORMAT_AND_COLD_ATTACH_BOUNDARY_WHILE_ADDING_CORRELATED_MARKERS_LOGS_AND_CACHE_SNAPSHOTS
```

No host wrapper is supplied.  The repository does not preserve a canonical
hypervisor command, and automating an unverified detach/attach path would make
the operational boundary less auditable.  Use the same reviewed VM GUI
passthrough path that produced the prior Windows OEM capture.

## Cold-init trigger decision

| Candidate | Device-side effect class | Factory-preserving evidence | Windows compatibility risk | Selected |
| --- | --- | --- | --- | --- |
| Start USBPcap capture in the running Windows VM, then attach the existing target through the normal VM GUI | normal USB enumeration and OEM D0/init lifecycle; volatile session activity expected | two historical target captures are classified as cold attach; normal OEM path contains no requested maintenance action | low, bounded to normal Windows attach; absolute absence of internal NVM effects is not claimed | yes |
| Restart Windows Biometric Service with capture active | normal WBF service close/open, expected volatile | D241-D251 prove Linux-side `fprintd` restoration, but the repository does not prove that `WbioSrvc` restart produces the complete target cold-init lifecycle | low but completeness is unproven | no; fallback requires separate review |
| Disable/enable the Windows device | PnP power/re-enumeration transition | ordinary Windows mechanism, but no retained target procedure proves necessity or exact outcome | higher than service/attach because it changes PnP state | no |

```text
COLD_INIT_TRIGGER=WINDOWS_VM_NORMAL_USB_COLD_ATTACH_WITH_USBPCAP_ALREADY_ACTIVE
DEVICE_SIDE_EFFECT_CLASS=NORMAL_OEM_ENUMERATION_AND_VOLATILE_SESSION_INITIALIZATION
FACTORY_PRESERVING_EVIDENCE=HISTORICAL_TARGET_COLD_ATTACH_CAPTURES_PLUS_NO_MAINTENANCE_COMMAND_REQUESTED; NOT_ABSOLUTE_DEVICE_NVM_PROOF
WINDOWS_COMPATIBILITY_RISK=LOW_BUT_NONZERO_NORMAL_ATTACH_RISK; NO_PERSISTENT_CHANGE_INTENDED
SELECTED=true
```

## Required tools and inputs

- Windows PowerShell 5.1 or PowerShell 7;
- Wireshark/TShark with USBPcap installed in the Windows VM;
- one exact USBPcap interface name copied from `tshark -D`;
- at least 1 GiB free in an operator-selected output directory outside Git;
- the existing Windows installation and normal Windows Hello recognition UI;
- known OEM/WBDI log paths when available.  Static OEM strings name
  `WBDI.log` and `_wbdi_.log`, but the target path is not established;
- optional targeted cache roots.  Defaults cover Goodix-specific ProgramData
  and system-profile Goodix directories only.

The cache search is deliberately targeted.  It selects 13520-byte files and
filenames containing Goodix/base/cache/WBDI/finger/NAV/image only within those
roots.  The 13520-byte layout remains a hypothesis until CRC, OTP binding, and
field correlations pass.

## Phase 0: offline preflight

Keep `27c6:5125` detached from the Windows guest.  On the Linux host, confirm
that no fingerprint operation is active and that the reviewed VM owns the
future passthrough path.  Do not stop services or attach the device during this
preflight.

From an ordinary PowerShell prompt in the Windows VM:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -PreflightOnly `
  -OutputRoot "D:\Goodix-D255-Raw" `
  -TsharkPath "C:\Program Files\Wireshark\tshark.exe" `
  -CaptureInterface "USBPcap1" `
  -OemLogPath "C:\verified\path\WBDI.log"
```

Expected output is `D255_PREFLIGHT_ONLY=PASS` and
`D255_HARDWARE_ACTION_COUNT=0`.  The script fails on ambiguous interfaces,
target already present, unreadable configured log/cache paths, output
collision, tool failure, or insufficient disk space.  Select the USBPcap root
hub interface that will receive the VM passthrough; do not guess.

## Authorized single run

Run this only after AI-PM review, baseline approval, and a new explicit user
authorization for one capture:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -OutputRoot "D:\Goodix-D255-Raw" `
  -TsharkPath "C:\Program Files\Wireshark\tshark.exe" `
  -CaptureInterface "USBPcap1" `
  -CaptureDurationSeconds 300 `
  -OemLogPath "C:\verified\path\WBDI.log" `
  -Authorization "--i-authorize-one-d255-windows-oem-evidence-capture"
```

The script creates a unique run directory, consumes the authorization, takes a
before-cache snapshot, and starts TShark before prompting for VM GUI attach.
It never invokes a VM, service, PnP, firmware, provisioning, or USB command
itself.  GUI prompts divide automatic collection from operator actions.

Follow the prompts exactly:

1. Attach the target to Windows using the normal reviewed VM GUI path.
2. Open the normal Windows Hello recognition prompt and do not touch the sensor.
3. Confirm the UI is waiting; the script records the arm marker.
4. Cancel through the normal Windows UI without a finger.
5. Reopen the normal recognition prompt without a finger and confirm readiness.
6. Wait for the bounded capture duration to expire.

The default proof target is `REENTRY_WITHOUT_FINGER`.  Do not pass
`-AllowReentryFinger` unless the separately reviewed run plan explicitly
allows one normal recognition event because no-finger re-entry is insufficient.
That switch never authorizes enrollment.

TShark stops on the fixed duration, not by process termination, so the pcapng
is closed normally.  If the duration expires before all operator phases, the
script fails closed.  Do not retry without a new authorization.

## Phase 5 outputs

The run directory contains:

- `raw/wire.pcapng`;
- copied raw OEM logs, if configured or found in targeted roots;
- before/after raw cache candidates and metadata;
- `operator_markers.tsv` with UTC timestamps;
- preflight and authorization-consumption records;
- `input_manifest.json` and its SHA-256 sidecar.

These are private raw evidence.  Do not place the run directory in Git, the
D255 bundle, cloud storage, or a support ticket.  It can contain OTP material,
biometric baselines, images, TLS traffic, or machine-specific data.

## Linux offline sanitization

Copy or mount the raw run directory outside this repository.  Read the exact
manifest hash from `input_manifest.json.sha256`, then run:

```bash
python3 analysis/D255/d255_postprocess_windows_evidence.py \
  --run-dir /external/private/D255_RUN \
  --manifest /external/private/D255_RUN/input_manifest.json \
  --manifest-sha256 MANIFEST_SHA256_FROM_SIDECAR \
  --output-dir /tmp/D255_sanitized
```

The postprocessor refuses changed inputs and output collisions.  It never
opens USB, invokes the network, or copies raw evidence.  Only the two files in
the sanitized output directory are candidates for later review.  Inspect them
before adding them to any future step.

If A8 does not prove `GF_ST411SEC_APP_12509`, processing terminates with:

```text
CAPTURE_FIRMWARE=UNKNOWN
D255_EVIDENCE_TARGET_SPECIFIC=false
```

and the run cannot close the target blocker.  A seed equality is reported as a
correlation only; it does not prove causal dataflow without matching timing and
OEM lifecycle evidence.

## Failure policy

There is no automatic retry.  Missing capture, ambiguous selectors, output
collision, missing markers, cancel before arm, firmware mismatch, unexpected
cache layout, CRC failure, or absent re-entry remain explicit failure or
inconclusive results.  If the UI cancel does not occur between its markers,
classify the evidence as:

```text
RESULT=INCONCLUSIVE_NO_CANCEL_MARKER
```

Do not repair an inconclusive run by replaying commands, tails, firmware, or
cache data to the sensor.
