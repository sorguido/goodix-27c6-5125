<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix host-only orchestrator (O001 + O002 + O003)

`orchestration/` contiene il core deterministico O001, il loop reale Codex/Git
sintetico O002 e il servizio local-first O003. Il dominio resta separato da
Goodix USB, protected material, `sudo`, live, pubblicazione e aggiornamenti
autonomi di `main`.

L'architettura adotta il paradigma Symphony (supervisore persistente,
state-machine, task isolati e recovery), ma non installa Symphony: il codice è
project-authored e il low-level agent harness reale è Codex App Server.

Il tick ordinario collega realmente contesti distinti PM-plan, Executor e
PM-review. Il coordinatore deterministico crea il manifest e il worktree,
tipizza commit/push/FF e applica `CORRECTIVE`, `REPLAN`, `HUMAN_GATE`, `PAUSE`,
`ACCEPT` e `DONE`; l'AI non possiede direttamente l'autorità sugli effetti Git.

## Topologia Git canonica

```text
main                 Human Gate soltanto
  ^
development          integrazione autonoma persistente, FF/CAS soltanto
  ^
task/<TASK_ID>       un solo branch/worktree effimero
```

`CORRECTIVE` riusa lo stesso task branch. Dopo `ACCEPT`, l'orchestratore
verifica head reviewato, expected-old, ancestry, FF local/remote e reachability;
solo allora rimuove worktree e branch task. Qualunque failure o ambiguità
preserva le evidenze.

Il `development` canonico non viene creato dall'head O003 non ancora accettato.
Dopo review, merge Human-gated O003 in `main` e ottenimento dello SHA accettato
`M`, l'attivazione prevista è l'operazione deterministica:

```text
development assente -> create local/remote esattamente a M -> reread == M
```

oppure una riconciliazione FF/CAS esplicitamente valida. Mai reset, rebase o
force push.

## Installazione locale

Da `<git-root>/orchestration`, installare il package nel profilo utente con il
meccanismo Python scelto dall'operatore, in modo che
`~/.local/bin/goodix-orchestrator` esista. Nessuna installazione richiede root.

Configurare repository e Human Authority in modo esplicito:

```bash
goodix-orchestrator configure \
  --repository-root <git-root> \
  --github-repository sorguido/goodix-27c6-5125-private \
  --authorized-github-user-id <NUMERIC_GITHUB_ID> \
  --authorized-github-login <LOGIN>
```

Il numeric ID è l'authority anchor; il login è cross-check leggibile. Non sono
accettati account inferiti. Il config non contiene token/email/secret: `gh api`
usa l'autenticazione già gestita da GitHub CLI. Se `gh` manca o non è
autenticato, installazione/login restano prerequisiti manuali.

Installare la sola unità utente e avviarla:

```bash
goodix-orchestrator install-service
systemctl --user enable --now goodix-orchestrator.service
```

La unit è inclusa come risorsa del package, quindi `install-service` funziona
anche da wheel non-editable. L'installer genera un drop-in con gli esatti path
canonici verificati per Git common-dir, config/state e worktree XDG:
`KillMode=control-group`, single-instance lock, `NoNewPrivileges`,
`PrivateDevices`, `RestrictSUIDSGID`, repository read-only salvo le superfici
Git/XDG strettamente necessarie, nessuna credential e nessun path repository
hard-coded nella risorsa distribuita. La compatibilità effettiva va verificata
con:

```bash
systemd-analyze --user verify ~/.config/systemd/user/goodix-orchestrator.service
systemctl --user status goodix-orchestrator.service
```

Rollback reversibile:

```bash
systemctl --user disable --now goodix-orchestrator.service
goodix-orchestrator uninstall-service
```

L'uninstall rimuove solo l'esatta unità utente; config, stato e backup restano
per recovery e possono essere rimossi manualmente soltanto dopo review.

## Controlli operatore

```bash
goodix-orchestrator status
goodix-orchestrator pause
goodix-orchestrator resume
goodix-orchestrator stop
goodix-orchestrator maintenance-enter
goodix-orchestrator maintenance-exit
goodix-orchestrator emergency-stop
goodix-orchestrator emergency-clear
goodix-orchestrator backup
```

`status` è read-only e redatto. `pause` impedisce nuovi turn/effect; verificare
`NO_INFLIGHT_TURN=true` e `NO_INFLIGHT_EFFECT=true` prima dello stop ordinario.
Questi due indicatori sono derivati dai ledger persistenti dei turni e degli
effetti, non da flag dichiarativi modificabili dall'operatore.
`stop` arresta il service tree senza inventare transizioni macchina.

`emergency-stop` persiste prima il latch e poi arresta l'unità. Il latch
sopravvive a restart/login e `resume` non può cancellarlo; un avvio con latch
termina con successo senza dispatch, quindi non innesca una restart storm con
`Restart=on-failure`. Dopo aver
riconciliato eventuali effetti in-flight, soltanto l'azione locale esplicita
`emergency-clear` lo rimuove.

