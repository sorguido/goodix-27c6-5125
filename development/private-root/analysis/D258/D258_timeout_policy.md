# D258 command timeout policy

`COMMAND_TIMEOUT_POLICY=PER_COMMAND_EVIDENCE_BOUNDED`

| Command | Budget | Static basis | D255 observed request→terminal response |
| --- | ---: | --- | ---: |
| `0x36` | 500 ms | `gf_update_all_base` passes `0x01f4` to each FDT-base acquisition | 11.025 ms for stage0 IRQ100 |
| `0x50` | 500 ms | NAV helper call uses `0x01f4`; SetMode mode5 also carries 500 ms | 17.934 ms |
| `0x82` | 500 ms | exact `ChipRegRead(0x0082,2)` call passes `r9w=0x01f4` | 2.198 ms |
| `0x20` | 2000 ms | baseline image helper is called with `dx=0x07d0` | 81.293 ms |
| `0x32` | 100 ms | final SetMode mode3 ACK budget is `0x64` | 0.957 ms |

The `0x36` value is the end-to-end FDT-base acquisition budget. The internal
SetMode ACK path separately contains 100 ms, but the exact candidate treats
the command and required IRQ100 as one bounded semantic operation. All timeout
paths are terminal and fail closed. Automatic retries remain zero.

