<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 — stato complessivo e roadmap A→F approvata

Data review: 13 settembre 2026

Baseline D293/04: `development` a
`e01cd6454c46919f818423085f50331d9e30b6ff`, con Phase A chiusa.

Decisione PM: D292/03 chiude A5/Phase A sulla base della source-of-truth
canonica, della build/ABI e delle suite integrate; D291 resta l'evidenza live
target-proven. D293/01 completa offline B1, senza auto-approvare la review PM,
e porta il boundary a B2. D293/02 implementa offline il caso multi-finger
`VerifyStart(any)` e il solo handoff fprintd IDENTIFY→ENROLL sicuro. D293/03
attraversa il vero daemon fprintd con più nomi principal e fissa il contratto
statico del KCM Users Plasma 6.7.5. D293/04 rende pronto offline il relativo
experiment sul common harness; il successivo boundary è la sua operator-run
Human Gate, non ancora eseguita.

```text
USER_APPROVED_ROADMAP=true
APPROVAL_DATE=2026-09-13
CURRENT_PHASE=B
PHASE_ORDER=A>B>C>D>E>F
```

Target production iniziale approvato: Goodix USB `27c6:5125` / APP12509 su
Fedora KDE, attraverso lo stack standard `libfprint -> fprintd -> PAM/KDE`.
Altre distribuzioni, desktop, sensori, firmware/target e utenti
AD/LDAP/network restano fuori scope senza una nuova decisione esplicita
dell'Utente.

## Conclusione esecutiva

Il progetto ha superato il confine di fattibilità: sul target APP12509 sono
provati enrollment, template FP3, matching SIGFM, integrazione libfprint/fprintd
e i consumer reali `sudo`, KDE lock/unlock e Plasma Login Manager. D290 chiude
la catena fingerprint → nuova sessione Plasma/Wayland.

La sorgente production è ora consolidata; il divario immediato è il contratto
multi-user nativo KDE/fprintd e la separazione fra storage template e materiali
runtime protetti. Gestibilità, packaging, lifecycle e release restano nelle
fasi successive. Le fasi privilegiano lavoro offline e ambienti host isolati;
i boundary D279–D291 non vanno ripetuti per sola maggiore confidenza.

D292/01 ha chiuso l'inventario A1. D292/02 chiude A3/A4: `production/` è ora
l'unica autorità di composizione, ricostruisce il pristine Fedora 44/libfprint
1.94.100 e applica una patch production di 15 file più il subset locale
hashato. Il delta Git completo è 16 file (4 build/ABI, 11 core, 1 test-only
escluso dal prodotto). Le 39 API host/test-only sono protette da seam, le 12
shared/internal restano production; build normal e ASan/UBSan passano, due
build da cwd diverse sono byte-identiche e ABI fprintd/no-RPATH sono verificate.
Non restano dipendenze build da Dxxx o `tests/`. D292/03 chiude A5 e Phase A
dopo review PM diretta. D293/01 deriva dal codice il contratto multi-user e
materiali protetti e chiude B1 offline. D293/02 chiude B2 offline con IDENTIFY
su gallery completa, handoff ENROLL bounded e modello storage multi-principal.
D293/03 esaurisce i prerequisiti offline di B3/B4: due nomi principal, ma un
solo UID Unix, sul vero fprintd e storage temporaneo, più il contratto statico
del KCM KDE.

