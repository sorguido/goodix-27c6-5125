<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Enrollment zero-mask and late-release contract

Phase E implements **functional recovery under an explicitly accepted, limited
host-side rule**. The ordinary production ENROLL path preserves the primary and
can continue the same action. Offline validation is complete; live behavior is
not yet validated. Phase D remains the diagnostic fallback. The general firmware
release-separation issue remains open.

```text
RUNTIME_ZERO_MASK_RECOVERY_IMPLEMENTED=1
DEVICE_RELEASE_BARRIER_PROVEN=0
SEPARATE_PROTOCOL_ISSUE=OPEN
FUNCTIONAL_RECOVERY_BLOCKED_BY_SEPARATE_IRQ0200_ISSUE=NO_UNDER_PHASE_E_AUTHORIZATION
LIVE_VALIDATED=0
```

## 1. Entry and scope

Recovery is enabled only for production ENROLL, after the first contact, at the
expected repeated-contact IRQ0100 slot: primary B0 acquired and held, first
34/ACK and manual36/ACK completed, no pending OUT, exact `control=0x36`,
`IRQ=0x0100`, `flags=0x0000`, valid checksum/frame/body 16, and all six little-endian
raw words satisfying `1 <= (word >> 1) <= 254`. No wrapping or truncation is
allowed. The existing contact accounting must identify exactly one pending
primary, with no previous zero window still open. The runtime opt-in is private
to the ENROLL setup; constructing a parser alone does not enable recovery.

The first-contact NAV tail, bootstrap, VERIFY, IDENTIFY, duplicate precheck,
IDENTIFY→ENROLL authorization, global FDT acceptance and persistent sensor state
are unchanged. Maximum contacts remain 20, maximum accepted stages remain 8,
and the existing SIGFM diversity convergence policy remains in force. A contact
is counted at primary acquisition, never again at zero or late release.

The optional Phase C diagnostic probe, when explicitly compiled and enabled,
intercepts first and retains its frozen/no-OUT observation behavior. It is not
part of the normal production build.

## 2. Primary, FDT and sample decision

The local `ZERO_MASK_RECOVERY` event performs these effects once:

1. Derive a temporary 12-byte DOWN table from the six raw words. Each pair is
   `0x80, word >> 1`. Validate every channel and stage relationship before a
   single atomic table copy. Associate it with this acquired contact.
2. Skip optional image-choice20, auxiliary B0 and final auxiliary34 entirely.
3. Deliver the held primary once through the existing preprocessing,
   quality/diversity and SIGFM/template pipeline, then clear software finger-down.
4. Wait for the ordinary host sample decision. No timer or release event grants
   another request.

A zero mask is not itself a quality pass or proof of physical finger removal.
An accepted primary advances at most one stage. Quality/extraction failure uses
the existing terminal error policy. An ordinary diversity rejection can produce
its existing **visible** retry and next-sample request within the same 20-contact
bound; the zero branch introduces no hidden retry or extra contact policy.

Relevant implementation boundaries:

- [Event parser/window](../libfprint-driver/goodix_enrollment_post_tls_events.c)
  recognizes zero and the single passive stale release.
- [FDT state](../libfprint-driver/goodix_enrollment_fdt_state.c) validates and
  commits the local table atomically.
- [Model](../libfprint-driver/goodix_enrollment_model.c),
  [pipeline](../libfprint-driver/goodix_enrollment_pipeline.c) and
  [lifecycle](../libfprint-driver/goodix_enrollment_lifecycle_adapter.c) retain
  primary ownership and ordinary stage/contact accounting.
- [USB binding](../libfprint-driver/goodix_enrollment_fpi_usb_binding.c) owns OUT
  dispatch and the passive-release exception.
- [Device context](../libfprint-driver/goodix_fpimage_device.c) waits for the
  normal libfprint `AWAIT_FINGER_ON` transition after asynchronous host evaluation.

## 3. Limited stale-release window

After a nonterminal zero has entered normal primary processing, the host window
opens. It remains open while the host decision is pending, through the one next
32/OUT completion and ACK32, until the first valid newly armed IRQ0002.

| Input during this window | Effect |
| --- | --- |
| First exact34/0200/flags0, body 16/checksum/raw valid | Record and consume passively as previous-contact release. No FDT update, primary delivery, stage/retry change, contact callback, command or extra rearm. |
| Same valid release while OUT32 is pending | The same passive-only exception; it cannot complete or replace the pending OUT. |
| Second recognizable0200 | Fail closed. |
| Malformed release, invalid raw, wrong flags/control or unexpected event | Existing terminal failure path. |
| IRQ0002 before actual32 completion/ACK | Fail closed; no image command or new contact admission. |
| First valid IRQ0002 after actual32/ACK | Close window and enter the ordinary new-contact graph. |
| Cancel, terminal completion or error, including failed OUT32 | Close window, fence and drain; no rearm. |

No late-release FDT refresh is used: the immutable candidate derived at zero is
already the table for the single next32. This avoids changing a serialized or
in-flight request. No background-image refresh is introduced.

After the valid new IRQ2,0200 belongs solely to the ordinary graph. It fails in
an incompatible slot. In the ordinary release slot, indistinguishable stale
bytes **can be accepted as the current release**; this is the remaining risk
explicitly accepted for Phase E, not a hidden guarantee of stale detection.
Old callback generations are still ignored/fenced; new-generation IN callbacks
can carry firmware bytes whose original contact is unknown.

