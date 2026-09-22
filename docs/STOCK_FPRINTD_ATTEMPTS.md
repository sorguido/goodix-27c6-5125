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

**Current evidence:** the user's clean-reinstall task reports PM-accepted
normal **44/44 PASS** and ASan/UBSan **44/44 PASS** at
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, and a clean, reviewed normal
runtime build from that SHA. This closes synthetic execution; it does not
claim real USB or biometric safety. The next gate is the
[clean replacement](../deployment/minimal-runtime/README.md), stopping with
fprintd inactive before a separate load-check review.

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
exactly once, without implicit retries. Each of the eight series cases then
attempts exactly one VERIFY or IDENTIFY after MATCH, requiring zero new
resources or submissions, then closes the Claim. Same-kind and cross-kind
rejections use separate fixtures, as mapped below. All ten cases verify
fresh state and an admitted action after full close/open. Existing retry/fatal
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

The first user-reported VM attempt stopped during compilation at
`goodix_fpimage_device.c:2530:44`: implicit `guint` to `gint` conversion in
`fpi_device_set_nr_enroll_stages`, rejected by `-Werror=sign-conversion`.
**Zero R3 tests ran; the reader remained disconnected and R3-A unchanged.**
The minimal correction checks `1..G_MAXINT` before stage completion and the
explicit `gint` cast, freeing the image pipeline and reporting an error for
an invalid value. Warning flags and retry semantics are unchanged.

The second VM attempt stopped at fixture line 1640 on
`CLAMP(value, 0, GOODIX_SENSOR_SAMPLE_MAX)`, rejected by `-Werror=sign-compare`:
`value` is `gint`, while the maximum is `4095u`. Again **zero R3 tests ran,
the reader stayed disconnected and R3-A remained unchanged**. The fixture
now asserts at compile time that the maximum fits `gint`, then uses a
`const gint` upper bound. All three CLAMP operands are signed; the intended
range remains 0..4095, including clipping negative values to zero. No
production source, attempt/retry rule, compiler flag or roadmap is changed.

## Post-MATCH lifecycle corrective

The preceding human-reported VM run **compiled and linked both builds and
started normal and sanitizer tests**. Both stopped at
`/goodix/r3/verify-match-1`: the first rejected post-MATCH action logged
`GOODIX_STOCK_CAPTURE_REJECT attempts=1 terminal=1 new_transport=0`, then the
next action caused the fatal `ACTIVATING -> ACTIVATING` state warning. This
is `TEST_LIFECYCLE_STATE_MACHINE`, not a compile failure or suite PASS. The
report does not establish results for the remaining nine R3 cases.

Source review confirms the cause in the canonical Fedora-base
`fpi-image-device.c`: `fpi_image_device_activate_complete(error)` completes
the action while retaining `ACTIVATING` and `active=false`; another capture
calls `fpi_image_device_activate()` and attempts the invalid transition.
`fpi_image_device_close_complete()` resets the state to `INACTIVE`, as does
open completion. The old two-kind rejection loop skipped this close.
The stock daemon retries only `FP_DEVICE_RETRY`; other errors complete the
action, and stock PAM exits and releases the device on terminal error.
No stock component or driver policy is changed to accommodate the test.

Reviewed all ten R3 registrations, shared action helpers, completion/error
callbacks, drain and teardown. The corrected sequences are below; all names
have prefix `/goodix/r3/`. Each row uses its own fixture and Claim.

| Case | Before close | Action after fresh open |
| --- | --- | --- |
| `verify-match-1` | MATCH, one rejected VERIFY | VERIFY |
| `verify-match-2` | NO_MATCH, MATCH, one rejected IDENTIFY | VERIFY |
| `verify-match-3` | Two NO_MATCH, MATCH, one rejected VERIFY | VERIFY |
| `verify-no-match-5-then-match` | Five NO_MATCH, sixth MATCH, one rejected VERIFY | VERIFY |
| `identify-match-1` | MATCH, one rejected IDENTIFY | IDENTIFY |
| `identify-match-2` | NO_MATCH, MATCH, one rejected VERIFY | IDENTIFY |
| `identify-match-3` | Two NO_MATCH, MATCH, one rejected IDENTIFY | IDENTIFY |
| `identify-no-match-5-then-match` | Five NO_MATCH, sixth MATCH, one rejected IDENTIFY | IDENTIFY |
| `verify-match-client-cancel` | Early MATCH callback, cancellation, drain, close | VERIFY |
| `identify-match-client-cancel` | Early MATCH callback, cancellation, drain, close | IDENTIFY |

The eight rejected actions still require `FP_DEVICE_ERROR_NOT_SUPPORTED`,
unchanged material/claim/IN/OUT counts, empty/drained transport, no held
material/claim and unchanged capture/transport-epoch counters. Exactly one
rejection is asserted. The two cancellation cases retain their pending-work,
poison, resource-release and TLS-cleansing checks; they do not insert another
capture before Release. Both now also exercise a fresh Claim.

