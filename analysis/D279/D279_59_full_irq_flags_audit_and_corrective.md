<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/59 — full IRQ flags audit and D279/57 corrective

## Outcome

The complete offline audit found one general modeling defect, rather than two
independent device anomalies: the low six IRQ flag bits are per-channel FDT
touch indicators, but D279/14 encoded selected observations as exact enum-like
constants. D279/58 changed one constant and therefore corrected only the first
visible symptom. The production model now validates the flags by protocol
context and consumes the touch bitfield when deriving the FDT-up table.

No live action, Goodix USB enumeration, protected-material access, `sudo`,
grant creation or approved-live preparation was performed in D279/59.

```text
OUTCOME=READY_OFFLINE_FULL_IRQ_POLICY_CORRECTIVE
ADVANCEMENT=AUTHENTIC_CORPUS_PLUS_CONTEXTUAL_FAIL_CLOSED_PRODUCTION_MODEL
D279_57_NEXT_LIVE_READINESS=READY
CURRENT_LIVE_AUTHORIZED=false
ALL_D279_57_PRIOR_GRANTS_CONSUMED=true
LIVE_OR_USB_ACTION_COUNT=0
REAL_USB_ENUMERATION_COUNT=0
```

`READY` means that no further equivalent magic-flags assumption is known that
can be eliminated from the current production enrollment path with the
available historical evidence. It is not a live authorization. A future run
still requires review and explicit approval of its new full SHA.

## Evidence and privacy boundary

The executable audit hash-gates and parses these authentic APP12509 captures:

| Evidence | SHA-256 | Role |
| --- | --- | --- |
| D255 zero-finger | `802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c` | bootstrap FDT |
| D274/03 multiframe | `5f11d06763d34531c72283a189a47d9bcd7c666a5fa3c043ec1371eddf107998` | bootstrap and repeated acquisition |
| D279/10 ATTEMPT01 | `557ff136e5a1d383f7413ca24d731eeae32d2b377e61003846b034ecda991743` | bootstrap |
| D279/10 ATTEMPT02 | `3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab` | complete 21-cycle enrollment |
| D279/54 identify | `6875b2d784d11cd4b3a8b68bd02af249f4b318883441a26068ef894767985c9b` | independent single-acquisition lifecycle |

The generated JSON contains all 65 D279/10 ATTEMPT02 IRQ rows with capture,
phase, cycle, PCAP frame, control, IRQ, flags and active-channel count. Raw IRQ
bytes are presence-classified but not exported. No raster, biometric payload,
TLS plaintext, template, key or secret enters either generated artifact.

Canonical executable evidence:

- `d279_59_full_irq_flags_audit.py` and its Python regression;
- `d279_59_verify_oem_touchflags.py`, which hash-gates the OEM DLL, canonical
  disassembly and Rockytkg source, reads the OEM 12-byte table-length value
  directly from the PE image and verifies the relevant instruction dataflow;
- `D279_59_full_irq_flags_audit.json`, complete metadata-only matrix;
- `D279_59_irq_flags_policy_corpus.tsv`, 65 authentic rows plus the sanitized
  Linux `0x002f` regression row;
- the independent C test `test_goodix_fdt_irq_policy.c`, which reads that
  corpus rather than copying parser constants.

## Complete D279/10 ATTEMPT02 matrix summary

| Context | Cycles | Control | IRQ | Flags | Count | Classification |
| --- | ---: | --- | --- | --- | ---: | --- |
| bootstrap FDT/manual | before cycle 1 | `0x36` | `0x0100` | `0x0000` | 3 | no-contact baseline sample |
| first finger-down | 1 | `0x32` | `0x0002` | `0x003f` | 1 | six active channels |
| first finger-up | 1 | `0x34` | `0x0200` | `0x0000` | 1 | no active channel |
| repeated finger-down | 2–20 | `0x32` | `0x0002` | `0x003f` | 19 | six active channels |
| repeated contact sample | 2–20 | `0x36` | `0x0100` | `0x003f` | 19 | six active channels |
| repeated finger-up | 2–20 | `0x34` | `0x0200` | `0x0000` | 19 | no active channel |
| terminal finger-down | 21 | `0x32` | `0x0002` | `0x003f` | 1 | six active channels |
| terminal contact sample | 21 | `0x36` | `0x0100` | `0x003f` | 1 | six active channels |
| terminal finger-up | 21 | `0x34` | `0x0200` | `0x0000` | 1 | no active channel |

Thus ATTEMPT02 itself has 21 IRQ2, 20 enrollment IRQ0100, 21 IRQ0200 and
three bootstrap IRQ0100 events. The identical IRQ number `0x0100` carries
zero during bootstrap and nonzero channel state during repeated enrollment;
control/IRQ alone does not define its flag contract.

