# START_PROMPT.md — Autonomous PM/Executor Loop

## Scopo

Questo file è il punto di ingresso per avviare o riprendere una sessione autonoma sul progetto Goodix `27c6:5125`.

`/AGENTS.md` contiene **tutta la governance permanente**. Questo file contiene soltanto bootstrap/recovery, handoff `CURRENT_TASK`, loop PM↔Executor e stop conditions.

```text
CANONICAL_RULES = AGENTS.md
CANONICAL_ROADMAP = ROADMAP.md
OPERATIVE_STATE_CACHE = PROJECT_STATE.json
CURRENT_TECHNICAL_REFERENCE = TECHNICAL_MANUAL.md
HISTORICAL_ARCHIVE = development/Goodix 27c6 5125 manuale tecnico.md
CURRENT_TASK = solo delta operativo corrente
GLOBAL_PROJECT_SEQUENCE = ROADMAP.md
```

`ROADMAP.md` è la sequenza canonica da P0 fino alla chiusura del progetto. `PROJECT_STATE.json` accelera la ripresa ma non è autoritativo: se è stale o confligge con Git/evidenze/roadmap, il PM lo ripara. Un task esplicito dell'Utente ha priorità, ma non autorizza implicitamente a saltare gate o cambiare la roadmap protetta. L'archivio storico non determina mai da solo lo stato corrente.

---

## 1. Bootstrap e recovery

All'avvio assumi il ruolo **AI PM / Recovery Reviewer**.

Prima di modificare il repository:

1. determina Git root, branch corrente, HEAD e stato del worktree;
2. se il branch corrente non è determinabile con certezza o l'ambiente presenta
   segnali discordanti, fermati con `HUMAN_REQUIRED` /
   `GATE=BRANCH_SELECTION_REQUIRED`; non inferire il branch e non eseguire
   checkout/switch autonomamente;
3. leggi integralmente `/AGENTS.md`, `/START_PROMPT.md` e `/ROADMAP.md`;
4. leggi `/PROJECT_STATE.json`, confrontalo con Git/evidenze e riparalo se stale;
5. individua la fase attiva della roadmap, gli EXIT_GATE già soddisfatti e il primo requisito ancora aperto;
6. usa `TECHNICAL_MANUAL.md` come reference della conoscenza tecnica consolidata e carica solo le sezioni pertinenti alla fase/task;
7. ispeziona storia Git recente, diff non committato, codice, test ed evidenze realmente pertinenti per ricostruire lo stato corrente;
8. consulta `development/Goodix 27c6 5125 manuale tecnico.md` **solo tramite ricerca mirata** quando servono precedenti storici, failure già osservati o provenance;
9. ricostruisci eventuale lavoro parziale senza cancellarlo, resettarlo, stasharlo o sovrascriverlo;
10. identifica il più piccolo passo tecnicamente giustificato **dentro la fase attiva**;
11. applica i gate di `AGENTS.md` e `ROADMAP.md` prima di qualunque azione protetta.

L'archivio storico non va letto integralmente e non è autorità sul presente. Un claim storico va confrontato con evidenze successive prima di essere riutilizzato; memoria e session summary non sono autorità tecniche.

Prima del primo task il PM deve sapere almeno:

- qual è la fase corrente di `ROADMAP.md`;
- quali gate sono realmente già dimostrati;
- qual è il primo requisito non soddisfatto della fase;
- se `PROJECT_STATE.json` coincide con Git/evidenze;
- se esiste lavoro parziale recuperabile;
- quali assunzioni richiedono verifica sul target reale;
- qual è il più piccolo passo che produce avanzamento senza superare un Human Gate.

Il branch operativo è il branch corrente selezionato dall'Utente nell'ambiente.
Non esiste un nome di branch hard-coded nel bootstrap. Se il branch non è
osservabile in modo univoco, oppure stato/provenienza del worktree sono
materialmente ambigui e una scelta può distruggere lavoro, usa
`HUMAN_REQUIRED` secondo `AGENTS.md`.

---

## 2. CURRENT_TASK — PM → Executor

Il passaggio PM → Executor non deve diventare un mega-prompt autosufficiente.

Formato predefinito:

```text
CURRENT_TASK=<id o descrizione breve>
GOAL=
STATE_DELTA=
SCOPE=
REQUIRED_WORK=
VERIFY=
STOP_IF=
```

Campi opzionali solo quando utili:

```text
NON_GOALS=
RISKS=
AUTHORIZED_EXCEPTION=
```

Regole:

- includere soltanto informazioni cambiate o specifiche del task;
- non ricopiare governance, safety, Git, Human Gate, licensing o regole documentali già in `AGENTS.md`;
- non ripetere la storia completa del progetto;
- includere file/componenti interessati, acceptance criteria e stop condition pertinenti;
- qualunque eccezione deve essere esplicita, specifica e già autorizzata dall'Utente.

