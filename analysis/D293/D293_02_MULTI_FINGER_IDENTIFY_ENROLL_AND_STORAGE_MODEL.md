<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293/02 — multi-finger `any`, handoff enrollment e storage

Baseline: `61c8ff33b13d977120a6faa45dea2ac0860bcbcc` (`development`).

## Esito

La policy canonica `GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE` pubblicizza
IDENTIFY e VERIFY. Nel vero fprintd 1.94.5, `VerifyStart("any")` con più print
usa IDENTIFY sulla gallery completa; con una print usa VERIFY. Prima di ENROLL,
fprintd carica tutte le print e usa IDENTIFY come duplicate-check.

Il core image-device comunica al driver l'esito host-side dell'identify. Il
driver arma un solo handoff esclusivamente se IDENTIFY termina con successo,
senza match, con STOP terminale e backend drenato. Claim USB, materiale
runtime, sessione TLS e lifecycle vengono rilasciati; ENROLL li riacquisisce
in un nuovo transport epoch. Match, processing failure, cancellation, poison,
non-quiescenza o un'altra action non abilitano il passaggio. Non viene aggiunto
alcun retry o contatto implicito. La telemetria production distingue logical
action, transport epoch e handoff e non registra immagini, template o secret.

## Storage multi-user

Il test content-free esercita il layout fprintd derivato in D293/01: due
principal, due dita, ricostruzione dopo restart, replace dello stesso dito,
delete singolo e name reuse dopo cleanup. Conferma l'isolamento per path e il
rischio residuo: fprintd non ha un hook account-delete, quindi senza cleanup
host il nome riusato può trovare dati stale. Qui non si implementa tale hook e
non si crea un database Goodix.

## Verifiche

- `production/check-source.sh`: PASS, patch 15 path, 30 TU e 32 header;
- `validate_d293_02.py`: PASS sul sorgente fprintd/libfprint/Goodix;
- `test_d293_02_storage_model.py`: PASS;
- `production-two-epoch-template-reuse`: PASS normal e ASan/UBSan, incluso
  IDENTIFY no-match → ENROLL 8-stage con risorse fresche e zero USB reale;
- `identify-failure-cancel-no-handoff`: PASS normal e ASan/UBSan; extraction
  retryable e cancellation post-TLS lasciano handoff disarmato, backend
  drenato e il successivo ENROLL fallisce senza acquire, claim, TLS o USB;
- profilo feature: PASS normal e ASan/UBSan, IDENTIFY/VERIFY annunciati;
- build canonica normal e ASan/UBSan: PASS; ABI `LIBFPRINT_2.0.0`, SONAME,
  assenza RPATH e assenza dei 39 simboli host/test-only: PASS.

Nessun contenuto protetto è stato letto; nessun USB, live, sudo, install o
deploy è stato eseguito. B2 è chiuso nello scope offline ma non chiude Phase B:
restano l'integrazione multi-principal col daemon reale e poi la prova target
KDE/fprintd, soggetta a Human Gate.

```text
D293_02_OUTCOME=PASS_OFFLINE_IMPLEMENTATION
PHASE_B_B1=COMPLETED
PHASE_B_B2=COMPLETED_OFFLINE
FPRINTD_ANY_MULTI_PRINT_USES_IDENTIFY=true
IDENTIFY_NO_MATCH_ENROLL_HANDOFF_MAX=1
IDENTIFY_FAILURE_CANCEL_HANDOFF_COUNT=0
AUTOMATIC_RETRY_ADDED=false
REAL_USB_ACCESS=0
PROTECTED_FILE_CONTENT_READ=false
CURRENT_PHASE=B
PRODUCTION_READY=false
NEXT_BOUNDARY=PHASE_B_B3_FPRINTD_MULTI_PRINCIPAL_INTEGRATION_OFFLINE
```