```text
D290_CLOSED_SUCCESSFULLY=true
D291_MULTI_VERIFY_TRANSPORT_LIVE=PROVEN
D291_BASELINE_PINNING=IMPLEMENTED_NOT_VALIDATED
D291_BIOMETRIC_STABILITY_GATE=PASS
D291_CLOSURE=PROVEN_ON_TARGET
D291_ROCKY_DIVERSITY_LIVE=PASS
D291_REGISTERED_SERIES_MATCHED=4/4
D291_NEW_LIVE_REQUIRED_NOW=false
D292_01_PRODUCTION_SOURCE_INVENTORY=PASS
PHASE_A_A1=COMPLETED
PHASE_A_A3=COMPLETED
PHASE_A_A4=COMPLETED
PHASE_A_A5=COMPLETED
PHASE_A_CLOSED=true
D292_02_SOURCE_OF_TRUTH_AND_REPRODUCIBLE_BUILD=PASS
D292_03_PHASE_A_CLOSURE=PASS
D293_01_OUTCOME=PASS_OFFLINE_CONTRACT
PHASE_B_B1=COMPLETED
PHASE_B_B2=COMPLETED_OFFLINE
D293_03_OUTCOME=PASS_HOST_ONLY
PHASE_B_B3_OFFLINE_PREREQUISITES=COMPLETED
KDE_KCM_STATIC_CONTRACT=PASS
PHASE_B_B4_OFFLINE_PREREQUISITES=COMPLETED
D293_04_OPERATOR_KIT=READY_OFFLINE
D293_04_LIVE_EXECUTION=HUMAN_REQUIRED_NOT_PERFORMED
PHASE_B_CLOSED=false
PROJECT_FEASIBILITY=PROVEN_ON_TARGET_APP12509
PRODUCTION_READY=false
NEXT_WORK_CLASS=INTEGRATION_PACKAGING_LIFECYCLE_RELEASE
NEXT_BOUNDARY=D293_04_OPERATOR_RUN_HUMAN_GATE
```

## Stato verificato del progetto

### Definitivamente PROVEN nello scope osservato

- Protocollo target e acquisizione: USB A0/B0, secure session TLS 1.2 PSK,
  configurazione volatile usata, FDT, record immagine, decode `80x64`, release
  tail e lifecycle nominale hanno attraversato il sensore reale senza retry di
  transport e senza famiglie di scrittura persistente note.
- Enrollment e template: enrollment SIGFM production a otto campioni; FP3
  serializzato, riletto dopo close/open e usato per identify/verify; storage,
  restart, list e delete fprintd sono stati attraversati. La policy diversity
  Rocky-derived ha inoltre prodotto live un nuovo template da otto contatti
  distinti, poi validato con dito errato e quattro serie registrate.
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

- D291 è chiuso funzionalmente: multi-VERIFY, max tre tentativi, stop al MATCH,
  assenza di retry nascosti e stabilità del nuovo template nel gate a quattro
  serie sono provati. Il pinning baseline resta implementato ma non isolato
  causalmente; questa attribuzione non è necessaria alla closure.
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

## Roadmap approvata dall'Utente

L'ordine A→B→C→D→E→F è vincolante: prima si definisce e consolida ciò che verrà
distribuito; poi il driver viene chiuso come multi-user e nativo KDE/fprintd;
soltanto dopo iniziano packaging e integrazione host, quindi i boundary
lifecycle realmente nuovi. AI PM può fare corrective e replan locali dentro la
fase corrente, ma non saltare o invertire fasi né ampliare il target senza una
nuova decisione esplicita dell'Utente.

### Phase A — consolidamento della sorgente production — CLOSED

- **OBIETTIVO:** scegliere una sola baseline libfprint mantenibile e trasformare
  i delta target-proven in una patch series/build production riproducibile,
  classificando senza ambiguità production, test, reference, evidenza,
  storico/deprecato, tooling sviluppatore e documentazione.
- **PERCHÉ SERVIVA:** all'ingresso della fase la funzione era provata, ma la
  sorgente autorevole era distribuita fra `libfprint-driver/`, fork Fedora e
  componenti SIGFM/R2 con licenze diverse.
- **PREREQUISITI:** evidenze D279–D291, `Rockytkg/PROVENANCE.md`, ledger
  `docs/LICENSING_AND_PROVENANCE.md`, versioni Fedora attualmente pin-nate.
- **OUTPUT ATTESO:** architecture decision record; inventario source-of-truth;
  patch series o tree integrato; build normal e sanitizer riproducibile;
  profilo production senza seam/test override raggiungibili; percorso dichiarato
  `sorgente production -> build -> libfprint -> fprintd`, indipendente da
  operator kit storici, launcher one-shot, fake backend e struttura Dxxx.
- **REGOLA STORICO/RED TAG:** nessun materiale storico o deprecato viene
  cancellato. Un eventuale spostamento nell'archivio privato `red tag/` è
  ammesso soltanto dopo audit di import, build, test, script, riferimenti
  documentali, provenance, licensing e dipendenze production; ciò che è ancora
  referenziato va prima disaccoppiato correttamente. Lo spostamento non è
  obbligatorio e `red tag/` non è un cestino.

