# D233 TLS 1.2 PSK and B0 bridge

`Tls12PskServer` is a real OpenSSL-backed server using Python 3.14
`ssl.MemoryBIO`. Both protocol bounds are TLS 1.2; the pre-1.3 cipher list is
restricted to `PSK-AES128-GCM-SHA256` (IANA `0x00a8`); the callback accepts only
`Client_identity`; tickets are disabled. There is no certificate, alternate
PSK, generated PSK, key log, downgrade, resumption or application-data method.

`B0TlsBridge` parses each Goodix B0 frame and feeds its payload to the input
BIO, so a TLS record may arrive across multiple B0 payloads. It drains the
output BIO, parses complete TLS records and sends each in its own B0 frame.
Partial USB reads/writes remain transport concerns: partial IN is accumulated;
partial OUT is an ambiguous terminal failure. Each pump consumes new input or
emits output, and the enclosing loop blocks on USB with a monotonic deadline,
so there is no busy loop.

The engine checks the negotiated version/cipher, permits one handshake, exposes
no post-handshake application-data path, and zeroizes its mutable PSK copy on
close. The authoritative `SecretBuffer` is independently zeroized by the
shared replay core. OpenSSL necessarily owns internal key schedule state during
the SSL object's lifetime; no claim is made about bytes managed internally by
the system library.

Offline tests complete a real server/client `0x00a8` loopback handshake with
7-byte fragmented input, cover multiple output records, wrong identity, wrong
suite, TLS-version mismatch, alert, malformed record, corrupted encrypted
Finished/Bad Record MAC and second-handshake rejection. No socket or device is
used.
