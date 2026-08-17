# D245 — risultati test

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
..................................................................................................................................
----------------------------------------------------------------------
Ran 130 tests in 3.908s

OK
```

```text
./operator_kit/d245-live-tls-once.sh --offline-dry-run
D245_PHASE=EXECUTABLE_CLOSURE
D245_RESULT=PASS
D245_FAILURE_CLASS=none
D245_LIVE_USB_EXECUTION=NOT_PERFORMED
```

Copertura D245: A8 byte-exact/short OUT; happy path con E4 ACK01 e ACK07; A8
ACK07; timeout OUT/IN; mismatch 12508/12510; fragmented/coalesced/stale/order e
checksum malformed; E4 OUT completato + IN timeout; intero pre-D1; B0 fixed-64,
tail zero e pacing; TLS timeout/success; durable checkpoint/restore/final;
cleanup e reseal exactly-once; secret zeroized; `fprintd` active/inactive;
zero retry/D4/application-data/persistent-write e zero accesso USB reale.
