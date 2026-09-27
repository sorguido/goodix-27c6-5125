<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Enrollment zero-mask and late-release contract

Status: **partial continuation specification, not implemented in the driver**.
The executable model checks local safety constraints and demonstrates the
missing information. It has no successful rearm transition. Green specification
tests do not mean that zero-mask enrollment recovery works. Phase D separately
classifies a valid repeated-contact `36/0100/0000` as an unusable contact and
terminates the action with a specific diagnostic; it does not deliver that
primary, retry the stage or implement this candidate continuation contract.

```text
FUNCTIONAL_PATCH_READY_FOR_APPROVAL=NO
RUNTIME_ZERO_MASK_RECOVERY_IMPLEMENTED=0
DEVICE_RELEASE_BARRIER_PROVEN=0
SEPARATE_PROTOCOL_ISSUE=OPEN
FUNCTIONAL_RECOVERY_BLOCKED_BY_SEPARATE_IRQ0200_ISSUE=YES
```

## 1. Scope and observation boundary

This contract concerns only a repeated enrollment contact after its primary B0,
first `34/ACK` and manual `36/ACK`, while expecting IRQ0100. It does not change
bootstrap, VERIFY, IDENTIFY, duplicate detection, global FDT policy or the first
contact's different NAV tail. Physical contacts remain bounded by 20. A contact
is counted at its primary acquisition, not again at zero-mask or release events.

An IRQ exposes a control and a sixteen-byte body: IRQ, flags, and six raw words.
There is no demonstrated request/stage/user/generation identifier in that body.
The Linux stage index is assigned from current host state. The receive callback's
generation identifies its host submission, not when or for which contact the
firmware generated the returned bytes.

Relevant current source boundaries:

- [IRQ parser](../libfprint-driver/goodix_enrollment_post_tls_events.c) validates
  shape/control/IRQ/flags but reads no contact identifier.
- [Lifecycle adapter](../libfprint-driver/goodix_enrollment_lifecycle_adapter.c)
  assigns the current stage to the FDT observation.
- [Router](../libfprint-driver/goodix_usb_router.c) delivers concatenated frames
  in received order and fences old callbacks. This is not a device event flush.
- [Transaction](../libfprint-driver/goodix_enrollment_outbound_transaction.c)
  rejects A0 during pending OUT; the binding submits graph-ready commands
  synchronously. Merely accepting zero can therefore immediately send a command.
- [FDT state](../libfprint-driver/goodix_enrollment_fdt_state.c) currently permits
  only one down observation per stage. The specification's candidate updates
  are not present in that implementation.

## 2. Evidence and its limits

The qualified `gfusb.dll` identity is SHA256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
The target mapping is PID5125 / APP12509 / chip2504, with OEM project8 and
sensor12/ChicagoHU. Address offsets below omit image base `0x180000000`.

The enrollment engine's image-choice request reaches `OnRetryCaptureIMG`
through IOCTL `442140`, type0. For project8, the normal zero branch skips the
optional `20/aux-B0/final34`, returns software down=false, and preserves the
already processed primary for ordinary quality/diversity evaluation. The
primary's capture request has already completed before the first34; a pending
request observed during rearm is a new capture request. Configuration defaults
enable the choice branch, but registry overrides exist. These findings establish
the direction of the candidate; they do not identify every live request from USB.

On target chip2504, manual IRQ0100 uses the down helper `29210`, not the up
refinement mode selected by another chip's primary path. IRQ0200 independently
updates shared flags/down, clears the up-refinement flag, sets device state2
(or error state13 for invalid raw), and signals the general device event. It
does not complete or redeliver the prior primary request.

SetMode36 serializes command work with a host lock, resets and waits for
manual-completion event4 (`5d6ad..5d7cd`). IRQ0100 signals event4; IRQ0200
signals a different device event (`28ba9..28cec`). No host-side cancellation
or drain of the armed34 is established by sending36. The release consumer and
new-request path may subsequently request32; their SetMode calls serialize
behind the same lock. This orders host command work, not firmware generation
or delivery of old events. No observed wire correlator closes that distinction.

When not busy, the general OEM release consumer also calls `gf_check_baseisvalid` (`66a40`).
If its baseline-valid flag is false it may acquire background data with20.
Consequently, **skip20 here refers to the optional image-choice branch**; it is
not a claim that every OEM consumer of0200 can never send20. That background
path is not imported into this Linux candidate and does not redeliver primary.

