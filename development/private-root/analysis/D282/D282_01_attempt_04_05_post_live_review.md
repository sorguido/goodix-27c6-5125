<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 Attempt 04 e 05 — review indipendente

```text
OUTCOME=PASS_LIVE_CLOSED_BY_ATTEMPT_05
ADVANCEMENT=FPRINTD_TARGET_SIGFM_ENROLL_RESTART_SAME_MATCH_DIFFERENT_NO_MATCH_DELETE
EXECUTABLE_CLOSURE=PASS_LIVE_PLUS_HASH_PINNED_EVIDENCE_AUDIT
RESIDUAL_BLOCKER_OR_RISK=SINGLE_SAMPLE_DOES_NOT_ESTIMATE_MATCHER_RELIABILITY
CANONICAL_DOCUMENTATION=GOODIX_TECHNICAL_MANUAL_UPDATED
REVIEW_SET=GIT_NATIVE
```

Entrambe le run usano la baseline
`ed94d33e1cf6a2387135598c58a27d6c1573ba13`. L'auditor riproducibile
verifica i quattro digest, summary, risultati client e il primo blocco finale
di quattro epoch presente in ciascun `operator.log`.

Attempt 04 ha completato il percorso software, ma l'operatore attesta di aver
presentato l'indice destro anche nella Phase B. Non prova quindi il requisito
different-finger. Preserva invece l'osservazione autentica e limitata: sullo
stesso enrollment il primo campione di verifica dello stesso indice ha
prodotto match, il secondo no-match. È un singolo false non-match osservato;
non consente una stima FRR né una conclusione generale sul matcher.

Attempt 05 ha usato otto contatti dell'indice destro per enrollment, lo stesso
indice per il match e, per attestazione esplicita dell'operatore, l'indice
sinistro per il no-match. Il percorso ha poi eseguito delete host-only e
rollback. L'audit mostra un ENROLL, due VERIFY e un epoch NONE di cleanup:
tre action consumate, tre handshake, zero retry/reopen/reset/clear-halt e zero
famiglie persistenti note; ogni backend è drenato e ogni context è chiuso.
Servizio, staging, libreria di sistema e storage preesistente sono ripristinati.

La stringa client `Verifying: right-index-finger` descrive il template
registrato, non lo stimulus fisico. Subito dopo l'istruzione Phase B può quindi
indurre l'operatore a riusare il dito destro. Il correttivo host-side aggiunge
una spiegazione esplicita e richiede di digitare `INDICE SINISTRO` prima di
avviare la seconda VERIFY. Non modifica driver, protocollo, matcher, action
budget o contatti.

I `summary.env` autentici contengono due chiavi duplicate con valori identici:
`AUTHORIZATION_CREDENTIAL_REQUIRED=false` e
`AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false`. Il dato resta univoco, ma
il launcher corretto le emette una volta sola tramite il finalizzatore di
cleanup. Nessuna nuova live D282 è richiesta: Attempt 05 chiude D282/01.
