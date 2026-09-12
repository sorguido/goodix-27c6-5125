<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 — stato complessivo e piano delle prossime fasi

Data review: 12 settembre 2026

Baseline esaminata: `development` con D291 transport provato e stabilità
biometrica ancora aperta

Decisione PM: transport multi-VERIFY D291 provato live; la baseline pinned non
è una root cause dimostrata e la closure biometrica non è consentita. Serve un
replan evidence-first; nessuna live equivalente e nessuna fase successiva
avviata

## Conclusione esecutiva

Il progetto ha superato il confine di fattibilità: sul target APP12509 sono
provati enrollment, template FP3, matching SIGFM, integrazione libfprint/fprintd
e i consumer reali `sudo`, KDE lock/unlock e Plasma Login Manager. D290 chiude
la catena fingerprint → nuova sessione Plasma/Wayland.

Il divario immediato è ora D291: comprendere la variabilità biometrica senza
ripetere una live equivalente e senza scegliere una correzione speculativa.
Una volta risolto quel boundary, il divario di prodotto resta trasformare la
candidate target-proven, oggi distribuita tra fork Fedora, componenti locali e
installazione D285, in un prodotto coerente, gestibile, aggiornabile e
distribuibile. Le fasi sotto privilegiano lavoro offline e ambienti host
isolati. Una nuova live ha senso soltanto dopo una nuova ipotesi causale e un
delta production che cambi materialmente il percorso osservato.

```text
D290_CLOSED_SUCCESSFULLY=true
D291_MULTI_VERIFY_TRANSPORT_LIVE=PROVEN
D291_BASELINE_PINNING=IMPLEMENTED_NOT_VALIDATED
D291_BIOMETRIC_STABILITY=OPEN
D291_CLOSURE=NOT_ALLOWED
D291_NEW_LIVE_REQUIRED_NOW=false
PROJECT_FEASIBILITY=PROVEN_ON_TARGET_APP12509
PRODUCTION_READY=false
NEXT_WORK_CLASS=INTEGRATION_PACKAGING_LIFECYCLE_RELEASE
NEW_D292_STARTED=false
```

## Stato verificato del progetto

### Definitivamente PROVEN nello scope osservato

- Protocollo target e acquisizione: USB A0/B0, secure session TLS 1.2 PSK,
  configurazione volatile usata, FDT, record immagine, decode `80x64`, release
  tail e lifecycle nominale hanno attraversato il sensore reale senza retry di
  transport e senza famiglie di scrittura persistente note.
- Enrollment e template: enrollment SIGFM production a otto campioni; FP3
  serializzato, riletto dopo close/open e usato per identify/verify; storage,
  restart, list e delete fprintd sono stati attraversati.
- Matcher: stesso dito `MATCH` e dito differente `NO_MATCH` sono provati sul
  target con threshold 40; la telemetria per-sample è reale. Questo non è uno
  studio statistico FAR/FRR e non qualifica da solo una soglia universale.
- libfprint/fprintd: la fork minima Fedora 44/libfprint 1.94.100 registra il
  target, usa il vero `FpImageDevice`, SIGFM e le action ENROLL/VERIFY/IDENTIFY;
  il daemon Fedora, D-Bus, storage FP3 e restart sono provati nel percorso
  target.
- Consumer reali: PAM dedicato, `sudo`, PAM dell'utente attivo,
  KScreenLocker in modalità ufficiale, sblocco di una sessione KDE realmente
  bloccata e login passwordless di Plasma Login Manager verso una nuova
  sessione Wayland sono provati.
- Persistenza host D285/D286: runtime hash-pinned, template single-user,
  restart e sopravvivenza al reboot sono provati; fallback password e
  readiness dell'uninstall sono stati auditati nello scope D285/D286.

### IMPLEMENTED, ma non production-ready

- D291 ha provato live che ogni nuovo `VerifyStart` esplicito dopo terminal
  NO_MATCH raggiunge una nuova epoch drained, senza retry o acquisizioni
  nascoste. Il pinning della baseline R2 ha prodotto un MATCH live a score 47,
  seguito però da sei NO_MATCH consecutivi con il dito registrato, inclusi due
  primi epoch con baseline appena acquisita. Il test precedente provava solo
  la meccanica pinned su un frame grezzo artificialmente fisso; il nuovo test
  session-coupled mostra che B0 e frame devono essere variati insieme. Senza
  fixture reali decodificate, la root cause e la stabilità restano aperte.
- Driver e integrazione SIGFM funzionano nella fork Fedora preservata, ma il
  delta production non è ancora presentato come una singola patch series o
  sorgente di build mantenibile rispetto a un upstream scelto.
