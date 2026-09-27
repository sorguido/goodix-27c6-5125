<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Enrollment zero-mask: terminal diagnosis and consumer limits

Phase D selects a **specific contact-unusable diagnosis followed by safe action
termination**. It does not implement enrollment recovery. The current KDE
consumer cannot display a terminal retry correctly, and stock fprintd does not
forward a driver's detailed terminal error message to that UI. Claiming that an
enum change fixes the visible enrollment failure would therefore be incorrect.

The separate [late/stale IRQ0200 contract](ENROLLMENT_ZERO_MASK_CONTRACT.md)
remains open. It does not prevent terminating the current action without another
sensor command. The [technical manual](../TECHNICAL_MANUAL.md) records the live
evidence and its provenance; this page records the API and consumer decision.

```text
SELECTED_STRATEGY=typed contact-unusable diagnosis; terminal abort
FUNCTIONAL_RECOVERY_IMPLEMENTED=NO
FUNCTIONAL_RECOVERY_BLOCKED_BY_SEPARATE_IRQ0200_ISSUE=YES
SEPARATE_PROTOCOL_ISSUE=OPEN
AFTER_ZERO_NEW_OUT=0
AFTER_ZERO_0x20=0
AFTER_ZERO_0x32=0
AFTER_ZERO_REARM=0
AFTER_ZERO_HIDDEN_RETRY=0
```

## Reviewed stack and evidence

The review checked the installed Fedora 44 package versions: libfprint
`1.94.100-1.fc44`, fprintd `1.94.5-5.fc44`, and the Users settings plugin from
`plasma-workspace-libs-6.7.5-1.fc44`. Library conclusions use this repository's
production libfprint source. The locally available fprintd reference's
`src/device.c` was compared byte-for-byte with the official `v1.94.5` source.
KDE conclusions use official `v6.7.5` sources, with relevant strings also present
in the installed plugin. These are source-based expectations, pending live
validation of Phase D. The versions are review provenance, not runtime pins.

## Options considered

| Option | Actual behavior | Decision |
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

## Selected boundary and manual restart

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

## Proposed live validation, not executed

This is the prompt's Case B diagnostic outcome. The production build has been
checked offline; a Phase D deployment and symmetric restoration of the previous
runtime have not been prepared. The existing full installer and uninstaller
are not such a pair: uninstall removes the integration rather than restoring
the preceding build. The following describes a future validation scope, not a
ready-to-run operator procedure.

After offline checks and manual installation of the reviewed candidate, perform
one manual enrollment through the normal consumer until the first target
zero-mask, completion, cancellation or unexpected error; then stop. The target
observation is the new explicit diagnostic followed by terminal cleanup, not
successful recovery. Record whether KDE returns to the fingerprint list as
expected and retain metadata-only logs identifying the candidate and outcome.

At zero-mask, require no further OUT (including `0x20` and `0x32`), rearm,
automatic contact, hidden retry or delivery of the held primary. Verify drained
USB with no outstanding transfers and a closed context after client Release.
Unexpected commands, continued acquisition or incomplete cleanup fail the test
and require stopping before another attempt. If zero-mask is not reached, the
specific Phase D behavior remains unvalidated; do not automatically repeat.
Neither a quiet interval nor successful cleanup proves the separate IRQ0200
contract. This proposed live test has not been executed by the agent.

The existing epoch audit has cumulative rearm counts, which can include earlier
ordinary contacts. Those counts must not be interpreted as commands after zero.
The specific terminal diagnostic and drain metadata are observable in the
journal; they are not an independent per-command USB trace.

## Offline validation

The final synthetic suites pass in normal and ASan/UBSan modes: 34 A0/graph
cases, 55 image-device cases, 65 cases with the optional Phase C probe compiled,
and 45 full TLS/stock-action cases. The zero-mask tests cover contacts 2, 4, 7
and 8, raw-value bounds, cancellation, malformed input and terminal cleanup.
They check no primary delivery or new acquisition, reject all 256 OUT controls
after the fence, and assert drained transfers and closed context. Ordinary
enrollment, VERIFY, IDENTIFY, duplicate precheck and distinct synthetic template
epochs retain their regression results. Template-epoch isolation is not a live
multi-user authorization or storage qualification.

The 23 independent Phase B specification tests still pass without a successful
rearm transition. The native production payload builds with its ABI, material
and PAM mock checks. The exported audit structure layout is unchanged. All
tests run without real USB; LeakSanitizer is disabled by the SDK runners, while
ASan/UBSan and explicit ownership/drain assertions remain active. These results
do not qualify Phase D's live behavior or improve the stock KDE error text.