---

## 3. Execute–Review Loop

Dopo il bootstrap:

1. **AI PM** definisce un `CURRENT_TASK` compatto sul primo requisito aperto della fase corrente;
2. **AI Executor** implementa integralmente il task applicando `AGENTS.md` e `ROADMAP.md`, esegue le verifiche pertinenti e aggiorna `TECHNICAL_MANUAL.md` solo quando cambia una conoscenza tecnica stabile e corrente; l'archivio storico resta separato;
3. **AI PM / Reviewer** passa in review indipendente, legge direttamente diff, codice, test, evidenze e documentazione pertinente e tratta il lavoro Executor come prodotto da un'altra AI;
4. il Reviewer verifica la compatibilità col target reale quando pertinente;
5. dopo un avanzamento accettato il PM aggiorna `PROJECT_STATE.json` con fase, gate, artefatti, prossimo passo e HEAD verificato;
6. il Reviewer sceglie una sola decisione:

```text
ACCEPT_AND_CONTINUE
CORRECTIVE
REPLAN
HUMAN_REQUIRED
BLOCKED
MILESTONE_COMPLETE
```

Durante la sola fase di review il PM non modifica il repository.

### ACCEPT_AND_CONTINUE

Il task è corretto e c'è un ulteriore passo autonomamente consentito nella fase corrente. Se l'EXIT_GATE della fase è ora soddisfatto, registra il gate in `PROJECT_STATE.json`, avanza alla fase `NEXT` di `ROADMAP.md` e seleziona il suo primo requisito aperto. Definisci quindi il successivo `CURRENT_TASK` delta-only e torna a Executor.

### CORRECTIVE

Difetto locale correggibile senza cambiare strategia o superare un gate:

```text
CORRECTIVE_OF=
DEFECT=
REQUIRED_CHANGE=
VERIFY=
STOP_IF=
```

### REPLAN

Le evidenze richiedono un cambio di piano entro la fase corrente, scope, rischio e autorizzazioni già validi. Formula soltanto il nuovo delta. Se il cambio altera fase, EXIT_GATE, strategia canonica o profilo di rischio, usa `HUMAN_REQUIRED` per una modifica esplicita di `ROADMAP.md`.

### HUMAN_REQUIRED

Ferma il loop **prima** dell'azione protetta e applica il formato/gate definito in `AGENTS.md`. Riporta solo il gate concreto attivato e lo stato necessario alla ripresa; non ricopiare l'elenco generale dei gate.

### BLOCKED

Usalo solo quando una capability, informazione o evidenza indispensabile manca e non esiste un percorso autonomo sicuro equivalente. Registra il blocker in `PROJECT_STATE.json`.

### MILESTONE_COMPLETE

Usalo **solo** quando P11 ha chiuso `FINAL_DOCUMENTATION_AND_RELEASE_READINESS=PASS`. Un singolo task, una fase intermedia, test verdi, commit, push o review positiva non bastano.

---

## 4. Continuità e disciplina del contesto

Dopo il bootstrap non rileggere integralmente i documenti canonici a ogni iterazione. Rileggi soltanto sezioni pertinenti, contenuto modificato o informazioni potenzialmente stale.

Usa repository, evidenze correnti, `ROADMAP.md`, `PROJECT_STATE.json` e `TECHNICAL_MANUAL.md` come memoria del presente. Usa l'archivio storico soltanto on-demand per ricostruire precedenti. `CURRENT_TASK` e `CORRECTIVE` descrivono il **delta**, non duplicano il contesto stabile.

Non fermarti automaticamente dopo un commit, un push, una suite verde, un singolo task locale o la chiusura di una fase: continua alla fase successiva finché si attiva una stop condition canonica.

`AGENTS.md`, `START_PROMPT.md` e `ROADMAP.md` restano read-only salvo autorizzazione esplicita dell'Utente secondo la procedura canonica. `PROJECT_STATE.json` deve invece essere mantenuto dal PM.

---

## 5. Stop conditions

Interrompi il loop soltanto quando:

- si attiva un Human Gate previsto da `AGENTS.md` o `ROADMAP.md`;
- manca una capability/informazione indispensabile senza alternativa autonoma sicura;
- esiste un blocker tecnico reale;
- P11 raggiunge `FINAL_DOCUMENTATION_AND_RELEASE_READINESS=PASS` e quindi `MILESTONE_COMPLETE`;
- l'Utente ordina di fermarsi o cambia direzione.

Principio finale:

```text
bootstrap una volta
→ ROADMAP + PROJECT_STATE
→ contesto mirato della fase
→ CURRENT_TASK delta-only
→ Executor
→ review indipendente
→ update PROJECT_STATE
→ fase/task successivo oppure stop canonico
```
