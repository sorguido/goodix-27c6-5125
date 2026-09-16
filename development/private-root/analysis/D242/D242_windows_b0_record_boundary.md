# D242 — Windows B0/TLS record boundary

For the D175 initial server flight the mapping is exactly:

| TLS record | B0 wrappers | B0 total | USB OUT submissions |
| --- | ---: | ---: | --- |
| ServerHello | 1 | 90 | 64 + 64 |
| ServerHelloDone | 1 | 13 | 64 |

The B0 header is four bytes: type `0xb0`, little-endian TLS-record length and
additive header tag `(0xb0 + lo + hi) & 0xff`. There is no trailing/body
checksum in this B0 contract. Padding exists outside the declared B0 object in
the 64-byte USB staging buffer and is ignored by the wrapper length. The D175
tail is not all zero; its content is redacted because only the fixed submission
length, not stale staging data, is part of the transport contract.

D241 already matched the one-record/one-B0 boundary but not the fixed USB
submission size. D242 changes only the latter and keeps OpenSSL record splitting
and B0 construction unchanged.
