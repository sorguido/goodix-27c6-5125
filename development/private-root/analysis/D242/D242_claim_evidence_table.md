# D242 — initial claim/evidence table

| CLAIM | EVIDENCE | EVIDENCE_CLASS | STILL_OPEN? |
| --- | --- | --- | --- |
| D241 reached D1 and handed the first B0 to TLS exactly once | `D241_operator_live_stdout.json`: 12 commands, one USB open, handoff count 1, ClientHello trace row | OBSERVED_LIVE_D241 | no |
| D241 ClientHello was a complete TLS 1.2 ClientHello | trace: version `0x0303`, payload 47, handshake type ClientHello | OBSERVED_LIVE_D241 | no |
| D241 emitted ServerHello and ServerHelloDone | live trace: payloads 81 and 4 | OBSERVED_LIVE_D241 | no |
| D241 completed the cryptographic handshake | no ClientKeyExchange before bounded timeout | OBSERVED_LIVE_D241 | yes: false for D241 |
| D241 exercised the PSK cryptographically at peer Finished | object binding is true, but no ClientKeyExchange/Finished occurred | OBSERVED_LIVE_D241 | yes |
| D241 physically completed its requested server-flight OUT transfers | timeout is reached only after both `write_frame()` calls return; short/error paths terminate with a different class | STRONG_INFERENCE from live terminal plus reviewed control flow | no for requested lengths; no per-transfer D241 counter exists |
| D241 continued bulk-IN polling after the server flight | `tls_handshake()` calls `read_frame()` in the loop; the live terminal is its `UsbTimeout` mapping | STRONG_INFERENCE from live terminal plus reviewed control flow | no |
| D175 historical TLS metadata and timing are locally measurable | sole capture SHA-256 `50071c0f…19c184b`, packets 117–125 | VERIFIED_PRIMARY_CAPTURE | no |
| D43 packet-level metadata is locally measurable | no D43 capture or step-local primary artifact exists in this checkout/history | UNKNOWN | yes; NOT_ASSESSABLE |
| D241 and Windows used identical USB OUT segmentation | D175 uses fixed 64-byte submissions; D241 code requested short final chunks | VERIFIED_PRIMARY_CAPTURE + VERIFIED_STATIC_WINDOWS | no: mismatch proven |
| D241 and Windows used identical inter-record pacing | D175 gap 21.933 ms; Windows callback calls `Sleep(10)`; D241 had no pacing | VERIFIED_PRIMARY_CAPTURE + VERIFIED_STATIC_WINDOWS | no: mismatch proven |
| Fixed-64 is a common A0/B0 transport contract | all 56 D175 bulk OUT submissions are 64 bytes; known A0 command-send and B0 paths pass `r8b=0x40` to the length-driven USB helper | VERIFIED_PRIMARY_CAPTURE + VERIFIED_STATIC_WINDOWS | no; common scope verified |
| D242 closure behavior can change through unpinned D241 code | recursive import audit finds only `d241_operator_dry_run.py` and `d241_preflight.py`; both canonical hashes are pinned before import | VERIFIED_STATIC_DEPENDENCY_GATE | no; unpinned count 0 |
| Corrected transport causes the real device to send ClientKeyExchange | no D242 live execution is authorized or performed | UNKNOWN | yes; requires separately authorized single shot |
