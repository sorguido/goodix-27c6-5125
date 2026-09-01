# D278/14 — three consumed live attempts and five host-only correctives

## Outcome

```text
OUTCOME=PASS_HOST_ONLY_CORRECTIVE
ADVANCEMENT=BOUNDED_PRE_ACK_PINNED_TYPED_A2_RESIDUE_HANDLING_PROVEN_HOST_ONLY
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
CANONICAL_DOCUMENTATION=UPDATED
```

This document records **three consumed D278/14 live attempts** and the host-only
correctives that followed. No new live execution is performed or authorized.

```text
START_BRANCH=main
START_HEAD=87c1bf89d0ba28497313f4bb75a8de4bbdb37b75
FINAL_STATE=COMMITTED_AND_PUSHED_TO_MAIN
```

## Live attempt #1

The first authorized D278/14 live was attempted on baseline
`2172e750ae7c100a3a891ba25d0797286230a4ab`.

```text
D278_14_ATTEMPT_1_BASELINE=2172e750ae7c100a3a891ba25d0797286230a4ab
D278_14_ATTEMPT_1_OUTCOME=FAIL_HOST_BINDING_BEFORE_PROTOCOL
D278_14_ATTEMPT_1_FIRST_FAILURE_BOUNDARY=FPDEVICE_USB_BINDING_CONSTRUCTION
D278_14_ATTEMPT_1_PROCESS_EXIT_CODE=134
D278_14_ATTEMPT_1_PROCESS_TERMINATION=SIGABRT
D278_14_ATTEMPT_1_A2_REACHED=false
D278_14_ATTEMPT_1_TLS_REACHED=false
D278_14_ATTEMPT_1_POST_TLS_REACHED=false
D278_14_ATTEMPT_1_CORE_DUMP_CREATED=OBSERVED
D278_14_ATTEMPT_1_AUTHORIZATION_CONSUMED=true
```

After target selection and open/claim, `goodix_fpimage_device_new_for_usb()`
aborted in repository-local `fp_device_set_property()`:

```text
Rockytkg/libfprint/libfprint/fp-device.c:336:
fp_device_set_property:
assertion failed: (g_value_get_object (value) == NULL)
```

The failure is host-side construction, not a Goodix protocol response. The
abort occurred before `begin_operator_epoch`, A2, A8, TLS or post-TLS. The
core dump was not read, copied, uploaded, analyzed or added to Git.

## Live attempt #2

A second, separate explicit one-shot authorization was granted for baseline
`fceae05d9ff3ed14348f9031706e70d5a808ff91`.

```text
D278_14_ATTEMPT_2_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_ATTEMPT_2_BINARY_SHA256=de935e0a3fc89a345a2bad624ba3d218f51ab036597d13566d985efbada4f270
D278_14_ATTEMPT_2_OUTCOME=FAIL_RECEIVE_REARM_HOST_PLUMBING
D278_14_ATTEMPT_2_FAILURE_CLASS=ONE_SHOT_DEADLINE
D278_14_ATTEMPT_2_PHASE_TRACE=REENTRY_RECOVERY_A2>TERMINAL
D278_14_ATTEMPT_2_SECURE_COMMAND_COUNT=1
D278_14_ATTEMPT_2_ACK_COUNT=1
D278_14_ATTEMPT_2_TYPED_COUNT=0
D278_14_ATTEMPT_2_PHYSICAL_IN_SUBMIT_COUNT=1
D278_14_ATTEMPT_2_PHYSICAL_OUT_SUBMIT_COUNT=1
D278_14_ATTEMPT_2_REENTRY_A2_RESULT=FAIL_CLOSED
D278_14_ATTEMPT_2_A8_REACHED=false
D278_14_ATTEMPT_2_TLS_REACHED=false
D278_14_ATTEMPT_2_POST_TLS_REACHED=false
D278_14_ATTEMPT_2_FIRST_ACQUISITION_REACHED=false
D278_14_ATTEMPT_2_SECOND_ACQUISITION_REACHED=false
D278_14_ATTEMPT_2_USB_OPEN_COUNT=1
D278_14_ATTEMPT_2_USB_CLAIM_COUNT=1
D278_14_ATTEMPT_2_USB_RELEASE_COUNT=1
D278_14_ATTEMPT_2_USB_CLOSE_COUNT=1
D278_14_ATTEMPT_2_BACKEND_DRAINED=true
D278_14_ATTEMPT_2_CLEANUP_COMPLETE=true
D278_14_ATTEMPT_2_PROJECT_SECRET_ZEROIZED=true
D278_14_ATTEMPT_2_CORE_DUMP_LIMIT=0
D278_14_ATTEMPT_2_RETRY_COUNT=0
D278_14_ATTEMPT_2_REOPEN_COUNT=0
D278_14_ATTEMPT_2_DEVICE_RESET_COUNT=0
D278_14_ATTEMPT_2_CLEAR_HALT_COUNT=0
D278_14_ATTEMPT_2_PERSISTENT_DEVICE_WRITE_COUNT=0
```

