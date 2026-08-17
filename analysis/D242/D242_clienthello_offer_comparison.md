# D242 — ClientHello offer comparison

The sole local primary capture is the file historically classified as D175,
SHA-256 `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
No D43 capture is present in the checkout or Git history; D43 is therefore
`NOT_ASSESSABLE`, not reconstructed from prose.

The D175 ClientHello is one B0 payload containing one complete TLS record:
record version `0x0303`, TLS payload 47, handshake length 43, client version
`0x0303`, empty session ID, suites `0x00a8` and `0x00ff`, null compression and
no extensions. D241 live independently verified record version `0x0303`, TLS
payload 47 and handshake type ClientHello. Its redacted trace did not retain
the remaining offer fields, so equality for those fields is not promoted to a
live observation.

`D239 response_body_length=52` is produced by
`_redacted_protocol_observation()` as `len(parse_b0(frame))`: it is the whole
TLS record. `D241 record_length=47` is produced by `_redacted_tls_record()` from
the TLS header's payload-length field. Therefore `52 = 5-byte TLS record header
+ 47-byte TLS record payload` and the classification is:

```text
D239_52_EQUALS_TLS_HEADER_PLUS_D241_47_CONFIRMED
```

No raw record, random, or session value is retained here.

