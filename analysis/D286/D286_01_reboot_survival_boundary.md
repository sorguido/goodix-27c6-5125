<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D286/01 — survival a reboot e rollback readiness

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

Il preflight D286 chiude `17/17` contratti. La matrice cumulativa D282–D286
chiude `197/197` nell'ambiente host; l'esecuzione confinata fallisce invece su
quattro controlli che richiedono socket systemd/PAM non concessi dal sandbox.
`shellcheck` non è installato, mentre `bash -n` è incluso nel preflight.

```text
OUTCOME=READY_OFFLINE_HUMAN_REQUIRED_REBOOT_CYCLE
ADVANCEMENT=NEW_CONTROLLED_REBOOT_AND_DIRECT_ROLLBACK_READINESS_OPERATOR_PATH
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=REBOOT_AND_ONE_POST_REBOOT_SENSOR_ACTION_NOT_EXECUTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
```
