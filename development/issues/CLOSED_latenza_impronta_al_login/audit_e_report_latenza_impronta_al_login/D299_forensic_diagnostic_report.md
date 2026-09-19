# D299 — Forensic diagnostic note: D293 → D298

## Scope

This note is diagnostic only. It proposes no functional protocol change.

Baselines compared:

- D293 installed baseline commit: `e61fce313794922a2dab156a1b38a8ddc5837f19`
- D298 candidate commit: `ed15eaa2a9625c30ce13b6a8e5524f5662853892`

The real MateBook has already rolled back successfully to D293.

## Key finding 1 — D293 is not a golden cold-boot implementation

D293 already:

- applies the fatal `classify_fdt_delta(1, 2)` check on the third FDT baseline sample;
- waits in `FIRST_IRQ2` for an explicit `0x32 / IRQ 0x0002` finger-down event;
- only after that event submits the `0x22` image command.

Therefore D297–D298 did not introduce the underlying cold-contact timing dependency. They made parts of it observable and added bounded recovery.

D293 remains useful as the known-good *stabilized/warm* path because it demonstrably reaches image + matcher on this hardware.

## Key finding 2 — the three D298 live actions split into two failure classes

### Action A — baseline never stabilizes

Observed:

```text
capture_entry=0
fdt_irq100_3_reason=DELTA_OUTSIDE_THRESHOLD
fdt_delta_recovery=2
fdt_delta_recovery_exhausted=1
first_image=0
rejected_a0_phase=FDT_IRQ100_3
control=0x36
irq=0x0100
flags=0x003f
```

D298 performed exactly two bounded extra re-samples and then failed closed.

Still unknown:

- negotiated threshold value;
- maximum absolute channel delta on each of the three third-sample attempts;
- number of six FDT channels above threshold.

Without those values we cannot distinguish marginal cold noise from a fundamentally different/contact-disturbed baseline.

### Actions B/C — bootstrap completes, but image command is probably never sent

Observed twice:

```text
capture_entry=1
post_tls_invalid_frame=0
rejected_a0=0
first_image=0
post_tls_ack_consumed=8
```

One also has:

```text
post_tls_reverse_irq80_consumed=1
```

This is highly diagnostic.

The ordinary successful pre-image sequence consumes eight ACKs through the ACK of `FIRST_ARM`.

The image command `0x22` is submitted only after a valid `FIRST_IRQ2 / IRQ 0x0002`; its ACK would be the ninth.

Therefore:

```text
ack_consumed=8
+ first_image=0
+ invalid_frame=0
```

strongly suggests:

```text
third baseline PASS
→ FIRST_ARM submitted
→ FIRST_ARM ACK consumed
→ phase FIRST_IRQ2
→ no accepted fresh IRQ 0x0002
→ no 0x22 image command
→ framework/deactivation teardown
```

The reverse `0x0080` observed in one action is also consistent with waiting in an FDT phase.

This matches the original empirical A/B:

```text
finger immediately after authentication starts -> unreliable
wait ~2 seconds before touching                 -> works
```

Most likely race:

> the finger is already physically present before `FIRST_ARM` begins waiting for a *new* finger-down transition, so no fresh IRQ `0x0002` is emitted after arming.

Important: `capture_entry=1` does **not** mean a finger-down was observed. D298 increments it after the third baseline passes, before `submit_arm(FIRST_ARM)`.

## Key finding 3 — why baseline touch flags alone cannot close the early-contact race

D297/02 correctly established that manual baseline IRQ `0x0100` may contain known touch bits up to `0x003f`.

Accepting those bits as metadata may be correct for parsing the manual sample, but it does not solve the lifecycle consequence of a finger already present:

- contact may already exist while baseline is sampled; or
- it may begin between the last baseline sample and `FIRST_ARM`; and
- once `FIRST_IRQ2` is waiting, the device may not produce a new down edge for an already-present contact.

This is still a hypothesis and must be measured before any functional correction.

## Instrumentation required

No raw FDT arrays, image data, biometric data, PSK, TLS plaintext, or secret data are logged.

### Hole A — third delta

Add only sanitized metrics:

```text
fdt_threshold
delta3_attempts
delta3_max1
delta3_max2
delta3_max3
delta3_over1
delta3_over2
delta3_over3
```

Definitions:

- `delta3_maxN`: maximum absolute difference across the six FDT channels;
- `delta3_overN`: number of six channels above the existing threshold.

Threshold and decision remain unchanged.

### Hole B — capture_entry=1 / first_image=0

Expose existing audit counters:

```text
first_irq2
first_cmd22
first_b0
first_decode
first_pipeline
```

Also expose existing transport counters:

```text
tls_plaintext
usb_out_submit
usb_in_complete
usb_out_complete
```

Add only:

```text
cancel_count
cancel_phase
```

`cancel_phase` records the lifecycle phase immediately before the existing cancellation turns the lifecycle terminal.

## Expected diagnostic outcomes

### H1 — early finger missed by arm

```text
capture_entry=1
first_irq2=0
first_cmd22=0
cancel_phase=FIRST_IRQ2
first_pipeline=0
```

This would strongly confirm the race.

### H2 — image command sent but image never returned

```text
first_irq2=1
first_cmd22=1
first_b0=0
cancel_phase=FIRST_B0
```

Investigation then moves to USB/TLS receive after `0x22`.

### H3 — TLS plaintext arrives but image path stops later

```text
first_cmd22=1
tls_plaintext increases
first_b0 / first_decode distinguish the stopping point
```

### Baseline interpretation examples

```text
threshold=8 delta3_max=9 over=1
```

suggests a marginal threshold miss.

```text
threshold=8 delta3_max=150 over=5
```

suggests a substantially different/unsettled/contact-disturbed state.

No threshold or retry change is justified before these measurements.

## Safety invariant for D299 diagnostic

The diagnostic delta MUST NOT:

- add sleeps;
- add retries;
- change thresholds;
- accept new IRQs;
- alter frame classification;
- send new protocol commands;
- reset/reopen/reconnect;
- write persistent sensor state.

It changes telemetry only.

## Recommended single live diagnostic campaign

After host build/tests and review:

1. start from D293 active;
2. install the diagnostic D298-derived runtime;
3. reboot once;
4. initiate fingerprint and touch immediately;
5. at most three physical attempts, only as required to capture the failure;
6. collect only `GOODIX_PRODUCTION_EPOCH_AUDIT` and `GOODIX_D299_FORENSIC_AUDIT`;
7. rollback immediately to D293.

No exploratory retry loop.