```text
DELETE_HISTORICAL_MATERIAL=false
RED_TAG_ARCHIVE_ALLOWED=true
MOVE_ONLY_AFTER_REFERENCE_AUDIT=true
```

- **RISCHIO:** medio; regressioni ABI/lifecycle e scelta del regime GPL-compatible.
- **HUMAN GATE:** nessuno per audit, build e test offline. È richiesta decisione
  dell'Utente prima di un cambio materiale del licensing boundary o della
  strategia di distribuzione.
- **CRITERIO DI CHIUSURA:** sono documentati sorgente production, file che
  costruiscono il driver, classificazione test/reference/storico, componenti
  realmente distribuiti e relativa provenance/licenza; clean build dalla sola
  sorgente dichiarata, ABI fprintd, suite production e compatibilità col target
  reale sono verificati e riproducibili.

### Phase B — driver multi-user e workflow Linux/KDE nativo — CURRENT

- **OBIETTIVO:** fare sì che ogni normale utente locale, presente o creato dopo
  l'installazione, possa registrare e gestire autonomamente le proprie impronte
  nel workflow standard KDE Plasma / Impostazioni di sistema → Utenti e fprintd,
  senza script Goodix, username/path hard-coded o configurazione user-specific.
- **PRINCIPIO:** Goodix implementa il dispositivo; fprintd gestisce utenti,
  ownership e template nel proprio storage standard. Nessun database parallelo
  Goodix salvo blocker tecnico concreto e riesame della strategia. Operator kit
  e terminale restano strumenti developer/diagnostici, non UX finale; nessuna
  GUI Goodix custom senza blocker dimostrato e nuova decisione dell'Utente.
- **PERCHÉ SERVE:** il percorso corrente prova un utente e un FP3, ma non
  definisce comportamento per utenti multipli o creati dopo l'installazione,
  re-enrollment, delete, template drift o macchina nuova.
- **PREREQUISITI:** source-of-truth Phase A; policy esplicita su origine,
  installazione e protezione dei materiali PE/FDT/PSK senza pubblicarli.
- **OUTPUT ATTESO:** contratto zero/uno/più template e più dita secondo le
  capacità standard; primo enrollment, re-enrollment, delete singolo/completo,
  comportamento alla cancellazione dell'utente, isolamento fra utenti, restart
  fprintd, logout/login e reboot; policy lecita per materiali runtime protetti,
  separata dal lifecycle dei template biometrici, che ne definisca necessità,
  origine/provenance, natura per-device, permessi, ownership e provisioning su
  una macchina nuova senza secret in repository, package, log o artefatti.
- **SCENARIO OBBLIGATORIO:** driver già installato; creazione di un nuovo utente
  locale; nessuna reinstallazione o modifica del driver; enrollment dalla UI
  KDE standard; template nuovo salvato da fprintd senza contaminare quelli
  preesistenti. AD/LDAP/network users restano fuori scope.
- **RISCHIO:** alto per privacy, autorizzazioni e cancellazione dati; nessun
  delete ampio o implicito.
- **HUMAN GATE:** necessario per accesso a materiale protetto e, più avanti,
  per enrollment/cancellazione reale o prova multi-user sul target. Nessun gate
  per modello e fixture offline.
- **CRITERIO DI CHIUSURA:** installato il driver, qualsiasi normale utente
  locale presente o creato successivamente può registrare e gestire le proprie
  impronte tramite il normale workflow KDE/fprintd, senza script Goodix o
  configurazioni user-specific; lifecycle multi-user deterministico,
  isolamento/ownership corretti e zero segreti/template negli artefatti.

