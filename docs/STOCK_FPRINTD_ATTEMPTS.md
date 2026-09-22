<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Stock fprintd retry and attempt review — R3

Installed baseline reviewed: `92311c5ebe1d05a68ad0542ecb8aeafb9776db0e`.
The source correction supersedes the cumulative cap introduced in `c0b2369`:
the user's explicit decision leaves the number of explicit attempts to Fedora
stock. A clean NO_MATCH with completed cleanup never exhausts a driver budget.
R3-A installation and stock library loading are **PASS, human-reported** in
Fedora 44 KDE x86_64/KVM with SELinux Enforcing and the sensor disconnected.
The daemon, its ExecStart and libgusb are Fedora-owned; only libfprint and four
OpenCV libraries load from the project directory. Installation remains in
place; rollback was not exercised. This accepts R3-A loading, not enrollment,
recognition, attempt safety or update survivability.

## Source findings

| Boundary | Code reviewed | Finding |
| --- | --- | --- |
| VERIFY vs IDENTIFY | `reference/fprintd-fedora44-1.94.5/source/src/device.c`, `fprint_device_verify_start` | One selected template uses VERIFY; multiple templates with `any` use IDENTIFY. Both need the same guard. |
| Daemon retry | Same file, `verify_cb`, `identify_cb`, `report_verify_status` | `FP_DEVICE_RETRY` reports `done=false` and immediately calls the same libfprint API again. A clean MATCH/NO_MATCH is `done=true` and does not trigger that branch. |
| Enrollment duplicate check | Same file, `enroll_identify_cb` | Also resubmits IDENTIFY on `FP_DEVICE_RETRY`; a clean duplicate MATCH ends enrollment. The same driver failure fence applies before a retry can reacquire resources. |
| Stock CLI | `source/utils/verify.c`, `do_verify`, `main` | One Claim, one VerifyStart, VerifyStop and Release. There is no three-attempt option/loop. Do not describe three separate CLI invocations as one driver-enforced series. |
| Stock PAM | `source/pam/pam_fprintd.c`, `do_verify`, `do_auth` | Default max-tries is 3; one Claim spans explicit VerifyStart calls after NO_MATCH. This is consumer policy, not a driver limit. MATCH returns success and closes the bus; timeout/error terminates. This is source evidence, not an enabled/validated guest authentication configuration. |
| Client disappearance | `src/device.c`, `_fprint_device_client_vanished`, `fprint_device_release` | Cancel the current action, wait for its completion, then close the libfprint device. No new capture is scheduled for cleanup. |
| Host result ordering | Canonical `reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-image-device.c`, `fpi_image_device_minutiae_detected`, `fp_image_device_maybe_complete_action` | Outcome callbacks reach the driver before the early match report to fprintd; the final API completion waits for deactivation and processing. The early report can precede finger-off/STOP. |
| Driver cleanup/reopen | `libfprint-driver/goodix_fpimage_device.c`, `complete_deactivation`, `finish_deactivation`, `close_completed_capture_epoch` | Clean outcomes wait for STOP/drain and asynchronous matcher completion, release claim/material/TLS, then permit a later explicit action. Processing failure/cancel/transport error poison the logical open. |

At the installed baseline, the driver does not reject every later same-kind
call after MATCH. That is the terminal-outcome gap addressed here. Its lack
of a cumulative cap after clean NO_MATCH is desired behavior. The cap in
`c0b2369` incorrectly turned a previous three-attempt test convention/PAM
default into driver access policy and has been removed. The prepared-login
`login_attempts` field is a separate historical private path, unused by stock
fprintd; it does not define the stock driver's semantics.

## Driver-only correction

The current source adds `production_capture_attempt_count` and
`production_capture_terminal` to the logical-open context and existing audit.
VERIFY and IDENTIFY share the count as telemetry only. Transport epoch reset
does not clear it, and no count threshold governs admission or terminality.
MATCH and processing error latch terminal. Later actions are rejected before
material/claim reacquisition, generation allocation or transport submission.
Every clean NO_MATCH allows a new explicit action after cleanup, including
fourth and subsequent attempts in the same Claim. The stock path logs
`NO_MATCH` regardless of count; it never infers `NO_MATCH_SERIES`. No new
retry, wire command, retained-session protocol or acquisition scheduler is added.
The first IDENTIFY NO_MATCH may still hand off to ENROLL for stock duplicate
checking; MATCH/error cannot authorize that handoff.

Existing poison remains checked first. If its saved error is itself
`FP_DEVICE_RETRY`, a subsequent activation now returns a terminal
`FP_DEVICE_ERROR_PROTO` instead of perpetuating a host-only restart loop.
The ordinary processing-retry path may therefore still produce a stock
daemon API resubmission, but it must produce **zero** new material acquisitions,
claims, transport epochs or sensor submissions and terminate with a non-retry
error. The design does not claim that stock fprintd never calls the API twice.