Across all five hash-gated captures the distinct authentic counts are:

| Control / IRQ / flags | Count | Context |
| --- | ---: | --- |
| `0x32 / 0x0002 / 0x003f` | 24 | observed finger-down |
| `0x34 / 0x0200 / 0x0000` | 23 | observed finger-up |
| `0x36 / 0x0100 / 0x0000` | 15 | bootstrap baseline |
| `0x36 / 0x0100 / 0x003f` | 21 | enrollment contact sample |

D279/10 does not vary within its 21 enrollment cycles. The additional Linux
D279/57 observation `0x32 / 0x0002 / 0x002f` is nevertheless semantically
explained by the underlying per-channel model: channels 0,1,2,3 and 5 are set;
channel 4 is clear. It does not justify accepting arbitrary flags.

## Flag semantics: observed, verified, inferred, unknown

**OBSERVED:** `0x003f` occurs with all six low bits set during OEM contact;
`0x0000` occurs in OEM no-contact bootstrap/finger-up contexts; `0x002f`
occurred at the Linux inter-stage re-arm. No authentic row has a bit above
bit 5 set.

**VERIFIED:** the hash-gated OEM DLL is
`904eab1d...f4cbc7e2`; its canonical disassembly is
`d661afb7...fb7c743`. The IRQ2 call-site `0x180028815–0x180028839` passes
mode zero to handler `0x180029314–0x1800296d6`. The handler reads a u16
touchflag followed by the raw table, whose length at OEM VA `0x180576df4` is
12 bytes, hence six channels. At `0x180029533–0x180029544` its loop shifts by
channel index and tests bit `i` independently. The active candidate is formed
at `0x18002947e–0x1800294d9` from `(raw >> 1) + delta`; a clear bit overwrites
only channel `i` at `0x180029548–0x18002958e` with `delta - 2` (encoded
default `0x1380` for `0x15-2`). The independently preserved Rockytkg function
`gx_fdt_learn_up_base()` implements the same six-bit rule and fallback.
Rockytkg is semantic corroboration, not target USB transcript proof.

**INFERRED:** `0x002f` represents one inactive FDT channel at that physical
contact, not a new IRQ class. The original D279/57 attempt without structural
mismatch telemetry probably failed in the same broad stale-model family, but
its exact A0 class cannot be recovered from the available aggregate counts.

**UNKNOWN:** the available target corpus does not establish every physically
possible nonzero channel subset or whether contact subsets change with finger
placement. General low-six-bit acceptance is derived from the verified OEM
per-bit algorithm, not a claim that all 63 nonzero values were observed.
Requiring a nonzero contact and rejecting high bits are conservative contextual
guards grounded respectively in the observed contact/no-touch separation and
the six verified channels; they are not claims that the OEM helper itself
rejects those values.

## Root cause and historical impact

Git history places the strict inbound constants in D279/14 commit
`ca899ee0...`. The D279/10 analysis counted the protocol events but did not
perform a complete per-frame flag extraction. The new D279/14 synthetic frame
builders then repeated `0x003f`/`0x0000`, so parser and tests validated each
other instead of the capture. Later production-shaped TLS/FpImageDevice
fixtures copied the same assumptions.

D279/58 commit `4de9c342...` correctly established that enrollment IRQ0100
was `0x003f` in ATTEMPT02, but its explicit “no mask” policy still interpreted
the bitfield as one exact value. It was therefore a symptom corrective, not a
complete model correction.

The two structurally observed Linux failures have the same general root cause:

1. `d94c7af...` expected IRQ0100 flags zero and rejected authentic `0x003f`;
2. `4de9c342...` expected IRQ2 flags `0x003f` and rejected valid `0x002f`.

Without D279/59 the same defect could recur for any other nonzero subset at
IRQ2 or enrollment IRQ0100. Bootstrap zero and finger-up zero were already
correct and remain exact.

## Canonical production model

`goodix_fdt_irq_policy.[ch]` is the sole production authority:

| Context | Accepted flags | Table rule |
| --- | --- | --- |
| bootstrap baseline sample | exact `0x0000` | six `(raw >> 1)` values |
| finger-down IRQ2 | nonzero subset of `0x003f` | active: `(raw >> 1)+delta`; inactive: `delta-2` |
| enrollment contact IRQ0100 | nonzero subset of `0x003f` | event validation; current state consumes no raw table here |
| finger-up IRQ0200 | exact `0x0000` | six `(raw >> 1)` values |

Wrong control, wrong IRQ, wrong A0 length, zero touch during contact and any
reserved high bit fail closed. The 12 raw bytes remain mandatory and bounded;
the IRQ2 touch mask is passed through the inbound binding and lifecycle adapter
to FDT state instead of being discarded. The enrollment IRQ0100 mask is
validated at its inbound event boundary but is not a table source for the
current state machine.

