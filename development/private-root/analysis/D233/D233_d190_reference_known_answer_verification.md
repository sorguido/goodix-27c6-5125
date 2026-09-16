# D190 known-answer verification

The five expected validators are provenance-valid historical outputs. The D190
record shows that the OEM machine-code oracle, Model A and independently written
Model B first reached 35/35 public checkpoint matches; only afterward were the
validator literals added to the reference self-test. Therefore the expected
side is independent of the recovered runtime function.

The closure invoked `derive_validator_from_canonical_pe()` for V0–V4 using the
local canonical PE. Results:

| Vector | Expected source | Result |
| --- | --- | --- |
| V0 | D190 OEM oracle | MATCH |
| V1 | D190 OEM oracle | MATCH |
| V2 | D190 OEM oracle | MATCH |
| V3 | D190 OEM oracle | MATCH |
| V4 | D190 OEM oracle | MATCH |

All five outputs were 32 bytes; mismatch count was zero. The PE hash and unique
instruction pattern were checked on each call. A one-bit secret mutation, a
mutated expected value, wrong PE hash and ambiguous pattern were separately
shown not to pass.

`D190_KAT_NONCIRCULAR=yes`.