### 2.1 Bounded Linux observations

Two human-operated Phase C runs reached the exact expected signature
`36/0100/0000`, body length 16, with valid framing and a valid conservative FDT
candidate. Run 1 had two accepted stages and three acquired contacts; run 2 had
one accepted stage and two acquired contacts. In each configured 3000 ms window,
the probe recorded no subsequent A0, no IRQ0200 or other IRQ, and no new OUT,
0x20, 0x32, rearm or contact. Both reported `outstanding=0`, `drained=1`,
`context_closed=1` and
successful close. These are driver/probe audits, not an independent USB trace;
the zero event has no separate timestamp from which to reconstruct duration.

The original evidence archive contains both run logs and the payload manifest,
although it was described as collected immediately after run 1. That chronology
cannot be reconciled from the archive alone. The separately recovered run 2
archive declares reconstruction from terminal output and remains secondary
evidence. Its probe and action records match the run 2 log in the original
archive; the latter has a process-exit record, while the reconstruction instead
has the wrapper's terminal-only stop/path lines. Do not silently assign the two
archives identical provenance. The original manifest matches the retained
Phase C payload and its source inventory; this supports payload consistency,
not independent attestation of live execution.

The observations confirm the signature at different enrollment stages and the
absence of recorded spontaneous A0 during these bounded observations. They do
not show that a late IRQ0200 is impossible, that a monitor was flushed, or that
a new 0x32 is safe. The H_old/H_new counterexample below therefore remains open.

## 3. Two different closure conditions

**Sample closure:** valid zero IRQ0100 is sufficient evidence, within the OEM
branch, to stop optional image selection. The primary remains available for
ordinary processing without waiting for an IRQ0200 which may never arrive.

**Release separation:** before starting another contact, the implementation
needs an observation or proved device contract that prevents the previous34's
release or duplicate from being accepted in the next contact's release slot.
This is not established by sample closure, one observed0200, a pending request,
ACK32, local drain, an empty receive batch, a new host generation, or silence
for a finite time. No supported event currently supplies this proof.

The candidate can define local sample/release handling while **leaving rearm
blocked**. `BLOCKED_UNPROVEN` in the model is a specification result, not a
proposed production wait state. It must not become an infinite wait, a hidden
timeout, an automatic retry or a runtime flag that tests set to bypass evidence.
The runtime continues to close the action at zero. Phase D distinguishes the
valid unusable-contact signature from malformed protocol input, but does not
approve or implement continuation of the same action.

## 4. Explicit candidate contract

The entry precondition is an existing primary for host contact C in action G,
completed first34 and36 OUT/ACK ownership, and expected IRQ0100. G and C label
host ownership; they are not claims about the firmware provenance of an IRQ.

```text
ZERO_MASK_BRANCH=Only expected 36/0100/0000 with valid shape and bounded raw; atomic local decision to skip optional acquisition.
PENDING_PRIMARY=Preserve the already acquired primary until ordinary delivery, cancellation or failure cleanup.
COMMAND_20=No optional image-choice20 from this branch.
AUX_B0=Not expected, acquired or delivered; unsolicited auxiliary input fails closed.
IRQ0200_OWNER=One optional host release slot for C before any new arm; actual physical provenance is not established by the slot.
IRQ0200_EFFECT=One valid observation may replace candidate down only; no extra sample, stage increment, finger-off, retry or rearm.
FDT_UPDATE=Derive an atomic candidate from0100; a valid optional0200 replaces it in receive order. No up change, no partial write, no outbound use before release separation is proven.
SAMPLE_DELIVERY=At most once after valid zero, independently of optional0200, through ordinary quality/diversity processing; logical finger-off at most once.
NEXT_32_ALLOWED_WHEN=Sample decision requests another contact, contacts<20, no cancel/error/terminal, OUT ownership clear, and a proven device release-separation boundary. Last prerequisite has no supported producer.
REARM_RULE=At most one32 per next-contact admission after all prerequisites; currently blocked, no positive rearm transition modelled.
DUPLICATE_IRQ0200=A second observable0200 in the open slot fails closed before another FDT update or delivery; after terminal fence it has no effect.
STALE_IRQ0200=Old callback generation is ignored; old firmware bytes in a current callback cannot be identified reliably. Never relabel them using a guessed stage or user.
EARLY_NEXT_IRQ0002=Fail closed before proven separation and authorized32/ACK; no defer queue, new contact or generation invented.
TERMINAL_STAGE_RULE=After ordinary terminal sample decision, fence and cleanup; no32 or waiting for optional0200; later callbacks cannot change action state.
FAIL_CLOSED_CASES=Bad framing/checksum/shape/control/IRQ/flags/raw, unexpected auxiliary, duplicate release, early contact/delivery and exhausted contact bound fail; cancellation fences; unresolved ownership forbids continuation (BLOCKED_UNPROVEN in this specification).
```

