# D232 implementation inventory

## Baseline

`HEAD == origin/main == ebaeda016bd3c66d78aa16b351fd0bd13d1daf8b`.
The public/sanitized tree contains one production source module,
`src/goodix5125_cleanroom.py`, and its unit tests. It implements only the
synthetic image-record codec (CRC, packed-12 conversion and transpose).

The tree has no USB import, libusb binding, hardware entrypoint, A0/B0 framing
implementation, TLS engine, secret loader, replay state machine, durable run
report, cleanup coordinator, live kit or operator kit. Consequently there is
no old live path to reuse and no hidden implementation to enable.

## Nearest existing seams

| required area | closest repository material | classification | D232 action |
| --- | --- | --- | --- |
| USB backend | documentation only | absent; live forbidden | do not implement; synthetic backend only |
| A0/B0 framing | README/EVIDENCE and D230 capture census | protocol contract, no public code | implement clean-room serializer/parser used only by synthetic backend |
| E4 validator | canonical D231/D230 evidence and recovered capture hash | target read-only contract | compare response shape and pinned validator hash; no provisioning |
| TLS PSK | canonical direct runtime dataflow and TLS profile | boundary known, engine absent | implement root-only 32-byte loader/zeroization and synthetic TLS oracle only |
| abort/report/cleanup | D231 timeout/blast-radius artifacts | design contract | implement monotonic abort, atomic redacted report and exactly-once cleanup |
| image codec | `goodix5125_cleanroom.py` | production-tested but post-TLS and unrelated | leave unchanged |

## Production-shaped versus synthetic-only

Production-shaped D232 components will be: exact phase contract, A0/B0
framing, target-material verification, PSK file checks, state transitions,
timeouts, abort policy, redacted atomic report schema, cleanup ownership and
future-live preflight data validation.

Synthetic-only components will be: all command exchanges, all response data,
the TLS handshake oracle, failure injection and test fixtures. There is no
device enumeration or transport implementation.

## Inherited boundaries

- D230 arbitrary resident read remains `EXHAUSTED_IN_LOCAL_CORPUS`.
- D231 permits only exact OEM replay on the original device; resident NVM
  nonmutation is not absolutely proven.
- PSK portability is limited to legitimately exported original machine-bound
  material; no replacement/provisioning path is allowed.
- D233 risk acceptance is `not_granted`; automatic reset is forbidden.
- the first capture is definitively lost; the recovered capture is the only
  packet-level target source used here.
- README/EVIDENCE/REFERENCES and production codec remain protected and unchanged.

## Inventory decision

One new, reviewable D232 module is necessary. It must remain incapable of live
transport even when executed with a sensor attached. No external/community
source code is used; Rockytkg remains a documentary oracle only.

