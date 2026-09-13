<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293/02 — multi-finger `any`, handoff enrollment e storage

Baseline storica D293/02: `61c8ff33b13d977120a6faa45dea2ac0860bcbcc`
(`development`). Correttivo R9 riesaminato nel commit
`c540d676ef619e3e1f1667778fd902c59566b917`.

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

## Correttivo R9 — action IDENTIFY ripetuta nello stesso open

L'incrocio del vero fprintd 1.94.5, di `pam_fprintd` e dell'adattatore ha
confermato un'incompatibilità deterministica: una serie PAM conserva Claim e
open logico, e con gallery multi-dito ogni nuovo `VerifyStart("any")` è una
IDENTIFY. Prima del correttivo, una IDENTIFY NO_MATCH pulita chiudeva la prima
epoch ma il ramo successivo ammetteva soltanto ENROLL; la seconda IDENTIFY era
rifiutata e il contesto diventava poisoned. Il nuovo test sul vero adattatore
ha riprodotto il rifiuto prima della patch.

Il delta minimo mantiene l'open logico standard e permette il rollover interno
fresh-resource per una nuova IDENTIFY esplicitamente richiesta dopo un esito
host pulito, allo stesso modo già previsto per VERIFY. Ogni nuova action
riacquisisce materiale, claim e TLS, conserva la baseline SIGFM dello stesso
open e non viene mai schedulata dal driver. Processing retry/fatal,
cancellazione, backend non drenato e poison restano terminali/fenced e non
possono riaprire risorse.

`identify_result` resta necessario: STOP e drain device-side possono precedere
il confronto SIGFM asincrono, quindi il solo stato del trasporto non distingue
NO_MATCH/MATCH puliti da errori di processing. Il correttivo aggiunge il
simmetrico callback privato `verify_result`; entrambi trasportano soltanto
`success` e `match` prima del normale report libfprint. Non sono API pubbliche,
non gestiscono sessioni fprintd e non esistono nelle origini pristine Fedora o
Rocky. La copia Rocky è solo parità di test.

| Comportamento | Rocky/framework originale | D293 + vincolo APP12509 | Scelta minima | Prova |
| --- | --- | --- | --- | --- |
| Claim/open | fprintd apre una volta per Claim; Rocky mantiene il trasporto fino a close | open logico stabile, ma ogni capture pulita rilascia claim/TLS/materiale | riusare l'open logico standard e conservare il rollover fresh-resource locale | sorgenti fprintd/Rocky; D291 target-proven per acquisition esplicite |
| Activate/deactivate/close | una activate per action, poi cancel/wait e close standard | STOP, drain e release locali sono richiesti prima del riuso | consentire solo la nuova action esplicita; conservare teardown APP12509 | secure-session normal/sanitizer |
| IDENTIFY→ENROLL | duplicate-check globale, poi ENROLL su no-match | handoff già bounded a uno e solo dopo esito pulito | invariato | `production-two-epoch-template-reuse` |
| IDENTIFY ripetuta | framework/fprintd ammettono una nuova action nello stesso open | il vecchio whitelist ENROLL-only rifiutava il secondo tentativo multi-dito | rollover IDENTIFY fresh-resource | `r9-explicit-multi-identify-same-open` |
| Esito asincrono | confronto host dopo capture; nessun vfunc upstream verso il driver | drain può precedere matcher e rendere ambiguo il riuso | callback privati outcome-only minimi | `r9-host-outcome-orders-capture-release` |
| Retry/error | fprintd può rilanciare subito l'action su `FP_DEVICE_RETRY` | non è una nuova richiesta client pulita | callback failure + sticky poison, zero reacquire | test dinamici retry/fatal/cancel/non-drain |

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
- `r9-explicit-multi-identify-same-open`: PASS normal e ASan/UBSan; prova
  NO_MATCH→MATCH e tre NO_MATCH nello stesso open, tre action esplicite, tre
  transport epoch e nessuna quarta acquisizione;
- `r9-host-outcome-orders-capture-release`: PASS normal e ASan/UBSan; VERIFY e
  IDENTIFY trattengono le risorse finché il matcher asincrono è bloccato e le
  rilasciano dopo l'outcome;
- `r9-fatal-host-processing-terminal`: PASS normal e ASan/UBSan; il matcher
  fatale attraversa il vero adattatore, avvelena il contesto e la successiva
  IDENTIFY è respinta senza nuova epoch, claim, materiale o submit;
- secure-session completa: 34/34 normal e 34/34 ASan/UBSan; FpImageDevice:
  32/32 normal e 32/32 ASan/UBSan;
- clean build production normal e sanitizer: PASS, SONAME
  `libfprint-2.so.2`, ABI fprintd, zero simboli host/test-only e zero RPATH.

Nessun contenuto protetto è stato letto; nessun USB, live, sudo, install o
deploy è stato eseguito. B2 è chiuso nello scope offline ma non chiude Phase B:
restano l'integrazione multi-principal col daemon reale e poi la prova target
KDE/fprintd, soggetta a Human Gate.

```text
D293_02_OUTCOME=PASS_OFFLINE_IMPLEMENTATION_WITH_R9_CORRECTIVE
PHASE_B_B1=COMPLETED
PHASE_B_B2=COMPLETED_OFFLINE
FPRINTD_ANY_MULTI_PRINT_USES_IDENTIFY=true
IDENTIFY_NO_MATCH_ENROLL_HANDOFF_MAX=1
IDENTIFY_FAILURE_CANCEL_HANDOFF_COUNT=0
R9_SAME_OPEN_IDENTIFY=CONFIRMED_AND_CORRECTED
R9_EXPLICIT_IDENTIFY_ACTIONS_TESTED_MAX=3
R9_HIDDEN_FOURTH_ACQUISITION=false
IDENTIFY_RESULT_CALLBACK=MAINTAINED_MINIMAL
VERIFY_RESULT_CALLBACK=ADDED_MINIMAL
AUTOMATIC_RETRY_ADDED=false
REAL_USB_ACCESS=0
PROTECTED_FILE_CONTENT_READ=false
CURRENT_PHASE=B
PRODUCTION_READY=false
NEXT_BOUNDARY=D293_04_R7_GUI_SESSION_BUDGET_DECISION
```
