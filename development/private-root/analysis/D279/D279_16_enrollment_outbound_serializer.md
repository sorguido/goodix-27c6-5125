<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/16 — serializer outbound enrollment-only, senza backend

## Esito

`goodix_enrollment_outbound_frame.[ch]` trasforma un comando già preparato in
un frame A0 fixed64, ma non possiede né accetta alcun backend. Prima della
serializzazione ricostruisce il body dal contratto tipizzato e richiede
corrispondenza byte-per-byte; applica inoltre un'allowlist chiusa:

```text
0x20 0x22 0x32 0x34 0x36 0x50
```

Tutte sono famiglie enrollment-only osservate in ATTEMPT02. Nessuna famiglia
persistente nota (`0xe0/0xa4/0xf0/0xf4`) è ammessa. Questa assenza non prova
che il completamento OEM sia privo di qualunque mutazione sensor-side; limita
soltanto ciò che questo serializer può costruire.

```text
OUTCOME=READY_OFFLINE_ENROLLMENT_OUTBOUND_SERIALIZER
ADVANCEMENT=STRICT_PREPARED_COMMAND_TO_FIXED64_BOUNDARY
CONTROL_ALLOWLIST=0x20;0x22;0x32;0x34;0x36;0x50
KNOWN_PERSISTENT_FAMILY_COUNT=0
BACKEND_PRESENT=false
SUBMIT_API_PRESENT=false
PRODUCTION_ENROLLMENT_ENABLED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Verifica

La regressione copre tutti gli otto purpose del planner, rilegge ogni frame
con il parser A0, verifica body esatto e padding fixed64 nullo e respinge un
body manomesso prima del build. Passa normal e ASan/UBSan. L'audit sorgente e
simboli impedisce dipendenze USB/backend/submit.

```text
D279_16_TESTS=2/2_PASS_NORMAL;2/2_PASS_ASAN_UBSAN
ALL_ENROLLMENT_COMMAND_PURPOSES=PASS
FIXED64_ZERO_PADDING=PASS
TAMPERED_PREPARED_BODY=FAIL_CLOSED
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
PERSISTENT_FAMILY_COUNT=0
RETRY_COUNT=0
SUBMIT_COUNT=0
EXECUTABLE_CLOSURE=PASS_SERIALIZER_ONLY_NO_BACKEND
```

La build production-shaped passa con registry standard e NBIS, senza warning
nuovi del serializer e senza enumerazione/open/claim/submit USB.

## Confine residuo

Il prossimo passo offline è un contratto di submit transazionale con backend
esclusivamente sintetico: un solo OUT pending, commit del planner soltanto
dopo completion positiva, nessun retry e terminale su errore/stale generation.
Il gate production deve restare invariato.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_ENROLLMENT_SYNTHETIC_SUBMIT_TRANSACTION_WITH_PRODUCTION_GATE
```
