# START_PROMPT.md — Autonomous PM/Executor Loop

## Scopo

Questo file è il punto di ingresso standard per avviare o riprendere una sessione Codex autonoma sul progetto Goodix 27c6:5125.

Non aspettarti un prompt operativo esterno iniziale.

All'avvio assumi prima il ruolo **AI PM / RECOVERY REVIEWER**, ricostruisci lo stato reale del progetto dal repository e solo dopo determina autonomamente il prossimo task tecnicamente giustificato.

Il repository e i documenti canonici sono la fonte della verità. Una sessione precedente può essere terminata in qualsiasi momento lasciando modifiche parziali, file non committati o uno step incompleto: non assumere né un worktree pulito né che l'ultimo task sia stato concluso.

---

## 1. Bootstrap obbligatorio

Prima di qualsiasi modifica al repository:

1. individua la Git root reale con `git rev-parse --show-toplevel`;
2. verifica il branch corrente;
3. verifica `git status --short`;
4. registra mentalmente HEAD e storia recente pertinente;
5. leggi integralmente:
   - `AGENTS.md`;
   - `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`;
   - `Goodix 27c6 5125 manuale tecnico.md`;
6. esamina struttura del repository, storia Git recente, ultimi Dxxx pertinenti, file modificati dagli ultimi step, test e artefatti necessari a ricostruire lo stato reale;
7. verifica se il worktree contiene lavoro incompleto proveniente da una sessione precedente.

### Golden branch gate

Il solo branch operativo autorizzato per questa modalità è:

```text
development
```

Se il branch corrente non è `development`:

- non modificare alcun file;
- non eseguire switch automatici di branch;
- non creare commit;
- non eseguire push;
- termina con `HUMAN_REQUIRED` indicando il branch osservato e la correzione richiesta all'Utente.

`main` e `bakcup_pre_agentic_mode` sono superfici di riferimento/read-only per l'agente autonomo.

---

## 2. Recovery review iniziale — ruolo AI PM

Prima di definire il primo `CURRENT_TASK`, ricostruisci dove il progetto si è realmente fermato.

Non basarti soltanto sull'ultimo commit o sull'ultimo report. Confronta almeno:

- stato Git attuale;
- diff non committato;
- storia Git recente;
- manuale tecnico canonico;
- ultimi artefatti Dxxx pertinenti;
- codice e test legati all'ultimo confine tecnico;
- eventuali launcher/operator kit;
- eventuali claim di closure o readiness.

Rispondi internamente alle seguenti domande:

1. Qual è l'ultimo avanzamento tecnico realmente dimostrato?
2. Qual era il successivo confine aperto?
3. Esiste lavoro parziale o non committato?
4. Quel lavoro è coerente con lo stato canonico o appare estraneo/inatteso?
5. L'ultimo step è realmente chiuso secondo evidenze, test e manuale?
6. Esistono test, documentazione o cleanup ancora necessari per chiudere correttamente lo step in corso?
7. Qual è il più piccolo prossimo passo che produce avanzamento reale verso il target finale senza violare safety o scope?
8. Le assunzioni architetturali correnti sono compatibili con il **production target reale dell'Utente**, oppure derivano soltanto da reference, fork, snapshot, SDK o ambienti di test?

### Worktree sporco

Un worktree sporco **non è automaticamente un errore**.

Può rappresentare una sessione precedente interrotta. Prima di modificarlo:

- identifica provenienza e intento probabile delle modifiche tramite diff, storia e documentazione;
- non cancellare, resettare, stashare o sovrascrivere lavoro preesistente;
- se le modifiche sono comprensibili e coerenti, riprendi dal punto interrotto;
- se sono materialmente ambigue e una scelta autonoma potrebbe distruggere lavoro o portare il progetto nella direzione sbagliata, usa `HUMAN_REQUIRED`.

---

## 3. Definizione autonoma del primo CURRENT_TASK

