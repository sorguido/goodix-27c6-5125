# D276/04 — TLS Memory-BIO nativo e backend FpiUsbTransfer host-only

## Esito

`OUTCOME=READY` e `LOCAL_EXECUTABLE_CLOSURE=PASS_HOST_ONLY`. OpenSSL 3 è stato
selezionato rispetto a GnuTLS perché offre direttamente server TLS 1.2 pure-PSK,
BIO di memoria, callback PSK, cleanup esplicito e integrazione in-process senza
thread/socket. La dipendenza è disponibile come `libssl-dev`/`openssl` e viene
installata esplicitamente nel workflow.

## Implementazione ed evidenza

`GoodixTlsServer` forza TLS 1.2 e `PSK-AES128-GCM-SHA256`, accetta esclusivamente
`Client_identity`, usa BIO di memoria, un solo handoff e fence terminale senza
restart. Il teardown usa `OPENSSL_cleanse`; la suite usa esclusivamente una PSK
sintetica e completa un handshake client/server in memoria.

`GoodixFpiUsbBackend` contiene il wiring production-shaped
`fpi_usb_transfer_new`/`fill_bulk`/`submit`, ma il test sostituisce soltanto il
submit mediante seam. L'unico completion path chiama
`goodix_usb_router_receive_complete`; generation, fence e pending impediscono
un secondo reader e submit concorrenti. Nessun transfer reale è stato inviato.

## Closure e limiti

Le suite D276/04 normal e ASAN/UBSAN passano due volte; D276/02 e D276/03
passano normal e sanitizer. Static audit conferma assenza di socket, endpoint
read, VID:PID e secondo completion path. GitHub Actions resta
`PENDING_AI_PM_NON_GATING`.

Restano invariati: `TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS=UNRESOLVED`,
`PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL=UNRESOLVED`,
`TARGET_DEVICE_TIMEOUT=UNKNOWN`, `ENROLLMENT_STAGE_POLICY=NOT_SELECTED`,
`ORIENTATION_CONTRACT=UNRESOLVED`, `POLARITY_CONTRACT=UNRESOLVED`,
`TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN`, `HARDWARE_EQUIVALENCE=UNPROVEN`.

`NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_AFTER_D276_04`. Nessun live è autorizzato.
