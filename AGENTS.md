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
4. durante bootstrap/recovery leggi integralmente `START_PROMPT.md`, questo
   `AGENTS.md` e le Linee Guida;
5. nel manuale tecnico leggi obbligatoriamente la sezione di stato corrente,
   l'ultimo avanzamento consolidato, la roadmap A→F approvata, la fase corrente
   e i blocker o le decisioni architetturali pertinenti;
6. per ogni claim tecnico storico, cerca nel manuale e leggi la sezione
   pertinente prima di usare quel claim;
7. esamina storia, diff e artefatti necessari allo step.

Il manuale tecnico non richiede lettura integrale per default. Memoria della
sessione e session summary non sono autorità tecniche:

```text
NO TECHNICAL CLAIM FROM MEMORY WHEN THE MANUAL CAN ANSWER IT
```

La lettura integrale del manuale resta eccezionale ed è richiesta soltanto
quando una decisione trasversale o una contraddizione non può essere risolta
con ricerca mirata e lettura delle sezioni rilevanti.

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

Target production iniziale: arrivare su Fedora KDE a uno stack standard
`libfprint -> fprintd -> PAM/KDE` funzionante per Goodix USB `27c6:5125` /
APP12509, preservando integralmente il percorso Windows e lo stato factory.
Altri sistemi, desktop, sensori, firmware/target e utenti AD/LDAP/network sono
fuori scope senza nuova decisione esplicita dell'Utente.

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

### 3.1 Roadmap production approvata

La roadmap A→F approvata dall'Utente il 13 settembre 2026 è il percorso
predefinito:

```text
PHASE_ORDER=A>B>C>D>E>F
```

Il dettaglio e la fase corrente vivono nel manuale tecnico canonico. L'AI PM
può applicare corrective e replan locali nella fase corrente, ma non può
saltare/invertire fasi, iniziare Phase C prima della closure di Phase B,
ampliare il target o cambiare materialmente la roadmap senza nuova decisione
esplicita dell'Utente.

Il materiale storico/deprecato non viene cancellato. L'eventuale archivio
privato `red tag/` può riceverlo solo dopo audit di import, build, test, script,
riferimenti documentali, provenance, licensing e dipendenze production, e dopo
il corretto disaccoppiamento di ciò che è ancora referenziato. Lo spostamento
non è obbligatorio e `red tag/` non è un cestino.

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

### Pragmatism First / Operator Time Is a Project Resource

Per domande tecniche semplici e a basso rischio, preferire il percorso più
diretto, reversibile e osservabile. Non costruire kit, harness, classifier,
state machine o capture framework quando una modifica locale reversibile e uno
smoke test manuale di pochi minuti rispondono affidabilmente al boundary senza
ridurre la safety.

Per ogni modifica software che richiede validazione reale, il default è una
patch installabile minimale, il rollback simmetrico e l'osservazione diretta
del normale workflow target da parte dell'Utente. La diagnostica aggiuntiva
nasce da un failure realmente osservato e resta ad hoc e proporzionata. Se
costo e review del test superano materialmente costo e rischio del test stesso,
rivalutare il metodo. Il tempo dell'Utente è una risorsa progettuale primaria.

```text
TEST_THE_TARGET, NOT_THE_TEST_HARNESS
PATCH_FIRST_LIVE_VALIDATION=true
OPERATOR_KIT_AS_DEFAULT_TEST_METHOD=false
REUSABLE_LIVE_HARNESS_AS_DEFAULT=false
```

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
- sezioni obbligatorie e pertinenti del manuale tecnico;
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

Per una normale live factory-preserving il Human Gate separa ciò che può fare
autonomamente l'AI da ciò che deve eseguire fisicamente l'Utente. Dopo
`HUMAN_REQUIRED` e la consegna di installazione, rollback e istruzioni non è
richiesta una seconda cerimonia: niente approvazione manuale dello SHA, grant,
authorization file, claim/consumo, token, ticket, nonce o autorizzazione della
candidate. La patch deve essere direttamente applicabile dall'Utente. Questo
non consente mai all'AI di installarla né di eseguire live, USB o `sudo`.

