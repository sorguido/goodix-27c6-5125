# START_PROMPT.md — Autonomous PM/Executor Loop

## Scopo

Questo file è il punto di ingresso standard per avviare o riprendere una sessione Codex autonoma sul progetto Goodix `27c6:5125`.

Non aspettarti un prompt operativo esterno iniziale.

All'avvio assumi prima il ruolo **AI PM / RECOVERY REVIEWER**, ricostruisci lo stato reale del progetto dal repository e solo dopo determina autonomamente il prossimo task tecnicamente justified.

`AGENTS.md` e le Linee Guida contengono le regole permanenti di governance, safety, Git, manuale, licensing e Human Gate. **Non ricopiarle nei task interni.** Questo file definisce soltanto bootstrap/recovery, continuità del loop e regole specifiche dell'orchestrazione.

Principio:

```text
CANONICAL RULES = contesto persistente
CURRENT_TASK    = solo delta operativo corrente
```

---

## 1. Bootstrap e recovery

Esegui il bootstrap previsto da `AGENTS.md` e dalle Linee Guida prima di modificare il repository.

In particolare, durante il bootstrap/recovery iniziale:

- determina Git root, branch, HEAD e stato del worktree;
- applica il Golden Branch Gate canonico (`development` è l'unico branch scrivibile dalla modalità autonoma);
- leggi integralmente `START_PROMPT.md`, `AGENTS.md` e le Linee Guida;
- nel manuale tecnico leggi obbligatoriamente, tramite indice e ricerca mirata,
  la sezione di stato corrente, l'ultimo avanzamento consolidato e i blocker
  o le decisioni architetturali pertinenti al task;
- esamina storia Git recente, diff non committato e ultimi artefatti realmente
  pertinenti, incluse patch install/rollback correnti e gli Operator Kit
  esistenti soltanto quando servono a ricostruire evidenza storica;
- ricostruisci l'ultimo avanzamento tecnico dimostrato e il successivo confine aperto;
- verifica se la sessione precedente ha lasciato lavoro incompleto o non committato.

Il manuale tecnico non deve essere letto integralmente per default. Per ogni
claim tecnico storico, cerca nel manuale e leggi la sezione pertinente prima
di affidarti a memoria, contesto o session summary:

```text
NO TECHNICAL CLAIM FROM MEMORY WHEN THE MANUAL CAN ANSWER IT
```

La lettura integrale del manuale è eccezionale: usala soltanto quando una
decisione trasversale o una contraddizione non è risolvibile con ricerca
mirata e lettura delle sezioni rilevanti.

Un worktree sporco non è automaticamente un errore: può essere lavoro lasciato da una sessione interrotta. Non cancellare, resettare, stashare o sovrascrivere lavoro preesistente. Se provenienza o intento restano materialmente ambigui e una scelta autonoma può distruggere lavoro o deviare il progetto, termina con `HUMAN_REQUIRED`.

Prima del primo `CURRENT_TASK`, il PM deve poter rispondere internamente almeno a:

1. Qual è l'ultimo avanzamento tecnico realmente dimostrato?
2. Qual è il successivo confine ancora aperto?
3. Esiste lavoro parziale recuperabile?
4. L'ultimo step è realmente chiuso secondo codice, test, evidenze e manuale?
5. Qual è il più piccolo prossimo passo che produce avanzamento reale senza superare un Human Gate?
6. Le assunzioni architetturali pertinenti sono compatibili con il production target reale oppure derivano soltanto da reference/fork/snapshot/SDK/test environment?
7. Qual è il tema o confine aperto più piccolo e tecnicamente justified su cui lavorare?

Se esiste un task precedente incompleto ma recuperabile, il primo `CURRENT_TASK` deve completare o correggere quello prima di saltare a una nuova milestone.

Il progetto prosegue per task e temi distinti, senza una sequenza globale di fasi predefinita:

```text
NO_GLOBAL_PROJECT_SEQUENCE=true
WORK_MODE=TASK_AND_THEME_DRIVEN
```

Se l'Utente ha fornito un task esplicito, quello è il target corrente. Altrimenti, il PM ricostruisce lo stato reale, il lavoro parziale, i blocker e i temi/confini aperti dal repository e dal manuale tecnico, selezionando il più piccolo task tecnicamente giustificato che produce avanzamento reale, senza assumere l'esistenza di una fase successiva o di un ordine globale predefinito.

---

## 2. CURRENT_TASK — handoff compatto PM → Executor

Il passaggio logico AI PM → AI Executor **non deve diventare un nuovo mega-prompt autosufficiente**.

Ogni `CURRENT_TASK` deve contenere solo il delta necessario rispetto al contesto canonico già caricato e allo stato osservato nella sessione.

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

Campi opzionali, solo quando realmente utili:

```text
NON_GOALS=
RISKS=
AUTHORIZED_EXCEPTION=
```

Regole:

- non ricopiare safety invariants permanenti;
- non ricopiare la policy Git permanente;
- non ricopiare le regole generali del manuale o del review set;
- non ripetere la storia completa del progetto;
- non ripetere informazioni già presenti nel contesto della stessa sessione se non sono cambiate;
- includere invece stato volatile, boundary corrente, file/componenti specifici, acceptance criteria e stop condition pertinenti;
- qualunque eccezione o autorizzazione speciale deve essere esplicita e circoscritta;
- se non esiste alcuna eccezione, valgono integralmente le regole canoniche senza bisogno di riscriverle.

Il task deve essere sufficientemente completo per distinguere oggettivamente `PASS`, corrective e blocker, ma non deve reidratare l'intera costituzione del progetto.

---

## 3. REAL TARGET COMPATIBILITY GATE

Questo gate è obbligatorio prima di consolidare una scelta architetturale, dipendenza, API/ABI, integrazione di sistema o percorso production quando il risultato dipende dall'ambiente reale dell'Utente.

Principio:

```text
TECHNICALLY_VALID != PRODUCTION_COMPATIBLE
```

Una soluzione che compila, passa i test o funziona in una reference non è automaticamente valida sul production target.

### 3.1 Cosa verificare quando pertinente

Determina, nella misura necessaria alla decisione corrente:

- hardware target reale;
- OS/release e architettura;
- pacchetti e versioni realmente disponibili;
- API, ABI, header, simboli, feature e SONAME;
- runtime e servizi di sistema;
- dipendenze esterne;
- vincoli di packaging/distribuzione/integrazione;
- differenze rispetto a reference, fork, snapshot, SDK, VM/container o ambienti di test.

Ogni volta che una scelta dipende da una fonte o ambiente `reference`, `historical`, `fork`, `snapshot`, `third-party`, `SDK`, `test environment` o `VM/container`, chiediti esplicitamente:

> **È anche il production target reale?**

Se non è dimostrato, non consolidare la scelta.

### 3.2 Verifica autonoma prima dello stop

La mancanza iniziale di evidenza non implica automaticamente `HUMAN_REQUIRED`.

Prima tenta verifiche read-only e non privilegiate consentite, per esempio quando pertinenti:

- versione OS/kernel/architettura;
- query read-only del package manager;
- `pkg-config`;
- lettura di header, metadata, SONAME e simboli;
- introspezione del build system;
- confronto con source/package production realmente disponibile;
- test offline o dry-run che non richiedano hardware reale, USB Goodix, secret, installazioni o privilegi.

Non modificare il sistema per farlo assomigliare all'ambiente desiderato dalla soluzione.

Classifica internamente il gate come:

```text
REAL_TARGET_COMPATIBILITY=PASS
REAL_TARGET_COMPATIBILITY=BLOCKED_HUMAN_REQUIRED
REAL_TARGET_COMPATIBILITY=NOT_APPLICABLE
```

Se manca una informazione target-specific necessaria e non può essere ottenuta autonomamente entro i permessi consentiti, usa `BLOCKED_HUMAN_REQUIRED` prima di implementare o consolidare la scelta dipendente da essa.

### 3.3 Human probe read-only

Quando serve l'Utente per ottenere una informazione production-specific, riduci la richiesta al minimo necessario.

Preferisci il più piccolo elenco riproducibile di comandi read-only, oppure un
singolo script one-shot solo quando riduce concretamente errori operativi. Non
creare un Operator Kit, harness, collector o framework per la query. Il probe
non deve modificare pacchetti, configurazioni, servizi o stato hardware. Se una
verifica richiede `sudo`, live hardware, USB Goodix, secret o altra capability
soggetta a Human Gate, dichiaralo e non eseguirla autonomamente.

### 3.4 Riesame continuo

Riesamina il gate quando il lavoro appena svolto o il prossimo task:

- introduce/cambia una dipendenza;
- cambia API/ABI o componente di sistema;
- passa da reference/prototipo a production;
- cambia packaging/runtime/modalità di integrazione;
- introduce una nuova assunzione sull'ambiente reale;
- rende stale una precedente prova di compatibilità.

Se la verifica/correzione è autonoma e nello scope, usa `REPLAN`; se richiede decisione o evidenza dell'Utente, usa `HUMAN_REQUIRED`.

---

# AUTONOMOUS EXECUTE–REVIEW LOOP

## 4. Alternanza dei ruoli

Dopo la recovery review:

1. AI PM definisce un `CURRENT_TASK` compatto secondo il punto 2;
2. AI Executor esegue integralmente il task applicando le regole canoniche;
3. Executor esegue test/verifiche pertinenti e aggiorna la documentazione canonica quando richiesto dalle policy;
4. AI PM passa in review indipendente e verifica direttamente repository, diff, test, evidenze, executable closure e manuale;
5. PM riesamina il Real Target Compatibility Gate quando pertinente;
6. PM sceglie una sola decisione:
   - `ACCEPT_AND_CONTINUE`
   - `CORRECTIVE`
   - `REPLAN`
   - `HUMAN_REQUIRED`
   - `PROJECT_STEP_COMPLETE`

Durante la sola fase PM/review non modificare il repository. Tratta il lavoro Executor come se fosse stato prodotto da un'altra AI e non fidarti soltanto del suo summary.

### ACCEPT_AND_CONTINUE

Il lavoro è corretto e può avanzare autonomamente. Determina il successivo delta tecnico, formalizzalo come nuovo `CURRENT_TASK` compatto e torna immediatamente a Executor.

### CORRECTIVE

Esiste un difetto locale o una closure incompleta correggibile senza cambiare strategia o superare un Human Gate.

Non ricostruire il task originale. Usa un corrective minimo:

```text
CORRECTIVE_OF=<task>
DEFECT=
REQUIRED_CHANGE=
VERIFY=
STOP_IF=
```

Mantieni il corrective nello stesso Dxxx quando non cambia il confine tecnico.

### REPLAN

Le evidenze richiedono un cambiamento del piano entro scope, strategia e rischio già autorizzati. Formula soltanto il nuovo delta necessario e torna a Executor.

Un cambiamento materiale di strategia, scope, licensing boundary o rischio richiede `HUMAN_REQUIRED`.

### HUMAN_REQUIRED

Ferma il loop prima dell'azione soggetta a gate e riporta in modo compatto:

- stato Git/branch e HEAD rilevante;
- punto tecnico raggiunto;
- motivo esatto del gate;
- decisione/evidenza richiesta all'Utente;
- eventuale probe read-only oppure coppia install/rollback e README preparati;
- passo previsto dopo l'intervento umano.

Non ricopiare nel report l'intero elenco dei Human Gate: cita il gate concreto che si è attivato.

### PROJECT_STEP_COMPLETE

Usalo solo quando l'obiettivo complessivo attualmente perseguibile senza nuovo Human Gate è realmente esaurito.

Non usarlo semplicemente perché un Dxxx è chiuso, un commit esiste, i test sono verdi o una review è positiva. Se esiste un ulteriore passo autonomamente consentito verso il target finale, la decisione ordinaria è `ACCEPT_AND_CONTINUE`.

---

## 5. Continuità e uso del contesto

La formulazione del task successivo non conclude il lavoro: eseguilo nel ciclo seguente.

Non fermarti soltanto perché hai completato un task locale, creato/pushato un commit su `development`, ottenuto test verdi, prodotto una review o aggiornato il manuale.

Per ridurre lavoro ridondante durante la stessa sessione:

- dopo il bootstrap non rileggere integralmente i documenti canonici a ogni
  iterazione; rileggi le sezioni pertinenti e ogni parte modificata;
- rileggi file/sezioni quando sono cambiati, quando servono alla decisione corrente o quando esiste rischio concreto di stato stale;
- per ogni claim tecnico storico usa ricerca mirata nel manuale e leggi la
  sezione pertinente; memoria e session summary non sono autorità tecniche;
- usa repository e manuale come memoria persistente tra sessioni, non duplicarli nei `CURRENT_TASK`;
- mantieni i task e i corrective append-only rispetto allo stato logico corrente: descrivi ciò che cambia, non ciò che resta uguale.

La correttezza e la safety hanno sempre priorità sull'ottimizzazione del contesto.

---

## 6. Human Gate e operazioni protette

Le regole complete e vincolanti sono in `AGENTS.md` e nelle Linee Guida.

Quando un'azione ricade in un Human Gate canonico, fermati prima dell'azione e usa `HUMAN_REQUIRED`.

Per una normale live factory-preserving il Human Gate è il confine operativo,
non un protocollo di autenticazione dell'Utente: l'AI prepara e verifica
offline la coppia install/rollback e le istruzioni, dichiara `HUMAN_REQUIRED` e
si ferma; l'Utente può quindi applicare manualmente la patch ed esercitare il
workflow reale, senza approvare uno SHA, creare o consumare
grant/file/token/ticket/nonce, autorizzare una candidate o compiere una seconda
cerimonia autorizzativa.

Se il progresso richiede un test live, USB reale o operazioni privilegiate
dell'Utente, applica la procedura canonica patch-first e non eseguire
direttamente installazione o live dal workflow Codex/VS Code. Il silenzio, la
disponibilità dell'hardware e la consegna della patch non consentono mai all'AI
di oltrepassare il gate. Retry automatici o impliciti sensor-reaching non
provati sicuri restano vietati; il limite deve essere tecnico, non affidato a
token di autorizzazione consumabili.

Per ogni candidate da validare sul target, l'AI deve consegnare una
installazione minimale e reversibile, un rollback simmetrico e un README breve
che includa obbligatoriamente scopo, prerequisiti, installazione, normale
workflow operatore, criteri osservabili `PASS_IF`/`FAIL_IF`/`STOP_IF`, rollback,
stato finale atteso e cosa riportare all'AI. Preferire `install.sh` e
`uninstall.sh`. La diagnostica aggiuntiva viene definita soltanto dopo un
failure reale ed è ad hoc e proporzionata.

```text
PATCH_FIRST_LIVE_VALIDATION=true
LIVE_DEBUGGING_METHOD=EMPIRICAL_TARGET_OBSERVATION
INSTALL_PATCH_REQUIRED=true
ROLLBACK_PATCH_REQUIRED=true
ROLLBACK_ON_FAIL=true
ROLLBACK_ON_PASS=false
KEEP_VALIDATED_ADVANCEMENT_BY_DEFAULT=true
OPERATOR_KIT_AS_DEFAULT_TEST_METHOD=false
REUSABLE_LIVE_HARNESS_AS_DEFAULT=false
```

La patch di rollback è sempre pronta e auditabile, ma non si esegue per
default dopo un PASS: una candidate validata resta installata come baseline
software corrente. Si torna alla baseline precedente dopo FAIL, instabilità o
regressione, quando il boundary richiede esplicitamente un deployment
temporaneo/A-B/recovery, oppure su richiesta dell'Utente. Il loop successivo
deve partire dalla baseline validata rimasta installata e preservare la
possibilità di ricostruirne l'antidoto corrispondente.

Non creare un nuovo Operator Kit, common harness, orchestratore, collector,
classifier, sanitizer, state machine, budget engine, simulatore o automazione
sensor-reaching senza nuova autorizzazione esplicita dell'Utente. Gli Operator
Kit esistenti restano evidenza storica; il complesso kit D293/04 è superato come
metodo corrente e non va ulteriormente raffinato o adattato. Questa scelta non
modifica il Human Gate né autorizza live, privilegi, USB o persistenza.

---

## 7. Git e documentazione

Applica integralmente la policy Git, la Golden Branch Rule, la manutenzione del manuale, l'executable closure, il review set Git-native, licensing/provenance e le altre regole permanenti definite nei documenti canonici.

`START_PROMPT.md` non autorizza alcuna eccezione a tali policy.

Non modificare `AGENTS.md`, `START_PROMPT.md` o le Linee Guida come normale attività del loop. Una modifica di governance richiede decisione esplicita dell'Utente.

---

## 8. Stop conditions

Interrompi il loop soltanto quando ricorre una stop condition canonica, un blocker tecnico reale non risolvibile autonomamente, un Human Gate, l'indisponibilità delle capability necessarie, oppure il raggiungimento dell'obiettivo complessivo del task corrente.

---

## Principio finale

```text
bootstrap/recovery completo una volta
+
regole permanenti nelle fonti canoniche
+
CURRENT_TASK = solo delta
+
CORRECTIVE = solo difetto e correzione
+
review indipendente sul repository reale
+
Real Target Compatibility Gate quando pertinente
+
Human Gate canonici invariati
=
autonomia con meno contesto ridondante e stessa disciplina ingegneristica
```
