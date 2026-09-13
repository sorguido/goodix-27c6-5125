<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293/04 — corrective KDE/new-user e blocker R7

## Decisione PM

La readiness del kit precedente è superata. Il corrective R1–R7 è stato
implementato e verificato offline, ma il gate non è pronto per l'operatore:
il KCM Users Plasma 6.7.5 non espone al kit un hook prima di ogni
`EnrollStart`. Chiudere la GUI dopo la prima enrollment e verificare il
journal rileva un'ulteriore action soltanto dopo che può avere raggiunto il
driver; è accounting retrospettivo, non un fence tecnico sul budget cumulativo
della sessione GUI.

Non è stato introdotto un proxy fprintd, un monitor race-based, un contatore
globale del daemon o una policy driver specifica del test. Sarebbero un cambio
materiale del metodo e interferirebbero con le normali action native appena
corrette in R9. `LIVE_CAPABLE=false`, `prepare.sh` termina con codice 3 prima
di build o privilegio, il common launcher respinge `--operator-run` prima di
creare la capture e `root-helper.sh --deploy` è disabilitato.

```text
HEAD=091846914d02f461d4af659ad5de17c0ba4c5363
CURRENT_PHASE=B
WORK_CLASS=D293_LOCAL_REPLAN_AND_CORRECTIVE
D293_04_OPERATOR_KIT=BLOCKED_OFFLINE
D293_04_BLOCKER=R7_GUI_SESSION_BUDGET_NOT_ENFORCED_BEFORE_EXTRA_ENROLLSTART
D293_04_LIVE_EXECUTION=BLOCKED_NOT_PERFORMED
PHASE_B_CLOSED=false
PRODUCTION_READY=false
```

## Esito R1–R8

| Rilievo | Esito | Evidenza offline |
| --- | --- | --- |
| R1 dito/duplicate-check | CORRECTED | Payload e README richiedono un dito fisico consapevolmente non registrato; duplicato è distinto, terminale e senza ENROLL/retry. |
| R2 privilegi/path | CORRECTED_OFFLINE | Il nuovo UID non usa journal/systemctl; il supervisor root pubblica soltanto marker whitelistati. Path pubblico e privato hanno modi distinti e la capture è per-run. ACL/PolicyKit autentiche restano target-only. |
| R3 marker/provenance | CORRECTED | Normalizzazione MESSAGE esatta, cardinalità, marker mancante/duplicato/SHA errato e classifier self-contained senza `/run` sono provati. |
| R4 interazione | CORRECTED | Tutti i prompt hanno newline; sanitizer fa flush; test streaming vede la domanda prima dell'input e copre EOF/timeout. |
| R5 rilascio KCM | CORRECTED_OFFLINE | Pulsante finale + chiusura normale, attesa della fine del processo prima di VERIFY, riapertura separata per delete; claim trattenuto blocca il flusso. Il binario target non è stato avviato. |
| R6 recovery | CORRECTED_OFFLINE | Rollback propagato e serializzato, fine reale supervisor, identità UID/GID/home, unmount fail-closed, intent atomico, seconda recovery idempotente e capture preservata sono attraversati sulla funzione `recover()` reale con soli comandi esterni mock. |
| R7 conteggi/budget | CORRECTED_PARTIAL_BLOCKED | `fprintd-list`, campi audit e cardinalità `action=` sono fail-closed; durante una finestra post-action non ancora validata i conteggi parziali sono `UNKNOWN`, mai zero inventati. VERIFY ha precheck e massimo tre tentativi. L'action UI extra viene rilevata post hoc ma non impedita prima di `EnrollStart`: blocker unico. |
| R8 provenance | CORRECTED | Callback privati Fedora, copia Rocky di sola parità, origine pristine, consumer Goodix e decisione R9 sono registrati nei tre ledger canonici; patch e hash production sono coerenti. |

La sequenza simulata mantiene una IDENTIFY di duplicate-check, una ENROLL a
otto stage/fino a venti contatti e fino a tre VERIFY, con `MAX_ACTIONS=5`,
`MAX_CONTACTS=24` e retry transport/secure/post zero. Gli audit autentici
confermano che il campo `first_image` vale uno per IDENTIFY e zero per ENROLL;
la regressione usa questa forma reale. Il totale contatti resta
`1 + enroll_contacts + verify_attempts`.