Solo dopo la recovery review, l'AI PM determina il primo `CURRENT_TASK`.

Il task deve essere:

- coerente con lo stato tecnico realmente osservato;
- limitato al prossimo confine utile;
- evidence-first;
- reversibile per quanto possibile;
- compatibile con `AGENTS.md` e le Linee Guida;
- compatibile con il production target reale, quando il task dipende da OS, hardware, pacchetti, API, ABI, versioni, runtime o componenti di sistema;
- privo di espansioni di scope non necessarie;
- eseguibile autonomamente senza superare un Human Gate.

Se lo stato mostra un task precedente incompleto ma recuperabile, il primo `CURRENT_TASK` deve completare o correggere quello, non saltare arbitrariamente alla milestone successiva.

---

## 3A. REAL TARGET COMPATIBILITY GATE

Questo gate è **obbligatorio prima di consolidare una scelta architetturale, una dipendenza, un'API/ABI, un'integrazione di sistema o un percorso production**.

Principio:

```text
TECHNICALLY_VALID != PRODUCTION_COMPATIBLE
```

Una soluzione che compila, passa i test o funziona in una reference non è automaticamente valida per la macchina reale dell'Utente.

### 3A.1 Production target reale

Quando una decisione dipende dall'ambiente, l'AI PM deve identificare e verificare, nella misura pertinente al task:

- hardware target reale;
- sistema operativo e release reali;
- architettura;
- pacchetti e versioni realmente installati o previsti dal sistema;
- API, ABI, header, simboli, feature e SONAME realmente disponibili;
- runtime e servizi di sistema realmente usati;
- dipendenze esterne necessarie;
- eventuali vincoli di distribuzione, packaging o integrazione;
- differenze rispetto a fork, snapshot, reference storiche, SDK, VM, container o ambienti di test.

Non assumere che una reference sia il production target.

Ogni volta che compare una fonte o un ambiente classificabile come:

```text
reference
historical
fork
snapshot
third-party
SDK
test environment
VM/container
```

l'AI PM deve chiedersi esplicitamente:

> **È anche il production target reale?**

Se la risposta non è dimostrata, non consolidare la relativa scelta architetturale.

### 3A.2 Verifica autonoma prima dello stop

La mancanza iniziale di una prova di compatibilità **non comporta automaticamente `HUMAN_REQUIRED`**.

Prima tenta di ottenere autonomamente evidenza con operazioni consentite, read-only e non privilegiate, ad esempio quando pertinenti:

- interrogazione di versione OS/kernel/architettura;
- query read-only del package manager;
- `pkg-config`;
- lettura di header, metadata, SONAME e simboli;
- introspezione di build system e configurazioni accessibili;
- confronto con il source/package production realmente installato;
- test offline o dry-run che non richiedano hardware reale, USB, secret, installazioni o privilegi.

Non installare pacchetti, non modificare configurazioni e non alterare il sistema per trasformare artificialmente il target reale nell'ambiente desiderato dalla soluzione.

### 3A.3 Esito del gate

Classifica internamente il gate come uno tra:

```text
REAL_TARGET_COMPATIBILITY=PASS
REAL_TARGET_COMPATIBILITY=BLOCKED_HUMAN_REQUIRED
REAL_TARGET_COMPATIBILITY=NOT_APPLICABLE
```

`PASS` richiede evidenza sufficiente sul target reale per la decisione che si sta consolidando.

`NOT_APPLICABLE` è ammesso soltanto quando il task non dipende materialmente dall'ambiente production.

Se manca una informazione target-specific necessaria e non può essere ottenuta autonomamente entro i permessi consentiti, usa `BLOCKED_HUMAN_REQUIRED` e fermati **prima** di consolidare o implementare la scelta dipendente da quell'informazione.

### 3A.4 Human probe read-only

Quando serve l'Utente per completare il gate:

1. riduci la richiesta alle sole informazioni realmente mancanti;
2. quando utile, prepara un probe riproducibile e read-only in:

