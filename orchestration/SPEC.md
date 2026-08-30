# Goodix Autonomous Orchestration — Architecture & Safety Specification

> **Versione**: Draft v0.1 — 30 agosto 2026  
> **Stato**: AI-PM authored; candidato alla review/merge umano, non canonico finché non integrato in `main`.  
> **Scope**: solo infrastruttura di orchestrazione host-only. Nessun avanzamento funzionale Goodix, nessun USB reale, nessun `sudo`, nessun secret reale, nessuna esecuzione live.

---

## 1. Scopo

Questa specifica definisce il servizio locale che deve rimuovere l'Utente dal ruolo di relay continuo tra **AI Project Manager (AI PM)** e **AI esecutrice**, preservando integralmente la governance v2.6 del progetto Goodix 27c6:5125.

Il servizio deve permettere il ciclo:

```text
AI PM -> AI esecutrice -> AI PM -> decisione
                              |
                              +-> ACCEPT -> task successivo
                              +-> CORRECTIVE -> AI esecutrice
                              +-> REPLAN -> AI PM
                              +-> HUMAN_GATE -> stop e notifica Utente
                              +-> PAUSE -> stop recuperabile
                              +-> DONE -> fine
```

L'orchestratore è un **coordinatore deterministico non-AI**. Non interpreta evidenze tecniche, non decide safety o architettura, non amplia scope e non può trasformare una decisione `HUMAN_GATE` in `ACCEPT`.

Questa specifica è subordinata a:

1. decisione/Human Gate corrente dell'Utente;
2. `Linee Guida di Progetto Goodix 27c6 5125 per AI.md` v2.6 o successiva;
3. `AGENTS.md` coerente con la governance corrente;
4. manuale tecnico canonico per lo stato tecnico.

In caso di conflitto, questa SPEC deve essere corretta; non prevale sulla governance.

---

## 2. Principi normativi

L'implementazione MUST rispettare i seguenti principi:

1. **Human authority senza human relay** — l'Utente decide i gate materiali, ma non trasferisce manualmente prompt e risultati ordinari.
2. **Factory-preserving assoluto** — l'automazione non introduce alcuna eccezione a firmware/PSK/OTP/factory/persistent-state invariants.
3. **Capability separation** — USB, root, secret reali, `main`, history rewrite e pubblicazione non devono essere protetti soltanto da prosa.
4. **Fail-closed** — stato ambiguo, quota esaurita, modello non disponibile, baseline incoerente o gate pendente bloccano il flusso.
5. **No paid fallback** — nessun passaggio automatico ad API pay-as-you-go, crediti a consumo o provider a pagamento.
6. **Git-native state** — codice, review set e documentazione devono essere verificabili nel repository; il runtime state deve essere persistente e ricostruibile.
7. **Idempotenza** — reboot/crash non devono causare doppia esecuzione involontaria di effetti esterni.
8. **No hidden downgrade** — PM ed Executor devono usare soltanto modelli presenti nell'allow-list e disponibili al momento dell'esecuzione.
9. **Least privilege** — ogni processo possiede solo le capability necessarie al proprio ruolo.
10. **Goodix freeze** — finché non è soddisfatta la bootstrap closure, nessun nuovo boundary funzionale Goodix viene eseguito dall'autopilot.

Le parole MUST, MUST NOT, SHOULD, SHOULD NOT e MAY sono normative.

---

## 3. Obiettivi e non-obiettivi

### 3.1 Obiettivi

Il bootstrap deve produrre un servizio locale capace di:

- mantenere due ruoli AI distinti: PM ed Executor;
- avviare/riprendere sessioni tramite il runtime Codex programmabile;
- trasferire automaticamente task e risultati;
- creare worktree/task branch isolati;
- mantenere un branch di integrazione autonomo separato da `main`;
- ottenere review AI PM su diff/test/manuale reali;
- gestire `ACCEPT`, `CORRECTIVE`, `REPLAN`, `HUMAN_GATE`, `PAUSE`, `DONE`;
- persistere lo stato e riprendere dopo restart;
- rilevare quota/modello indisponibile e sospendere senza fallback a pagamento;
- generare Human Gate auditabili tramite GitHub privato;
- dimostrare che l'Executor host-only non può raggiungere Goodix, root o `main`;
- produrre log strutturati redatti senza secret.

