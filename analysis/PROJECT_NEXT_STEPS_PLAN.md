<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 — stato complessivo e roadmap A→F approvata

Data review: 14 settembre 2026

Baseline di ingresso del corrective metodologico patch-first: `development` a
`5db8a868fb539254a481edea4c1443d15dfebb6e`, con Phase A chiusa e il
precedente corrective D293/04 concluso offline ma mai eseguito live. Il 13
settembre 2026 la successiva patch-first D293 è stata eseguita manualmente
dall'Utente sul target reale e ha dato PASS nel workflow KDE nativo.

Decisione PM: D292/03 chiude A5/Phase A sulla base della source-of-truth
canonica, della build/ABI e delle suite integrate; D291 resta evidenza live
target-proven precedente e D293 aggiunge il workflow KDE multi-user nativo.
D293/01 completa offline B1, senza auto-approvare la review PM,
e porta il boundary a B2. D293/02 implementa offline il caso multi-finger
`VerifyStart(any)`, l'handoff fprintd IDENTIFY→ENROLL sicuro e, col corrective
R9, le IDENTIFY esplicite ripetute nello stesso open. D293/03
attraversa il vero daemon fprintd con più nomi principal e fissa il contratto
statico del KCM Users Plasma 6.7.5. La decisione Utente R7 del 13 settembre
2026 resta evidenza storica valida per il protocollo GUI nativo, ma una
successiva decisione esplicita dello stesso giorno supera il complesso kit
D293/04 come metodo corrente. Il nuovo boundary è
`PATCH_FIRST_LIVE_VALIDATION`: installazione minimale della corrente production
candidate, rollback simmetrico, README completo e osservazione manuale del
workflow KDE reale dopo il Human Gate. Quel boundary è ora PASS. Il MATCH è
stato osservato, ma il numero esatto del tentativo non è stato riportato. Il
rollback eseguito dopo il PASS seguiva un'istruzione poi superata e non è un
rigetto della candidate. La candidate è stata quindi reinstallata: runtime,
wrapper e drop-in D293 allo SHA `e61fce313794922a2dab156a1b38a8ddc5837f19`
sono osservabili read-only; D293 è la baseline software configurata e D285 il
predecessore di rollback. Il riesame dei lifecycle residui ha individuato come
ultimo gap Phase B la relazione fra template e account deletion/name reuse.
D293/05 implementa una guard host-only `userdel` e una singola live patch-first
che copre anche multi-finger, re-enroll, delete, logout/login e reboot; la
review PM della candidate era `ACCEPT_AND_CONTINUE`. Dopo i failure host
intermedi e i correttivi manuali autorizzati registrati nella lineage Git, la
live finale sul target Fedora 44 KDE è PASS pieno: blocco con print, pass senza
print, name reuse, SELinux Enforcing senza alert e principal Guido invariato
sono provati. Guard e modulo restano installati. La review evidence-based
chiude Phase B e porta il boundary a Phase C.

