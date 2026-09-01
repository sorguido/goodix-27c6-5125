# D278/14 — two consumed live attempts, two host-only correctives, operator UX/telemetry micro-corrective

## Outcome

```text
OUTCOME=PASS_HOST_ONLY_MICRO_CORRECTIVE
ADVANCEMENT=D278_14_HISTORY_CORRECTED_AND_OPERATOR_TELEMETRY_CLOSED_HOST_ONLY
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
CANONICAL_DOCUMENTATION=UPDATED
```

This document records **two consumed D278/14 live attempts** and the host-only
correctives that followed. No new live execution is performed or authorized.

```text
START_BRANCH=main
START_HEAD=3f495b5176ba4c37f72710b7f26f179a5ab8df96
FINAL_STATE=STEP_LOCAL_WORKTREE_DIFF_NO_COMMIT
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
D278_14_TOTAL_LIVE_ATTEMPTS=2
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=2
```

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

## Micro-corrective #3 — operator UX, evidence history, telemetry closure

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
OPERATOR_PROMPTS_RUNTIME_STATE_DRIVEN=true
OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true
OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true
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

## Regression results

All commands ran from the Git root. Flatpak tests used Freedesktop SDK 25.08
with networking explicitly disabled. No test enumerated or opened a real USB
device.

| Check | Result |
| --- | --- |
| `run_goodix_fpimage_device_test.sh` | 18/18 normal PASS; 18/18 ASAN/UBSAN PASS |
| `run_goodix_d278_secure_session_test.sh` | 18/18 normal PASS; 18/18 ASAN/UBSAN PASS |
| `run_goodix_d278_12_post_tls_test.sh` | 6/6 normal PASS; 6/6 ASAN/UBSAN PASS |
| `run_goodix_d278_02_test.sh` | 62/62 normal PASS; 62/62 ASAN/UBSAN PASS |
| D278/13 adapter build/link/`ldd` | PASS |
| operator launcher `--host-only-prelive` from cwd `/tmp` | PASS |
| adapter `--operator-prompt-state-machine-host-only` | PASS |
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
D278_14_TOTAL_LIVE_ATTEMPTS=2
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=2
D278_14_HISTORY_CORRECTED=true
OPERATOR_MESSAGES_LANGUAGE=ITALIAN
OPERATOR_ACTION_BANNERS_IMPLEMENTED=true
OPERATOR_PROMPTS_RUNTIME_STATE_DRIVEN=true
OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true
OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true
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
REVIEW_SET=BASELINE_3f495b5176ba4c37f72710b7f26f179a5ab8df96_ON_main_PLUS_CURRENT_WORKTREE_DIFF_PLUS_analysis/D278/D278_14_integrated_native_c_two_acquisition_live_once.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_libfprint-driver/goodix_post_tls_lifecycle.c_PLUS_libfprint-driver/goodix_post_tls_lifecycle.h_PLUS_libfprint-driver/goodix_fpimage_device.c_PLUS_libfprint-driver/goodix_fpimage_device.h_PLUS_libfprint-driver/goodix_fpi_usb_backend.c_PLUS_libfprint-driver/goodix_fpi_usb_backend.h_PLUS_tools/d278_integrated_path_once.c_PLUS_operator_kit/d278-13-integrated-path-once.sh_PLUS_libfprint-driver/tests/test_goodix_d278_secure_session.c_PLUS_libfprint-driver/tests/build_goodix_d278_13_adapter_inner.sh_PLUS_libfprint-driver/tests/test_goodix_fpimage_device.c_PLUS_libfprint-driver/tests/support/gusb_stub.c
```

No ZIP/Base64, commit, push, branch change, merge, reset, core-dump operation,
real USB access or production-secret read was performed by this corrective.
