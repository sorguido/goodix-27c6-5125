<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/01 — boundary e closure offline del probe PAM active-user

## Decisione di design

```text
EXPERIMENT=ACTIVE_USER_SESSION_PAM_CONFDIR_SINGLE_VERIFY_PROBE
OUTCOME=OFFLINE_DESIGN_AND_EXECUTABLE_CLOSURE_COMPLETE
ADVANCEMENT=MATERIAL_HOST_CONTEXT_EXPERIMENT_DESIGNED_AND_OFFLINE_PROVEN
EXECUTABLE_CLOSURE=PASS_OFFLINE_LIVE_REQUIRES_HUMAN
RESIDUAL_BLOCKER_OR_RISK=ONE_REAL_FACTORY_PRESERVING_VERIFY_REQUIRES_OPERATOR
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
LIVE_EXECUTION_PERFORMED=false
```

La failure precedente era anteriore a VERIFY: `pam_fprintd` raggiungeva
`ListEnrolledFingers`, ma Polkit negava il subject del greeter perché il
launcher `pkexec -> runuser` conservava sessione/cgroup root
`background-light`. Ripetere il greeter o aggiungere soltanto logging non
avrebbe testato una nuova ipotesi.

Il nuovo esperimento mantiene D287/01 e cambia una sola variabile causale: il
runner che effettua `pam_start_confdir()` vive direttamente nella sessione
grafica attiva dell’utente. Non usa greeter, namespace root, `runuser` o
`systemd-run`. I soli privilegi sono gli audit host D286 pre/post, processi
separati che non avvolgono né generano il runner PAM.

## Sequenza chiusa

1. gate Git su `development`, HEAD/origin identici e critical set pulito;
2. verifica hash/NEVRA di runner, PAM, `pam_fprintd`, libpam, `pkcheck` e policy;
3. verifica sessione Wayland, runtime, bus e cgroup non root-background;
4. cardinalità sysfs del target pari a uno e fprintd non già attivo;
5. compilazione privata e prova reale offline `pam_start_confdir + pam_permit`;
6. root audit D286 pre, senza sensore;
7. cursor globale del boot e conferma unica `INDICE DESTRO`;
8. nello stesso processo utente: subject PID/start-time/UID, `pkcheck`
   non-interattivo dell’action VERIFY e, solo se PASS, una chiamata PAM;
9. timeout esterno 60 s, PAM `max-tries=1 timeout=45`;
10. export journal unit-specific e globale filtrato, classificazione e root
    audit D286 post anche dopo esito negativo o interruzione dell’azione;
11. summary e manifest SHA-256 della capture.

Il `pkcheck` non dimostra anticipatamente che la successiva autorizzazione
fprintd passerà in ogni dettaglio: dimostra però l’esatta proprietà rimasta
incerta, cioè che quel processo è autorizzato per l’action VERIFY prima che
PAM possa attivare fprintd. Se fallisce, `PAM_NOT_STARTED=true` chiude il probe
senza contatto.

## Guardrail e osservabilità

Il PAM dedicato vive solo nel confdir temporaneo e contiene una singola regola
assoluta `pam_fprintd.so max-tries=1 timeout=45 debug`. La callback non legge o
stampa risposte segrete: inoltra soltanto messaggi informativi e restituisce
risposte vuote. Nessun file PAM host viene scritto.

La classificazione positiva richiede congiuntamente:

- un’unica epoch totale e VERIFY;
- un solo marker start ed extract e almeno un confronto;
- `attempts=1`, `rejected=0`, `consumed=1`, `tls=1`, `first_image=1`;
- `outstanding=0`, `drained=1`, `context_closed=1`;
- retry/reopen/reset/clear-halt/persistent tutti a zero;
- esattamente un outcome matcher e coerenza con i return code PAM.

Una seconda epoch, un’action differente o un contatore vietato è
`SAFETY_VIOLATION`. Il journal diagnostico globale viene filtrato dal
`journalctl --grep` nativo sul solo campo MESSAGE e sanitizzato in streaming:
nessuna riga globale estranea viene materializzata nel temporaneo o nella
capture. Le risposte PAM, template, immagini e protected material non entrano
nella capture.

## Riesame metodologico pre-live

1. **Cosa cambia realmente?** Il processo PAM appartiene alla sessione utente
   attiva e non discende dal contesto logind root creato da `pkexec`.
2. **Quale nuova ipotesi viene testata?** Che il subject attivo esatto superi
   Polkit e consenta a `pam_fprintd` di oltrepassare `ListEnrolledFingers` fino
   a una singola VERIFY sul runtime D285 installato.
3. **Se fallisce nello stesso punto?** Nessun rerun equivalente: review della
   capture completa e nuova analisi di subject/session/policy. Se fallisce più
   avanti, il nuovo boundary PAM/fprintd/runtime decide il replan.

## Evidenza offline

Il preflight reale è stato eseguito fuori dal sandbox filesystem della sessione
AI, perché quel sandbox rimappa l’ownership dei moduli PAM di sistema e libpam
restituisce `PAM_SYSTEM_ERR` persino per `pam_permit`. Nell’ambiente host
normale, senza privilegi e senza percorso biometrico, ha prodotto:

```text
D287_01_PROBE_OFFLINE_PREFLIGHT=PASS
D287_01_PROBE_RUNNER_REAL_PAM_PERMIT=PASS
D287_01_PROBE_PKCHECK_EXACT_SUBJECT_CONSTRUCTION=PASS_STATIC
D287_01_PROBE_LIVE_EXECUTION=HUMAN_REQUIRED
REAL_USB_ENUMERATION_ATTEMPTED=false
REAL_SENSOR_ACCESSED=false
LIVE_EXECUTION_PERFORMED=false
```

Il marker `PKCHECK_EXACT_SUBJECT_CONSTRUCTION` è una prova statica: il
preflight offline non esegue `pkcheck`. La sola invocazione reale è riservata
all’operatore, immediatamente prima di PAM nello stesso PID subject.

## Stato PM

```text
PM_DECISION=ACCEPT_AND_CONTINUE
OPERATOR_KIT_RELEASED=true
NEXT_STATE=HUMAN_REQUIRED
```