Raw policy for this **candidate branch only**: exactly six little-endian words;
each `word >> 1` must be in `[1,254]`. Encode each down word as the two bytes
`80,value`. Validate all six before replacing the candidate. This conservatively
combines the existing Linux no-overflow bound with the OEM helper's invalid
0/ff exclusion. It deliberately does not copy the OEM's truncation or continue
with an old table after invalid raw. The current global FDT policy is unchanged.
In particular, current Linux IRQ0200 derivation permits components0 and255;
the model's restriction to1..254 also for optional0200 is an additional local
proposal, not a description of that runtime implementation.

The model's `sample` then logical `finger_off` effects describe a proposed
libfprint mapping. OEM primary preservation alone does not prove Linux callback
ordering, asynchronous feature extraction or completion-hold correctness.
Those integration checks belong to any future implementation; these effect
records are not calls into libfprint and are not production validation.

The optional slot is not a stale-event detector. Updating a candidate within it
is a conditional host attribution; the candidate is never used for32 while
release separation is unproved. This partial contract therefore cannot satisfy
the full requirement to accept every legitimate release while rejecting every
same-byte stale release. That limitation is an explicit reason for readiness NO.

If a full contract is later proved, serialize the chosen down-table snapshot
at actual32 dispatch. An observation after dispatch cannot rewrite bytes already
submitted. Recheck cancellation, terminal decision, contact bound, ownership and
single-admission status at dispatch, including reentrant framework callbacks.

## 5. Required interleavings

| Case | Local result | New32 / outstanding proof |
| --- | --- | --- |
| A1: zero, no0200 | Preserve/deliver primary once; derive candidate down from0100. No mandatory0200 wait. | Blocked: absence of release is not proved by silence. |
| A2: zero then immediate0200 | Establish slot during zero handling before processing the next frame; replace candidate down once. | Blocked even when both frames share one IN completion. |
| A3: zero, skip decision,0200 | Same contract as A2. Skip is internal and atomic, not an additional wire event. | No separate permissive window or extra command. |
| A4: next request pending, late0200 | Latch request; release changes only candidate down. Cancel/terminal fences take precedence. | Request is not permission to arm; one0200 does not prove no later duplicate. |
| A5: duplicate/stale0200 | Recognizable duplicate fails closed; old callback is ignored. Same-byte stale firmware event remains indistinguishable. | No new contact admitted on guessed provenance. |
| A6: early newIRQ2 | Fail closed; retain no usable pending sample/request/table after failure. | No22, no new primary count and no32. |

An ordinary terminal decision may finish after one primary delivery without
requiring optional0200. This is local action closure, not proof that a subsequent
action's newly submitted IN cannot read old firmware bytes. Fresh software
objects and old-callback fencing establish memory/ownership isolation only.
No cross-action device flush or fprintd user authorization is claimed.

## 6. Executable specification and counterexamples

Run the independent standard-library model tests:

```sh
python3 -I -B libfprint-driver/tests/spec/test_irq0200_late_contract.py
```

The [model](../libfprint-driver/tests/spec/zero_mask_contract.py) is separate
from the C driver and production test runners. It cannot open USB, launch a
process, load material or emit a command. No expected-failure marker disguises
missing runtime support. There is no setter or synthetic receipt that can make
the unproved device barrier true. The maximum-one-rearm constraint is checked
as an upper bound with zero emissions; **the successful one-rearm case remains
unproved**, rather than being made green by an invented barrier.

The tests use hard-coded local effect expectations, frame-shape/range cases,
bounded event permutations and per-prefix invariants. Primary identity is an
opaque synthetic token. Principal/contact labels appear only on the host
context; IRQ input has no oracle-only provenance field.

The central counterexample consists of two possible histories with identical
observations at the next contact's release slot:

```text
H_old: the received 34/0200/0000/raw belongs to the previous34
H_new: the received 34/0200/0000/raw belongs to the current34
Observed control, body, raw and current callback generation: identical
Required decision under strict stale rejection: reject H_old, accept H_new
```

A deterministic receiver cannot make those different decisions from identical
inputs. This is an information-boundary demonstration, **not proof that the
firmware actually emits H_old**. The missing proof must exclude that history
with a target-supported ordering/replacement guarantee or make it impossible
through an equally supported protocol boundary. FIFO order of bytes already
emitted does not by itself establish when an old monitor stops emitting.

Other counterexamples distinguish old callback tokens from old bytes returned
by a new IN, and a finite silent prefix from an event arriving just after it.
An empty host queue or one observed release is not promoted to a firmware fence.

## 7. Approval boundary

| Readiness requirement | Result |
| --- | --- |
| 1. Late0200 ownership | Host slot defined; physical stale/current separation not proved. |
| 2. Primary fate | Preserve for one ordinary delivery or dispose on cancel/error. |
| 3. Optional20 decision | Skip in the zero branch. |
| 4. FDT update | Exact conservative candidate rule defined; no outbound use yet. |
| 5. Boundary before32 | Unproved; no event/token/timeout accepted as its producer. |
| 6. Duplicate/stale release | Observable duplicate fenced; same-byte stale/current ambiguity remains. |
| 7. Terminal stage | No rearm; model delivery/fence defined, async libfprint integration still to validate. |
| 8. Hidden retries | None in the candidate. |
| 9. Bounded contacts | Already acquired primary counted once; no admission beyond20. |
| 10. Evidence or conservative safety | OEM host semantics established; conservative blocked model does not establish useful continuation. |
| 11. Sufficient mechanical patch tests | Local effects/counterexamples covered; positive rearm and cross-stage release tests cannot yet be qualified. |

Primary fate, optional20/aux decision, local FDT candidate rule, terminal/cancel
behavior and bounded accounting are explicit. Safe continuation into a new
contact remains unproved. The model documents this obstruction rather than
qualifying an unusable indefinite wait or a guessed recovery sequence.

To change readiness to YES, establish the release-separation contract on this
target, then cover positive32 dispatch, immutable table snapshot, release during
OUT/ACK32 and newIRQ2, duplicate/stale events, reentrant cancel and the terminal
case against that contract. A new live experiment is not automatically required
by the absence of an old zero-mask trace; a sufficient static/protocol proof may
close it. No functional implementation, install, privileged operation or sensor
test is authorized by this specification.

## 8. Separate issue: late/stale IRQ0200 before the next 0x32

```text
SEPARATE_PROTOCOL_ISSUE=OPEN
ISSUE=late/stale IRQ0200 release separation before next 0x32
DEVICE_RELEASE_BARRIER_PROVEN=0
```

This issue owns the missing device-side separation before continuation into
another contact: identical H_old/H_new observations, no demonstrated wire
correlator, and no qualified replacement/flush guarantee. The two silent Phase C
windows add evidence about those runs without closing this issue. No sleep,
quiet window, timeout, host generation or drained callback queue grants a 0x32.

Phase D's independent change is strictly diagnostic. An exact valid zero
signature closes the action through the existing terminal fence, cancellation
and drain path; the held primary is discarded. It adds no OUT, auxiliary
acquisition, FDT update, stage advancement, rearm or hidden retry, and has no
observation timer. Malformed, reserved, wrong-control and wrong-IRQ input still
fails closed. The global FDT acceptance policy remains unchanged.

The driver uses a terminal `FP_DEVICE_ERROR_GENERAL` with an explicit contact
diagnostic. It deliberately does not emit an enrollment retry: the ordinary
retry API continues the action, while a terminal retry maps poorly to the
examined stock KDE consumer. fprintd still reports `enroll-unknown-error` with
`done=true`; KDE still shows its failure state. The
[consumer review](ENROLLMENT_ZERO_MASK_UX.md) records the API and UI limitations.
This improves diagnosis, not successful enrollment recovery or the stock UI's
error text.

A later user-requested attempt must use the existing close/open and bootstrap
lifecycle. Phase D adds no automatic action, reopen or alternate synchronization
sequence. Closing host state is not proof of firmware release separation; the
existing bootstrap/receive synchronization is not promoted to a newly proved
late IRQ0200 barrier. Functional continuation of the interrupted enrollment remains
blocked by this separate issue.