Sono sempre Human Gate per l'agente:

### 6.1 Hardware e live

- nuova esecuzione live sul sensore;
- accesso USB Goodix reale;
- invio di comandi sensor-reaching;
- retry automatico o implicito sensor-reaching non provato sicuro;
- installazione/attivazione runtime che possa raggiungere il sensore;
- operazioni che possano modificare stato persistente;
- qualunque eccezione alle invarianti factory-preserving.

Ogni invocazione deve imporre tecnicamente i limiti di action, contatti e retry
pertinenti; non deve delegare la safety a credenziali autorizzative consumabili.

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

## 8. Validazione live patch-first

Se il progresso richiede un intervento live, USB reale o un'operazione
privilegiata dell'Utente, l'agente **non deve eseguirla direttamente**. Prima
del Human Gate deve:

1. implementare e testare offline la modifica;
2. produrre una patch/installazione minimale e reversibile, preferibilmente
   `install.sh`;
3. produrre una patch/disinstallazione o rollback corrispondente e simmetrica,
   preferibilmente `uninstall.sh`;
4. consegnare un README operativo breve e completo;
5. verificare offline i percorsi nel massimo grado consentito;
6. terminare con `HUMAN_REQUIRED` prima di installazione, privilegi, USB o live.

La coppia install/rollback deve essere leggibile, auditabile, limitata al
boundary corrente, fail-closed sui prerequisiti, idempotente quando
ragionevolmente possibile ed esplicita su file, symlink, drop-in, servizi e
configurazioni modificati. Non deve contenere segreti, introdurre dipendenze
permanenti non necessarie o modificare firmware e stato persistente del
sensore. Il rollback deve ripristinare esattamente lo stato precedente previsto
per gli elementi toccati dalla patch.

Il README è obbligatorio e deve contenere:

- scopo della live, modifica/requisito validato e non-oggetto della prova;
- branch/commit/candidate attesa, prerequisiti e condizioni di STOP;
- directory e comandi esatti di installazione, `sudo`/PolicyKit previsto,
  effetti e verifica dell'attivazione;
- soltanto il normale workflow reale da esercitare;
- criteri direttamente osservabili `PASS_IF`, `FAIL_IF` e `STOP_IF`;
- comando e condizioni di rollback, effetti annullati, verifiche successive e
  stato finale atteso;
- cosa riportare all'AI: comportamento osservato, messaggio d'errore e punto
  preciso del failure; log o query read-only vengono richiesti solo dopo un
  failure reale quando necessari.

```text
PATCH_FIRST_LIVE_VALIDATION=true
LIVE_DEBUGGING_METHOD=EMPIRICAL_TARGET_OBSERVATION
INSTALL_PATCH_REQUIRED=true
ROLLBACK_PATCH_REQUIRED=true
PATCH + README OPERATIVO != OPERATOR KIT
```

Non costruire un nuovo Operator Kit, common harness, collector, classifier,
sanitizer, orchestratore, protocollo interattivo artificiale, state machine,
budget engine, simulatore del test o automazione sensor-reaching senza una
nuova autorizzazione esplicita dell'Utente. Dopo un failure reale sono ammessi
comandi read-only mirati, journal/log, query di stato, piccoli comandi one-shot
e test offline proporzionati a spiegare quel failure.

### 8.1 Materiale storico

Gli Operator Kit e `operator_kit/live_probe/` esistenti sono preservati come
evidenza e diagnostica storica, senza essere il default o una dipendenza per le
nuove patch-first live. Non vengono cancellati o spostati automaticamente. Il
complesso kit D293/04 è superato dalla decisione metodologica e non deve essere
ulteriormente raffinato, adattato o ricreato sotto altro nome.

