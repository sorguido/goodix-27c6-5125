# TASK — Rimuovere la roadmap A→F dall’orchestrazione canonica

## Contesto e decisione Utente

L’Utente ha deciso esplicitamente che la roadmap sequenziale A→F è sostanzialmente chiusa e **non deve più governare il progetto**.

Da questo momento il progetto prosegue per **task e temi distinti**, senza una sequenza globale di fasi predefinita.

Questa istruzione costituisce autorizzazione esplicita alla modifica dei documenti di governance/canonici necessaria per recepire il nuovo metodo di lavoro.

## Obiettivo

Modificare il repository privato sul branch `development` in modo che, alla prossima ripartenza tramite `START_PROMPT.md`, Codex:

- non cerchi più una roadmap A→F;
- non cerchi più una “fase corrente”;
- non imponga più sequencing A>B>C>D>E>F;
- non interpreti la chiusura di una fase come stop obbligatorio;
- non usi più `analysis/PROJECT_NEXT_STEPS_PLAN.md` come piano operativo canonico;
- ricostruisca invece lo stato reale del progetto e lavori sul task esplicito dell’Utente oppure, in assenza di task esplicito, sul più piccolo task tecnicamente giustificato tra i temi/confini realmente aperti.

Contestualmente, riportare la documentazione canonica dalla posizione attuale sotto `development/private-root/` alla **Git root reale del progetto**, così che le fonti principali siano immediatamente visibili e non dipendano dal subtree in cui Codex sta operando.

La modifica deve essere documentale/governance-only. Non modificare codice runtime, packaging, driver, test funzionali o comportamento hardware.

---

## Obiettivo strutturale aggiuntivo — documentazione canonica in Git root

La struttura finale desiderata è:

```text
<git-root>/
├── AGENTS.md
├── START_PROMPT.md
├── Goodix 27c6 5125 manuale tecnico.md
├── Linee Guida di Progetto Goodix 27c6 5125 per AI.md
├── production/
├── libfprint-driver/
├── deployment/
├── docs/
├── development/
└── ...
```

Le quattro fonti canoniche devono esistere in **una sola copia operativa**, direttamente nella Git root:

```text
AGENTS.md
START_PROMPT.md
Goodix 27c6 5125 manuale tecnico.md
Linee Guida di Progetto Goodix 27c6 5125 per AI.md
```

### Regole di migrazione

1. Individua le versioni canoniche correnti sotto:
   ```text
   development/private-root/
   ```
2. Porta i quattro file canonici nella Git root preservando integralmente il contenuto salvo le modifiche richieste da questo task.
3. Aggiorna tutti i riferimenti interni, path hard-coded relativi e istruzioni di bootstrap che assumono la vecchia collocazione.
4. Dopo la migrazione non devono restare copie operative duplicate sotto:
   ```text
   development/private-root/
   ```
5. Non lasciare due `AGENTS.md` concorrenti con la stessa funzione.
6. Non creare symlink come soluzione principale.
7. Non creare wrapper/redirect Markdown inutili se non servono realmente alla compatibilità di tooling esistente.
8. Prima di rimuovere le vecchie copie, verifica che nessuno script, test, documento canonico o workflow attivo le referenzi ancora per path.
9. Se esistono riferimenti storici dentro report/evidenze chiuse, non riscriverli in massa solo per cosmetica; devono però essere chiaramente non autoritativi.
10. La Git root deve diventare l’unico punto canonico per bootstrap, governance e manuale tecnico.

### `AGENTS.md`

`AGENTS.md` deve essere posizionato nella Git root e deve governare l’intero repository.

Non mantenere una seconda copia sotto `development/private-root/`, perché una copia più profonda potrebbe diventare autorità locale per quel subtree e divergere dalla governance globale.

### `START_PROMPT.md`

Portarlo nella Git root come entrypoint standard e aggiornare `AGENTS.md`/Linee Guida affinché lo referenzino semplicemente come:

