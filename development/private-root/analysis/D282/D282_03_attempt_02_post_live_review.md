<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/03 Attempt 02 — review indipendente e decisione post-live

## Decisione

`PASS_LIVE_CLOSED`. La seconda run valida D282/03 chiude sufficientemente la
caratterizzazione preliminare same-finger/different-finger per passare al
boundary PAM dedicato già progettato. Non prova affidabilità statistica e non
cancella il rischio storico di un falso non-match occasionale sul dito
corretto.

La prima run D282/03 errata non è promossa a evidenza canonica. L’unico set
usato per questa decisione è:
`captures/D282_03/D28203_ATTEMPT_02_20260910T222713Z_4a3ee4bb96f6/sanitized/`.

## Integrità e provenance

SHA-256 ricalcolati:

- `operator.log`: `0877ef2aa822107667a5161ce2aadb701a9f46cdf6604e7dd0ffe07674718916`;
- `summary.env`: `5186b8bef974f95b661394915c9b1ea78f895be6ad3fa60156fcb571f71d8394`;
- `trials.tsv`: `0eac5367ef03f2b0dbfcd949f82b9ca927ddbb9ddda1e3617100f1b2116bd026`;
- `terminal-transcript.log`: `d93402647e80ebb5f17ec5cf15cbff2a99c90ff9366279dd7f5338c5039597b6`.

La baseline live è
`4a3ee4bb96f6f4e9bca838aabb51edc9ce4b2db1`.

## Risultati tecnici

La sequenza operatore e i metadati per-trial coincidono con il piano R-L-R /
L-R-L. Ogni trial registra conferma `DESTRO` o `SINISTRO`, classe fisica,
ordine, posizione, PID e InvocationID.

```text
SAME_FINGER:      3/3 MATCH       score osservati 674, 75, 54
DIFFERENT_FINGER: 3/3 NO_MATCH    score completi 0, 0, 0
THRESHOLD:        40
```

I match 1 e 3 terminano sul sample 1; il match 5 termina sul sample 5 dopo
quattro score zero. I vettori same-finger sono quindi censurati
dall’early-return e non rappresentano otto confronti completi. Tutte le prove
different-finger scandiscono invece gli otto sample, sempre con score zero.

I keypoint dei probe same-finger sono 155, 148, 139; quelli different-finger
115, 117, 111. La separazione del conteggio keypoint è osservata ma non viene
interpretata come causa né come classificatore: l’API pubblica non espone un
quality score equivalente e la prova non controlla la qualità del contatto.

## Processi, lifecycle e safety

Il blocco A usa PID 94915 / InvocationID
`4259de9f292845f2857c4b79ca9ac29b`; il blocco B usa PID 95050 /
InvocationID `5b49fdaa12a74ad8b2bfb98391cb3bf7`. L’ordine contiene un same-finger in
seconda posizione nel blocco B, che fa match, e match same-finger prima e dopo
restart.

Sono presenti 8 epoch coerenti: un enrollment, sei verify e un NONE/delete.
Le 7 action biometriche sono consumate una volta; `real_submit` totale 678;
zero retry, reopen, reset, clear-halt o famiglie persistenti note; tutti gli
epoch risultano drained e context-closed. Il solo close pair 1/1 è sul trial 5
che fa match; gli altri sono 0/0. Il template non è esportato; servizio,
staging, libreria di sistema e storage preesistente sono ripristinati.

## Interpretazione e next step

Il campione 3+3 è troppo piccolo per FRR, FAR o generalizzazioni di robustezza,
ma ridimensiona i tre dubbi operativi che bloccavano D283: nessun effetto
deterministico della seconda verify, nessun degrado globale dopo re-entry e
separazione perfetta same/different in questa run bilanciata. Un ulteriore test
esplorativo prima di PAM non aggiungerebbe informazione proporzionata.

D283/01 può quindi essere sbloccato come singola prova PAM dedicata. Poiché un
false reject same-finger è già stato osservato storicamente, un eventuale
`PAM_AUTHENTICATE` non riuscito non sarà attribuito automaticamente al layer
PAM: la diagnostica deve conservare outcome e score SIGFM oltre al return code
PAM.

```text
OUTCOME=PASS_LIVE_CLOSED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_LIVE_WITH_ROLLBACK
RESIDUAL_BLOCKER_OR_RISK=SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE
NEXT_STEP=HUMAN_GATE_D283_01_DEDICATED_PAM
```