## 4. Request, terminal and fallback rules

At most one new32 follows each nonterminal zero transition. The model must be
waiting for command32, ordinary host evaluation must have requested another
sample, contact budget must remain, OUT must be free, and cancel/error/terminal
fences must be absent. The context defers rearm until the A0 handler unwinds;
this also prevents reentrant host callbacks from sending a command inside zero
processing. Submission consumes the pending-request permission once.

For a terminal primary, zero can complete the action without a release0200;
there is no32, rearm or release wait. Late callbacks after the terminal fence
cannot modify state. A failed OUT32 explicitly notifies the context even when
IN is already pending, so failure cannot leave an uncompleted action waiting
indefinitely for sensor input.

If strict recovery prerequisites are unavailable, the exact valid zero signature
retains Phase D's typed contact-unusable diagnostic and terminal GENERAL path.
Malformed input is still protocol failure. Fallback discards the pending primary
and follows the existing cancellation/drain lifecycle without new commands.
No cosmetic retry status substitutes for functional recovery; see the
[consumer review](ENROLLMENT_ZERO_MASK_UX.md).

## 5. Evidence and accepted uncertainty

The two human Phase C runs reached valid zero at different contacts and recorded
no A0/0200 during their configured 3000 ms windows, with no post-zero command
and complete drain/close. They do not bound all firmware latency. Their archive
provenance and chronology limitation remain in the
[technical manual](../TECHNICAL_MANUAL.md#205-isolated-zero-mask-observation-probe).

The qualified OEM APP12509 reconstruction links PID5125, chip2504, project8,
ChicagoHU/sensor12 to skipping optional20/auxiliary B0, preserving the
preprocessed primary, clearing software finger-down and issuing a later32 only
for another request. Its zero IRQ0100 path uses the target down-table helper.
This establishes the host behavior being replicated, not a general firmware
flush/replacement guarantee. Rockytkg informs SIGFM/preprocessing only; it is
not evidence for this Goodix protocol or FDT/rearm contract.

An IRQ carries control, IRQ, flags and six raw words, with no demonstrated
contact/request/user/generation identifier. The Phase B counterexample remains:

```text
H_old: 34/0200/0000/raw belongs to the previous contact's34
H_new: 34/0200/0000/raw belongs to the current contact's34
Observed bytes and current receive generation: identical
```

A deterministic host cannot reject H_old and accept H_new from identical inputs.
This does not prove that the firmware emits H_old. Phase E deliberately uses the
first valid newly armed IRQ2 as its **host boundary** and accepts the residual
case above. Silent time, a drained host queue, one release or a fresh software
epoch is never promoted to a device barrier.

## 6. Offline checks and live gate

Public synthetic entrypoints:

```sh
sh libfprint-driver/tests/run_goodix_enrollment_a0_test.sh
sh libfprint-driver/tests/run_goodix_zero_mask_probe_test.sh
python3 -I -B libfprint-driver/tests/spec/test_irq0200_late_contract.py
python3 -I -B operator_kit/phase-e-zero-mask/test_kit.py
```

The C parser/binding suite passes 60 cases; the actual libfprint image-device
suite passes 58, and its probe-enabled variant 68, each in normal and combined
ASan/UBSan builds. Tests cover zero contacts 2/4/7/8, raw bounds, command omissions,
single delivery/rearm, terminal zero, late release before host evaluation,
during OUT32, after ACK and after newIRQ2, duplicates, malformed input,
cancellation, old-generation callbacks, OUT32 errors, fresh objects and 20-contact
limits. Supplementary internal full-TLS/SIGFM synthetic regressions pass 53 cases
in both modes, including quality rejection, diversity retry, VERIFY, IDENTIFY,
duplicate precheck, handoff and zero→ordinary distinct-template epochs. Synthetic
principal metadata is not live multi-user authorization/storage validation.
LeakSanitizer is disabled by the existing SDK runners; explicit resource
ownership, drain and close assertions remain enabled.

The 23 Phase B Python specification tests remain a **historical stronger-contract
model** with no successful rearm. They demonstrate the missing firmware proof,
not the implemented Phase E acceptance rule. Runtime coverage is supplied by the
C tests above; the model is not relabeled as a successful recovery test.

The production build checks ABI and host-test symbol exclusion and runs material
and PAM mocks. The separate zero audit does not enlarge exported existing audit
structures. Independent review corrected pending-OUT failure notification and
interrupted rollback handling; the runtime and kit were accepted after review.

The [reversible operator kit](../operator_kit/phase-e-zero-mask/README.md) provides
manual install, normal KDE enrollment, metadata collection and restoration of
the previous runtime. No installation, sudo, USB access, protected-material read
or live test is performed by the agent. Target live PASS requires logged recovery,
ordinary UI continuation and completion plus drain/close; no zero means
inconclusive. Stop/rollback on unexpected behavior. All hardware invariants,
including no persistent sensor write and Windows compatibility preservation,
remain unchanged.

## 7. Separate general IRQ0200 issue

`SEPARATE_PROTOCOL_ISSUE=OPEN`: general physical stale/current discrimination
across contacts/actions is unresolved. Phase E narrows the implemented host
contract under the user's explicit risk acceptance. It neither closes this
issue nor leaves functional recovery blocked pending a stronger proof.
