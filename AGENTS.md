# AGENTS.md — Goodix 27c6:5125

## 1. Ruolo, autorità e file canonici

Questo file contiene la **governance permanente** per gli agenti AI che lavorano sul progetto Goodix `27c6:5125`.

Ordine di autorità:

1. istruzione esplicita corrente dell'Utente;
2. `<git-root>/AGENTS.md`;
3. repository, codice, test, Git ed evidenze correnti osservabili;
4. `<git-root>/TECHNICAL_MANUAL.md` per la conoscenza tecnica consolidata corrente;
5. `<git-root>/development/GOODIX_27C6_5125_DEVELOPMENT_ARCHIVE.md` esclusivamente come evidenza storica on-demand;
6. altra documentazione pubblica e fonti/reference esterne;
7. contesto della sessione e inferenza del modello.

`<git-root>/START_PROMPT.md` definisce bootstrap, recovery e orchestrazione PM↔Executor. Non può derogare a questo file.

I due file interni canonici di governance/orchestrazione vivono nella **root** del clone:

```text
<git-root>/AGENTS.md
<git-root>/START_PROMPT.md
```

La reference tecnica pubblica resta `<git-root>/TECHNICAL_MANUAL.md`. L'archivio storico interno vive invece in:

```text
<git-root>/development/GOODIX_27C6_5125_DEVELOPMENT_ARCHIVE.md
```

Non assumere path assoluti della workstation: determina sempre la root con `git rev-parse --show-toplevel`.

### Protezione di `AGENTS.md` e `START_PROMPT.md`

`AGENTS.md` e `START_PROMPT.md` sono **read-only per qualunque agente per default**.

Un agente può modificarli soltanto quando:

- l'Utente richiede esplicitamente e specificamente la modifica nella conversazione corrente; oppure
- l'agente propone un `HUMAN_REQUIRED` con `GATE=CANONICAL_FILE_CHANGE_APPROVAL` e l'Utente approva esplicitamente la modifica proposta.

Un generico “procedi”, un'autorizzazione passata o una convenienza tecnica non costituiscono approvazione.

Se l'agente ritiene necessaria una modifica non già autorizzata, deve fermarsi prima di applicarla e riportare almeno:

```text
HUMAN_REQUIRED
GATE=CANONICAL_FILE_CHANGE_APPROVAL
FILES=
REASON=
PROPOSED_CHANGE=
IMPACT=
```

---

## 2. Target e invarianti non negoziabili

Target del progetto: integrazione del lettore Goodix USB `27c6:5125` / APP12509 su Fedora KDE nel normale stack `libfprint -> fprintd -> PAM/KDE`, preservando compatibilità Windows e stato factory del sensore.

Fuori scope senza nuova decisione esplicita dell'Utente: altri sensori/firmware, altri sistemi o desktop, utenti AD/LDAP/network e ampliamenti sostanziali del target.

Invariante principale:

```text
factory_firmware_and_persistent_state_must_remain_untouched
```

Senza autorizzazione esplicita e specifica dell'Utente:

- no flash, IAP, ClearApp o provisioning;
- no sostituzione, overwrite o reprovisioning PSK;
- no PSK random/null;
- no scrittura OTP, factory data o configurazione persistente;
- no cambio persistente di modalità o VID:PID;
- no comando wire non compreso con possibile effetto persistente;
- nessuna regressione intenzionale della compatibilità Windows.

Un'implementazione terza più invasiva non autorizza a replicarne il comportamento sul target locale.

### Update survivability

Invariante di integrazione:

```text
NORMAL_DISTRO_UPDATE_MUST_NOT_BREAK_PASSWORD_LOGIN_OR_DESKTOP
```

Un update può rendere temporaneamente indisponibile il fingerprint o richiedere reinstallazione del driver; non deve compromettere desktop, password login, `sudo` o PolicyKit.

