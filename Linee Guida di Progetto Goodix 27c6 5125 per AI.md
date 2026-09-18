# Linee Guida di Progetto Goodix 27c6:5125 per AI

> **Versione**: 3.4 — Revisione 17 settembre 2026
> **Stato**: Attivo; sostituisce la v3.3 del 14 settembre 2026
> **Motivazione**: la v3.4 recepisce il passaggio dall'orchestrazione per fasi (roadmap A→F) al lavoro per task e temi distinti senza una sequenza globale predefinita. Mantiene integralmente Human Gate, safety, invarianti factory-preserving, protezioni Git, licensing, target Fedora KDE e rollback simmetrico.

---

## 1. Scopo del documento

Questo documento definisce le regole permanenti di governance, sicurezza, qualità e metodo del progetto Goodix 27c6:5125.

I soggetti logici sono:

- **Utente**: autorità finale, proprietario dell'hardware e decisore su scope, rischio, live, main e cambi di policy;
- **AI PM / Reviewer**: ruolo logico di pianificazione, recovery, review critica e scelta del passo successivo;
- **AI Executor**: ruolo logico di implementazione, test, documentazione e produzione delle evidenze.

Nella modalità autonoma AI PM e AI Executor possono essere due ruoli alternati dalla stessa sessione Codex. La condivisione del runtime non riduce l'obbligo di review indipendente: il ruolo PM deve riesaminare direttamente repository ed evidenze e non limitarsi a confermare il summary del ruolo Executor.

Repository privato canonico:

```text
sorguido/goodix-27c6-5125-private
```

La root reale del clone deve essere determinata dal repository, ad esempio con:

```bash
git rev-parse --show-toplevel
```

Manuale tecnico canonico:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

---

## 2. Obiettivo generale

Arrivare in modo tecnicamente fondato, riproducibile e documentato a uno stack Linux funzionante per il sensore **Goodix USB 27c6:5125**, mantenendo integralmente stato factory e compatibilità Windows.

Il risultato atteso comprende:

- comprensione documentata del protocollo;
- userspace core e/o integrazione driver coerente con l'architettura Linux/libfprint;
- preservazione di firmware residente, PSK/OTP, factory data e configurazione persistente;
- compatibilità con il percorso Windows preesistente;
- procedure di build, test, installazione e rollback documentate;
- evidenze e provenance sufficienti per review futura e ripresa autonoma.

Invariante assoluto:

```text
factory_firmware_and_persistent_state_must_remain_untouched
```

Supporto Linux ≠ riprovisionamento del sensore.

---

## 3. Modello di intervento

L'agente lavora per iterazioni. Ogni iterazione affronta un problema o un avanzamento ben definito.

La condotta dell'agente è regolata dai seguenti principi:

- **Safety First**: mai rischiare lo stato del sensore per un test frettoloso;
- **Evidence-First**: ogni affermazione tecnica deve basarsi su dati riscontrabili (capture, log, sorgenti, test);
- **Trasparenza**: le decisioni, i risultati e i failure devono essere documentati;
- **Reversibilità**: ogni modifica al sistema dell'Utente deve essere facilmente annullabile.

---

## 4. Human Gate — operazioni riservate all'Utente

L'agente non deve mai eseguire in autonomia azioni che rientrano nei Human Gate.

Quando un task richiede una di queste azioni, l'agente deve preparare il materiale necessario (codice, script, istruzioni) e rilasciare il controllo dichiarando `HUMAN_REQUIRED`.

### Operazioni che costituiscono Human Gate:

1. **Esecuzione live sul sensore**: qualsiasi comando o codice che interagisce con l'hardware reale Goodix USB 27c6:5125;
2. **Uso di privilegi elevati**: comandi `sudo`, installazione di pacchetti di sistema, modifica di file di sistema outside-sandbox;
3. **Modifica del branch `main` o `bakcup_pre_agentic_mode`**: commit, push, merge o rebase su questi branch protetti;
4. **Operazioni su repository esterni/pubblici**: push, PR o pubblicazione di codice/documenti;
5. **Cambi di policy o scope**: modifiche a questo documento, ad `AGENTS.md`, a `START_PROMPT.md` o espansioni del target di progetto.

