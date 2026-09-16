# D242 — server-flight structural comparison

## Result

```text
D242_SERVER_FLIGHT_STRUCTURAL_MATCH=VERIFIED
```

D175 contains a ServerHello TLS record with version `0x0303`, payload length
81, handshake length 77, TLS 1.2 server version, new 32-byte session-ID length,
selected suite `0x00a8`, null compression and only `renegotiation_info`
(`0xff01`, length 1). It is followed by one ServerHelloDone record with TLS
payload length 4 and handshake length 0. ServerKeyExchange is absent.

D241 live recorded the same record version, message order and payload lengths
81/4. The reviewed OpenSSL configuration is TLS 1.2 only, suite `0x00a8`, no
tickets/resumption, and its offline canonical fixture reproduces the remaining
metadata. Values deliberately redacted from the live trace—random and session
ID value—are neither compared nor published.

The structural TLS flight is therefore not the D241 divergence. The proven
differences are below TLS: fixed-size USB submissions and pacing.