### 3.2 Non-obiettivi del bootstrap

Il bootstrap MUST NOT:

- eseguire USB Goodix;
- accedere a protected material/PSK reali;
- usare `sudo` o root;
- installare libfprint/fprintd/PAM;
- eseguire Windows VM/OEM sul sensore;
- fare merge in `main` autonomamente;
- modificare history Git;
- pubblicare nel repository pubblico;
- riprendere il boundary tecnico Goodix;
- creare un framework general-purpose multi-repository;
- replicare Symphony integralmente;
- introdurre dashboard web, database server, Redis, queue broker o dipendenze infrastrutturali non necessarie.

Il primo servizio deve essere piccolo, locale, auditabile e facilmente disattivabile.

---

## 4. Attori e trust boundary

### 4.1 Utente — Human Authority

L'Utente:

- mantiene autorità finale;
- riceve Human Gate soltanto quando necessario;
- può approvare o negare un gate;
- può sospendere l'autopilot in qualunque momento;
- mantiene il gate su `main`, live, root, scope materiale, history rewrite e pubblicazione.

### 4.2 AI PM autonomo

Nell'autopilot il ruolo AI PM è una **sessione separata GPT-5.6 Sol nel runtime Codex**, non questa specifica conversazione ChatGPT.

Ragione: il client locale non dispone di un'interfaccia supportata per inviare autonomamente turni a questa chat e recuperarne le risposte. Il ruolo PM deve quindi essere trasferibile a un endpoint programmabile mantenendo modello, fonti canoniche, regole e criteri di review.

Requisiti:

- modello iniziale richiesto: `GPT-5.6 Sol` nella denominazione effettivamente pubblicizzata dal runtime Codex;
- nessun downgrade silenzioso;
- se Sol non è disponibile: `PAUSE_MODEL_UNAVAILABLE`;
- il PM non deve avere accesso live al sensore;
- il PM SHOULD essere Git read-only durante la normale review;
- il PM riceve task precedente, risultato Executor, diff, test, stato canonico e manuale aggiornato;
- il PM emette una disposition strutturata.

Questa chat ChatGPT resta il canale umano per:

- decisioni strategiche;
- audit dell'orchestratore;
- eventuali modifiche di governance;
- discussione dei Human Gate quando l'Utente lo desidera.

### 4.3 AI esecutrice

L'Executor usa Codex in un thread distinto dal PM.

Requisiti:

- modello scelto dal PM tra quelli autorizzati dalla governance corrente;
- worktree/task branch dedicato;
- shell host-only;
- nessun accesso Goodix;
- nessun root/sudo;
- nessun secret reale;
- nessuna credenziale che consenta update di `main`;
- nessuna capability di pubblicazione;
- commit solo sul task branch assegnato.

### 4.4 Orchestratore deterministico

È un processo locale non-AI. Possiede soltanto logica di coordinamento e policy meccanica.

MUST:

- mantenere la state machine;
- parlare con Codex App Server;
- creare/riprendere thread;
- validare i manifest;
- gestire worktree/ref autorizzati;
- persistere stato;
- applicare capability allow-list;
- aprire/leggere Human Gate tramite adapter GitHub;
- arrestarsi su condizioni non autorizzate.

MUST NOT:

- decidere autonomamente che un rischio è accettabile;
- riscrivere un task tecnico;
- ampliare scope;
- inventare un commit live;
- concedere USB/root/secret;
- approvare un proprio gate.

### 4.5 Live Runner futuro

Non appartiene alla prima implementazione.

Quando verrà introdotto, sarà un processo deterministico separato dall'Executor e potrà eseguire soltanto una azione live esplicitamente legata a:

- `GATE_ID`;
- commit/ref;
- launcher/azione;
- policy one-shot;
- approvazione valida dell'Utente.

Fino ad allora `LIVE_RUNNER_ENABLED=false`.

---

## 5. Architettura logica minima

```text
                         GitHub private
                     Human Gate / notification
                               ^
                               |
+-------------------------------------------------------------+
|                    GOODIX ORCHESTRATOR                       |
|                                                             |
|  State Store  Policy Engine  Git Manager  Gate Adapter      |
|       |             |             |             |            |
|       +-------------+-------------+-------------+            |
|                             |                               |
|                     Codex App-Server Client                  |
|                       /                 \                    |
|                      /                   \                   |
|             PM THREAD                     EXECUTOR THREAD    |
|           GPT-5.6 Sol                    allowed model      |
|                 |                            |               |
|                 +---------- review ----------+               |
+-------------------------------------------------------------+
                              |
                        task worktree
                              |
                     autonomous integration
                           branch only

main ------------------------------------------------ HUMAN GATE
USB/root/secrets ------------------------------------ HUMAN GATE
```

Il bootstrap SHOULD essere implementato come singolo servizio locale con moduli separati, non come microservizi.

---

## 6. Componenti obbligatori

### 6.1 Supervisor

Responsabile del lifecycle del servizio:

- startup;
- lock di istanza singola;
- load/reconcile stato;
- event loop;
- shutdown pulito;
- restart recovery.

MUST impedire due orchestratori concorrenti sullo stesso state directory.

### 6.2 Policy Engine

Valida:

- stato corrente;
- transition richiesta;
- capability;
- branch/ref;
- gate pendenti;
- modello;
- quota;
- operazioni Git.

La policy è deny-by-default.

### 6.3 Codex Adapter

Il runtime iniziale è Codex App Server, processo long-lived JSON-RPC bidirezionale.

L'adapter MUST:

- inizializzare il server;
- verificare account/auth;
- interrogare `model/list` o superficie equivalente corrente;
- leggere `account/rateLimits/read` quando disponibile;
- creare/riprendere thread PM ed Executor;
- inviare turn;
- consumare eventi fino a completion/failure;
- gestire `usageLimitExceeded`, session budget, unauthorized, sandbox e transport failure;
- persistere thread IDs come cache recuperabile, non come unica fonte dello stato progetto;
- non affidarsi a API/shape undocumented senza test di compatibilità.

La superficie App Server corrente espone concetti quali `thread/start`, `thread/resume`, `turn/start`, `model/list`, account/rate-limit read, notifiche di completion e richieste bidirezionali di approval. L'implementazione MUST capability-discover e testare la versione realmente installata invece di assumere che ogni dettaglio del protocollo resti immutabile.

### 6.4 Git Manager

Gestisce esclusivamente operazioni allow-listed:

- creazione worktree;
- creazione task branch;
- commit Executor;
- push task branch;
- fast-forward del branch di integrazione dopo `ACCEPT`;
- apertura/aggiornamento PR private se configurato.

MUST rifiutare:

- update non fast-forward;
- merge `main`;
- rebase;
- amend;
- force push;
- reset distruttivo;
- delete branch non previsto;
- modifica Git config globale/utente.

### 6.5 State Store

Il formato iniziale SHOULD essere file JSON atomico o SQLite locale singolo-file. La scelta implementativa deve privilegiare:

- transazioni/atomicità;
- backup semplice;
- ispezionabilità umana;
- nessun servizio esterno.

Lo state store MUST contenere solo metadata operativi, mai secret.

### 6.6 Human Gate Adapter

Adapter iniziale preferito: issue GitHub nel repository privato.

Responsabilità:

- creare/aggiornare gate;
- includere summary redatto;
- leggere commenti/decisioni;
- verificare identità autorizzata;
- accettare soltanto sintassi strutturata;
- impedire replay.

### 6.7 Structured Logger

MUST produrre log macchina con:

- timestamp;
- run/task/turn/gate ID;
- old/new state;
- disposition;
- operazione Git;
- error class;
- model selected;
- quota state redatta.

