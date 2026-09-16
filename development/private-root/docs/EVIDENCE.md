# Evidence index

This index records the load-bearing claims in the public manual. Proprietary or
private sources are identified but not redistributed.

## HW-001

- **Claim:** `gfusb.dll` is the UMDF NativeUSB driver for `27c6:5125`; the target firmware name is `GF_ST411SEC_APP_12509`.
- **Status:** CONFIRMED
- **Evidence:** INF metadata, PE exports/static behavior, two private capture responses, embedded APP record identity.
- **Source type:** non-redistributed OEM package and private captures.
- **Source identifier/hash:** `gfusb.dll` SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`; APP SHA-256 `70d3befbf0111ddc4cca0ea00989e672380323e9b543c08ffa3f548d0bdccb47`.
- **Independent cross-check:** target A8 firmware-version response in both private captures and a bounded read-only live query.
- **Known falsifiers:** target response naming another firmware; hash mismatch; INF not binding the VID:PID.
- **Residual uncertainty:** the missing resident segment is not part of the available APP payload.

## USB-001

- **Claim:** interface 1 uses bulk OUT `0x01` and bulk IN `0x81`, both max-packet 64; interrupt IN `0x82` has max-packet 8.
- **Status:** CONFIRMED
- **Evidence:** USB configuration descriptor and transfer timeline.
- **Source type:** private capture.
- **Source identifier/hash:** cold-attach capture SHA-256 `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
- **Independent cross-check:** Windows chunking code uses `0x40`-byte chunks.
- **Known falsifiers:** a target descriptor with different interface/endpoint coordinates.
- **Residual uncertainty:** the runtime role of interrupt endpoint `0x82` is not established.

## USB-002

- **Claim:** A0 uses magic, LE length, additive outer tag and an inner additive checksum; selected PID-5125 builders calculate the final byte in pre-OR control coordinates.
- **Status:** CONFIRMED
- **Evidence:** complete capture corpus, checksum generator/validator addresses `0x180059a70`/`0x180059390`, exact builder/wire comparisons.
- **Source type:** non-redistributed OEM static source and private captures.
- **Source identifier/hash:** `gfusb.dll` SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`; capture SHA-256 values listed in REFERENCES.
- **Independent cross-check:** synthetic serializer/parser tests and target-correct D1 wire.
- **Known falsifiers:** a valid target frame that violates both ordinary and tightly bounded special rules.
- **Residual uncertainty:** nominal meanings of ACK status `0x01` and `0x07`.

## USB-003

- **Claim:** B0 is a four-byte Goodix wrapper around a complete TLS record, with additive tag and 64-byte USB chunking.
- **Status:** CONFIRMED
- **Evidence:** B0 writer `0x180012660`, send/RX copy paths and capture length equality.
- **Source type:** non-redistributed OEM static source and private captures.
- **Source identifier/hash:** `gfusb.dll` SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`; B0 writer address `0x180012660`.
- **Independent cross-check:** clean-room B0/TLS synthetic interoperability.
- **Known falsifiers:** an extra transformation between TLS record and B0 payload.
- **Residual uncertainty:** no real device TLS handshake has completed on Linux.

## SEC-001

- **Claim:** the Windows container is machine-scope DPAPI material; `validator = KDF_OEM(out A)` and `PSK_TLS = out A`.
- **Status:** CONFIRMED
- **Evidence:** Windows protect/unprotect call chain, cache consumer and TLS setup dataflow.
- **Source type:** non-redistributed OEM static source and private redacted host evidence.
- **Source identifier/hash:** `gfusb.dll` SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`; runtime PSK publication area `0x180576e50`.
- **Independent cross-check:** locally transferred legitimate material matches E4 on the original device.
- **Known falsifiers:** a second OEM KDF between `out A` and the TLS PSK, or user-scope rather than machine-scope protection.
- **Residual uncertainty:** no general factory-preserving Linux provisioning procedure exists.

## SEC-002

- **Claim:** the legitimate transport material from the original machine produced one live read-only E4 `MATCH`.
- **Status:** CONFIRMED
- **Evidence:** redacted, hash-pinned operator result with cleanup and service restoration.
- **Source type:** private operator observation.
- **Source identifier/hash:** result SHA-256 `504cdcfc4b0e622f54e833506c5ba8a811a2fc5ef8c083abd4d636867fd66841`.
- **Independent cross-check:** the E4 selector/validator path was independently reconstructed statically.
- **Known falsifiers:** invalid result signature/hash, mismatched device or validator.
- **Residual uncertainty:** this establishes the original laptop only, not general reproducibility.

## SEC-003

- **Claim:** the profile is TLS 1.2 pure PSK, suite `0x00a8`, identity `Client_identity`, device client and host server.
- **Status:** CONFIRMED for the profile; UNKNOWN for a Linux/device completed handshake.
- **Evidence:** OEM TLS setup, authenticated private capture history and independent cross-engine synthetic tests.
- **Source type:** OEM static source, private capture metadata and clean-room test.
- **Source identifier/hash:** `gfusb.dll` SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`; TLS suite identifier `0x00a8`.
- **Independent cross-check:** OpenSSL-server/GnuTLS-client synthetic interoperability through the B0 model.
- **Known falsifiers:** a target session negotiating a different suite, identity or endpoint role.
- **Residual uncertainty:** `LIVE_TLS_HANDSHAKE_VERIFIED=false`.

