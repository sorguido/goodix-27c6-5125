# Cold-login immediate contact: resolution review, 2026-09-19

## Post-live decision: same-action result

This section supersedes the initial decision below. Entry HEAD was
`a27259194de10a706837f4259d774f5d91a47e8c`, branch `development`, clean.
The diagnostic runtime was recipe `c7238d00ae618edbdffc423cdb21ec77fb7a3a5a`,
patch SHA-256 `b0fa8d3dade95bf13b1b59295709583ae95b84f859b9ec44296c7d3c209a0936`.
The new task authorizes evaluating A first, then B, and preparing one candidate
only if justified. The temporary experiment is not promoted to production.

### What the new action establishes

Source: [`goodix-same-action-live.txt`](goodix-same-action-live.txt), lines 10–16,
plus the User's physical account: one Enter, continuous immediate contact for
slightly over 4 s, complete lift for slightly over 1 s, recontact for slightly
over 3 s; no second Enter or third contact within that action.

| Time | First cold action |
| --- | --- |
| 20:42:56 | Baseline masks 63, 0, 0; waiting_irq2 |
| 20:43:01 | One reverse80 event, temporally consistent with the reported lift |
| 20:43:16 | Cancel in FIRST_IRQ2; first_image=0; drained; no retry/rearm/reopen/reset/persistent write reported |

There is no accepted IRQ2, primary fingerprint image, SIGFM extraction or
matcher decision. Calling this a bad finger or a NO_MATCH is incorrect.
The 20:43:23 wait is a separate action; its physical sequence is not established
by this testimony. The 20:48:32 MATCH (lines 33–43) is another authentication:
it confirms the temporary runtime can acquire/match, not cold-login success.
Installation-time sudo fingerprint authentication preceded cold boot; no
evidence supports treating it as causal here. Generation=1 is reused in fresh
contexts, so action identity also requires timestamp/process/audit boundaries.

### Causal challenge: SUPPORTED, not PROVEN

The **host update is PROVEN** in the actual temporary patch and production
code (`goodix_post_tls_lifecycle.c`, `goodix_fdt_irq_policy.c`):

```text
36(seed) -> sample1(raw1,63) -> T1
36(T1)   -> sample2(raw2, 0) -> T2
20       -> baseline B0
36(T2)   -> sample3(raw3, 0) -> T3
32(T3)   -> wait
Tn[channel] = 80 || ((raw_n[channel] >> 1) & ff)
```

NAV/82/ACK steps are omitted only from this dataflow sketch. The diagnostic
patch passes validated metadata through the unchanged table transform even
when the first mask is 63. Thus the subsequent masks use updated references;
zeros do not independently certify finger absence. Stable raw deltas cannot
certify absence either. This explains how a held finger **could** become the
reference, a lift could become a reverse transition, and recontact could return
toward that reference without IRQ2. It is an inference about the firmware:
there are no channel values/comparator internals in the log, and analog
adaptation or an arming fault is not excluded. The reverse80 timing is not a
universal finger-off specification. The narrow model “valid clean baseline,
only the initial edge was missed, any fresh edge recovers” fails this test;
not every possible edge-detection defect is falsified.

`first_image=0` counts the primary `22` path. Reaching FIRST_IRQ2 necessarily
passes `handle_plaintext(FDT_B0)`, baseline decode/copy and the third sample.
Therefore a bootstrap image from `20` was accepted, although no fingerprint
image was delivered to matching. This is call-flow evidence, not inspection of
its contents. A held finger may contaminate both FDT and image references.

### A before B: exact selection boundary

**A is preferred in size, but not implementable as a justified recovery yet.**
The current strict driver already rejects a nonzero baseline mask instead of
learning it. Recovery needs a trustworthy clean-state transition before
continuing. `36` is a manual sample, not a demonstrated finger-off subscription.
Accepting zero after learning contact or treating reverse80 as absolute absence
would beg the causal question. Repeating samples against a frozen seed is
polling without a proven empty-state predicate, and does not make a held finger
leave the sensor. The validated `34/IRQ0200` path uses an up-table derived from
IRQ2 after the first acquisition. Even enrollment's contact IRQ0100 does not
derive that table (`goodix_enrollment_post_tls_events.c:319`,
`goodix_enrollment_fdt_state.c:67`); the source remains IRQ2. Extending the raw
interpretation and using `34` during setup is a new target contract. A range
check passing, a synthetic IRQ0200 or an ACK would not prove that contract.
Normal PAM also does not turn FingerPresent/FingerNeeded properties into a
setup recovery dialogue; it displays VerifyStatus messages. A driver-only wait
must not promise transparent success while the operator keeps the finger down.

