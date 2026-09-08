<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/55 — production identify single-acquisition boundary

## Decision and evidence separation

D279/55 enables the production `FPI_DEVICE_ACTION_IDENTIFY` path offline.  It
combines two authorities without merging their claims:

- D279/54 ATTEMPT01 is the APP12509 sensor-side authority for one acquisition,
  the release tail through NAV, and no subsequent re-arm;
- Rockytkg remains the implementation reference for R2 preprocessing, SIGFM
  extraction/storage/matching and the libfprint single-probe architecture.

The OEM transcript is not claimed wire-identical to Rockytkg.  This step does
not change the enrollment sample-count policy and does not interpret D279/54
as evidence about enrollment.

## Minimal implementation

`GoodixPostTlsMaterial` now selects one of two explicit capture profiles.  The
zero/default value preserves the established two-acquisition behavior and the
enrollment first-arm handoff.  Production identify selects
`GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION` and does not install the
enrollment graph.

After the first authenticated primary B0 has traversed the existing session
baseline -> R2 -> SIGFM pipeline, the retained target-specific release tail is:

```text
0x34 -> IRQ 0x0200 -> 0x20 -> post-up B0 -> 0x50 -> NAV
```

On valid NAV the single-acquisition profile moves to `STOP` before delivering
the release-tail and finger-up callbacks.  Consequently a synchronous
libfprint state transition cannot observe `REARM_GATE`; later framework
await-finger-on notifications cannot submit another `0x32`, and receive re-arm
is false at `STOP`.

The production allowlist now admits `ENROLL` and `IDENTIFY`; `CAPTURE` remains
rejected before generation allocation or submit.  The existing one-action per
open-epoch rule, cancellation/generation fences, pre-session sync, TLS,
backend drain and persistent-family guardrails are unchanged.  In the pinned
libfprint 1.94.100 core, public verify falls back to the identify vfunc with a
one-print gallery, so it reaches the same `FPI_DEVICE_ACTION_IDENTIFY` profile.

## Offline verification

The deterministic lifecycle suite passes normal and ASan/UBSan, including the
new complete single-acquisition transcript.  It proves one image and one
finger-on, release through NAV, phase `STOP`, zero re-arm, zero second IRQ/image,
zero retry, zero persistent-family send and no outstanding fake transfer.

The focused production-device test passes normal and ASan/UBSan.  With a
non-null production-shaped USB object and in-memory submit seam it proves that
identify consumes the open epoch, configures the secure/post-TLS graph with the
single-acquisition profile, and does not install the enrollment graph.  It is
cancelled at the synthetic pre-session boundary and closes with backend drain;
real USB submit remains zero.

The broader legacy `run_goodix_fpimage_device_test.sh` first required a local
compile-only correction for an otherwise unused parameter when SIGFM is not
defined.  Its D279/55 focused run is green.  The unfiltered run exposes a
pre-existing D279/24 test-harness incompatibility: the old non-SIGFM 21-stage
fixture loses its enrollment binding after image extraction fails, then feeds
more plaintext into the stopped bootstrap lifecycle.  That unrelated legacy
fixture remains a residual test-harness issue; it does not occur in either the
D279/55 lifecycle test or the production SIGFM build configuration.

The Fedora/OpenCV production-shaped runner was updated to assert the new
allowlist/profile and output state.  Its pinned RPM cache was not present in
this session, so the already-validated real-SIGFM D279/52–53 binary closure was
not re-executed here.  No dependency was installed or downloaded.

## Closure

```text
OUTCOME=READY
ADVANCEMENT=PRODUCTION_IDENTIFY_SINGLE_ACQUISITION_BOUNDARY_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=PASS_FOCUSED_NORMAL_ASAN_UBSAN;FULL_LEGACY_NON_SIGFM_FIXTURE_RESIDUAL
PRODUCTION_IDENTIFY_ACTION_ENABLED=true
PRODUCTION_VERIFY_VIA_IDENTIFY=true
IDENTIFY_PRIMARY_ACQUISITION_COUNT=1
IDENTIFY_RELEASE_TERMINAL=NAV_THEN_STOP
IDENTIFY_POST_TOUCH_REARM_COUNT=0
IDENTIFY_ENROLLMENT_GRAPH_INSTALLED=false
ENROLLMENT_BEHAVIOR_CHANGED=false
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_SUBMIT=0
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
SIGFM_THRESHOLD_PRODUCTION_VALIDATED=false
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE
RESIDUAL_BLOCKER_OR_RISK=NO_LIVE_LINUX_IDENTIFY_PROOF;ADAPTIVE_PERSISTENCE_UNEXCLUDED;SIGFM_THRESHOLD_NOT_VALIDATED;LEGACY_NON_SIGFM_D279_24_FIXTURE_RED
NEXT_PRIMARY_BOUNDARY=OFFLINE_D279_56_AUTHENTIC_ENROLLMENT_DYNAMIC_POLICY_REPLAY
```
