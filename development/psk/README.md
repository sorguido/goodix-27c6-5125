# Goodix 27c6:5125 — Live-qualified single-write PSK PoC

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
- exact live pairing-F baseline (`BB010002` and `BB020003`)
- qualified WB self-test
- exact local OEM-shaped `E0` frame validation
- explicit `--commit` plus confirmation phrase
- one logical `E0` maximum, with no retry

After the write it requires:
- exact OEM ACK and qualified `E0`/`E2` result
- unchanged `BB010002`
- `BB020003 == SHA256(BB010003)`
- immediate TLS 1.2 PSK handshake using `PSK-AES128-GCM-SHA256`

Each outbound TLS `B0` record is followed by a 10 ms processing interval. This
matches the qualified reference implementation and the inter-record interval
observed in the Windows OEM capture; sending the ServerHello flight records
back-to-back caused the target to stop before ClientKeyExchange. With the 10 ms
interval, the target completed ClientKeyExchange, ChangeCipherSpec and Finished,
and the writer verified TLS 1.2 with `PSK-AES128-GCM-SHA256`.

The generated PSK is never printed and never persisted.

Preflight reads both pairing fields before evaluating the exact baseline, so a
baseline mismatch still produces complete read-only evidence while remaining
fail-closed before PSK generation or any `E0` path.

The pinned pre-write gate used for live qualification was pairing F, established
by Windows A recovery:

```text
BB010002 SHA256 = d33c4758d7c44ab4f8fab210b5cb8b62382ee18cf93c9382ee1b9a4bd3c3856a
BB020003        = f7dee3d7050c4e08aab9dbb6964dc85d5ec6ba6a8636c7152caf3f5ac5cdb688
```

That baseline was consumed by the successful single-write experiment. The
generated PSK was deliberately not persisted, and Windows A subsequently
recognized the reader normally through the already-qualified recovery path.
Pairing F is retained only as provenance for the qualified attempt and must no
longer be treated as an authorized live pre-write baseline; commit mode must
not be rerun.

The qualified terminal result was:

```text
E0_RESPONSE_CONTROL=0xE0
E0_RESPONSE_CODE=0x03
POSTWRITE_BB010002_UNCHANGED=PASS
POSTWRITE_BB020003_MATCH=PASS
TLS_PROTOCOL=TLSv1.2
TLS_CIPHER=PSK-AES128-GCM-SHA256
TERMINAL_RESULT=WRITE_VERIFIED
E0_LOGICAL_WRITE_COUNT=1
```