```text
USER_APPROVED_ROADMAP=true
APPROVAL_DATE=2026-09-13
CURRENT_PHASE=C_CLOSED
PHASE_ORDER=A>B>C>D>E>F
PHASE_C_CLOSED=true
NEXT_PHASE=D
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

La sorgente production e il contratto multi-user sono consolidati. Phase C ha
ora provato su Fedora 44 KDE il percorso source-first gestito completo: build,
import separato, install/idempotenza, update, PAM e consumer, rollback
bidirezionale, uninstall, preservazione dati e recovery/reinstall. La baseline
finale della VM è `448f5c8...`; il PAM vendor resta invariato. I due lifecycle
operativi residui della Phase D — suspend/resume e cancellation/recovery — e
la qualificazione release appartengono alle fasi successive, che non vengono
avviate in questa sessione. I boundary D279–D295 chiusi non vanno ripetuti per
sola maggiore confidenza.

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
del KCM KDE. D293 ha poi prodotto il PASS target del workflow nativo minimo.
D293/05 chiude il gap account deletion/name reuse con una guard fail-closed che
non chiama fprintd e non accede al sensore. La lineage conserva separatamente
il primo AVC, i failure installer/checksum e l'AVC accessorio TCGETS2. La
candidate finale con `allowxperm` ristretto a `0x542a` è PASS sul target sotto
SELinux Enforcing senza alert; guard e modulo restano installati. Phase B è
formalmente chiusa e il lavoro corrente passa al packaging Phase C.

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
R9_SAME_OPEN_IDENTIFY=CONFIRMED_AND_CORRECTED
D293_03_OUTCOME=PASS_HOST_ONLY
PHASE_B_B3_OFFLINE_PREREQUISITES=COMPLETED
KDE_KCM_STATIC_CONTRACT=PASS
PHASE_B_B4_OFFLINE_PREREQUISITES=COMPLETED
D293_04_HISTORICAL_RESULT=READY_OFFLINE_NOT_EXECUTED
D293_04_COMPLEX_KIT=SUPERSEDED_BY_METHOD_DECISION
TEST_METHOD=PATCH_FIRST_LIVE_VALIDATION
OPERATOR_KIT_DEFAULT=false
D293_INSTALL_PATCH=READY
D293_ROLLBACK_PATCH=READY
D293_LIVE_INSTRUCTIONS=READY
D293_TEST_PURPOSE_DOCUMENTED=true
D293_PASS_FAIL_STOP_CRITERIA=READY
D293_ROLLBACK_INSTRUCTIONS=READY
D293_INSTALLS_OPERATOR_KIT=false
D293_INSTALLS_CURRENT_PRODUCTION_CANDIDATE=true
D293_04_LIVE_EXECUTION=NOT_PERFORMED
D293_NATIVE_KDE_LIVE=PASS
D293_NATIVE_INSTALL=PASS
D293_NEW_LOCAL_USER_READER_VISIBLE=true
D293_NATIVE_KDE_ENROLL=PASS
D293_NATIVE_VERIFY=MATCH
D293_NATIVE_VERIFY_ATTEMPT=NOT_REPORTED
D293_NATIVE_KDE_DELETE=PASS
D293_PREEXISTING_PRINCIPAL_UNCHANGED=true
D293_NATIVE_ROLLBACK=PASS
D293_TEST_ACCOUNT=d239live0913
D293_TARGET_EVIDENCE=HUMAN_OBSERVED_ON_REAL_FEDORA_KDE_TARGET
D293_VALIDATED_FEATURE=ACTIVE_BASELINE
D293_ACTIVE_BASELINE_SHA=e61fce313794922a2dab156a1b38a8ddc5837f19
D285=ROLLBACK_PREDECESSOR
ROLLBACK_PATCH_REQUIRED=true
ROLLBACK_ON_FAIL=true
ROLLBACK_ON_PASS=false
KEEP_VALIDATED_ADVANCEMENT_BY_DEFAULT=true
LIVE_EXECUTED_BY_AI=false
PHASE_B_CLOSED=true
PROJECT_FEASIBILITY=PROVEN_ON_TARGET_APP12509
PRODUCTION_READY=false
PHASE_B_CLOSURE_REVIEW=PASS_ALL_REQUIRED_CRITERIA
D293_05_FIRST_INSTALL=PASS
D293_05_FIRST_LIVE=FAIL
D293_05_FAILURE_CLASS=HOST_SELINUX_EXECUTION_POLICY
D293_05_FAILURE_POINT=USERDEL_PRE_HOOK_EXEC
D293_05_DRIVER_REGRESSION=false
D293_05_SENSOR_FAILURE=false
D293_05_ROLLBACK=PASS
D293_05_ACCOUNT_DELETE_AFTER_ROLLBACK=PASS
D293_05_SELINUX_CORRECTIVE=PASS_ON_TARGET
D293_05_CORRECTIVE_LIVE=PASS
D293_05_OUTCOME=PASS_FULL_ON_TARGET
D293_B5_SELINUX_ENFORCING=PASS
D293_B5_SELINUX_ALERTS=0
D293_B5_PATCH_LEFT_INSTALLED=true
FINGERPRINT_LOGIN=PASS
PASSWORD_LOGIN_NON_ENROLLED_USERS=PASS_NO_DELAY
PASSWORD_FALLBACK_ENROLLED_USERS=PASS_WITH_APPROX_30S_DELAY
PAM_ENROLLED_PASSWORD_DELAY_SEVERITY=ACCEPTED_UX_LIMITATION
PHASE_B_BLOCKER=false
NEXT_WORK_CLASS=PHASE_D_NOT_STARTED
PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL
RPM_OFFICIAL_DISTRIBUTION=false
D294_RPM_ROLE=HISTORICAL_PROTOTYPE_AND_EVIDENCE
CURRENT_TASK=NONE_PHASE_C_CLOSED
NEXT_BOUNDARY=USER_INITIATED_PHASE_D_DECISION
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
- D293 patch-first sul target: un nuovo utente locale creato dopo
  l'installazione vede il reader, completa enrollment, VERIFY con MATCH e
  delete nel workflow KDE/fprintd nativo; il principal preesistente resta
  invariato per osservazione dell'Utente. Il tentativo MATCH non è riportato.

### IMPLEMENTED, ma non production-ready

- D291 è chiuso funzionalmente: multi-VERIFY, max tre tentativi, stop al MATCH,
  assenza di retry nascosti e stabilità del nuovo template nel gate a quattro
  serie sono provati. Il pinning baseline resta implementato ma non isolato
  causalmente; questa attribuzione non è necessaria alla closure.
- Driver e integrazione SIGFM funzionano nella fork Fedora preservata; Phase A
  ha consolidato il delta come patch production rigenerabile e source-of-truth
  mantenibile. Restano da trasformare in package Fedora gestito nella Phase C.
- L'installazione D285 sotto `/usr/local` resta il predecessore di rollback.
  La baseline software configurata D293 è ancora single-host e legata a
  SHA/versioni esatte: è recuperabile ma non è un package di distribuzione.
- D295/02 ha sostituito la modifica PAM manuale con l'override amministrativo
  gestito `/etc/pam.d/plasmalogin`, derivato dal vendor verificato e provato
  live per password, fingerprint Plasma e `sudo`. Resta da attraversare sul
  sistema reale il solo lifecycle rollback/uninstall/recovery.
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

- mancano package, install/upgrade/uninstall transazionali e una policy per
  dipendenze OpenCV, systemd, SELinux e PAM;
- restano lifecycle amministrativo account deletion/name reuse e provisioning
  lecito dei materiali runtime protetti su una macchina nuova;
- restano da chiudere i due boundary Phase D esplicitamente approvati:
  suspend/resume e cancellation/recovery di un'action; hotplug, device removal,
  concorrenza e gli altri fault scenario non sono requisiti dedicati salvo un
  boundary reale nel codice o un bug osservato;
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
  cancellato. Prima della pubblicazione Phase F un audit completo deve
  disaccoppiare ciò che è ancora referenziato, spostare tutto il materiale non
  pubblico nell'archivio privato `red_tag/`, aggiungerlo a `.gitignore` e
  provare che build, test e release non ne dipendono. Non anticipare lo
  spostamento nelle fasi A–E; `red_tag/` non è un cestino.

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

### Phase B — driver multi-user e workflow Linux/KDE nativo — CLOSED

- **OBIETTIVO:** fare sì che ogni normale utente locale, presente o creato dopo
  l'installazione, possa registrare e gestire autonomamente le proprie impronte
  nel workflow standard KDE Plasma / Impostazioni di sistema → Utenti e fprintd,
  senza script Goodix, username/path hard-coded o configurazione user-specific.
- **PRINCIPIO:** Goodix implementa il dispositivo; fprintd gestisce utenti,
  ownership e template nel proprio storage standard. Nessun database parallelo
  Goodix salvo blocker tecnico concreto e riesame della strategia. Operator kit
  e terminale restano strumenti developer/diagnostici, non UX finale; nessuna
  GUI Goodix custom senza blocker dimostrato e nuova decisione dell'Utente.
- **PERCHÉ SERVE:** D293 prova ora il nuovo utente creato dopo l'installazione
  nel workflow KDE reale, ma non chiude da solo account deletion/name reuse,
  tutti i lifecycle richiesti o il provisioning su macchina nuova.
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
sessione. Il corrective R9 consente inoltre una nuova IDENTIFY esplicita dopo
un outcome host pulito nello stesso claim/open, necessario alla normale serie
PAM con gallery multi-dito; match/no-match puliti restano distinti da processing
retry, errore, cancellazione, non-drain e poison, che non riaprono risorse. Il
modello content-free copre due principal, più dita, restart, replace, delete e
name reuse; l'hook account-delete resta integrazione host.

D293/03 esercita il vero daemon Fedora su bus privato: due nomi principal
autorizzati via `setusername`, tre template sintetici, restart/list,
`VerifyStart(any)`, isolamento, replace e delete singolo/completo sono PASS.
Il sender/UID Unix resta uno, quindi non è una prova multi-account. L'audit
hash-pinned del KCM Users Plasma 6.7.5 conferma discovery, list, enroll/
re-enroll e delete tramite le API fprintd standard, senza UI Goodix; il KCM
non è stato avviato.

D293/04 conserva come storia il common harness, la decisione R7, i fence della
singola action, la serie VERIFY massima di tre tentativi e i correttivi F1–F4.
Il risultato offline resta valido nel proprio scope, ma il kit non è mai stato
eseguito live ed è ora `SUPERSEDED_BY_METHOD_DECISION`: non va raffinato,
adattato, installato o usato come metodo corrente. La validazione attuale usa
`deployment/d293-native-kde-live/`: installa la corrente production candidate
D293 con una patch minimale e reversibile, conserva D285 intatta e dispone di
rollback simmetrico e README completo; install/rollback sintetici sono 7/7
PASS, inclusa la preservazione dei metadati parent, e la build production
offline è PASS. La live patch-first successiva è PASS: il nuovo account locale
ha visto il reader, enrollment/verify MATCH/delete nativi sono riusciti e il
principal preesistente è rimasto invariato secondo osservazione dell'Utente.
Il tentativo esatto del MATCH non è noto. Questo chiude lo scenario
discriminante, ma non prova da solo tutti i lifecycle richiesti dalla closure
Phase B; account deletion/name reuse e gli altri casi non attraversati restano
da riesaminare contro le evidenze già esistenti.

I cinque input runtime sono un prerequisito di sistema unico, root-only e
target-pinned, separato da utenti e FP3. Il package non può contenerli; origine
lecita, provisioning amministrativo no-overwrite e compatibilità con una
macchina/unità diversa restano requisiti. L'unicità effettiva per device/lotti
è `UNKNOWN` e l'accesso autentico resta Human Gate.

#### Review formale di closure Phase B

| Criterio | Classificazione | Base probatoria |
|---|---|---|
| nuovo utente locale, reader ed enrollment KDE nativo | `PROVEN_ON_TARGET` | D293 patch-first |
| zero/uno/più template, multi-finger, re-enroll e delete | `PROVEN_ON_TARGET` | D291, prima run D293/05 e D293/02–03 offline |
| isolamento multi-principal e ownership/storage fprintd | `PROVEN_ON_TARGET` | Guido invariato, nuovo account e name reuse pulito |
| restart fprintd, logout/login e reboot | `PROVEN_ON_TARGET` | prima run D293/05 |
| account deletion/name reuse sotto SELinux Enforcing | `PROVEN_ON_TARGET` | live finale D293/05 |
| policy per materiali runtime separata dai template | `DOCUMENTED_POLICY` | D293/01; provisioning gestito ricade in Phase C |
| assenza di secret/template negli artefatti | `PROVEN_OFFLINE` | validator e review set Git-native |
| delay password fallback per utenti enrolled | `DOCUMENTED_POLICY` | limite UX accettato, non blocker |

Tutti i criteri obbligatori della fase sono soddisfatti nel rispettivo livello
di prova richiesto. Packaging, provisioning amministrativo dei materiali e
gestione package-owned di PAM/systemd/SELinux appartengono esplicitamente alla
Phase C e non vengono promossi retroattivamente a prove Phase B.

```text
PHASE_B_CLOSED=true
NEXT_PHASE=C
NEXT_WORK_CLASS=SOURCE_FIRST_MANAGED_HOST_INTEGRATION
```

### Phase C — distribuzione source-first e integrazione host gestita — CLOSED

- **DECISIONE ARCHITETTURALE:** il percorso ufficiale è clone del repository →
  build da `production/` → installer gestito → stack Fedora. L'RPM D294 resta
  prototipo storico/evidenza e non è una distribuzione ufficiale.
- **OBIETTIVO:** rendere build e installazione da sorgente idempotenti,
  diagnosticabili e reversibili, con runtime immutabile per commit, dipendenze
  esplicite, systemd/SELinux, guard account-lifecycle, update, rollback,
  uninstall e recovery; l'override PAM amministrativo resta derivato dal vendor
  verificato e fail-closed rispetto a drift Fedora.
- **PERCHÉ SERVE:** `/usr/local` hash-pinned, la modifica diretta di
  `plasmalogin` e l'overlay RPM dipendente da D293 dimostrano funzione, non una
  installazione clean-room autonoma.
- **PREREQUISITI:** Phase A e Phase B chiuse; contratto utenti/dati multi-user
  nativo KDE/fprintd provato; scelta esplicita dei consumer supportati e del
  fallback password.
- **OUTPUT ATTESO:** gestore source-first e manifest di provenance; dipendenze
  OpenCV hash-pinned; integrazione systemd/SELinux idempotente e reversibile;
  materiali protetti importati separatamente e mai nel repository; install,
  update, rollback e uninstall con state verificabile; guida Phase C dedicata;
  verifica clean-room di PAM/KDE, fallback password e aggiornamenti Fedora.
- **RISCHIO:** alto sullo stato host; un errore può impedire login o lasciare
  template/runtime incompatibili.
- **HUMAN GATE:** nessuno per build e simulazioni su filesystem temporaneo;
  obbligatorio prima di qualunque `sudo`, import di materiale protetto, modifica
  systemd/SELinux/PAM o accesso al sensore, anche nella VM.
- **CRITERIO DI CHIUSURA:** candidate source-first riproducibile; install,
  update, rollback, uninstall e recovery verdi in Fedora 44 KDE pulita;
  fallback password preservato; nessun file vendor modificato manualmente fuori
  dal package manager.

**Closure:** PASS. D295/01 ha provato build, candidate, import, installazione e
idempotenza; D295/02 update, PAM gestito, password, login Plasma e `sudo`;
D295/03 rollback bidirezionale, uninstall, preservazione di materiali/template
e recovery/reinstall. La baseline finale nella VM è `448f5c8...`, con runtime
root `0755` e PAM vendor Fedora invariato.

### Phase D — lifecycle e recovery operativa minima

- **DECISIONE DI SCOPE (14 settembre 2026):** la fase prosegue esclusivamente
  con suspend/resume e cancellation/recovery. Non è una campagna generale di
  fault injection né una ricerca preventiva di casistiche esotiche.
- **OBIETTIVO:** verificare soltanto i due boundary operativi realistici che
  possono lasciare il sensore o il driver inutilizzabili nell'uso quotidiano:
  1. suspend/resume;
  2. cancellazione di un'action con successivo recovery/riutilizzo.
- **SUSPEND/RESUME:** dopo sospensione e riattivazione del sistema il sensore
  deve tornare utilizzabile attraverso il normale stack
  `libfprint -> fprintd -> PAM/KDE`. Un'action in corso può fallire o essere
  annullata; il requisito è convergere in stato pulito e consentire una nuova
  action.
- **CANCELLATION/RECOVERY:** una action cancellata deve terminare con cleanup
  definito, ritorno a uno stato riutilizzabile e possibilità di avviare la
  successiva senza reboot o workaround Goodix-specifici. Testare soltanto i
  punti realmente significativi del ciclo se il codice converge sullo stesso
  percorso di cleanup.
- **FUORI SCOPE SALVO EVIDENZA CONCRETA:** hotplug; device removal durante
  action; crash di componenti esterni come fprintd oltre ai normali restart già
  coperti; richieste concorrenti; consumer simultanei; late bytes/
  cross-generation; introduzione preventiva di uno stato `POISONED` o di
  meccanismi speciali di recovery. Questi casi vengono riaperti soltanto se il
  codice espone concretamente il relativo boundary o se un bug osservato ne
  dimostra la rilevanza. Una eventuale scomparsa/riapparizione logica del device
  causata dal power management viene trattata dentro suspend/resume, non come
  campagna hotplug separata.
- **PREREQUISITI:** Phase C chiusa; prima progettazione e test host-only quando
  sufficienti; nessun comando recovery device-side non compreso.
- **OUTPUT ATTESO:** contratto minimo di suspend/resume e cancellation/cleanup;
  test host-only mirati dove bastano; live sul sensore reale soltanto quando
  necessarie a chiudere uno dei due boundary.
- **RISCHIO:** medio; evitare reset, clear-halt, retry impliciti o nuove
  primitive device-side non provate.
- **HUMAN GATE:** obbligatorio per ogni prova che raggiunge il sensore reale o
  sospende il laptop. Nessun gate per progettazione e test host-only.
- **CRITERIO DI CHIUSURA:** dopo suspend/resume il sensore torna utilizzabile;
  una action cancellata termina con cleanup definito e non impedisce l'action
  successiva; i failure esercitati terminano in tempo finito con diagnostica
  leggibile e senza loop/retry nascosti; nessun fault scenario aggiuntivo viene
  investigato senza un boundary reale nel codice o un bug osservato.

### Phase E — qualificazione release, sicurezza e licenze

- **OBIETTIVO:** definire la qualità supportata e auditare l'intero artefatto di
  distribuzione, senza confondere un test funzionale con una stima FAR/FRR.
- **PERCHÉ SERVE:** i match/no-match provano correttezza del percorso, non tassi
  biometrici, robustezza generale o completezza dell'audit di supply chain.
- **PREREQUISITI:** candidate source-first e lifecycle chiusi; popolazione e criteri
  di accettazione definiti prima di raccogliere dati.
- **OUTPUT ATTESO:** threat/privacy review; SBOM/licenze/attribution; test
  matrix supportata; criteri di affidabilità e compatibilità; release candidate
  source-first riproducibile e attestabile.
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
- **OUTPUT ATTESO:** completamento delle guide di uso, amministrazione e
  sviluppo; architettura, limiti noti, evidence matrix, audit privacy/secret,
  licensing/attribution e ringraziamenti; tutta la documentazione pubblica in
  inglese; manuale rieditato e ristrutturato come vero manuale tecnico, non
  traduzione letterale o diario Dxxx; export pulito e auditato senza capture,
  firmware, secret o dati biometrici. La governance interna non richiede
  traduzione.
- **RISCHIO:** alto per disclosure accidentale; basso per codice runtime.
- **HUMAN GATE:** obbligatorio prima di modificare repository pubblico,
  pubblicare release o esporre materiale privato.
- **CRITERIO DI CHIUSURA:** documentazione coerente con l'installazione verificata,
  export/content/history audit PASS e pubblicazione approvata esplicitamente
  dall'Utente. Prima della pubblicazione tutto il materiale non pubblico è
  isolato in `red_tag/`, la directory è in `.gitignore`, nessuna build/release
  ne dipende e l'export pubblico la esclude.

La closure formale di qualunque fase richiede aggiornamento documentale,
commit e push su `origin/development`, quindi stop assoluto prima della fase
successiva:

```text
PHASE_CLOSED => STOP
```

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
- D293: installazione patch-first, visibilità reader per il nuovo utente,
  enrollment/VERIFY MATCH/delete KDE nativi e isolamento osservato del
  principal preesistente.
- D295: build/install source-first, PAM gestito e consumer, rollback
  bidirezionale, uninstall, preservazione materiali/template e recovery.

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

Le Phase A, B e C sono chiuse. Il kit D291 è
`HISTORICAL_CLOSED_DO_NOT_RERUN` e non deve essere riusato. D292/01 ha chiuso
A1, D292/02 ha chiuso A3/A4 e la review PM
D292/03 ha chiuso A5/Phase A. D293/01 chiude B1 offline con contratto e
validator statico, senza accesso ai secret. D293/02 chiude B2 offline con
implementazione e test, incluso il corrective R9 same-open IDENTIFY. D293/03
esaurisce i prerequisiti offline di B3/B4 e il contratto statico KDE
installato. Il precedente D293/04 resta evidenza offline storica non eseguita,
ora superata come metodo. La patch-first D293 è invece PASS sul target reale.
La review evidence-based dei lifecycle residui ha isolato il gap account
deletion/name reuse e D293/05 lo ha chiuso. Dopo i failure intermedi preservati
nella lineage, la candidate finale esegue il hook sotto SELinux Enforcing,
blocca l'account con print, consente la cancellazione dopo delete KDE/fprintd,
non lascia dati al name reuse e non produce alert SELinux. La baseline D293,
la guard B5 e il modulo locale restano attivi e validati. Il password fallback
di un utente enrolled conserva un ritardo osservato di circa 30 secondi per
l'ordine seriale PAM; l'Utente lo accetta come limite UX non bloccante. D294/01
resta una candidate RPM costruita e verificata offline, ma la decisione Utente
del 14 settembre 2026 la riclassifica come prototipo storico/evidenza: non è la
distribuzione ufficiale e non va installata nella nuova VM.

D295/01 apre il percorso ufficiale source-first. Il gestore costruisce da
`production/`, genera una candidate content-addressed senza secret e installa
una runtime immutabile per commit con systemd, SELinux e guard B5 indipendenti
dalle baseline Dxxx. Le simulazioni offline coprono install idempotente, update
con singolo slot, rollback, uninstall fail-closed e import separato dei cinque
materiali. README e guida Phase C sono allineati.

La Human Gate D295/01 nella Fedora 44 KDE pulita è PASS per build, hash,
materiali, install/idempotenza, USB, discovery, enrollment KDE, template,
`sudo` fingerprint e SIGFM MATCH via `pam_fprintd`. Il solo FAIL è il login
fingerprint Plasma; il login password è PASS. La causa è isolata al service
PAM `plasmalogin`: include `password-auth`, che nella profile authselect locale
non raggiunge `pam_fprintd`, mentre `system-auth` lo contiene e `sudo` funziona.

D295/02 implementa il correttivo nello stesso confine: override amministrativo
`/etc/pam.d/plasmalogin` generato dalla copia package-owned verificata, una sola
regola `auth sufficient pam_fprintd.so` prima del substack `password-auth`,
vendor `/usr/lib` intatto e stack password/session/KWallet preservato. La Human
Gate è PASS: update su `b51b4c6...`, vendor byte-identico, password login,
fingerprint login Plasma e `sudo` fingerprint sono verdi.

La review post-live conserva `status` privilegiato per i materiali root-only e
sposta la normalizzazione della runtime root nel livello privilegiato: fresh
`0755`, solo legacy `0700 -> 0755`, altri modi/ownership fail-closed. Dieci test
offline sono PASS.

D295/03 è PASS umano con sensore scollegato: rollback verso `4c9cd74...` e
ritorno a `b51b4c6...`, uninstall e fresh reinstall di `448f5c8...` hanno
preservato PAM vendor, materiali protetti e conteggio template. La baseline
finale è `ACTIVE`, material-ready, PAM gestito attivo e runtime root `0755`.
Tutti i criteri di closure C sono soddisfatti. `NEXT_PHASE=D` è soltanto stato
di roadmap: nessuna attività Phase D viene iniziata o preparata in questa
sessione.

Decisione Utente del 14 settembre 2026: la Phase D è ridotta ai soli
`suspend/resume` e `cancellation/recovery`. Hotplug, device removal,
concorrenza/consumer simultanei, late bytes/cross-generation e stato `POISONED`
non sono requisiti di test dedicati e verranno riaperti soltanto davanti a un
boundary concreto nel codice o a un bug osservato.

```text
PM_DECISION=PROJECT_STEP_COMPLETE
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
R9_SAME_OPEN_IDENTIFY=CONFIRMED_AND_CORRECTED
D293_03_OUTCOME=PASS_HOST_ONLY
PHASE_B_B3_OFFLINE_PREREQUISITES=COMPLETED
KDE_KCM_STATIC_CONTRACT=PASS
PHASE_B_B4_OFFLINE_PREREQUISITES=COMPLETED
D293_04_HISTORICAL_RESULT=READY_OFFLINE_NOT_EXECUTED
D293_04_COMPLEX_KIT=SUPERSEDED_BY_METHOD_DECISION
TEST_METHOD=PATCH_FIRST_LIVE_VALIDATION
OPERATOR_KIT_DEFAULT=false
D293_INSTALL_PATCH=READY
D293_ROLLBACK_PATCH=READY
D293_LIVE_INSTRUCTIONS=READY
D293_TEST_PURPOSE_DOCUMENTED=true
D293_PASS_FAIL_STOP_CRITERIA=READY
D293_ROLLBACK_INSTRUCTIONS=READY
D293_INSTALLS_OPERATOR_KIT=false
D293_INSTALLS_CURRENT_PRODUCTION_CANDIDATE=true
D293_04_LIVE_EXECUTION=NOT_PERFORMED
D293_NATIVE_KDE_LIVE=PASS
D293_NATIVE_VERIFY=MATCH
D293_NATIVE_VERIFY_ATTEMPT=NOT_REPORTED
D293_VALIDATED_FEATURE=ACTIVE_BASELINE
D293_ACTIVE_BASELINE_SHA=e61fce313794922a2dab156a1b38a8ddc5837f19
D285=ROLLBACK_PREDECESSOR
ROLLBACK_PATCH_REQUIRED=true
ROLLBACK_ON_FAIL=true
ROLLBACK_ON_PASS=false
KEEP_VALIDATED_ADVANCEMENT_BY_DEFAULT=true
LIVE_EXECUTED_BY_AI=false
PHASE_B_CLOSED=true
PROJECT_NEXT_STEPS_PLAN_READY=true
CURRENT_PHASE=C_CLOSED
PRODUCTION_READY=false
PHASE_B_CLOSURE_REVIEW=PASS_ALL_REQUIRED_CRITERIA
D293_05_FIRST_INSTALL=PASS
D293_05_FIRST_LIVE=FAIL
D293_05_FAILURE_CLASS=HOST_SELINUX_EXECUTION_POLICY
D293_05_FAILURE_POINT=USERDEL_PRE_HOOK_EXEC
D293_05_ROLLBACK=PASS
D293_05_ACCOUNT_DELETE_AFTER_ROLLBACK=PASS
D293_05_SELINUX_CORRECTIVE=PASS_ON_TARGET
D293_05_CORRECTIVE_LIVE=PASS
D293_05_OUTCOME=PASS_FULL_ON_TARGET
D293_B5_SELINUX_ENFORCING=PASS
D293_B5_SELINUX_ALERTS=0
D293_B5_PATCH_LEFT_INSTALLED=true
FINGERPRINT_LOGIN=PASS
PASSWORD_LOGIN_NON_ENROLLED_USERS=PASS_NO_DELAY
PASSWORD_FALLBACK_ENROLLED_USERS=PASS_WITH_APPROX_30S_DELAY
PAM_ENROLLED_PASSWORD_DELAY_SEVERITY=ACCEPTED_UX_LIMITATION
PHASE_B_BLOCKER=false
NEW_LIVE_REQUIRED_NOW=false
NEXT_PHASE=D
NEXT_WORK_CLASS=PHASE_D_NOT_STARTED
PHASE_D_SCOPE=MINIMAL_SUSPEND_RESUME_AND_CANCELLATION_RECOVERY
PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL
RPM_OFFICIAL_DISTRIBUTION=false
D294_RPM_ROLE=HISTORICAL_PROTOTYPE_AND_EVIDENCE
D294_01_LIVE_VALIDATION=SUPERSEDED_NOT_TO_RUN
CURRENT_TASK=NONE_PHASE_C_CLOSED
NEXT_BOUNDARY=USER_INITIATED_PHASE_D_DECISION
D294_01_RPM_BUILD=PASS
D294_01_PACKAGED_LIBRARY_BYTE_IDENTICAL=true
D294_01_OFFLINE_TESTS=12_PASS
D294_01_PAM_FILE_COUNT=0
D294_01_PROTECTED_MATERIAL_FILE_COUNT=0
D294_01_OUTCOME=READY_FOR_FACTORY_PRESERVING_LIVE
D294_01_EXECUTABLE_CLOSURE=PASS_OFFLINE_MAXIMUM
D295_01_OFFLINE_TESTS=6_PASS
D295_01_SOURCE_FIRST_BUILD=PASS
D295_01_CANDIDATE_DIGESTS=PASS
D295_01_INSTALL_IDEMPOTENT=PASS_SYNTHETIC_ROOT
D295_01_UPDATE_ROLLBACK_UNINSTALL=PASS_SYNTHETIC_ROOT
D295_01_PROTECTED_MATERIAL_IMPORT=PASS_SYNTHETIC_CONTENT_ONLY
D295_01_REAL_SUDO_EXECUTED=false
D295_01_REAL_USB_ACCESS=0
D295_01_PAM_CHANGED=false
D295_01_CLEAN_VM_BUILD_INSTALL=PASS_HUMAN_OBSERVED
D295_01_CLEAN_VM_ENROLLMENT=PASS_HUMAN_OBSERVED
D295_01_GENERIC_PAM_FINGERPRINT=PASS_HUMAN_OBSERVED
D295_01_PLASMALOGIN_FINGERPRINT=FAIL_HUMAN_OBSERVED
D295_PLASMALOGIN_PAM_CORRECTIVE=PASS_LIVE
PACKAGE_OWNED_PLASMALOGIN_MODIFIED=false
MANAGED_PAM_INTEGRATION=true
INSTALL_IDEMPOTENT=true
ROLLBACK_SUPPORTED=true
UNINSTALL_RESTORES_PREVIOUS_STATE=true
PASSWORD_FALLBACK_PRESERVED_BY_DESIGN=true
USER_SPECIFIC_CONFIGURATION=false
SENSOR_REACHING_EXECUTED_BY_AI=false
D295_02_OFFLINE_TESTS=10_PASS_POST_REVIEW
D295_02_LIVE_EXECUTION=PASS_HUMAN_OBSERVED
D295_02_PASSWORD_LOGIN=PASS
D295_02_FINGERPRINT_LOGIN=PASS
D295_02_SUDO_FINGERPRINT=PASS
D295_02_VENDOR_PAM_UNCHANGED=true
D295_03_LIVE_EXECUTION=PASS_HUMAN_OBSERVED
D295_03_ROLLBACK_BIDIRECTIONAL=PASS
D295_03_UNINSTALL=PASS
D295_03_PROTECTED_MATERIAL_PRESERVATION=PASS
D295_03_TEMPLATE_PRESERVATION=PASS
D295_03_RECOVERY_REINSTALL=PASS
D295_03_FINAL_BASELINE_COMMIT=448f5c8cc6099032a23115a96e90428d75b74a7b
PHASE_C_CLOSURE_CRITERIA=PASS
PHASE_C_CLOSED=true
PM_DECISION=PROJECT_STEP_COMPLETE
PHASE_CLOSED => STOP
```