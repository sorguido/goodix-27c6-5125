# D258 host semantic-gate callgraph

All offsets below belong to hash-gated `gfusb.dll` SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
The bounded audit found the target orchestration in `gfusb.dll`; no ownership
promotion from the Chicago algorithm DLLs is needed.

```text
caller 0x180068940
  -> gf_update_all_base 0x180068adc..0x18006987d
       -> 0x1800676f8  stage0 0x36 / raw FDT base0
       -> 0x180067874  0x50 NAV acquisition and store
       -> 0x1800676f8  stage1 0x36 / raw FDT base1
       -> 0x180059488  ChipRegRead(0x0082, 2)
       -> compare abs(base0[i]-base1[i]) with response[1]
       -> 0x180067914  0x20 baseline image acquisition
       -> 0x1800676f8  stage2 0x36 / raw FDT base2
       -> compare abs(base1[i]-base2[i]) with response[1]
       -> 0x180023fdc -> 0x180022654  NAV classifier, mode 1
       -> 0x180023fa8 -> 0x180022654  image classifier, mode 0
  -> success -> 0x180068abe ChicagoHUSetMode(3,1,1) / final 0x32
```

| Gate | OWNER_MODULE | OWNER_FUNCTION_OR_OFFSET | INPUT | OUTPUT | NEXT_STAGE_BRANCH | EVIDENCE_CLASS |
| --- | --- | --- | --- | --- | --- | --- |
| `0x50` | `gfusb.dll` | acquire `0x180067874`; consume `0x180069377 → 0x180023fdc → 0x180022654` | dynamic NAV body, cached NAV base, runtime classifier state | stored NAV then enum `0..3` after stage2 | acquisition permits stage1 unconditionally; later enum selects keep/update NAV base | target OEM static + D255 target capture |
| `0x82` | `gfusb.dll` | `gf_update_all_base 0x180068e26..0x180068ffe` | two-byte register result and unsigned raw base0/base1 words | byte 1 zero-extended as threshold; byte 0 ignored | every absolute word delta at or below threshold continues; otherwise cached-base fallback or rebuild loop | target OEM static + D255 target capture |
| `0x20` | `gfusb.dll` | acquire `0x180067914`; consume `0x180069531 → 0x180023fa8 → 0x180022654` | decrypted baseline image, cached image base, runtime classifier state | enum `0..3` after stage2 | acquisition permits stage2; later enum selects keep/update image base | target OEM static; D255 plaintext unavailable |

The important correction is temporal: neither the NAV nor image classifier is
a predicate that admits the third `0x36`. Both are evaluated after stage2.
Their unresolved decisions still block an exact host replay because the prompt
requires reproduction of all host decisions, not merely the command census.