## Verifiche eseguite

- `analysis/D293/test_d293_04_operator_scripts.py`: 24/24 PASS. Attraversa
  payload, sanitizer, classifier e `recover()` reali con esterni mock in
  `/tmp`: MATCH al primo, NO_MATCH→MATCH, tre NO_MATCH senza quarto,
  duplicato, errori list/DBus/PolicyKit/device busy/tecnici, claim KCM
  trattenuto, marker/campi errati o duplicati, telemetria post-action `UNKNOWN`,
  action UI extra, rollback/supervisor/
  template/unmount/identity failure e recovery ripetuta.
- common harness: 14/14 PASS; i quattro file comuni restano invariati.
- common `--offline-test` da cwd `/tmp`: PASS con capture autocontenuta.
- common `--operator-run`: rifiuto `EXPERIMENT_NOT_LIVE_CAPABLE` prima della
  capture; `prepare.sh`: `BLOCKED`, rc 3.
- sintassi di tutti gli script experiment e `git diff --check`: PASS.
- R9 sul vero adattatore: secure-session 34/34 normal e 34/34 ASan/UBSan,
  incluso il fatal host-processing con poison e zero reacquire;
  FpImageDevice 32/32 normal e 32/32 ASan/UBSan.
- clean build production normal e sanitizer: PASS; ABI
  `LIBFPRINT_2.0.0`, SONAME `libfprint-2.so.2`, zero RPATH e zero simboli
  host/test-only.
- D293/03 vero fprintd su bus privato/virtual image: PASS, due nomi principal
  ma un solo UID Unix; non è prova del lifecycle Goodix o multi-account reale.

## Real Target Compatibility Gate

Query read-only confermano Fedora 44 KDE x86_64, fprintd
`1.94.5-5.fc44`, libfprint `1.94.100-1.fc44`, Plasma 6.7.5, systemd 259.8,
polkit 127, SONAME `libfprint-2.so.2` e SELinux disabilitato. Il Flatpak SDK
Freedesktop 25.08 locale chiude le build senza rete; i pacchetti `-devel` host
non sono installati e non sono necessari al builder canonico.

Non sono stati verificati con un vero nuovo UID/KCM: ACL effettive del laptop,
decisioni PolicyKit, rilascio della GUI installata, journal del servizio,
creazione/rimozione account, mount, storage autentico e comportamento USB.
Questi limiti non possono trasformare i mock in `PASS_LIVE`.

## Sequenza e recovery preservate, ma non eseguibili

Il percorso progettato resta descritto in
`operator_kit/live_probe/experiments/d293-kde-new-user/README_IT.md`: utente
originale, deployment transiente, creazione KDE post-deploy, attesa del valore
`READY_FOR_NEW_USER`, sessione del nuovo UID, dito non già registrato,
duplicate-check, enrollment, chiusura KCM, fino a tre VERIFY, riapertura per
delete, logout e recovery dall'utente originale. La sessione originale può
restare aperta senza altri consumer fingerprint; password e richieste Polkit
restano nella UI e mai nei log.

La capture progettata vive in
`/var/tmp/goodix-d293-04-captures/<run-id>/capture/`. `recover.sh` resta
utilizzabile solo per un'eventuale predisposizione precedente/interrotta:
propaga rollback, non elimina account o contenitori su identità/mount/template
ambigui e conserva la capture. Non è un comando per avviare una nuova run.

```text
EXECUTABLE_CLOSURE=PASS_OFFLINE_LIVE_ENTRYPOINTS_BLOCKED
R1_TO_R6=CORRECTED_OFFLINE
R7=PARTIAL_CORRECTED_BLOCKED_PREACTION_GUI_BUDGET
R8=CORRECTED
REAL_USB=0
SUDO_ROOT_OR_PKEXEC_EXECUTED_BY_AI=0
PROTECTED_MATERIAL_READ_BY_AI=false
LIVE_EXECUTED_BY_AI=false
PM_DECISION=HUMAN_REQUIRED
NEXT_BOUNDARY=USER_DECISION_ON_R7_PREACTION_ENFORCEMENT
```