MUST NOT loggare:

- PSK;
- secret/protected material;
- token auth;
- environment completo;
- body di file sensibili;
- biometric data.

---

## 7. State machine

### 7.1 Stati normativi

```text
BOOTSTRAP
IDLE
PM_PLANNING
TASK_READY
EXECUTOR_RUNNING
EXECUTOR_RESULT_READY
PM_REVIEWING
HUMAN_GATE_WAIT
PAUSED_RATE_LIMIT
PAUSED_MODEL_UNAVAILABLE
PAUSED_INFRASTRUCTURE
DONE
ERROR_LOCKED
```

### 7.2 Transizioni principali

```text
BOOTSTRAP -> IDLE
IDLE -> PM_PLANNING
PM_PLANNING -> TASK_READY
TASK_READY -> EXECUTOR_RUNNING
EXECUTOR_RUNNING -> EXECUTOR_RESULT_READY
EXECUTOR_RESULT_READY -> PM_REVIEWING

PM_REVIEWING + ACCEPT     -> PM_PLANNING | DONE
PM_REVIEWING + CORRECTIVE -> TASK_READY
PM_REVIEWING + REPLAN     -> PM_PLANNING
PM_REVIEWING + HUMAN_GATE -> HUMAN_GATE_WAIT
PM_REVIEWING + PAUSE      -> PAUSED_*
PM_REVIEWING + DONE       -> DONE

HUMAN_GATE_WAIT + APPROVE -> stato autorizzato specificato dal gate
HUMAN_GATE_WAIT + DENY    -> PM_PLANNING | DONE

PAUSED_* -> stato precedente recuperabile dopo reconciliation
```

Qualunque transizione non esplicitamente ammessa è vietata.

### 7.3 `ERROR_LOCKED`

Entrare in `ERROR_LOCKED` quando:

- state store corrotto/non riconciliabile;
- ref Git osservata non compatibile con lo stato persistito;
- task branch modificato fuori orchestrazione in modo ambiguo;
- approval replay/identity mismatch;
- capability enforcement non verificabile;
- impossibile determinare se una azione con effetto esterno sia già avvenuta.

Uscita da `ERROR_LOCKED` richiede Human Gate o riparazione deterministica esplicitamente prevista.

---

## 8. Identificatori e idempotenza

Ogni ciclo deve avere identificatori stabili:

```text
RUN_ID
TASK_ID
TURN_ID
GATE_ID
BASELINE_SHA
RESULT_SHA
```

Formato raccomandato:

```text
ORCH-YYYYMMDD-NNN
TASK-YYYYMMDD-NNN
HG-YYYYMMDD-NNN
```

Ogni operazione con effetto esterno deve registrare un idempotency record prima/dopo l'esecuzione.

Esempi:

- branch create;
- commit/push;
- fast-forward integration branch;
- issue create/update;
- futura live run.

Dopo restart l'orchestratore MUST prima riconciliare lo stato reale e poi decidere se riprendere. Non deve "provare di nuovo" alla cieca.

---

## 9. Contratto task PM -> Executor

Il PM deve emettere sia contenuto Markdown leggibile sia un manifest strutturato validabile.

Schema concettuale minimo:

```json
{
  "protocol_version": "1.0",
  "task_id": "TASK-...",
  "parent_task_id": null,
  "title": "...",
  "objective": "...",
  "baseline_sha": "40-hex",
  "integration_branch": "...",
  "task_branch": "...",
  "model_policy": {
    "preferred": "...",
    "allowed": ["..."]
  },
  "gate_class": "HOST_ONLY",
  "capabilities_required": ["HOST_READ", "WORKTREE_WRITE", "TASK_COMMIT"],
  "scope": {
    "paths": ["..."],
    "non_goals": ["..."]
  },
  "acceptance_criteria": ["..."],
  "manual_update_required": true,
  "stop_conditions": ["..."]
}
```

Il manifest è il contratto macchina. Il Markdown completa il contesto tecnico.

