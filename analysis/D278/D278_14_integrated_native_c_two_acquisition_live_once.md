# D278/14 — consumed live failure, FpDevice USB binding corrective, and IN re-arm follow-up corrective

## Outcome

```text
OUTCOME=PASS_HOST_ONLY_CORRECTIVE
ADVANCEMENT=FPDEVICE_USB_BINDING_EXECUTABLE_CLOSURE_FIXED_AND_IN_REARM_UNIFIED
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
CANONICAL_DOCUMENTATION=UPDATED
```

This document records two host-only corrective passes after one consumed live
failure. No new live execution is performed or authorized.

```text
START_BRANCH=main
START_HEAD=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_APPROVED_LIVE_BASELINE=2172e750ae7c100a3a891ba25d0797286230a4ab
FINAL_STATE=STEP_LOCAL_WORKTREE_DIFF_NO_COMMIT
```

## Consumed live evidence

The operator wrapper recorded one execution and no retry. The target had been
selected and the executable order strongly supports that open and claim had
completed when object construction aborted in repository-local libfprint:

```text
Rockytkg/libfprint/libfprint/fp-device.c:336:
fp_device_set_property:
assertion failed: (g_value_get_object (value) == NULL)
```

The failure is host-side construction, not a Goodix protocol response. The
abort occurred before `goodix_device_context_begin_operator_epoch()` and before
any A2, A8, TLS or post-TLS operation. `SIGABRT` bypassed normal project
cleanup, so release/close and canonical cleanup are not claimed as PASS.

```text
D278_14_LIVE_OUTCOME=FAIL_HOST_BINDING_BEFORE_PROTOCOL
D278_14_LIVE_EXECUTION_COUNT=1
D278_14_ONE_SHOT_CONSUMED=true
D278_14_RERUN_AUTHORIZED=false
FIRST_FAILURE_BOUNDARY=FPDEVICE_USB_BINDING_CONSTRUCTION
PROCESS_EXIT_CODE=134
PROCESS_TERMINATION=SIGABRT
REAL_USB_CONTEXT_REACHED=true
USB_TARGET_SELECTION_REACHED=true
USB_OPEN_AND_CLAIM_PRECEDED_ASSERT=STRONGLY_SUPPORTED_BY_EXECUTION_ORDER
GOODIX_APPLICATION_PROTOCOL_SUBMIT_REACHED=false
A2_REACHED=false
TLS_REACHED=false
POST_TLS_REACHED=false
PERSISTENT_DEVICE_WRITE_COUNT=0
RETRY_COUNT=0
CORE_DUMP_CREATED=OBSERVED
CORE_DUMP_MAY_CONTAIN_PROTECTED_IN_MEMORY_MATERIAL=true
CORE_DUMP_NOT_PART_OF_REVIEW_SET=true
```

The core dump was not read, copied, uploaded, analyzed or added to Git.

## Root cause and corrective design

`GoodixFpImageDeviceClass` declared `FP_DEVICE_TYPE_VIRTUAL`, while
`goodix_fpimage_device_new_for_usb()` assigned a non-NULL `fpi-usb-device`.
Repository-local `fp_device_set_property()` accepts that property only when
the final instance class type is `FP_DEVICE_TYPE_USB`; otherwise it asserts
that the value is NULL. The exact root cause is therefore:

```text
D278_14_ROOT_CAUSE=NON_NULL_FPI_USB_DEVICE_BOUND_TO_FP_DEVICE_TYPE_VIRTUAL
```

The base shell must remain virtual because the framework's normal
`fp_device_open()` path automatically calls `g_usb_device_open()` for USB
classes, while the existing deterministic shell tests intentionally use a
non-USB in-memory lifecycle. The corrective therefore uses the prompt's thin
transport-typing option:

- `GoodixFpImageDevice` is a derivable base with its context in private data;
- the existing synthetic constructor still returns the virtual base class;
- the physical constructor returns a private, unregistered subclass whose
  only class delta is `FpDeviceClass->type = FP_DEVICE_TYPE_USB`;
- the subclass inherits the exact same context, vfuncs, backend, router,
  secure-session, TLS, post-TLS lifecycle, decoder and image pipeline;