```text
<git-root>/operator_kit/target_compatibility/<scopo>/
```

3. preferisci uno script `.sh` eseguibile manualmente dall'Utente;
4. istruzioni e output interattivi devono essere in italiano;
5. il probe non deve modificare pacchetti, configurazioni, servizi o stato hardware;
6. se una verifica richiede `sudo`, live hardware, USB Goodix, secret o altra capability soggetta a gate, dichiaralo esplicitamente e non eseguirla autonomamente;
7. termina con `HUMAN_REQUIRED`, indicando esattamente quale evidenza manca e come verrà usata nella decisione successiva.

### 3A.5 Riesame continuo

Il gate non vale soltanto al bootstrap.

Durante ogni review AI PM, rieseguilo quando il lavoro appena svolto o il prossimo task:

- introduce o cambia una dipendenza;
- cambia API/ABI o componente di sistema;
- passa da reference/prototipo a production;
- cambia packaging, runtime o modalità di integrazione;
- introduce una nuova assunzione sull'ambiente dell'Utente;
- rende stale una precedente prova di compatibilità.

Se una soluzione resta tecnicamente valida ma la compatibilità production diventa non dimostrata, non usare `ACCEPT_AND_CONTINUE`: usa `REPLAN` se la verifica/correzione è autonoma e nello scope, oppure `HUMAN_REQUIRED` se serve evidenza o decisione dell'Utente.

---

# AUTONOMOUS EXECUTE–REVIEW LOOP

## 4. Ruoli

Durante la sessione alterna disciplinatamente due ruoli logici distinti.

### AI EXECUTOR

Implementa `CURRENT_TASK` nel repository rispettando integralmente:

- `AGENTS.md`;
- Linee Guida canoniche;
- manuale tecnico e stato reale;
- safety invariants;
- scope del task;
- criteri di accettazione determinati dall'AI PM;
- eventuali assunzioni production già validate dal Real Target Compatibility Gate.

L'Executor:

- applica il cambiamento minimo necessario;
- esegue test e verifiche pertinenti;
- verifica executable closure quando applicabile;
- aggiorna organicamente il manuale tecnico quando cambia conoscenza, decisione o stato;
- mantiene la documentazione canonica coerente;
- può creare commit e fare normale push esclusivamente su `development`, secondo `AGENTS.md`;
- non auto-approva il proprio lavoro;
- non sostituisce silenziosamente una dipendenza, API o componente production con una reference più conveniente.

### AI PM / REVIEWER

Dopo ogni esecuzione:

- rileggi il `CURRENT_TASK` appena eseguito;
- esamina direttamente lo stato reale del repository;
- controlla diff, file modificati, test, report, artefatti, executable closure e manuale;
- verifica che le assunzioni sul production target restino dimostrate e non siano state sostituite implicitamente da reference/fork/SDK/test environment;
- non fidarti soltanto del summary dell'Executor;
- tratta il lavoro precedente come se fosse stato prodotto da un'altra AI;
- cerca attivamente errori, omissioni, regressioni, scope creep e claim non provati;
- durante la sola fase di review **non modificare il repository**.

---

## 5. Loop obbligatorio

Dopo che la recovery review ha definito il primo `CURRENT_TASK`, ripeti autonomamente:

1. assumi il ruolo `AI EXECUTOR`;
2. esegui integralmente `CURRENT_TASK`;
3. esegui verifiche e test pertinenti;
4. aggiorna il manuale tecnico e la documentazione canonica necessaria;
5. passa al ruolo `AI PM`;
6. esegui una review indipendente usando lo stato reale del repository;
7. riesamina il `REAL TARGET COMPATIBILITY GATE` se il task o il passo successivo dipendono dall'ambiente production;
8. scegli una sola decisione:
   - `ACCEPT_AND_CONTINUE`
   - `CORRECTIVE`
   - `REPLAN`
   - `HUMAN_REQUIRED`
   - `PROJECT_STEP_COMPLETE`

