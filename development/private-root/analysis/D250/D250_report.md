<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D250 — Rocky canonicalization and exactly-one AF offline closure

## Outcome

D250 is `READY_OFFLINE`. It verifies the already canonical Rocky snapshot and
closes the candidate path, without hardware, at:

```text
TLS completed -> D4 once -> ACK d4/01 -> AF attempt once
-> one direct validated AE -> STOP_AFTER_AF
```

The engineering decision is:

```text
D250_AF_LIVE_BOUNDARY=READY_FOR_SEPARATE_USER_AUTHORIZATION
```

This decision is not live authorization. The delivered D250 launcher accepts
only `--offline-dry-run`; every other invocation stops at a pre-USB fence.

## Repository baseline and Rocky snapshot

- Git root: `/home/guido/Repository/goodix-27c6-5125_private`.
- Initial branch: `main`; upstream: `origin/main`.
- Initial HEAD and upstream: `e40761b344bc44e492111aab8ff39769e99e6006`.
- This locally verified baseline supersedes the prompt's earlier observed
  `0b03b3af6ff9ad2d40ad606bf190ff033c4a34f0`; no history operation was made.
- Initial worktree: clean.
- Rocky is directly materialized at `<git-root>/Rockytkg/`; there is no second
  nesting, nested `.git`, or mode-160000 entry.
- `Rockytkg/libfprint/` consists of normal tracked files.
- `Rockytkg/.gitmodules` is retained only as a historical snapshot file.
- The pre-existing `Rockytkg/PROVENANCE.md` was verified complete and left
  unchanged (SHA-256
  `5381bc4f74d91db7947bc111e122cfa3b77bb2af5dfcab11422fafc7289fe91b`).

