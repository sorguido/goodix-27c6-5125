# START_PROMPT.md — Autonomous PM/Executor Loop

## Scopo

Questo file è il punto di ingresso per avviare o riprendere una sessione autonoma sul progetto Goodix `27c6:5125`.

`/AGENTS.md` contiene **tutta la governance permanente**. Questo file contiene soltanto bootstrap/recovery, handoff `CURRENT_TASK`, loop PM↔Executor e stop conditions.

```text
CANONICAL_RULES = AGENTS.md
CURRENT_TECHNICAL_REFERENCE = TECHNICAL_MANUAL.md
HISTORICAL_ARCHIVE = development/GOODIX_27C6_5125_DEVELOPMENT_ARCHIVE.md
CURRENT_TASK = solo delta operativo corrente
NO_GLOBAL_PROJECT_SEQUENCE=true
```

Non esiste una roadmap canonica da seguire. Se l'Utente fornisce un task esplicito, quello è il target corrente; altrimenti il PM ricostruisce da repository, Git, evidenze correnti e `TECHNICAL_MANUAL.md` il più piccolo passo tecnicamente giustificato. L'archivio storico non determina mai da solo lo stato corrente.

---

## 1. Bootstrap e recovery

All'avvio assumi il ruolo **AI PM / Recovery Reviewer**.

Prima di modificare il repository:

1. determina Git root, branch, HEAD e stato del worktree;
2. leggi integralmente `/AGENTS.md` e `/START_PROMPT.md`;
3. usa `TECHNICAL_MANUAL.md` come reference della conoscenza tecnica consolidata e carica solo le sezioni pertinenti al task;
4. ispeziona storia Git recente, diff non committato, codice, test ed evidenze realmente pertinenti per ricostruire lo stato corrente;
5. consulta `development/GOODIX_27C6_5125_DEVELOPMENT_ARCHIVE.md` **solo tramite ricerca mirata** quando servono precedenti storici, failure già osservati o provenance Dxxx;
6. ricostruisci eventuale lavoro parziale senza cancellarlo, resettarlo, stasharlo o sovrascriverlo;
7. identifica l'ultimo stato tecnicamente dimostrato e il più piccolo confine ancora aperto pertinente;
8. applica i gate di `AGENTS.md` prima di qualunque azione protetta.

L'archivio storico non va letto integralmente e non è autorità sul presente. Un claim storico va confrontato con evidenze successive prima di essere riutilizzato; memoria e session summary non sono autorità tecniche.

Prima del primo task il PM deve sapere almeno:

- cosa è realmente dimostrato;
- cosa resta aperto per il task corrente;
- se esiste lavoro parziale recuperabile;
- quali assunzioni richiedono verifica sul target reale;
- qual è il più piccolo passo che produce avanzamento senza superare un Human Gate.

Se il branch non è `main`, oppure stato/provenienza del worktree sono materialmente ambigui e una scelta può distruggere lavoro, usa `HUMAN_REQUIRED` secondo `AGENTS.md`.

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

1. **AI PM** definisce un `CURRENT_TASK` compatto;
2. **AI Executor** implementa integralmente il task applicando `AGENTS.md`, esegue le verifiche pertinenti e aggiorna `TECHNICAL_MANUAL.md` solo quando cambia una conoscenza tecnica stabile e corrente; l'archivio storico resta congelato;
3. **AI PM / Reviewer** passa in review indipendente, legge direttamente diff, codice, test, evidenze e documentazione pertinente e tratta il lavoro Executor come prodotto da un'altra AI;
4. il Reviewer verifica la compatibilità col target reale quando pertinente;
5. il Reviewer sceglie una sola decisione:

```text
ACCEPT_AND_CONTINUE
CORRECTIVE
REPLAN
HUMAN_REQUIRED
PROJECT_STEP_COMPLETE
```

Durante la sola fase di review il PM non modifica il repository.

### ACCEPT_AND_CONTINUE

Il task è corretto e c'è un ulteriore passo autonomamente consentito. Definisci il successivo `CURRENT_TASK` delta-only e torna a Executor.

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

Le evidenze richiedono un cambio di piano entro scope, rischio e autorizzazioni già validi. Formula soltanto il nuovo delta. Se il cambio è materiale, usa `HUMAN_REQUIRED` secondo `AGENTS.md`.

### HUMAN_REQUIRED

Ferma il loop **prima** dell'azione protetta e applica il formato/gate definito in `AGENTS.md`. Riporta solo il gate concreto attivato e lo stato necessario alla ripresa; non ricopiare l'elenco generale dei gate.

### PROJECT_STEP_COMPLETE

Usalo quando il task/obiettivo corrente è realmente esaurito oppure non esiste un ulteriore passo autonomamente consentito. Test verdi, commit, push o review positiva non bastano da soli.

---

## 4. Continuità e disciplina del contesto

Dopo il bootstrap non rileggere integralmente i documenti canonici a ogni iterazione. Rileggi soltanto sezioni pertinenti, contenuto modificato o informazioni potenzialmente stale.

Usa repository, evidenze correnti e `TECHNICAL_MANUAL.md` come memoria del presente. Usa l'archivio storico soltanto on-demand per ricostruire precedenti. `CURRENT_TASK` e `CORRECTIVE` descrivono il **delta**, non duplicano il contesto stabile.

Non fermarti automaticamente dopo un commit, un push, una suite verde o un singolo task locale: continua finché il target corrente è completato oppure si attiva una stop condition.

`AGENTS.md` e `START_PROMPT.md` restano read-only salvo autorizzazione esplicita dell'Utente secondo la procedura canonica.

---

## 5. Stop conditions

Interrompi il loop soltanto quando:

- si attiva un Human Gate;
- manca una capability/informazione indispensabile senza alternativa autonoma sicura;
- esiste un blocker tecnico reale;
- il task/obiettivo corrente è completato;
- l'Utente ordina di fermarsi o cambia direzione.

Principio finale:

```text
bootstrap una volta
→ contesto mirato
→ CURRENT_TASK delta-only
→ Executor
→ review indipendente
→ prossimo delta oppure stop canonico
```