D293/01 chiude B1 offline. Il contratto standard usa il nome utente risolto
dal sender D-Bus e il layout fprintd
`<state>/<username>/<driver>/<device-id>/<finger>`; il nuovo utente locale non
richiede configurazione driver e crea lo storage al primo enrollment. Rename e
delete OS non gestiscono però i template perché la chiave è il nome, non l'UID,
e il name reuse può ereditare dati stale. Con il driver corrente
`goodix_27c6_5125/0`, più dita sono archiviabili. D293/02 supera il precedente
limite `VerifyStart(any)`: la policy `GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE`
annuncia IDENTIFY e un callback core interno arma soltanto il passaggio
clean/no-match a ENROLL. Il driver rilascia e riacquisisce claim, materiale e
sessione; match, errore, cancellazione e action diverse non abilitano il
passaggio. Il modello content-free copre due principal, più dita, restart,
replace, delete e name reuse; l'hook account-delete resta integrazione host.

D293/03 esercita il vero daemon Fedora su bus privato: due nomi principal
autorizzati via `setusername`, tre template sintetici, restart/list,
`VerifyStart(any)`, isolamento, replace e delete singolo/completo sono PASS.
Il sender/UID Unix resta uno, quindi non è una prova multi-account. L'audit
hash-pinned del KCM Users Plasma 6.7.5 conferma discovery, list, enroll/
re-enroll e delete tramite le API fprintd standard, senza UI Goodix; il KCM
non è stato avviato.

D293/04 riusa il common harness invariato per il primo discriminante live
B3/B4: deployment transiente della build production corrente, account creato
dal KCM dopo il deploy, vera sessione Plasma/Wayland del nuovo UID, una
impronta enroll/delete solo da KCM e `VerifyStart(any)` bounded a tre. Gli
audit impongono IDENTIFY + ENROLL a otto stage/fino a venti contatti + fino a
tre VERIFY (`MAX_ACTIONS=5`, `MAX_CONTACTS=24`, retry transport zero). Il
principal preesistente è confrontato internamente su contenuto e metadata; il
supervisore rende READY soltanto dopo aver fermato fprintd. Il kit è pronto
offline, ma live/USB/pkexec non sono stati eseguiti dall'AI.

I cinque input runtime sono un prerequisito di sistema unico, root-only e
target-pinned, separato da utenti e FP3. Il package non può contenerli; origine
lecita, provisioning amministrativo no-overwrite e compatibilità con una
macchina/unità diversa restano requisiti. L'unicità effettiva per device/lotti
è `UNKNOWN` e l'accesso autentico resta Human Gate.

La Phase B deve essere chiusa prima di iniziare la Phase C.

### Phase C — packaging e integrazione host gestita

- **OBIETTIVO:** produrre package installabili e reversibili per driver/runtime,
  dipendenze, systemd/SELinux e configurazione PAM, senza edit manuale di file
  package-owned.
- **PERCHÉ SERVE:** `/usr/local` hash-pinned e la modifica diretta di
  `plasmalogin` dimostrano funzione, non manutenzione, upgrade safety o
  distribuzione.
- **PREREQUISITI:** Phase A e Phase B chiuse; contratto utenti/dati multi-user
  nativo KDE/fprintd provato; scelta esplicita dei consumer supportati e del
  fallback password.
- **OUTPUT ATTESO:** sorgenti RPM/spec o formato equivalente; dipendenze OpenCV
  dichiarate; integrazione systemd/SELinux/PAM idempotente e reversibile per
  `sudo`, KScreenLocker, Plasma Login Manager e Polkit quando pertinente;
  install, upgrade/downgrade e uninstall transazionali; recovery documentata;
  verifica che aggiornamenti Fedora rilevanti non rompano configurazione,
  fallback password o template senza diagnosi/recovery.
- **RISCHIO:** alto sullo stato host; un errore può impedire login o lasciare
  template/runtime incompatibili.
- **HUMAN GATE:** nessuno per build e installazione in rootfs/VM usa-e-getta;
  obbligatorio prima di installazione privilegiata o modifica PAM/systemd sul
  laptop reale.
- **CRITERIO DI CHIUSURA:** package riproducibile; install, upgrade, downgrade
  quando supportato, uninstall, rollback e recovery verdi in ambiente pulito;
  fallback password preservato; nessun file vendor modificato manualmente fuori
  dal package manager.

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
  piattaforme e versioni dichiarate. I claim iniziali coprono soltanto Fedora
  KDE + Goodix `27c6:5125`/APP12509; altri sistemi, desktop, sensori e firmware
  restano non rivendicati.

### Phase F — documentazione, handoff e pubblicazione