- L'installazione attiva D285 sotto `/usr/local` è single-host, single-user e
  legata a SHA/versioni esatte. È un'installazione sperimentale recuperabile,
  non un package di distribuzione.
- La riga `pam_fprintd.so max-tries=3 timeout=45 debug` nel PAM package-owned
  `plasmalogin` è funzionalmente provata, ma è una modifica manuale che un
  aggiornamento RPM può sovrascrivere. Non è la strategia di configurazione
  definitiva.
- Guardrail, audit e test host-only sono estesi e utili, ma molti sono legati a
  operator kit storici. Devono restare evidenza/regressione, non diventare il
  framework di installazione del prodotto.

### Prototipo, PoC o materiale storico

- I percorsi Python e i tool GPL storici, i launcher one-shot e i kit Dxxx
  restano oracle, evidenza e diagnostica; non sono una UI o un installer per
  l'utente finale.
- Le overlay PAM, gli staging in `/run`, i grant/token storici e il kit
  persistente D290 sono audit-only. D290 overlay e micro-kit sono
  `HISTORICAL_ONLY` / `DO_NOT_RERUN`.
- Le seam sintetiche, i fake backend e i profili test-only sono necessari alle
  regressioni ma non devono risultare raggiungibili nella build production.

### Factory state e compatibilità Windows

Le live chiuse hanno imposto allowlist factory-preserving e riportano zero
flash/IAP/ClearApp/provisioning/OTP e zero famiglie di scrittura persistente
note. Nessuna regressione Windows intenzionale è stata introdotta. Questo è un
risultato forte ma corpus-bounded: la telemetria di allowlist non prova
l'assenza assoluta di ogni possibile mutazione NVM interna, e il repository non
contiene una qualificazione Windows completa successiva a ogni singola live
Linux. Non si deve elevare il claim oltre:

```text
KNOWN_PERSISTENT_WRITE_FAMILY_COUNT=0_IN_REVIEWED_LIVE_PATHS
FACTORY_PRESERVING_GUARDRAILS=PASS_IN_REVIEWED_LIVE_PATHS
ABSOLUTE_SENSOR_NVM_NONMUTATION=NOT_PROVEN
CURRENT_WINDOWS_REGRESSION_QUALIFICATION=NOT_EXHAUSTIVE
```

## Blocker reali e debiti non bloccanti

Blocker di produzione:

- manca una topologia sorgente/build unica e mantenibile;
- mancano package, install/upgrade/uninstall transazionali e una policy per
  dipendenze OpenCV, systemd, SELinux e PAM;
- mancano modello multi-user, lifecycle amministrativo dei template e
  provisioning lecito dei materiali runtime protetti su una macchina nuova;
- restano da chiudere cancellazione/quiescenza device-side arbitraria,
  suspend/resume, hotplug e concorrenza fra consumer;
- prima di distribuire serve chiudere regime del combined work, attribution e
  audit dei contenuti/history pubblicabili.

Debiti non bloccanti per la fattibilità già provata:

- FAR/FRR, qualità fra utenti/dita e criteri quantitativi di release non sono
  caratterizzati;
- il README pubblico è obsoleto e dichiara ancora assente un driver Linux;
- nomenclatura e suite storiche sono frammentate in molti Dxxx;
- supporto oltre Fedora 44, oltre questo host e oltre APP12509 non è provato.

## Roadmap proposta

L'ordine è intenzionale: prima si definisce e consolida ciò che verrà
distribuito; poi si costruiscono gestione utenti e packaging; soltanto dopo si
qualificano i boundary lifecycle realmente nuovi.

### Phase A — consolidamento della sorgente production

- **OBIETTIVO:** scegliere una sola baseline libfprint mantenibile e trasformare
  i delta target-proven in una patch series/build production riproducibile,
  separando nettamente test seam, reference tree e codice storico.
- **PERCHÉ SERVE:** oggi la funzione è provata, ma la sorgente autorevole è
  distribuita fra `libfprint-driver/`, la fork Fedora preservata e componenti
  SIGFM/R2 con licenze diverse.
- **PREREQUISITI:** evidenze D279–D290, `Rockytkg/PROVENANCE.md`, ledger
  `docs/LICENSING_AND_PROVENANCE.md`, versioni Fedora attualmente pin-nate.
- **OUTPUT ATTESO:** architecture decision record; inventario source-of-truth;
  patch series o tree integrato; build normal e sanitizer riproducibile;
  profilo production senza seam/test override raggiungibili.
- **RISCHIO:** medio; regressioni ABI/lifecycle e scelta del regime GPL-compatible.
- **HUMAN GATE:** nessuno per audit, build e test offline. È richiesta decisione
  dell'Utente prima di un cambio materiale del licensing boundary o della
  strategia di distribuzione.
