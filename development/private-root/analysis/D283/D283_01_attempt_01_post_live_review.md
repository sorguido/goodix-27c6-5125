<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D283/01 Attempt 01 — review indipendente e decisione post-live

## Decisione

`PASS_LIVE_CLOSED`. La run prova sul target reale il percorso dedicato
`pam_start_confdir()` → `pam_authenticate()` → `pam_fprintd.so` → fprintd →
driver Goodix/SIGFM, con un solo enrollment e una sola VERIFY. Non prova login,
autenticazione biometrica di `sudo`, affidabilità statistica o assenza assoluta
di scritture sensor-side sconosciute.

Il set canonico è
`captures/D283_01/D28301_ATTEMPT_01_20260911T042655Z_2cf82fd1fdb6/sanitized/`.
L'auditor ripetibile è `analysis/D283/d283_01_attempt_01_evidence_audit.py`.

## Integrità e provenance

La baseline live è
`2cf82fd1fdb613cc44c997c4f1df74f582dfc376`. Gli SHA-256 ricalcolati
coincidono con quelli operator-supplied:

- `operator.log`: `bf42acfb2e0ee849ea4554cb9b3ee29c7b2f9cceb4d4ba2bc44ad40736e4597a`;
- `summary.env`: `6b472c31960051b7562880bfc08abc54eafba4f77d138316a240e8a3079a74c1`;
- `terminal-transcript.log`: `86e819f4e5221f76805b297704a58162a89aed644ed3685ce05e9b9856481ff1`.

L'export dichiara `TEMPLATE_INCLUDED_IN_EXPORT=false`; i tre file sanitizzati
non contengono FP3 o pixel biometrici.

## PAM e matcher

Il transcript attraversa Phase A, B e C. L'enrollment dell'indice destro
completa otto stage senza `enroll-retry-*`. Il runner dedicato osserva:

```text
pam_start_confdir() = 0
pam_authenticate()  = 0
pam_end()           = 0
```

Il journal lega il successo PAM a una vera epoch VERIFY e a telemetria SIGFM
coerente: otto sample nel template, threshold 40, primo confronto sul sample 1
con score 1116 e outcome `match`. Lo score è ampiamente sopra soglia, ma resta
una singola osservazione e non autorizza stime FAR/FRR o generalizzazioni di
robustezza.

## Lifecycle, safety e rollback

Le tre epoch distinte sono ENROLL, VERIFY e NONE/delete. Le prime due consumano
esattamente due action e due handshake TLS; i submit reali sono 203 + 75 = 278.
La terza epoch non consuma action, TLS o submit sensor-reaching. Tutte riportano
outstanding zero, backend drenato e context chiuso. Retry, reopen, reset,
clear-halt e famiglie persistenti note sono zero.

Il delete del solo template isolato è osservato. Il summary finale, scritto dal
cleanup dopo la run, dichiara servizio ripristinato, staging rimosso, libreria
di sistema e storage preesistente invariati, rollback completo e return code
zero. Lo zero delle famiglie persistenti note resta una verifica su allowlist,
non una prova assoluta dell'assenza di ogni possibile effetto NVM sconosciuto.

## Normalizzazione del marker storico

`operator.log` inizia con `D283_01_FAILURE_PHASE=PRE_SENSOR_STAGING`, mentre il
`summary.env` finale non contiene alcuna failure phase e classifica la run PASS.
Il sorgente della baseline mostra che la riga era emessa incondizionatamente
all'ingresso nello staging come stato iniziale; soltanto
`capture_d283_failure()` associa una phase a un return code e riscrive il
risultato come `FAIL_<phase>`. Non è quindi evidenza di failure.

La semantica viene normalizzata come
`INITIALIZATION_ONLY_NOT_RUN_OUTCOME`. Il launcher corrente usa invece
`D283_01_PROGRESS_PHASE=PRE_SENSOR_STAGING` per evitare ambiguità future; i
campi `D283_01_FAILURE_PHASE` restano riservati ai summary/failure path.

## Closure e prossimo confine

```text
OUTCOME=PASS_LIVE_CLOSED
ADVANCEMENT=REAL_DEDICATED_PAM_TARGET_AUTHENTICATION_COMPLETED
EXECUTABLE_CLOSURE=PASS_LIVE_WITH_HASH_PINNED_REVIEW_AND_ROLLBACK
RESIDUAL_BLOCKER_OR_RISK=SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE
NEXT_BOUNDARY=PROJECT_INTEGRATION_DECISION
```
