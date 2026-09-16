<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D292/03 — closure Phase A e passaggio a Phase B

Baseline: `9f86fa8984f3188a6de74593d1eb814b26f07291`  
Target: Fedora 44 KDE x86_64, Goodix `27c6:5125` / APP12509  
Tipo: consolidamento A5 e review di closure; nessun codice, build input,
licensing boundary, live, USB, privilegio o materiale protetto modificato.

## Decisione di closure

La review PM diretta chiude Phase A. A1 ha derivato e classificato il file set
reale; A3/A4 hanno materializzato `production/` come unica autorità di
composizione e provato la build riproducibile; A5 verifica che manifest,
provenance/licenze, patch production e artefatto siano coerenti e che la
pipeline non dipenda da operator kit Dxxx, aree test o analysis.

```text
D292_03_OUTCOME=PASS_PHASE_A_CLOSURE
PHASE_A_A1=COMPLETED
PHASE_A_A3=COMPLETED
PHASE_A_A4=COMPLETED
PHASE_A_A5=COMPLETED
PHASE_A_CLOSED=true
CURRENT_PHASE=B
PRODUCTION_READY=false
NEXT_BOUNDARY=PHASE_B_B1_MULTI_USER_FPRINTD_STORAGE_AND_PROTECTED_RUNTIME_MATERIAL_CONTRACT_OFFLINE
```

Questa closure non dichiara pronto il prodotto: multi-user, packaging,
lifecycle e release restano rispettivamente nelle Phase B–E. Non autorizza
move/delete/red tag, install/deploy, nuovo accesso live o riuso di materiale
protetto.

## Evidence set riesaminato dal PM

La review PM ha verificato direttamente:

- `production/check-source.sh` e il validator D292: PASS;
- canonical normal build: PASS, SHA-256
  `11f829bd8aa912aef92a00eb68a15b4b5ab430fafd948fec944da33f9c1482a2`;
- ABI fprintd: 47/47 simboli `LIBFPRINT_2.0.0`, SONAME
  `libfprint-2.so.2`, nessun RPATH/RUNPATH;
- tutti i 39 simboli host/test-only assenti dalla libreria production;
- D291 enrollment diversity: 4/4 normal e 4/4 sanitizer;
- secure-session: 30/30 normal e 30/30 sanitizer;
- FpImageDevice: 32/32 normal e 32/32 sanitizer;
- preprocess KAT/audit: PASS;
- standalone preprocess ASan: `BLOCKED_ENVIRONMENT_LIBASAN_ABSENT`.

Il solo blocker standalone ASan non blocca A: la canonical sanitizer build e
le suite integrate sanitizer passano, quindi il codice production è già
compilato/linkato ed esercitato nel percorso che conta. Non viene degradato a
PASS: resta registrato come limite dell'ambiente standalone.

```text
PM_REVIEW=PASS
CANONICAL_NORMAL_BUILD=PASS
CANONICAL_ARTIFACT_SHA256=11f829bd8aa912aef92a00eb68a15b4b5ab430fafd948fec944da33f9c1482a2
FPRINTD_ABI_REQUIRED_PROVIDED=47/47
SONAME=libfprint-2.so.2
RPATH_OR_RUNPATH=false
PRODUCTION_HOST_TEST_ONLY_SYMBOLS=0/39
D291_DIVERSITY_NORMAL_SANITIZER=4/4_4/4
SECURE_SESSION_NORMAL_SANITIZER=30/30_30/30
FPIMAGEDEVICE_NORMAL_SANITIZER=32/32_32/32
PREPROCESS_KAT_AUDIT=PASS
PREPROCESS_STANDALONE_ASAN=BLOCKED_ENVIRONMENT_LIBASAN_ABSENT_NON_BLOCKING
REAL_USB=0
```

## Compatibilità target senza nuova live

La compatibilità richiesta dalla closure A è una composizione di evidenze,
non una nuova inferenza device-side isolata:

1. D291 prova sul target APP12509 enrollment diversity, re-enrollment,
   wrong-finger e quattro serie con MATCH attraverso libfprint/fprintd;
2. il delta D292 che raggiunge production è limitato a source composition,
   build policy stabile, esclusione di emulazione/seam test e superficie
   simboli; non cambia protocollo wire, lifecycle sensor-reaching, decoder,
   SIGFM/R2 o materiali runtime target-proven;
3. la build corrente prova Fedora 44, ABI richiesta dal fprintd installato,
   SONAME, dipendenze e assenza di RPATH, mentre normal/sanitizer e suite
   integrate coprono il percorso risultante.

Perciò una ripetizione live non aggiungerebbe evidenza sul boundary Phase A e
non è autorizzata. `REAL_USB=0` per D292/03.

## A5 — superficie distribuibile e provenance

La superficie distribuibile è definita dalla baseline pristine Fedora
44/libfprint 1.94.100, patch production di 15 file e subset locale
Goodix/SIGFM/R2 manifestato e hashato. Il delta test storico
`tests/meson.build` è fuori dalla patch prodotto. Il ledger conserva licenze
per-file: libfprint/SIGFM LGPL, componenti locali secondo SPDX e R2 GPL;
il combined work resta nel regime GPL-compatible già documentato. Nessun
relicensing o nuovo materiale esterno è introdotto.

I path storici D282/D285 restano evidence/tooling: non sono input della build
canonica e non vengono spostati o cancellati. D285 `/usr/local`, wrapper e path
dei materiali protetti sono problemi successivi di contratto multi-user e
packaging, non residui della source-of-truth Phase A.

## Boundary corrente Phase B/B1

Il primo task di Phase B è un'analisi offline del contratto multi-user nativo:
ownership e storage standard fprintd, isolamento e lifecycle dei template per
utenti locali, e requisiti separati dei materiali protetti runtime (necessità,
origine, natura per-device, permessi/ownership e provisioning lecito). Non va
creato un database Goodix parallelo; non vanno letti secret o materiali
protetti durante l'analisi. Ogni futura live resta Human Gate.

```text
PHASE_ORDER=A>B>C>D>E>F
PHASE_B_B1_MODE=OFFLINE_ANALYSIS
FPRINTD_OWNS_USERS_AND_TEMPLATES=true
PROTECTED_RUNTIME_MATERIAL_ACCESS_AUTHORIZED=false
NEW_LIVE_REQUIRED_NOW=false
```