Root cause:

```text
D278_14_ATTEMPT_2_ROOT_CAUSE=REAL_USB_BACKEND_COMPLETION_BYPASSES_CONTEXT_RECEIVE_REARM_FOLLOWUP
```

The A2 command was submitted and its ACK was received, but the typed A2
response was **not observable because no second physical IN was submitted**.
The receive re-arm logic lived in `goodix_device_context_complete_receive()`,
which the production real-USB path does not call. The operator did not place a
finger; finger interaction was irrelevant because the run never reached A8,
TLS, post-TLS or acquisition.

```text
D278_14_TOTAL_LIVE_ATTEMPTS=3
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=3
```

## Live attempt #3

The third authorization was consumed on baseline
`87c1bf89d0ba28497313f4bb75a8de4bbdb37b75`. Its first receive completed with
an A0/A2 typed-shaped three-byte body before any ACK. The run did not log that
body's hash, so a match against the pinned A2 response is unknown and must not
be claimed.

```text
D278_14_ATTEMPT_3_BASELINE=87c1bf89d0ba28497313f4bb75a8de4bbdb37b75
D278_14_ATTEMPT_3_BINARY_SHA256=346aadf64c49b6757c236a097264465ef4de130798aa82109056604930162d90
D278_14_ATTEMPT_3_OUTCOME=FAIL_PRE_ACK_TYPED_A2
D278_14_ATTEMPT_3_FAILURE_CLASS=INTEGRATED_PATH_TERMINAL
D278_14_ATTEMPT_3_PHASE_TRACE=REENTRY_RECOVERY_A2>TERMINAL
D278_14_ATTEMPT_3_SECURE_COMMAND_COUNT=1
D278_14_ATTEMPT_3_ACK_COUNT=0
D278_14_ATTEMPT_3_TYPED_COUNT=0
D278_14_ATTEMPT_3_PHYSICAL_IN_SUBMIT_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_OUT_SUBMIT_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_IN_COMPLETION_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_OUT_COMPLETION_COUNT=1
D278_14_ATTEMPT_3_PROTOCOL_FAILURE_KIND=TYPED_SHAPE_MISMATCH
D278_14_ATTEMPT_3_OBSERVED_OUTER_TYPE=0xA0
D278_14_ATTEMPT_3_OBSERVED_A0_CONTROL=0xA2
D278_14_ATTEMPT_3_OBSERVED_BODY_LENGTH=3
D278_14_ATTEMPT_3_OBSERVED_ACK_ECHO=UNAVAILABLE
D278_14_ATTEMPT_3_OBSERVED_ACK_STATUS=UNAVAILABLE
D278_14_ATTEMPT_3_A8_REACHED=false
D278_14_ATTEMPT_3_TLS_REACHED=false
D278_14_ATTEMPT_3_POST_TLS_REACHED=false
D278_14_ATTEMPT_3_STOP_TIME_MS=145
D278_14_ATTEMPT_3_BACKEND_DRAINED=true
D278_14_ATTEMPT_3_CLEANUP_COMPLETE=true
D278_14_ATTEMPT_3_PROJECT_SECRET_ZEROIZED=true
D278_14_ATTEMPT_3_RETRY_COUNT=0
D278_14_ATTEMPT_3_REOPEN_COUNT=0
D278_14_ATTEMPT_3_DEVICE_RESET_COUNT=0
D278_14_ATTEMPT_3_CLEAR_HALT_COUNT=0
D278_14_ATTEMPT_3_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_14_ATTEMPT_3_CORE_DUMP_LIMIT=0
PRE_ACK_TYPED_A2_OBSERVED=true
PRE_ACK_TYPED_A2_PIN_MATCH=UNKNOWN
STALE_TYPED_FROM_ATTEMPT_2=STRONG_HYPOTHESIS_NOT_PROVEN
```