```text
<git-root>/START_PROMPT.md
```

### Linee Guida

Portarle nella Git root come fonte canonica permanente di governance dettagliata.

### Manuale tecnico

Portarlo nella Git root come autorità narrativa tecnica primaria:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

### Acceptance strutturale

A fine task deve valere:

```text
CANONICAL_DOCS_LOCATION=GIT_ROOT
CANONICAL_DOC_DUPLICATES=0
NESTED_CANONICAL_AGENTS=0
```

---

## Preflight obbligatorio

1. Individua la Git root reale con:
   ```bash
   git rev-parse --show-toplevel
   ```
2. Verifica:
   ```bash
   git branch --show-current
   git status --short
   git rev-parse HEAD
   ```
3. Opera soltanto se il branch corrente è `development`.
4. Non cambiare branch autonomamente.
5. Non modificare `main`, `bakcup_pre_agentic_mode`, repository pubblico o Git history.
6. Se il worktree contiene modifiche preesistenti non riconducibili con certezza a questo task, non sovrascriverle: analizzale e usa `HUMAN_REQUIRED` solo se esiste conflitto materiale.

### Provenance utile

La roadmap A→F fu resa vincolante dal commit storico:

```text
420894d093c04b2dc31980cf9292389362dfc6f0
docs: approve roadmap A-F
```

Quel commit toccò almeno:

- `AGENTS.md`
- `Goodix 27c6 5125 manuale tecnico.md`
- `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`
- `START_PROMPT.md`
- `analysis/PROJECT_NEXT_STEPS_PLAN.md`

Nel layout corrente del branch `development`, le copie canoniche risultano collocate sotto:

```text
development/private-root/
```

Il task deve quindi coprire sia la rimozione della roadmap sia la migrazione delle fonti canoniche nella Git root reale.

Non limitarti però a questi file: il repository corrente può contenere riferimenti successivi.

---

## Metodo di audit

Prima di modificare, cerca nell’intero working tree almeno:

```bash
rg -n -i \
  -e 'roadmap' \
  -e 'A[→>-]F' \
  -e 'PHASE_ORDER' \
  -e 'CURRENT_PHASE' \
  -e 'NEXT_PHASE' \
  -e 'USER_APPROVED_ROADMAP' \
  -e 'PROJECT_NEXT_STEPS_PLAN' \
  -e 'Phase [A-F]' \
  -e 'fase [A-F]' \
  .
```

Escludi soltanto `.git/`, file binari e materiale che `rg` non tratta come testo.

Classifica i match in:

1. **canonici / operativi / orchestration-facing** → devono essere corretti;
2. **stato corrente / documentazione viva** → devono essere corretti;
3. **evidenze storiche Dxxx / report chiusi** → non riscriverli in massa solo per cosmetica se ciò ne altererebbe la provenance; devono però essere chiaramente non autoritativi e non letti come piano operativo.

Cerca inoltre ogni riferimento alla vecchia collocazione canonica:

```bash
rg -n   -e 'development/private-root/AGENTS\.md'   -e 'development/private-root/START_PROMPT\.md'   -e 'development/private-root/Goodix 27c6 5125 manuale tecnico\.md'   -e 'development/private-root/Linee Guida di Progetto Goodix 27c6 5125 per AI\.md'   .
```

Verifica anche nomi file senza path quando il contesto può implicare una directory specifica.

L’obiettivo non è cancellare la storia Git: è eliminare ogni **aspettativa operativa corrente** della roadmap.

---

## Modifiche richieste

### 0. Migrazione della documentazione canonica nella Git root

Prima o contestualmente alle modifiche testuali:

- sposta nella Git root:
  - `development/private-root/AGENTS.md` → `AGENTS.md`
  - `development/private-root/START_PROMPT.md` → `START_PROMPT.md`
  - `development/private-root/Goodix 27c6 5125 manuale tecnico.md` → `Goodix 27c6 5125 manuale tecnico.md`
  - `development/private-root/Linee Guida di Progetto Goodix 27c6 5125 per AI.md` → `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`
- usa normali operazioni Git/file, preservando history quanto ragionevolmente possibile;
- non lasciare copie concorrenti nelle vecchie posizioni;
- aggiorna i riferimenti attivi alla nuova posizione;
- verifica che il bootstrap parta sempre dalla Git root reale e non da una path hard-coded;
- non spostare automaticamente altri file da `development/private-root/` solo perché sono vicini ai quattro documenti canonici: questo task riguarda esclusivamente la documentazione canonica e i riferimenti necessari.

### 1. `START_PROMPT.md`

Rimuovi ogni istruzione che obbliga il bootstrap a:

- leggere la roadmap A→F;
- determinare una fase corrente;
- verificare coerenza del task con una fase;
- rispettare `PHASE_ORDER=A>B>C>D>E>F`;
- fermarsi automaticamente alla closure di una fase;
- richiedere una nuova interazione Utente per “passare alla fase successiva”.

Sostituisci la logica con una regola semplice task-driven, concettualmente equivalente a:

```text
NO_GLOBAL_PROJECT_SEQUENCE=true
WORK_MODE=TASK_AND_THEME_DRIVEN
```

e con comportamento narrativo del tipo:

- se l’Utente ha fornito un task esplicito, quello è il target corrente;
- altrimenti il PM ricostruisce stato, lavoro parziale, blocker e temi/confini aperti dal repository e dal manuale;
- seleziona il più piccolo task tecnicamente giustificato che produce avanzamento reale;
- non assume l’esistenza di una fase successiva o di un ordine globale predefinito.

Mantieni invariati Human Gate, Real Target Compatibility Gate, Git policy, recovery evidence-first e alternanza PM↔Executor.

### 2. `AGENTS.md`

Rimuovi:

- `analysis/PROJECT_NEXT_STEPS_PLAN.md` dalla gerarchia delle fonti canoniche;
- la definizione di “Piano operativo canonico”;
- l’obbligo di leggerlo al bootstrap;
- qualunque vincolo di sequencing/fase corrente;
- la sezione dedicata alla roadmap production A→F;
- le eccezioni `PHASE_CLOSED => STOP` o equivalenti;
- ogni altra formulazione che faccia dipendere il prossimo task da una fase A–F.

Mantieni invece:

- target production reale già qualificato;
- invarianti hardware/factory-preserving;
- policy Git;
- Human Gate;
- safety;
- licensing/provenance;
- manuale tecnico come autorità narrativa tecnica;
- recovery e review indipendente.

Nel recovery sostituisci “fase corrente / sequencing / prossimo boundary dal piano” con:

- task Utente corrente, se presente;
- ultimo avanzamento tecnico documentato;
- eventuale lavoro incompleto;
- blocker;
- task/temi/confini tecnici ancora aperti pertinenti.

### 3. `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`

Questa è una modifica di policy esplicitamente autorizzata dall’Utente.

- incrementa la versione rispetto a quella corrente;
- usa data revisione `17 settembre 2026`;
- nella motivazione spiega sinteticamente che il progetto passa da sequencing per fasi a lavoro task/theme-driven;
- dichiara che Human Gate, safety, factory-preserving, Git protection, licensing e target tecnico non vengono rilassati.

Rimuovi:

- roadmap A→F dalla motivazione e dalle regole permanenti;
- lettura obbligatoria di roadmap/fase al bootstrap;
- sezione “Roadmap production approvata e phase gate” o equivalente;
- sequencing A>B>C>D>E>F;
- stop obbligatorio alla closure di una fase;
- riferimenti alla “fase successiva” come meccanismo di orchestrazione.

Sostituisci con una regola permanente essenziale:

> Il progetto non ha una sequenza globale predefinita. Il lavoro viene scelto dal task esplicito dell’Utente oppure, in assenza di esso, dal più piccolo task tecnicamente giustificato ricostruito da stato reale, manuale, evidenze e blocker.

Non creare un nuovo sistema di pianificazione complesso per sostituire la roadmap.

### 4. `Goodix 27c6 5125 manuale tecnico.md`

Il manuale deve smettere di fungere da fonte di sequencing A→F.

Individua e rimuovi/reformula:

- sezioni narrative “Roadmap production A→F”;
- `USER_APPROVED_ROADMAP`;
- `APPROVAL_DATE` se esiste solo per la roadmap;
- `CURRENT_PHASE`;
- `PHASE_ORDER`;
- `NEXT_PHASE`;
- `NEXT_WORK_CLASS=PHASE_*`;
- `NEXT_BOUNDARY` quando esprime esclusivamente il passaggio alla fase successiva;
- formule come “Phase X è chiusa quindi ora si passa a Phase Y”;
- criteri di closure A/B/C/D/E/F usati come piano futuro.

### Preservazione della conoscenza

Non cancellare risultati tecnici solo perché erano descritti dentro una fase.

Per esempio, se il manuale dice che un certo lavoro è stato completato durante “Phase D”, conserva il fatto tecnico rilevante ma riscrivilo come stato/risultato, senza trasformarlo in una milestone ancora da eseguire.

Il manuale deve descrivere:

- stato tecnico corrente;
- ciò che è provato;
- ciò che è supportato;
- limiti e rischi residui;
- temi/task eventualmente aperti;

ma **non un percorso A→F da seguire**.

### 5. `analysis/PROJECT_NEXT_STEPS_PLAN.md`

Questo file non deve più essere una fonte canonica né un piano operativo.

Default preferito:

1. verifica se contiene conoscenza tecnica corrente unica non presente nel manuale;
2. migra nel manuale soltanto eventuali fatti durevoli realmente unici;
3. elimina `analysis/PROJECT_NEXT_STEPS_PLAN.md`.

Non sostituirlo con una nuova roadmap, un backlog globale obbligatorio o un altro file equivalente.

Se per una ragione concreta non può essere eliminato, trasformalo in documento puramente storico/non autoritativo e rinominalo in modo che non possa essere scambiato per il piano corrente. Questa è però seconda scelta: preferire la rimozione se la conoscenza utile è già nel manuale.

### 6. Altri file correnti

Per ogni altro match dell’audit:

- rimuovi o riformula il riferimento se il file può guidare lavoro futuro;
- aggiorna README/documentazione corrente se presenta ancora A→F come percorso da seguire;
- non fare una riscrittura cosmetica massiva di raw evidence o report Dxxx chiusi solo per cancellare parole storiche.

Se restano match storici intenzionali, elencali esplicitamente nel report finale e spiega perché non sono autoritativi né raggiunti dal bootstrap.

---

## Stato desiderato dopo la modifica

Alla ripartenza Codex deve poter concludere, senza ambiguità:

```text
GLOBAL_ROADMAP=NONE
CURRENT_PHASE=NOT_APPLICABLE
WORK_SELECTION=USER_TASK_OR_EVIDENCE_BASED_OPEN_TASK
```

Questi tre valori sono criteri concettuali: non è obbligatorio inserirli letteralmente nei documenti se una formulazione narrativa è più pulita.

La selezione del lavoro futuro non deve dipendere da `Phase A`, `Phase B`, … `Phase F`.

---

## Verifica obbligatoria

Dopo le modifiche:

### A. Audit testuale

Ripeti la ricerca completa:

```bash
rg -n -i \
  -e 'roadmap' \
  -e 'A[→>-]F' \
  -e 'PHASE_ORDER' \
  -e 'CURRENT_PHASE' \
  -e 'NEXT_PHASE' \
  -e 'USER_APPROVED_ROADMAP' \
  -e 'PROJECT_NEXT_STEPS_PLAN' \
  -e 'Phase [A-F]' \
  -e 'fase [A-F]' \
  .
```

Verifica manualmente ogni residuo.

**Acceptance:**

- zero residui autoritativi/operativi della roadmap;
- zero bootstrap dependency da `PROJECT_NEXT_STEPS_PLAN.md`;
- zero obbligo di determinare una fase A–F;
- zero phase-order gate;
- zero stop automatico legato alla closure di una fase;
- eventuali residui sono soltanto evidenza storica non autoritativa e sono elencati nel report.

### B. Coerenza incrociata

Confronta almeno:

- `START_PROMPT.md`
- `AGENTS.md`
- Linee Guida
- manuale tecnico

e verifica che non si contraddicano sul metodo di selezione del lavoro.

### B1. Verifica collocazione canonica

Verifica esplicitamente:

```bash
test -f AGENTS.md
test -f START_PROMPT.md
test -f 'Goodix 27c6 5125 manuale tecnico.md'
test -f 'Linee Guida di Progetto Goodix 27c6 5125 per AI.md'
```

e verifica l’assenza delle vecchie copie:

```bash
test ! -e development/private-root/AGENTS.md
test ! -e development/private-root/START_PROMPT.md
test ! -e 'development/private-root/Goodix 27c6 5125 manuale tecnico.md'
test ! -e 'development/private-root/Linee Guida di Progetto Goodix 27c6 5125 per AI.md'
```

Poi controlla che non restino riferimenti attivi alla vecchia posizione:

```bash
rg -n   -e 'development/private-root/AGENTS\.md'   -e 'development/private-root/START_PROMPT\.md'   -e 'development/private-root/Goodix 27c6 5125 manuale tecnico\.md'   -e 'development/private-root/Linee Guida di Progetto Goodix 27c6 5125 per AI\.md'   .
```

Acceptance:

```text
CANONICAL_DOCS_LOCATION=GIT_ROOT
CANONICAL_DOC_DUPLICATES=0
OLD_CANONICAL_PATH_REFERENCES=0
```

### C. Git diff

Controlla:

```bash
git diff --check
git status --short
git diff --stat
git diff
```

Nessuna modifica fuori scope.

### D. Executable closure

```text
EXECUTABLE_CLOSURE=NOT_APPLICABLE
```

Task documentale/governance-only. Non eseguire live, USB, `sudo`, installazioni o test hardware.

---

## Commit e push

Se la review finale è PASS:

1. crea **un solo commit coerente** sul branch `development`, per esempio:
   ```text
   docs: retire A-F roadmap orchestration
   ```
2. esegui normale push a:
   ```text
   origin/development
   ```
3. niente force push, amend, rebase o history rewrite.

---

## Report finale richiesto

Riporta in modo compatto:

```text
OUTCOME=
BRANCH=
BASELINE_HEAD=
FINAL_HEAD=
FILES_CHANGED=
ROADMAP_OPERATIONAL_REFERENCES=0
PROJECT_NEXT_STEPS_PLAN_STATUS=
CANONICAL_DOCS_LOCATION=
CANONICAL_DOC_DUPLICATES=
OLD_CANONICAL_PATH_REFERENCES=
HISTORICAL_RESIDUAL_REFERENCES=
EXECUTABLE_CLOSURE=NOT_APPLICABLE
PUSH_STATUS=
```

Aggiungi una breve spiegazione di come funzionerà il bootstrap futuro:

> task esplicito Utente → esecuzione/review; altrimenti recovery evidence-first → scelta del più piccolo task giustificato tra temi/confini aperti; nessuna fase A–F implicita.

Non avviare autonomamente un nuovo task tecnico dopo questo commit: questo task termina con la sola rimozione della roadmap dall’orchestrazione.