- **OBIETTIVO:** rendere installazione, uso, recovery e limiti comprensibili e
  allineare manuale, README e superficie pubblica allo stato reale.
- **PERCHÉ SERVE:** il manuale privato è corrente, mentre il README pubblico è
  rimasto al vecchio stato “nessun driver”; la history privata non è sicura da
  pubblicare automaticamente.
- **PREREQUISITI:** artefatto e claim di release delle fasi precedenti.
- **OUTPUT ATTESO:** guide di installazione, uso, gestione impronte KDE,
  amministrazione, troubleshooting e recovery; documentazione sviluppatore,
  architettura, limiti noti, README, evidence matrix, audit privacy/secret,
  licensing/attribution e ringraziamenti; export pulito e auditato senza
  capture, firmware, secret o dati biometrici.
- **RISCHIO:** alto per disclosure accidentale; basso per codice runtime.
- **HUMAN GATE:** obbligatorio prima di modificare repository pubblico,
  pubblicare release o esporre materiale privato.
- **CRITERIO DI CHIUSURA:** documentazione coerente con il package verificato,
  export/content/history audit PASS e pubblicazione approvata esplicitamente
  dall'Utente. L'eventuale inclusione di `red tag/` nell'export pubblico è una
  decisione separata della Phase F dopo audit.

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
- D291: enrollment diversity Rocky-derived, discriminazione wrong-finger e
  quattro serie registrate concluse con MATCH.

Una regressione mirata è giustificata soltanto se cambia codice/configurazione
nel percorso rilevante, cambia materialmente la piattaforma supportata, emerge
un difetto riproducibile oppure l'Utente richiede esplicitamente una nuova
qualificazione. In quel caso si testa il delta più piccolo; non si ripete
l'intera storia D279–D291 e si applica sempre la serie bounded:

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

La Phase B è ora il boundary corrente. Il kit D291 è
`HISTORICAL_CLOSED_DO_NOT_RERUN` e non deve essere riusato. D292/01 ha chiuso
A1, D292/02 ha chiuso A3/A4 e la review PM
D292/03 ha chiuso A5/Phase A. D293/01 chiude B1 offline con contratto e
validator statico, senza accesso ai secret. D293/02 chiude B2 offline con
implementazione e test. D293/03 esaurisce i prerequisiti offline di B3/B4 e
il contratto statico KDE installato. Il prossimo boundary richiede il vero scenario KDE con un nuovo
utente locale ed è soggetto a Human Gate.

```text
PM_DECISION=ACCEPT_AND_CONTINUE
D290_CLOSED_SUCCESSFULLY=true
D291_CLOSURE=PROVEN_ON_TARGET
D291_BIOMETRIC_STABILITY_GATE=PASS
D291_OPERATOR_KIT=HISTORICAL_CLOSED_DO_NOT_RERUN
D292_01_PRODUCTION_SOURCE_INVENTORY=PASS
PHASE_A_A1=COMPLETED
PHASE_A_A3=COMPLETED
PHASE_A_A4=COMPLETED
PHASE_A_A5=COMPLETED
PHASE_A_CLOSED=true
D292_02_SOURCE_OF_TRUTH_AND_REPRODUCIBLE_BUILD=PASS
D292_03_PHASE_A_CLOSURE=PASS
D293_01_OUTCOME=PASS_OFFLINE_CONTRACT
PHASE_B_B1=COMPLETED
PHASE_B_B2=COMPLETED_OFFLINE
D293_03_OUTCOME=PASS_HOST_ONLY
PHASE_B_B3_OFFLINE_PREREQUISITES=COMPLETED
KDE_KCM_STATIC_CONTRACT=PASS
PHASE_B_B4_OFFLINE_PREREQUISITES=COMPLETED
D293_04_OPERATOR_KIT=READY_OFFLINE
D293_04_LIVE_EXECUTION=HUMAN_REQUIRED_NOT_PERFORMED
PHASE_B_CLOSED=false
NEW_LIVE_REQUIRED_NOW=true
PROJECT_NEXT_STEPS_PLAN_READY=true
CURRENT_PHASE=B
PRODUCTION_READY=false
NEXT_BOUNDARY=D293_04_OPERATOR_RUN_HUMAN_GATE
```
