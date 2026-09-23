<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Stock fprintd retry and attempt review — R3

Original installed baseline reviewed: `92311c5ebe1d05a68ad0542ecb8aeafb9776db0e`.
The source correction supersedes the cumulative cap introduced in `c0b2369`:
the user's explicit decision leaves the number of explicit attempts to Fedora
stock. A clean NO_MATCH with completed cleanup never exhausts a driver budget.
R3-A installation and stock library loading are **PASS, human-reported** in
Fedora 44 KDE x86_64/KVM with SELinux Enforcing and the sensor disconnected.
The daemon, its ExecStart and libgusb are Fedora-owned; only libfprint and four
OpenCV libraries load from the project directory. That installation was retained
until the later clean replacement below. This accepted R3-A loading, not enrollment,
recognition, attempt safety or update survivability.

**Current evidence:** the user's clean-reinstall task reports PM-accepted
normal **44/44 PASS** and ASan/UBSan **44/44 PASS** at
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, and a clean, reviewed normal
runtime build from that SHA. This closes synthetic execution; it does not
claim real USB or biometric safety. The subsequent clean replacement at install
`264cd7ff1ba77857e1985502f299e4375f9a0516`, load/material/Claim gates and native
enrollment acquisition/storage have now passed in the VM. The user clarified
before any verify that the physical RIGHT index was enrolled as `guido` /
`left-index-finger`: a known label mismatch, not a matching result. Enrollment
completed with eight stages/contacts and clean closure; the canonical
manual preserves the complete user telemetry. Subsequent stock VERIFY passed
at the first attempt: RIGHT index against stored left-index-finger, terminal
MATCH, one capture/epoch, completed release tail and drained/closed resources.
Runtime and template are retained, sensor detached, fprintd inactive. No second
verify, no relabeling or rollback. **R3 is closed at the biometric boundary.**
This single MATCH does not qualify a real NO_MATCH series inside one Claim or
impose a cumulative driver cap. The current gate is
[R4 PolicyKit configuration query](../deployment/minimal-runtime/R4_POLKIT_PREFLIGHT_VM.md), reader detached.
Stock KScreenLocker subsequently passed password unlock with the reader absent
and fingerprint unlock at contact 1 without a password. MATCH was terminal and
resources closed/drained; release_tail/single_terminal were zero, consistent
with the early-MATCH cancellation case below, not proof of device quiescence.
The reported audit query identifies three fprintd/read nr_hugepages denials,
non-fatal for that completed path. KScreenLocker is SUPPORTED on the tested
baseline with the denial documented; no universal harmlessness or exact library
callsite is claimed. No repeated unlock, audit query or rollback is needed.
Ordinary sudo subsequently passed password with reader absent and first-contact
MATCH without password, exit 0, drained/closed resources and inactive/MainPID 0.
The same tail counters were zero, compatible with early PAM return; the warning
recurred during success. Sudo is SUPPORTED on the tested baseline; sudo-i auth
is configuration-covered, without a live claim for its login shell/session.

## Source findings

| Boundary | Code reviewed | Finding |
| --- | --- | --- |
| VERIFY vs IDENTIFY | `reference/fprintd-fedora44-1.94.5/source/src/device.c`, `fprint_device_verify_start` | One selected template uses VERIFY; multiple templates with `any` use IDENTIFY. Both need the same guard. |
| Daemon retry | Same file, `verify_cb`, `identify_cb`, `report_verify_status` | `FP_DEVICE_RETRY` reports `done=false` and immediately calls the same libfprint API again. A clean MATCH/NO_MATCH is `done=true` and does not trigger that branch. |
| Enrollment duplicate check | Same file, `enroll_identify_cb` | Also resubmits IDENTIFY on `FP_DEVICE_RETRY`; a clean duplicate MATCH ends enrollment. The same driver failure fence applies before a retry can reacquire resources. |
| Stock CLI | `source/utils/verify.c`, `do_verify`, `main` | One Claim, one VerifyStart, VerifyStop and Release. There is no three-attempt option/loop. Do not describe three separate CLI invocations as one driver-enforced series. |
| Stock PAM | `source/pam/pam_fprintd.c`, `do_verify`, `do_auth` | Default max-tries is 3; one Claim spans explicit VerifyStart calls after NO_MATCH. This is consumer policy, not a driver limit. MATCH returns success and closes the bus; timeout/error terminates. The later R4 query confirms this module without options in guest fingerprint-auth; native KScreenLocker later passed at contact 1; an actual multi-attempt PAM series remains untested. |
| Stock sudo | Guest preflight at `168469b79565cf401f2cb256448c184f3a803d8c`; sudo v1.9.17p2 `auth/pam.c`, `auth/sudo_auth.c` | system-auth uses pam_fprintd sufficient before pam_unix. The 3-try PAM budget resets on a new call; sudo can repeat PAM after whole-stack failure. One live series must detach USB before password fallback to prevent further sensor work. `sudo -k command` ignores and does not refresh cached credentials. Subsequent ordinary sudo live at reported `f5a4430` passed reader-absent password, then first-contact MATCH without password and exit 0; clean host closure. No live multi-attempt/failure-fallback qualification. |
| Client disappearance | `src/device.c`, `_fprint_device_client_vanished`, `fprint_device_release` | Cancel the current action, wait for its completion, then close the libfprint device. No new capture is scheduled for cleanup. |
| Host result ordering | Canonical `reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-image-device.c`, `fpi_image_device_minutiae_detected`, `fp_image_device_maybe_complete_action` | Outcome callbacks reach the driver before the early match report to fprintd; the final API completion waits for deactivation and processing. The early report can precede finger-off/STOP. |
| Driver cleanup/reopen | `libfprint-driver/goodix_fpimage_device.c`, `complete_deactivation`, `finish_deactivation`, `close_completed_capture_epoch` | Clean outcomes wait for STOP/drain and asynchronous matcher completion, release claim/material/TLS, then permit a later explicit action. Processing failure/cancel/transport error poison the logical open. |

