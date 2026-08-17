# D238 state-machine and evidence audit

## Repository state before D238

`git status --short` showed the D230–D237 working corpus, sources, tests, manual
and prior bundles as untracked relative to the small public Git history. D238
therefore did not treat `HEAD` as the intended post-live source. The current
files were reconciled against D236 patches and inventories.

- `goodix5125_d233_backend.py` had `_d233_usb_source_seal()` restored.
- `goodix5125_d235_entrypoint.py` had `_d235_source_seal()`, authorization `no`
  and risk acceptance `not_granted`; the safe nonzero exit-code correction was
  retained.
- The canonical E4 correction accepted ACK status `0x07` only for E4.
- The A2 diagnostic modification was not present in source; its source was
  resealed and only redacted run artifacts remained.
- No root-owned `__pycache__` or `.pyc` existed. User-owned caches existed under
  `analysis/D230/tools`, `analysis/D236`, `poc`, `src` and `tests`; none was
  modified as part of the protocol decision.

## Primary ACK lifecycle

The existing D230 offline parser output and the primary recovered capture were
used; no new capture parser was written. The capture hash is
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
Packets 53–117 establish the exact pre-D1 logical sequence and status `0x01`
for all ACK-bearing controls. Typed responses follow E4, both A2 commands,
`0x82`, A6 and `0x90`; `0x70` and `0x80` are ACK-only; D1 transitions directly
to B0/TLS.

D236 run 1 proves E4 status `0x07` and, more importantly, the non-circular
runtime binding `real G5125POC record -> recovered OEM reference -> validator ==
live E4 validator`. Run 2 proves the first A2 was transmitted after `E4_MATCH`.
The deliberately truncated run 3 preserves the first A2 IN frame as
`A0/B0`, echo `A2`, status `0x07`, body length 2.

The same session value is stable across two different controls in D236, while
`0x01` is stable across all controls in the recovered OEM session. D238 models
`0x01` and `0x07` as the two evidenced successful transport/session ACK values,
listed explicitly for every ACK-bearing phase. This does not admit arbitrary
odd values or reinterpret ACK as an application response. All other statuses,
wrong echoes, malformed A0, extra frames, wrong order and wrong typed bodies
remain terminal.

Historical D43, D178 and D226 step-local artifacts named by the prompt were not
present anywhere in the current repository or its Git history. The first
capture is also canonically documented as lost. D238 records those cells as
unavailable instead of manufacturing evidence. D175 corresponds to the
surviving recovered-capture lineage and is grounded here in the primary pcapng.

## Consolidated policy implementation

`PHASE_RESPONSE_POLICIES` replaces the opcode-local exception in `_expect_ack`.
Each row pins request control, allowed ACK values and one of:

- `ack_then_typed` — exactly two A0 frames, ACK first, same-control typed result;
- `ack_only` — exactly one correlated B0-control A0 ACK;
- `b0_tls_client_hello` — exactly one B0 frame after D1.

USB completion boundaries are not logical protocol boundaries. The production
transport now records which bulk completion(s) supplied each exact frame. Two
exact framed A0 messages can be separated or coalesced, but no combined body or
additional response shape is accepted. Asynchronous/unrelated A0 frames fail
the expected count/control/order checks.

The production report adds only redacted `protocol_observations`: phase,
request control, first wrapper/control, ACK echo/status/body length, response
control/body length, ordering classification and completion classification.
It does not retain raw payloads, config90, PSK or biometric data.

## Runtime material

The production path remains pinned to:

- `transport-material.bin`: canonical 88-byte `G5125POC` record, SHA-256
  `eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75`;
- config90: 224 bytes, SHA-256
  `e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82`;
- manifest SHA-256
  `1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15`;
- canonical `gfusb.dll` SHA-256
  `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.

The loader checks the whole record before extracting bytes 24–55 into one
owned `SecretBuffer`, zeroizes the 88-byte temporary and later gives the same
validated `SecretBuffer` object to TLS. The E4 binder derives from the loaded
secret and hash-gated PE, so it is not circular.

## Preserved invariants

- exact order `E4/A2/82/A6/A2/70/80x4/90/D1/TLS/STOP`;
- one exchange per phase, no retry or automatic reset;
- ambiguous completion aborts;
- D4, application data, FDT, capture, enroll, E0/A4/F0/F4 unreachable;
- no automatic power-cycle or invasive recovery;
- checkpoint before restore, final report after restore;
- secret cleanup and source reseal remain mandatory.
