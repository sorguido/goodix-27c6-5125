# AGENTS.md — Goodix 27c6:5125

## 1. Scopo e gerarchia

Questo file è la costituzione operativa persistente per l'agente AI che lavora nel repository Goodix 27c6:5125.

Le fonti principali sono:

1. decisione esplicita corrente dell'Utente;
2. `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`;
3. questo `AGENTS.md`;
4. `Goodix 27c6 5125 manuale tecnico.md` per lo stato tecnico corrente;
5. evidenze versionate nel repository.

Una decisione esplicita corrente dell'Utente può modificare o derogare in modo limitato la governance. L'avvio manuale di un operator kit live da parte dell'Utente costituisce di per sé scelta operativa sufficiente per quella esecuzione: non richiede frasi di autorizzazione, grant, token, file one-shot o approvazioni rituali.

`START_PROMPT.md` definisce il bootstrap/recovery e il loop autonomo PM↔Executor.

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

## 6. Gate umani — solo decisioni materiali e operazioni protette

`HUMAN_REQUIRED` è riservato a decisioni realmente materiali o a operazioni che escono dalle invarianti del progetto. Non va usato come cerimonia per normali test live già confinati da un operator kit factory-preserving.

### 6.1 Live ordinario

NON richiedono una autorizzazione separata, un grant, un token one-shot o una baseline approvata dall'Utente:

- avvio manuale di un operator kit live factory-preserving;
- accesso USB Goodix reale previsto dal kit;
- comandi sensor-reaching già compresi e confinati dal kit;
- `sudo` digitato dall'Utente per avviare il kit;
- riesecuzione manuale del kit dopo review del risultato, purché il kit non segnali `RECOVERY_REQUIRED` e non cambi scope/rischio.

L'atto di eseguire il comando del kit è sufficiente. Restano vietati retry automatici o impliciti dentro una singola action quando il protocollo non li prevede.

### 6.2 Operazioni realmente protette

Richiedono decisione esplicita dell'Utente:

- qualunque eccezione all'invariante factory-preserving;
- flash, IAP, ClearApp, provisioning, sostituzione/reprovisioning PSK, OTP/factory/persistent writes o cambio persistente VID:PID/mode;
- accesso o trasferimento di protected material fuori dallo scope già definito;
- installazioni permanenti o modifiche persistenti del sistema non previste dal piano corrente;
- qualunque comando wire non compreso con possibile effetto persistente.

### 6.3 Git protetto

Richiedono decisione esplicita dell'Utente:

- qualsiasi modifica di `main`;
- commit/push/merge/rebase/cherry-pick/update-ref/reset che alteri `main`;
- qualsiasi modifica di `bakcup_pre_agentic_mode`;
- force push, amend di storia condivisa o history rewrite;
- reset/stash distruttivo o cancellazione di modifiche preesistenti dell'Utente.

### 6.4 Governance, scope e licensing

Richiedono decisione esplicita dell'Utente:

- cambiamento materiale dell'obiettivo o ampliamento sostanziale dello scope;
- cambio di strategia con nuovo profilo di rischio;
- modifica del licensing boundary;
- modifica delle policy permanenti;
- operazioni sul repository pubblico o pubblicazione di materiale privato/non auditato.

### 6.5 Ambiguità materiale e blocker reale

Le normali incertezze tecniche vanno risolte autonomamente. Usa `HUMAN_REQUIRED` solo se una scelta non risolvibile dalle fonti potrebbe alterare materialmente sicurezza, scope, strategia, licensing, Git protetto o distruggere lavoro significativo, oppure se manca una capability esterna indispensabile.

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

Se il progresso richiede live, USB reale o privilegi, l'agente prepara quando possibile un operator kit in:

```text
<git-root>/operator_kit/<step-o-scopo>/
```

Il kit deve essere **direttamente eseguibile dall'Utente** e partire al primo comando utile, senza flussi di attivazione separati. Deve includere almeno:

- script `.sh` eseguibile e istruzioni operative in italiano;
- prerequisiti realmente necessari;
- rischio, scopo e comportamento atteso;
- output/evidenze e failure reporting leggibili;
- cleanup/release/reseal quando applicabili;
- guardrail tecnici fail-closed.

Regole permanenti:

