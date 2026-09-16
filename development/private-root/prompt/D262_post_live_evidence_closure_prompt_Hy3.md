# D262 — post-live evidence closure

**Target AI executor:** Hy3 Free  
**Reasoning level:** MEDIUM  
**Mode:** OFFLINE / DOCUMENTATION-AND-EVIDENCE ONLY  
**Milestone:** keep the same **D262**. Do **not** create D263.

## Objective

Close D262 after the single authorized live fresh-FDT arm attempt completed successfully.

This is **not** a new hardware step. The live attempt has already occurred and MUST NOT be repeated.

The operator-visible terminal result was:

```json
{
  "phase_reached": "STOP_AFTER_FDT_ARM_ACK",
  "report": "/var/lib/goodix-5125-poc/d261-results/d261-final.json",
  "result": "PASS_STOP_AFTER_FDT_ARM_ACK"
}
```

The durable result report was retrieved read-only and is reproduced below as authoritative operator-provided evidence for this closure.

## Authoritative live-result evidence

```json
{
  "approved_baseline_sha": "e9073a171697bd68dd2debabb851f23d007bf718",
  "cache_write_count": 0,
  "fdt_command_trace": [
    "0x36",
    "0x50",
    "0x36",
    "0x82",
    "0x20",
    "0x36",
    "0x32"
  ],
  "finalized_utc": "2026-08-23T23:31:37.419371+02:00",
  "finger_interaction_count": 0,
  "firmware_version": "GF_ST411SEC_APP_12509",
  "fprintd_initial_state": "active",
  "fprintd_restore_status": "restored_to_initial_state",
  "live_critical_fileset_digest": "39d162077156b2af5fdb4b43d4382923006aa44f75e1e44c0fff741709761418",
  "marker_status": "claimed_single_use",
  "persistent_write_count": 0,
  "phase_reached": "STOP_AFTER_FDT_ARM_ACK",
  "result": "PASS_STOP_AFTER_FDT_ARM_ACK",
  "retry_count": 0,
  "runtime_audit": {
    "0x70_special_recovery_count": 0,
    "a2_special_recovery_count": 0,
    "af_attempt_count": 1,
    "af_retry_count": 0,
    "af_send_count": 1,
    "baseline_b0_consumed_before_stage2": true,
    "baseline_b0_tls_consumed": true,
    "classifier_call_count": 0,
    "cold_start_command_trace": [
      "0xa8",
      "0xe4",
      "0xa2",
      "0x82",
      "0xa6",
      "0xa2",
      "0x70",
      "0x80",
      "0x80",
      "0x80",
      "0x80",
      "0x90"
    ],
    "cold_start_gpl_runtime_completed": true,
    "cold_start_phase_trace": [
      "A8",
      "E4",
      "A2_1",
      "CHIP_82",
      "OTP_A6",
      "A2_2",
      "MODE_70",
      "DAC_220",
      "DAC_236",
      "DAC_238",
      "DAC_23A",
      "CONFIG_90"
    ],
    "d4_attempt_count": 1,
    "d4_send_count": 1,
    "d4_tls_application_record_count": 0,
    "e4_validation_count": 1,
    "exact_fdt_command_trace": [
      "0x36",
      "0x50",
      "0x36",
      "0x82",
      "0x20",
      "0x36",
      "0x32"
    ],
    "failure_reason": null,
    "host_cache_write_count": 0,
    "operational_fdt_physical_policy": true,
    "persistent_device_write_count": 0,
    "raster_decode_count": 0,
    "retry_count": 0,
    "runtime_state": "CLOSED",
    "second_native_delta_passed": true,
    "second_psk_provisioning": false,
    "second_server_session_created": false,
    "secret_boundary_handoff_count": 1,
    "secret_boundary_zeroized": true,
    "target_firmware": "GF_ST411SEC_APP_12509",
    "tls_close_count": 1,
    "tls_server_handshake_count": 1,
    "tls_server_session_object_count": 1,
    "tls_uses_same_secret_boundary_object": true,
    "transport_cleanup_count": 1,
    "transport_reopen_after_tls": false,
    "usb_transport_session_count": 1
  },
  "schema": "D261_LIVE_FDT_ARM_ONCE_RESULT_V1",
  "secret_log_count": 0,
  "secret_zeroized": true,
  "signal_restore_status": "restored",
  "target_identity": "27c6:5125"
}
```