Salvo prova temporanea esplicitamente autorizzata, non trasformare componenti Fedora/KDE/PAM/systemd/sudo/PolicyKit in componenti privati del progetto e non congelare configurazioni vendor in modo da mascherare aggiornamenti successivi. Un blast radius oltre il sottosistema fingerprint è un blocker di release/integration.

---

## 3. Metodo evidence-first e compatibilità reale

Distinguere sempre:

```text
OBSERVED
PROVEN
INFERRED
ASSUMED
UNKNOWN
```

Per una root cause materiale considerare anche evidenze a favore, evidenze contro, spiegazioni alternative, confidenza e il minimo esperimento discriminante utile.

Per claim target-specific su APP12509, safety, persistenza o factory state, preferire nell'ordine: stato reale di repository/host → evidenza corrente → `TECHNICAL_MANUAL.md` → archivio storico mirato quando serve ricostruire provenance o failure precedenti → fonti esterne → memoria/inferenza.

Un claim presente nell'archivio storico non è automaticamente corrente: deve essere verificato contro evidenze successive prima di essere riutilizzato.

```text
NO TECHNICAL CLAIM FROM MEMORY WHEN CURRENT EVIDENCE OR THE TECHNICAL MANUAL CAN ANSWER IT
HISTORICAL_CLAIM_REQUIRES_CURRENT_VALIDATION=true
TECHNICALLY_VALID != PRODUCTION_COMPATIBLE
```

Prima di consolidare una dipendenza, API/ABI, integrazione di sistema o percorso production dipendente dall'ambiente reale:

- verificare il target reale con query read-only e non privilegiate quando possibile;
- non assumere che reference, fork, snapshot, SDK, VM/container o test environment coincidano con production;
- non modificare il sistema per farlo assomigliare alla soluzione desiderata;
- se manca un'informazione target-specific materiale non ottenibile autonomamente, usare `HUMAN_REQUIRED` prima di consolidare la scelta.

### Pragmatismo

Preferire il percorso più semplice, reversibile e osservabile che risponde al boundary tecnico. Non costruire framework, harness, collector, classifier, state machine o automazioni se una modifica locale e una verifica diretta bastano.

```text
TEST_THE_TARGET, NOT_THE_TEST_HARNESS
OPERATOR_TIME_IS_A_PROJECT_RESOURCE=true
```

Una suite verde, un commit o un nuovo artefatto non provano da soli avanzamento o closure.

---

## 4. Git e integrità del worktree

Branch operativo scrivibile:

```text
main
```

Prima di modificare file:

- determina Git root, branch, HEAD e `git status --short`;
- se il branch corrente non è `main`, non cambiare branch autonomamente e termina con `HUMAN_REQUIRED`;
- tratta un worktree sporco come possibile lavoro valido: ricostruiscine provenienza e intento prima di toccarlo.

Su `main` sono consentiti, quando coerenti con il task:

- modifiche normali;
- commit normali;
- push normali a `origin/main`.

Gli altri branch sono read-only salvo autorizzazione esplicita dell'Utente.

Senza autorizzazione esplicita sono vietati:

- force push;
- rebase/history rewrite;
- amend di commit già condivisi;
- merge/cherry-pick/update-ref che alterino la topologia;
- creazione, cancellazione o rinomina di branch;
- reset/stash distruttivi;
- cancellazione o sovrascrittura di lavoro preesistente non attribuito con certezza all'agente.

L'esistenza di commit, branch o PR non prova correttezza tecnica.

---

## 5. Human Gate

Quando ricorre un Human Gate, fermarsi **prima** dell'azione protetta. Non degradare il gate a warning e non inferire autorizzazioni da silenzio, hardware disponibile o precedenti sessioni.

Sono Human Gate:

- live sul sensore reale, accesso USB Goodix reale o comandi sensor-reaching;
- installazione/attivazione runtime che possa raggiungere il sensore;
- `sudo`, root o privilegi equivalenti eseguiti dall'agente;
- accesso/manipolazione di PSK, secret, chiavi, protected material o dati biometrici reali non specificamente autorizzati;
- qualunque possibile modifica persistente del sensore o eccezione alle invarianti factory-preserving;
- cambiamento materiale di obiettivo, scope, strategia tecnica o profilo di rischio;
- modifica del licensing boundary;
- operazioni Git protette definite al §4;
- creazione/pubblicazione di release/tag o distribuzione di materiale privato/non auditato;
- modifica di `AGENTS.md` o `START_PROMPT.md` non già autorizzata esplicitamente;
- modifica, riscrittura o append dell'archivio storico congelato, salvo richiesta esplicita e specifica dell'Utente;
- ambiguità materiale non risolvibile autonomamente quando una scelta errata può compromettere safety, scope, licensing, storia Git o lavoro significativo;
- blocker reale dovuto a capability, informazione o risorsa indispensabile non disponibile.

Le normali incertezze tecniche vanno prima investigate autonomamente con mezzi sicuri e read-only.

Formato minimo, adattabile al caso:

```text
HUMAN_REQUIRED
GATE=
PURPOSE=
EXPECTED_RESULT=
COMMANDS=
RISK=
ROLLBACK=
EVIDENCE_TO_RETURN=
```

Campi non applicabili possono essere marcati `N/A`.

---

## 6. Live validation: patch-first e guardrail hardware

Se la verifica richiede live, USB reale o privilegi dell'Utente, l'agente non la esegue direttamente. Prima del gate deve, quando applicabile:

1. implementare e verificare offline la modifica;
2. preparare installazione minimale e reversibile;
3. preparare rollback/uninstall simmetrico;
4. fornire istruzioni brevi con prerequisiti, comandi, `PASS_IF`, `FAIL_IF`, `STOP_IF`, rollback ed evidenza da riportare;
5. fermarsi con `HUMAN_REQUIRED` prima dell'esecuzione protetta.

Non è richiesta una seconda cerimonia di autorizzazione della candidate dopo il gate: l'Utente esegue manualmente ciò che è stato preparato. Questo non autorizza mai l'agente a usare sudo, USB reale o live.

Il rollback deve essere pronto e auditabile. Dopo PASS non viene eseguito automaticamente: una candidate validata può restare baseline; rollback dopo FAIL, instabilità/regressione, test esplicitamente temporaneo o richiesta dell'Utente.

Per validazioni VERIFY/MATCH o consumer biometrici reali, salvo diversa decisione esplicita:

```text
MAX_PHYSICAL_ATTEMPTS=3
STOP_ON_FIRST_MATCH=true
FOURTH_ATTEMPT_ALLOWED=false
HIDDEN_OR_UNBOUNDED_RETRY_ALLOWED=false
```

In generale preservare:

- budget bounded di action/contatti/retry;
- nessun retry sensor-reaching nascosto o non compreso;
- fail-closed su comandi con possibile effetto persistente non compreso;
- cleanup/release/reseal anche su errore;
- provenance identificabile del percorso live realmente eseguito;
- diagnostica proporzionata e leggibile.

Non creare nuovi Operator Kit, harness o orchestratori live come metodo predefinito. Dopo un failure reale sono ammessi probe read-only, log/query mirati e diagnostica ad hoc proporzionata.

Prima di ripetere una live fallita, deve cambiare almeno l'ipotesi tecnica o il metodo discriminante; pacing, packaging o logging da soli non costituiscono una nuova ipotesi.

---

## 7. Documentazione e memoria tecnica

### Archivio storico di sviluppo

`<git-root>/development/GOODIX_27C6_5125_DEVELOPMENT_ARCHIVE.md` è un **archivio storico congelato**, non una fonte dello stato corrente. Contiene cronologia Dxxx, ipotesi, failure, test, evidenze e corrective dello sviluppo originario.

Regole:

- non leggerlo integralmente per default; usare ricerca mirata solo quando un task richiede precedenti storici, failure già osservati o provenance tecnica;
- non usare un vecchio `Current state`, `Stato corrente`, gate o conclusione Dxxx come stato attuale senza verifica contro repository ed evidenze successive;
- non aggiungere nuovi task, risultati o note e non correggere retroattivamente la cronologia;
- non modificarlo senza richiesta esplicita e specifica dell'Utente nella conversazione corrente;
- quando una nuova evidenza cambia una conoscenza tecnica corrente, aggiornare la fonte corrente appropriata, non l'archivio.

### Manuale pubblico

`<git-root>/TECHNICAL_MANUAL.md` è la reference tecnica pubblica, durevole e orientata allo stato corrente.

**`TECHNICAL_MANUAL.md` contiene conoscenza tecnica stabile, non la cronaca delle prove.**

**`TECHNICAL_MANUAL.md` contiene conoscenza tecnica stabile, non memoria o telecronaca degli agenti.**

**`TECHNICAL_MANUAL.md` contiene conoscenza tecnica stabile, non step-by-step di sviluppo o debug.**

Non inserirvi Dxxx, Human Gate, commit/worktree/push, transcript, tentativi, report AI, output di terminale o dettagli il cui valore principale sia ricordare come si è arrivati allo stato corrente. Se una nuova evidenza cambia un fatto tecnico, aggiornare direttamente il fatto tecnico corrente.

La documentazione pubblica resta in inglese salvo decisione esplicita diversa.

---

## 8. Closure, review e provenance

Un task non è chiuso solo perché compila o ha test verdi. Verificare, quando pertinente:

- diff reale e file modificati;
- test pertinenti e failure path;
- cwd/import/path resolution/modalità di invocazione reali;
- dry-run/offline path quando esiste;
- compatibilità con il target reale;
- documentazione canonica aggiornata se cambia la conoscenza;
- rischio residuo e rollback quando applicabile.

Se il percorso reale richiede Human Gate, verificare offline tutto ciò che è possibile e fermarsi prima dell'esecuzione protetta.

La review standard è Git-native: repository, HEAD, diff, codice, test e documentazione pertinenti. Non creare ZIP o bundle di review senza necessità reale.

Per operazioni sensor-reaching, quando utile alla safety conservare telemetria sufficiente a ricostruire action/comandi/retry/claim-release/cleanup e stato terminale, senza duplicare report inutilmente.

---

## 9. Licensing, protected material e repository hygiene

- preservare licenze e notice per-file esistenti;
- non relicenziare materiale di terzi senza base giuridica esplicita;
- prima di riuso/adattamento di terzi verificare origine, commit/path, licenza, attribution, modifiche e compatibilità dell'insieme risultante;
- mantenere aggiornata la provenance pubblica quando pertinente, in particolare `docs/LICENSING_AND_PROVENANCE.md`;
- non committare o distribuire PSK, secret, chiavi, protected material, dati biometrici reali, cache private o materiale proprietario non redistribuibile;
- usare fixture sintetiche nei test pubblicabili quando possibile;
- non creare nuovi file/artefatti “per completezza” se non hanno un proprietario e uno scopo reali.

Correttivi locali dello stesso boundary non richiedono nuova numerazione Dxxx. Un nuovo artefatto decisionale deve corrispondere a nuova evidenza, nuovo confine tecnico o decisione materiale, non alla semplice cronaca dell'attività dell'agente.

---

## 10. Orchestrazione e configurazione modello

L'orchestrazione PM↔Executor è definita esclusivamente da `START_PROMPT.md`.

I task interni devono descrivere soltanto il delta necessario: obiettivo, stato rilevante, scope, lavoro richiesto, verifica e stop condition. Non reidratare questa governance nei prompt intermedi.

Non prescrivere o registrare nel repository nomi di modelli AI o livelli di reasoning: la scelta appartiene all'Utente e all'ambiente di esecuzione.

Principio operativo:

```text
safety forte
+ evidence-first
+ target reale verificato
+ main recuperabile
+ Human Gate espliciti
+ documentazione con ownership chiara
+ task delta-only
= autonomia senza perdita di controllo
```
