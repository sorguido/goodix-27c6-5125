# D241 — D1 direct-B0 TLS transition

Date: 2026-08-16

## Result

```text
D241_RESULT=D241_OPERATOR_READY_FOR_ONE_LIVE_TLS_ATTEMPT
D241_FAILURE_CLASS=none
D241_EXECUTABLE_CLOSURE_GATE=PASS
D241_D1_DIRECT_B0_HANDOFF=EXACTLY_ONCE
D241_PSK_BINDING=SAME_E4_VALIDATED_SECRET_OBJECT_USED_BY_TLS
D241_D4_COUNT=0
D241_APPLICATION_DATA_COUNT=0
D241_PERSISTENT_WRITE_FAMILY_COUNT=0
D241_RETRY_COUNT=0
D241_MARKER_NAMESPACE=/var/lib/goodix-5125-poc/d241-operator-invocation.marker
D241_SEAL_COHERENCE=PASS
D241_TLS_HANDSHAKE_TIMEOUT_POLICY=BOUNDED_3000MS_NO_RETRY
D241_TLS_TRACE_REDACTED=true
D241_MANUAL_UPDATED=true
```

This is an offline technical delivery and operator-readiness classification.
D241 did not access the sensor and is not new live roadmap evidence.

## Causal map and root cause boundary

```text
D1 send
→ ProductionUsbTransport.read_frame reassembles and consumes the first B0
→ ProductionReplayBackend.exchange returns the already-read frame
→ _validate_responses parses B0 and validates the ClientHello
→ D239 terminates here as unexpected_data
→ TLS bridge is never entered and same_validated_psk_used_by_tls remains false
```

The D239 protocol observation proves that the Goodix B0 wrapper parsed and had
a 52-byte body. The locally available artifacts do not contain those 52 bytes,
so the exact failing ClientHello predicate cannot be recovered. The old code
required TLS record version `0x0303` and an offered-suite list containing
exactly `0x00a8`; D241 proves that an interoperable legacy record version or a
list containing `0x00a8` together with SCSV/other suites was rejected before
OpenSSL. D241 accepts record-layer versions `0x0301`–`0x0303` and requires
`0x00a8` in a structurally valid suite list. The server remains restricted to
`0x00a8`; TLS 1.2 body version, lengths, wrapper and ClientHello checks remain.

Epistemic classification:

```text
D239_FIRST_B0_TLS_BYTES_NOT_LOCALLY_AVAILABLE
```

It is therefore not claimed that the D239 record used `0x0301`, nor is the
52-byte body promoted to a confirmed ClientHello.

## B0/TLS contract and ownership

- USB completion fragments are accumulated by `ProductionUsbTransport` until
  the complete Goodix frame length is available.
- `read_frame()` verifies A0/B0 magic, outer length and header tag and returns a
  full B0 frame.
- `parse_b0()` verifies the wrapper and returns only its TLS payload.
- `B0TlsBridge.accept_b0()` receives a full B0 frame, parses it once and feeds
  only the TLS bytes to `ssl.MemoryBIO`.
- D241 stores the D1 frame in `_pending_first_b0`. `tls_handshake()` verifies
  that its payload is the record validated by the core, removes the pending
  frame before feed, and calls the bridge with `first_record=True` once.
- A consumed pending frame cannot be reread, rebuilt, duplicated or fed twice.
  B0 remains authorized only at the D1→TLS transition.

No second parser or alternate framing contract was introduced.

## PSK provenance

```text
protected G5125POC record
→ one SecretBuffer
→ RuntimePskE4Binder derives validator from that buffer
→ constant-time E4 MATCH
→ ProductionReplayBackend retains the same object
→ tls_handshake requires `secret is self.secret`
→ tls_factory receives that same object
→ Tls12PskServer copies it into its zeroized owned buffer
```

The report boolean now additionally requires the backend's object-identity
check. T6 captures the actual object received by the TLS factory; it does not
test a report flag in isolation.

## Timeout and redacted observability

The handshake owns one monotonic 3000 ms deadline. Every later USB read and
every B0 write receives only the remaining budget. Expiry is terminal, does not
retry, and produces one of:

```text
TLS_HANDSHAKE_TIMEOUT_BEFORE_FIRST_TLS_RECORD
TLS_HANDSHAKE_TIMEOUT_AFTER_CLIENTHELLO
TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT
TLS_HANDSHAKE_TIMEOUT_STATE_UNRESOLVED
```

`AFTER_CLIENTHELLO` is used only after the first record passed the complete
ClientHello validator. Trace rows contain record index, direction, observed
content type/version/length, state before/after, alerts when plaintext and a
handshake type only when a complete plaintext handshake header was verified.
They contain no record payload, PSK, key schedule, nonce, IV or key log.

## Operator kit

`operator_kit/d241-live-tls-once.sh` is source-sealed and accepts exactly one
live authorization argument. It uses only the D241 marker namespace. Historical
D236/D238/D239 markers are reported as benign and are never deleted. In the
authorized root branch the launcher creates the D241 result directory with
`install -d -m 0700 -o root -g root` before the read-only sensor preflight,
which then revalidates type, owner, mode, non-symlink state and writability.

The launcher prints `D241_PHASE`, `D241_RESULT` and `D241_FAILURE_CLASS` for
preflight and live terminals. It applies one hash-pinned unseal patch, invokes
the entrypoint once, and reseals from byte-exact backups on success, failure or
signal. It never invokes D4 or an application-data API.

## Executable closure

The real launcher `--offline-dry-run` traverses:

```text
launcher and hash gates
→ real imports and production paths
→ sandbox report directory lifecycle
→ historical/current marker regression
→ sealed baseline and unseal patch apply
→ real entrypoint composition
→ direct B0 fragmented across USB completions
→ bridge handoff and success fixture
→ server-flight timeout fixture
→ redacted checkpoint/final reports
→ USB release/close and secret zeroization
→ patch rollback and byte-exact reseal
```

No root access, `/var/lib` write, libusb system API, real secret or sensor is
used by this mode.

## Test mapping

| Requirement | Evidence |
| --- | --- |
| T1 direct B0 | pass, exact payload and handoff count 1 |
| T2 USB fragmentation | pass, identical stream and one handoff |
| T3 no double consumption | pass, one feed and no extra bulk IN |
| T4 malformed fail-closed | pass for wrapper tag, TLS length and content type |
| T5 unrelated data | pass, A0 data after D1 rejected |
| T6 PSK provenance | pass, captured object identity after binder MATCH |
| T7 forbidden operations | pass, no D4/application/persistent write/retry path |
| T8 cleanup/zeroization | pass on success and timeout |
| T9 result directory | pass in sandbox; launcher command statically verified |
| T10 marker namespace | pass for historical-present/current-absent and consumed D241 |
| T11 seal coherence | pass for hashes, apply, reverse and final hashes |
| T12 timeout/trace | pass after ClientHello and after server flight; redaction checked |

The closure success fixture completes both sides of a real OpenSSL TLS 1.2 PSK
handshake through B0, including a generated legacy-version, multi-suite
ClientHello. No dependency was added.

## Scope invariants

```text
D4_count=0
application_data_count=0
persistent_write_family_count=0
retry_count=0
live_USB_execution=NOT_PERFORMED
```

D240 is `SUPERSEDED / DO_NOT_EXECUTE / NOT_EXECUTED`.