Treat this report as primary evidence for the D262 live result. Do not invent fields that are not supported by it.

Approved immutable live-critical baseline:

```text
e9073a171697bd68dd2debabb851f23d007bf718
```

Expected working branch:

```text
sandbox_free_model
```

## Absolute prohibitions

Do **not**:

- execute the live launcher;
- use `sudo`;
- open real USB;
- read the real secret again;
- create or reset the single-use marker;
- mutate `fprintd`;
- touch persistent device state;
- flash/IAP/ClearApp;
- provision or replace PSK material;
- send any hardware command;
- put a finger on the sensor;
- attempt 0x22, post-finger image, enrollment, verification, matching, or any later live step;
- modify any D261 live-critical file;
- create a commit, push, merge, rebase, amend, or reset.

The single-use attempt is already consumed:

```text
marker_status = claimed_single_use
SECOND_LIVE_ATTEMPT_ALLOWED = false
```

If any requested closure work would require modification of a D261 live-critical path, STOP and report:

```text
OUTCOME=BLOCKED_LIVE_CRITICAL_CHANGE_REQUIRED
```

## 1. Verify repository state only

Run lightweight repository checks:

```bash
git branch --show-current
git status --short
git diff --check
git diff --name-only e9073a171697bd68dd2debabb851f23d007bf718
```

Confirm that no D261 live-critical path has changed from the approved baseline.

Do not run the live launcher, even with `--dry-run`, unless needed purely to resolve an inconsistency in existing D262 evidence. The expected closure should not require it.

Do not rerun the 238-test suite unless a code file unexpectedly changed. No code change is expected or allowed.

## 2. Record the live evidence under `analysis/D262/`

Create or update step-local D262 evidence artifacts so the successful live result is preserved in the repository rather than only in chat.

At minimum create:

```text
analysis/D262/D262_live_fdt_arm_result.json
analysis/D262/D262_post_live_closure_report.md
analysis/D262/D262_post_live_decision.json
```

The JSON evidence should faithfully preserve the authoritative live report above, either verbatim or as a clearly identified normalized copy with provenance back to:

```text
/var/lib/goodix-5125-poc/d261-results/d261-final.json
```

Do not include secrets, raw biometric data, B0 plaintext, OTP/cache bytes, DLLs, firmware blobs, or other protected material.

### Required conclusions supported by the live report

Record, without broadening beyond the tested target/firmware:

```text
D262_LIVE_ATTEMPT=PASS
D262_LIVE_RESULT=PASS_STOP_AFTER_FDT_ARM_ACK
PHASE_REACHED=STOP_AFTER_FDT_ARM_ACK

TARGET_IDENTITY=27c6:5125
TARGET_FIRMWARE=GF_ST411SEC_APP_12509

APPROVED_BASELINE_SHA=e9073a171697bd68dd2debabb851f23d007bf718
LIVE_CRITICAL_FILESET_DIGEST=39d162077156b2af5fdb4b43d4382923006aa44f75e1e44c0fff741709761418

EXACT_FDT_COMMAND_TRACE=0x36,0x50,0x36,0x82,0x20,0x36,0x32
FDT_ARM_BOUNDARY_LIVE_PROVEN=true

FINGER_INTERACTION_COUNT=0
RASTER_DECODE_COUNT=0
RETRY_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
CACHE_WRITE_COUNT=0
HOST_CACHE_WRITE_COUNT=0
A2_SPECIAL_RECOVERY_COUNT=0
0X70_SPECIAL_RECOVERY_COUNT=0

USB_TRANSPORT_SESSION_COUNT=1
TLS_SERVER_SESSION_OBJECT_COUNT=1
TLS_SERVER_HANDSHAKE_COUNT=1
TRANSPORT_REOPEN_AFTER_TLS=false
TRANSPORT_CLEANUP_COUNT=1
TLS_CLOSE_COUNT=1

SECOND_SERVER_SESSION_CREATED=false
SECOND_PSK_PROVISIONING=false
SECRET_BOUNDARY_HANDOFF_COUNT=1
SECRET_BOUNDARY_ZEROIZED=true
SECRET_ZEROIZED=true
SECRET_LOG_COUNT=0

BASELINE_B0_TLS_CONSUMED=true
BASELINE_B0_CONSUMED_BEFORE_STAGE2=true
SECOND_NATIVE_DELTA_PASSED=true

FPRINTD_RESTORE_STATUS=restored_to_initial_state
SIGNAL_RESTORE_STATUS=restored
RUNTIME_STATE=CLOSED

SINGLE_USE_MARKER_STATUS=claimed_single_use
SECOND_LIVE_ATTEMPT_ALLOWED=false
```

