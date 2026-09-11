<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/01 — review AI PM del probe PAM active-user

## Decisione

```text
PM_DECISION=ACCEPT_AND_CONTINUE
OUTCOME=READY_FOR_ONE_HUMAN_GATED_ACTIVE_USER_PAM_PROBE
ADVANCEMENT=OFFLINE_EXECUTABLE_CLOSURE_AND_OPERATOR_OBSERVABILITY_VERIFIED
EXECUTABLE_CLOSURE=PASS_OFFLINE_LIVE_PENDING_HUMAN
RESIDUAL_BLOCKER_OR_RISK=ONE_REAL_VERIFY_REQUIRES_USER_EXECUTION
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
OPERATOR_KIT_RELEASED=true
NEXT_STATE=HUMAN_REQUIRED
LIVE_EXECUTION_PERFORMED=false
```

La review ha riesaminato direttamente sorgente C, launcher, PAM privato,
istruzioni, manuale, diff e test; non si è basata sul summary dell’Executor.
Il delta prova una nuova ipotesi causale e non ripete il greeter difettoso: PAM
parte dal processo utente della sessione grafica attiva, mentre `pkexec` resta
confinato ai due audit host D286 separati.

## Finding chiusi durante la review

1. Il pathspec multilinea del gate Git iniziale poteva essere eseguito come
   comando, la stessa classe già osservata nel vecchio D287. È stato corretto
   con continuazione esplicita e provato su repository fixture pulito/sporco.
2. `Ctrl-C` poteva terminare `tee` prima di export e post-audit. Il runner è ora
   sotto `timeout --foreground`; i tee di capture ignorano HUP/INT/TERM fino a
   EOF e il wrapper differisce l’uscita. Una `SIGINT` reale su process group
   fixture prova classificazione, journal export e post-audit.
3. L’export diagnostico materializzava temporaneamente tutto il journal
   globale. Ora `journalctl --grep` filtra il solo MESSAGE prima dello stream;
   le righe estranee non entrano nel temporaneo o nella capture. Empty result è
   distinto da errore di lettura.
4. Il classificatore iniziale poteva sovrastimare un log vuoto come failure
   Polkit e non chiudeva ogni coerenza matcher/PAM. Ora richiede marker espliciti
   `FAIL + PAM_NOT_STARTED`, cardinalità univoche, conteggi
   observed/declared coerenti, return code esatti e tutti i contatori hardware.
5. Alcune pipeline controllavano il producer ma non il writer della capture.
   Ogni `PIPESTATUS` viene ora congelato atomicamente e sia producer sia
   `tee`/`sed` devono terminare con successo; altrimenti l’esito è terminale.
6. Il temporaneo era creato nel sottoprocesso della pipeline ma il cleanup
   finale viveva anche nel parent. La serie ora possiede un trap EXIT e un
   cleanup bounded espliciti; un failure diventa `FAIL_TEMP_CLEANUP`.

Nessun finding resta aperto.

## Evidenza riesaminata

- `42/42` test D287/01 active-user PASS, con fixture MATCH, NO_MATCH, Polkit
  preflight fail, negazione fprintd, timeout, log incompleto, action non-VERIFY,
  seconda epoch, contatori vietati, pipeline, summary/hash e SIGINT reale;
- `324/324` regressioni D282-D287 PASS nell’ambiente host consentito;
- preflight host PASS su build deterministica e
  `pam_start_confdir + pam_permit` reale;
- `bash -n` e `git diff --check` PASS; `shellcheck` non installato;
- hash sorgente, PAM, binario compilato e componenti host verificati; build ID
  disabilitato per rendere deterministico il runner;
- nessuna invocazione `--operator-run`, `pkcheck`, `pam_fprintd`, fprintd, USB,
  sensore, `sudo` o live eseguita dall’AI.

## Safety ed executable closure

Il subject `PID,start-time,UID` viene calcolato dal runner e verificato da
`pkcheck` nello stesso processo che prosegue a PAM. `pkcheck` non può mostrare
prompt né installare un agent. Un suo failure impedisce `pam_start_confdir()`.
Il PAM ha una sola regola, `max-tries=1 timeout=45`; il timeout esterno è 60 s.

Il successo del kit richiede una sola epoch VERIFY, un TLS, un extract, almeno
un confronto, action consumata, cleanup drenato/context-closed e zero
retry/reopen/reset/clear-halt/persistent. Qualsiasi secondo evento o
contraddizione fallisce chiuso. La capture conserva return code, subject,
cgroup, boot/cursor, PAM, fprintd, Polkit/logind pertinenti, root audit,
classificazione, summary e hash, senza risposte PAM o payload biometrici.

Il solo gap non chiudibile offline è l’esecuzione reale del `pkcheck` subject e
della successiva singola VERIFY. È un Human Gate e deve essere eseguito
manualmente dall’Utente una sola volta seguendo `README_IT.md`; qualunque esito
torna a review e non autorizza un rerun.
