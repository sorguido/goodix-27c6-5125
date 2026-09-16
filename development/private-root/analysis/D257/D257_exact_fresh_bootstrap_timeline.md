# D257 exact target fresh-bootstrap timeline

Raw D255 SHA-256 gate: `802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`.

The full logical-frame census derives the segment from the first fresh AF/AE pair through the ACK of the first subsequent `0x32`; it does not preselect only FDT commands.

```text
AF/AE fresh -> 0x36/ACK/IRQ100 -> 0x50/ACK/NAV -> 0x36/ACK/IRQ100
-> 0x82/ACK/response -> 0x20/ACK/B0 baseline -> 0x36/ACK/IRQ100 -> 0x32/ACK
```

Dynamic NAV/image bytes, OTP and FDT table bytes are redacted; request payloads and response structure/correlation remain audit-visible.

## Temporal provenance

- cache mtime: `2026-08-22T20:29:28.5244390Z` (not proven to be generation time)
- VM attach begin: `2026-08-22T20:56:34.7220147Z`
- first `0x36`: `2026-08-22T20:56:44.146639Z`
- mtime to attach: `1626.1975757` seconds
- mtime to first `0x36`: `1635.6222000` seconds

D255 therefore proves successful reuse of an OTP-bound, CRC-valid cache that pre-existed the attach by more than 27 minutes. It does not prove a general TTL.

## Inter-stage decision

`0x50`, inter-stage `0x82`, and `0x20` are observed and causal necessity is not excluded. They are required in the exact candidate. Their dynamic NAV/FDT-delta/baseline outputs feed host-side gates whose exact target predicates are not derivable from the D255 raw alone, so exact replay remains blocked rather than silently projecting them away.