## 3. Retire the D262 zero-tail uncertainty precisely

Before this live attempt the main unresolved D262 risk was:

```text
FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
```

The successful exact live trace now proves, **for the primary target `27c6:5125` running `GF_ST411SEC_APP_12509` and for this bounded path**, that the operational fixed-64 zero-tail policy was accepted through:

```text
0x36
0x50
0x36
0x82
0x20
0x36
0x32
```

Therefore update the D262 evidence taxonomy so that:

```text
0x32 zero-tail = PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED
0x36 zero-tail = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
0x50 zero-tail = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
0x82 zero-tail = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
0x20 zero-tail = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
```

Do **not** generalize this to:

- other Goodix devices;
- other firmware versions;
- other control commands;
- post-finger flow;
- 0x22;
- enrollment/matching;
- persistent-write operations.

Record explicitly:

```text
D262_PRIMARY_ZERO_TAIL_RISK_RETIRED=true
D262_ZERO_TAIL_PROOF_SCOPE=PRIMARY_TARGET_27C6_5125_APP_12509_BOUNDED_FDT_ARM_PATH
```

Do not invent a new "primary future risk" if the existing evidence/manual does not yet justify one. If a later boundary remains unknown, describe it only as an unreviewed future boundary, not as a proven blocker.

## 4. Update the canonical manual organically

Update:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

The manual must remain an ordered technical manual, not an append-only bundle log.

Update the **high/canonical state sections** as needed, not only a D262 appendix.

Required semantic changes:

- D262 live execution is now completed and successful.
- The fresh-FDT arm boundary is live-proven on the primary target.
- The exact successful sequence is:
  `0x36 → 0x50 → 0x36 → 0x82 → 0x20 → 0x36 → 0x32 → STOP_AFTER_FDT_ARM_ACK`.
- The previously unresolved zero-tail acceptance for `0x36/0x50/0x82/0x20` is now retired for this target/firmware/path.
- `0x32` remains target-proven and ACK-accepted.
- No finger interaction occurred.
- `0x22` and post-finger image were not reached.
- No retry occurred.
- No persistent device or cache write occurred.
- No A2/0x70 recovery occurred.
- One USB transport session and one TLS server session/handshake were used.
- B0 was consumed on retained TLS before stage2.
- Secret material was zeroized and not logged.
- `fprintd` and signal state were restored.
- Runtime closed cleanly.
- The single-use marker is consumed and the same attempt must not be repeated.
- Preserve factory-preserving constraints and Windows compatibility requirements.

Do not leave this knowledge only in D262 report files.

## 5. Final D262 decision state

Create/update `analysis/D262/D262_post_live_decision.json` with a concise machine-readable closure.

Expected maximum state:

```text
OUTCOME=PASS
ADVANCEMENT=LIVE_FDT_ARM_BOUNDARY_PROVEN
EXECUTABLE_CLOSURE=PASS

D262_LIVE_ATTEMPT=PASS
D262_LIVE_RESULT=PASS_STOP_AFTER_FDT_ARM_ACK
FDT_ARM_BOUNDARY_LIVE_PROVEN=true
D262_PRIMARY_ZERO_TAIL_RISK_RETIRED=true

READY_FOR_D262_OPERATOR_EXECUTION_REVIEW=false
READY_FOR_D262_OPERATOR_EXECUTION=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false

SECOND_LIVE_ATTEMPT_ALLOWED=false
NEXT_LIVE_BOUNDARY_REQUIRES_NEW_AI_PM_REVIEW_AND_EXPLICIT_USER_AUTHORIZATION=true

CANONICAL_MANUAL_UPDATED=true
```

The `READY_FOR_*` values are false because D262 is already executed and closed, not because D262 failed.

Do not authorize or prepare a new post-finger live execution in this step.

## 6. Bundle

Create a **step-local, non-cumulative** bundle:

```text
analysis/D262/D262_post_live_evidence_closure_bundle.zip
analysis/D262/D262_post_live_evidence_closure_bundle.zip.sha256
```

Include only the D262 post-live closure artifacts needed for review plus the updated canonical manual.

Recommended contents:

```text
analysis/D262/D262_live_fdt_arm_result.json
analysis/D262/D262_post_live_closure_report.md
analysis/D262/D262_post_live_decision.json
Goodix 27c6 5125 manuale tecnico.md
```

Optionally include an updated D262 manifest if useful.

Exclude raw captures, raw cache/OTP, secret material, OEM DLL/firmware, plaintext B0/image data, biometric material, old cumulative bundles, and `prompt/`.

Verify:

```bash
git diff --check
```

and verify ZIP CRC plus SHA-256 sidecar.

## 7. Final closure output

Return a concise closure containing at least:

```text
OUTCOME
ADVANCEMENT
EXECUTABLE_CLOSURE

D262_LIVE_ATTEMPT
D262_LIVE_RESULT
PHASE_REACHED
FDT_ARM_BOUNDARY_LIVE_PROVEN
D262_PRIMARY_ZERO_TAIL_RISK_RETIRED

TARGET_IDENTITY
TARGET_FIRMWARE
APPROVED_BASELINE_SHA
LIVE_CRITICAL_FILESET_DIGEST

EXACT_FDT_COMMAND_TRACE
FINGER_INTERACTION_COUNT
RASTER_DECODE_COUNT
RETRY_COUNT
PERSISTENT_DEVICE_WRITE_COUNT
CACHE_WRITE_COUNT
A2_SPECIAL_RECOVERY_COUNT
0X70_SPECIAL_RECOVERY_COUNT

USB_TRANSPORT_SESSION_COUNT
TLS_SERVER_SESSION_OBJECT_COUNT
TLS_SERVER_HANDSHAKE_COUNT
TRANSPORT_REOPEN_AFTER_TLS
TRANSPORT_CLEANUP_COUNT

SECRET_BOUNDARY_ZEROIZED
SECRET_ZEROIZED
SECRET_LOG_COUNT

FPRINTD_RESTORE_STATUS
SIGNAL_RESTORE_STATUS
RUNTIME_STATE
SINGLE_USE_MARKER_STATUS
SECOND_LIVE_ATTEMPT_ALLOWED

READY_FOR_D262_OPERATOR_EXECUTION_REVIEW
READY_FOR_D262_OPERATOR_EXECUTION
READY_FOR_FDT_LIVE_REVIEW
READY_FOR_FDT_LIVE

NEXT_LIVE_BOUNDARY_REQUIRES_NEW_AI_PM_REVIEW_AND_EXPLICIT_USER_AUTHORIZATION

CANONICAL_MANUAL_UPDATED
BUNDLE
BUNDLE_SHA256
```

Stop after producing the bundle and final closure.

**Do not execute hardware.**
