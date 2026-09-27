<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Enrollment zero-mask: functional recovery and diagnostic fallback

Phase E preserves a valid zero-mask contact's primary and evaluates it through
normal quality/diversity/SIGFM processing. An accepted nonterminal sample
continues the same enrollment via one normal next-sample request; a terminal
sample completes without waiting for IRQ0200. This is a runtime change, not an
error-enum or UI-text change. KDE is expected to continue without a red error
for an accepted zero-mask sample. **Phase E has not yet been validated live.**

```text
SELECTED_STRATEGY=Phase E functional recovery under the limited host contract
FUNCTIONAL_RECOVERY_IMPLEMENTED=YES
SEPARATE_PROTOCOL_ISSUE=OPEN
AFTER_ZERO_0x20=0
AFTER_ZERO_AUX_B0=0
AFTER_ZERO_FINAL_AUX_34=0
AFTER_ZERO_0x32=one normal request if needed; none on terminal/error/cancel
AFTER_ZERO_HIDDEN_RETRY=0
PRIMARY_MAX_DELIVERY=1
STAGE_MAX_INCREMENT=1
```

The [contract](ENROLLMENT_ZERO_MASK_CONTRACT.md) defines strict entry, atomic
DOWN-table derivation, one passive late0200 before the first valid new IRQ2, and
failure outside that window's rules. That IRQ2 is an explicitly accepted host
boundary, not a demonstrated firmware fence. A same-byte stale0200 in the next
ordinary release slot can remain indistinguishable from the current release.
The [technical manual](../TECHNICAL_MANUAL.md) retains the Phase C observations
and OEM evidence supporting this bounded candidate.

A zero mask does not bypass quality checks. An extraction/quality failure keeps
the project's terminal error policy; an ordinary diversity rejection keeps its
visible retry policy and contact bound. Phase E adds no hidden sensor retry and
manufactures no successful stage. The software finger-down transition permits
the existing libfprint host decision to request the next sample after processing.

Phase D's typed contact-unusable GENERAL remains a **fallback** when strict
recovery prerequisites are unavailable. It is no longer the ordinary result of
an eligible, valid zero contact. Its UI limitation and the alternatives examined
in Phase D are retained below as historical consumer analysis.

## Reviewed stack and evidence

The review checked the installed Fedora 44 package versions: libfprint
`1.94.100-1.fc44`, fprintd `1.94.5-5.fc44`, and the Users settings plugin from
`plasma-workspace-libs-6.7.5-1.fc44`. Library conclusions use this repository's
production libfprint source. The locally available fprintd reference's
`src/device.c` was compared byte-for-byte with the official `v1.94.5` source.
KDE conclusions use official `v6.7.5` sources, with relevant strings also present
in the installed plugin. These are source-based expectations, from the Phase D review, without a live qualification of either Phase D or E. The versions are review provenance, not runtime pins.

## Phase D alternatives considered (historical fallback decision)

| Option | Actual behavior | Phase D decision |
| --- | --- | --- |
| 1. Classify zero-mask as a normal recoverable scan with `fpi_image_device_retry_scan()` | Enrollment progress reports retry, then the image-device state waits for finger removal and can return to waiting for another finger. The action remains open. | Reject: no demonstrated way to complete another contact without crossing the unresolved rearm boundary. |
| 2. End enrollment with terminal `FP_DEVICE_RETRY` | Enrollment completion preserves the error domain; fprintd emits a retry status with `done=true`. KDE ignores `done` and presents this as another scan of the same enrollment. | Reject: the reader would be stopped while the UI invites a scan it cannot process. |
| 3. Close the action and permit a later explicit request | The client must complete Stop/Release; a later Claim and EnrollStart use the normal fresh action path. | Retain the existing manual path. No automatic new action or recovery loop. |
| 4. Return a specific terminal error message | A driver caller and the fprintd journal can retain the reason. Stock fprintd converts it to a fixed status; KDE displays its generic terminal error. | Select for accurate diagnosis, with the visible UI limitation explicit. |
| 5. Use another error enum or emit retry progress before abort | Protocol-error falsely maps to disconnection; synthetic cancellation misstates who cancelled. A progress hint followed by terminal failure does not provide a stable final explanation. | Reject misleading enums and additional callbacks with no demonstrated benefit. |