The bounded hypothesis is that attempt #2 received the A2 ACK but terminated
before submitting the next IN, leaving the expected typed A2 unread; attempt
#3 then received a typed-shaped A2 first. The router preserves byte order and
can parse multiple frames from one completion, excluding software reordering.
This remains a strong hypothesis, not proof of provenance or pin equality.

## Corrective #1 — FpDevice USB binding

The first host-only corrective kept the base shell `VIRTUAL` and added a
thin transport-typing `USB` subclass used only by
`goodix_fpimage_device_new_for_usb()`. The subclass inherits the same
`GoodixDeviceContext`, backend, router, secure-session, TLS, lifecycle and
decoder. Construction and binding validation now happen after target selection
but before open/claim.

```text
D278_14_CORRECTIVE_1=FPDEVICE_USB_BINDING_CONSTRUCTION
D278_14_CORRECTIVE_1_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_CORRECTIVE_1_OUTCOME=PASS_HOST_ONLY
FPDEVICE_USB_BINDING_CORRECTED=true
FPDEVICE_TRANSPORT_TYPE_USB_COMPATIBLE=true
NON_NULL_GUSBDEVICE_FPDEVICE_BINDING_HOST_ONLY_PROVEN=true
PHYSICAL_CONSTRUCTOR_BEFORE_USB_OPEN_CLAIM=true
FPDEVICE_USB_BINDING_CONSTRUCTION_HOST_ONLY=PASS
```

## Corrective #2 — IN completion re-arm unification

The second host-only corrective unified IN-completion follow-up between the
synthetic test seam and the production backend path. `GoodixDeviceContext`
registers `context_usb_in_completed()` once on the backend; the callback
re-arms receive when needed and no IN is outstanding.
`goodix_device_context_complete_receive()` remains only a host/test injection
seam.

```text
D278_14_CORRECTIVE_2=IN_COMPLETION_REARM_UNIFICATION
D278_14_CORRECTIVE_2_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_CORRECTIVE_2_OUTCOME=PASS_HOST_ONLY
D278_14_CORRECTIVE_2_ROOT_CAUSE=REAL_USB_BACKEND_COMPLETION_BYPASSES_CONTEXT_RECEIVE_REARM_FOLLOWUP
D278_14_CORRECTIVE_2_FIX=IN_COMPLETED_CALLBACK_UNIFIES_REAL_AND_SYNTHETIC_PATHS
SYNTHETIC_AND_REAL_IN_COMPLETION_FOLLOWUP_UNIFIED=true
BACKEND_LEVEL_A2_ACK_COMPLETION_REARMS_NEXT_IN=true
BACKEND_LEVEL_A2_TYPED_COMPLETION_ADVANCES_TO_A8=true
MAX_PHYSICAL_IN_OUTSTANDING=1
NO_PARALLEL_STACK=true
```

`test_backend_in_completion_rearms_receive` calls
`goodix_fpi_usb_backend_complete_receive()` directly for the A2 ACK, asserts
that a second IN is submitted, then feeds the typed A2 response on that second
IN and asserts advancement to A8.

## Corrective #3 — operator UX, evidence history, telemetry closure

This step corrects the historical record and closes operator-facing UX without
changing protocol semantics or the core re-arm design.

### Operator prompt state machine

The operator tool now monitors the actual `GoodixPostTlsPhase` at 10 ms and
emits Italian action banners only once per persistent wait phase:

- `GOODIX_POST_TLS_PHASE_FIRST_IRQ2`
  `METTI IL DITO SUL SENSORE E ATTENDI IL PROSSIMO MESSAGGIO`
- `GOODIX_POST_TLS_PHASE_RELEASE_IRQ200`
  `TOGLI IL DITO DAL SENSORE E ATTENDI IL PROSSIMO MESSAGGIO`
