# Goodix 27c6:5125 — Offline-qualified single-write PSK PoC

This experimental tool is intentionally separate from the production driver.

Default execution is **preflight-only** and performs no persistent write.

## Offline response qualification

The response path is split into a pure incremental parser and the USB wrapper.
The parser requires a valid `B0` acknowledgement for `E0`, then accepts either
of the two narrowly qualified completion controls, `E0` or `E2`. The admitted
completion bodies are:

- `00 02`, observed in `WINDOWS_A_RETURN_AFTER_B.pcapng`;
- `00 03`, observed after the Linux `E0` attempt and followed by a proven
  `BB020003 == SHA256(BB010003)` readback.

`E0` was observed directly in both captures; `E2` remains supported because it
is documented by the pinned Rockytkg production-command layer. A completion
response only advances the writer to the independent readback and TLS gates;
it is not by itself reported as a verified persistent write.

It does not infer persistent success from a completed USB transfer. The writer
reports these stages independently:

```text
TRANSFER
PROTOCOL_RESPONSE
READBACK
HASH_VERIFY
TLS_VERIFY
TERMINAL_RESULT
```

Direct `E4` readback of `BB010003` is not a mandatory gate because that read
path is not qualified on this target. The post-write gates instead use the
unchanged `BB010002`, `BB020003 == SHA256(locally generated BB010003)`, and the
TLS proof with the in-memory PSK.

Run the offline suite without a sensor:

```text
make test
```

The suite covers literal captured `E0` responses with both admitted bodies,
synthetic `E2`, ACK handling, stream fragmentation/reassembly, timeout,
unexpected controls, malformed frames, duplicate/late results, one terminal
transition, and the no-retry guard.

The commit path is gated by:
- exact USB target `27c6:5125`
- exact firmware `GF_ST411SEC_APP_12509`
- exact live pairing-D baseline (`BB010002` and `BB020003`)
- qualified WB self-test
- exact local OEM-shaped `E0` frame validation
- explicit `--commit` plus confirmation phrase
- one logical `E0` maximum, with no retry

After the write it requires:
- exact OEM ACK and qualified `E0`/`E2` result
- unchanged `BB010002`
- `BB020003 == SHA256(BB010003)`
- immediate TLS 1.2 PSK handshake using `PSK-AES128-GCM-SHA256`

The generated PSK is never printed and never persisted.

The current pre-write gate is pairing D:

```text
BB010002 SHA256 = 7931b70b2b9eb0264546f0da4478ddaa499da8404e336b76a506ae01be5cfc66
BB020003        = 0dec75577b297e42bf9850367efda42be7c6e29dbd7787ffda71c14343d378b0
```

Do not run commit mode unless the live preflight has just passed and the operator
accepts the experimental persistent-write boundary.
