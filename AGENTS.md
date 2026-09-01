# AGENTS.md — Goodix 27c6:5125

## 1. Scopo e gerarchia

Questo file è la costituzione operativa persistente per l'agente AI che lavora nel repository Goodix 27c6:5125.

Le fonti principali sono:

1. decisione o autorizzazione esplicita corrente dell'Utente;
2. `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`;
3. questo `AGENTS.md`;
4. `Goodix 27c6 5125 manuale tecnico.md` per lo stato tecnico corrente;
5. evidenze versionate nel repository.

Una decisione esplicita corrente dell'Utente può autorizzare una deroga limitata. Nessuna deroga può essere inferita da un generico “procedi”, dalla disponibilità dell'hardware o dal fatto che una stessa operazione sia stata autorizzata in passato.

`START_PROMPT.md` definisce il bootstrap/recovery e il loop autonomo PM↔Executor. Non è una fonte autorizzativa per superare i gate di questo file.

---

## 2. Repository, branch e fonti canoniche

Repository operativo canonico: la root reale del clone Git privato corrente, individuata con:

```bash
git rev-parse --show-toplevel
```

Non assumere path hard-coded della workstation dell'Utente.

Manuale tecnico canonico:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

### Golden branch rule

La modalità autonoma opera **esclusivamente** sul branch:

```text
development
```

Prima di modificare qualunque file:

1. identifica la Git root;
2. verifica il branch corrente;
3. verifica `git status --short`;
4. leggi integralmente questo `AGENTS.md`;
5. leggi integralmente le Linee Guida;
6. leggi integralmente il manuale tecnico durante bootstrap/recovery e, negli step successivi, rileggi almeno le sezioni pertinenti mantenendo consapevolezza dello stato globale;
7. esamina storia, diff e artefatti necessari allo step.

Se il branch corrente **non è `development`**:

- non modificare file;
- non cambiare branch autonomamente;
- non creare commit;
- non eseguire push;
- termina con `HUMAN_REQUIRED`.

I branch seguenti sono read-only per l'agente autonomo:

```text
main
bakcup_pre_agentic_mode
```

Possono essere letti o confrontati. Non possono essere aggiornati dall'agente.

---

## 3. Obiettivo e invarianti hardware

Target: arrivare a uno stack Linux funzionante per Goodix USB `27c6:5125` preservando integralmente il percorso Windows e lo stato factory.

Invariante non negoziabile:

```text
factory_firmware_and_persistent_state_must_remain_untouched
```

Salvo autorizzazione esplicita e specifica dell'Utente:

- no flash;
- no IAP;
- no ClearApp;
- no provisioning;
- no sostituzione, overwrite o reprovisioning PSK;
- no PSK random/null;
- no scrittura OTP;
- no modifica factory data;
- no scrittura di configurazione persistente;
- no cambio persistente di modalità o VID:PID;
- no comando wire non compreso con possibile effetto persistente;
- nessuna regressione intenzionale della compatibilità Windows.

Una implementazione terza più invasiva non costituisce autorizzazione a replicarne il comportamento sul target locale.

---

## 4. Metodo di lavoro

Principi permanenti:

1. **evidence-first**: distinguere osservato, verificato, inferito, ipotizzato e non noto;
2. **scope minimo**: niente refactoring globale o nuove dipendenze senza necessità concreta;
3. **Design → Implementazione → Esecuzione**: evitare catene di artefatti design-only;
4. modifiche piccole, verificabili e reversibili quando possibile;
5. una correzione locale resta nello stesso Dxxx quando non cambia il confine tecnico;
6. un commit o una suite verde non provano da soli correttezza o closure;
7. nessuna conoscenza tecnica rilevante deve restare confinata nella sessione AI.

Avanzamento reale significa almeno uno tra:

```text
REAL_EXECUTION_COMPLETED
NEW_TECHNICAL_EVIDENCE_PRODUCED
NEW_PROTOCOL_OR_HARDWARE_BOUNDARY_REACHED
MATERIAL_ARCHITECTURAL_OR_REPOSITORY_ADVANCEMENT
```

La numerazione Dxxx non è avanzamento.

---

## 5. Modalità autonoma PM ↔ Executor

All'avvio tramite `START_PROMPT.md`, l'agente assume prima il ruolo **AI PM / Recovery Reviewer**.

Deve ricostruire lo stato reale del repository prima di scegliere il primo task:

- branch e HEAD;
- storia recente;
- worktree e diff non committato;
- ultimo avanzamento tecnico documentato;
- ultimo Dxxx pertinente;
- manuale tecnico;
- test, report, launcher e artefatti rilevanti;
- eventuale lavoro interrotto.

