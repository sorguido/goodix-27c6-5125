# D231 post-seal contract repair report

Repair scope: governance and artifact contract only. D231 technical analysis
was not rerun; D230 was not reopened; no hardware, USB, driver, firmware or
secret was accessed.

| OLD | NEW | REASON | TECHNICAL_EVIDENCE_CHANGED |
| --- | --- | --- | --- |
| `D231_EXACT_OEM_PRE_D1_REPLAY_CLEARED_FOR_D233_REVIEW_ONLY` | `D231_PRE_D1_CLEARED_FOR_EXACT_OEM_REPLAY` | Restore the approved enumerated D231 terminal decision. | no |
| unqualified `PRE_D1_PATH_CLEARED` with value `true` | `PRE_D1_PATH_CLEARED_FOR_EXACT_OEM_REPLAY=true` | Remove universal/ambiguous gate naming and preserve the original-device exact-replay scope. | no |
| D233 described as harness preparation/review | D232 is offline implementation/review with live hard-disabled; D233 is a future live single-shot | Restore the approved D232/D233 governance boundary. | no |
| `psk_portability_status=PROVEN_FOR_ORIGINAL_DEVICE_MACHINE_BOUND_NOT_GENERAL` | `psk_portability_status=PSK_PORTABILITY_PROVEN` plus the explicit original-device/machine-bound scope | Use an approved D231 REV2 enum without broadening portability. | no |
| D231 JSON used non-contract field names and omitted required risk/PSK fields | All mandatory schema keys and valid enum values are present | Restore machine-readable contract compatibility. | no |
| D233 risk readiness was mixed with review authorization | Risk model ready; operator acceptance `not_granted`; automatic reset `forbidden`; live authorization `no` | Separate risk-model completeness from human acceptance and live authority. | no |
| Root manual routed directly to D233 review | Root manual routes D231 → D232 offline → optional separately authorized D233 live | Make the canonical narrative match the approved workflow. | no |

`TECHNICAL_EVIDENCE_CHANGED=no`

The preserved technical result remains: A2 and 0x70 host semantics, exact
capture matches, cross-version convergence and the DAC chain are proven;
device-resident absence of NVM side effects is not proven; exact OEM replay is
operationally factory-preserving; D230 remains
`EXHAUSTED_IN_LOCAL_CORPUS`.
