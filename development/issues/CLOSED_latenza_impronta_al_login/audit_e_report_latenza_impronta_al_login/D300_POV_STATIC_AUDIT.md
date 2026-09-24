# D300 — Static audit: pre-capture MCU state / POV path

## Scope

Static/evidence audit only. No code change and no live command is authorized by this document.

Question:

> Does the D299 cold-login failure plausibly correspond to a firmware state in which the finger/contact is already present before `FIRST_IRQ2`, and does the existing OEM/Rocky protocol contain a distinct pre-capture path for that state?

## D299 fact

Two immediate-finger cold runs independently ended with:

```text
capture_entry=1
post_tls_ack_consumed=8
post_tls_invalid_frame=0
first_irq2=0
first_cmd22=0
first_b0=0
first_decode=0
first_pipeline=0
cancel_count=1
cancel_phase=FIRST_IRQ2
```

The third-baseline delta was valid in both runs.

Therefore the normal image command was never submitted: the lifecycle reached the wait for a fresh FDT finger-down event but never observed it.

## Evidence chain for a pre-capture state decision

### OEM / project-local evidence

D251 static reverse engineering of `gfusb.dll` identifies `GetMcuState` and three direct call sites. State byte 1 is used for:

- bit0: POV-valid;
- bit1: TLS-connected;
- bit3: locked.

The project already proved on the real APP12509 that AF receives a direct structurally valid `0xAE` response containing 16 state bytes.

D249 preserved the target-observed AF wire body:

```text
55, timestamp16le, 00, 00
```

and modeled two branches:

```text
fresh:
AF POV=0 -> FDT down -> IRQ2 -> image

cached:
AF POV=1 -> D2 -> cached image
```

The cached branch reached `FIRST_IMAGE_RECEIVED` offline, but D249 explicitly classified the target D2 occurrence as incomplete/not established and FDT disarm/restore as unknown.

### Windows target evidence

Recovered D255 evidence from the real APP12509 contains a re-entry command sequence:

```text
0xD5 -> 0xAF -> 0x32
```

with no finger interaction.

This is target-specific evidence that the OEM path performs an AF state query immediately before normal FDT-down arming.

### Rockytkg corroboration

Rockytkg `gx_capture()`:

1. queries MCU state immediately before choosing the capture path;
2. reads POV-valid/TLS-connected/locked from state byte 1;
3. if POV-valid is false, arms normal FDT down `0x32`;
4. if POV-valid is true, sends `0xD2 {0,0}` WakeupMCU and waits for the image stream.

Rocky adds a 300 ms sleep after D2. That timing is not target-specific proof for this project and must not be copied automatically.

## Current local semantic gap

The current local lifecycle performs an AF query only near the beginning of the post-TLS bootstrap and requires:

```text
POV bit = 0
TLS-connected bit = 1
```

After the later baseline/image bootstrap it does not query MCU state again.

After the third baseline passes it unconditionally submits `FIRST_ARM` and then waits in `FIRST_IRQ2`.

This leaves an unmodeled interval:

```text
initial AF says POV=0
      |
      | baseline/nav/image/bootstrap activity
      | user places finger immediately
      v
third baseline passes
      |
      +--> local: FIRST_ARM -> wait for a *new* IRQ2
      |
      +--> OEM/Rocky model: query AF again, then choose POV or normal FDT
```

D299 is consistent with the local branch missing a contact that became current before the arm/wait transition.

## Why D2 is NOT yet authorized

A direct POV implementation would bypass the normal `IRQ2` event.

The local release path derives `first_up_table` only from that `IRQ2` raw FDT event, and after the first image it sends `0x34` using `first_up_table`.

Therefore:

```text
POV path without IRQ2
-> first_up_table not derived
-> existing 0x34 release body has no proven table
```

Rocky learns its `fdt_up_base` on IRQ2 as well, but after any successful image it sends `0x34` with whatever `fdt_up_base` is currently held. That may be zero or stale on a true cold POV path. This is not sufficient safety evidence for our production implementation.

D249 explicitly left FDT disarm/restore unclosed.

Additional reasons not to send D2 yet:

- no target-live `POV=true` occurrence is currently preserved;
- no target-live D2 occurrence is currently established;
- Rockytkg's post-D2 300 ms sleep is unproven for this target;
- TLS reconnect behavior in Rocky remains an intentional local divergence and must not be imported.

## Recommended next boundary — D300/01

A single **read-only pre-capture AF query**, and nothing else.

Insert a second `AF/GetMcuState` after the third baseline succeeds and immediately before `FIRST_ARM`.

Requirements:

```text
new D2 submits = 0
new retries = 0
threshold changes = 0
timing sleeps = 0
reset/reopen/reconnect = 0
persistent writes = 0
```

Record only sanitized state:

```text
precap_af_count
precap_af_response_count
precap_state_byte0
precap_flags
precap_pov
precap_tls_connected
precap_locked
precap_unknown_flags
```

Semantics:

```text
AE malformed or TLS-connected=0 -> fail closed
POV=0 -> continue existing FIRST_ARM path unchanged
POV=1 -> record it; do NOT send D2 in D300/01
```

For a diagnostic run, POV=1 may terminate intentionally after telemetry rather than entering an unproven POV capture path.

## Decision matrix

### Outcome A

```text
immediate finger
precap_pov=1
```

This provides direct target evidence that the missing pre-capture state branch explains the D299 race.

Next work: design the POV capture/release lifecycle offline, with the release/up-table problem explicitly solved before any D2 live action.

### Outcome B

```text
immediate finger
precap_pov=0
FIRST_IRQ2 timeout/cancel persists
```

The POV hypothesis is falsified for the observed failure. Investigation returns to FDT arming semantics / already-present contact handling without D2.

## Current verdict

```text
D299_H1=CONFIRMED
PRECAPTURE_STATE_QUERY_SEMANTICS=STRONGLY_SUPPORTED_BY_OEM_WINDOWS_AND_ROCKY
POV_PATH_EXISTS=SUPPORTED_BY_OEM_REVERSE_ENGINEERING_AND_ROCKY
TARGET_POV_TRUE_OCCURRENCE=NOT_YET_PROVEN
TARGET_D2_OCCURRENCE=NOT_YET_PROVEN
POV_RELEASE_UP_TABLE_SEMANTICS=UNRESOLVED
FULL_D2_IMPLEMENTATION_AUTHORIZED=false
D300_01_READ_ONLY_PRECAPTURE_AF=RECOMMENDED_NEXT_BOUNDARY
```
