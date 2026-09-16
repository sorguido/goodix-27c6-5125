# D258 — exact FDT host semantic-gate closure

## Decision

```text
OUTCOME=BLOCKED_POST_STAGE2_HOST_CLASSIFIERS
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_0x82_PROTOCOL_BOUNDARY_CLOSED
EXECUTABLE_CLOSURE=PARTIAL_FAIL_CLOSED
RESIDUAL_BLOCKER_OR_RISK=POST_STAGE2_NAV_CLASSIFIER_RUNTIME_STATE/ABI; D255_BASELINE_B0_PLAINTEXT_AND_IMAGE_CLASSIFIER_RUNTIME_STATE
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
BUNDLE=analysis/D258/D258_host_semantic_gate_closure_bundle.zip
```

D258 found the exact target orchestration in the local OEM `gfusb.dll`, at
`gf_update_all_base 0x180068adc..0x18006987d`. This is new target-specific
evidence and supersedes the narrower D257 statement that all three host gates
were unavailable from the local corpus.

The `0x82` decision is now closed and implemented. The function reads two
bytes, ignores byte zero on this path, zero-extends byte one, and checks each
unsigned raw FDT-base word:

```text
forall i: abs(uint16(base0[i]) - uint16(base1[i])) <= uint8(response[1])
```

The D255 raw bases differ by at most one and the observed threshold is 29, so
the native predicate passes without treating the literal response as a magic
“good” value.

## NAV and baseline correction

`0x50` is an acquisition/store step before stage1, not an immediate semantic
admission gate. `0x20` likewise acquires the baseline before stage2. Only after
stage2 does `gf_update_all_base` call the same large classifier through mode-1
NAV and mode-0 image wrappers. The enum result selects keeping or updating the
corresponding cached base; it does not admit the already-completed third
sample. The GPL candidate now preserves both dynamic inputs, performs the
native `0x82` check in the right place, completes stage2, and then fails closed
at the unresolved post-sample classifier boundary.

The common classifier at `0x180022654` was located, but an exact executable
model cannot be validated from this corpus: its target runtime configuration
and state are not captured as an exact ABI instance. For `0x20`, the D255 B0
application body is also unavailable because the approved factory PSK is held
outside the user-readable repository boundary. No privilege request was made
and no secret was read or copied.

```text
GATE_0x50_STATUS=PARTIAL_STORE_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
GATE_0x50_OWNER=gfusb.dll:0x180067874;0x180069377;0x180023fdc;0x180022654
GATE_0x50_PREDICATE=NONE_BEFORE_STAGE1; POST_STAGE2_CLASSIFIER_UNREPRODUCED
GATE_0x50_DYNAMIC_STATE_ROLE=PRESERVED_NAV_INPUT_TO_POST_STAGE2_KEEP_OR_UPDATE_BASE_DECISION

GATE_0x82_STATUS=CLOSED_NATIVE_PREDICATE_IMPLEMENTED
GATE_0x82_OWNER=gfusb.dll:gf_update_all_base:0x180068e26..0x180068ffe
GATE_0x82_PREDICATE=forall i: abs(uint16(base0[i])-uint16(base1[i])) <= uint8(response[1])
GATE_0x82_RESPONSE_ROLE=BYTE0_IGNORED_BYTE1_UNSIGNED_THRESHOLD

GATE_0x20_STATUS=PARTIAL_ACQUISITION_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
GATE_0x20_OWNER=gfusb.dll:0x180067914;0x180069531;0x180023fa8;0x180022654
GATE_0x20_PREDICATE=POST_STAGE2_CLASSIFIER_UNREPRODUCED
D255_B0_DECRYPTION_STATUS=INPUT_UNAVAILABLE_WITHOUT_PRIVILEGE
```

## Timeout and replay closure

The accidental D257 single timeout was replaced by the static-callsite and
D255-latency bounded policy documented separately.

```text
COMMAND_TIMEOUT_POLICY=PER_COMMAND_EVIDENCE_BOUNDED
TIMEOUT_0x36_MS=500
TIMEOUT_0x50_MS=500
TIMEOUT_0x82_MS=500
TIMEOUT_0x20_MS=2000
TIMEOUT_0x32_MS=100

CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x50_GATE=true
CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x82_GATE=true
CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x20_GATE=true

PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL
EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY=BLOCKED
DYNAMIC_HOST_GATES_CLOSED=false
FDT_OFFLINE_CANDIDATE_CLOSED=false
HOST_BUS_LIFECYCLE_READY=true
```

For `0x82`, corpus exhaustion means closure: no information is missing. For
`0x50`, the missing datum is the exact target runtime classifier
configuration/state and a validated ABI/model. For `0x20`, the missing data
are the decrypted D255 B0 application body and that same exact runtime
classifier configuration/state. Repeating another static string/callsite
audit without one of those inputs would not test a new hypothesis.

```text
SEED_FRESHNESS_FACTORY_PRESERVATION_BLOCKER=false
SEED_FRESHNESS_FUNCTIONAL_SUCCESS_RISK=GENERAL_TTL_UNPROVEN_BOUNDED_RISK
NO_SPECIAL_FDT_RECOVERY_COMMAND_POLICY=DEFAULT
A2_REENTRY_INJECTION=0
0x70_REENTRY_INJECTION=0
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false

REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
REAL_COMMAND_SEND_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
```