Close/open helpers read the actual `fpi-image-device-state` property and
`fp_device_is_open()`. Close resets the property without emitting the
state-changed signal, so the fixture's cached signal value cannot prove this
reset. No internal state is forced by the tests. The new Claim must have zero
capture count, no terminal latch/poison and admit one normal acquisition of
the original action kind, with one new material acquisition/claim and balanced
releases. Existing VERIFY and IDENTIFY `FP_DEVICE_RETRY` cases retain one
automatic API resubmission, a terminal non-retry error, zero new resources or
submissions, then close; they do not repeat activation failures in one Claim.

Offline lifecycle review closed for **10/10 cases** in `620ee15`, with the
fixture passing `-fsyntax-only` in both profiles. The next VM report identifies
the D291 audit failure below as the only known failure in both runs. A complete
suite PASS was still pending at that point; the accepted result is recorded
above. The AI has not executed the suite or accessed the VM.

## D291 SIGFM audit corrective

The VM run preceding `5b0369e` builds/links and starts both suites. Its
only known failure, identical in normal and sanitizer, is
`/goodix/d291/fixed-raw-baseline-pinning-mechanics` at fixture line 2146.
The seam had reversed the probe and enrolled signatures in its audit arrays.

Reviewed the actual call chain: canonical `fpi-print.c` calls
`goodix_sigfm_match_ephemeral(probe, enrolled, &score)`; the metrics adapter
forwards the arguments in that order to `sigfm_match_score()`. The active
`libfprint-driver/tests/support/fpimage_link_stubs.c` now names the first
parameter `probe`, records it in the probe array and records the second
parameter in the enrolled array. The comment is corrected. Score calculation,
locking, counters, array bounds and getters are unchanged.

All four getter uses are in the D291 continuity fixture. With
`N = GOODIX_SIGFM_ENROLL_MAX_STAGES`, their unchanged assertions mean:

| Getter use | Intended evidence |
| --- | --- |
| enrolled signature at 0 | Save the nonzero signature of the first template sample as `T` |
| probe signature at 0 | The initial wrong raster gives a probe different from `T` |
| enrolled signature at N | The next explicit action still compares against the same template sample `T` |
| probe signature at N | The enrolled raw raster, normalized with the pinned baseline A despite new session baseline B, gives `T` |

The first NO_MATCH compares all N template samples; the next MATCH stops at
the first sample, so the audit indices are justified by the existing call-count
assertions. The test still proves fixed-raw pinning mechanics only, not physical
session equivalence or biometric stability. No fixture assertion, production
preprocessing/pinning, attempt policy, stock component, compiler flag or
roadmap changes. The gate compiles the active support file in both profiles;
the historical private-root copy is not its build input and is left intact.

Static review and `-fsyntax-only` of the corrected support file passed in both
profiles in `5b0369e`. The subsequent VM report identifies the D282 expectation
failure below. No new test framework or physical-host execution was introduced.

## D282 expected-warning scope corrective

The run preceding `b8cdd17` builds/links and starts normal and sanitizer
suites; both fail at
`/goodix/d282/production-enrollment-intermediate-extraction-terminal` with
`libfprint-image-FATAL-: GOODIX_SIGFM_EXTRACT_AUDIT keypoints=30`.
That is a normal successful-extraction message, made fatal by a pending
expectation for a different domain/level/message. The fixture registered
`Failed to detect minutiae:*` before stages 1 and 2, although only stage 3
was meant to fail. Classification: `TEST_EXPECTATION_SCOPE`.

The expectation is now installed inside the existing failure-stage branch,
after `goodix_test_sigfm_extract_wait_blocked()` succeeds and immediately
before `set_failure(TRUE)` and `unblock()`. Earlier stages finish without a
pending expectation. The helper returns after unblocking stage 3; the caller
still drains the terminal failure, checks the single expected warning with
`g_test_assert_expected_messages()` and restores the failure seam. Existing
assertions still require two enrollment progress reports and no fourth contact.

Reviewed all three `g_test_expect_message()` uses and their paired assertions:

| Scope | Why unrelated successful logs do not fall inside the expectation |
| --- | --- |
| D282 enrollment stage 3 | Stages 1/2 and the stage-3 release tail precede installation; the worker is confirmed blocked before the expectation is installed. Only the intended failing extraction remains. |
| VERIFY processing retry in `test_d280_01_production_two_epoch_template_reuse` | Prior successful actions finish before this open. Activation/TLS precede installation, failure is already enabled, and the single image returns an extraction error before the success audit message. |
| IDENTIFY processing retry in `test_d293_02_identify_failure_cancel_no_handoff` | Enrollment and activation/TLS precede installation. The only image uses the already-enabled failure seam; expectation is asserted before any later API resubmission. |