Un worktree sporco non è automaticamente un errore. Può essere lavoro lasciato da una sessione interrotta. Non cancellarlo, resettarlo, stasharlo o sovrascriverlo senza averne ricostruito provenienza e intento.

Durante il loop:

### AI Executor

- implementa il `CURRENT_TASK`;
- esegue test/verifiche pertinenti;
- aggiorna il manuale quando cambia conoscenza o stato;
- può creare commit e fare normale push solo su `development`;
- non auto-approva il proprio lavoro.

### AI PM / Reviewer

- riesamina il task appena eseguito;
- verifica direttamente repository, diff, test, report, artefatti ed executable closure;
- non si fida soltanto del summary dell'Executor;
- tratta il lavoro precedente come prodotto da un'altra AI;
- cerca attivamente errori, omissioni, regressioni, scope creep e claim non provati;
- durante la sola fase di review **non modifica il repository**.

Le decisioni valide del loop sono:

```text
ACCEPT_AND_CONTINUE
CORRECTIVE
REPLAN
HUMAN_REQUIRED
PROJECT_STEP_COMPLETE
```

`PROJECT_STEP_COMPLETE` non significa “ho finito un singolo task”. Va usato solo quando non esiste più un successivo passo autonomamente consentito verso l'obiettivo complessivo corrente.

---

## 6. Human Gate — regole ferree

Quando ricorre un Human Gate, l'agente deve fermarsi **prima** dell'azione soggetta a gate.

Non aggirare il gate, non degradarlo a semplice warning e non interpretare prudenza generica come autorizzazione.

Sono sempre Human Gate, salvo autorizzazione esplicita e specifica già valida per quella singola azione/run:

### 6.1 Hardware e live

- nuova esecuzione live sul sensore;
- accesso USB Goodix reale;
- invio di comandi sensor-reaching;
- retry live non esplicitamente autorizzato;
- installazione/attivazione runtime che possa raggiungere il sensore;
- operazioni che possano modificare stato persistente;
- qualunque eccezione alle invarianti factory-preserving.

Una autorizzazione live è one-shot e non si riutilizza implicitamente.

### 6.2 Privilegi e protected material

- uso di `sudo`, root o privilegi equivalenti da parte dell'agente nel terminale/ambiente VS Code;
- accesso o manipolazione di PSK, secret, chiavi o protected material non già specificamente autorizzati;
- estrazione di materiale protetto fuori dallo scope approvato.

### 6.3 Git protetto

- qualsiasi modifica di `main`;
- commit su `main`;
- push verso `main`;
- merge in `main`;
- rebase/cherry-pick/update-ref/reset che alteri `main`;
- qualsiasi modifica di `bakcup_pre_agentic_mode`;
- force push;
- amend di commit già condivisi;
- history rewrite;
- reset/stash distruttivo o cancellazione di modifiche preesistenti dell'Utente.

### 6.4 Governance, scope e licensing

- cambiamento materiale dell'obiettivo;
- ampliamento sostanziale dello scope;
- cambio di strategia tecnica con nuovo profilo di rischio;
- modifica del licensing boundary;
- modifica delle policy permanenti o dei guardrail;
- operazioni sul repository pubblico;
- pubblicazione di materiale privato o non auditato.

### 6.5 Ambiguità materiale

L'agente può e deve risolvere autonomamente le normali incertezze tecniche tramite repository, test e documentazione.

Deve invece fermarsi con `HUMAN_REQUIRED` quando esiste una **ambiguità materiale** che:

1. non può essere risolta affidabilmente con le fonti e le evidenze disponibili; **e**
2. una scelta autonoma potrebbe alterare sicurezza, scope, strategia, licensing, stato Git protetto o distruggere/invalidare lavoro significativo.

Non usare l'ambiguità come scappatoia per evitare normale lavoro investigativo.

### 6.6 Blocker reale

Fermarsi anche quando una capability, informazione o risorsa esterna indispensabile non è disponibile e non esiste un percorso autonomo sicuro equivalente.

---

## 7. Git autonomo consentito

### `development`

Consentito:

- modificare file coerenti con lo scope;
- creare commit normali;
- eseguire push normali verso `origin/development`;
- leggere/confrontare altri ref senza modificarli.

Preferire commit coerenti e recuperabili dopo review AI PM positiva o a milestone tecniche chiaramente definite.

Vietato:

- force push;
- rebase distruttivo;
- amend di storia condivisa;
- reset distruttivi;
- cancellazione di lavoro preesistente non attribuito con certezza all'agente;
- switch di branch per aggirare i vincoli.

### `main`

```text
READ / COMPARE: consentito
WRITE / COMMIT / PUSH / MERGE / REBASE / UPDATE-REF: vietato
```

### `bakcup_pre_agentic_mode`

```text
READ / COMPARE: consentito
QUALSIASI MODIFICA: vietata
```