## libfprint action, callbacks and ownership

`FP_DEVICE_RETRY` describes scan conditions, rather than a transport reset or
permission to send a command. The enum does not establish the cause of zero-mask:
small contact, short contact and poor placement remain possible explanations,
not independently proved diagnoses. See the public
[retry enum documentation](../reference/libfprint-fedora44-1.94.100/source/libfprint/fp-device.h#L105).

For ENROLL, [`fpi_image_device_retry_scan()`](../reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-image-device.c#L678)
reports progress and enters `AWAIT_FINGER_OFF`; the
[subsequent transition](../reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-image-device.c#L175)
can enter `AWAIT_FINGER_ON`. This is not terminal completion.
[`fpi_image_device_session_error()`](../reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-image-device.c#L739)
deactivates the device. The
[completion helper](../reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-image-device.c#L187)
waits for deactivation and pending image processing before reporting the action
error. It warns when session-error is misused with a retry-domain error.

[`fpi_device_enroll_progress()`](../reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-device.c#L2071)
calls the client's progress callback synchronously, then releases the passed
error and print. In contrast,
[`fpi_device_enroll_complete()`](../reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-device.c#L1357)
transfers the terminal result to the task; the
[idle completion](../reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-device.c#L1060)
clears the action before client completion. A retry error survives ENROLL
completion. VERIFY and IDENTIFY completion explicitly replace an incorrectly
passed retry error with GENERAL; that separate behavior must remain unchanged.

Cancellation follows the existing
[image-device cancel handler](../reference/libfprint-fedora44-1.94.100/source/libfprint/fp-image-device.c#L82)
and deactivation path. An actual user cancellation remains cancellation. Phase D
does not manufacture cancellation to obtain a different UI string, and does not
deliver the held primary as enrollment progress or a successful print.

## What fprintd and KDE do

fprintd's [status mapping](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/device.c#L632)
uses domain and code, not the detailed message. Its
[progress callback](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/device.c#L1858)
emits `done=false`; its
[enrollment completion callback](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/device.c#L2007)
emits `done=true` and logs the detailed error. It does not automatically resubmit
ENROLL for terminal RETRY. However, the
[duplicate-precheck IDENTIFY callback](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/device.c#L2097)
does resubmit on RETRY: the Phase D classification must remain ENROLL-only.

KDE 6.7.5's
[`FprintDevice::enrollStatus()`](https://invent.kde.org/plasma/plasma-workspace/-/blob/v6.7.5/kcms/users/src/fprintdevice.cpp#L60)
ignores `done`. Retry status names call
[`handleEnrollRetryStage()`](https://invent.kde.org/plasma/plasma-workspace/-/blob/v6.7.5/kcms/users/src/fingerprintmodel.cpp#L297),
which updates scan feedback without closing enrollment. Terminal GENERAL instead
becomes `enroll-unknown-error`; KDE's
[failure handler](https://invent.kde.org/plasma/plasma-workspace/-/blob/v6.7.5/kcms/users/src/fingerprintmodel.cpp#L312)
shows its generic error and stops enrollment. The
[dialog](https://invent.kde.org/plasma/plasma-workspace/-/blob/v6.7.5/kcms/users/src/ui/FingerprintDialog.qml#L80)
renders that error and returns to the fingerprint list. There is no driver-only
route for substituting a detailed terminal contact-quality message in this UI.

```text
DRIVER_RESULT=contact unusable; specific diagnostic; FP_DEVICE_ERROR_GENERAL; action terminated
FPRINTD_RESULT=enroll-unknown-error; done=true; detailed cause in journal
KDE_EXPECTED_BEHAVIOR=generic error and return to fingerprint list; no automatic retry
```

## Phase D fallback boundary and manual restart

The diagnostic applies only to the expected repeated-contact ENROLL
`control=0x36 / IRQ=0x0100 / flags=0x0000`, with valid frame shape, checksum and
bounded raw values, after the preceding OUT has completed. It identifies a
contact the current path cannot use. It does not relax global FDT acceptance,
advance a stage, retain the contact's primary as a successful sample, or declare
that firmware state is ready for another contact. Malformed data, reserved
flags, wrong control/IRQ and unexpected phases retain fail-closed handling.

The typed diagnostic is converted to a terminal GENERAL error with an
explanatory message. The existing fence, cancel, drain and resource-release
sequence closes the action; no auxiliary acquisition, new contact, rearm or
hidden retry is authorized. There is no observation timer or quiet-window
prerequisite for the decision.

A later manual attempt is a new enrollment from its beginning, not continuation
of the discarded action. fprintd requires
[EnrollStop before another action](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/device.c#L1382);
its [completion bookkeeping](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/device.c#L1479)
retains the enrollment action until Stop. KDE's
[stop handler](https://invent.kde.org/plasma/plasma-workspace/-/blob/v6.7.5/kcms/users/src/fingerprintmodel.cpp#L173)
calls Stop and Release. fprintd
[Release closes the device](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/device.c#L1163).
The [Goodix device implementation](../libfprint-driver/goodix_fpimage_device.c)
rejects reuse of a poisoned or consumed enrollment epoch until full close/open.
Only a subsequent explicit Claim/EnrollStart follows the existing fresh
bootstrap path. No new automatic reopen behavior is added. Host close/open and
drain are not a claimed firmware release barrier, and this review does not
resolve late/stale IRQ0200 ownership.

## Phase E manual live validation, not executed

The [operator kit](../operator_kit/phase-e-zero-mask/README.md) is now prepared
with manual installation, metadata collection and symmetric restoration of the
previous runtime. The agent has built and checked the candidate offline and
has not installed it, invoked sudo, opened USB or performed a live attempt.

Use one normal KDE enrollment and try the observed brief/poorly positioned
little-finger contact after the first accepted sample. An actual logged zero
must preserve the primary, skip20/auxiliary B0/final auxiliary34 and continue the
same enrollment if host processing accepts it. Completion and the absence of a
red error are human observations; metadata counters alone do not establish UX.
No zero means the target behavior is inconclusive. Do not automatically repeat.

After targeted PASS, check one ordinary enrollment, verification and duplicate
attempt through the normal consumer. A second profile requires human involvement
and is optional. Preserve existing prints. Unexpected error, command/retry,
stalled action or missing drain/close means stop, collect and roll back.

The zero-specific sample/rearm/late-release/closed records distinguish the
allowed post-zero activity. The existing epoch audit's cumulative rearm counter
also includes earlier ordinary contacts and must not be interpreted as activity
after zero. Require final `outstanding=0`, `drained=1`, `context_closed=1` and
`persistent=0` after client Release. The counters are metadata, not an independent
USB trace or firmware separation proof.

## Offline validation

Normal and combined ASan/UBSan runs pass 60 A0/graph cases, 58 actual image-device
cases and 68 with the optional Phase C probe compiled. They exercise successful
zero at contacts 2/4/7/8, strict entry/raw bounds, ownership, terminal/cancel,
late-release interleavings and failed32 cleanup. Supplementary internal
full-TLS/SIGFM tests pass 53 cases in both modes, including zero-sample quality
failure, visible diversity retry, ordinary enrollment, VERIFY, IDENTIFY,
duplicate precheck, IDENTIFY→ENROLL handoff and distinct synthetic template
epochs following zero recovery. This is not live multi-user storage/authorization
qualification. SDK runners disable LeakSanitizer; explicit drain/free assertions
remain active.

The 23 Phase B model tests still demonstrate the stronger unresolved firmware
contract and have no successful rearm; Phase E runtime tests exercise the newly
authorized rule. The native production build checks ABI, test-symbol exclusion,
materials and PAM mocks. The reversible kit passes 13 synthetic deployment tests.
Independent runtime/kit review accepted the corrected candidate. No exported
audit structure layout, fprintd consumer, KDE code or global FDT policy changes.
