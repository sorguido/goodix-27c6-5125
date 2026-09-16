# D233 USB backend contract

`LibusbSystemApi` binds only the system libusb operations needed by
`ProductionUsbTransport`. Every real ABI method first enters the unconditional
D233 source seal, so no shipped path can initialize, enumerate, open, claim or
transfer to USB.

Future D234 behavior after an explicit source patch is constrained to:

- exact `27c6:5125`, interface 0, bulk OUT `0x01`, bulk IN `0x81`;
- no wildcard/fallback device and no detach, auto-detach, clear-halt or reset;
- descriptor plus bus/address/port-path identity at open and around every phase;
- one open and one claim; release, close and context exit at most once;
- OUT split into 64-byte USB packets; a partial OUT is ambiguous and terminal;
- IN accumulation supports partial reads and multiple buffered frames, but
  rejects zero progress, invalid magic/length/tag and oversized frames;
- monotonic deadline per frame and D232 phase timeouts;
- phase order and forbidden controls inherited from D232; no retry;
- unexpected re-enumeration or identity change is terminal.

`ProductionReplayBackend` connects these framed operations to the unchanged
D232 core and adds command/open/handshake/cleanup counters. The live allowlist
cannot represent D4, E0, A4, F0 or F4; no provisioning or firmware functions
exist in the module.