At the original R3-A baseline, the driver did not reject every later same-kind
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
1.94.5 reference and its provenance. The original load evidence contains paths, not
the guest package NEVRA. The later R4 query reports fprintd/fprintd-pam
1.94.5-5.fc44.x86_64; this does not retroactively prove the earlier guest version.

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
SYNTHETIC_REAL_SENSOR_REQUIRED=false
LAST_REPORTED_SENSOR_CONNECTED=false
STOCK_EXPLICIT_ATTEMPT_COUNT_POLICY=FEDORA_CONSUMER
DRIVER_CUMULATIVE_CAPTURE_LIMIT=NONE
STOCK_RETRY_OFFLINE_CLOSURE=PASS_SYNTHETIC_HUMAN_REPORTED
SYNTHETIC_PHASE_NEXT_GATE=COMPLETED_VM_CLEAN_REPLACEMENT
R3_VERIFY=PASS_FIRST_ATTEMPT_MATCH_HUMAN_REPORTED
R3=CLOSED_BIOMETRIC_BOUNDARY
R4_PREFLIGHT=PASS_QUERY_ONLY_HUMAN_REPORTED
R4_KSCREENLOCKER_FUNCTIONAL=PASS_CONTACT_1_HOST_CLEANUP_PASS_HUMAN_REPORTED
R4_KSCREENLOCKER_CLASSIFICATION=SUPPORTED_ON_TESTED_BASELINE
R4_SELINUX_ASSESSMENT=NON_FATAL_FOR_TESTED_KSCREENLOCKER_PATH
R4_SUDO_PREFLIGHT=PASS_CONFIG_POLICY_PASSWORD_QUERY
R4_SUDO_FINGERPRINT=PASS_CONTACT_1_NO_PASSWORD_EXIT0_HUMAN_REPORTED
R4_SUDO_CLASSIFICATION=SUPPORTED_ON_TESTED_BASELINE
R4_SUDO_HOST_CLEANUP=PASS_DRAINED_CLOSED_INACTIVE_PID0_SENSOR_DETACHED
SUDO_I_AUTH=CONFIGURATION_COVERED_NOT_LIVE_TESTED
SUDO_I_LOGIN_SHELL_SESSION=UNTESTED
CURRENT_GATE=HUMAN_REQUIRED_VM_POLKIT_CONFIG_QUERY_SENSOR_ABSENT
NEXT_SENSOR_LIVE_HANDOFF_READY=false
CURRENT_INSTALLED_RUNTIME=QUALIFIED_R3_BUILD_RETAINED
```

The previous compiler/lifecycle/audit/expectation failures above are historical,
not current failures. The qualified build already exists at
`/home/guido/goodix-r3-20260922-111144`; do not rerun the synthetic gate or build.
The [clean replacement procedure](../deployment/minimal-runtime/README.md) and
native enrollment/verify are completed evidence; do not repeat them. Proceed
to the R4 PolicyKit configuration query, retaining the qualified runtime, template,
reconciled receipt and saved inverse. Sudo configuration and native authentication
have passed; do not repeat them. The KScreenLocker SELinux review is closed.

Architectural review: no increased distro coupling, no Fedora-owned auth
component changed, and no new password/desktop dependency. An incompatible
driver still has the intended class-C failure boundary; R5 must establish
survivability empirically. This repository preparation changes no installed
file. The next step is the human-only PolicyKit query, without a sensor or
PolicyKit authentication. The repeated nr_hugepages read denial was also non-fatal
during the completed sudo query and, as reported, the successful sudo live;
no policy change is prepared. PolicyKit, login and R5 remain unqualified.