- no shared class type is mutated dynamically.

This matches local libfprint semantics because the property setter consults
the final instance class before `constructed()` copies its type into private
state.

## Attempt #2 — IN completion re-arm follow-up corrective

The first corrective fixed FpDevice USB construction but could not exercise the
real-USB receive path, because the consumed live attempt aborted before any A0
or B0 traffic. A second host-only corrective unifies IN-completion follow-up
between the synthetic test seam and the production backend path.

### Root cause

`goodix_device_context_complete_receive()` originally performed two jobs:

1. inject a received buffer into `goodix_fpi_usb_backend_complete_receive()`;
2. after injection, re-arm a fresh IN if the secure-session or post-TLS
   lifecycle still needed receive.

The production real-USB path, however, calls
`goodix_fpi_usb_backend_complete_receive()` directly from the libfprint USB
transfer callback. It never entered the context helper, so the re-arm logic was
bypassed on real hardware. The synthetic integrated tests happened to work
because they used the context helper, but a real ACK A2 would leave the backend
with no outstanding IN and the subsequent typed A2 response would have no queue
slot, stalling at `REENTRY_RECOVERY_A2`.

```text
D278_14_ATTEMPT_2_ROOT_CAUSE=BACKEND_IN_COMPLETION_BYPASSED_CONTEXT_REARM
```

### Design

A single `GoodixFpiUsbBackendInCompletedFunc` callback is registered when the
context is created:

```text
context_usb_in_completed() -> goodix_fpi_usb_backend_set_in_completed_callback()
```

The callback re-arms receive when `needs_receive()` is true and no IN is already
outstanding. `goodix_device_context_complete_receive()` is reduced to a
host/test injection seam that only forwards to the backend; the callback owns
the one follow-up policy. This makes synthetic and real-USB IN completions
converge on the same code path.

```text
D278_14_ATTEMPT_2_FIX=IN_COMPLETED_CALLBACK_UNIFIES_REAL_AND_SYNTHETIC_PATHS
```

### Regression proof

`test_backend_in_completion_rearms_receive` creates an integrated context,
starts the secure session, completes the A2 command OUT, then calls
`goodix_fpi_usb_backend_complete_receive()` directly for the A2 ACK. It asserts:

- a second IN is submitted (`in_submit_count` grows from 1 to 2);
- the backend still has exactly one IN outstanding;
- feeding the typed A2 response on that second IN advances the phase to A8;
- the A8 command is queued for transmission.

This reproduces the exact real-USB shape: backend-level completion, not the
context helper, drives the multi-response A2 chain.

`tools/d278_integrated_path_once.c` adds
`--operator-prompt-state-machine-host-only`. It uses synthetic secure-session
and post-TLS material, drives the same A2 ACK → re-arm → typed A2 → A8 chain,
and prints Italian operator banners at each step. No USB access, no secrets,
no persistent writes.

```text
D278_14_ATTEMPT_2_A2_BACKEND_REARM_HOST_ONLY_PROVEN=true
D278_14_ATTEMPT_2_A2_TYPED_ADVANCE_TO_A8_HOST_ONLY_PROVEN=true
D278_14_ATTEMPT_2_OPERATOR_PROMPT_STATE_MACHINE_HOST_ONLY=PASS
D278_14_ATTEMPT_2_ITALIAN_OPERATOR_MESSAGES=true
```

### Telemetry improvements

The live-shaped JSON output now includes failure and timing diagnostics:

```text
secure_protocol_failure_recorded
secure_protocol_failure_phase
secure_protocol_failure_kind
post_tls_terminal
stop_time_ms
```

Italian operator banners are emitted as human-readable `OPERATOR_MESSAGE_IT=...`
lines alongside the machine telemetry.

## Constructor-before-open guardrail

The live-shaped order is now:

```text
enumerate/select target
construct Goodix USB-typed FpDevice
validate non-NULL property identity, USB type and drained owner graph
open
claim
begin operator epoch
```

Construction creates the context and its owner graph but starts no generation
and submits no traffic. The adapter build performs an order audit over the
actual source and requires constructor line `<` open line `<` claim line.