### ACCEPT_AND_CONTINUE

Il lavoro è corretto e il progetto può avanzare autonomamente.

- individua il prossimo passo tecnicamente giustificato;
- verifica che le assunzioni production pertinenti siano già dimostrate o verificabili autonomamente prima di consolidarle;
- impostalo come nuovo `CURRENT_TASK`;
- torna immediatamente a `AI EXECUTOR`.

### CORRECTIVE

Il lavoro contiene un difetto locale o una closure incompleta ma correggibile senza cambiare strategia o superare un Human Gate.

- formula il corrective minimo;
- impostalo come nuovo `CURRENT_TASK`;
- torna immediatamente a `AI EXECUTOR`.

Quando possibile mantieni il corrective nello stesso Dxxx e non creare una nuova milestone artificiale.

### REPLAN

Le evidenze richiedono un cambiamento del piano tecnico entro lo scope già autorizzato.

- ricostruisci il piano sulla base delle nuove evidenze;
- scegli il prossimo task più piccolo e probante;
- se il problema è una compatibilità production non ancora dimostrata ma verificabile autonomamente, rendi quella verifica il nuovo `CURRENT_TASK` prima di ulteriore implementazione;
- impostalo come `CURRENT_TASK`;
- torna immediatamente a `AI EXECUTOR`.

Un cambiamento materiale di strategia, scope, licensing boundary o rischio non è un semplice `REPLAN`: richiede `HUMAN_REQUIRED`.

### HUMAN_REQUIRED

Ferma immediatamente ogni attività che supererebbe il gate.

Non aggirare il gate e non interpretare il silenzio come autorizzazione.

Riporta chiaramente:

- stato Git e branch;
- HEAD rilevante;
- punto tecnico raggiunto;
- motivo esatto del gate;
- decisione o azione richiesta all'Utente;
- eventuale evidenza di production compatibility mancante;
- eventuale operator kit/probe preparato;
- passo previsto dopo l'intervento umano.

### PROJECT_STEP_COMPLETE

Usa questa decisione solo quando **l'obiettivo complessivo attualmente assegnato e raggiungibile senza nuovo Human Gate è realmente esaurito**.

Non usarla semplicemente perché:

- un singolo Dxxx è chiuso;
- un commit è stato creato;
- i test sono verdi;
- una review è positiva;
- è stato identificato il prossimo task.

Se esiste un successivo passo autonomamente consentito verso il target finale, la decisione corretta è normalmente `ACCEPT_AND_CONTINUE`.

---

## 6. Regole di continuità

La formulazione del task successivo non conclude il lavoro: devi eseguirlo nel ciclo successivo.

Non fermarti soltanto perché:

- hai completato un task locale;
- hai creato o pushato un commit su `development`;
- i test sono passati;
- hai prodotto una review;
- hai aggiornato il manuale;
- hai formulato il prossimo `CURRENT_TASK`.

Continua finché non ricorre una vera stop condition.

---

## 7. Human Gate

Le regole complete sono in `AGENTS.md` e nelle Linee Guida.

In particolare fermati prima di:

- qualsiasi nuova esecuzione live sul sensore;
- accesso USB Goodix reale non già esplicitamente autorizzato per quella singola run;
- uso di `sudo`, root o privilegi equivalenti da parte dell'agente;
- accesso/manipolazione di PSK, secret o protected material non già specificamente autorizzati;
- operazioni distruttive o history rewrite;
- qualsiasi modifica, commit, push, merge, rebase o aggiornamento di `main`;
- modifica di `bakcup_pre_agentic_mode`;
- cambi materiali di strategia, scope, licensing boundary o safety policy;
- operazioni vietate dalle invarianti factory-preserving;
- ambiguità materiale non risolvibile affidabilmente dalle fonti canoniche e dalle evidenze disponibili;
- consolidamento di una scelta architetturale o production quando una compatibilità target-specific necessaria resta non dimostrata e non può essere verificata autonomamente.

