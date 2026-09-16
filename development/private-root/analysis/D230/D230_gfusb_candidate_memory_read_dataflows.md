# D230 gfusb candidate memory-read dataflows

## Census boundary

The static x86-64 census identifies 65 call-sites into the command transport
builders: 61 calls to A0 generic `0x18005c148`, three to A0 no-ack
`0x18005cc04`, and one to B0/TLS `0x18005c344`.  PE `.pdata` ranges were used to
assign call-sites to 34 enclosing functions/roles.  The command byte formula at
constant call-sites is `(r8 << 4) | (r9 << 1)`; 27 constant logical controls and
dynamic subtype call-sites were classified.

## Closest candidates

### `ChipRegRead`, `0x180059488`, opcode `0x82`

Minimal recovered serializer:

```text
body[0]   = fixed selector/status coordinate
body[1:3] = caller LE16 register
body[3:5] = caller LE16 count/quantity
send A0 control 0x82; copy typed response to caller
```

This is a real host-controlled read, but in a 16-bit chip/sensor-register
namespace.  It cannot encode `0x080272e0` or `0x0802b8f4`, and no range-extension
field or alias to raw MCU flash was found.

### `production_read_mcu`, `0x18003c7f4`, opcode `E4`

This wrapper sends a caller blob, parses an execution status/returned length,
and copies a bounded typed result.  Its high-level callers use production
selectors.  Neither the wrapper nor its classified callers serialize a
host-controlled 32-bit MCU address plus length.  The symmetric E0 function at
`0x18003d8e0` is a write operation and cannot supply negative side-effect proof
for a hypothetical undocumented selector.

### `ProductionOperateKey`, `0x18005b4bc`

The dynamic E-family selector exposes fixed enums such as MCU state, PMK-hash
or Pkey reads.  The input is an operation enum, not an address, and results are
operation-specific typed objects.  This is not a raw memory primitive.

### A6, A8, AE/AF

A6 is a fixed OTP/production read, A8 returns firmware identity, and AE (wire AF
for the captured coordinate) returns fixed MCU state.  All are read-like but
fixed/selective.

## Literal, string and serializer searches

Searches covered `ReadMemory`, `MemoryRead`, `FlashRead`, `ReadFlash`,
`IAPRead`, `DebugRead`, `Peek`, firmware/read/upload/download/dump strings, and
literal target/range values.  “Dump” strings resolve to host diagnostics/image
files, not a device memory command.  No device-flash literal participates in a
read request builder; generic `0x80000000` values are host masks/status values.

## Dataflow decision

No classified path satisfies:

```text
host 32-bit pointer/address → serialize into A0/alternate USB request
→ APP handler reads that source → length-proportional bytes copied to host
```

The conclusion is limited to the inventoried DLL and its statically recovered
transport-builder graph.  A new OEM module or target-specific primary artifact
is a falsifier.