L'orchestratore MUST rifiutare il task se:

- capability non consentita;
- baseline non corrisponde;
- modello fuori allow-list;
- `gate_class` sconosciuta;
- task ID già concluso;
- Human Gate pendente.

---

## 10. Contratto Executor -> PM

L'Executor deve restituire un completion manifest strutturato più una sintesi leggibile.

Schema minimo:

```json
{
  "protocol_version": "1.0",
  "task_id": "TASK-...",
  "outcome": "READY",
  "advancement": "...",
  "executable_closure": "PASS",
  "residual_blocker_or_risk": "...",
  "canonical_documentation": {
    "manual_updated": true,
    "sections": ["..."]
  },
  "review_set": {
    "baseline_sha": "...",
    "head_sha": "...",
    "changed_paths": ["..."]
  },
  "tests": [
    {"command": "...", "status": "PASS"}
  ],
  "policy_assertions": {
    "usb_open_count": 0,
    "sudo_used": false,
    "protected_material_accessed": false,
    "main_modified": false
  }
}
```

Il PM non deve fidarsi del manifest senza verificare almeno:

- Git state;
- diff;
- test evidence disponibile;
- manuale;
- path modificati;
- policy assertions verificabili dall'infrastruttura.

---

## 11. Contratto PM disposition

La disposition primaria MUST essere esattamente una tra:

```text
ACCEPT
CORRECTIVE
REPLAN
HUMAN_GATE
PAUSE
DONE
```

Schema minimo:

```json
{
  "protocol_version": "1.0",
  "task_id": "TASK-...",
  "disposition": "ACCEPT",
  "reason": "...",
  "reviewed_head_sha": "...",
  "findings": [],
  "next": {
    "action": "PLAN_NEXT_HOST_ONLY_TASK"
  }
}
```

Regole:

- `ACCEPT` richiede `reviewed_head_sha` esatto;
- `CORRECTIVE` deve restare nello stesso boundary quando possibile;
- `REPLAN` può cambiare metodo ma non capability/scope materiale;
- `HUMAN_GATE` deve includere gate manifest;
- `PAUSE` deve classificare quota/modello/infrastruttura;
- `DONE` non genera nuovi task.

L'orchestratore non deve inferire una disposition da testo libero. Se il JSON manca/non valida: `ERROR_LOCKED` o ritorno al PM per una sola rigenerazione strutturale senza side effect.

---

## 12. Capability model

### 12.1 Capability host-only iniziali

```text
HOST_READ
WORKTREE_WRITE
TASK_COMMIT
TASK_PUSH
INTEGRATION_FF
PRIVATE_PR_WRITE
PRIVATE_GATE_ISSUE_WRITE
PUBLIC_NETWORK_READ
CODEX_APP_SERVER
```

Queste capability sono concedibili soltanto secondo scope e policy.

### 12.2 Capability protette

```text
PROTECTED_MATERIAL_REAL
USB_GOODIX
ROOT_SUDO
WINDOWS_USB_GOODIX
RUNTIME_INSTALL
MAIN_MERGE
HISTORY_REWRITE
PUBLICATION
LIVE_RUNNER
```

Durante il bootstrap:

```text
PROTECTED_MATERIAL_REAL=false
USB_GOODIX=false
ROOT_SUDO=false
WINDOWS_USB_GOODIX=false
RUNTIME_INSTALL=false
MAIN_MERGE=false
HISTORY_REWRITE=false
PUBLICATION=false
LIVE_RUNNER=false
```

Il processo Executor non deve ricevere queste capability neppure se il modello le richiede.

### 12.3 Enforcement

Il bootstrap deve dimostrare almeno due livelli:

1. **policy-level deny**;
2. **OS/runtime-level impossibility** quando praticabile.

Per Goodix USB il test finale del bootstrap deve dimostrare che l'Executor non possiede accesso utile al device node. Il semplice prompt `do not use USB` non è sufficiente.

---

## 13. Git/worktree lifecycle

### 13.1 Branch canonici del flusso

