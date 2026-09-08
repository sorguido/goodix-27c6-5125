<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/54 — production identify protocol and safety design review

## Decision

At the design checkpoint, production `FPI_DEVICE_ACTION_IDENTIFY` had to remain
disabled. D279/53 closed public FP3 and the true libfprint/SIGFM identify action
on a host-only device, but did not yet supply a target-specific USB protocol or
a proven single-capture terminal boundary. ATTEMPT01 has now supplied that
missing evidence; the production gate remains unchanged until the distinct
D279/55 implementation and regression review.

```text
DECISION=ACCEPT_EVIDENCE_AND_CONTINUE_OFFLINE_TO_D279_55
PRODUCTION_IDENTIFY_ACTION_ENABLED=false
```

## Post-run evidence review

The authorized passive run `D27954_20260908_ATTEMPT01` completed exactly one
Windows Hello verification with UI-confirmed success and zero automatic retry.
The three supplied files are preserved unchanged under `captures/D279_54/`.
Their SHA-256 values are:

```text
wire.pcapng=6875b2d784d11cd4b3a8b68bd02af249f4b318883441a26068ef894767985c9b
operator_events.json=bb258a20f00f01efe271ca282e3dd6d0cba1ac6a4d6747da67e16417b2ddf555
attempt_status.json=20b45b1a07d0843a55e9314fe0d20668331258ba0a722b48126ed7d298f039bc
```

The strict repository-local parser reads 228 pcapng packets, 216 packets for
the unique `27c6:5125` target and 95 complete target protocol frames. It also
observes `GF_ST411SEC_APP_12509`. After the final action arm the exact
metadata-only trace is:

```text
C32,K32:01,I0002,C22,K22:01,BF,C34,K34:01,I0200,
C20,K20:01,BF,C50,K50:01,NAV
```

There is exactly one finger-on IRQ, one primary image lifecycle, one post-up
B0 and no subsequent `0x32`, second finger-on or second primary image. NAV is
the last protocol frame. The sole target packet after UI completion is an
empty IN completion; there are no later non-empty target packets or protocol
frames. This directly establishes the APP12509 OEM identify action as
single-touch/single-acquisition and its normal terminal boundary as release
NAV followed by no re-arm.

No known persistent command family (`E0`, `A4`, `F0`, `F4`) appears. This does
not prove that Windows or the sensor performed no adaptive template update;
that risk remains explicitly unexcluded. The capture is authority for the
target-specific USB lifecycle, not for the biometric matcher or enrollment
sample count. The derived audit is
`analysis/D279/D279_54_oem_identify_capture_audit.json`; it exports no payload,
plaintext, raster, feature, template or secret.

Rockytkg independently delivers one frame for verify/identify and delegates
matching to SIGFM. This is architectural corroboration only: its wire protocol
is not treated as identical to ATTEMPT01. The justified D279/55 composition is
therefore OEM lifecycle through release NAV, one R2/SIGFM probe, libfprint
identify, then terminal completion without a second arm.

## Evidence reviewed

- The production gate rejects every action other than enrollment before a
  generation or USB submit.
- The D279 enrollment model is a target-observed 21-stage graph with 125
  commands from OEM ATTEMPT02. Its command and state semantics are
  enrollment-specific.
- D278/14 proves the native target lifecycle through two acquisitions and
  reaches `STOP` only after the second image. After the first release it waits
  at `REARM_GATE` for the framework before sending the second `0x32`.
- D279/29 reaches the first production raster and then fails NBIS extraction.
  It proves drained host cleanup and close, but explicitly does not infer
  device-side timeout or quiescence.
- D256 proves bounded host/bus behavior around OEM cancellation, not internal
  FDT/disarm state.
- No versioned capture is classified as a successful OEM identify/verify
  transaction. ATTEMPT02 is a complete enrollment.

## Architecture boundary

Keep without semantic change:

- pre-session passive RX synchronization;
- APP12509 secure session, TLS and protected-material ownership;
- D4/AF/FDT bootstrap and image decoder;
- session baseline, Rockytkg R2 preprocessing and SIGFM extraction/storage;
- Fedora 44/libfprint 1.94.100 identify/match state machine.

Do not adapt or reuse for identify:

- the 21-stage enrollment model;
- its 125-command ATTEMPT02 profile;
- enrollment auxiliary B0 and progress semantics;
- the assumption that a drained host backend proves a safe device terminal.

After target evidence exists, the minimum implementation candidate is a
separate action-profile boundary that shares only proven bootstrap/capture
primitives. It must define exact terminal/release behavior, cancellation,
generation fencing, drain, one action per open epoch and fail-closed command
allowlisting before the production gate can change.

