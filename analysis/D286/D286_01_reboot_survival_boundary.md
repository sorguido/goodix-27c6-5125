<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D286/01 — survival a reboot e rollback readiness (design iniziale)

> Il primo ciclo è stato eseguito sulla baseline `f9bb4551a477` ed è ora
> chiuso. Il survival persistente è PASS, la VERIFY è `NO_MATCH` e il percorso
> timestamp/fallback è superato dal correttivo cursor + FIFO documentato in
> `D286_01_first_cycle_post_live_review.md`.

## Decisione e metodo

D285 è installato e chiuso live, ma non prova sopravvivenza a reboot né
coerenza corrente diretta dei valori root-only. D286 usa un audit privilegiato
separato dal PAM sudo: `pkexec` è disponibile sul target Fedora e il suo PAM
`/usr/lib/pam.d/polkit-1` include `system-auth`, dal quale D285 ha rimosso
pam_fprintd. L'audit password/polkit non deve quindi consumare azioni sensore.

Il ciclo ha due fasi legate dal boot ID. Prima del reboot verifica tutti i
pre-delete gate dell'uninstall senza cancellare nulla. Dopo un boot ID diverso
ripete lo stesso audit, quindi esegue una sola `sudo -v` con max-tries=1 e
richiede una sola epoch VERIFY, un solo match, zero retry/reopen/reset/
clear-halt/persistenza nota e cleanup drenato. Un audit finale conferma ancora
state, runtime, template e rollback readiness.

Se la sola `sudo -v` fallisce, il kit non la ripete: dopo avere invalidato il
timestamp raccoglie via polkit la telemetria sanitizzata della singola prova e
termina fail-closed, lasciando una capture adatta alla review indipendente.

## Riesame metodologico pre-live

1. **Cosa cambia rispetto a D285?** Nessun enrollment o reinstallazione: il
   nuovo evento è un reboot reale fra due audit root-only, seguito da una sola
   VERIFY sul template già persistente.
2. **Quale ipotesi viene testata?** Che configurazione, wrapper/runtime e FP3
   D285 sopravvivano al reboot e che sudo continui a caricare la candidate,
   lasciando contemporaneamente praticabile l'uninstall fail-closed.
3. **Se fallisce nello stesso punto?** Nessun retry. La capture viene
   revisionata distinguendo drift host/runtime da non-match biometrico
   occasionale; non si procede a lock screen, login o uninstall automatico.

## Scope e closure offline

Il kit non modifica PAM, authselect, runtime o template; non esegue enrollment,
delete o uninstall. La pre-fase ha budget sensore zero, la post-fase una sola
action/contatto. Le capture esportano soltanto booleani e telemetry
sanitizzata, mai state, hash/path template o FP3.

Il preflight del design iniziale chiudeva `17/17` contratti. La relativa
matrice cumulativa D282–D286 chiudeva `197/197` nell'ambiente host;
l'esecuzione confinata falliva invece su
quattro controlli che richiedono socket systemd/PAM non concessi dal sandbox.
`shellcheck` non è installato, mentre `bash -n` è incluso nel preflight.

```text
OUTCOME=SUPERSEDED_BY_POST_LIVE_REVIEW_AND_EXPLICIT_RETRY_CORRECTIVE
ADVANCEMENT=HISTORICAL_INITIAL_REBOOT_OPERATOR_PATH
EXECUTABLE_CLOSURE=SUPERSEDED_SEE_POST_LIVE_REVIEW
RESIDUAL_BLOCKER_OR_RISK=SEE_CURRENT_EXPLICIT_RETRY_CORRECTIVE
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
```
