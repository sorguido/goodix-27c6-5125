# D232 target material provenance

## Gate result

`TARGET_MATERIAL_PROVENANCE_COMPLETE=yes`

All target-specific material required to construct or validate the exact path
is available in the recovered, operator-designated provenance-valid corpus.
No value is taken from Rockytkg or another external codebase.

## C1 — 0x82 and A6

The recovered target capture provides the exact read-only response contracts:

- 0x82 request body length 5; typed response body length 4 and SHA-256
  `82537d2c...6d5703` (packet 69);
- A6 request body length 2; typed response body length 64 and SHA-256
  `d7e81a41...c2b92b` (packet 75).

D232 does not redistribute those raw response bodies. The state machine checks
length and hash. A mismatch aborts before the next command.

Both A2 typed responses are byte-identical in the recovered capture. Their
three-byte body is pinned by SHA-256 `39e469ce...c022f5`; a different IRQ body
is treated as unexpected and stops the synthetic state machine.

## C2 — DAC values

D231 proved the local DLL chain `ChicagoHUsetDac` from target OTP/config context
through `SetMode(7,0,0)` and four register writes. The recovered capture fixes
the order 0x0220, 0x0236, 0x0238, 0x023a and the target material manifest holds
the four little-endian values as non-secret metadata, not source constants.

The 0x90 body independently contains the same register/value tuples at offsets
117, 121, 125 and 129. The loader requires exact order and equality between the
manifest DAC values and those config tuples. Thus the runtime command values
come from hash-pinned target material and remain correlated with the target
config; they are not invented or copied from community code.

## C3 — 0x90

The provenance-valid recovered Windows target capture contains exactly one
224-byte 0x90 body at packet 103. Its SHA-256 is
`e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82`.
The body finalizer `519a` independently satisfies the documented additive-u16
rule, and the four DAC tuples cross-check at the offsets above.

The raw body remains only in the private capture/local protected material. It
is not copied into source, tests, analysis artifacts or the bundle. A future
D233 must place the exact 224 bytes at the manifest-named root-only path and the
loader must verify regular-file type, root ownership, mode, no symlink, exact
length, SHA-256, finalizer and tuple correlation before any transport exists.

## C4 — hygiene and limits

The analysis manifest contains identifiers, hashes and non-secret DAC metadata
only. It contains no PSK, DPAPI material, raw OTP, raw 0x90 or biometric data.
The first historical capture is definitively lost; coverage is one recovered
capture. This does not change the positive provenance of the exact material
actually present, but prevents a second packet-level comparison.