**B's smallest real boundary is before the greeter accepts Enter, not open.**
The installed fprintd 1.94.5 path is directly traced in the local Fedora source:
`pam_fprintd.c:claim_device` -> `device.c:fprint_device_claim` -> `fp_device_open`
-> Claim reply -> VerifyStart -> driver activation. The observed Plasma action
starts this PAM path after Enter. `img_open` currently acquires materials and
the USB interface; secure/TLS/FDT start in activate. `device.c:1756` replies and
emits VerifyFingerSelected without waiting for activation; PAM displays it.
Starting the daemon does not Claim/open. Moving calibration to Claim/open would
still race the specified immediate physical contact, even with a later prompt.

A real B design would keep fprintd as sole owner, complete preparation before
enabling login input, retain the prepared session, and gate acquisition on the
authorized action, with bounded idle/cancel/suspend cleanup. That requires an
actual greeter/readiness integration and a split driver lifetime, not a boot
ordering drop-in. More fundamentally, moving `20` earlier cannot guarantee a
non-biometric baseline without a reliable empty-sensor predicate; deferring it
leaves image calibration exposed to the finger after Enter. A contact while
armed but before Verify also needs correct presence/removal handling. These
are concrete reasons not to label B a safe completed fix from this evidence.
The new task permits its evaluation; lack of authorization is not the blocker.

**One missing device-side fact:** the valid APP12509 pre-image empty-state
transition after a contact-bearing `36/IRQ0100`. Specifically, can `34` be used
there, with what valid up-table provenance absent IRQ2, and does its IRQ0200
certify the clean state needed for calibration in the same session? This is
one protocol contract, not a request for more A/B timing runs. The same-action
log never exercised it; post-image evidence and other chips cannot establish
it. No early-34 live sequence is presented as ready or safe. Evidence should
address exactly this contract; a broad capture campaign is not requested.

### Compact community architecture comparison (read-only)

Repository: `goodix-fp-linux-dev/libfprint`, master observed at immutable commit
`eebdacff358c90e3f909ae4f5526fff194fe3f7c`. Sources were read in `/tmp`; no code
was imported or executed. These are architectural examples, not APP12509 proof.
“Ready” below is the host/protocol milestone, not measured analog readiness.
PAM can invite contact during asynchronous action setup; Claim/open completion
can precede that prompt but still follows Enter in the target workflow.