```text
PHYSICAL_CONSTRUCTOR_BEFORE_USB_OPEN_CLAIM=true
```

## Non-NULL GUsbDevice regression

The focused FpImageDevice suite creates a non-NULL synthetic GUsb-compatible
GObject, invokes the actual physical constructor and proves:

- no assertion or abort;
- `fpi_device_get_usb_device()` returns the identical object;
- the final class transport type is USB;
- context, backend and router are non-NULL and stable by identity;
- backend is drained with zero IN/OUT outstanding and zero real submits;
- stub open and close counters remain zero;
- destruction is clean.

This exact case would abort on the starting baseline. It passes both normal
and ASAN/UBSAN variants. The live-shaped adapter adds an independent test with
an actual concrete `GUsbDevice` from the installed libgusb runtime, created by
`g_object_new(G_USB_TYPE_DEVICE, NULL)` without context creation, enumeration,
open or claim. It binds the same physical constructor and emits:

```text
FPDEVICE_USB_BINDING_CONSTRUCTION_HOST_ONLY=PASS
FPDEVICE_TRANSPORT_TYPE=USB
NON_NULL_GUSBDEVICE_BOUND=true
NON_NULL_GUSBDEVICE_FPDEVICE_BINDING_HOST_ONLY_PROVEN=true
SINGLE_GOODIX_DEVICE_CONTEXT=true
SINGLE_USB_BACKEND_OWNER=true
SINGLE_USB_ROUTER=true
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_ACCESS=false
REAL_USB_SUBMIT=0
REAL_PRODUCTION_SECRET_READ=false
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
| real-libgusb non-NULL constructor closure | PASS |
| constructor-before-open/claim order audit | PASS |
| baseline and ticket single-shot guards | PASS |
| forbidden persistent-recovery source/symbol audit | PASS |
| duplicate-stack audit | PASS |
| legacy-harness fallback audit | PASS |
| changed shell `sh -n` | PASS |

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
FPDEVICE_USB_BINDING_CORRECTED=true
FPDEVICE_TRANSPORT_TYPE_USB_COMPATIBLE=true
NON_NULL_GUSBDEVICE_FPDEVICE_BINDING_HOST_ONLY_PROVEN=true
FPDEVICE_USB_BINDING_CONSTRUCTION_HOST_ONLY=PASS
D278_14_ATTEMPT_2_HOST_ONLY_CORRECTIVE=true
D278_14_ATTEMPT_2_A2_BACKEND_REARM_HOST_ONLY_PROVEN=true
D278_14_ATTEMPT_2_A2_TYPED_ADVANCE_TO_A8_HOST_ONLY_PROVEN=true
D278_14_ATTEMPT_2_OPERATOR_PROMPT_STATE_MACHINE_HOST_ONLY=PASS
REAL_USB_ACCESS=false
REAL_USB_SUBMIT=0
REAL_PRODUCTION_SECRET_READ=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

These no-live markers apply to the corrective executions, not to the consumed
failed live attempt. A future sensor-reaching execution requires commit/push,
independent AI-PM review of a new live-critical baseline, explicit User
authorization and a new one-shot operator kit/ticket.

## Git-native review set

```text
REVIEW_SET=BASELINE_fceae05d9ff3ed14348f9031706e70d5a808ff91_ON_main_PLUS_CURRENT_WORKTREE_DIFF_PLUS_analysis/D278/D278_14_integrated_native_c_two_acquisition_live_once.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_libfprint-driver/goodix_fpimage_device.c_PLUS_libfprint-driver/goodix_fpimage_device.h_PLUS_libfprint-driver/goodix_fpi_usb_backend.c_PLUS_libfprint-driver/goodix_fpi_usb_backend.h_PLUS_tools/d278_integrated_path_once.c_PLUS_libfprint-driver/tests/test_goodix_d278_secure_session.c_PLUS_libfprint-driver/tests/build_goodix_d278_13_adapter_inner.sh_PLUS_libfprint-driver/tests/test_goodix_fpimage_device.c_PLUS_libfprint-driver/tests/support/gusb_stub.c
```

No ZIP/Base64, commit, push, branch change, merge, reset, core-dump operation,
real USB access or production-secret read was performed by this corrective.
