# Linee Guida di Progetto Goodix 27c6:5125 per AI

> **Versione**: 2.6 — Revisione 30 agosto 2026
**Stato**: Attivo; sostituisce la v2.5 del 27 agosto 2026
**Motivazione**: La v2.6 mantiene invarianti factory-preserving, evidence-first, executable closure, licensing/provenance e review Git-native della v2.5, ma cambia il modello operativo per rimuovere l'Utente dal ruolo di relay continuo tra AI PM e AI esecutrice. Introduce una **standing delegation** per il lavoro autonomo non-live entro un envelope già approvato, un **orchestratore deterministico** non-AI che trasferisce task e risultati, una state machine PM → Executor → PM, Human Gate espliciti per le decisioni materiali e le capability sensibili, separazione tecnica tra ambiente host-only e live runner, pausa fail-closed su quota/modello indisponibile e divieto di fallback automatico verso API a consumo. L'Utente conserva autorità finale e viene coinvolto soltanto quando una decisione supera la delega permanente o richiede una capability protetta.
> 

---

## 1. Scopo del documento

Questo documento definisce come devono operare, nel progetto Goodix 27c6:5125, i tre soggetti decisionali coinvolti:

- **Utente**: autorità umana finale, proprietario dell'hardware e dell'ambiente operativo reale.
- **AI Project Manager (AI PM)**: pianificatrice tecnica, responsabile della decomposizione, della guidance, della supervisione e della review.
- **AI esecutrice**: implementatrice, responsabile della consegna tecnica nel repository.

A supporto dei tre soggetti può operare un **orchestratore deterministico locale**. L'orchestratore non è una quarta AI e non possiede autorità tecnica o di governance: trasferisce task e risultati, applica policy meccaniche, persiste stato, controlla capability e arresta il flusso sui Human Gate.

Le linee guida sono vincolanti per qualsiasi modello AI impiegato nel progetto (ChatGPT, Codex, Aider, Qwen o futuri strumenti equivalenti) e per qualsiasi orchestratore o runner che ne automatizzi il flusso.

Il repository privato di sviluppo è il workspace canonico. La root reale va determinata dal repository stesso, ad esempio con `git rev-parse --show-toplevel`; non si deve assumere un path locale hard-coded se il clone viene rinominato o spostato.

Il manuale tecnico canonico è sempre:

```
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

---

## 2. Obiettivo generale

Arrivare in modo tecnicamente fondato, riproducibile e documentato a uno stack Linux funzionante per il sensore **Goodix USB 27c6:5125**. Il risultato atteso comprende:

- comprensione documentata del protocollo;
- userspace core e/o integrazione driver coerente con l'architettura Linux/libfprint;
- preservazione totale di firmware residente, PSK/OTP, factory data e configurazione persistente;
- compatibilità mantenuta con il percorso Windows preesistente;
- procedura di build, test, installazione e rollback documentata;
- materiale verificabile e con provenance sufficiente per review futura.

**Invariante assoluto**: `factory_firmware_and_persistent_state_must_remain_untouched`.

Supporto Linux ≠ riprovisionamento del sensore.

---

## 3. Principi fondamentali gerarchizzati

In caso di conflitto tra principi, l'ordine seguente è vincolante.

### 3.1 Factory-preserving — massima priorità

Nessuna operazione deve modificare firmware, PSK, OTP, factory data o configurazione persistente del sensore. Questo principio non si bilancia con comodità implementativa, velocità, automazione o compatibilità con codice esterno.

### 3.2 Eseguibilità reale > correttezza teorica

Quando uno step produce o modifica un percorso eseguibile, il codice deve funzionare nell'ambiente reale dell'operatore: stesso comando, `cwd`, meccanismo di import/PYTHONPATH e, quando pertinente, stesso contesto di privilegi. Una suite offline verde non dimostra executable closure.

### 3.3 Avanzamento di confine > produzione di artefatti

Review set, report e numerazione Dxxx non sono di per sé avanzamento. Avanzamento tecnico reale significa nuova esecuzione, nuova evidenza, nuovo comportamento/protocollo compreso o nuovo confine hardware raggiunto. Una decisione architetturale, di licensing, repository o orchestrazione che cambia realmente lo stato del progetto può essere uno step legittimo, ma deve essere dichiarata come avanzamento non hardware e non confusa con evidenza device-side.

### 3.4 Conservatività operativa, non cerimoniale

Preferire cambi piccoli, verificabili e reversibili. Non trasformare la sicurezza in accumulo di preflight, marker, sealing, hash o report che non riducono un rischio reale. La conservatività si misura nella capacità di prevenire danni e fare rollback, non nella quantità di cerimonia.

### 3.5 Fail-closed intelligente

L'AI non deve dichiarare completato un task in presenza di ambiguità hardware o di comportamento non compreso. Non deve però inventare blocker di governance host-side quando il dispositivo è già protetto e il problema non incide sul rischio reale. L'orchestrazione deve fermarsi automaticamente quando incontra un Human Gate, una capability non autorizzata, una quota esaurita o una condizione che supera la standing delegation.

### 3.6 Evidence-first

Distinguere sempre tra **osservato**, **verificato**, **inferito**, **ipotizzato** e **non noto**. Non promuovere ipotesi a fatti.

### 3.7 Nessuna conoscenza confinata nella chat o nella sessione agente

La conoscenza tecnica o metodologica rilevante deve essere integrata nel manuale o negli artefatti canonici; non deve rimanere solo in chat, sessioni PM/Executor, report isolati o artefatti temporanei. La ripresa dopo crash, pausa quota o nuova sessione deve dipendere da stato persistito e fonti canoniche, non dalla memoria effimera del modello.

### 3.8 Autorità umana finale senza relay umano obbligatorio

L'Utente mantiene sempre la decisione finale su obiettivo generale, factory-preserving, rischio live, cambi materiali di scope/strategia, capability sensibili, merge in `main`, history rewrite, pubblicazione e sospensione del progetto.

Questa autorità **non implica** che l'Utente debba approvare o trasferire manualmente ogni prompt, risultato, review o corrective. Entro la standing delegation definita dalla v2.6, AI PM e AI esecutrice possono concatenare autonomamente step non-live tramite l'orchestratore. L'Utente viene coinvolto solo quando si verifica un Human Gate o quando decide volontariamente di intervenire.

### 3.9 Capability separation > divieti solo linguistici

Quando tecnicamente praticabile, i vincoli critici devono essere enforceable dall'infrastruttura: un executor host-only non deve avere accesso al sensore, ai privilegi o ai secret reali solo perché un prompt glielo vieta. Le capability live, Git distruttive e sensibili devono essere separate e concesse dal supervisore deterministico soltanto dopo il gate richiesto.

---

## 4. Autorità di governance e autorità probatoria

### 4.1 Governance

Per le regole di processo e sicurezza valgono, in ordine:

1. decisione, revoca o Human Gate esplicito corrente dell'Utente;
2. versione MD canonica corrente delle presenti linee guida nel repository privato;
3. `AGENTS.md` come sintesi operativa persistente;
4. envelope/state machine dell'orchestratore, purché derivati dalle fonti 1-3 e senza possibilità di ampliarle;
5. prompt/task Dxxx corrente emesso dall'AI PM entro la standing delegation;
6. manuale tecnico per lo stato tecnico corrente.

Un prompt specifico non può rilassare implicitamente un vincolo permanente. Una vera eccezione deve essere esplicita, limitata e autorizzata dall'Utente.

Un prompt Dxxx **non richiede approvazione manuale separata dell'Utente** quando:

- resta integralmente dentro la standing delegation;
- non apre alcun Human Gate;
- non amplia scope o capability;
- è stato prodotto dall'AI PM dopo review del risultato precedente o come bootstrap approvato.

L'AI PM e l'orchestratore non possono auto-modificare la standing delegation né auto-approvare un Human Gate.

### 4.2 Autorità probatoria tecnica

Per affermazioni target-specific su `GF_ST411SEC_APP_12509`, sicurezza, persistenza, PSK/factory state e comportamento del device, la priorità è:

1. stato reale del repository e dell'ambiente host;
2. evidenza locale prodotta da test ripetibili, capture canoniche, `gfusb.dll`, APP12509 e live autorizzati;
3. manuale tecnico canonico;
4. report e artefatti degli step precedenti;
5. fonti esterne, implementazioni terze e conversazioni esterne;
6. contenuto delle chat o delle sessioni agente;
7. supposizioni del modello.

Una fonte esterna può essere eccellente per implementazione o corroborazione senza diventare prova primaria del target 12509.

---

## 5. Ruoli

### 5.1 Utente — Human Authority

- definisce obiettivo generale e priorità;
- approva la standing delegation e può restringerla o revocarla in qualunque momento;
- autorizza i Human Gate;
- autorizza scope expansion o cambi strategici materiali;
- autorizza operazioni live, sensibili, irreversibili o di history rewrite;
- autorizza merge in `main` e pubblicazione;
- può sospendere, correggere o terminare il flusso in qualunque momento;
- **non è il relay ordinario** tra AI PM e AI esecutrice.

### 5.2 AI Project Manager

- definisce criteri di accettazione coerenti con lo scope già autorizzato;
- individua rischi, dipendenze ed esclusioni;
- prepara task piccoli ma non artificialmente frammentati, con un path di esecuzione chiaro quando applicabile;
- sceglie la classe di modello/ragionamento appropriata e vieta downgrade silenziosi;
- riesamina diff, test, report, review set e stato reale del repository;
- verifica aggiornamento organico del manuale;
- emette una decisione strutturata `ACCEPT`, `CORRECTIVE`, `REPLAN`, `HUMAN_GATE`, `PAUSE` o `DONE`;
- prepara e invia autonomamente il task successivo all'AI esecutrice quando la decisione resta dentro la standing delegation;
- non approva governance host-side aggiuntiva se non riduce un rischio reale;
- non auto-autorizza live, scope expansion, merge, history rewrite o altre capability soggette a Human Gate;
- in modalità orchestrata opera preferibilmente come reviewer/planner senza capability dirette di modifica del worktree o del sensore.

### 5.3 AI esecutrice

- opera nel worktree/branch assegnato e legge prima il contesto canonico;
- identifica root, branch, HEAD e stato Git;
- applica il cambiamento minimo necessario;
- esegue test coerenti con lo scope;
- quando esiste un percorso eseguibile, verifica executable closure nel contesto appropriato;
- aggiorna ricorsivamente e organicamente il manuale tecnico canonico;
- rende disponibile un review set step-local versionato nel repository, senza creare ZIP o Base64 salvo necessità esplicita;
- riporta limiti, rischi e verifiche con linguaggio fedele all'evidenza;
- non decide autonomamente di ampliare scope o capability;
- non può usare capability live/sensibili non concesse dal supervisore.

### 5.4 Orchestratore deterministico — infrastruttura, non quarto decisore

L'orchestratore:

- mantiene la state machine del flusso;
- trasferisce task PM → Executor e risultati Executor → PM senza intervento manuale dell'Utente;
- persiste gli identificatori necessari a ripresa, audit e idempotenza;
- applica allow-list, capability, policy Git e Human Gate meccanici;
- crea o assegna worktree/branch di task secondo policy;
- mantiene, quando previsto, un branch di integrazione autonomo separato da `main` e lo avanza solo fast-forward dopo `ACCEPT` dell'AI PM;
- può aprire/aggiornare PR e superfici di notifica quando autorizzato dalla standing delegation;
- arresta e persiste il flusso su gate, quota, errore infrastrutturale o stato non determinabile;
- non interpreta autonomamente evidenze tecniche e non prende decisioni architetturali: queste appartengono all'AI PM o all'Utente;
- non può trasformare un `HUMAN_GATE` in `ACCEPT` né ampliare la propria allow-list.

---

## 6. Procedura obbligatoria per ogni step

### 6.1 Preparazione dello step — AI PM

Prima di consegnare il task:

- chiarire obiettivo preciso sulla base dello stato canonico;
- definire scope, rischi, esclusioni e criteri di completamento;
- indicare classe di ragionamento/modello appropriata;
- creare il prompt come file `.md` versionabile o persistibile dall'orchestratore, non come testo che richiede copia/incolla dell'Utente;
- richiedere aggiornamento del manuale canonico;
- richiedere un review set step-local Git-native, identificabile tramite baseline, HEAD/commit e file rilevanti;
- dichiarare il `GATE_CLASS` dello step e le capability necessarie;
- vietare espansioni di scope non autorizzate.

### 6.2 Handoff automatico PM → Executor

In modalità orchestrata il task `.md` viene passato direttamente all'AI esecutrice. L'Utente non deve scaricarlo, leggerlo, copiarlo o inoltrarlo per consentire l'esecuzione ordinaria.

Prima del dispatch l'orchestratore verifica almeno:

- task identificabile e non già eseguito in modo ambiguo;
- baseline/ref attesa;
- capability richieste consentite dalla standing delegation;
- assenza di Human Gate pendenti;
- modello richiesto disponibile nell'allow-list;
- quota sufficiente oppure possibilità di mettere il task in pausa senza fallback a pagamento.

### 6.3 Lettura iniziale — AI esecutrice

Prima di modificare file:

- determinare la Git root reale;
- leggere linee guida canoniche, `AGENTS.md`, manuale e prompt dello step;
- esaminare gli step precedenti pertinenti;
- controllare stato Git e baseline;
- identificare file, launcher, test e artefatti coinvolti;
- verificare le capability effettivamente disponibili e non tentare di aggirarne l'assenza.

### 6.4 Analisi preliminare

Dichiarare sinteticamente:

- obiettivo compreso;
- stato iniziale osservato;
- file presumibilmente coinvolti;
- rischi principali;
- esclusioni;
- criteri di completamento.

In caso di contraddizione sostanziale, l'AI esecutrice non chiede automaticamente all'Utente: restituisce il problema all'AI PM. L'AI PM risolve autonomamente se la decisione resta dentro lo scope delegato; altrimenti emette `HUMAN_GATE`.

### 6.5 Implementazione

- cambiamento minimo;
- no refactoring globali non richiesti;
- no nuove dipendenze senza necessità documentata;
- no modifiche a file storici come effetto collaterale;
- no occultamento di modifiche automatiche o generate;
- no risultati dipendenti da stato sporco non controllato;
- usare directory temporanee per simulazioni distruttive;
- rispettare sempre sicurezza, capability e scope.

### 6.6 Verifica tecnica

- eseguire test pertinenti;
- ripetere test quando serve dimostrare determinismo;
- confrontare hash/blob prima e dopo quando rilevante;
- verificare modifiche fuori scope;
- distinguere test passati, falliti, saltati e non disponibili;
- non mascherare pass parziali come completamento.

### 6.7 Handoff automatico Executor → PM e prosecuzione

Il risultato torna direttamente all'AI PM insieme a baseline, HEAD/ref, diff, test, report e documentazione canonica aggiornata.

L'AI PM deve emettere una sola disposition macchina primaria:

- `ACCEPT` — step chiuso; può generare il successivo entro la standing delegation;
- `CORRECTIVE` — genera e invia un corrective nello stesso boundary quando possibile;
- `REPLAN` — cambia metodo restando dentro scope/capability già delegati;
- `HUMAN_GATE` — arresto obbligatorio in attesa dell'Utente;
- `PAUSE` — arresto recuperabile per quota/modello/infrastruttura;
- `DONE` — obiettivo delegato completato, nessun task successivo automatico.

Il loop ordinario è quindi:

```
AI PM -> AI esecutrice -> AI PM -> decisione -> [AI esecutrice | Human Gate | pausa | fine]
```

L'Utente non è un hop di trasporto del loop.

---

## 7. Executable Closure Gate

L'Executable Closure Gate è **vincolante quando lo step crea, modifica, abilita o dichiara pronto un percorso eseguibile/operator/runtime**. Per step puramente documentali, di licensing, provenance o repository hygiene che dimostrano assenza di modifiche runtime, il valore corretto è `NOT_APPLICABLE`.

Quando applicabile, prima di dichiarare lo step ready l'AI esecutrice deve:

1. eseguire il launcher nel modo in cui verrebbe realmente invocato dall'operatore, oppure il dry-run/preflight equivalente quando il live non è autorizzato;
2. usare stesso comando shell, `cwd`, meccanismo di import/PYTHONPATH e contesto di privilegi pertinente;
3. confrontare ambiente di test e ambiente operativo;
4. considerare bloccanti errori come `ModuleNotFoundError`, `PermissionError`, path errati o marker incoerenti se impediscono l'esecuzione reale;
5. dare priorità al fallimento del launcher rispetto a una suite offline verde.

Un review set perfettamente ordinato non rende eseguibile un launcher rotto.

---

## 8. Review interna, chiusura tecnica e review AI PM

### 8.1 Review interna

Prima di chiudere lo step, l'AI esecutrice verifica:

- requisito iniziale realmente soddisfatto;
- executable closure superata o correttamente `NOT_APPLICABLE`;
- diff non più ampio del necessario;
- assenza di file inattesi o assunzioni non dimostrate;
- test pertinenti realmente probanti;
- manuale coerente con il nuovo stato;
- review set limitato ai file e alle evidenze necessarie allo step.

### 8.2 Chiusura tecnica

Uno step può essere `READY` solo se:

- criteri di accettazione soddisfatti;
- executable closure `PASS` oppure `NOT_APPLICABLE` per ragione documentata;
- limiti residui espliciti;
- manuale aggiornato quando cambia stato o conoscenza;
- review set identificabile e verificabile nel repository;
- report finale fedele.

### 8.3 Review esterna — AI PM

L'AI PM deve:

- confrontare risultato e prompt originale;
- verificare lo stato reale del repository, non solo il summary dell'AI esecutrice;
- verificare diff, report, test e review set;
- controllare executable closure quando applicabile;
- controllare coerenza del manuale;
- distinguere blocker reali da limiti accettabili;
- decidere `ACCEPT`, `CORRECTIVE`, `REPLAN`, `HUMAN_GATE`, `PAUSE` o `DONE`;
- preparare e dispatchare automaticamente lo step successivo quando la decisione resta dentro la standing delegation.

L'AI PM **non deve chiedere all'Utente l'accettazione ordinaria di ogni step host-only**. Deve coinvolgerlo soltanto quando la decisione ricade nei Human Gate definiti dalla governance o quando non può stabilire in modo affidabile che la decisione resti dentro la delega.

Se commit/branch/PR e gli artefatti dello step sono disponibili nel repository remoto accessibile all'AI PM, la review avviene direttamente sullo stato Git e sui file versionati. L'Utente non deve creare, scaricare, riconvertire, ricaricare o inoltrare ZIP/Base64, prompt o summary per consentire la review.

---

## 9. Manuale tecnico canonico

`Goodix 27c6 5125 manuale tecnico.md` nella Git root è la **fonte narrativa canonica dello stato tecnico**.

L'AI esecutrice deve integrare organicamente ogni nuova conoscenza, decisione, correzione o cambiamento di stato. Il manuale:

- non deve diventare un log append-only di step o review set;
- deve aggiornare sezioni alte/canoniche quando cambia una decisione;
- aggiunge una sezione Dxxx solo quando utile a provenance o ricostruzione;
- mantiene indice, tabelle, spiegazioni e stato tecnico coerenti;
- non lascia conoscenza nuova solo in chat, report o artefatti di review;
- non duplica o depreca inutilmente contenuto ancora valido.

Le presenti linee guida regolano **come lavorare**; il manuale descrive **cosa sappiamo tecnicamente e qual è lo stato corrente**. Gli snapshot tecnici volatili non appartengono alle linee guida.

---

## 10. Review set Git-native e repository hygiene

Al termine di ogni step l'AI esecutrice rende disponibile un **review set step-local Git-native**. Il review set non è un archivio separato: è l'insieme verificabile delle modifiche, evidenze e documentazione versionate nel repository e necessarie alla review dello step.

La superficie di audit standard è costituita da:

- baseline Git rilevante;
- HEAD/commit finale, oppure branch/PR quando il commit finale non è ancora stato integrato;
- diff rispetto alla baseline;
- artefatti Dxxx in `analysis/Dxxx/`;
- file di codice, test e documentazione realmente modificati dallo step.

Regole permanenti:

- output Dxxx e report step-local risiedono in `analysis/Dxxx/`;
- non duplicare manuale, policy, storia o file non modificati solo per rendere il review set autosufficiente;
- niente cache, file temporanei, backup `.orig/.bak`, credenziali, PSK, chiavi TLS, firmware/DLL OEM, capture reali o dati biometrici nei review set o artefatti destinati alla pubblicazione;
- il report dello step indica baseline/commit o ref rilevante e riferimenti al manuale quando necessari alla review;
- eventuali artefatti storici vengono relocati solo byte-preserving e solo se il move non rompe consumatori eseguibili o riproducibilità;
- eccezioni di compatibilità sono documentate e possono restare in root se necessarie alla executable closure storica;
- i bundle ZIP storici già versionati restano evidenza storica e non devono essere cancellati, rigenerati o riconvertiti senza una ragione tecnica specifica.

ZIP, `.zip.b64` e altri packaging equivalenti **non sono requisiti di closure né mezzi di trasporto standard**. Possono essere creati solo quando una piattaforma, un destinatario o un'attività di export lo richiede esplicitamente; in tal caso devono restare temporanei quando possibile, non duplicare inutilmente il tree canonico e usare hash/round-trip solo quando servono a proteggere un rischio concreto. Il repository Git resta la fonte canonica per la review.

---

## 11. Git e integrità del repository

### 11.1 Separazione delle capability Git

In modalità orchestrata si applica il principio del minimo privilegio:

- **AI esecutrice**: può modificare e committare soltanto nel worktree/branch di task assegnato; non deve spostare `main`, fare merge o riscrivere history;
- **AI PM**: review e decisione; preferibilmente nessuna capability diretta di scrittura Git;
- **orchestratore**: può creare/assegnare worktree e task branch, eseguire push fast-forward, e mantenere un **branch di integrazione autonomo** separato da `main`; dopo `ACCEPT` dell'AI PM può avanzare tale branch solo fast-forward al commit accettato e usarlo come baseline del task successivo; può inoltre aprire/aggiornare PR quando previsto dalla standing delegation;
- **Utente**: mantiene il gate per merge del branch di integrazione in `main`, force operation, history rewrite e pubblicazione salvo futura delega esplicita più restrittivamente definita.

Regole permanenti:

- non assumere che uno stato sporco sia baseline valida;
- non cancellare modifiche dell'Utente;
- non eseguire reset distruttivi senza Human Gate;
- commit e push sono ammessi autonomamente **solo sul task branch assegnato o sul branch di integrazione autonomo tramite fast-forward controllato dall'orchestratore** e solo entro la standing delegation;
- nessun merge in `main` senza Human Gate esplicito;
- nessun rebase, amend, force push o history rewrite senza Human Gate esplicito e specifico;
- non installare hook Git o modificare configurazioni Git globali/utente senza autorizzazione specifica;
- non aggiungere artefatti generati fuori scope;
- spiegare ogni modifica retroattiva necessaria;
- l'orchestratore deve rifiutare aggiornamenti di ref non fast-forward salvo Human Gate dedicato.

### 11.2 Baseline Git approvata per il live-critical set

Per i percorsi live evitare pinning SHA-256 manuale diffuso di manuali, report e test. Quando serve una baseline live, identificarla con un commit SHA completo reviewato dall'AI PM e legato al relativo Human Gate dell'Utente.

La verifica di integrità riguarda il **live-critical set**, normalmente:

- launcher live corrente;
- backend USB reale;
- entrypoint reale;
- moduli che possono inviare comandi USB o cambiare il percorso live;
- guardrail che implementano single-shot, cleanup/reseal o autorizzazione operatore.

Modifiche a manuale, report, manifest o test offline non devono invalidare automaticamente una baseline live già approvata.

Né Codex, né l'AI PM, né l'orchestratore possono inventare o auto-approvare un commit SHA per un live. Hash per-file indipendenti sono ammessi quando proteggono un artefatto esterno o un rischio concreto non coperto dalla baseline Git, non come cerimonia generalizzata.

---

## 12. Sicurezza hardware, firmware e host

### 12.1 Operazioni permanentemente vietate nel progetto

La standing delegation e i Human Gate **non possono** autorizzare:

- flashing, erase, ClearApp, provisioning o IAP del firmware;
- modifica del firmware residente;
- provisioning, sostituzione o randomizzazione della PSK factory;
- scrittura OTP, factory data o configurazione persistente;
- cambio permanente di VID:PID o modalità boot;
- procedure che rendano incerta la compatibilità Windows successiva;
- introduzione intenzionale di una persistent-write family non già dimostrata sicura e necessaria allo scope factory-preserving.

Una futura eccezione a questi invarianti richiederebbe un diverso progetto/governance, non un semplice Human Gate della v2.6.

### 12.2 Capability soggette a Human Gate

Salvo futura delega esplicita dell'Utente, richiedono Human Gate specifico:

- apertura/claim/accesso USB reale e qualunque comando sensor-reaching;
- esecuzione live sul Goodix;
- uso di protected material o secret reali oltre un preflight esplicitamente già delegato;
- `sudo`, root o privilegi equivalenti;
- accesso della Windows VM/OEM path al sensore per nuove evidenze;
- installazione/attivazione runtime di driver, plugin libfprint/fprintd o PAM;
- merge in `main` e pubblicazione;
- operazioni Git distruttive o history rewrite;
- cambi di scope/strategia che alterano in modo materiale safety boundary, licensing boundary, architettura canonica o obiettivo approvato.

### 12.3 Standing delegation host-only

Sono autonomamente delegabili, quando non richiedono capability della sezione 12.2:

- lettura e analisi del repository;
- progettazione e review AI PM;
- modifica codice/documenti su task branch;
- build, test, sanitizer e fixture offline;
- dry-run e preflight senza apertura del device;
- aggiornamento del manuale;
- commit/push fast-forward su task branch e PR;
- corrective e replan nello stesso scope;
- step host-only successivi coerenti con l'obiettivo già approvato.

### 12.4 Capability separation e live runner

L'ambiente standard dell'AI esecutrice deve essere **host-only**. Quando tecnicamente praticabile deve essere privo di:

- accesso a `/dev/bus/usb` del Goodix;
- `sudo`/root;
- protected material/secret reali;
- credenziali o capability per aggiornare `main`;
- capability di pubblicazione.

Il percorso live deve essere eseguito da un **live runner separato e deterministico**, non dalla libera shell dell'AI esecutrice. Il runner può eseguire soltanto l'azione/baseline esplicitamente autorizzata dal Human Gate.

Un Human Gate live deve essere:

- legato a un `GATE_ID` univoco;
- legato a commit/ref e azione precisa;
- one-shot salvo diversa autorizzazione esplicita;
- non trasferibile a un task successivo;
- invalidato da cambi live-critical non reviewati;
- consumato o revocato al termine dell'azione;
- `retry_count=0` per default.

`LIVE_AUTHORIZED` è quindi `false` per default e non si eredita da un precedente step o da una precedente sessione.

### 12.5 Gerarchia di sicurezza

La sicurezza dispositivo ha priorità massima. La sicurezza host-side è secondaria e deve servire la prima.

Guardrail economici che riducono direttamente un rischio sul device vanno preservati: autorizzazione esplicita, capability separation, single-shot, zero retry implicito, fail-closed sui comandi non compresi o persistenti, cleanup/release/reseal, verifica del live-critical set.

Preflight, marker, sealing e reporting host-side non devono diventare un ostacolo insuperabile se non proteggono un rischio reale. Un meccanismo host-side che blocca ripetutamente l'esecuzione senza migliorare la safety va semplificato, corretto o rimosso, non ulteriormente stratificato.

---

## 13. Observability dei failure

Quando un gate o launcher fallisce, il sistema deve esporre immediatamente una causa redatta e utile.

Sono insufficienti messaggi come `root preflight failed`, `unexpected_ack` o `import failed` senza dettaglio.

Quando pertinenti, il report deve rendere visibili almeno:

- classificazione del failure;
- path/modulo/marker coinvolto;
- ACK/response o frame osservato;
- `USB_OPEN_COUNT` e se il live è iniziato;
- stato cleanup/reseal;
- eventuale contatore retry.

Un gate che produce diagnostica ma la nasconde all'operatore è un gate fallito.

---

## 14. Evidenze e linguaggio tecnico

Ogni affermazione importante va classificata come:

- **osservato**: derivato direttamente da file, test o catture;
- **verificato**: confermato da procedura ripetibile;
- **inferito**: dedotto da più evidenze ma non dimostrato direttamente;
- **ipotizzato**: spiegazione plausibile da verificare;
- **non noto**: informazione non disponibile.

Non usare implementazioni terze, commenti esterni o analogie come sostituto della validazione target-specific.

---

## 15. Scope, milestone e regole anti-frammentazione

Ogni milestone deve ridurre almeno una incertezza reale tra protocollo, firmware, inizializzazione, USB, cifratura, formato dati, interfaccia driver, integrazione libfprint, build, test, riproducibilità, sicurezza o manutenzione.

### 15.1 Fix di classe, non di singolo sintomo

Se un fallimento appartiene a una classe (per esempio policy ACK troppo stretta), la correzione deve coprire l'intera classe prima della nuova run. Evitare successioni di patch una-opcode-alla-volta quando il pattern è già riconoscibile.

### 15.2 Audit orizzontale prima del live

Prima di autorizzare una nuova run live, le fasi del percorso atteso devono avere policy ACK/response e failure handling coerenti con transcript/capture disponibili.

### 15.3 Prerequisiti locali nello stesso step

Difetti locali emersi durante la costruzione di un operator kit (shell, import, path, quoting, marker fixture) vanno chiusi nello stesso Dxxx quando possibile. Non creare automaticamente D+1 per correggere un difetto locale di D.

### 15.4 Numerazione Dxxx ≠ avanzamento

Un nuovo numero Dxxx è giustificato da almeno uno tra:

- nuova esecuzione reale autorizzata;
- nuova evidenza tecnica;
- nuovo confine protocollo/hardware;
- decisione architetturale/licensing/repository che cambia realmente lo stato del progetto.

Una correzione locale senza nuovo confine resta nello stesso Dxxx con revisione degli artefatti.

### 15.5 Stop metodologico

Se due tentativi consecutivi orientati allo stesso confine device-side non producono nuova evidenza o un avanzamento sostanziale, l'AI PM deve fermare la ripetizione e riesaminare il metodo prima di proporre un terzo tentativo equivalente.

Questa regola non vieta step deliberatamente non hardware, come licensing, provenance o repository hygiene, purché siano dichiarati per ciò che sono e non usati per fingere avanzamento device-side.

---

## 16. [AGENTS.md](http://AGENTS.md), prompt Codex e contratti macchina

### 16.1 [AGENTS.md](http://AGENTS.md) come costituzione operativa persistente

La root deve contenere `AGENTS.md` con un riepilogo breve e stabile delle regole permanenti necessarie a Codex. `AGENTS.md` non deve diventare copia integrale delle presenti linee guida né del manuale.

Deve contenere almeno:

- root/manuale canonici;
- invarianti factory-preserving e compatibilità Windows;
- standing delegation e Human Gate;
- capability separation host-only/live;
- disciplina Git e scope;
- ciclo Design → Implementazione → Esecuzione/Review;
- definizione di avanzamento reale;
- riesame metodologico pre-live;
- aggiornamento organico del manuale;
- review set step-local Git-native;
- closure minima;
- distinzione safety telemetry / project reporting;
- licensing boundary e regole minime di provenance post-D247;
- repository hygiene minima post-D248;
- divieto di fallback silenzioso su modello o API a consumo.

`AGENTS.md` è un'istruzione operativa derivata, non una fonte normativa alternativa e non può contraddire il MD canonico.

### 16.2 Prompt Dxxx: delta dello step e handoff automatico

Il prompt specifico non deve ricopiare inutilmente regole permanenti già in `AGENTS.md` e nelle linee guida. Deve contenere:

- classe di modello/ragionamento richiesta;
- contesto tecnico strettamente necessario;
- obiettivo specifico;
- scope e file particolari;
- criteri di accettazione specifici;
- `GATE_CLASS` e capability necessarie;
- eventuali eccezioni esplicitamente autorizzate;
- obbligo di aggiornare organicamente il manuale canonico.

Il prompt resta un file `.md` identificabile e auditabile, ma in modalità orchestrata **non deve essere consegnato all'Utente per il semplice trasporto**. L'orchestratore lo passa direttamente all'AI esecutrice.

La prevenzione dei conflitti avviene riducendo la duplicazione, non dichiarando artificialmente una fonte "insuperabile".

### 16.3 Contratto macchina minimo AI PM

In modalità orchestrata, oltre al testo tecnico, l'AI PM deve produrre campi strutturati sufficienti perché l'orchestratore non debba interpretare liberamente il linguaggio naturale. Almeno:

- `TASK_ID`;
- `BASELINE`;
- `EXECUTOR_MODEL_CLASS`;
- `GATE_CLASS`;
- `REQUIRED_CAPABILITIES`;
- `DISPOSITION`;
- `NEXT_TASK` oppure `NONE`;
- `HUMAN_GATE_ID` quando applicabile.

L'orchestratore valida lo schema e fallisce chiuso se i campi necessari sono mancanti o contraddittori.

---

## 17. Riesame metodologico pre-live

Prima di preparare o autorizzare una nuova run live dopo un fallimento precedente, l'AI esecutrice deve produrre un blocco conciso che risponda a tre domande:

1. **Cosa cambia realmente nel metodo rispetto all'ultimo tentativo?**
2. **Quale nuova ipotesi tecnica viene testata?**
3. **Se fallisce di nuovo nello stesso punto, quale azione diversa verrà intrapresa?**

Il riesame deve distinguere una variazione sostanziale da modifiche cosmetiche a pacing, logging, packaging, hash, preflight o altre cautele host-side.

Se non esiste una risposta sostanziale alle prime due domande, non va creato un nuovo step live solo per ripetere lo stesso esperimento con nuova cerimonia.

Non creare per default un secondo diario metodologico: la conclusione rilevante confluisce nel manuale canonico.

---

## 18. Architettura software e licensing boundary post-D247

La decisione D247 introduce una separazione intenzionale:

```
core/              GPL-2.0-or-later
  transport
  protocol
  tls
  fdt
  capture
  image
      |
      | licensing boundary
      v
