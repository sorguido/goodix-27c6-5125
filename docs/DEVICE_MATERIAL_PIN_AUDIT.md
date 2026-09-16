<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Device-material pin classification

| Value/check | Classification | Release treatment |
| --- | --- | --- |
| VID:PID `27c6:5125`, APP12509 identity | `KEEP_UNIVERSAL` | Fixed compatibility boundary |
| `G5125POC` v1 header, 88-byte length | `KEEP_UNIVERSAL` | Parsed exactly before the PSK is used |
| CONFIG90 224-byte length and arithmetic finalizer | `KEEP_UNIVERSAL` | Recomputed from the supplied bytes |
| OEM `gfusb.dll` size/digest and producer offsets | `KEEP_UNIVERSAL` | Qualified producer implementation, not reader identity |
| FDT cache 13,520-byte layout and CRC-32/MPEG-2 | `KEEP_UNIVERSAL` | Recomputed structurally |
| protected regular files, root ownership, `0600`; directory `0700`; no symlinks | `KEEP_UNIVERSAL` | Fail-closed filesystem boundary |
| manifest v1 exact required-key grammar, maximum length and no duplicate/unknown/trailing data | `KEEP_UNIVERSAL` | Deterministic fail-closed metadata boundary |
| manifest, transport, CONFIG90, FDT cache and OTP digests | `MAKE_DEVICE_DYNAMIC` | Supplied per reader and checked against the imported bundle |
| A2, chip82 and OTP A6 response digests | `MAKE_DEVICE_DYNAMIC` | Manifest values checked against live typed responses |
| E4 validator digest | `MAKE_DEVICE_DYNAMIC` | Derived from the user's PSK and qualified DLL producer data |
| DAC tuple bytes and concrete CONFIG90 finalizer | `MAKE_DEVICE_DYNAMIC` | Read from the validated user's CONFIG90 |
| Historical hashes including `e1988b…` | `TEST_FIXTURE_ONLY` | May remain only in private regression evidence/tests |
| Historical packet-index selectors | `REMOVE_OBSOLETE` | Not part of runtime acceptance; acquisition tooling is outside release scope |

A SHA-256 is not weakened merely because it is dynamic: the protected manifest
commits to the actual bundle, and live response pins bind runtime traffic to the
reader-specific material. A mismatched, missing, malformed, or insecurely
stored input remains rejected.
