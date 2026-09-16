<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D286/01 — review del primo ciclo post-reboot

## Classificazione

```text
OUTCOME=PERSISTENT_SURVIVAL_PASS_VERIFY_NO_MATCH
POST_REBOOT_PERSISTENT_STATE_AUDIT=PASS
FIRST_POST_REBOOT_VERIFY=NO_MATCH
PASSWORD_FALLBACK_ENTERED=true
PASSWORD_USED_FOR_TEST=false
FAILURE_AUDIT_TIMESTAMP_BUG=true
AUTOMATIC_RETRY_PERFORMED=false
EXECUTABLE_CLOSURE=PARTIAL_LIVE_FAILURE_DIAGNOSTIC_RECOVERED
```

La capture originale sotto
`captures/D286_01/D28601_CYCLE_20260911T184820Z_f9bb4551a477/sanitized/`
è preservata senza riscritture e hash-pinned dall'auditor dedicato.

## Evidenza osservata

- il boot ID cambia da `b281de25-3fba-48c7-9ea3-e0021b8d1342` a
  `351d5424-2894-4d0c-ba9a-596c42481ab7`;
- gli audit root-only pre e post reboot chiudono state, runtime, wrapper,
  authselect, password fallback, template, libfprint e uninstall readiness;
- il journal dello stesso boot, letto senza privilegi e senza nuova azione
  sensore, conserva una sola epoch VERIFY, un TLS, 76 submit, cleanup drenato e
  zero retry/reopen/reset/clear-halt/famiglie persistenti;
- SIGFM estrae 112 keypoint, confronta tutti gli otto sample e produce
  `no_match`; il massimo è score 14 sul sample 1, sotto soglia invariata 40;
- la failure capture registra return code sudo 137 e nessun retry automatico;
- il failure audit fallisce soltanto perché `journalctl` non accetta il
  timestamp con virgola decimale generato dalla locale italiana.

Il log sudo nella capture è vuoto. L'ingresso nel prompt password e il fatto
che nessuna password sia stata immessa sono attestazioni dell'operatore,
coerenti con il `NO_MATCH`, il successivo timeout/kill e il return code 137, ma
non vengono promossi a osservazione byte-for-byte della capture.

## Decisione correttiva

Il survival persistente non deve essere ripetuto con un altro reboot. Il
vecchio entrypoint è chiuso. Il correttivo usa cursor journal indipendenti
dalla locale e fino a tre processi `/usr/bin/sudo -v` distinti. Ogni processo
mantiene PAM `max-tries=1`; un FIFO senza writer rende impossibile fornire una
password, mentre un prompt sentinella termina direttamente sudo al fallback.
Un tentativo successivo richiede una nuova conferma testuale dell'operatore e
il primo match chiude la serie.

Non cambiano matcher, threshold, preprocessing, template o installazione D285.
Tre `NO_MATCH` non costituiscono da soli una misura FRR e terminano con review
indipendente, senza quarto tentativo.

## Closure offline del correttivo

Il launcher corretto chiude il vecchio ciclo reboot, usa cursor systemd con
`LC_ALL=C`, blocca il canale password sudo e limita la nuova serie a tre
contatti espliciti. I contratti dedicati chiudono `30/30`; la regressione host
D282–D286 chiude `210/210`. I cinque RPM OpenCV nel nuovo path persistente
verificano il manifest canonico `5/5` e il preflight D285 ha ricostruito
offline la candidate direttamente da quel path. La nuova run resta
`HUMAN_REQUIRED`.

```text
OUTCOME=READY_OFFLINE_HUMAN_REQUIRED_EXPLICIT_RETRY_SERIES
ADVANCEMENT=FIRST_CYCLE_CLASSIFIED_AND_RETRY_METHOD_CORRECTED
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=UP_TO_THREE_REAL_SENSOR_VERIFY_ACTIONS_NOT_EXECUTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
```
