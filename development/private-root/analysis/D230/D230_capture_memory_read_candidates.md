# D230 capture memory-read candidates

## Result

The one recovered target capture contains 52 host framed requests: 48 A0 and
four B0/TLS.  The A0 requests use 20 distinct wire control values.  No request
has a structurally valid `LE32 MCU address + length` layout, incrementing flash
addresses, a page/block walk, or a following IN response proportional to a
caller-selected memory length.

The operator-designated first capture is definitively lost.  It is not silently
replaced by historical summaries and is not counted as inventoried.  The sole
packet-level source is `rilevamento.pcapng`, SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.

## Structural search

Every A0 inner body was scanned at every byte offset for little-endian values in
`0x08000000..0x080fffff`, then candidates were reviewed as fields rather than
accepted on byte coincidence.  Three windows occur in the 224-byte `0x90`
DEVICE_CONFIG body:

- inner offset 176: `0x08012a1d`;
- inner offset 200: `0x08012a58`;
- inner offset 204: `0x08005200`.

They are adjacent bytes inside one fixed configuration download.  They do not
occur at a command field boundary, are not paired with a requested output
length, do not increment across requests, and are followed by a typed status
rather than a proportional data return.  The target APP receiver for family 9
classifies `0x90` as config application, consistent with the host builder
`gf_download_config` at `0x180067328`.  These are false positives, not read
addresses.

## Cold-start coverage

The recovered capture includes the complete observed pre-D1 order:
`E4 → A2 → 82 → A6 → A2 → 70 → 80×4 → 90 → D1 → B0`.
It also contains enumeration queries and later normal-session operations.  This
makes it strong evidence for the available normal workflow, while the lost
capture prevents a claim of two-capture packet-level replication.

## Falsifier

A provenance-valid recovered/new target capture containing a previously unseen
opcode or an address/length request would reopen this result.  Aggregate legacy
claims about a second capture are not used to exclude that falsifier.