- **CRITERIO DI CHIUSURA:** clean build dalla sola sorgente dichiarata, ABI
  fprintd verificata, suite production pertinenti verdi e mapping completo da
  ogni file distribuito a provenance/licenza.

### Phase B — modello utenti, enrollment e dati protetti

- **OBIETTIVO:** sostituire assunzioni single-user/hard-coded con un lifecycle
  amministrativo definito per enroll/list/verify/delete, ownership e accesso
  concorrente, mantenendo i template nello storage standard fprintd.
- **PERCHÉ SERVE:** il percorso corrente prova un utente e un FP3; non definisce
  comportamento per più utenti, re-enrollment, template drift o macchina nuova.
- **PREREQUISITI:** source-of-truth Phase A; policy esplicita su origine,
  installazione e protezione dei materiali PE/FDT/PSK senza pubblicarli.
- **OUTPUT ATTESO:** specifica del data model; comandi amministrativi e policy
  Polkit/PAM; casi zero/uno/più template; backup/migrazione/delete ownership-pinned;
  test con utenti e template sintetici.
- **RISCHIO:** alto per privacy, autorizzazioni e cancellazione dati; nessun
  delete ampio o implicito.
- **HUMAN GATE:** necessario per accesso a materiale protetto e, più avanti,
  per enrollment/cancellazione reale o prova multi-user sul target. Nessun gate
  per modello e fixture offline.
- **CRITERIO DI CHIUSURA:** lifecycle multi-user deterministico e fail-closed,
  zero segreti/template negli artefatti, rollback testato e nessun utente
  hard-coded nel percorso production.

### Phase C — packaging e integrazione host gestita

- **OBIETTIVO:** produrre package installabili e reversibili per driver/runtime,
  dipendenze, systemd/SELinux e configurazione PAM, senza edit manuale di file
  package-owned.
- **PERCHÉ SERVE:** `/usr/local` hash-pinned e la modifica diretta di
  `plasmalogin` dimostrano funzione, non manutenzione, upgrade safety o
  distribuzione.
- **PREREQUISITI:** Phase A chiusa; contratto utenti/dati della Phase B; scelta
  esplicita dei consumer supportati e del fallback password.
- **OUTPUT ATTESO:** sorgenti RPM/spec o formato equivalente; dipendenze OpenCV
  dichiarate; integrazione systemd/SELinux/PAM idempotente; install,
  upgrade/downgrade e uninstall transazionali; recovery documentata.
- **RISCHIO:** alto sullo stato host; un errore può impedire login o lasciare
  template/runtime incompatibili.
- **HUMAN GATE:** nessuno per build e installazione in rootfs/VM usa-e-getta;
  obbligatorio prima di installazione privilegiata o modifica PAM/systemd sul
  laptop reale.
- **CRITERIO DI CHIUSURA:** package reproducibile; install/upgrade/uninstall e
  rollback verdi in ambiente pulito; fallback password preservato; nessun file
  vendor modificato fuori dal package manager.

### Phase D — lifecycle, recovery e concorrenza

- **OBIETTIVO:** chiudere i soli boundary operativi non ancora provati:
  cancellazione in fasi diverse, quiescenza, suspend/resume, hotplug,
  crash/restart e richieste concorrenti dei consumer.
- **PERCHÉ SERVE:** open/action/close nominale e reboot sono provati, ma non
  coprono byte tardivi cross-generation, rimozione del device o interruzioni
  arbitrarie.
- **PREREQUISITI:** candidate package-managed della Phase C; matrice di stato e
  stop condition progettata offline; nessun comando recovery device-side non
  compreso.
- **OUTPUT ATTESO:** lifecycle contract; test fault-injection host-only;
  comportamento `POISONED`/recovery leggibile; matrice suspend/hotplug/concurrency
  ridotta ai casi che cambiano una decisione.
- **RISCHIO:** alto sul device e medio sull'host; evitare reset, clear-halt e
  retry impliciti non provati.
- **HUMAN GATE:** obbligatorio per ogni prova che raggiunge il sensore, sospende
  il laptop o scollega/riattiva il target. Prepararlo solo dopo closure offline
  e soltanto per una nuova ipotesi reale.
- **CRITERIO DI CHIUSURA:** ogni evento termina in recupero nominale oppure in
  failure bounded e diagnosticabile con fallback disponibile, zero loop/retry
  nascosti e cleanup definito.

### Phase E — qualificazione release, sicurezza e licenze

- **OBIETTIVO:** definire la qualità supportata e auditare l'intero artefatto di
  distribuzione, senza confondere un test funzionale con una stima FAR/FRR.
- **PERCHÉ SERVE:** i match/no-match provano correttezza del percorso, non tassi
  biometrici, robustezza generale o completezza dell'audit di supply chain.
