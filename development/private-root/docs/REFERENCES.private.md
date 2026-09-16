# References

Community code is referenced, not vendored. Proprietary and private sources
are identifiers only and are not included in the public repository.

## Upstream/community references

### libfprint

- Repository: <https://gitlab.freedesktop.org/libfprint/libfprint>
- Local reference version: `1.94.5`
- Referenced areas: driver lifecycle API, `FpDevice`, `FpiSsm`, cancellation,
  image ownership and the GoodixMOC driver as an architectural comparison.
- Use: API/architecture atlas only; it does not prove `27c6:5125` protocol or
  biometric semantics.
- Status: **referenced, not vendored**.

### goodix-fp-linux-dev / goodix-fp-dump

- Repository: <https://github.com/goodix-fp-linux-dev/goodix-fp-dump>
- Referenced areas: Goodix family framing, firmware/version naming and
  comparative device workflows.
- Use: related-family structural atlas only; not target proof.
- Status: **referenced, not vendored**.

### goodix-fp-linux-dev / goodix-firmware

- Repository: <https://github.com/goodix-fp-linux-dev/goodix-firmware>
- Referenced file: `GF_ST411SEC_APP_12109.bin`, SHA-256
  `100fc8a9fc3b37d018e6ffc7cd84ac7b28c8f1f71e9e8d7b94c1b1a96bf8a585`.
- Use: older 51x7/ST411 structural atlas; not a substitute for version 12509.
- Upstream policy states the firmware remains Goodix property and must remain
  hosted in that repository.
- Status: **referenced, not vendored**.

## Non-redistributed OEM sources

| Source | SHA-256 | Role |
| --- | --- | --- |
| `gfusb.dll`, driver 1.1.125.14 | `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2` | UMDF transport, protocol, TLS, target APP container; proprietary source, not redistributed. |
| `EngineAdapter.dll` | `bdf8026011d52983c4a17cc2479c354f62d33b1496c033503d407b08228326b9` | WBF engine and image handoff; proprietary source, not redistributed. |
| `AlgoChicago.dll` | `4b87e3e3552a6756a4c9c1ca2c9872237f4a371dfcb06242982a6e4042f4d705` | selected u16 image consumer; proprietary source, not redistributed. |
| `AlgoChicagoT.dll` | `5d22690afe6bde397cb1bd6d6979bb667c5a236c78e816f6abc0d96521bfe734` | related Chicago algorithm variant; proprietary source, not redistributed. |
| `GF_ST411SEC_APP_12509`, 128406 bytes | `70d3befbf0111ddc4cca0ea00989e672380323e9b543c08ffa3f548d0bdccb47` | exact target APP used for static receiver analysis; proprietary source, not redistributed. |

Complete disassembly, decompiler and string dumps are also excluded.

## Private captures and local evidence

| Identifier | SHA-256 | Role |
| --- | --- | --- |
| cold attach capture A | `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b` | USB descriptors, cold-start order, A0/B0 and image cycles; not redistributed. |
| cold attach capture B | `4ac611e089a1aefa786014a65831ae02a648e2ee96162b73a4375c86e4647e87` | independent cold-start/order and target-wire cross-check; not redistributed. |
| community issue capture | `5b2e9649b8acdbf93bbb19275feb32203dacc50d727ef2222d58162fbd1b63d0` | early comparative USB evidence; not redistributed here. |
| redacted one-shot operator result | `504cdcfc4b0e622f54e833506c5ba8a811a2fc5ef8c083abd4d636867fd66841` | live E4 MATCH and historical TLS timeout; private observation, not redistributed. |

No cache, DPAPI container, PSK, master secret, traffic key, decrypted payload,
fingerprint image or biometric template is included.

## Standards

- RFC 5246, *The Transport Layer Security (TLS) Protocol Version 1.2*.
- RFC 5288, *AES Galois Counter Mode (GCM) Cipher Suites for TLS*.
- CRC catalogue parameters commonly named CRC-32/MPEG-2: width 32,
  polynomial `0x04c11db7`, init `0xffffffff`, non-reflected, xorout zero.
- Microsoft Windows Biometric Framework and UMDF concepts are used as
  architecture terminology; no Microsoft source is vendored.