The canonical `fp-image.c` worker emits the keypoint audit only after
`GOODIX_SIGFM_OK`; injected extraction failure returns before that message.
In the callback, the expected warning precedes result/cleanup logs, so it is
consumed before those logs. No second overlapping expectation or successful
extraction remains in these three scopes. The other two sites need no change.
The fix does not suppress audit logs, alter fatal-log handling, add expected
success messages or change any production code/flags. Static syntax checks
of the fixture passed in both existing profiles; the subsequent 44/44 PASS
in both modes closes that sensor-free VM gate.

## Preventive compile-surface review (22 September 2026)

Reviewed both `production/minimal-runtime/check-stock-attempts.sh` and
`libfprint-driver/tests/run_goodix_fpimage_device_test_inner.sh`, with the
actual gate settings `GOODIX_STOCK_ATTEMPT_TEST=1` and
`GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE_TEST=1`. The normal and sanitized
branches compile the same **43 translation units in the same order**,
including both generated enum registration sources and the 12-source loop.

| Units | Effective builder profile |
| --- | --- |
| 27 project C sources, including `goodix_sigfm_preprocess.c` | `-std=gnu11 -O2 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wconversion`, test seams, SIGFM and production action profile, function/data sections |
| 1 complete secure-session fixture | Same strict flags plus the existing `-Wno-conversion`; `-Wsign-compare` remains active through `-Wextra` |
| 14 base/support C sources | Existing `local_flags`: eight Fedora core sources, two generated enum sources, three stubs and `rockytkg-imgproc/goodix_imgproc.c`; existing warning exceptions are unchanged |
| 1 C++ metrics source | Existing `-std=c++17 -O2 -g` profile; C warning flags are not attributed to this target |

The sanitized C profiles append `-O1 -fno-omit-frame-pointer
-fsanitize=address,undefined`; C++ uses `-std=c++17` with these sanitizer
options, as in the builder. Include order, generated enum inputs and
pkg-config flags were retained. No warning suppression was added or widened.

The full fixture was checked for comparisons, macro expansions and ternary
signedness. Its signed image delta and score branches stay signed; count
branches use unsigned operands, and sizes/deadlines use their corresponding
unsigned/signed types. No other diagnostic was found with the effective
flags. All five sources compiled **after** the fixture were also checked:
`gusb_stub.c`, `fpimage_link_stubs.c`, `goodix_imgproc.c`,
`goodix_sigfm_preprocess.c` and `goodix_sigfm_metrics.cpp`. In particular,
preprocessing uses `size_t` for lengths, representable image/parameter
constants, explicit byte extraction and matching enum return types; it needs
no source change under the full strict profile.

Static compiler-front-end analysis used the already installed local SDK
25.08 headers and GCC/G++ 15.2.0, GLib 2.84.4 and OpenSSL 3.5.7, read-only,
with `-fsyntax-only` in both profiles. SDK front ends were invoked through
their SDK loader; no Flatpak instance, project executable or test was started.
Result: **86 successful parses, zero diagnostics**, covering all 43 units in
both profiles. Only temporary generated enum source/header and diagnostic
files were written; no object, assembly or executable was produced. This
closes the static review, not code generation, linking, optimization-dependent
diagnostics or sanitizer/test execution. The guest toolchain version has not
been inferred from the local SDK.

Source digest/path audit, shell syntax and the test entry point's help/non-VM
refusal from an unrelated cwd passed. The static review preceded the successful
VM build/link; the user now supplies the complete suite qualification:

```text
R3_A_STOCK_LOAD=PASS_HUMAN_REPORTED
R3_SYNTHETIC_NORMAL=44/44 PASS
R3_SYNTHETIC_ASAN_UBSAN=44/44 PASS
QUALIFIED_SOURCE_COMMIT=b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226
REAL_SENSOR_REQUIRED=false
SENSOR_CONNECTED=false
STOCK_EXPLICIT_ATTEMPT_COUNT_POLICY=FEDORA_CONSUMER
DRIVER_CUMULATIVE_CAPTURE_LIMIT=NONE
STOCK_RETRY_OFFLINE_CLOSURE=PASS_SYNTHETIC_HUMAN_REPORTED
NEXT_GATE=HUMAN_REQUIRED_VM_CLEAN_REPLACEMENT_LEAVE_FPRINTD_STOPPED
LIVE_HANDOFF_READY=false
INSTALLED_RUNTIME_CHANGED=false
```

The previous compiler/lifecycle/audit/expectation failures above are historical,
not current failures. The qualified build already exists at
`/home/guido/goodix-r3-20260922-111144`; do not rerun the synthetic gate or build.
Follow the [clean replacement procedure](../deployment/minimal-runtime/README.md):
old saved inverse first, verify Fedora stock, install the qualified runtime,
leave fprintd stopped and return evidence before its load-check. The old
installed inverse remains unchanged until the user runs it. Native consumer
workflow and material handoff remain separate boundaries before sensor use.

Architectural review: no increased distro coupling, no Fedora-owned auth
component changed, and no new password/desktop dependency. An incompatible
driver still has the intended class-C failure boundary; R5 must establish
survivability empirically. This repository preparation changes no installed
file; the VM replacement is manual and still pending.