```text
DELETE_HISTORICAL_OPERATOR_KITS=false
EXISTING_OPERATOR_KITS=HISTORICAL_EVIDENCE_ONLY
NEW_OPERATOR_KIT_DEFAULT=false
D293_04_COMPLEX_KIT=SUPERSEDED_BY_METHOD_DECISION
```

### 8.2 Serie bounded VERIFY/MATCH

Ogni validazione live che testa riconoscimento fingerprint, VERIFY/MATCH o un
consumer biometrico reale deve prevedere, salvo diversa decisione esplicita
dell'Utente, una serie tecnicamente bounded e telemetrata di fino a tre
tentativi fisici indipendenti:

```text
MAX_PHYSICAL_ATTEMPTS=3
STOP_ON_FIRST_MATCH=true
NO_MATCH_1_CONTINUE=true
NO_MATCH_2_CONTINUE=true
NO_MATCH_3_TERMINAL=true
FOURTH_ATTEMPT_ALLOWED=false
HIDDEN_OR_UNBOUNDED_RETRY_ALLOWED=false
```

Un solo MATCH chiude con successo la serie. Il production path e il workflow
nativo devono preservare i limiti tecnici e l'osservabilità pertinenti; le
istruzioni operatore rendono inoltre esplicito lo stop senza introdurre un
orchestratore di test. Retry automatici interni vanno evitati oppure devono
essere esplicitamente compresi, bounded e autorizzati dal design. Un test
one-shot è ammesso soltanto su richiesta esplicita dell'Utente o per un boundary
realmente one-shot, con eccezione motivata prima del live. Questa regola
prevale sui default one-shot dei singoli Dxxx.

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

- budget tecnico bounded di action/contatti per invocazione;
- per VERIFY/MATCH o consumer biometrici reali, capacità di tre tentativi
  fisici espliciti, stop al primo MATCH e `NO_MATCH_SERIES` soltanto dopo tre
  NO_MATCH consecutivi, salvo eccezione esplicita/motivata secondo §8.2;
- zero retry automatico o implicito sensor-reaching non provato sicuro;
- nessun quarto tentativo, retry illimitato, nascosto o non telemetrato;
- fail-closed su comandi non compresi o potenzialmente persistenti;
- cleanup/release/reseal garantiti anche su uscita anomala;
- verifica di integrità e provenance del live-critical set realmente eseguito;
- diagnostica leggibile del failure.

Questi sono guardrail hardware. Non sostituirli con sola prosa.

---

## 11. Provenance live e live-critical set

La build e il percorso live realmente eseguiti devono essere identificati con
il commit SHA completo e, quando necessario, con hash del live-critical set.
Lo SHA è provenance, non autorizzazione: una normale live factory-preserving
non richiede uno SHA approvato manualmente dall'Utente né una candidate
autorizzata come prerequisito separato.

La verifica deve concentrarsi sul live-critical set, normalmente:

- launcher live corrente;
- backend USB reale;
- entrypoint reale;
- moduli che possono inviare comandi USB;
- guardrail software sui limiti tecnici di action/retry e su cleanup/reseal.

Modifiche a manuale, report o test offline non devono rendere ambigua la
provenance né invalidare automaticamente un live-critical set invariato.

---

## 12. Manuale tecnico — obbligo permanente

Ogni step che cambia conoscenza, decisioni o stato tecnico deve aggiornare organicamente:

```text
Goodix 27c6 5125 manuale tecnico.md
```

Il manuale è la fonte narrativa canonica dello stato del progetto ed è essenziale per la ripresa autonoma dopo interruzione della sessione.

È l'autorità narrativa tecnica primaria: ogni claim storico deve essere
verificato tramite ricerca mirata e lettura della sezione pertinente. La
memoria della sessione non può sostituirlo. La lettura integrale non è il
default e si usa solo per decisioni trasversali o contraddizioni non risolvibili
con consultazione mirata.

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

Se il percorso reale richiede live, USB o privilegi, verificarne offline tutto
ciò che è possibile e demandare installazione ed esecuzione effettive alla
coppia patch-first e al Human Gate.

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