The provenance preserves Rocky upstream commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`, tree
`6dda93a960ceddb085c59b5382df47ecc5d56a39`, and original libfprint gitlink
`7ebe0c809b4d1df3400e84299a4ec4acdea84590`. It distinguishes Rocky GPL,
`src/goodixgf.c` LGPL, upstream third-party libfprint material, and vendor
firmware outside the blanket licenses. Import remains file-specific and ledgered;
the public project does not automatically receive this snapshot or vendor data.

The canonical project guidelines were verified as version 2.4, revision
21 August 2026, and were not rewritten. `AGENTS.md` now contains only the
minimal derived Rocky routing rule. The online Rocky repository is provenance,
not an ordinary workflow dependency; Issue #1 remains a distinct external
corroborating source.

## Evidence order and AF audit

The audit used primary local evidence first: the canonical target capture and
local DLL analysis, then the technical manual, D249/core, and the verified Rocky
snapshot. Rocky was not promoted to target-specific proof.

The capture is
`analysis/D230/work/GoodixExport/rilevamento.pcapng`, SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
The reproducible, redacted audit is `D250_af_capture_audit.json`, SHA-256
`ab5d9c9e164113294f04d51e5b06a5782f5af83f94a3652e3b183c339eab9f0c`.

| Property | Bounded conclusion | Evidence class |
| --- | --- | --- |
| Logical request | A0 payload control `AF`; data `55 || timestamp16le || 00 00`; logical frame 13 bytes | local DLL + capture, target-specific |
| USB framing | bulk OUT `0x01`, bulk IN `0x81`; OEM AF submission 64 bytes | target capture |
| OUT completion | success completion paired with the 64-byte submission; completion event has no duplicate payload | target capture |
| AF response | direct AE, no AF ACK and no intervening nonempty IN; one logical/physical 24-byte frame with 16-byte state body | all five local occurrences |
| Timing | D4 ACK→AF OUT 58.365 ms; AF OUT→completion 14.521 ms; completion→AE 0.088 ms | exact post-D4 target sequence |
| Candidate budget | 20 ms host pacing, 500 ms total AF exchange timeout, maximum one IN frame | DLL Sleep/builder plus bounded policy |
| State | version 1; observed flags `0x02`: POV false, TLS connected true, locked false; unknown bits are preserved and exposed | target capture + strict parser |
| Trailing data | coalesced trailing bytes abort; a separately queued frame remains unowned because execution stops; no consumer or next command exists | implemented and tested offline |
| Side effects | the exact fixed AF/GetMcuState family is a corpus-bounded state query with no address, data blob, persistent selector, or write family | target DLL/capture + local core; Rocky corroborates only |

The five OEM AF submissions contain 51 bytes beyond the declared A0 length.
Their tails are identical and contain six opaque nonzero bytes at tail offsets
27–32. D250 deliberately does not replay opaque host staging: the candidate
submits the valid 13-byte AF frame in a deterministic 64-byte zero-filled
buffer. The target-specific equivalence of that AF zero tail is not live proven.
Safety is bounded by the declared A0 frame length and the already successful
D4 zero-tail precedent, but this remains the principal experiment risk.

The device-side receiver implementation and a universal proof about arbitrary
AF bodies remain unknown. The READY decision applies only to the fixed serializer
above, its one-shot response contract, and immediate stop.

## Candidate and fail-closed boundary

`core/post_d4.py` supplies the canonical serializer/parser and a one-shot
state machine. `D250_af_continuation.patch` is the minimal continuation over the
sealed historical runtime after D245 and D246 patches. It:

- requires a completed single D4 and exact `d4/01` ACK;
- latches `af_attempt_count=1` before the physical submission;
- allows at most one AF send and one IN frame;
- accepts only one checksum-valid AE with exactly 16 state bytes;
- rejects timeout, ambiguous completion, AF ACK, wrong control, wrong length,
  bad checksum, duplicate/coalesced data, identity change, and re-entry;
- preserves unknown state bits in telemetry;
- performs no retry, reset, reopen, or recovery command;
- makes `STOP_AFTER_AF` terminal, leaving FDT `32`, SetMode `20`, D2, finger,
  image, provisioning, IAP, and persistent write families unreachable.

The repository's real USB backend and entrypoint remain source-sealed. The
offline closure copies them to a temporary tree, applies D245→D246→D250,
executes the synthetic matrix, reverses all patches, and verifies exact source
hash restoration.

## Verification

All verification was offline and required no `sudo`:

- full suite: `python3 -m unittest discover -s tests -v` — 154/154 PASS;
- D250 tests: `python3 -m unittest -v tests.test_d250_af_boundary` — 6/6 PASS;
- D249 regression — 13/13 PASS;
- D246 regression — 4/4 PASS;
- D245 regression — 7/7 PASS;
- real operator invocation `operator_kit/d250-live-af-once.sh --offline-dry-run`
  from repository and external cwd — PASS;
- shell syntax and `git diff --check` — PASS.

The synthetic matrix covers predecessor TLS stop, happy D4→AF→AE, AF timeout,
ambiguous completion and re-entry denial, unexpected AF ACK, short/long/wrong
control/bad-checksum AE, duplicate/coalesced and separate trailing data, second
AF denial, and the post-AF FDT/32/20/D2 fence. Cleanup/reseal remain intact.

Real D250 counters are:

```text
USB_OPEN_COUNT=0
AF_ATTEMPT_COUNT=0
AF_SEND_COUNT=0
RETRY_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
```

## Review set and residual risk

The step-local bundle contains only this report, compact status, capture audit
metadata/script, continuation patch, runtime matrix, offline closure, launcher,
tests, and the canonical changes patch. It excludes Rocky, firmware, raw
capture, DLL, secrets, TLS material, and biometric data. Its SHA-256 is recorded
in the external sidecar `D250_bundle.zip.sha256` because an archive cannot
contain its own stable digest.

Residual risk: AF zero-tail device equivalence is not live proven; the receiver
implementation is unavailable; no commit SHA has been reviewed or approved as
a live baseline. A future run therefore still requires AI-PM review and explicit
user authorization. D250 performed no hardware access and does not authorize it.

## Closure fields

```text
OUTCOME=READY_OFFLINE
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_NEW_OFFLINE_PROTOCOL_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=AF_ZERO_TAIL_DEVICE_EQUIVALENCE_NOT_LIVE_PROVEN;RECEIVER_IMPLEMENTATION_UNKNOWN;LIVE_BASELINE_NOT_APPROVED
CANONICAL_DOCUMENTATION=UPDATED_MANUAL_AGENTS_ANALYSIS_INDEX
BUNDLE=analysis/D250/D250_bundle.zip;SHA256_IN_EXTERNAL_SIDECAR
GIT_ROOT=/home/guido/Repository/goodix-27c6-5125_private
INITIAL_HEAD=e40761b344bc44e492111aab8ff39769e99e6006
FINAL_WORKTREE_STATUS=MODIFIED:AGENTS.md,MANUAL,analysis/README.md,core/post_d4.py;UNTRACKED:analysis/D250/,operator_kit/d250-live-af-once.sh,tests/test_d250_af_boundary.py
ROCKY_SNAPSHOT_STATUS=VERIFIED_CANONICAL_LOCAL_MATERIALIZED_NO_NESTED_GIT_OR_GITLINK
ROCKY_PROVENANCE_STATUS=VERIFIED_PREEXISTING_CANONICAL_NO_CHANGE
GUIDELINES_VERSION_STATUS=VERIFIED_V2.4_2026-08-21_UNCHANGED
AF_AUDIT_RESULT=PASS_BOUNDED_QUERY_ONLY_DIRECT_AE_STOP_BEFORE_FDT
D250_AF_LIVE_BOUNDARY=READY_FOR_SEPARATE_USER_AUTHORIZATION
USB_OPEN_COUNT=0
AF_ATTEMPT_COUNT=0
AF_SEND_COUNT=0
RETRY_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
```
