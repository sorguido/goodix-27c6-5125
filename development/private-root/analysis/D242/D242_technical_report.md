# D242 — OEM contract divergence correction

## Decision

```text
D242_RESULT=D242_OEM_CONTRACT_DIVERGENCES_PROVEN_AND_CORRECTED_OPERATOR_KIT_READY_NOT_EXECUTED
D242_PROVEN_DIVERGENCES=FIXED_64_BYTE_USB_OUT_MISMATCH_AND_TLS_RECORD_PACING_MISMATCH
D242_DEVICE_CAUSAL_SUFFICIENCY=NOT_YET_LIVE_VERIFIED
```

D241 reached the first live boundary after the server flight but did not use
the transport contract observed in the accepted Windows session. D242 proves
two concrete implementation divergences—fixed-size USB OUT submissions and
inter-record pacing—and corrects both offline. The corrected path has not been
executed against the sensor, so causal sufficiency at the device remains the
new live-unverified boundary. `PROVEN_DIVERGENCE` is not
`PROVEN_DEVICE_ROOT_CAUSE`.

## Scope and provenance

- D241 live evidence was validated from its final report, redacted TLS trace,
  pre-restore checkpoint and operator output.
- The only local primary capture is `rilevamento.pcapng`, SHA-256
  `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`,
  historically classified as D175.
- No D43 primary capture or packet-level derivative exists in the checkout or
  Git history. Every D43 cell is therefore `NOT_ASSESSABLE`.