Range validation follows the pre-corrective production contracts rather than
borrowing the bootstrap-only component filter: an active FDT-up candidate must
fit in one byte, an inactive channel uses the OEM fallback without constraining
its ignored raw candidate, and finger-up accepts the complete byte range.
Bootstrap alone retains its historical rejection of `0x00`/`0xff` components.

The corrective is wired into both the iterative enrollment graph and the
legacy production post-TLS lifecycle still used by bootstrap/identify. The
Fedora 44 Meson overlay and every relevant focused/production-shaped build
runner compile the policy module. No Rockytkg USB transcript was imported.

## Repository-wide occurrence census

The audit searched control values `0x32/0x34/0x36`, IRQs
`0x0002/0x0100/0x0200`, flags `0x003f/0x002f/0x0000`, `parse_irq`, A0 IRQ
builders and the D279/14, D279/24 and D279/57 fixtures. Occurrences were
classified, not globally replaced:

| Class | Main locations | Disposition |
| --- | --- | --- |
| production-current | `goodix_enrollment_post_tls_events.c`, enrollment adapter/state, `goodix_post_tls_lifecycle.c` | centralized contextual policy and bit-aware derivation |
| production-other-path | secure-session/FpImageDevice bindings and Fedora Meson overlay | fixtures/build closure updated where they exercise current production; exact bootstrap zero retained |
| authentic-evidence parser | D274 postprocessor, D279/59 generator, capture-derived JSON/TSV | unchanged parser; new SHA-gated corpus authority |
| regression fixture | D279/12–14, D278/12, secure-session, FpImageDevice | signatures/builds updated; repeated-cycle `0x002f` and invalid masks tested |
| synthetic-only | earlier model/build helpers | retained when not on production path and not making current target claims |
| historical/deprecated | `core/fdt_lifecycle.py`, frozen older operator kits/reports | left reproducible; explicitly not current production authority |
| documentation | D279/14, D279/57, D279/58, READMEs, provenance, manual | superseded exact-value claims corrected while preserving history |

There is no remaining exact `0x003f` gate in the current enrollment parser or
FDT derivation. Constants in authentic matrices, explicit positive fixtures
and the `GOODIX_FDT_TOUCH_MASK` definition are intentional. Exact zero remains
intentional only for proven no-touch contexts.

## D279/57 end-to-end review

| Transition | Evidence classification | Review result |
| --- | --- | --- |
| bootstrap D4/AF and three `0x36/IRQ0100/zero` samples | directly OEM observed; Linux path previously live-validated | exact-zero baseline policy preserved |
| enrollment entry, first `0x32/IRQ2`, `0x22`, primary B0 | directly OEM observed | nonzero six-bit flags and raw source accepted |
| first final `0x34/IRQ0200`, `0x20`, post-up B0, `0x50/NAV` | directly OEM observed | exact finger-up zero and special first-cycle tail preserved |
| repeated `0x32/IRQ2` | OEM observed plus Linux `0x002f` | context mask feeds inactive-channel fallback |
| repeated primary B0, `0x34`, `0x36/IRQ0100`, `0x20`, auxiliary B0, final `0x34/IRQ0200` | directly OEM observed in cycles 2–20 | current state order matches full ATTEMPT02 |
| sample delivery after release-ready, not primary B0 | derived from OEM ordering; Linux-specific libfprint mapping independently tested | contact/progress separation preserved |
| stage 8 completion hold until terminal IRQ0200 | Linux-specific and independently tested | both SIGFM/IRQ orderings and fatal copy failure covered |
| no ninth `0x32` after stage 8 | production candidate, host-tested against configured stage cap | target sensor-side terminal behavior remains live-unproven |
| close/drain/cleanup | Linux-specific, independently tested and observed on consumed failures | fail-closed invariants retained |

The remaining live question is the already declared stage-8 early terminal,
not another offline-resolvable flag constant. Reusability/template persistence
and dynamic duplicate convergence remain separate non-goals.

## Offline executable closure

The closure set comprises:

- D279/59 hash-gated Python evidence tests and independent C corpus tests;
- D279/12 FDT state, D279/13 lifecycle adapter and D279/14 inbound events,
  normal and ASan/UBSan;
- D278/12 legacy post-TLS lifecycle and secure-session production graph,
  normal and ASan/UBSan;
- full production-shaped `FpImageDevice` graph, normal and ASan/UBSan;
- the exact D279/57 `--offline-preflight`, compiling the production snapshot
  and rejecting the unapproved live baseline before `FpContext`/USB.

