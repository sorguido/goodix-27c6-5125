# D262 — post-live evidence closure report

**Step:** D262 (kept, not D263)
**Mode:** OFFLINE / DOCUMENTATION-AND-EVIDENCE ONLY
**Target AI executor:** Hy3 Free
**Reasoning level:** MEDIUM

## 1. Scope and prohibitions honored

This closure step does **not** execute hardware. The single authorized live
fresh-FDT arm attempt was already performed and MUST NOT be repeated. The
following were not performed and are not permitted by this step:

- no execution of the live launcher;
- no `sudo`;
- no real USB open;
- no real secret read;
- no creation/reset of the single-use marker;
- no `fprintd` mutation;
- no persistent device state change;
- no flash/IAP/ClearApp;
- no PSK provisioning/replacement;
- no hardware command send;
- no finger on sensor;
- no `0x22`, post-finger image, enrollment, verification, matching, or later live step;
- no modification of any D261 live-critical file;
- no commit, push, merge, rebase, amend, or reset.

The single-use attempt is consumed:

```text
marker_status = claimed_single_use
SECOND_LIVE_ATTEMPT_ALLOWED = false
```

## 2. Repository state verification

```bash
git branch --show-current        # sandbox_free_model
git status --short               # manual modified; analysis/D262/ + prompt/ untracked (prompt/ user-managed, outside D262 scope)
git diff --check                 # clean
git diff --name-only e9073a171697bd68dd2debabb851f23d007bf718
```

No D261 live-critical path (`core/`, `src/goodix5125_cleanroom.py`,
`poc/goodix5125/tools/binding_reference/`, `tools/d261_live_fdt_arm_once.py`,
`operator_kit/d261-live-fdt-arm-once.sh`) differs from the approved baseline
`e9073a171697bd68dd2debabb851f23d007bf718`. The D262 technical changes relevant
to this closure are the canonical manual plus the `analysis/D262/` artifacts;
`prompt/` is user-managed and explicitly outside D262 technical scope. No D261
live-critical path is modified.

## 3. Authoritative live result

The durable result report was retrieved read-only from
`/var/lib/goodix-5125-poc/d261-results/d261-final.json` and is preserved
verbatim (normalized copy with provenance) in
`D262_live_fdt_arm_result.json`.

Operator-visible terminal result:

```json
{
  "phase_reached": "STOP_AFTER_FDT_ARM_ACK",
  "report": "/var/lib/goodix-5125-poc/d261-results/d261-final.json",
  "result": "PASS_STOP_AFTER_FDT_ARM_ACK"
}
```

## 4. Required conclusions (supported only by the authoritative report)

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

None of the above generalizes beyond `27c6:5125` running
`GF_ST411SEC_APP_12509` on the bounded FDT arm path.

## 5. Zero-tail uncertainty retirement

Before this live attempt the main unresolved D262 risk was:

```text
FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
```

The successful exact live trace now proves, for the primary target
`27c6:5125` running `GF_ST411SEC_APP_12509` and for this bounded path, that the
operational fixed-64 zero-tail policy was accepted through:

```text
0x36
0x50
0x36
0x82
0x20
0x36
0x32
```

Therefore the D262 evidence taxonomy is updated so that:

```text
0x32 zero-tail = PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED
0x36 zero-tail = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
0x50 zero-tail = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
0x82 zero-tail = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
0x20 zero-tail = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
```

Not generalized to other Goodix devices, other firmware versions, other
control commands, post-finger flow, `0x22`, enrollment/matching, or
persistent-write operations.

```text
D262_PRIMARY_ZERO_TAIL_RISK_RETIRED=true
D262_ZERO_TAIL_PROOF_SCOPE=PRIMARY_TARGET_27C6_5125_APP_12509_BOUNDED_FDT_ARM_PATH
```

No new "primary future risk" is invented. The only remaining forward boundary is
an unreviewed future boundary: `0x22` and the post-finger image were not reached
and remain an open future boundary, described only as such (not as a proven
blocker).

## 6. Canonical manual update

`Goodix 27c6 5125 manuale tecnico.md` was updated organically:

- high/canonical `Stato del progetto` D262 paragraph now records the executed
  live success;
- `Current critical boundary` zero-tail risk statement retired for the primary
  target/firmware/path;
- detailed `D262` section extended with a "esecuzione live una tantum e closure"
  subsection;
- Hard Wall gained post-live D262 entries (`D262_LIVE_EXECUTION_PERFORMED_ONCE`,
  zero-tail per-command status, closure `OUTCOME/ADVANCEMENT/EXECUTABLE_CLOSURE`).

## 7. Closure decision (summary)

See `D262_post_live_decision.json` for the machine-readable closure.

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

The `READY_FOR_*` values are false because D262 is already executed and closed,
not because D262 failed. No new post-finger live execution is authorized here.