## Next evidence and operator kit

The minimum new evidence is one passive USBPcap observation of a Windows Hello
fingerprint verification using an already enrolled OEM template. This avoids
a speculative Linux sender and avoids intentional enrollment. It may still
cause host cache or adaptive sensor-template updates, which cannot be undone
by restoring the VM and therefore requires explicit acceptance.

The kit is in:

```text
operator_kit/d279-54-oem-passive-identify-observe/
```

It contains a closed authority template, an Italian PowerShell 5.1 launcher
and instructions. Its controls include:

- exact approved full SHA and `development` branch;
- clean live-critical set;
- target absent before capture;
- one unambiguous USBPcap interface;
- private, attempt-scoped outputs and `CreateNew` lock;
- existing OEM template and snapshot confirmations;
- explicit adaptive-persistence risk acceptance;
- exactly one UI verification and zero automatic/operator retry;
- five-second terminal tail and pcap readback/hash;
- export-before-restore instructions and conservative restore classification.

The Linux source/authority suite passes 4/4. Native Windows PowerShell Desktop
5.1 qualification is pending and must run with the Goodix target absent. The
versioned authority remains closed; no live action is authorized.

## Pre-live methodological review

1. **Real method change:** unlike D279/29, the new run sends no Linux enrollment
   transaction. It passively observes one OEM verification already supported
   by Windows.
2. **New technical hypothesis:** the OEM identify workflow has a bounded
   single-acquisition command/release/terminal sequence that can be separated
   from both the 21-stage enrollment graph and the D278/14 two-acquisition
   closure.
3. **Different action after same-boundary failure:** do not retry. Export the
   attempt, restore the VM where required, classify whether capture, attach or
   UI action failed, and redesign that boundary before requesting a distinct
   authorization.

## Original pre-run closure

```text
OUTCOME=HUMAN_REQUIRED
ADVANCEMENT=NEW_PROTOCOL_AND_SAFETY_BOUNDARY_CLASSIFIED
EXECUTABLE_CLOSURE=PASS_LINUX_SOURCE_TESTS;WINDOWS_NATIVE_QUALIFICATION_PENDING
OPERATOR_KIT=operator_kit/d279-54-oem-passive-identify-observe
AUTHORITY_TEMPLATE_CLOSED=true
OEM_IDENTIFY_ATTEMPT_MAX=1
AUTOMATIC_RETRY_COUNT=0
PRODUCTION_IDENTIFY_ACTION_ENABLED=false
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE
RESIDUAL_BLOCKER_OR_RISK=EXACT_OEM_IDENTIFY_TRANSCRIPT_AND_SINGLE_CAPTURE_DEVICE_TERMINAL_UNKNOWN;WINDOWS_NATIVE_QUALIFICATION_PENDING;EXPLICIT_ADAPTIVE_PERSISTENCE_ACCEPTANCE_AND_ONE_SHOT_AUTHORIZATION_REQUIRED
NEXT_PRIMARY_BOUNDARY=HUMAN_GATE_FULL_SHA_ONE_OEM_PASSIVE_IDENTIFY_CAPTURE
```

## Post-run closure

```text
OUTCOME=READY
ADVANCEMENT=TARGET_SPECIFIC_OEM_IDENTIFY_SINGLE_ACQUISITION_LIFECYCLE_PROVEN
EXECUTABLE_CLOSURE=PASS_OFFLINE_STRICT_PCAP_AUDIT
OEM_IDENTIFY_ATTEMPT_COUNT=1
OEM_IDENTIFY_UI_RESULT=SUCCESS
OEM_IDENTIFY_SINGLE_TOUCH=true
OEM_IDENTIFY_PRIMARY_IMAGE_COUNT=1
OEM_IDENTIFY_POST_UP_B0_COUNT=1
OEM_IDENTIFY_POST_TOUCH_REARM_COUNT=0
OEM_IDENTIFY_SECOND_FINGER_ON_COUNT=0
OEM_IDENTIFY_TERMINAL_PROTOCOL_EVENT=NAV
KNOWN_PERSISTENT_COMMAND_FAMILY_COUNT=0
ADAPTIVE_TEMPLATE_PERSISTENCE_EXCLUDED=false
PRODUCTION_IDENTIFY_ACTION_ENABLED=false
LIVE_AUTHORIZATION_CONSUMED=true
CURRENT_LIVE_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=OFFLINE_D279_55_PRODUCTION_IDENTIFY_SINGLE_ACQUISITION_PROFILE
```