libfprint-driver/  LGPL-2.1-or-later

tools/             GPL-2.0-or-later
```

Il materiale originale già pubblicato fino a D246 sotto BSD-2-Clause conserva quella concessione: non viene relicenziato retroattivamente. Codice di terzi mantiene i propri termini. Firmware/DLL OEM, capture, secret, materiale biometrico, factory data e asset non redistribuibili non ricevono alcuna blanket open-source license.

L'architettura post-D247 è stata adottata **precisamente per consentire il riuso diretto, l'adattamento e l'integrazione nel dominio GPL del codice esterno compatibile GPL**, preservando licenza, attribution e provenance. Il licensing boundary non vieta il riuso: impedisce che espressione GPL-only entri involontariamente nel driver upstream-facing LGPL.

Codice con una licenza LGPL compatibile può essere valutato per `libfprint-driver/` dopo audit per-file dei diritti, degli header SPDX, dei contributi e delle eventuali origini terze. Espressione GPL-only può entrare nel driver LGPL solo in presenza di dual licensing o licenza alternativa compatibile concessa da tutti i titolari pertinenti; in assenza, il driver deve essere implementato indipendentemente da specifiche, fatti di protocollo, test ed evidenza.

---

## 19. Rockytkg: fonte implementativa, non autorità probatoria

Snapshot locale canonico di riferimento:

`<git-root>/Rockytkg/`

La scheda di provenance dello snapshot è:

`<git-root>/Rockytkg/PROVENANCE.md`

Per audit, confronto, adattamento o riuso del materiale Rockytkg, Codex e le altre AI devono usare **come riferimento operativo unico** lo snapshot presente nella Git root e leggere prima `Rockytkg/PROVENANCE.md`. Il repository online non è una dipendenza del normale workflow: lo snapshot locale è preservato e versionato proprio per mantenere disponibile la conoscenza anche in assenza della fonte remota e per consentire analisi offline.

Conversazione tecnica principale:

[Issue #1 — goodix-linux-27c6-5125](https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1)

Codice Rockytkg verificato come compatibile GPL può essere letto, copiato, adattato e incorporato nel dominio GPL `core/`/`tools/`, con licenza, attribution e provenance. Eventuale codice specificamente disponibile sotto licenza LGPL compatibile può essere valutato per il dominio LGPL dopo audit per-file. La presenza di un file nello snapshot non implica automaticamente che esso sia coperto dalla licenza GPL/LGPL del codice: valgono le eccezioni e i diritti descritti nella scheda di provenance e nei file di licenza originali, in particolare per firmware/vendor material e componenti terzi.

Questo permesso non promuove Rockytkg a prova primaria per APP12509 e non dimostra da solo safety, assenza di persistenza, compatibilità con PSK/factory state o correttezza sul target locale. Ogni comportamento sensor-reaching richiede validazione differenziale locale e, quando necessario, autorizzazione live separata.

---

## 20. Provenance permanente

Ogni import o adattamento di codice esterno registra almeno:

- repository e commit/ref sorgente;
- path sorgente;
- licenza/SPDX originale;
- copyright holder noto;
- eventuali componenti o contributi di terzi;
- data/step locale;
- path di destinazione;
- natura delle modifiche.

Preservare gli header applicabili e non assumere che la licenza repository-level copra automaticamente ogni file o dipendenza.

Il ledger operativo è `docs/LICENSING_AND_PROVENANCE.md`.

---

## 21. Pubblicazione e confine privato/pubblico

Il repository privato è il workspace canonico di sviluppo.

Il repository pubblico resta una superficie congelata finché uno step separato non esegue sanitizzazione e audit di **contenuto e history**.

L'uguaglianza del working tree non dimostra che la storia privata sia pubblicabile. Quando necessario usare clean export, nuova storia o filtri espliciti, senza sincronizzazione automatica.

Nessuna operazione sul repository pubblico è implicita nelle attività sul privato.

---

## 22. Closure, disposition di orchestrazione e safety telemetry

La sintesi finale di ogni step usa, salvo necessità concreta, i sei campi tecnici canonici:

1. `OUTCOME` — `READY` | `BLOCKED` + classificazione tecnica breve;
2. `ADVANCEMENT` — esecuzione reale, nuova evidenza, avanzamento architetturale/non hardware oppure `NONE`, senza fingere device progress;
3. `EXECUTABLE_CLOSURE` — `PASS` | `FAIL` | `NOT_APPLICABLE`;
4. `RESIDUAL_BLOCKER_OR_RISK` — descrizione sintetica;
5. `CANONICAL_DOCUMENTATION` — manuale aggiornato sì/no + sezioni toccate;
6. `REVIEW_SET` — baseline + HEAD/commit (o branch/PR) e path/file rilevanti che compongono il review set step-local.

In modalità orchestrata si aggiungono obbligatoriamente:

7. `PM_DISPOSITION` — `ACCEPT` | `CORRECTIVE` | `REPLAN` | `HUMAN_GATE` | `PAUSE` | `DONE`;
8. `NEXT_ACTION` — task successivo identificabile oppure `NONE`;
9. `GATE_STATE` — `NONE` oppure `PENDING:<GATE_ID>`;
10. `RATE_LIMIT_STATE` — stato utile a decidere prosecuzione o pausa senza consumo alternativo.

Campi aggiuntivi sono ammessi quando rappresentano informazione tecnica non derivabile e realmente utile.

La riduzione della closure non riduce la safety telemetry. I report macchina possono e devono conservare, quando pertinenti:

- `usb_open_count`;
- `command_count`;
- `tls_count`;
- `retry_count`;
- D4/application-data reachability;
- claim/release;
- cleanup/reseal;
- device state;
- ACK/response osservati;
- persistent-write-family count.

Questi dati non devono essere duplicati in molte fonti con nomi differenti quando una singola fonte macchina è sufficiente.

---

## 23. Criterio generale di qualità

La qualità non si misura in:

- numero di file prodotti;
- numero di test offline passati;
- numero di report o artefatti di review;
- numero di step Dxxx.

La qualità si misura in:

- riduzione di un'incertezza reale;
- repository più comprensibile;
- progetto più riproducibile;
- assenza di rischi nascosti;
- documentazione chiara di ciò che è noto e non noto;
- avanzamento concreto verso lo stack Linux finale;
- quando lo step è device-oriented, avanzamento o apprendimento reale al confine device-side.

---

## 24. Fonte normativa canonica e modifica della policy

Il file:

```
<git-root>/Linee Guida di Progetto Goodix 27c6 5125 per AI.md
```

sul branch canonico privato è la **fonte normativa primaria delle linee guida**. Eventuali pagine Notion o copie locali sono superfici di authoring, consultazione o backup e non prevalgono sul file versionato nel repository.

Regole:

- una modifica di policy richiede decisione esplicita dell'Utente;
- dopo tale decisione, l'AI può applicare direttamente al MD canonico la modifica espressamente delegata, con incremento di versione e commit identificabile;
- AI PM, AI esecutrice e orchestratore **non possono auto-emendare la governance** per facilitare un task o superare un gate;
- `AGENTS.md` resta una sintesi operativa derivata e deve essere mantenuto coerente, ma non sostituisce né supera il MD;
- il manuale tecnico resta separatamente la fonte narrativa canonica dello **stato tecnico**, non delle regole permanenti di governance;
- ogni divergenza tra `AGENTS.md` e il MD canonico deve essere risolta aggiornando `AGENTS.md`, non reinterpretando il MD.

---

## 25. Orchestrazione autonoma, standing delegation e Human Gate

### 25.1 Obiettivo operativo

La v2.6 elimina il relay umano ordinario tra AI PM e AI esecutrice. Il sistema deve poter avanzare autonomamente per più step host-only consecutivi, fermandosi soltanto quando:

- serve una decisione materiale dell'Utente;
- serve una capability soggetta a Human Gate;
- si esaurisce la quota o il modello richiesto non è disponibile;
- emerge un errore infrastrutturale non recuperabile in modo deterministico;
- l'AI PM dichiara `DONE` o un blocker non risolvibile entro la delega.

### 25.2 Standing delegation iniziale

Con l'approvazione della v2.6 l'Utente delega permanentemente, fino a revoca o modifica, le seguenti attività non-live:

- pianificazione AI PM entro l'obiettivo e la safety boundary già approvati;
- generazione e dispatch di prompt Dxxx;
- implementazione e test host-only;
- review AI PM;
- corrective e replan entro lo stesso scope;
- aggiornamento del manuale;
- gestione di task branch/worktree e push fast-forward;
- avanzamento fast-forward del branch di integrazione autonomo dopo `ACCEPT` AI PM, senza toccare `main`;
- apertura/aggiornamento di PR private;
- prosecuzione automatica allo step host-only successivo quando l'AI PM emette `ACCEPT`.

La standing delegation non include le capability elencate nella sezione 12.2.

### 25.3 Human Gate

Il Human Gate è l'unico meccanismo ordinario che richiede l'intervento dell'Utente durante il loop autonomo.

Il gate deve presentare in modo conciso almeno:

- `GATE_ID`;
- decisione richiesta;
- ragione tecnica;
- commit/ref e, se pertinente, live-critical set;
- azione esatta che verrebbe sbloccata;
- rischi residui noti;
- cosa resta tecnicamente impossibile o vietato anche dopo l'approvazione.

Il meccanismo iniziale preferito per i gate è una **issue o superficie equivalente nel repository GitHub privato**, in modo che le normali notifiche GitHub possano raggiungere l'Utente anche via email/mobile. L'implementazione deve verificare che l'approvazione provenga dall'identità GitHub autorizzata dell'Utente.

Per evitare autorizzazioni ambigue, l'approvazione deve usare una forma strutturata equivalente a:

```
/approve <GATE_ID>
```

oppure:

```
/deny <GATE_ID>
```

Il gate non può essere approvato da AI PM, AI esecutrice o orchestratore.

### 25.4 Pausa per quota, modello o infrastruttura

Quando il modello richiesto o la quota inclusa nel piano non sono disponibili:

- salvare stato e review set;
- impostare `PM_DISPOSITION=PAUSE` o stato macchina equivalente;
- non degradare silenziosamente a un modello non autorizzato;
- non passare automaticamente ad API a consumo, crediti pay-as-you-go o provider a pagamento;
- riprendere dal medesimo stato quando la risorsa torna disponibile, previa verifica di baseline e idempotenza.

L'esaurimento token è una pausa operativa, non un motivo per ridurre safety o qualità.

### 25.5 Ripresa, idempotenza e crash recovery

L'orchestratore deve poter riprendere dopo reboot, crash o perdita della sessione AI senza affidarsi alla memoria della chat. Prima di rieseguire un'azione deve stabilire se essa è:

- non iniziata;
- iniziata ma non conclusa;
- conclusa e già reviewata;
- conclusa ma in attesa di review;
- in attesa di Human Gate;
- in pausa quota/modello.

Azioni con effetti esterni devono avere identificatori/idempotency guard sufficienti a evitare doppia esecuzione involontaria.

### 25.6 Bootstrap obbligatorio prima dell'autopilot Goodix

Dal passaggio alla v2.6 l'avanzamento funzionale Goodix viene intenzionalmente sospeso durante la costruzione dell'orchestrazione, salvo esplicita riapertura dell'Utente.

Prima di usare l'autopilot per nuovi step tecnici Goodix devono essere dimostrati almeno:

- loop PM → Executor → PM senza relay umano;
- `ACCEPT`, `CORRECTIVE`, `REPLAN`, `HUMAN_GATE`, `PAUSE` e `DONE` gestiti correttamente;
- persistenza e ripresa dopo arresto simulato;
- impossibilità dell'executor host-only di raggiungere il sensore o usare `sudo`;
- impossibilità di merge/main o history rewrite senza gate;
- funzionamento del branch di integrazione autonomo con avanzamento solo fast-forward dopo `ACCEPT`;
- `AGENTS.md` sincronizzato con la v2.6 e nessuna contraddizione operativa residua;
- stop reale su Human Gate e ripresa solo dopo approvazione valida;
- pausa pulita su quota/modello indisponibile e nessun fallback a pagamento;
- review reale di diff/test/manuale da parte dell'AI PM;
- assenza di secret nei log/stato/notifiche;
- almeno un ciclo sintetico completo e un ciclo reale host-only a basso rischio.

Solo dopo questa closure l'AI PM può dichiarare `ORCHESTRATION_READY_FOR_GOODIX=true` e proporre all'Utente l'eventuale riapertura del boundary tecnico corrente.

---

## 26. Principio sintetico della v2.6

**sicurezza hardware forte e capability separation**

+

**AI PM ed Executor collegati direttamente, senza Utente-relay**

+

**standing delegation per il lavoro host-only**

+

**Human Gate stretti per live, scope materiale, main e operazioni distruttive**

+

**evidence-first, executable closure e review Git-native**

+

**manuale tecnico e stato persistente come memoria del progetto**

+

**pausa fail-closed su quota/modello, senza fallback a pagamento**

=

**più autonomia delle AI senza cedere all'automazione l'autorità umana o la safety del sensore**