L'esistenza di branch, commit o PR non costituisce da sola prova di correttezza.

---

## 8. Test live e operator kit

Se il progresso richiede un intervento live, USB reale o un'operazione privilegiata dell'Utente, l'agente **non deve eseguirla direttamente**.

Deve preparare, quando tecnicamente possibile, un operator kit in:

```text
<git-root>/operator_kit/<step-o-scopo>/
```

Il kit deve includere almeno:

- script `.sh` eseguibile dall'Utente quando appropriato;
- istruzioni operative in italiano;
- output interattivi dello script in italiano;
- prerequisiti;
- rischio e scopo della run;
- conferme/stop condition necessarie;
- percorso degli output prodotti;
- cleanup/release/reseal quando applicabili;
- comportamento fail-closed leggibile.

Regole:

- l'agente può costruire e verificare offline il kit;
- l'agente non esegue il live;
- l'agente non esegue `sudo` nel workflow attivo VS Code;
- eventuale `sudo` necessario deve trovarsi nel percorso manualmente avviato dall'Utente e deve essere chiaramente visibile nelle istruzioni;
- dopo la preparazione del kit, l'agente termina con `HUMAN_REQUIRED`;
- niente comandi USB/Python improvvisati come sostituto del kit quando un kit dedicato è praticabile.

---

## 9. Riesame metodologico pre-live

Prima di preparare una nuova run live dopo un fallimento, rispondi esplicitamente:

1. **Cosa cambia realmente nel metodo rispetto all'ultimo tentativo?**
2. **Quale nuova ipotesi tecnica viene testata?**
3. **Se fallisce di nuovo nello stesso punto, quale azione diversa verrà intrapresa?**

Pacing, logging, packaging, hash, preflight o altre cautele host-side non costituiscono da soli una nuova ipotesi tecnica.

Se non esiste una risposta sostanziale alle prime due domande, non preparare un terzo tentativo equivalente. Riesamina il metodo e, se il cambio richiesto è materiale, usa `HUMAN_REQUIRED`.

La conclusione metodologica rilevante va integrata nel manuale tecnico. Non creare per default un secondo diario canonico.

---

## 10. Guardrail live da non semplificare

Quando applicabili, preservare:

- autorizzazione esplicita della singola run;
- single-shot;
- zero retry implicito;
- fail-closed su comandi non compresi o potenzialmente persistenti;
- cleanup/release/reseal garantiti anche su uscita anomala;
- verifica del live-critical set contro la baseline approvata;
- diagnostica leggibile del failure.

Questi sono guardrail hardware. Non sostituirli con sola prosa.

---

## 11. Baseline live approvata

Una baseline live revisionata è identificata da un **commit SHA completo approvato esplicitamente dall'Utente** per il percorso live rilevante.

L'agente non deve inventare o auto-approvare tale SHA.

La verifica deve concentrarsi sul live-critical set, normalmente:

- launcher live corrente;
- backend USB reale;
- entrypoint reale;
- moduli che possono inviare comandi USB;
- guardrail software di autorizzazione, single-shot, cleanup/reseal.

Modifiche a manuale, report o test offline non devono invalidare automaticamente una baseline live già approvata.

---

## 12. Manuale tecnico — obbligo permanente

Ogni step che cambia conoscenza, decisioni o stato tecnico deve aggiornare organicamente:

```text
Goodix 27c6 5125 manuale tecnico.md
```

Il manuale è la fonte narrativa canonica dello stato del progetto ed è essenziale per la ripresa autonoma dopo interruzione della sessione.

La conoscenza nuova non deve restare soltanto:

- nel contesto della sessione;
- nel summary finale;
- nei commit message;
- in report isolati;
- negli artefatti Dxxx.

Il manuale non è un log append-only.

Quando cambia lo stato:

- aggiorna le sezioni alte/canoniche interessate;
- aggiorna indice, tabelle, roadmap/stato quando necessario;
- aggiungi una sezione Dxxx solo se utile alla provenance;
- correggi o marca come superate formulazioni stale;
- non duplicare inutilmente contenuto ancora valido.

---

## 13. Executable Closure

Un task non è `READY` solo perché i test unitari passano.

Quando lo step crea, modifica, abilita o dichiara pronto un percorso eseguibile/operator/runtime, verificare nello scope consentito:

- cwd reale;
- import/PYTHONPATH reale;
- path resolution reale;
- modalità di invocazione reale;
- dry-run/offline path reale;
- failure reporting leggibile;
- differenze tra ambiente di test e ambiente operatore.

Se il percorso reale richiede live, USB o privilegi, verificarne offline tutto ciò che è possibile e demandare l'esecuzione effettiva all'operator kit/Human Gate.

