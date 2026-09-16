# D230 IAP, boot, maintenance and debug readback audit

## Result

No arbitrary flash readback path was found in any mode.  The maintenance domain
contains erase/program/check/reset operations, not a raw byte-return service.
Consequently there is also no “read exists but requires IAP” path to preserve as
a candidate.

## Classified maintenance flow

- `device_action_erase_app` at `0x180061550` builds A4 and explicitly checks IAP
  state, erases APP and resets the MCU.  It is persistently mutating.
- `gfUpdatefirmware` at `0x1800656f4` includes the ClearApp/update decision.
- `updatefirmware` at `0x18006bb3c` sends F0 firmware slices and F4
  check/finalize/reset operations.
- APP family F at `0x08033c4c` is the device-side update family.
- APP flash control around `0x0802d874` accesses the flash controller at
  `0x40023c00`; it is positive control evidence for programming, not readback.

“Check firmware” returns operation success/status in the classified host
consumer.  No address+length input and no requested flash bytes flow back to the
caller.  A checksum/version comparison is not equivalent to resident memory
extraction.

## Safety classification

Even if a future artifact exposed a read adjacent to these flows, any required
A4/ClearApp/F0 programming, boot-mode transition, IAP entry or reset would fail
the factory-preserving gate.  D230 performed none of those actions.

No vendor control request, debug endpoint, SWD/JTAG path, raw bulk maintenance
format or UMDF alternate IO surface carrying a memory read was found.
