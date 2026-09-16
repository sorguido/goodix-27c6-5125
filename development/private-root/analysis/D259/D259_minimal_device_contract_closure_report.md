# D259 corrective — mechanical Class A proof and TLS runtime integration audit

```text
OUTCOME=BLOCKED_LIVE_TLS_RUNTIME_ADAPTER_GAP
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_CLASS_A_MECHANICALLY_CONFIRMED_AND_TLS_RUNTIME_GAP_LOCALIZED
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=SEALED_D245_RUNTIME_CLOSES_AND_DOES_NOT_EXPOSE_THE_HANDSHAKED_TLS_ENGINE
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
BUNDLE=analysis/D259/D259_mechanical_classA_tls_integration_corrective_bundle.zip
BUNDLE_SHA256=SEE_STEP_LOCAL_SIDECAR
```

## Mechanical classifier result

The preliminary D259 assertion harness is superseded. The corrective parser
hash-gates `gfusb.dll` and the D255 raw, parses only the bounded D258/D259
address ranges, extracts compare/jump/call instructions, follows every NAV and
IMAGE case `0/1/2/3/default` to its merge, and derives the matrix from those
paths. The sanitized excerpt and structured CFG are reviewable without the DLL
or full disassembly.

The derived proof confirms Class A for the bounded first arm. All reachable
classifier returns preserve the successful `gf_update_all_base` result. Return
`1` keeps the current host base; all other returns copy the acquired host base
and set the host-cache dirty flag. The parsed paths contain no FDT-table write,
additional device command, retry/back-edge, A2/`0x70` recovery, or blocker to
the caller's final `ChicagoHUSetMode(3,1,1)`. The mode-3 builder independently
reads global FDT table `0x180580818` at `0x1800252c0`.

```text
POST_CLASSIFIER_BRANCH_PROOF=PASS_MECHANICALLY_DERIVED
BRANCH_MATRIX_DERIVATION_MODE=PARSED_DISASSEMBLY_CFG
NAV_RETURN_CFG_PROVEN=true
IMAGE_RETURN_CFG_PROVEN=true
CLASS_A_CLASSIFIER_HOST_ONLY_FOR_FIRST_ARM=true
CLASSIFIER_CHANGES_GF_UPDATE_ALL_BASE_SUCCESS=false
CLASSIFIER_CHANGES_FDT_TABLE=false
CLASSIFIER_CHANGES_FINAL_0x32_PAYLOAD=false
CLASSIFIER_EMITS_ADDITIONAL_DEVICE_COMMAND=false
CLASSIFIER_CAUSES_RETRY_OR_REBUILD=false
CLASSIFIER_CAUSES_RECOVERY=false
CLASSIFIER_BLOCKS_FINAL_0x32=false
```

## B0 ordering and same-session proof

The replay now consumes/authenticates/decrypts the synthetic target-shaped B0
immediately after the `0x20` response and before the third `0x36`. The minimal
finalizer no longer accepts a consumer or delays the B0. A second synthetic
application record is then decrypted by the same server `SSLObject` to prove
continued sequence/cipher state. No second server context, handshake, PSK
provisioning, or transport is created.

```text
LIVE_TLS_ROLE=SERVER
B0_CONSUMED_BEFORE_STAGE2=true
TLS_SERVER_SESSION_OBJECT_COUNT=1
TLS_CLIENT_SESSION_OBJECT_COUNT=1
TLS_SERVER_HANDSHAKE_COUNT=1
TLS_APPLICATION_RECORD_CONSUMPTION_COUNT=1
SECOND_SERVER_SESSION_CREATED=false
SECOND_PSK_PROVISIONING=false
SAME_TLS_SESSION_B0_CONSUMPTION=PASS_OFFLINE_ARCHITECTURAL
POST_B0_TLS_SESSION_CONTINUITY=PASS_OFFLINE_ARCHITECTURAL
```

Only the mutable plaintext buffer returned to project code is wiped
best-effort. Python `SSLObject.read()` returns immutable bytes and OpenSSL may
retain internal copies, so full physical memory zeroization is not claimed.

```text
PLAINTEXT_MUTABLE_BUFFER_BEST_EFFORT_ZEROIZED=true
OPENSSL_INTERNAL_COPY_ZEROIZATION=NOT_PROVEN
PYTHON_IMMUTABLE_TEMP_COPY_ZEROIZATION=NOT_PROVEN
```

## Runtime integration gap

The live-proven D245 direction is correct: Linux is the TLS server. However,
the sealed runtime creates `engine = self.tls_factory(secret)` as a local in
`ProductionReplayBackend.tls_handshake()` and unconditionally calls
`engine.close()` in its `finally`; it stores no post-handshake engine member.
The new GPL adapter can consume records through an already-handshaked
`SSLObject` and input MemoryBIO, but the unchanged live runtime cannot supply
that object after handshake.

The prompt forbids modifying `src/` or live launchers. Consequently the gap is
reported rather than bypassed:

```text
LIVE_TLS_TO_B0_ADAPTER_STATUS=UNIMPLEMENTED
SRC_SEALED_UNCHANGED=true
LIVE_LAUNCHERS_UNCHANGED=true
MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED=false
FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED=false
FDT_OFFLINE_CANDIDATE_CLOSED=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

## Replay and safety

The corrected offline replay passes the request trace
`36,50,36,82,20,36,32`, both native delta predicates and exactly-one final
`0x32`. It performs zero classifier, raster decode, cache write, retry, special
recovery or persistent family. D255 supplies requests and non-B0 responses by
private reference; the B0 and PSK fixture are synthetic and non-biometric.

```text
REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
REAL_COMMAND_SEND_COUNT=0
FINGER_INTERACTION_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
HOST_CACHE_WRITE_COUNT=0
```

The former `D259_minimal_device_contract_closure_bundle.zip` is preserved for
provenance and marked `SUPERSEDED_BY_D259_MECHANICAL_PROOF_CORRECTIVE`.