## CFG-001

- **Claim:** the observed cold-start order is `E4 -> A2 -> 82 -> A6 -> A2 -> 70 -> 80x4 -> 90 -> D1 -> B0`.
- **Status:** CONFIRMED as ordering; UNKNOWN as causal minimum.
- **Evidence:** two independent private cold-attach captures.
- **Source type:** private captures.
- **Source identifier/hash:** SHA-256 `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b` and `4ac611e089a1aefa786014a65831ae02a648e2ee96162b73a4375c86e4647e87`.
- **Independent cross-check:** Windows builders and target receivers for the resolved commands.
- **Known falsifiers:** an independently initialized target session with a different required order.
- **Residual uncertainty:** A2/`0x70` effects and minimum sequence.

## CFG-002

- **Claim:** target-correct D1 wire is `a00600a6d103000000d7`; the final byte uses pre-OR control coordinates.
- **Status:** CONFIRMED
- **Evidence:** Windows builder and both target captures.
- **Source type:** OEM static source and private captures.
- **Source identifier/hash:** exact wire above; builder in `gfusb.dll` SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
- **Independent cross-check:** checksum rule predicts `d7`; direct wire checksum predicts the known-wrong `d6`.
- **Known falsifiers:** a target-correct builder/capture using another final byte under the same body.
- **Residual uncertainty:** D1 sufficiency is not proven because the pre-D1 path is not cleared.

## CFG-003

- **Claim:** the studied four `0x80` writes and `0x90` application are volatile and factory-preserving.
- **Status:** CONFIRMED, limited to these paths.
- **Evidence:** exact target APP receivers, SRAM/register destinations, factory source reapplied at startup and separate positive flash-programming control.
- **Source type:** non-redistributed target APP static analysis.
- **Source identifier/hash:** APP SHA-256 `70d3befbf0111ddc4cca0ea00989e672380323e9b543c08ffa3f548d0bdccb47`; receivers `0x08033568` and `0x080367d0`; flash control `0x0802d874`/`0x40023c00`.
- **Independent cross-check:** host calibration producer reconstructs the current 224-byte body and four register values.
- **Known falsifiers:** a reachable nonvolatile commit from either receiver or failure to restore the factory source on startup.
- **Residual uncertainty:** this does not classify A2, `0x70` or the complete cold-start path.

## CFG-004

- **Claim:** both A2 instances are byte-identical and dispatch subtype 2 to `0x080272e1`; semantics/lifetime are unresolved.
- **Status:** BLOCKED
- **Evidence:** exact wire in two captures and target APP absolute jump table.
- **Source type:** private captures and non-redistributed target APP static analysis.
- **Source identifier/hash:** exact request `a00600a6a203000114f0`; target APP SHA-256 `70d3befbf0111ddc4cca0ea00989e672380323e9b543c08ffa3f548d0bdccb47`.
- **Independent cross-check:** table entry is below APP start `0x0802c000`; nearby APP code is not table entry 2.
- **Known falsifiers:** a target-specific resident body proving the effect and persistence class.
- **Residual uncertainty:** `A2_SEMANTICS=UNRESOLVED`, `A2_LIFETIME=PERSISTENCE_UNKNOWN`.

## CFG-005

- **Claim:** `0x70` dispatches through base `0x20006d4c`, slot `0x20006d5c`, initialized to target `0x0802b8f5`; semantics/lifetime are unresolved.
- **Status:** BLOCKED
- **Evidence:** dispatch literal at `0x08035f24` and four direct initializer stores in the target APP.
- **Source type:** non-redistributed target APP static analysis.
- **Source identifier/hash:** APP SHA-256 `70d3befbf0111ddc4cca0ea00989e672380323e9b543c08ffa3f548d0bdccb47`; dispatch `0x08035eb0`; initializer sites `0x080342f0`, `0x0803456e`, `0x08034828`, `0x0803496e`.
- **Independent cross-check:** all configuration branches store the same odd Thumb target.
- **Known falsifiers:** a target-specific resident body or a branch initializing another family-7 target.
- **Residual uncertainty:** `70_SEMANTICS=UNRESOLVED`, `70_LIFETIME=PERSISTENCE_UNKNOWN`.