| Driver / pinned source | open/init | verify/identify or capture | Ready for finger | Setup while UI invites contact? | Finger present during setup |
| --- | --- | --- | --- | --- | --- |
| [Goodix MOC](https://github.com/goodix-fp-linux-dev/libfprint/blob/eebdacff358c90e3f909ae4f5526fff194fe3f7c/libfprint/drivers/goodixmoc/goodix.c#L1087) | Version, config, template list; complete open after init | Shield, CAPTURE_DATA, IDENTIFY | Reports NEEDED at capture; firmware owns acquisition | Init precedes Claim reply; action setup can overlap prompt; physical touch after Enter can precede either | No host empty-baseline guard; firmware behavior opaque. Init includes flash config and possible storage deletion: expressly not reusable here |
| [FPC MOC](https://github.com/goodix-fp-linux-dev/libfprint/blob/eebdacff358c90e3f909ae4f5526fff194fe3f7c/libfprint/drivers/fpcmoc/fpc.c#L1516) | INIT/event, load DB, then open complete | ARM/event, GET_IMG, IDENTIFY, ABORT | NEEDED at ARM, PRESENT at FINGER_DWN | Init precedes Claim reply; ARM/capture runs after action request and may overlap prompt | Explicit firmware events; no visible host proof of finger-free calibration |
| [Elan MOC](https://github.com/goodix-fp-linux-dev/libfprint/blob/eebdacff358c90e3f909ae4f5526fff194fe3f7c/libfprint/drivers/elanmoc/elanmoc.c#L1001) | Bounded status polling for 03, mode, version, dimensions, enrolled count | Set mode and firmware verify command/wait | Status gate during open; verify wait during action | Readiness polling is before open complete; action command can overlap prompt | Explicit not-ready failure; 03 is not a documented finger-absence predicate. USB reset in this driver is not imported |
| [Synaptics](https://github.com/goodix-fp-linux-dev/libfprint/blob/eebdacff358c90e3f909ae4f5526fff194fe3f7c/libfprint/drivers/synaptics/synaptics.c#L1322) | FPS_INIT in probe and again in open; success/already-initialized accepted, busy handled by cancel | VERIFY_USER / ordered identify | Init callback completes open; firmware capture events govern action | Probe can run at discovery; open init precedes Claim reply; action readiness can overlap prompt | Explicit FINGER_REPORT tracks on/off; completion can wait for removal. No host empty-reference learning shown |
| [Elan image](https://github.com/goodix-fp-linux-dev/libfprint/blob/eebdacff358c90e3f909ae4f5526fff194fe3f7c/libfprint/drivers/elan.c#L632) | Interface claim and host parameters only | Activate queries version/dimensions; AWAIT_FINGER_ON starts background/calibration, then capture | Calibration complete starts capture; activate-complete was earlier | **Yes**: calibration starts after activation in AWAIT_FINGER_ON | Bounded calibration status cycle 01→03; image path diagnoses possible finger-during-calibration. No general prevention is proved |
| [AES2501 image](https://github.com/goodix-fp-linux-dev/libfprint/blob/eebdacff358c90e3f909ae4f5526fff194fe3f7c/libfprint/drivers/aes2501.c#L679) | Interface claim | Register initialization in activate, then histogram detection and capture | Init completion precedes start_finger_detection | **Yes**, action initialization can overlap the PAM prompt | Histogram examines current presence after init; no learned empty-FDT guard. Polling behavior is not copied |

The signal is separation of setup from matching plus chip-specific status
contracts. It is not “all drivers calibrate before Enter”, nor evidence that
a callback or service startup repairs the Goodix boundary.

### Offline closure and methodological decision

The existing lifecycle test now checks the actual outgoing baseline tables:
seed in first 36, previous raw-derived table in second/third 36, third table in
32. One new host-only case uses the observed mask sequence 63/0/0, one reverse80
and cancellation, with synthetic raw/image data. It asserts one baseline B0,
zero primary images/finger callbacks/retries and no invented IRQ2 suffix.
This characterizes the risky host behavior of the diagnostic, not firmware.
18/18 variant and 13/13 baseline tests pass normally and with ASan/UBSan.
`production/check-source.sh` passes. Production sources/ABI and deployment
scripts are unchanged; no redundant build/ABI run or installation is claimed.

PM decision: **HUMAN_REQUIRED**, no sufficiently justified A or B candidate.
The new evidence changes the question from a missed first contact to the
pre-image clean-state contract; the next test cannot be another paced login
or parser relaxation. Without that contract, no new install/rollback pair or
live is advertised. The historical pair remains available.

Read-only host check: the temporary runtime, wrapper, PAM override, drop-in 96
and transaction state are absent; effective ExecStart is D293 and service is
inactive. D293 wrapper/drop-in and vendor PAM hashes match the pinned baseline.
No sensor, protected material, service mutation or privileged action was used.

## Initial investigation (historical)

The remainder preserves the earlier investigation. Its missing same-action
experiment and authorization status are superseded by the post-live decision
above; historical observations and source provenance remain valid.

Baseline: `development`, `9f8dcb8eb6c652c8b511284f33e64b5be2dac7cb`.
The worktree was clean at entry. This is a topic review, not a new D-number.
The Italian technical manual remains the canonical narrative.

## Decision

`HUMAN_REQUIRED`: the requested immediate-contact login is **not fixed**.
No production candidate is selected. The source-supported explanation is a
collision between physical contact and calibration/arming started after Enter.
Its device-side mechanism remains unresolved. Two distinct failures must not
be conflated: the current parser can reject contact during baseline sampling;
the historical relaxed parser can get past that point and then receive no IRQ2.

The proposed D301 activation callback cannot solve the externally visible
timing contract: fprintd replies to VerifyStart and emits VerifyFingerSelected
without waiting for libfprint activation. Moreover, stable baseline samples do
not prove that the baseline was measured without a finger. These two findings
invalidate selecting either D301 or the old flag relaxation as a resolution.

No install/rollback pair is advertised: there is no justified production delta
to deploy. Providing one for unchanged production would misrepresent readiness.
The build below is an offline artifact, not an installed runtime. No sensor,
sudo, service activation, protected-material loader or new capture was used.

## Evidence coverage and provenance

All 11 original files under this issue directory were enumerated and read:
the handoff, both audit reports, all six A/B journals, and both complete cold
boot journals. The last two include unrelated system/service messages; the
analysis separates login attempts from later sudo activity. Original files are
preserved. Their baseline Git blobs identify the exact inputs.

Additional sources inspected:

- Current `libfprint-driver/` production adapter, secure/post-TLS lifecycle,
  FDT policy, runtime seed interface and cleanup path; production manifests.
- Fedora source snapshots: `reference/libfprint-fedora44-1.94.100/source/` and
  `development/reference/fprintd-fedora44-1.94.5/source/`, with provenance.
- Read-only history: D297 login diagnostics, D298, D301 commit
  `5bda2ab4bf6d86a7188dbee600fcc1f3f004d554` against parent
  `73dab22227909d3496672b0a47ddd4870f078b17`. These login D297/D298 labels
  belong to historical experimental work, not the later KScreenLocker and
  publication milestones carrying those numbers in the current manual.
- Manual sections D252–D259, D279/59 and current production/deployment state.
- Target D255 capture directory, operator markers and its preserved sanitized
  D255/D256 analyses/timeline; independent raw hash/packet count check and
  agreement of 20 selected A0 control headers/timestamps with that timeline,
  without body decoding or extraction; D258/D259 static audits and targeted OEM
  disassembly at `development/private-root/analysis/D230/work/GoodixExport/`.
  No decryption, secret extraction or protected cache contents were needed.
- `development/Rockytkg/snapshot/PROVENANCE.md`, licensing ledger and relevant
  `goodix_capture.c`, `goodix_init.c`, `goodix_base.c`. Reference revision:
  `227eba219fa9e3fbac5bd59aca79f624f67cd11b`. No code was copied into production.
- Existing host journal, queried read-only without privilege; selected audit
  records are preserved in `journal-evidence-2026-09-15.tsv`.

The TSV contains 49 existing audit messages, boot IDs, journal receipt UTC and
monotonic microseconds. It deliberately excludes host/account/process identity,
raw frames, images and secrets. Query: `journalctl --no-pager -o json --since
'2026-09-15 00:00:00' --until '2026-09-17 00:00:00' -u fprintd.service
--grep='GOODIX_D299|GOODIX_D300|rejected_a0'`, in Europe/Rome. Only
GOODIX_PRODUCTION_EPOCH_AUDIT, GOODIX_D299_FORENSIC_AUDIT and
GOODIX_D300_PRECAP_AUDIT messages were retained. The export is evidence, not a
new collector or an executable test workflow. Receipt time need not equal the
original application timestamp to the microsecond.

## Normalized first-login observations

Here `t=0` is “About to call VerifyStart”, not physical finger-down. A/B logs
have second resolution. `E` means unknown/protocol error, `T` timeout, `M` match.
All E/T entries have `first_image=0`; all M entries have `first_image=1`.

| File | VerifyStart local wall time | Reply Δs | Result Δs | USB submits |
|---|---|---:|---:|---:|
| 1 | 10:14:43 | 0 | E +1 | 52 |
| 1 | 10:14:48 | 0 | E +1 | 52 |
| 1 | 10:14:52 | 0 | E +0 | 52 |
| 1 | 10:15:00 | 1 | T +46 | 70 |
| 2 | 10:16:52 | 0 | M +10 | 76 |
| 3 | 10:18:33 | 0 | E +0 | 58 |
| 3 | 10:18:37 | 0 | E +0 | 67 |
| 3 | 10:18:41 | 0 | E +0 | 67 |
| 3 | 10:18:44 | 0 | E +1 | 52 |
| 3 | 10:18:48 | 0 | M +5 | 75 |
| 4 | 10:19:55 | 0 | M +5 | 76 |
| 5 | 10:20:58 | 0 | E +0 | 58 |
| 5 | 10:21:02 | 0 | E +0 | 52 |
| 5 | 10:21:05 | 0 | E +1 | 67 |
| 5 | 10:21:10 | 0 | E +0 | 58 |
| 5 | 10:21:14 | 0 | M +2 | 76 |
| 6 | 10:22:17 | 0 | M +2 | 76 |

The successful action at 10:15:59 in file 1 is sudo, not successful login.
The earliest reproducible *logged* divergence is a protocol error within
0–1 seconds versus continued acquisition and later match. It is not the
VerifyStart reply, matcher or template comparison. Submission counts alone do
not identify an exact frame: fragmentation and receive completions matter.
Recorded cleanup drains; no retry/reset/reopen/persistent write is reported.

The controlled pair provides finer timestamps and independent cold boots:

| Event, Δs from VerifyStart | PRE-HELD | DELAYED |
|---|---:|---:|
| VerifyStart origin, monotonic seconds | 20.099483 | 15.872057 |
| Method reply | 0.018027 | 0.016155 |
| PAM finger prompt | 0.018036 | 0.016166 |
| Greeter information message | 0.018542 | 0.016572 |
| Secondary clean-drain error | 0.492639 | absent |
| Primary unexpected A0 error | 0.492938 | absent |
| Result | unknown +0.493212 | match +2.980607 |
| SIGFM extraction | absent | +2.978377 |
| Production audit | +0.494677 | +2.981895 |
| first_image / submits | 0 / 52 | 1 / 76 |

Source lines: case1 2025–2034; case2 2024–2045. The case1 error is 0.474911 s
after the method reply. The later case1 action starts at 27.862561 and times
out after 45.007994 s; it is no longer a pristine cold attempt. The journals
do not encode the exact physical touchdown time. USB enumeration occurs long
before these actions; neither journal shows a relevant disconnect/reset or
SELinux denial explaining the pair. Shared unrelated service warnings do not
explain the differential result.

## Historical diagnostics: what they really establish

The recovered journal gives stronger metadata than the coarse A/B logs:

| Historical path | Observed boundary | Interpretation |
|---|---|---|
| D297/01, boot `a18f012133…` | Repeated `FDT_IRQ100_1`, control 0x36, IRQ 0x0100, flags 0x003f, first_image=0 | Current zero-only baseline policy rejects this target-observed event. Does not identify the unlogged frame in every later cold case. |
| D297/02, boot `644bcaf1c8…` | FDT_82 response ordering; FIRST_IRQ2 with IRQ 0x0080; stage3 contact flags | Multiple distinct states were collapsed into the generic error. |
| D297/03, boot `ff8c5acc2e…` | First wait with eight ACKs; later FIRST_B0 rejection; stage3 delta failure | Historical dispatcher correction and calibration issues, not a single cold cause. |
| D298, boot `aa393076a5…` | Third baseline failure after bounded resampling; then no-image waits | More permissive classification/resampling did not resolve the target. |
| D299, boot `89f8f25b8fa2472aa8cbbec2f97ecf17` | At monotonic 62.081344 and 121.362727: first_irq2=0, cmd22=0, b0=0, decode=0, pipeline=0; cancel FIRST_IRQ2 | Two actions in **one boot**, not two independent cold starts. |
| D300, boot `50490d929aef46a2913c34bd50a100ea` | Both initial waits have precap POV=0, TLS=1, locked=0; no IRQ2/image | A separate boot corroborates the later missing-event boundary and falsifies the proposed cached-POV explanation for these actions. |

D299's first action accepted one baseline event with flags 63; the second did
not. Both completed the delta gate (threshold 29; third-stage maxima 4 and 1)
and stopped only at cancellation in FIRST_IRQ2. Later in the same boot,
monotonic 383.777129, IRQ2→22→B0→decode→pipeline all equal 1. D300 likewise
contains a later successful acquisition. This proves that the historical
instrumented path could still acquire; it does not reconstruct unrecorded
finger lift/replacement or prove what restored that ability.

**Correction to the historical synthesis:** delta-pass means stable samples,
not a proven empty-sensor baseline. `abs(base[i]-base[j]) <= threshold` also
passes when the same finger remains stationary across all samples. A zero
touch mask after updating a reference cannot independently certify absence
of contact. There are no absolute baseline/contact measurements in D299 that
close this gap.

Historical replay is not physical proof: D298's positive missing-IRQ replay
appends an IRQ2 to the observed waiting prefix. Such a suffix proves host
handling *if an IRQ arrives*, not that the target will generate it.

## Actual vertical contract

1. The greeter invokes PAM on Enter. The observed method reply and finger
   prompt occur roughly 16–18 ms after VerifyStart, before the failed action
   reaches its ~0.49 s terminal point.
2. Fedora fprintd `src/device.c:fprint_device_verify_start` schedules
   `fp_device_verify`/`fp_device_identify`, immediately completes the D-Bus
   method, then emits `VerifyFingerSelected`. There is no activation-ready
   await here. `pam/pam_fprintd.c:verify_finger_selected` sends the PAM text.
3. `fpi-image-device.c:fpi_image_device_activate_complete` sets active and
   transitions IDLE→AWAIT_FINGER_ON. It gates internal image-device state,
   not the D-Bus reply, PAM conversation, or physical finger movement.
4. Current `goodix_fpimage_device.c:context_maybe_start_production_secure_session`
   emits arm-complete after starting the asynchronous secure graph. D301 moved
   it to the FIRST_ARM ACK. Neither position prevents pre-existing contact.
5. Current post-TLS calibration is D4→AF/AE→36/IRQ100→50→36/IRQ100→82/delta→
   20/B0 baseline→36/IRQ100/delta→32/ACK→FIRST_IRQ2. Each sample learns a new
   FDT table. Baseline IRQ100 flags must be zero. Only a valid 32/IRQ2 with
   contact flags leads to 22 and a finger image. Setting framework readiness
   in FIRST_IRQ2 does not submit a new command or manufacture a contact.
6. `unexpected` records the rejected A0 metadata, then cancels the backend.
   `goodix_fpimage_device_close_completed_capture_epoch` can also complain
   about incomplete capture while draining. The latter log appearing first
   does not prove cancellation caused the original protocol rejection.

FIRST_ARM ACK proves command acceptance according to the implemented protocol.
No target evidence establishes the latency to effective analog detection or
whether contact is level-sensitive versus edge-sensitive. OEM host code
cannot prove a firmware receiver behavior that is absent from this corpus.

## Windows and implementation references

D255 raw identity is 27,684 bytes, 218 packets, SHA-256
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`.
Its preserved D256 timeline puts the three 36 commands at 20:56:44.146639,
.193051 and .310242 UTC, then first 32 at .346378; ACK follows in 0.957 ms.
The VM was already running, USB was attached, and passive bootstrap occurred
before Hello Setup. This is **not** a Windows pre-login capture.

The later UI entry has D5 at 20:57:20.458080, AF at .574716 and 32 at
20:57:27.322625 (AF→arm 6.747909 s). Reentry has D5 at 20:57:59.768352,
AF at .831667 and 32 at 20:58:04.344844 (4.513177 s). Neither reentry repeats
the three baseline samples. Operator markers bound UI actions, not firmware
readiness. These gaps are not a recommended sleep duration.

D258's OEM orchestrator and D259's classifier audit show sampling/learning
before final arm. The post-stage3 NAV/image classifier controls cache reuse or
replacement, not a different 32 payload. Reintroducing that classifier does
not by itself repair this timing contract. Rocky explicitly assumes an empty
sensor when first creating FDT/image baselines and reuses cached bases in
some paths. Neither proves that the current target may safely skip fresh
sampling, reuse a seed across sessions, or capture 22 without IRQ2. The current
runtime seed supplies the initial 36, not a proven substitute for the complete
fresh baseline/image path.

## Competing hypotheses and candidate selection

| Hypothesis | Status | Discriminator / implication |
|---|---|---|
| H1: contact predates arm; no new edge | SUPPORTED, not PROVEN | Missing IRQ2 fits. No physical lift/recontact trace within the same waiting action is recorded. |
| H2: ACK precedes effective FDT readiness | UNKNOWN | No local receiver semantics or measured arm-ready/contact timestamp; callback gating cannot establish it. |
| H3: framework cancellation causes fast rejection | Not supported as primary explanation | Explicit parser rejection precedes logical failure/cleanup in code; long waits terminate much later by PAM cancel. Ordering of error logs alone is misleading. |
| H4: legitimate contact frame rejected | PROVEN for target-observed D297/01 event and current policy; only SUPPORTED for exact new case | Relaxation already exposed the second, missing-IRQ failure. Parser-only patch is insufficient. |
| H5: unnecessary work before arm | PARTLY SUPPORTED | OEM separates bootstrap and UI reentry. Removing cold fresh calibration has no target equivalence or clean-baseline proof. |
| H6: UI advertises finger before driver ready | PROVEN in current fprintd/PAM contract | D301 alone cannot change it; even delaying the prompt cannot stop immediate physical contact after Enter. |
| H7: early contact becomes learned FDT/image baseline | SUPPORTED by learning code and no-finger reference contract, not directly measured on target | Stable deltas do not falsify it; it also explains missing IRQ2 without requiring edge-only firmware. |

Candidate comparison:

- **D301**: small and wire-preserving, but does not change the physical/UI
  cause; rejected as primary correction.
- **Accept flags/order/reverse IRQ**: evidence supports individual parser
  cases, but prior live attempts already reached the same unresolved wait;
  rejected as a resolution candidate.
- **Direct image on IRQ100, cached POV/D2, relaxed thresholds, retries,
  reset/reconnect**: lack the required target semantics or contradict observed
  evidence. Not selected.
- **Reuse seed/cache or capture before clean image calibration**: missing
  validity and contamination guarantees; not a proven safe optimization.
- **Initialize on Claim/open**: still occurs after Enter in this path and
  merely moves the race relative to the prompt.
- **Keep calibration/arming ready before Enter**: the most promising
  architectural direction suggested by D255, but requires a new lifetime and
  ownership model (boot, no-client wait, cancellation, suspend and handover),
  and a decision about contact during bootstrap. Starting fprintd alone does
  not run a fingerprint action. This is a material strategy/risk change,
  subject to AGENTS §6.4; not implemented by silently adding a boot service.

## One missing observation, not a new campaign

The narrow missing fact is: **during a D299/D300 action already waiting in
FIRST_IRQ2, did a complete physical lift and new contact occur without any
new VerifyStart/rearm, and did an IRQ2 follow?** Neither the existing journal
nor a later successful action answers this. On 2026-09-19 the User clarified
that, in the remembered tests, every failure closed the verification and
returned to password entry; another Enter and another contact started a new
verification. The finger was **not** lifted and replaced within the same
active verification. This operator evidence confirms that the discriminating
physical sequence was not tested; it does not supply its unknown outcome.

The smallest discriminating experiment would observe
one such waiting action, then one deliberate lift/recontact *inside that same
action*, retaining the same learned baseline and arm. An IRQ2/image after the
new contact supports the missing-transition model and demonstrates that the
existing baseline can detect that contact. No IRQ2 after the new contact
falsifies the simple “only the original edge was missed” account; it does not
alone prove baseline poisoning or distinguish it from ineffective arming.
The latter outcome changes the next work to calibration/arming semantics,
not another timing or logging variant.

This is an **experiment design, not an executable live instruction**. Current
production can terminate during baseline sampling, so it cannot be claimed
to reach this precondition. Reinstalling D299 blindly is not an acceptable
substitute. Reaching the precondition would require a separately reviewed,
minimal temporary change and its install/rollback, preserving bounded
contacts (at most three, stop on first match), no rearm/retry/reset, normal
timeout/cleanup and password fallback. No such build is declared ready here.
This explicit limitation prevents an unreviewed third equivalent run.

Before any proposed next live, the methodological answers are:

1. Change: control a new physical transition within the *same* initialized
   action; do not repeat cold immediate versus delayed actions.
2. Hypothesis: a fresh edge alone is sufficient with the existing baseline
   and arm, versus a baseline/arming condition a fresh edge cannot repair.
3. If still no IRQ2: stop timing experiments and review the device-side
   calibration/arming contract or seek the material earlier-init decision.

The eventual product PASS remains cold first login with natural immediate
contact, no deliberate delay; PRE-HELD must not poison later authentication.
The experiment above is not itself product PASS. No current change requires
rollback because no runtime was installed or modified.

### Material decision available to the User

The alternative to restoring a diagnostic waiting path is to authorize the
earlier-initialization direction, under this bounded scope:

- Keep the standard fprintd/libfprint stack and a single device owner.
- Prepare clean calibration before the greeter's Enter-triggered verification;
  retain the prepared session until authentication, with an explicit lifetime.
- Keep finger-image acquisition tied to the requested verification. Preparing
  calibration is not authorization for background biometric recognition.
- Define finite initialization, idle/cancel/suspend cleanup and handover before
  implementation; no autonomous retry, reset, persistent write or new secrets.
- Preserve password fallback and the existing enrollment/verification limits.
- Produce and review one offline implementation, build and symmetric deployment
  pair before asking for the normal immediate-contact cold-login validation.

This is a proposed change of ownership/lifetime strategy, not an assertion
that its implementation or PRE-HELD behavior is already closed. The User's
decision under AGENTS §6.4 is needed before adopting it. No governance change
or permission for the AI to perform installation/USB/live is requested.

## Offline changes and verification

Only two executable test files changed. The existing lifecycle runner now
uses the relocated, pinned Fedora libfprint headers instead of the obsolete
Rockytkg header path. Two characterization cases were added to the existing
suite, with no new harness:

- Target-observed 36/IRQ100/flags003f is rejected by current policy; synthetic
  channel values are explicitly labelled; no 22 or real USB submission occurs.
- A normal bootstrap stops at FIRST_IRQ2 without a fabricated IRQ. Toggling
  framework readiness does not capture or retry; explicit cancellation drains.

These tests pass **while the product bug still exists**. They prove bounded
host behavior and counterexamples to proposed reasoning, not a fix, firmware
behavior, or D301 integration. Existing positive traces remain checked.

Validation from repository root:

| Check | Result |
|---|---|
| `development/private-root/libfprint-driver/tests/run_goodix_d278_12_post_tls_test.sh` | 13/13 normal + 13/13 ASan/UBSan PASS; source/symbol audits PASS; real USB submits 0 |
| `production/check-source.sh` | PASS, 62 pinned source hashes; support manifest valid |
| `production/build.sh normal <fresh /tmp output>` | PASS; real production library linked/staged under /tmp; ABI check PASS; no RPATH, host-test-only symbols or private-tree production dependencies |

Local build output: `/tmp/goodix-login-review-build.HTvxL0/`; library SHA-256
`acf6d19af4e22a364390c61485259fa7fb3bcd10126a03ded53d4acd7e90593e`.
This is provenance for the verification, not a candidate approval or a
requirement that a later rebuild have identical bytes.

Build environment: installed Freedesktop SDK 25.08, commit
`b90ed309cc1d505dea48b6a2121c5dcfac22868120eee643b0596d31f96b9bb8`.
The five missing pinned OpenCV 4.13.0-1.fc44 RPMs were downloaded to ignored
`GoodixArtifacts/opencv-4.13-rpms/`, verified by the existing build and extracted
for compilation; no RPM installation occurred. Compiler warnings were in
OpenCV headers. No production source manifest change was necessary.

Read-only target compatibility inventory: Fedora 44 KDE x86_64;
fprintd/fprintd-pam 1.94.5-5.fc44, libfprint 1.94.100-1.fc44,
plasma-login-manager 6.7.5-1.fc44. The service was inactive. Its ExecStart is
`/usr/local/sbin/goodix-d293-native-fprintd`, using historical runtime directory
`d293-native-e61fce313794922a2dab156a1b38a8ddc5837f19`. Actual Plasma PAM is
`/usr/lib/pam.d/plasmalogin`, with `max-tries=3 timeout=45 debug` and password
fallback; `/etc/pam.d/plasmalogin` is absent. KDE fingerprint has the same
limits. The current source deployment and historical installed runtime must
not be conflated or silently migrated for a timing experiment. Package version
matching is not proof that the installed local library equals the new build.

## PM review and closure limits

Review checks the actual diff, evidence and code, separately from execution.
The physical timeline refutes D301 as a sufficient correction. Synthetic
success suffixes and passing stability deltas do not close the target bug.
Neither PRE-HELD recovery nor immediate first login is newly validated.
No production patch has survived causal review, so no LIVE_READY assertion,
installer, autonomous sensor action or publication is justified.

PM decision: accept the bounded offline evidence/test correction for
versioning; retain `HUMAN_REQUIRED` for the unresolved product task. Review
does not approve a production solution or a live run.

`OUTCOME=HUMAN_REQUIRED`; `ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED`;
`ROOT_CAUSE_STATUS=SUPPORTED_CONTACT_CALIBRATION_ARMING_COLLISION`;
`SELECTED_CORRECTION=NONE`;
`EXECUTABLE_CLOSURE=OFFLINE_TESTS_AND_PRODUCTION_BUILD_PASS_ONLY`;
`RESIDUAL_BLOCKER_OR_RISK=DEVICE_MECHANISM_UNRESOLVED`;
`CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md`;
`REVIEW_SET=BASELINE_GIT_DIFF_PLUS_THIS_TOPIC_EVIDENCE_AND_TESTS`.