- `main`: branch umano/canonico; autopilot non lo modifica.
- branch di integrazione autonomo: nome configurabile, inizialmente raccomandato `orchestration/integration` durante bootstrap e successivamente un nome dedicato al flusso Goodix.
- task branch: un branch per task/corrective logicamente separato.

### 13.2 Creazione task

Per ogni nuovo task:

1. verificare integration ref;
2. creare task branch dalla exact integration SHA;
3. creare worktree dedicato;
4. registrare baseline SHA;
5. avviare Executor soltanto nel worktree.

### 13.3 Accept

Dopo `ACCEPT` PM:

1. verificare `reviewed_head_sha` == task branch HEAD;
2. verificare ancestry;
3. avanzare integration branch **solo fast-forward**;
4. persistere nuova integration SHA;
5. generare task successivo dalla nuova baseline.

Nessun merge commit automatico è necessario nel bootstrap.

### 13.4 Reject/corrective

`CORRECTIVE` SHOULD continuare sullo stesso task branch salvo ragione tecnica documentata.

`REPLAN` MAY creare un nuovo task branch se il piano precedente viene abbandonato, ma deve preservare provenance e non cancellare il branch/evidenza precedente automaticamente.

---

## 14. Modello, autenticazione e quota

### 14.1 Autenticazione

Il bootstrap deve usare l'autenticazione Codex associata al piano ChatGPT disponibile sul PC dell'Utente, non API key pay-as-you-go.

Secret/token auth non devono entrare nello state store o nei log.

### 14.2 Model discovery

All'avvio e prima di ogni dispatch rilevante:

- interrogare i modelli disponibili;
- verificare preferred/allowed model;
- non inventare alias;
- persistere l'identificatore effettivo usato nel run metadata.

Per il PM iniziale, se GPT-5.6 Sol non è disponibile, il sistema va in `PAUSED_MODEL_UNAVAILABLE`.

### 14.3 Rate limit

Quando disponibile, `account/rateLimits/read` o superficie equivalente deve essere consultata e gli aggiornamenti rate-limit devono essere trattati come telemetry.

In ogni caso `usageLimitExceeded`/session-budget equivalente deve causare `PAUSED_RATE_LIMIT`.

MUST NOT:

- consumare automaticamente crediti aggiuntivi;
- comprare/reset credit;
- passare a API key;
- scegliere automaticamente un provider a pagamento alternativo.

La ripresa dopo reset quota deve riconciliare baseline e stato prima di continuare.

---

## 15. Human Gate

### 15.1 Gate manifest

Ogni gate contiene:

```json
{
  "gate_id": "HG-...",
  "task_id": "TASK-...",
  "decision_required": "...",
  "reason": "...",
  "commit_sha": "...",
  "action_to_unlock": "...",
  "residual_risks": ["..."],
  "still_forbidden": ["..."],
  "requested_by": "AI_PM",
  "status": "PENDING"
}
```

### 15.2 Approval syntax

Forma iniziale:

```text
/approve <GATE_ID>
/deny <GATE_ID>
```

Il gate adapter MUST verificare:

- repository corretto;
- issue/gate corretto;
- comment author autorizzato;
- ID esatto;
- stato ancora PENDING;
- commit/ref invariato se il gate è commit-bound.

### 15.3 Replay protection

Dopo APPROVED/DENIED il gate è terminale.

Una nuova live attempt o nuova baseline richiede un nuovo gate ID.

### 15.4 Notification

Le normali notifiche GitHub/email/mobile sono sufficienti per il bootstrap. Non introdurre un mail sender separato finché non emerge una necessità reale.

---

## 16. Crash recovery e reconciliation

Al bootstrap/restart:

1. acquisire instance lock;
2. leggere state store;
3. verificare repo/root;
4. verificare integration branch/ref;
5. verificare eventuale task branch/worktree;
6. verificare thread state Codex se recuperabile;
7. verificare Human Gate;
8. classificare l'ultima azione esterna;
9. solo dopo scegliere la transizione.

