# D259 — minimal device contract closure

```text
OUTCOME=READY_CLASS_A_OFFLINE
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_MINIMAL_OFFLINE_CANDIDATE_CLOSED
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=LIVE_REVIEW_REQUIRED_FOR_RUNTIME_TLS_INTEGRATION_BASELINE_AND_GUARDRAILS; GENERAL_CACHE_TTL_REMAINS_FUNCTIONAL_RISK; EXACT_OEM_CLASSIFIER_FIDELITY_DEFERRED
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
BUNDLE=analysis/D259/D259_minimal_device_contract_closure_bundle.zip
BUNDLE_SHA256=SEE_STEP_LOCAL_SIDECAR
```

## Result

D259 closes the factory-preserving minimal FDT candidate offline as readiness
Class A. It does not authorize a live run. The hash-gated branch audit covers
NAV and image classifier returns `0`, `1`, `2`, `3`, and negative/other. Every
return converges with `gf_update_all_base` still returning success. Return `1`
keeps the existing host base; every other value copies the newly acquired host
base and marks the shared host-cache dirty flag. No return changes the FDT table,
final `0x32` payload, command sequence, retry/rebuild behavior, recovery command,
or reachability of the caller's final `0x32`.

This means classifier execution is causally non-observable by the MCU for the
bounded first-arm contract. It does not mean the MCU blindly accepts `0x32`, or
that classifiers have no future role. Exact classifier behavior remains relevant
to full OEM host fidelity, quality decisions, base refresh, and cache fidelity.

## Wire and cache cut

The target `gfusb.dll` initializes the successful result before both classifier
switches and returns it unchanged. The FDT-down builder reads the independent
global table `0x180580818`. The OEM host-cache path calls
`gf_savebaseTofile`/`goodix.dat` conditionally before returning to the caller;
the caller then reaches final `ChicagoHUSetMode(3,1,1)`. The cache call result is
not a final-arm gate, and no post-arm cache write is observed in this path.

Linux first-live policy therefore remains `HOST_CACHE_WRITE_COUNT=0`. This is a
cut between OEM host fidelity and factory preservation: omitting the unnecessary
new host persistence does not mutate the device or Windows factory state.

## Required TLS consumption

The `0x20` B0 is not discarded as ciphertext. The reusable GPL core retains an
active TLS 1.2 PSK OpenSSL MemoryBIO session after handshake, feeds the B0 TLS
application record into that session, authenticates/decrypts it, promptly
zeroizes the application plaintext, and discards it. The minimal path performs
no raster decode and no semantic classifier.

D245 is the live target evidence that the Linux runtime completed one TLS
session using the same E4-validated secret. D259's new post-handshake B0
capability is verified offline with a synthetic non-biometric PSK/plaintext. The
historical D255 B0 plaintext remains unavailable and was neither requested nor
claimed; D255 supplies wire requests and non-B0 responses only by reference.

## Offline replay

The complete candidate replay passes:

```text
validated OTP-bound seed
-> 0x36 + ACK/IRQ100
-> 0x50 + structurally valid response
-> 0x36 + ACK/IRQ100
-> 0x82 + native delta PASS
-> 0x20 + B0 TLS authenticate/decrypt/zeroize/discard
-> 0x36 + ACK/IRQ100
-> second native delta PASS
-> final 0x32 exactly once
```

All seven requests are byte-exact against D255. The B0 response alone is a
synthetic TLS application record with the target-observed 7,726-byte outer
shape. Per-command timeouts are `500,500,500,500,2000,500,100` ms. Classifier,
raster decode, cache write, retry, A2, `0x70`, device persistence, and all real
hardware counters are zero. Failure policy remains no retry, no special
recovery command, and terminal host-side cleanup.

## Required closure fields

```text
POST_STAGE2_CLASSIFIER_DEVICE_PROGRESS_REQUIRED=false
POST_STAGE2_CLASSIFIER_FACTORY_PRESERVATION_REQUIRED=false
POST_STAGE2_CLASSIFIER_FIRST_ARM_REQUIRED=false
POST_STAGE2_CLASSIFIER_OEM_HOST_FIDELITY_REQUIRED=true
POST_STAGE2_CLASSIFIER_HOST_PERSISTENCE_REQUIRED=false

NAV_CLASSIFIER_FINAL_0x32_EFFECT=NONE
IMAGE_CLASSIFIER_FINAL_0x32_EFFECT=NONE
CLASSIFIER_FDT_TABLE_EFFECT=NONE
CLASSIFIER_FINAL_0x32_PAYLOAD_EFFECT=NONE
CLASSIFIER_ADDITIONAL_DEVICE_COMMANDS=NONE
CLASSIFIER_RETRY_OR_REBUILD_EFFECT=NONE
CLASSIFIER_ERROR_RECOVERY_COMMANDS=NONE

BASELINE_B0_TLS_CONSUMPTION_REQUIRED=true
BASELINE_B0_IMAGE_CLASSIFICATION_REQUIRED=false
BASELINE_B0_RASTER_DECODE_REQUIRED=false
HISTORICAL_D255_B0_PLAINTEXT_AVAILABLE=false
FUTURE_LINUX_RUNTIME_TLS_SESSION_PROVEN=true
FUTURE_LINUX_RUNTIME_B0_CONSUMPTION_CAPABILITY=true

OEM_CACHE_WRITE_BEFORE_FINAL_0x32=CONDITIONAL
OEM_CACHE_WRITE_AFTER_FINAL_0x32=false
OEM_CACHE_WRITE_REQUIRED_FOR_FINAL_0x32=false
OEM_CACHE_WRITE_REQUIRED_FOR_DEVICE_PROGRESS=false
LINUX_FIRST_LIVE_CACHE_WRITE_POLICY=DISABLED

CORPUS_EXHAUSTED_FOR_EXACT_OEM_HOST_FIDELITY=true
CORPUS_EXHAUSTED_FOR_MINIMAL_DEVICE_LIVE_CONTRACT=false
MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED=true
FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED=true
FDT_OFFLINE_CANDIDATE_CLOSED=true
READY_FOR_FDT_LIVE_REVIEW=true
READY_FOR_FDT_LIVE=false

NO_SPECIAL_FDT_RECOVERY_COMMAND_POLICY=DEFAULT
A2_REENTRY_INJECTION=0
0x70_REENTRY_INJECTION=0
REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
REAL_COMMAND_SEND_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
HOST_CACHE_WRITE_COUNT=0
```

`READY_FOR_FDT_LIVE_REVIEW=true` is only permission to conduct a separate
review. It is not a live authorization, does not approve a Git baseline, and
does not create D260 or an operator kit.