- niente grant, token, authorization file, claim one-shot o frasi rituali di autorizzazione;
- niente step `prepare authorization` / `activate` separati dalla normale preparazione tecnica;
- il kit registra automaticamente HEAD/build/provenance necessari alla review;
- eventuale `sudo` deve essere visibile nel comando avviato dall'Utente, ma non richiede una seconda autorizzazione;
- il kit può fare preflight tecnici automatici e deve fallire prima del sensor-reaching se l'ambiente è incompatibile;
- retry **automatici/impliciti** sensor-reaching restano vietati salvo semantica protocollo già provata; una nuova invocazione manuale del kit non richiede un nuovo grant;
- non sostituire un kit dedicato con comandi USB/Python improvvisati quando il kit è praticabile;
- l'agente non deve trasformare hash, marker o audit host-side in cerimonie che impediscono l'avvio senza ridurre un rischio reale.

---

## 9. Riesame metodologico pre-live

Prima di preparare una nuova run live dopo un fallimento, rispondi esplicitamente:

1. **Cosa cambia realmente nel metodo rispetto all'ultimo tentativo?**
2. **Quale nuova ipotesi tecnica viene testata?**
3. **Se fallisce di nuovo nello stesso punto, quale azione diversa verrà intrapresa?**

Pacing, logging, packaging, hash, preflight o altre cautele host-side non costituiscono da soli una nuova ipotesi tecnica.

Se non esiste una risposta sostanziale alle prime due domande, non preparare un tentativo equivalente: riesamina e correggi il metodo. Usa `HUMAN_REQUIRED` solo se il cambio richiesto modifica materialmente scope, rischio o invarianti.

La conclusione metodologica rilevante va integrata nel manuale tecnico. Non creare per default un secondo diario canonico.

---

## 10. Guardrail live tecnici

Quando applicabili, preservare:

- zero retry automatico/implicito non provato;
- limiti espliciti di action/contatti quando il protocollo li richiede;
- fail-closed su comandi non compresi o potenzialmente persistenti;
- cleanup/release/reseal garantiti anche su uscita anomala;
- verifica automatica del live-critical set rispetto al commit/build effettivamente eseguito;
- diagnostica ed evidenza raccolte prima del cleanup quando possibile;
- distinzione tra failure protocollo/safety e failure di parser/audit host-side.

Non sono guardrail hardware e non vanno reintrodotti: autorizzazioni rituali, grant one-shot, token di consenso, approvazione manuale dello SHA o passaggi di attivazione separati.

---

## 11. Provenance della live

Ogni kit live deve registrare automaticamente il commit SHA completo e gli hash del live-critical set/build effettivamente eseguito. Questo serve alla **provenance**, non come meccanismo autorizzativo.

Il launcher deve rifiutare worktree/live-critical drift non previsto quando tale drift rende ambigua la provenance; non deve richiedere che l'Utente “approvi” preventivamente lo SHA.

La review successiva usa SHA, hash, log e artefatti per stabilire cosa è stato realmente eseguito.

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

Se il percorso reale richiede live, USB o privilegi, verificarne offline tutto ciò che è possibile e demandare l'esecuzione effettiva al relativo operator kit avviato direttamente dall'Utente.

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

## 16. Licenze, provenance e compatibilità della distribuzione

- nuovo core userspace e tool collegati: `core/`, `tools/` = `GPL-2.0-or-later`;
- `libfprint-driver/` conserva la licenza per-file esistente; `LGPL-2.1-or-later` è il default per nuovo codice locale, non un vincolo architetturale assoluto sulla fork Goodix o sul combined work distribuito;
- il riuso diretto o l'adattamento minimo di codice Rockytkg è la via preferita quando licenza, attribution, provenance e compatibilità della distribuzione risultante lo consentono;
- espressione GPL-only può entrare nel percorso production/libfprint soltanto sotto termini GPL-compatible applicabili all'insieme risultante: non diventa LGPL e non autorizza il relicensing indiscriminato di file di terzi;
- prima del riuso verificare per file commit/path/licenza/copyright/destinazione/modifiche e aggiornare il ledger; l'implementazione indipendente è fallback quando esiste un blocker concreto di licenza o integrazione;
- Rocky è reference implementativa primaria per il percorso SIGFM, ma non prova target-specific per APP12509;
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
- usa `HUMAN_REQUIRED` solo se è materiale e richiede realmente una decisione dell'Utente;
- altrimenti correggi autonomamente la procedura.

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
gate umani limitati alle sole decisioni materiali
+
review Git-native
=
autonomia senza perdere controllo
```