Il sistema deve distinguere almeno:

```text
NOT_STARTED
IN_PROGRESS
COMPLETED_UNREVIEWED
REVIEWED_ACCEPTED
WAITING_HUMAN
PAUSED
AMBIGUOUS
```

`AMBIGUOUS` -> `ERROR_LOCKED`.

---

## 17. Security boundary del bootstrap

Prima di dichiarare il servizio pronto, i test devono dimostrare:

- Executor non può aprire Goodix;
- Executor non può usare `sudo`/root;
- PM non può aprire Goodix;
- né PM né Executor possono aggiornare `main`;
- orchestratore rifiuta update non fast-forward;
- gate pending blocca realmente dispatch;
- approval con identity errata viene ignorata/bloccata;
- approval per gate/commit obsoleto viene rifiutata;
- log/state non contengono secret;
- quota esaurita non causa fallback a pagamento;
- restart non duplica commit/push/gate.

La verifica deve preferire test eseguibili e capability negative reali a semplici assert documentali.

---

## 18. Bootstrap validation plan

### Phase A — Unit/state-machine

Nessun Codex necessario.

Testare:

- transizioni valide/invalide;
- schema task/result/disposition/gate;
- idempotency records;
- policy capability;
- Git command allow-list;
- redaction.

### Phase B — Fake agents

Sostituire PM/Executor con stub deterministici.

Eseguire almeno:

1. `ACCEPT -> next task -> DONE`;
2. `CORRECTIVE -> ACCEPT`;
3. `REPLAN -> ACCEPT`;
4. `HUMAN_GATE -> APPROVE -> resume`;
5. `HUMAN_GATE -> DENY`;
6. `PAUSE_RATE_LIMIT -> resume`;
7. crash tra commit e state update;
8. crash tra gate creation e state update.

### Phase C — Real Codex synthetic repo

Usare repository/worktree sintetico privo di Goodix.

Scenario minimo:

- PM genera task semplice;
- Executor implementa;
- PM rileva un difetto preordinato;
- PM emette `CORRECTIVE`;
- Executor corregge;
- PM `ACCEPT`;
- integration branch avanza;
- task successivo conclude `DONE`.

L'Utente non deve effettuare alcun relay.

### Phase D — Real repository, orchestration-only

Usare il repository Goodix reale ma modificare soltanto file dell'infrastruttura orchestration o documentazione a basso rischio.

Dimostrare:

- lettura governance/manuale;
- task branch/worktree;
- review reale;
- manuale aggiornato se necessario;
- integration fast-forward;
- nessun USB/root/secret/main.

### Phase E — Human Gate end-to-end

Generare gate sintetico innocuo e dimostrare:

- issue/notifica;
- stop;
- approval identity-bound;
- resume;
- replay rejection.

### Phase F — Hardening readiness

Solo dopo A-E:

- systemd user service o equivalente;
- restart/reboot recovery;
- log rotation;
- backup state;
- operator commands minimi `status`, `pause`, `resume`, `stop`;
- dry-run capability audit.

---

## 19. Criteri per `ORCHESTRATION_READY_FOR_GOODIX=true`

Il flag può essere emesso dall'AI PM soltanto se tutti i seguenti criteri sono verificati:

1. loop PM -> Executor -> PM reale senza relay umano;
2. tutte le disposition esercitate almeno in test, incluse `HUMAN_GATE` e `PAUSE`;
3. crash recovery verificata;
4. Goodix USB non raggiungibile dall'Executor host-only;
5. `sudo` non disponibile all'Executor;
6. `main` non modificabile dal loop autonomo;
7. integration branch solo fast-forward dopo exact `ACCEPT` SHA;
8. Human Gate identity/commit bound e replay-safe;
9. quota/modello fail-closed, nessun fallback pay-as-you-go;
10. PM reviewa diff/test/manuale reali;
11. nessun secret in log/state/gate;
12. ciclo sintetico completo PASS;
13. ciclo reale low-risk sul repository PASS;
14. `AGENTS.md` e governance non contraddetti dall'implementazione;
15. review set bootstrap disponibile e verificabile.

