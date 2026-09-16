# D242 — pacing conclusion

```text
BEFORE_FIX=D241_TOO_FAST_VS_WINDOWS_PROVEN
AFTER_FIX=PACING_MATCH_VERIFIED_OFFLINE
TIMEOUT_HYPOTHESIS=FALSIFIED
```

The D175 ClientHello-to-ServerHello interval is 0.219 ms. ServerHello and
ServerHelloDone are separate B0/USB emissions; from completion of the final
ServerHello OUT to the first ServerHelloDone OUT the measured gap is 21.933 ms.
The ClientKeyExchange begins 13.338 ms after completion of ServerHelloDone.

The Windows TLS send callback ends each record emission with imported
`Sleep`: 10 ms in the observed ordinary state and 60 ms only in alternate
states. D241 drained both OpenSSL records in one loop and wrote them without an
explicit gap. D242 adds the evidenced ordinary 10 ms pacing after each emitted
TLS record, charged to the existing 3000 ms monotonic deadline.

The 3000 ms timeout is more than two orders of magnitude above the D175
post-flight response and is not increased. Rockytkg is not used as proof.

