# D245 — risultati test

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
...................................................................................................................................
----------------------------------------------------------------------
Ran 131 tests

OK
```

```text
./operator_kit/d245-live-tls-once.sh --offline-dry-run
D245_PHASE=EXECUTABLE_CLOSURE
D245_RESULT=PASS
D245_FAILURE_CLASS=none
D245_LIVE_USB_EXECUTION=NOT_PERFORMED
```

Copertura D245: A8 byte-exact/short OUT; full synthetic path sia ACK01 sia ACK07
con response FW12509 valida; ACK07 + timeout/malformed/wrong control/FW12508/
FW12510/extra frame; ACK01 + firmware mismatch; ACK02 senza seconda IN;
fragmented/coalesced ACK07+response; E4 OUT completato + IN timeout; intero
pre-D1; B0 fixed-64, tail zero e pacing; TLS timeout/success; durable
checkpoint/restore/final; cleanup e reseal exactly-once; secret zeroized;
`fprintd` active/inactive; zero retry/D4/application-data/persistent-write e
zero accesso USB reale. I launcher D239–D244 sono verificati byte-per-byte sui
bundle storici canonici.
