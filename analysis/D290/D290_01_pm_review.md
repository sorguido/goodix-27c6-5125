<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D290/01 — review PM pre-live

## Decisione

```text
PM_DECISION=ACCEPT_AND_CONTINUE_TO_HUMAN_GATE
OUTCOME=READY_FOR_HUMAN_GATE_AFTER_FIRST_PRE_AUDIT_CORRECTIVE
ADVANCEMENT=PLASMALOGIN_ONE_SHOT_LIVE_BOUNDARY_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=PASS_OFFLINE_PLUS_TARGET_READ_ONLY_ASSESSMENT
RESIDUAL_BLOCKER_OR_RISK=MANUAL_LOGOUT_REAL_GREETER_AND_ONE_SENSOR_VERIFY
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
LIVE_EXECUTION_PERFORMED=false
```

## Riesame indipendente

La review ha verificato direttamente:

- capture integra della prima invocazione su baseline `1a8c5528...`, chiusa
  `FAIL_PRE_AUDIT` con payload non avviato, post-audit/cleanup PASS e zero
  azioni sensore;
- root cause del vecchio filtro `State=active` e predicati distinti per il
  desktop tty2 ancora loggato (`active|online`) e per la nuova sessione con ID
  causalmente diverso;
- classificazione pulita del pre-audit fallito senza richiedere artefatti del
  payload mai avviato;

- target Fedora 44: `display-manager.service=plasmalogin.service`, daemon root
  nel cgroup system, pacchetto 6.7.5, service PAM effettivo e hash di PAM,
  daemon, helper e greeter;
- sorgente upstream KDE `v6.7.5` al commit
  `e63894e7923db053413915ea582db2757303ca8f`: submit esplicito dal greeter,
  service PAM `plasmalogin`, helper root, authenticate/account/open-session e
  creazione/attivazione sessione;
- compatibilità del common harness col lifecycle da TTY, senza modifiche al
  common e senza daemonizzazione aggiuntiva;
- candidato PAM byte-identico al file Fedora salvo una sola riga fingerprint
  bounded; fallback/account/password/session invariati;
- ordine fail-closed di daemon/namespace/hash prima del mount, mount read-only,
  helper pipe-bounded, cleanup/recovery hash-pinned;
- un solo submit operatore, un solo PAM `max-tries=1`, una sola epoch ammessa e
  zero retry; nessun loop per un secondo tentativo;
- causalità distinta MATCH → nuova sessione Wayland logind e NO_MATCH → zero
  nuova sessione; entrambe rilasciano l'overlay prima del post-audit o del
  recupero password;
- assenza di logout/terminate/unlock automatici, USB diretto e comandi sensore
  persistenti nel payload.

La prima passata di review ha corretto tre failure potenziali senza cambiare
boundary: race fra outcome SIGFM ed emissione dell'epoch finale, journal
plasmalogin raccolto troppo presto e assunzione errata che il processo greeter
resti nel cgroup `session-N.scope`. Il payload attende ora l'unica epoch
completa, raccoglie il journal dopo l'esito sessione e accetta soltanto i due
cgroup utente previsti dal percorso PAM/systemd, verificando separatamente
l'unica sessione logind `Service=plasmalogin-greeter`, `Class=greeter`.

La diagnostica di errore non dichiara più ripristinato l'overlay quando il
cleanup non è confermato: in quel caso vieta il login e indica la recovery da
TTY.

## Verifiche

- `bash -n`: PASS per i sei eseguibili e la libreria session-model D290;
- vero `run.sh d290-plasmalogin --offline-test` da cwd esterna: PASS;
- contratti D290: `23/23 PASS`;
- common harness: `13/13 PASS`;
- regressione combinata common harness + D286–D290: `215/215 PASS`;
- `git diff --check`: PASS;
- `shellcheck`: non disponibile sul target.

Le prove offline non invocano `pkexec`, PAM fingerprint, logout, mount,
fprintd, USB o sensore. Il comando operatore è direttamente eseguibile, senza
grant/token/file di autorizzazione separato, ma resta Human Gate perché provoca
logout, overlay PAM runtime e una VERIFY reale.
