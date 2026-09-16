<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/53 — fprintd storage and SIGFM identify interoperability

## Scope

This step closes the host-only interoperability boundary after D279/52. It
does not execute fprintd, enable production identify, access USB or use real
biometric material.

## Evidence

The production-shaped Fedora 44/libfprint 1.94.100 build completed with the
real Rockytkg SIGFM/OpenCV path and a deterministic structured non-biometric
raster. The action test proved:

- 21-stage true `FpImageDevice` SIGFM enrollment;
- public `fp_print_serialize()` / `fp_print_deserialize()` round-trip;
- canonical equality, device compatibility and FP3 metadata preservation;
- a true `fp_device_identify()` action using the deserialized template;
- returned gallery match and one-sample SIGFM scanned print;
- zero production USB access.

The exact installed `/usr/libexec/fprintd` belongs to
`fprintd-1.94.5-5.fc44.x86_64`. Static ELF audit confirms it needs
`libfprint-2.so.2`; all 47 undefined `LIBFPRINT_2.0.0` symbols it requires are
exported by the built library. The checked surface includes the public print
serialization/deserialization and identify start/finish calls. The daemon
execution count remained zero.

## Corrective found during execution

The first identify run reached a valid SIGFM score of `1026` against threshold
`40`, then failed under `G_DEBUG=fatal-warnings`. Fedora libfprint 1.94.100's
`fpi_device_identify_report()` rejected the scanned SIGFM print because it was
not byte-equal to a gallery entry. That validation already excludes NBIS,
whose matcher-backed probe likewise need not equal its template.

The local corrective extends this existing exclusion to `FPI_PRINT_SIGFM`.
The validation remains unchanged for other print types. Rockytkg's older
libfprint tree does not contain the newer equality check, so the change is a
local LGPL adaptation of the preserved Fedora core and not a direct Rockytkg
import. The second run completed successfully.

## Production boundary

`goodix_fpimage_device_activate()` still rejects every production USB action
other than `FPI_DEVICE_ACTION_ENROLL`. The identify result therefore proves
the libfprint/SIGFM host action and storage path only. No production protocol
lifecycle, device transcript, cancellation/quiescence behavior, fprintd
on-disk storage policy, D-Bus/SELinux behavior or biometric threshold is
claimed.

## Closure

```text
OUTCOME=READY
ADVANCEMENT=PUBLIC_FP3_AND_TRUE_SIGFM_IDENTIFY_ACTION_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY_WITH_EXACT_INSTALLED_FPRINTD_ABI_AUDIT
PUBLIC_FP3_STORAGE_ROUNDTRIP=PASS
TRUE_SIGFM_IDENTIFY_ACTION=PASS
FPRINTD_PACKAGE=fprintd-1.94.5-5.fc44.x86_64
FPRINTD_LIBFPRINT_REQUIRED_SYMBOL_COUNT=47
FPRINTD_LIBFPRINT_ABI_CLOSURE=PASS
FPRINTD_EXECUTION_COUNT=0
PRODUCTION_IDENTIFY_ACTION_ENABLED=false
SIGFM_THRESHOLD_PRODUCTION_VALIDATED=false
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
LIVE_EXECUTION_PERFORMED=false
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE
RESIDUAL_BLOCKER_OR_RISK=PRODUCTION_IDENTIFY_PROTOCOL_AND_SAFETY_NOT_DESIGNED_OR_AUTHORIZED;FPRINTD_RUNTIME_AND_ON_DISK_POLICY_NOT_EXECUTED;SIGFM_THRESHOLD_NOT_VALIDATED
NEXT_PRIMARY_BOUNDARY=OFFLINE_PRODUCTION_IDENTIFY_PROTOCOL_AND_SAFETY_DESIGN_REVIEW
```