- The canonical Windows binary is `gfusb.dll`, SHA-256
  `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
- No network, root store, real secret, sensor, sudo, live USB or live TLS was
  used during D242. Raw capture, TLS/B0 records, randoms, session values and key
  material are excluded from D242 artifacts and the bundle.
- The prior D242 bundle SHA-256
  `a112fe2be21a48ff84072194e38cf07bfdb0817b42c44de43bc01e858a56df20`
  is `SUPERSEDED_DO_NOT_USE_FOR_LIVE_AUTHORIZATION`: its technical differential
  and runtime fix are valuable, but provenance/closure/manual review failed.
- The intermediate review bundle SHA-256
  `df0f01b6fe78786eb22adf156f5d0c830d93a475e7a45f349635c5fb2843e60f`
  is
  `SUPERSEDED_BY_FINAL_OPERATOR_OBSERVABILITY_CORRECTION_DO_NOT_USE_FOR_LIVE_AUTHORIZATION`.
  The final archive is identified only by its external `.zip.sha256` sidecar;
  no archive attempts to contain its own digest.

The two behavior-relevant D241 dependencies were recursively enumerated and
are byte-exact, read-only and pinned before import:

| module_path | imported_directly_or_indirectly | behavior_relevant | sha256 | pinned |
| --- | --- | --- | --- | --- |
| `analysis/D241/d241_operator_dry_run.py` | directly by D242 closure | true | `0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f` | true |
| `analysis/D241/d241_preflight.py` | directly by D242 preflight; indirectly via D241 operator fixture | true | `6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7` | true |

```text
D242_D241_BEHAVIOR_RELEVANT_DEPENDENCY_COUNT=2
D242_D241_PINNED_DEPENDENCY_COUNT=2
D242_UNPINNED_CLOSURE_DEPENDENCY_COUNT=0
D241_PROVENANCE_MUTATION_COUNT=0
```

The fixed-64 synthetic compatibility adapter is D242-local; no D241 artifact
is changed.

The initial claim/evidence split is recorded in
`D242_claim_evidence_table.md`. The redacted primary derivation is reproducible
with `d242_capture_forensics.py`.

## D241 validation

The canonical D241 terminal is
`TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT`. Legacy fields such as
`decision=D236_ABORTED_USB_TRANSPORT` and
`backend_failure_domain=usb_transport` are nominal inheritance and do not
override the more specific live failure class.

```text
D241_LIVE_SINGLE_SHOT_COMPLETED=true
D241_CLIENT_HELLO_VERIFIED=true
D241_CLIENT_HELLO_RECORD_LENGTH=47
D241_SERVER_HELLO_SENT=true
D241_SERVER_HELLO_RECORD_LENGTH=81
D241_SERVER_HELLO_DONE_SENT=true
D241_SERVER_HELLO_DONE_RECORD_LENGTH=4
D241_CLIENT_KEY_EXCHANGE_OBSERVED=false
D241_TLS_CRYPTOGRAPHIC_HANDSHAKE_COMPLETED=false
D241_ERROR_CLASS=TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT
D241_D4_COUNT=0
D241_APPLICATION_DATA_COUNT=0
D241_PERSISTENT_WRITE_FAMILY_COUNT=0
D241_RETRY_COUNT=0
D241_SECRET_ZEROIZED=true
D241_FPRINTD_RESTORED=true
D241_SOURCE_RESEALED=true
D241_DO_NOT_RETRY=true
```

Control-flow review proves that this timeout is reachable only after both
server-flight `write_frame()` calls returned and at least one following bulk IN
was attempted. Libusb errors and short completions map to other terminal paths.
Thus D241 fully transmitted the lengths it requested; it did not reproduce the
OEM request sizes.

## Gate A — TLS metadata

D175 and D241 match on the server-flight structure available from the redacted
live trace: TLS 1.2 record version `0x0303`, ServerHello payload 81 followed by
ServerHelloDone payload 4, with the configured PSK suite `0x00a8`. The D175
ClientHello payload is 47, offers `0x00a8|0x00ff`, has an empty session ID and
no extensions. D175 then sends a ClientKeyExchange for the classified identity
`Client_identity`; D241 does not.

The D239/D241 length discrepancy is resolved from the producer functions:
D239 `response_body_length=52` is the complete record returned by
`parse_b0()`, while D241 `record_length=47` is the TLS header payload length.
The exact classification is
`D239_52_EQUALS_TLS_HEADER_PLUS_D241_47_CONFIRMED`.

## Gate B — B0 and USB transmission

D175 maps ServerHello and ServerHelloDone one-to-one into two B0 wrappers.
Their total sizes are 90 and 13; declared TLS lengths, actual lengths and B0
header tags are valid. Windows submits the first as `64|64` and the second as
`64`, all successfully completed. Captured bytes outside the declared final B0
length are nonzero but semantically outside the wrapper and remain redacted.

D241 preserved the same record/B0 grouping but requested `64|26` and `13`.
The reviewed Windows send path copies at most 64 meaningful bytes per staging
iteration while always passing length 64 to the USB routine. Therefore:

```text
GROUPING=TRANSPORT_MATCH_VERIFIED
BEFORE_FIX=USB_SEGMENTATION_DIVERGENCE_PROVEN
AFTER_FIX=TRANSPORT_MATCH_VERIFIED_OFFLINE
```

D242 now initializes a 64-byte staging chunk deterministically, copies the
meaningful suffix into it, submits exactly 64 bytes and requires a completion
of exactly 64. B0 declared length and checksum remain authoritative; a partial
completion is terminal and there is no retry.

The scope audit classifies the transport change as
`D242_FIXED64_SCOPE=OEM_COMMON_A0_B0_TRANSPORT_CONTRACT_VERIFIED`. All 56 bulk
OUT submissions in D175, covering A0 and B0 frames including continuations,
are 64 bytes. The already-known command-send call-sites at `0x18005d164` and
`0x18005d407`, as well as the B0 path, pass `r8b=0x40` to `0x18005a42c`, whose
caller-supplied length controls the submission. D242 does not reproduce stale
Windows tail bytes: it zero-initializes the non-semantic staging suffix.
Synthetic A0 regression proves that declared length, header/checksum,
ACK/response parsing and logical frame bytes remain unchanged while the USB
submission is 64 bytes. The live-verified pre-D1 semantics from D239/D241 are
therefore preserved rather than reopened.

## Gates C and D — pacing and Windows send path

D175 timing is 0.219 ms from ClientHello completion to first ServerHello byte,
21.933 ms from final ServerHello completion to first ServerHelloDone byte, and
13.338 ms from ServerHelloDone completion to first ClientKeyExchange byte.
Static Windows code at the existing TLS anchors maps one mbedTLS send callback
to one B0, submits fixed 64-byte blocks, then calls `Sleep(10)` in the ordinary
state. No intervening non-TLS ACK, state write or coalescing is observed.

D241 drained the two OpenSSL records and sent them back-to-back without a
pacing call. D242 adds one 10 ms pacing event after each emitted TLS record,
within the existing monotonic 3000 ms budget. The timeout is not increased:
D175's 13.338 ms response falsifies `H6_TIMEOUT_TOO_SHORT` for this boundary.

```text
BEFORE_FIX=D241_TOO_FAST_VS_WINDOWS_PROVEN
AFTER_FIX=PACING_MATCH_VERIFIED_OFFLINE
```

## Gate E — divergence matrix

The falsifiable matrix is in `D242_post_server_flight_hypotheses.csv`. H4 USB
segmentation mismatch and H5 inter-record pacing mismatch are `PROVEN` as
divergences, not as device-side causal sufficiency.
Structural, grouping, coalescing, wrapper, timeout, polling-stop, length-field
and incomplete-D241-transmission hypotheses are falsified by local evidence.
An unknown device rejection and a later OpenSSL fatal remain possible only at
the new boundary; D242 adds redacted submit/complete, receive, WANT/fatal and
pacing counters to discriminate them.

## Runtime correction and closure

The correction is deliberately narrow:

- fixed 64-byte bulk OUT staging and full-completion enforcement;
- 10 ms record pacing in `B0TlsBridge`;
- redacted server-flight transmission, post-flight receive and OpenSSL state
  counters;
- D242 marker/result namespace and a newly sealed single-use launcher.

First-B0 ownership, the identical E4-validated `SecretBuffer`, suite/version
policy, D4 exclusion, persistent-write exclusion, zero retry, bounded timeout,
cleanup, zeroization, fprintd restore and source reseal remain intact.

The complete test suite passes 104/104. The launcher-driven executable closure
gate passes with synthetic USB/TLS peers: two B0 records, three 64-byte OUTs,
two 10 ms pacing events, a post-flight timed-out bulk IN, no OpenSSL fatal, one
cleanup, zero D4/application/persistent-write/retry, no live I/O, and exact
unseal/reseal restoration. Details are in `D242_test_results.md` and
`D242_executable_closure_report.json`.

## Final operator-failure observability closure

The live preflight already writes a redacted structured report, but the former
launcher reduced every nonzero exit to `PREFLIGHT_FAILED`. The final D242
correction keeps that JSON authoritative and adds a small hash-pinned D242-local
renderer used by the same launcher. It emits only whitelisted diagnostics:
specific failure class, failure list, marker namespace and zero/live-not-started
counters. Missing JSON, invalid JSON/schema and renderer failure have distinct
fail-closed classifications.

The same launcher exposes an offline fixture-only rendering branch used by the
test suite. The synthetic failure proves a specific terminal cause is visible,
the generic-only classification is absent, sealed sources are byte-identical,
and there is no unseal, marker creation, USB open, Goodix command, real-secret
read or fprintd mutation. This branch exits before every live operation.

```text
D242_OPERATOR_FAILURE_OBSERVABILITY=PASS
D242_GENERIC_PREFLIGHT_FAILURE_ONLY=FORBIDDEN
D242_LIVE_USB_EXECUTION_DURING_CODEX=0
```

## New boundary

The repository is ready only for review of a separately authorized, human-run,
single-use D242 attempt. Such an attempt may perform the already verified
factory-preserving pre-D1 path, D1 once and the TLS handshake, then must stop
immediately before D4. D242 itself authorizes no run. Whether the corrected
server flight causes the real 12509 device to send ClientKeyExchange remains
unverified and must not be described as live advancement.

```text
D242_FINAL_REVIEW_CORRECTION=PASS
D242_PREVIOUS_SUPERSEDED_BUNDLE_SHA256=a112fe2be21a48ff84072194e38cf07bfdb0817b42c44de43bc01e858a56df20
D242_PREVIOUS_SUPERSEDED_BUNDLE_STATUS=SUPERSEDED_DO_NOT_USE_FOR_LIVE_AUTHORIZATION
D242_INTERMEDIATE_REVIEW_BUNDLE_SHA256=df0f01b6fe78786eb22adf156f5d0c830d93a475e7a45f349635c5fb2843e60f
D242_INTERMEDIATE_REVIEW_BUNDLE_STATUS=SUPERSEDED_BY_FINAL_OPERATOR_OBSERVABILITY_CORRECTION_DO_NOT_USE_FOR_LIVE_AUTHORIZATION
D242_OPERATOR_FAILURE_OBSERVABILITY=PASS
D242_GENERIC_PREFLIGHT_FAILURE_ONLY=FORBIDDEN
D242_D241_HISTORICAL_ARTIFACT_RESTORED=true
D242_D241_OPERATOR_DRY_RUN_SHA256=0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f
D242_D241_PREFLIGHT_SHA256=6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7
D242_D241_BEHAVIOR_RELEVANT_DEPENDENCY_COUNT=2
D242_D241_PINNED_DEPENDENCY_COUNT=2
D242_UNPINNED_CLOSURE_DEPENDENCY_COUNT=0
D242_FIXED64_SCOPE=OEM_COMMON_A0_B0_TRANSPORT_CONTRACT_VERIFIED
D242_PROVEN_DIVERGENCES=FIXED_64_BYTE_USB_OUT_MISMATCH_AND_TLS_RECORD_PACING_MISMATCH
D242_DEVICE_CAUSAL_SUFFICIENCY=NOT_YET_LIVE_VERIFIED
D242_RUNTIME_FIX_IMPLEMENTED=true
D242_OPERATOR_KIT_CREATED=true
D242_EXECUTABLE_CLOSURE_GATE=PASS
D242_MANUAL_UPDATED=true
D242_LIVE_USB_EXECUTION_DURING_CODEX=0
D242_REAL_TLS_HANDSHAKE_DURING_CODEX=0
D242_BUNDLE_PATH=analysis/D242/D242_post_server_flight_causal_differential_bundle.zip
D242_BUNDLE_SHA256=RECORDED_IN_EXTERNAL_ZIP_SHA256_SIDECAR
```