- `GOODIX_POST_TLS_PHASE_SECOND_IRQ2`
  `METTI DI NUOVO IL DITO SUL SENSORE E ATTENDI IL PROSSIMO MESSAGGIO`
- `GOODIX_POST_TLS_PHASE_STOP`
  `TEST COMPLETATO. TOGLI IL DITO DAL SENSORE. NON ESEGUIRE NUOVAMENTE IL COMANDO.`
- terminal / one-shot deadline
  `TEST INTERROTTO. NON ESEGUIRE NUOVAMENTE IL COMANDO.`

Banners are surrounded by visible `======================` separator lines.
Success and failure banners are mutually exclusive; duplicate suppression is
proven host-only.

```text
OPERATOR_MESSAGES_LANGUAGE=ITALIAN
OPERATOR_ACTION_BANNERS_IMPLEMENTED=true
OPERATOR_ACTION_BANNER_FORMAT_EXACT=true
OPERATOR_ACTION_BANNER_MACHINE_PREFIX=false
OPERATOR_PROMPTS_RUNTIME_STATE_DRIVEN=true
OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true
OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_STOP_THEN_TERMINAL_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_TERMINAL_THEN_STOP_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_PRELIVE_GATED=true
```

### Bounded stop telemetry

The live-shaped JSON output now captures stop-state values before teardown:

```text
secure_protocol_failure_recorded
secure_protocol_failure_phase
secure_protocol_failure_kind
post_tls_terminal
observed_outer_type
observed_a0_control
observed_ack_echo
observed_ack_status
observed_body_length
secure_phase_at_stop
post_tls_phase_at_stop
in_outstanding_at_stop
router_outstanding_at_stop
stop_time_ms
```

No PSK, raw OTP, raw CONFIG90, FDT bytes, raw fingerprint/image data,
authorization nonce or protected material is logged.

```text
BOUNDED_STOP_TELEMETRY_COMPLETE=true
SENSITIVE_TELEMETRY_EXPOSURE=false
```

## Corrective #4 — exact banners and terminal/STOP exclusivity

The follow-up micro-corrective pins the exact multiline banner format, removes
machine prefixes from operator actions, and proves that STOP→TERMINAL and
TERMINAL→STOP callback orderings cannot emit contradictory final banners.

## Corrective #5 — bounded pre-ACK pinned A2 residue

Only in `REENTRY_RECOVERY_A2`, the secure-session policy may discard exactly
one typed A2 received before the current ACK when its body is exactly three
bytes and its SHA-256 matches `material.a2_response_sha256`. The discarded
frame is audited as `PRE_ACK_PINNED_TYPED_DISCARDED`, does not increment the
normal typed count, complete the phase, advance to A8 or submit another A2.
The existing backend completion callback re-arms the sole physical IN, after
which the current command must still complete the normal strict sequence:
valid ACK, then a second pinned typed A2, then A8.

Wrong length, wrong pin, a second pre-ACK pinned A2, any attempt outside the
reentry phase, unexpected control/class and malformed frames remain terminal.
No raw three-byte body is logged.

The integrated backend-level regression uses one `GoodixDeviceContext` and
calls `goodix_fpi_usb_backend_complete_receive()` directly. It proves IN
submit counts 1→2→3 across pre-ACK discard and ACK, maximum one outstanding
IN, normal typed count 0 until the post-ACK typed response, and final advance
to A8. The unchanged ACK→typed regression remains green.

```text
REENTRY_PRE_ACK_PINNED_TYPED_BOUNDED_DISCARD_IMPLEMENTED=true
PRE_ACK_PINNED_TYPED_THEN_ACK_THEN_TYPED_TO_A8_HOST_ONLY_PROVEN=true
SECOND_PRE_ACK_TYPED_FAIL_CLOSED_HOST_ONLY_PROVEN=true
WRONG_PIN_PRE_ACK_TYPED_FAIL_CLOSED_HOST_ONLY_PROVEN=true
WRONG_LENGTH_PRE_ACK_TYPED_FAIL_CLOSED_HOST_ONLY_PROVEN=true
PRE_ACK_TYPED_OUTSIDE_REENTRY_FAIL_CLOSED_HOST_ONLY_PROVEN=true
CORE_IN_REARM_CORRECTIVE_RETAINED=true
MAX_PHYSICAL_IN_OUTSTANDING=1
NO_PARALLEL_STACK=true
```