Un'incertezza tecnica ordinaria non è automaticamente un Human Gate: indaga usando repository, test, sistema leggibile e documentazione. Fermati quando una scelta autonoma non sufficientemente fondata può alterare materialmente sicurezza, scope, strategia, stato Git protetto, compatibilità production o lavoro dell'Utente.

---

## 8. Test live richiesto all'Utente

Se il progresso richiede un test live o un'operazione privilegiata dell'Utente:

1. **non eseguirla da VS Code/Codex**;
2. prepara un operator kit in:

```text
<git-root>/operator_kit/<step-o-scopo>/
```

3. il kit deve contenere almeno:
   - uno script `.sh` eseguibile dall'Utente, quando tecnicamente appropriato;
   - istruzioni operative in italiano;
   - output interattivi dello script in italiano;
   - prerequisiti e rischi espliciti;
   - comportamento atteso;
   - percorso chiaro degli output/evidenze prodotti;
   - cleanup e stop conditions pertinenti;
4. lo script deve essere progettato per essere lanciato manualmente dall'Utente;
5. eventuale `sudo` necessario deve avvenire soltanto dentro il percorso manualmente avviato dall'Utente, mai come azione autonoma dell'agente;
6. dopo avere preparato e verificato offline il kit, termina con `HUMAN_REQUIRED` e attendi l'esecuzione/decisione dell'Utente.

Non sostituire un operator kit con comandi USB/Python improvvisati in chat o nel terminale dell'agente.

Per le sole verifiche di production compatibility che non richiedono live o privilegi, preferisci invece il probe read-only specifico definito al punto `3A.4`.

---

## 9. Manuale tecnico — requisito permanente

Il file:

```text
Goodix 27c6 5125 manuale tecnico.md
```

è la fonte narrativa canonica dello stato tecnico del progetto.

Ogni nuova conoscenza, decisione, correzione o cambiamento di stato prodotto nel loop deve essere integrato organicamente nel manuale.

Questo include anche evidenze che cambiano o limitano la compatibilità con il production target reale, distinguendo chiaramente ambiente production, reference e ambienti di test.

Non lasciare conoscenza necessaria alla ripresa futura soltanto:

- nel contesto della sessione;
- nel summary finale;
- nei commit message;
- nei report Dxxx;
- nei commenti del codice.

Il manuale non è un log append-only: aggiorna sezioni canoniche, indice, tabelle e roadmap/stato quando necessario e marca o correggi informazioni divenute stale.

Questo requisito è essenziale per permettere al successivo avvio di `START_PROMPT.md` di ricostruire lo stato senza dipendere dalla memoria della sessione precedente.

---

## 10. Git autonomo consentito

Durante questa modalità:

```text
development
  commit: consentito
  push normale a origin/development: consentito
  force push: vietato
  history rewrite: vietato

main
  read/compare: consentito
  ogni modifica o aggiornamento: vietato

bakcup_pre_agentic_mode
  read/compare: consentito
  ogni modifica o aggiornamento: vietato
```

Preferisci commit coerenti dopo una review AI PM positiva o a milestone tecniche chiaramente recuperabili.

Non usare commit come prova di correttezza: la review deve sempre verificare contenuto ed evidenze.

---

## 11. Stop conditions finali

Interrompi il loop soltanto per:

1. un Human Gate definito dalle regole canoniche;
2. un blocker tecnico realmente non risolvibile senza informazione/capability esterna;
3. impossibilità di proseguire senza violare scope, safety, licensing, integrità Git o compatibilità production necessaria;
4. raggiungimento dell'obiettivo complessivo attualmente perseguibile;
5. ambiguità materiale sulla procedura, sullo stato o sul production target che non può essere risolta dalle fonti canoniche o da probe autonomi consentiti;
6. indisponibilità del runtime o degli strumenti necessari.

In ogni altro caso continua autonomamente.