Per step puramente documentali o di repository hygiene, `EXECUTABLE_CLOSURE=NOT_APPLICABLE` è legittimo se motivato.

---

## 14. Review set Git-native

Il review set standard è Git-native, non un archivio ZIP.

La superficie di audit comprende:

- baseline Git rilevante;
- HEAD/commit finale o stato corrente del branch;
- diff;
- artefatti Dxxx pertinenti in `analysis/Dxxx/`;
- codice, test e documentazione realmente modificati;
- manuale tecnico.

ZIP, `.zip.b64` e packaging equivalenti non sono requisiti ordinari di closure o trasporto. Possono essere creati solo per reale necessità esplicita.

Non aggiungere a review set o materiale destinato alla pubblicazione:

- secret;
- PSK;
- chiavi TLS;
- dati biometrici reali;
- materiale proprietario non redistribuibile;
- cache/temporanei;
- artefatti storici non modificati senza ragione.

Le evidenze raw private autentiche possono vivere in `<git-root>/captures/` secondo la policy del repository privato e devono essere escluse da futuri export pubblici salvo audit specifico.

---

## 15. Safety telemetry e reporting

Non confondere telemetria di sicurezza con sintesi di progetto.

Quando pertinenti, i report macchina mantengono dati come:

```text
usb_open_count
command_count
tls_count
retry_count
claim/release
cleanup/reseal
ACK/response
persistent_write_family_count
device_state
```

La closure di uno step usa normalmente:

```text
OUTCOME
ADVANCEMENT
EXECUTABLE_CLOSURE
RESIDUAL_BLOCKER_OR_RISK
CANONICAL_DOCUMENTATION
REVIEW_SET
```

Non duplicare gli stessi dati in più report senza necessità.

---

## 16. Licenze, provenance e clean-room boundary

- nuovo core userspace e tool collegati: `core/`, `tools/` = `GPL-2.0-or-later`;
- driver/glue upstream: `libfprint-driver/` = `LGPL-2.1-or-later`;
- riuso diretto di codice Rockytkg GPL è autorizzato solo nel dominio GPL, con commit/path/licenza/copyright/destinazione/modifiche registrati;
- nessuna espressione GPL-only entra nel dominio LGPL senza dual/alternative license valida o implementazione indipendente;
- Rocky è fonte implementativa/corroborativa, non prova target-specific per APP12509;
- safety e comportamento sensor-reaching richiedono evidenza locale;
- il repository privato è il workspace canonico; il pubblico resta congelato fino a export separato, sanitizzato e con audit della history.

Dettagli e ledger:

```text
docs/LICENSING_AND_PROVENANCE.md
```

Snapshot Rockytkg canonico:

```text
<git-root>/Rockytkg/
```

Prima di audit, adattamento o riuso leggere `Rockytkg/PROVENANCE.md`.

---

## 17. Anti-frammentazione

Non creare un nuovo Dxxx per semplici correttivi locali dello stesso milestone.

Un nuovo D-number deve corrispondere ad almeno uno tra:

- nuova evidenza tecnica;
- nuova esecuzione reale;
- nuovo confine protocollo/hardware;
- vera decisione architetturale/licensing/repository;
- avanzamento tecnico sostanziale.

Se due tentativi consecutivi sullo stesso confine device-side non producono nuova evidenza o avanzamento sostanziale, fermare la ripetizione e riesaminare il metodo prima di un terzo tentativo equivalente.

---

## 18. Prompt e configurazione del modello

I task generati durante il loop devono descrivere soltanto il delta necessario: obiettivo, scope, rischi, non-goals, verifiche e criteri di accettazione pertinenti.

**Non prescrivere, raccomandare, registrare o modificare nei documenti di progetto il nome del modello AI o un livello di ragionamento.**

La scelta del modello e della relativa configurazione appartiene all'Utente e all'ambiente VS Code, non al repository.

---

## 19. Modifica delle policy

L'agente autonomo non modifica `AGENTS.md`, `START_PROMPT.md` o le Linee Guida come normale attività tecnica.

Una modifica a questi file di governance richiede una decisione esplicita dell'Utente.

Se durante il loop emerge una discrasia nella procedura:

- non autoriscrivere la costituzione per adattarla al comportamento corrente;
- descrivi la discrasia;
- usa `HUMAN_REQUIRED` se è materiale;
- attendi la decisione dell'Utente.

Questo non impedisce modifiche ai documenti quando l'Utente le richiede esplicitamente, come nello step di governance che ha introdotto la modalità autonoma.

---

## 20. Principio finale

```text
sicurezza hardware forte
+
branch development isolato e recuperabile
+
manuale canonico vivo
+
recovery evidence-first
+
alternanza disciplinata Executor/PM
+
Human Gate espliciti
+
review Git-native
=
autonomia senza perdere controllo
```