The operator preflight source guard also rejects a return to literal
exact-value parser gates or a build that omits the centralized policy module.
The focused C suite exhaustively exercises all 63 nonzero low-six-bit subsets,
including active/fallback output per channel, while separately proving exact
zero for baseline/finger-up and rejection of every tested reserved-bit form.

Final offline results:

| Closure surface | Normal | ASan/UBSan | Result |
| --- | ---: | ---: | --- |
| hash-gated Python audit/verifier regression | 2/2 | n/a | PASS |
| independent D279/59 C policy/corpus suite | 3/3 | 3/3 | PASS |
| D279/12 FDT state | 4/4 | 4/4 | PASS |
| D279/13 lifecycle adapter | 3/3 | 3/3 | PASS |
| D279/14 inbound enrollment events | 12/12 | 12/12 | PASS |
| D278/12 legacy post-TLS lifecycle | 11/11 | 11/11 | PASS |
| D278 secure-session production graph | 25/25 | 25/25 | PASS |
| full production-shaped `FpImageDevice` graph | 31/31 | 31/31 | PASS |
| exact D279/57 operator `--offline-preflight` | one complete invocation | n/a | PASS_OFFLINE |

Two closure findings were corrected before the final runs above. First, the
new exhaustive test needed an explicit integer cast to satisfy the existing
`-Wconversion` sanitizer build; this did not change production behavior.
Second, the `FpImageDevice` census exposed an accidental fixture edit that had
assigned contact flags to a bootstrap IRQ0100. That bootstrap row was restored
to authentic exact zero while the enrollment IRQ0100 row remains nonzero.
The subsequent AI-PM review also caught a bootstrap-only raw-component filter
that had been generalized to up/down derivation: the implementation now
preserves the original range contracts and applies the inactive-channel
fallback before considering its ignored raw candidate. All final runs then
passed, and both production-shaped paths reported zero real USB submissions.

```text
EXECUTABLE_CLOSURE=PASS_OFFLINE
AUTHENTIC_D27910_IRQ_ROWS=65
CORPUS_ROWS_INCLUDING_LINUX_REGRESSION=66
CONTROL_IRQ_MISMATCH=FAIL_CLOSED
ZERO_CONTACT_FLAGS=FAIL_CLOSED
RESERVED_FLAG_BITS=FAIL_CLOSED
FIRST_REPEATED_TERMINAL_PROFILES=PASS
POST_STAGE8_REARM_COUNT=0
PROTECTED_PAYLOAD_EXPORTED=false
RESIDUAL_BLOCKER_OR_RISK=APP12509_STAGE8_NO_REARM_TERMINAL_UNPROVEN_LIVE;POST_CLOSE_REUSABILITY_SEPARATE
NEXT_PRIMARY_BOUNDARY=HUMAN_GATE_NEW_FULL_SHA_ONE_D279_57_ACTION_NO_RETRY
```

## Post-corrective live validation and D279 closure

The remaining live question was subsequently exercised once on approved full
SHA `38962cc00b7707dc1bf56bc38cd4457d7d11b5e1`. The hash-pinned sanitized
evidence is preserved in
`captures/D279_57/D27957_20260910T055810Z_38962cc/sanitized/` and independently
validated by `analysis/D279/d279_57_stage8_success_audit.py`.

All eight stages completed with eight primary and eight auxiliary B0 records,
seven inter-stage re-arms, eight `0x32` commands, one terminal transition and
zero rejected inbound events. Thus the contextual six-channel flag policy and
bit-aware FDT derivation survived the complete target-real enrollment path,
including the stage-8 terminal with no ninth re-arm. The run used no retry,
reopen, reset or clear-halt and completed host-side drain, release, runtime
cleanup and TLS secret zeroization.

This addendum promotes the D279/59 corrective from offline-ready to live-
validated for this APP12509 enrollment path. It does not prove template
reusability/persistence, identify/fprintd integration, SIGFM matching threshold
or absence of sensor-side persistence. The successful grant and all preceding
D279/57 grants are consumed; no new live action is authorized.

```text
D279_59_POST_LIVE_OUTCOME=PASS_TARGET_VALIDATED
D279_59_POST_LIVE_BASELINE=38962cc00b7707dc1bf56bc38cd4457d7d11b5e1
D279_59_CONTEXTUAL_IRQ_POLICY_TARGET_VALIDATED=true
D279_59_STAGE8_NO_REARM_TARGET_VALIDATED=true
D279_59_POST_LIVE_REJECTED_INBOUND_COUNT=0
D279_59_POST_LIVE_AUTHORIZATION_CONSUMED=true
D279_CLOSED=true
CURRENT_LIVE_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=OFFLINE_D280_01_POST_CLOSE_SERIALIZED_TEMPLATE_REUSE_AND_PRODUCTION_IDENTIFY_OPERATOR_BOUNDARY
```
