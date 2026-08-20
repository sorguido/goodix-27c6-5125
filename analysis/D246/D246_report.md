# D246 — closure della run live TLS→D4

## Chiusura

```text
OUTCOME=D246_D4_LIVE_EXECUTION_COMPLETED_STOP_AFTER_D4
ADVANCEMENT=REAL_EXECUTION_COMPLETED
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=AF_UNASSESSED
CANONICAL_DOCUMENTATION=manual_updated=true; sections=Stato del progetto,D246,Current critical boundary,Stato implementazione Linux
BUNDLE=path=analysis/D246/D246_bundle.zip; sha256=RECORDED_IN_EXTERNAL_SIDECAR
```

D246 è stato eseguito live con successo una sola volta. La categoria primaria
di avanzamento è `REAL_EXECUTION_COMPLETED`; la run ha inoltre prodotto nuova
evidenza tecnica live che il target reale accetta l'exchange D4 previsto. Non
viene estesa la prova oltre il receiver APP12509 esatto.

Questa closure Codex è esclusivamente documentale: non ha aperto USB, eseguito
TLS reale, tentato D4, effettuato retry o raggiunto AF.

## Evidenza live canonica

Il raw evidence prodotto dall'operatore è
`analysis/D246/D246_operator_live_stdout.json`, SHA-256
`055ace08832e2297d1b3687523fd41a410ed80b215207d63c352ea1cee2493e0`.
È stato conservato byte-identico.

Fatti osservati nel JSON live:

```text
result                                  pass
execution_mode                          live_single_shot
usb_open_count                          1
tls_handshake_completed                 true
tls_handshake_count                     1
d4_attempt_count                        1
d4_send_count                           1
d4_ack_status                           1 (0x01)
d4_completed                            true
d4_failure_class                        none
retry_count                             0
application_data_count                  0
persistent_write_family_count           0
D246_NEXT_APPLICATION_ACTION_REACHABLE  false
unexpected_data                         false
cleanup_count                           1
secret_zeroized                         true
source_seal_state                       sealed
fprintd_restore_status                  restored
runtime_psk_e4_binding_status           match
same_validated_psk_used_by_tls          true
```

L'osservazione protocollo D4 è:

```text
request_control            0xd4
request_logical_length     10
request_physical_length    64
ack_status                 0x01
response_body_length       0
completion_classification  single_frame_usb_completion
terminal_action            STOP_AFTER_D4
```

Cleanup, zeroizzazione, restore e reseal sono quindi completati. Nessun frame
applicativo e nessuna famiglia di scrittura persistente sono stati raggiunti.

## Metadata legacy nel raw evidence

Il raw JSON contiene ancora:

```text
LIVE_BASELINE_APPROVAL=PENDING_USER_REVIEW
decision=D236_LIVE_TLS_HANDSHAKE_SUCCESS
reached_phase=TLS_HANDSHAKE_OK
```

Sono campi legacy/stale del renderer, non lo stato finale D246. Non invalidano
la run e non sono stati corretti in-place. Il risultato autoritativo deriva da
`result=pass`, `execution_mode=live_single_shot`, dai contatori TLS/D4, dai
campi D246 specifici e dall'osservazione protocollo D4 sopra riportata.

## Portata semantica

La semantica non è inferita dal solo ACK live; resta quella già dimostrata
dall'analisi statica e dalla correlazione host/wire/receiver:

```text
D4 semantic class       VOLATILE_SESSION_INITIALIZATION
scope                    EXACT_APP12509_D4_RECEIVER_PATH_ONLY
logical request          a00600a6d403000000d3
physical OUT             fixed 64 byte, zero tail
post-TLS pacing          20 ms
timeout                  200 ms
accepted ACK             exact d4/01
typed D4 response        none
terminal                 STOP_AFTER_D4
```

Sul receiver APP12509 esatto il branch D4 subtype 2 modifica soltanto SRAM e
non raggiunge flash/IAP, OTP, factory data, configurazione persistente,
provisioning o enrollment. La run live prova l'accettazione dell'exchange sul
target, non l'assenza assoluta di persistenza per firmware, receiver o comandi
diversi.

## Nuovo boundary

A8, E4, TLS e D4 non sono più blocker aperti. Il prossimo confine tecnico è AF:

```text
AF = NEXT UNASSESSED PROTOCOL BOUNDARY
```

AF non è stato classificato, implementato, eseguito o autorizzato. Anche un
secondo D4 e qualunque retry restano non autorizzati.

## Provenance del preflight e chiusura locale

Il preflight della run è conservato in
`analysis/D246/D246_preflight_report.json`, SHA-256
`0843096d32a8f3dea0a202c8bd7bb04d0c0c88e2289116782aa0f6cb5bd744b8`.
Registra `status=pass`, namespace D246, zero open USB e zero letture secret
prima dell'esecuzione. Non contiene il secret né configurazione raw.

Contatori della sola closure Codex corrente:

```text
D246_REAL_USB_ACCESS=0
D246_REAL_TLS_HANDSHAKE=0
D246_REAL_D4_ATTEMPT=0
```

Il bundle è step-local. Il suo hash non può essere auto-incluso nei file che
esso contiene; il valore autoritativo è nel sidecar esterno
`analysis/D246/D246_bundle.zip.sha256` e nell'output finale della closure.