---

## 5. Branch Strategy e Git Policy

Il repository utilizza la seguente struttura di branch:

- `main`: branch di produzione/pubblicazione. **Read-only per l'agente.**
- `bakcup_pre_agentic_mode`: backup storico pre-agente. **Read-only per l'agente.**
- `development`: branch principale di lavoro per l'agente autonomo.

### Regole Git per l'agente:

1. L'agente opera **esclusivamente** sul branch `development` (o sul branch di PR dedicato);
2. Commit atomici e con messaggi descrittivi secondo convenzioni standard (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`);
3. Niente `git push --force`, `git rebase` o riscrittura della storia condivisa;
4. Verificare sempre `git status` e `git diff` prima e dopo ogni modifica;
5. Non lasciare modifiche uncommitted al termine di un task, salvo lavoro parziale esplicitamente documentato.

---

## 6. Recovery e Gestione della Sessione

Alla ripartenza o all'inizio di una sessione, l'agente non assume uno stato precedente dalla propria memoria di sessione, ma ricostruisce lo stato dal repository.

`START_PROMPT.md` è il punto d'ingresso standard.

La sessione non deve aspettarsi un primo prompt operativo esterno. All'avvio assume il ruolo **AI PM / Recovery Reviewer** e ricostruisce lo stato reale.

Prima di definire il primo `CURRENT_TASK` deve:

1. individuare Git root;
2. verificare branch, HEAD e `git status --short`;
3. leggere integralmente:
   - `START_PROMPT.md`;
   - `AGENTS.md`;
   - le presenti Linee Guida;
4. leggere nel manuale tecnico, tramite indice e ricerca mirata:
   - la sezione di stato corrente;
   - l'ultimo avanzamento consolidato;
   - lo stato del progetto, l'ultimo avanzamento e i temi/confini aperti;
   - i blocker e le decisioni architetturali pertinenti;
5. esaminare storia recente e struttura pertinente del repository;
6. identificare ultimo avanzamento tecnico reale e ultimo confine aperto;
7. esaminare ultimi Dxxx pertinenti, codice, test, launcher, patch di installazione/rollback e, quando utili alla ricostruzione storica, gli Operator Kit esistenti;
8. verificare se esiste lavoro parziale o non committato;
9. determinare se l'ultimo step è realmente chiuso o deve essere completato/corretto.

Per ogni claim tecnico storico l'agente deve cercare nel manuale e leggere la sezione pertinente prima di affidarsi a memoria, contesto o session summary:

```text
NO TECHNICAL CLAIM FROM MEMORY WHEN THE MANUAL CAN ANSWER IT
```

La lettura integrale del manuale non è richiesta per default. Resta eccezionale e si usa soltanto quando una decisione trasversale o una contraddizione non è risolvibile con ricerca mirata e lettura delle sezioni rilevanti.

### 6.1 Worktree sporco

Un worktree sporco non è automaticamente un errore.

Una sessione precedente può essersi interrotta dopo avere modificato file e prima del commit. L'agente deve quindi:

- analizzare il diff;
- ricostruire provenienza e intento probabile;
- non cancellare, resettare, stashare o sovrascrivere modifiche preesistenti;
- riprendere il lavoro se è chiaramente coerente e recuperabile;
- usare `HUMAN_REQUIRED` se l'origine o l'intento sono materialmente ambigui e una scelta autonoma potrebbe distruggere lavoro o deviare il progetto.

### 6.2 Definizione del primo task

Solo dopo la recovery review, l'AI PM determina `CURRENT_TASK`.

Se esiste un task precedente incompleto ma recuperabile, il primo compito deve completare o correggere quello prima di saltare a una nuova milestone.

### 6.3 Selezione del lavoro task e theme-driven

Il progetto non ha una sequenza globale predefinita. Il lavoro viene scelto dal task esplicito dell’Utente oppure, in assenza di esso, dal più piccolo task tecnicamente giustificato ricostruito da stato reale, manuale, evidenze e blocker.

```text
NO_GLOBAL_PROJECT_SEQUENCE=true
WORK_MODE=TASK_AND_THEME_DRIVEN
```

Il target production iniziale è Fedora KDE con Goodix USB `27c6:5125` / APP12509 attraverso lo stack standard `libfprint -> fprintd -> PAM/KDE`. Altre distribuzioni, desktop environment, sensori, firmware/target, utenti AD/LDAP/network o un upstream generalizzato oltre quanto necessario sono fuori scope salvo nuova decisione esplicita dell'Utente.

Il dettaglio e lo stato tecnico vivono nel manuale tecnico canonico. Durante bootstrap/recovery l'AI PM analizza lo stato reale e i temi/confini aperti prima di selezionare il primo task. Può applicare `CORRECTIVE` o fare `REPLAN` quando giustificato, ma non può ampliare lo scope del target o modificare la governance senza nuova decisione esplicita dell'Utente.

Il materiale storico o deprecato non viene cancellato. L'archivio privato canonico è `red_tag/`. Prima di qualsiasi pubblicazione pubblica è obbligatorio auditare import, build, test, script, riferimenti documentali, provenance, licensing e dipendenze production; gli elementi ancora referenziati devono essere disaccoppiati, tutto il materiale non pubblico va spostato in `red_tag/` e la directory va aggiunta a `.gitignore`. Build, test e release non devono dipenderne. `red_tag/` è un archivio controllato, non un cestino.

---

## 7. Autonomous Execute–Review Loop

La sessione alterna due ruoli logici: AI Executor e AI PM / Reviewer.

### 7.1 AI Executor
Implementa il task assegnato, esegue verifiche offline, aggiorna la documentazione e produce le evidenze.

### 7.2 AI PM / Reviewer
Riesamina criticamente il lavoro svolto dall'Executor senza fidarsi del solo summary. Verifica diff, test, documentazione e stato Git.

Decisioni di review ammesse:
- `ACCEPT_AND_CONTINUE`
- `CORRECTIVE`
- `REPLAN`
- `HUMAN_REQUIRED`
- `PROJECT_STEP_COMPLETE`

#### HUMAN_REQUIRED
Il loop si ferma prima dell'azione soggetta a gate. Il PM riporta stato, motivo, decisione richiesta e passo successivo previsto.

#### PROJECT_STEP_COMPLETE
Usare solo quando l'obiettivo complessivo attualmente perseguibile senza nuovo Human Gate è realmente esaurito.

---

## 8. Human Gate e Patch-First Validation

Se il progresso richiede un intervento live, USB reale o un'operazione privilegiata dell'Utente, l'agente **non deve eseguirla direttamente**. Deve:

1. Implementare e testare offline la modifica;
2. Produrre una patch/installazione minimale e reversibile (`install.sh`);
3. Produrre una patch/disinstallazione o rollback simmetrico (`uninstall.sh`);
4. Consegnare un README operativo breve e completo;
5. Verificare offline i percorsi nel massimo grado consentito;
6. Terminare con `HUMAN_REQUIRED` prima di installazione, privilegi, USB o live.

---

## 9. Real Target Compatibility Gate

Prima di consolidare una scelta architetturale o di integrazione, l'agente deve verificare che la soluzione sia compatibile con l'ambiente di produzione reale dell'Utente (Fedora 44 KDE x86_64, fprintd 1.94.5, libfprint 1.94.100).

```text
TECHNICALLY_VALID != PRODUCTION_COMPATIBLE
```

---

## 10. Licensing e Provenance

1. Codice nuovo in `core/` e `tools/`: `GPL-2.0-or-later`;
2. Codice in `libfprint-driver/`: conserva la licenza per-file preesistente (`LGPL-2.1-or-later` per nuovo codice driver);
3. Nessun inserimento di codice proprietario, secret o dati biometrici reali;
4. Tracciare provenance di estratti e reference in `docs/LICENSING_AND_PROVENANCE.md`.

---

## 11. Anti-Frammentazione

Non creare un nuovo D-number (es. D299) per semplici correzioni locali dello stesso task. Un nuovo D-number è riservato ad avanzamenti tecnici sostanziali, nuove evidenze o nuovi confini hardware.

---

## 12. Executable Closure

Un task non è completo solo perché i test unitari passano. Se modifica o abilita un percorso eseguibile, l'agente deve verificarne invocation, cwd, import path, dry-run e gestione errori.

---

## 13. Safety Telemetry

Mantenere la telemetria di sicurezza (conteggio comandi USB, retry, open/close, cleanup/reseal) separata dai report di sintesi del progetto.

---

## 14. Governance e Modifica delle Policy

Queste Linee Guida, `AGENTS.md` e `START_PROMPT.md` costituiscono la costituzione del progetto. L'agente non modifica questi file salvo richiesta ed autorizzazione esplicita dell'Utente.

---

## 15. Manuale tecnico canonico

`Goodix 27c6 5125 manuale tecnico.md` è la **fonte narrativa canonica dello stato tecnico**.

Ogni nuova conoscenza, decisione, correzione o cambiamento di stato deve essere integrato organicamente nel manuale.

Il manuale:

- non è un log append-only;
- aggiorna sezioni alte/canoniche quando cambia una decisione;
- mantiene indice, tabelle e stato tecnico coerenti;
- aggiunge una sezione Dxxx solo quando utile alla provenance o ricostruzione;
- corregge o marca come superate formulazioni stale;
- non lascia conoscenza nuova soltanto in sessione AI, report o commit message;
- non duplica inutilmente contenuto ancora valido.

Nel percorso verso la pubblicazione pubblica, il manuale destinato alla pubblicazione deve essere rieditato e ristrutturato in inglese come vero manuale tecnico, non tradotto letteralmente né mantenuto come diario Dxxx. Tutta la documentazione pubblica finale è in inglese. I file interni `AGENTS.md`, `START_PROMPT.md` e queste Linee Guida non richiedono traduzione.

Il bootstrap ne legge obbligatoriamente stato corrente, ultimo avanzamento consolidato, confini/temi aperti e blocker/decisioni architetturali pertinenti. Ogni altro claim tecnico storico richiede ricerca mirata e lettura della sezione rilevante; memoria e session summary non hanno autorità tecnica. La lettura integrale è riservata a decisioni trasversali o contraddizioni non risolvibili con consultazione mirata.

---

## 16. Review set Git-native e repository hygiene

Il review set standard è Git-native, non un archivio separato.

La superficie di audit comprende:
- baseline Git rilevante;
- HEAD/commit finale o stato corrente del branch;
- diff;
- artefatti Dxxx pertinenti in `analysis/Dxxx/`;
- codice, test e documentazione realmente modificati;
- manuale tecnico.

---

## 17. Configurazione del Modello AI

Le policy del repository non devono prescrivere, raccomandare o registrare il nome del modello AI o il livello di ragionamento.

---

## 18. Pubblicazione e Confine Privato/Pubblico

Il repository privato è il workspace canonico. Il repository pubblico resta congelato fino ad audit e sanitizzazione dedicati. Prima di qualsiasi pubblicazione pubblica, l'audit deve spostare tutto il materiale non pubblico in `red_tag/` e verificare l'assenza di dipendenze build/release.

---

## 19. Principio sintetico della v3.4

```text
sicurezza hardware forte
+
factory state preservato
+
branch development isolato
+
recovery evidence-first
+
manuale canonico vivo
+
alternanza disciplinata Executor/PM
+
Human Gate espliciti
+
patch-first install/rollback minimale e reversibile
+
workflow nativo osservato dall'Utente
+
pragmatism first e tempo operatore protetto
+
serie VERIFY/MATCH max-3 stop-on-first-match
+
selezione del lavoro task e theme-driven
+
target iniziale Fedora KDE + APP12509
+
storia preservata e `red_tag/` obbligatorio prima della pubblicazione dopo audit completo
+
review Git-native
+
licensing/provenance preservati
=
autonomia senza perdere controllo, memoria o reversibilità
```