Anche dopo questo flag, la ripresa del progresso tecnico Goodix richiede Human Gate/decisione esplicita dell'Utente secondo la governance v2.6.

---

## 20. Struttura repository raccomandata

La prima implementazione SHOULD convergere verso una struttura simile:

```text
orchestration/
  SPEC.md
  README.md
  pyproject.toml              # se Python viene scelto
  goodix_orchestrator/
    __init__.py
    supervisor.py
    state.py
    policy.py
    protocols.py
    codex_adapter.py
    git_manager.py
    gate_adapter.py
    logging.py
    cli.py
  tests/
    test_state_machine.py
    test_policy.py
    test_protocols.py
    test_git_manager.py
    test_gate_adapter.py
    test_crash_recovery.py
    fixtures/
```

Python è una scelta raccomandata per il bootstrap per semplicità, disponibilità su Fedora, process management, JSON/SQLite e velocità di audit; non è però un requisito normativo se un'altra scelta offre meno complessità reale.

---

## 21. Implementation sequence raccomandata

Dopo approvazione/merge di questa SPEC, la costruzione dovrebbe essere suddivisa in pochi vertical slice, non micro-task artificiali:

### O001 — Deterministic core

- state machine;
- manifest schemas;
- state persistence;
- policy/capability engine;
- fake-agent tests;
- crash/idempotency unit tests.

### O002 — Codex + Git minimal loop

- App Server adapter;
- PM/Executor thread separation;
- model/rate-limit handling;
- worktree/task branch;
- PM review;
- integration fast-forward;
- synthetic real-Codex cycle.

### O003 — Human Gate + service hardening

- GitHub gate adapter;
- identity/replay/commit binding;
- pause/resume;
- systemd user service;
- restart reconciliation;
- end-to-end gate test.

### O004 — Real-repo low-risk qualification

- un ciclo orchestration-only nel repository Goodix;
- capability negative tests;
- review finale;
- decisione `ORCHESTRATION_READY_FOR_GOODIX`.

Il live runner non appartiene a O001-O004 salvo come interfaccia/stub non eseguibile.

---

## 22. Dipendenze e semplicità

La prima implementazione SHOULD usare la standard library quando ragionevole.

Dipendenze esterne devono essere giustificate. In particolare evitare per default:

- web framework;
- ORM;
- message broker;
- Redis;
- container orchestration;
- database server;
- background queue esterna.

Il sistema deve poter essere compreso e riprodotto da una persona che legge repository, SPEC e manuale senza conoscere le chat di progetto.

---

## 23. External technical anchors

La SPEC usa come riferimento concettuale, non come dipendenza runtime:

- OpenAI Symphony: orchestrator state autoritativo, workspace isolati, agent runner, policy versionata e human handoff;
- OpenAI Codex App Server: processo long-lived con protocollo JSON-RPC bidirezionale, thread/turn lifecycle, model discovery, account/rate-limit surface, eventi/approval.

Poiché queste superfici evolvono, l'implementazione deve verificare la versione Codex installata e coprire l'adapter con test. Le linee guida di progetto e questa SPEC restano il contratto di comportamento del nostro sistema; un cambiamento dell'API Codex non autorizza automaticamente un cambiamento di safety policy.

---

## 24. Questioni deliberatamente rinviate

Non sono blocker per O001:

- nome definitivo del branch di integrazione per il futuro lavoro Goodix;
- UI/dashboard opzionale;
- eventuale retention policy avanzata dei thread Codex;
- live runner reale;
- modalità futura di delega di protected-material preflight;
- eventuale supporto ad altri executor/modelli.

Queste decisioni devono essere prese solo quando diventano necessarie.

---

## 25. Principio sintetico

```text
AI autonomy
+ deterministic coordinator
+ capability separation
+ Git-native evidence
+ persistent state
+ human gates only where material
+ fail-closed quota/model handling
= no human relay without surrendering human authority
```
