# D230 APP 12509 memory-read candidates

## Dispatcher coverage

The APP dispatch state at `0x08035e3c` covers all 16 high-nibble families.
Families 8, 9, A, D, E and F dispatch to APP-present handlers at respectively
`0x0803356c`, `0x080367d4`, `0x08033188`, `0x080396b0`, `0x08033b3c` and
`0x08033c4c`.  Families 2–7 use the SRAM callback table based at
`0x20006d4c`; family 7 slot `0x20006d5c` resolves to the absent resident target
`0x0802b8f5`.  A-family subtype 2 similarly resolves to absent resident target
`0x080272e1`.

The private ZIP contains 20 byte-identical embedded named 12509 code records.
Their extracted code hash is recorded in the manifest.  The separately
documented canonical standalone APP file is not present as such; therefore the
fresh D230 review is used as a bounded cross-check of the existing hash-pinned
address model, not as a claim that its standalone hash was reproduced.

## Candidate analysis

- Family 8 consumes bounded register fields.  Its read side is the device half
  of `ChipRegRead`, not an MCU address dereference service.
- Family 9 contains config, DAC, driver-state and communication-test operations.
  The large `0x90` input is consumed as configuration; it does not cause a raw
  read response.
- Family A has an eight-way subtype switch.  Present subtypes construct fixed
  status, version, OTP/production results; the A2 subtype-2 body is resident and
  unknown, but the exact host A2 request is fixed and carries no arbitrary
  address/length fields.
- Families D and E handle TLS/state and production selector protocols.  No
  APP-present branch parses a host-supplied flash pointer and returns bytes from
  it.
- Family F handles firmware update/check/finalize behavior.  It exposes status,
  not a raw flash readback, and belongs to a mutating maintenance domain.

Ordinary firmware necessarily contains CPU load/copy primitives.  Existence of
such internal primitives is not exposure: no response-building call is reached
with a host-controlled source address in the APP-present handlers.

## Resident-code limitation

The bodies at `0x080272e0` and `0x0802b8f4` are absent, so D230 does not assert
that the device can never implement an undocumented resident command.  That is
not a material blind spot for the narrower host-path result because the complete
gfusb builder census and recovered normal request census contain no arbitrary
address carrier into those handlers.  A new host builder, new opcode capture, or
the resident/combined firmware would reopen the issue.