## IMG-001

- **Claim:** a 7684-byte record contains 7680 packed-12 bytes and a four-byte CRC-32/MPEG-2 trailer, producing an owned transposed `80x64` u16 raster.
- **Status:** CONFIRMED
- **Evidence:** target Windows decoder and clean-room independent implementation.
- **Source type:** OEM static source facts and synthetic test.
- **Source identifier/hash:** decoder/CRC area `0x180024010..0x1800244d9`; `gfusb.dll` SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
- **Independent cross-check:** exhaustive value-position round trips, full synthetic frame and corruption rejection.
- **Known falsifiers:** a valid target record requiring another polynomial, packing formula or destination mapping.
- **Residual uncertainty:** final intensity semantics and libfprint orientation policy.

## WIN-001

- **Claim:** `0x442120` copies the decoded u16 frame to `AcceptSampleData`; sensor index 12 selects `AlgoChicago.dll`, which consumes u16 directly.
- **Status:** CONFIRMED
- **Evidence:** `gfusb.dll`, `EngineAdapter.dll` and `AlgoChicago.dll` static call/data flow.
- **Source type:** non-redistributed OEM static sources.
- **Source identifier/hash:** EngineAdapter SHA-256 `bdf8026011d52983c4a17cc2479c354f62d33b1496c033503d407b08228326b9`; AlgoChicago SHA-256 `4b87e3e3552a6756a4c9c1ca2c9872237f4a371dfcb06242982a6e4042f4d705`.
- **Independent cross-check:** exact `2*width*height` copy sizes and WORD operations in the selected consumer.
- **Known falsifiers:** a proven u16-to-u8 conversion on the selected per-frame path.
- **Residual uncertainty:** Linux must define its own `FpImage` contract after live acquisition is safe.

## LNX-001

- **Claim:** the public tree implements and reproducibly tests only the image-record codec: exact 7684-byte validation, CRC-32/MPEG-2, packed-12 encode/decode, and the `80x64` transpose. A0/B0 framing, TLS/BIO boundaries, and lifecycle state-machine designs are documented from the private research corpus but are not currently provided as public implementations; runtime device support is not ready.
- **Status:** STRONGLY_SUPPORTED; implementation evidence is limited to the public image codec, while the documented transport, TLS/BIO, lifecycle, and hardware-runtime implementation shapes are not present in the public tree.
- **Evidence:** six deterministic synthetic tests cover the exact record length, CRC validation and rejection, all 4096 values in each packed-12 position, full record round-trip, and transpose bijection.
- **Source type:** project-authored public clean-room codec and synthetic tests; public documentation records the non-implemented designs.
- **Source identifier/hash:** `src/goodix5125_cleanroom.py` SHA-256 `ef63eb3852e6526722ee12cc5e61e753783007f082819f20218a19fbbe41e3e9`; `tests/test_cleanroom.py` SHA-256 `7997880f232c124ee7ebe688dbd0623e7d2b71ef51752924937f308de6c02274`.
- **Independent cross-check:** the closed public source tree contains the codec and tests but no A0/B0 framing module, TLS/BIO implementation, complete lifecycle state machine, USB import, embedded secret, firmware/provisioning operation, or hardware entrypoint.
- **Known falsifiers:** a public-tree implementation contradicting this scope, a codec that accepts a non-7684-byte or bad-CRC record, a packed-12 mismatch, or a non-bijective transpose.
- **Residual uncertainty:** A0/B0, TLS/BIO, complete lifecycle, and hardware runtime remain documented but unimplemented publicly; target resident receivers, real TLS, real images, and libfprint policy remain unresolved.

## BLK-001

- **Claim:** the current PoC blocker is the unavailable target-specific resident code for A2 and `0x70`; general reproducibility is separately blocked by machine-bound provisioning.
- **Status:** BLOCKED
- **Evidence:** closed local target-segment inventory and Windows descriptor audit.
- **Source type:** local publication metadata and non-redistributed target APP facts.
- **Source identifier/hash:** APP range starts `0x0802c000`; missing range `0x080272e0..0x0802b8f4`.
- **Independent cross-check:** both concrete aligned targets fall below APP and no inventoried ST411/12509 resident/IAP/combined segment covers them.
- **Known falsifiers:** a provenance-valid target-specific resident source or independently verifiable receiver description.
- **Residual uncertainty:** the code is absent only from the inventoried local target-specific corpus, not asserted absent globally.
