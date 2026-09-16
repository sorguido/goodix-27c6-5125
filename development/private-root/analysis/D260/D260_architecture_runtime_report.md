# D260 — Persistent runtime architecture readiness

## Outcome

`READY` for architecture review only. D260 implements and exercises one
continuous GPL runtime object offline:

```text
D1/B0 TLS handshake
-> retained TLS engine
-> D4 A0 plaintext
-> AF/AE A0
-> 36,50,36,82,20,36,32
-> baseline B0 consumed by the same TLS engine before stage2
-> final cleanup
```

`READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW=true`.
`READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=false`, the legacy unqualified
`READY_FOR_FDT_LIVE_REVIEW=false`, and `READY_FOR_FDT_LIVE=false`.

## Implemented boundary

- `core/tls_b0.py` retains one TLS 1.2 PSK server through the explicit
  `CREATED -> HANDSHAKING -> ESTABLISHED -> APPLICATION_ACTIVE -> CLOSED`
  lifecycle and bridges one TLS record per Goodix B0 wrapper.
- `core/runtime_transport.py` separates logical framing, physical submission
  policy, asynchronous events, and the validated-secret interface.
- `core/persistent_runtime.py` owns one simulated transport session, one
  synthetic secret handoff, one TLS server/handshake, mixed A0/B0 routing, and
  the D259 exact minimal FDT state machine.
- `core/fdt_lifecycle.py` now optionally obtains each IRQ100 from a separate
  `EventSource` after the corresponding ACK.

The historical D245/D246/D251 runtime, launchers, and live evidence remain
byte-identical. No `src/` file was modified.

## Verified contracts

- D4 is the canonical 10-byte A0 frame, submitted exactly once under a
  fixed-64 zero-tail policy after 20 ms with a 200 ms timeout. Its TLS
  application-record count is zero.
- Server-flight B0 uses fixed-64 staging and 10 ms record pacing metadata.
- AF is plaintext A0 and is sent exactly once without retry.
- Three ACKs and three IRQ100/touch0/raw12 events use separate interfaces and
  occur once per stage.
- The exact FDT trace is `36,50,36,82,20,36,32`.
- The B0 following `0x20` is authenticated/decrypted through the same retained
  TLS session before stage2. The mutable synthetic plaintext copy is wiped
  best-effort; OpenSSL internal and immutable Python copies are not claimed
  zeroized.
- Both native delta predicates pass; classifier, raster decode, host cache
  write, retry, A2/`0x70` recovery, and persistent-device-write counts are zero.

## Failure containment

All 15 required failures are terminal: malformed handshake B0, TLS bad MAC,
TLS timeout, wrong D4 ACK, malformed AF/AE, invalid seed, first-`0x36` timeout,
missing/wrong IRQ100, malformed NAV, first delta reject, baseline B0 auth
failure, delayed B0, second delta reject, and final `0x32` ACK failure. Each
has zero retry/cache/device write/special recovery, one TLS close, and one
transport cleanup.

## Deliberately unresolved operational axes

The physical submission status is
`ABSTRACT_OFFLINE_FOR_FDT_A0_WITH_EXACT_D4_AND_B0_TLS_POLICIES`. D260 does not
invent bytes outside the declared FDT A0 length. A separate operational review
must still address the real USB adapter, FDT A0 physical policy, privilege
model, real E4-validated secret binding, fprintd stop/restore, single-use
marker, approved live baseline, operator kit, and explicit authorization.

## Safety

Execution was offline only: real USB opens, target TLS handshakes, captures,
hardware actions, real command sends, finger interactions, host cache writes,
and persistent-write-family operations were all zero. No real secret,
biometric plaintext, raw capture, firmware, DLL, or OEM material is included.