## Regression results

All commands ran from the Git root. Flatpak tests used Freedesktop SDK 25.08
with networking explicitly disabled. No test enumerated or opened a real USB
device.

| Check | Result |
| --- | --- |
| `run_goodix_fpimage_device_test.sh` | 18/18 normal PASS; 18/18 ASAN/UBSAN PASS |
| `run_goodix_d278_secure_session_test.sh` | 20/20 normal PASS; 20/20 ASAN/UBSAN PASS |
| `run_goodix_d278_12_post_tls_test.sh` | 6/6 normal PASS; 6/6 ASAN/UBSAN PASS |
| `run_goodix_d278_02_test.sh` | 62/62 normal PASS; 62/62 ASAN/UBSAN PASS |
| D278/13 adapter build/link/`ldd` | PASS |
| operator launcher `--host-only-prelive` from cwd `/tmp` | PASS |
| adapter `--operator-prompt-state-machine-host-only` | PASS |
| operator prompt STOP→TERMINAL exclusivity | PASS |
| operator prompt TERMINAL→STOP exclusivity | PASS |
| operator action banner exact format (no machine prefix) | PASS |
| adapter `--physical-constructor-host-only` | PASS |
| canonical baseline guard (`--baseline-only`) | PASS |
| ticket single-shot guard tests (built-in) | PASS |
| forbidden persistent-recovery source/symbol audit | PASS |
| duplicate-stack audit | PASS |
| legacy-harness fallback audit | PASS |
| changed shell `sh -n` | PASS |
| `git diff --check` | PASS |

The unchanged architecture tests retain:

```text
D278_13_ARCHITECTURE_RETAINED=true
NO_PARALLEL_STACK=true
SINGLE_GOODIX_DEVICE_CONTEXT=true
SINGLE_USB_BACKEND_OWNER=true
SINGLE_USB_ROUTER=true
SINGLE_PHYSICAL_IN_OWNER=true
SINGLE_TLS_OBJECT=true
TLS_HANDSHAKE_COUNT_MAX=1
SECRET_HANDOFF_COUNT_MAX=1
THIRD_CYCLE_COMMAND_COUNT=0
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

## No-live boundary and residual gate

```text
CORE_IN_REARM_CORRECTIVE_RETAINED=true
SYNTHETIC_AND_REAL_IN_COMPLETION_FOLLOWUP_UNIFIED=true
BACKEND_LEVEL_A2_ACK_COMPLETION_REARMS_NEXT_IN=true
BACKEND_LEVEL_A2_TYPED_COMPLETION_ADVANCES_TO_A8=true
D278_14_TOTAL_LIVE_ATTEMPTS=3
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=3
D278_14_HISTORY_CORRECTED=true
OPERATOR_MESSAGES_LANGUAGE=ITALIAN
OPERATOR_ACTION_BANNERS_IMPLEMENTED=true
OPERATOR_ACTION_BANNER_FORMAT_EXACT=true
OPERATOR_ACTION_BANNER_MACHINE_PREFIX=false
OPERATOR_PROMPTS_RUNTIME_STATE_DRIVEN=true
OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true
OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_STOP_THEN_TERMINAL_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_TERMINAL_THEN_STOP_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_PRELIVE_GATED=true
BOUNDED_STOP_TELEMETRY_COMPLETE=true
SENSITIVE_TELEMETRY_EXPOSURE=false
NO_PARALLEL_STACK=true
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
REAL_USB_ACCESS=false
REAL_USB_SUBMIT=0
REAL_PRODUCTION_SECRET_READ=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

A future sensor-reaching execution requires commit/push, independent AI-PM
review of a new live-critical baseline, explicit User authorization and a new
one-shot operator kit/ticket.

## Git-native review set

```text
REVIEW_SET=BASELINE_87c1bf89d0ba28497313f4bb75a8de4bbdb37b75_ON_main_PLUS_FINAL_COMMIT_PLUS_CURRENT_STEP_CHANGED_FILES
```

No ZIP/Base64, branch change, merge, reset, core-dump operation, real USB
access or production-secret read was performed by this corrective.