Maintenance richiede quiescenza, persiste main/development/task e blocca
dispatch, FF e cleanup. `maintenance-exit` esegue fetch/prune e riconcilia
Git+SQLite: cambi FF comportano replan del task stale; divergenza causa
`PAUSED_INFRASTRUCTURE`, senza merge/rebase automatici. L'aggiornamento del
manuale da parte del workflow manuale è obbligatorio quando cambia conoscenza,
ma non sostituisce la riconciliazione.

## Human Gate GitHub

Il gate crea/riconcilia una issue privata con summary redatto e binding locale
di repository, issue node/number/body digest, numeric user ID/login, `GATE_ID`,
`TASK_ID`, commit/ref, action ID e action digest. Sono autoritativi soltanto:

```text
/approve <GATE_ID>
/deny <GATE_ID>
```

come singola riga esatta, sull'issue esatta, dall'identità configurata. Email,
ChatGPT, reazioni, PR review, quote o prosa fuzzy sono notification/help surface,
non approval bus. La decisione è terminale; replay o baseline/azione diversa
richiedono un nuovo gate.

In `HUMAN_GATE_WAIT` non partono PM, Executor, task, commit, FF o retry modello.
Il servizio può soltanto riconciliare gate, health/re-probe bounded e comandi
operatore.

## Quota e modello

`PAUSED_RATE_LIMIT` e `PAUSED_MODEL_UNAVAILABLE` non fanno fallback a API key,
pay-as-you-go, provider alternativo o modello/effort diverso. Il servizio locale
esegue un re-probe conservativo (default 900 secondi) di account ChatGPT,
rate-limit e catalogo modello tramite Codex App Server, seguito da un turno
bounded, read-only e senza tool sull'esatta coppia modello/effort. Riprende solo
dopo output atteso, route effettiva riosservata e riconciliazione di store, Git,
task/worktree, gate, turn ledger ed effetti; il probe non avanza il task.

## Stato, log e recovery

- config: `${XDG_CONFIG_HOME:-~/.config}/goodix-orchestrator/config.json`;
- DB: `${XDG_STATE_HOME:-~/.local/state}/goodix-orchestrator/state.sqlite`;
- backup: sottodirectory `backups/`, API SQLite consistente, retention 5;
- log: stdout/stderr strutturato e redatto sotto journald, con rotazione
  system-managed.

Schema O003: v6. Store operativi v1/v2/v3/v4/v5 incompatibili non vengono migrati
inventando metadata; restano fail-closed. SQLite non conserva prompt/reasoning,
token, email, PSK, protected material, biometria o environment dump.

`ERROR_LOCKED` richiede ricostruzione deterministica dell'esito esterno prima
di qualunque retry. `PAUSED_INFRASTRUCTURE` espone il prerequisito operatore e
non degrada policy.

## Test e qualification

```bash
cd <git-root>/orchestration
python -m compileall -q goodix_orchestrator tests
python -W error::ResourceWarning -m unittest discover -s tests -v
python -m goodix_orchestrator --help
systemd-analyze --user verify systemd/goodix-orchestrator.service
python -m goodix_orchestrator.service_qualification \
  --repository <repo-disposable> \
  --state-dir <xdg-state-disposable>
python -m goodix_orchestrator.service_qualification --real-codex \
  --repository <repo-disposable> \
  --state-dir <xdg-state-disposable>
```

La suite deterministica copre anche crash dopo plan, Executor, review, FF,
cleanup e creazione issue, con checkpoint di fase e identità logiche di
dispatch persistite. Un risultato strutturato completato viene conservato in
forma bounded per impedire un secondo turno dopo crash. Gli effetti Git/GitHub
distinguono `NO_EFFECT`, `COMPLETED` e stato ambiguo prima del retry.

Il loop production completo su repository
disposable: PM plan, task/worktree/commit/push, review, `CORRECTIVE` sullo stesso
branch, seconda review, `ACCEPT`, FF di `development`, cleanup e `DONE`, con
`main` invariato. La CI non richiede USB, root, secret, GitHub auth o interazione
Human reale. Il drill GitHub reale deve restare distinto dalla coverage fake. La qualifica
Codex sintetica O002 resta disponibile con
`python -m goodix_orchestrator.qualification --real-codex ...`.

O003 non rende ancora l'orchestrazione pronta per Goodix: restano necessarie la
prova negativa sul repository/service reale e la decisione Human sul merge.
Restano falsi:

```text
ORCHESTRATION_READY_FOR_GOODIX=false
CURRENT_LIVE_AUTHORIZED=false
GOODIX_FUNCTIONAL_ADVANCEMENT=NONE
LIVE_RUNNER_ENABLED=false
```

Tutto il codice O001–O003 è project-authored `GPL-2.0-or-later`; non incorpora
Rockytkg, OEM, capture, biometria o materiale protetto.