- **PREREQUISITI:** package candidate e lifecycle chiusi; popolazione e criteri
  di accettazione definiti prima di raccogliere dati.
- **OUTPUT ATTESO:** threat/privacy review; SBOM/licenze/attribution; test
  matrix supportata; criteri di affidabilità e compatibilità; release candidate
  riproducibile e firmabile.
- **RISCHIO:** alto per privacy biometrica e rischio di overclaim statistico;
  medio per incompatibilità licenze/dipendenze.
- **HUMAN GATE:** necessario per raccolta biometrica reale, prove Windows
  comparative, variazioni hardware o qualunque decisione di licensing
  materiale. Analisi statica e fixture sintetiche restano offline.
- **CRITERIO DI CHIUSURA:** claim limitati ai dati; nessun dato biometrico o
  secret nel package; licenze soddisfatte; pass/fail release esplicito per
  piattaforme e versioni dichiarate.

### Phase F — documentazione, handoff e pubblicazione

- **OBIETTIVO:** rendere installazione, uso, recovery e limiti comprensibili e
  allineare manuale, README e superficie pubblica allo stato reale.
- **PERCHÉ SERVE:** il manuale privato è corrente, mentre il README pubblico è
  rimasto al vecchio stato “nessun driver”; la history privata non è sicura da
  pubblicare automaticamente.
- **PREREQUISITI:** artefatto e claim di release delle fasi precedenti.
- **OUTPUT ATTESO:** guida utente/amministratore; troubleshooting e recovery;
  documentazione sviluppatore; evidence matrix aggiornata; export pulito e
  auditato senza capture, firmware, secret o dati biometrici.
- **RISCHIO:** alto per disclosure accidentale; basso per codice runtime.
- **HUMAN GATE:** obbligatorio prima di modificare repository pubblico,
  pubblicare release o esporre materiale privato.
- **CRITERIO DI CHIUSURA:** documentazione coerente con il package verificato,
  export/content/history audit PASS e pubblicazione approvata esplicitamente
  dall'Utente.

## WHAT_NOT_TO_TEST_AGAIN

Non riaprire o ripetere per sola “maggiore confidenza”:

- D279: enrollment production fixed-eight e terminale corretto;
- D280: serializzazione FP3, close/open, deserialize e identify same-finger;
- D282: fprintd ENROLL/VERIFY, restart/storage, same-finger match,
  different-finger no-match e delete;
- D283: PAM dedicato → fprintd → VERIFY;
- D284: consumer `sudo` transiente;
- D285/D286: installazione single-user corrente, restart/reboot e `sudo` match;
- D287: PAM nell'identità della sessione utente attiva;
- D288: consumer KScreenLocker e propagazione `Unlocked`;
- D289: fingerprint → sblocco di una sessione KDE realmente bloccata;
- D290: fingerprint passwordless → login Plasma → nuova sessione Wayland.

Una regressione mirata è giustificata soltanto se cambia codice/configurazione
nel percorso rilevante, cambia materialmente la piattaforma supportata, emerge
un difetto riproducibile oppure l'Utente richiede esplicitamente una nuova
qualificazione. In quel caso si testa il delta più piccolo; non si ripete
l'intera storia D279–D290 e si applica sempre la serie bounded:

```text
MAX_PHYSICAL_ATTEMPTS=3
STOP_ON_FIRST_MATCH=true
NO_MATCH_1_CONTINUE=true
NO_MATCH_2_CONTINUE=true
NO_MATCH_3_TERMINAL=true
FOURTH_ATTEMPT_ALLOWED=false
HIDDEN_OR_UNBOUNDED_RETRY_ALLOWED=false
```

## Decisione corrente

Il piano non avvia la Phase A mentre D291 è aperto. Il precedente kit D291 è
`HISTORICAL_ONLY_DO_NOT_RERUN`; non è richiesta alcuna azione live immediata
dell'Utente. Il prossimo piano deve prima rendere osservabile la variabilità
B0/raster/descrittori con dati reali già disponibili o con una futura
strumentazione privacy-preserving motivata da una nuova ipotesi, quindi
proporre soltanto il delta production minimo.

```text
PM_DECISION=REPLAN
D290_CLOSED_SUCCESSFULLY=true
D291_CLOSURE=NOT_ALLOWED
D291_BIOMETRIC_STABILITY=OPEN
D291_OPERATOR_KIT=HISTORICAL_ONLY_DO_NOT_RERUN
NEW_LIVE_REQUIRED_NOW=false
PROJECT_NEXT_STEPS_PLAN_READY=true
NO_NEXT_PHASE_EXECUTION_STARTED=true
```