Cleanup is unchanged: cancellation fences and drains outstanding callbacks;
abnormal device quiescence is not asserted. Clean completion releases the
per-action resources; failed/cancelled contexts remain non-reusable until
full close frees/cleanses them. A new Claim after full close starts with fresh
state. MATCH blocks subsequent actions in the same Claim; mandatory
finger-release/cleanup work still completes. There is no cumulative capture
limit or account lockout imposed by this driver.

The daemon/PAM source findings are bound to the retained Fedora fprintd
1.94.5 reference and its provenance. The load evidence contains paths, not
the guest package NEVRA; no assertion of an unreported guest version is made.
The test records the guest package version for the subsequent review.

## Verification status and gate

The existing integration suite in
`development/private-root/libfprint-driver/tests/test_goodix_d278_secure_session.c`
has ten R3 cases: VERIFY and IDENTIFY with MATCH at 1/2/3, five consecutive
clean NO_MATCH followed by MATCH on a sixth explicit action, and cancellation
from the early MATCH callback. Each admitted action checks one normal
acquisition and cleanup; fourth/fifth calls must reacquire materials/claim
exactly once, without implicit retries. The eight series cases then attempt
further VERIFY and IDENTIFY after MATCH, requiring zero new resources or
submissions, and verify fresh state on full close/open. Existing retry/fatal
tests also check actual acquisition and OUT submission counters on rejected
resubmission. The two early-MATCH cases cancel before
finger-off/STOP, require outstanding callbacks to drain and verify resource
release and TLS cleansing at full close. They model the stock PAM owner-loss
ordering through libfprint callbacks, without claiming a real D-Bus execution.
Existing cases cover processing-retry resubmission, cancellation,
non-drained work, late host outcomes, fatal
processing, duplicate-check ENROLL and synthetic TLS cleanup.

The current inner test builder reuses these fixtures against the canonical
Fedora libfprint base and driver with SIGFM and the production action profile.
USB, materials and the feature matcher are synthetic; TLS and async adapter
execution are real test code. No daemon/consumer source is modified or run.
The fixture's historical private path is a test-only dependency, explicitly
not a production/runtime or qualified public-release test dependency.

The user-reported VM attempt stopped during compilation at
`goodix_fpimage_device.c:2530:44`: implicit `guint` to `gint` conversion in
`fpi_device_set_nr_enroll_stages`, rejected by `-Werror=sign-conversion`.
**Zero R3 tests ran; the reader remained disconnected and R3-A unchanged.**
The minimal correction checks `1..G_MAXINT` before stage completion and the
explicit `gint` cast, freeing the image pipeline and reporting an error for
an invalid value. Warning flags and retry semantics are unchanged.

Source digest/path audit, shell syntax, and the test entry point's help/non-VM
refusal from an unrelated cwd are PASS. **Corrected compilation and the 44
normal/ASan/UBSan cases remain pending manual VM execution.** Static review
does not substitute for those results. No dynamic or sensor-safety PASS is claimed.

```text
R3_A_STOCK_LOAD=PASS_HUMAN_REPORTED
PM_R3_A_LOAD_REVIEW=ACCEPT_AND_CONTINUE
PREVIOUS_VM_COMPILATION=FAIL_SIGN_CONVERSION
PREVIOUS_VM_R3_TESTS_EXECUTED=0
STOCK_ATTEMPT_SOURCE_CORRECTION=IMPLEMENTED
STOCK_EXPLICIT_ATTEMPT_COUNT_POLICY=FEDORA_CONSUMER
DRIVER_CUMULATIVE_CAPTURE_LIMIT=NONE
STOCK_RETRY_OFFLINE_CLOSURE=PENDING_VM_SYNTHETIC_EXECUTION_AND_REVIEW
NEXT_GATE=HUMAN_REQUIRED_VM_TEST_BUILD_WITHOUT_SENSOR
LIVE_HANDOFF_READY=false
INSTALLED_RUNTIME_CHANGED=false
```

Follow [the VM test procedure](../production/minimal-runtime/STOCK_ATTEMPTS_VM.md).
Retain the installed R3-A baseline and R2 output. Do not use the old installer
from the new source checkout: its source-continuity guard correctly rejects
changed driver code. The installed inverse remains unchanged and available.
After test evidence, review the correction before preparing a separate build
and reversible runtime update. The native consumer workflow and material
handoff must be settled before a sensor-reaching request. The consumer chooses
the number of explicit attempts; the driver fences terminal outcomes and
implicit sensor-reaching retries.

Architectural review: no increased distro coupling, no Fedora-owned auth
component changed, and no new password/desktop dependency. An incompatible
driver still has the intended class-C failure boundary; R5 must establish
survivability empirically. This test-only step changes no installed file.
