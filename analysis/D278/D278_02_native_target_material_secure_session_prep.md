# D278/02 — native target-material boundary e harness secure-session live-capable

```text
OUTCOME=READY
ADVANCEMENT=REAL_EXECUTION_COMPLETED_AUTHENTIC_PROTECTED_MATERIAL_PREFLIGHT_WITH_E4_BINDING_MATCH_AND_ZERO_USB_ACCESS
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=NATIVE_SECURE_SESSION_TARGET_UNPROVEN_BEYOND_A8_A0;TARGET_E4_NATIVE_LIVE_UNPROVEN;TARGET_TLS_NATIVE_LIVE_UNPROVEN;CURRENT_LIVE_AUTHORIZED_FALSE
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_1d25abc7b4a99ea1719cc4381d6f780501483209_PLUS_BRANCH_ai-pm/d27802-preflight-closure_PLUS_analysis/D278/D278_02_operator_protected_material_preflight_20260829.json_PLUS_D278_02_CANONICAL_DOC_UPDATES

AI_PM_INITIAL_REVIEW=FAIL_CORRECTIVE_REQUIRED
INITIAL_REVIEW_BLOCKER=CANONICAL_A2_RESPONSE_SHA256_PRODUCTION_PIN_MISMATCH
CANONICAL_A2_SHA256_EXPECTED=39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5
CANONICAL_A2_SHA256_IMPLEMENTED_AFTER_FIX=39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5

D278_02_NORMAL=PASS
D278_02_ASAN_UBSAN=PASS
D278_02_DETERMINISM_RUNS=2
D278_02_TEST_COUNT_PER_BINARY_RUN=62
PRODUCTION_POLICY_CANONICAL_PIN_MATRIX=PASS
```

## Cronologia del correttivo D278/02

La revisione AI-PM iniziale sul commit
`6f98d80c8fc82ea9d69d17fa0e18df325eee9128` richiese un correttivo
focalizzato: il pin A2 della policy produttiva in
`goodix_target_material_policy_production()` non corrispondeva all'evidenza
canonica D232.

```text
initial clean D278/02 implementation = 6f98d80c8fc82ea9d69d17fa0e18df325eee9128
initial GitHub Actions run = 33246743946
initial CI = PASS
AI-PM initial review = FAIL_CORRECTIVE_REQUIRED
reason = CANONICAL_A2_RESPONSE_SHA256_PRODUCTION_PIN_MISMATCH
```

Il valore canonico fu verificato direttamente in
`analysis/D232/D232_target_material_manifest.json`:

```text
A2 response length = 3
A2 response SHA-256 = 39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5
```

L'array C fu corretto per allinearsi a questo valore. Il test indipendente
`/d278_02/material/production_policy_canonical_pins` confronta i pin critici
della policy produttiva con costanti attese indipendenti, ricavate dalle
evidenze canoniche del progetto senza derivarle dalla policy stessa.

Nota storica: il testo del prompt correttivo riportava un hash A2 terminante in
`5f`; questo valore non è presente nel repository né nel manuale tecnico
canonico e non è stato utilizzato. L'unica fonte canonica resta il manifest
D232.

## Micro-correttivo di osservabilità e closure canonica

La cronologia resta distinta: implementazione iniziale `6f98d80...`, review
AI-PM iniziale `FAIL_CORRECTIVE_REQUIRED`, correttivo A2, review AI-PM del
correttivo A2 `PASS`, quindi merge su main
`01b2379395b59219112236a6387bee9e5bd47bbf` con CI `33252621869` PASS.

Il successivo micro-correttivo di osservabilità è il commit
`4d388a8031f99f8cee07102811680ee6167353c1`. La review AI-PM è `PASS`; la PR
#35 è confluita su `main` con merge commit
`1d25abc7b4a99ea1719cc4381d6f780501483209` e la CI post-merge
`33255017404` è `PASS`.

La composizione del preflight conserva la provenance redatta come coppia
stabile `failure_stage`/`failure_class`: load (`ARGUMENT_OR_POLICY`,
`PROTECTED_OPEN`, `PROTECTED_METADATA`, `PROTECTED_READ`,
`PROTECTED_CONTENT`), PE/DLL (`CANONICAL_PE_OR_DLL`), bind E4
(`E4_BINDING`) ed export/state (`MATERIAL_EXPORT_OR_STATE`). Nessun messaggio
GError libero né byte protetto entra nella telemetria JSON. I casi di test
usano esclusivamente fixture temporanee sintetiche.

```text
D278_02_CANONICAL_A2_CORRECTIVE_AI_PM_REVIEW=PASS
AI_PM_REVIEWED_MAIN_BASELINE=01b2379395b59219112236a6387bee9e5bd47bbf
CORRECTIVE_CI_RUN=33252621869
CORRECTIVE_CI=PASS
D278_02_MICRO_CORRECTIVE_COMMIT=4d388a8031f99f8cee07102811680ee6167353c1
D278_02_MICRO_CORRECTIVE_AI_PM_REVIEW=PASS
D278_02_MICRO_CORRECTIVE_MERGED_MAIN=1d25abc7b4a99ea1719cc4381d6f780501483209
D278_02_POST_MERGE_CI_RUN=33255017404
D278_02_POST_MERGE_CI=PASS
PROTECTED_PREFLIGHT_FAILURE_OBSERVABILITY=PASS
PROTECTED_PREFLIGHT_REDACTION=PASS
NO_SECRET_BYTES_IN_FAILURE_TELEMETRY=PASS
FAILURE_CLASS_STABLE=PASS
FAILURE_STAGE_STABLE=PASS
```

## Risultato e confine probatorio

D278/02 aggiunge il boundary nativo per i materiali target, il binder D190
PSK→validator E4, l'estrattore PE read-only, l'orchestratore single-generation
con watchdog per fase e un eseguibile che compila sia il percorso sintetico sia
il binding libfprint/GUsb destinato a una futura run live.

Le classi di evidenza restano separate:

- `HISTORICAL_PROVENANCE`: commit D190
  `b475a6eca72e340816779afae917334a6146c986`, sorgenti BSD-2-Clause e cinque
  validator noti indipendenti;
- `D277_02_TARGET_PROOF`: soltanto A8/A0/identity APP12509 sul target;
- `D278_01_HOST_ONLY_PROOF`: catena sintetica A8→STOP con peer OpenSSL TLS 1.2
  PSK, incluso il correttivo D1→TLS revisionato, passato in CI e confluito su
  main;
- `D278_02_HOST_ONLY_PROOF`: binder, parser PE, loader, composizione, watchdog,
  drain e telemetria provati con materiali sintetici;
- `D278_02_AUTHENTIC_PROTECTED_MATERIAL_PREFLIGHT`: materiali autentici del
  target verificati read-only dall'operatore, con D190/E4 binding `MATCH` e
  zero accesso USB;
- `TARGET_UNPROVEN`: nessuna nuova prova live target di E4, pre-D1, D1 o TLS è
  stata prodotta dal preflight.

```text
TARGET_PROTECTED_MATERIAL_PREFLIGHT_EXECUTED=true
TARGET_PROTECTED_MATERIAL_PREFLIGHT=PASS
TARGET_E4_BINDING_PREFLIGHT=PASS
TARGET_MATERIAL_PREFLIGHT_FAILURE_STAGE=NONE
TARGET_MATERIAL_PREFLIGHT_FAILURE_CLASS=none
TARGET_MATERIAL_PREFLIGHT_RC=0
TARGET_MATERIAL_PREFLIGHT_REAL_USB_ACCESS=0
TARGET_MATERIAL_PREFLIGHT_USB_OPEN_COUNT=0
TARGET_MATERIAL_PREFLIGHT_USB_CLAIM_COUNT=0
TARGET_MATERIAL_PREFLIGHT_REAL_USB_SUBMIT_COUNT=0
TARGET_MATERIAL_PREFLIGHT_RETRY_COUNT=0
TARGET_MATERIAL_PREFLIGHT_DEVICE_RESET_COUNT=0
TARGET_MATERIAL_PREFLIGHT_PERSISTENT_DEVICE_WRITE_COUNT=0
TARGET_MATERIAL_PREFLIGHT_PROJECT_SECRET_ZEROIZED=true
LIVE_EXECUTION_PERFORMED=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
CURRENT_LIVE_AUTHORIZED=false
D4_REACHABLE=false
APPLICATION_DATA_COUNT=0
```

L'evidenza redatta dell'esecuzione operatore è versionata in
`analysis/D278/D278_02_operator_protected_material_preflight_20260829.json`.
Il log locale `/tmp/d278_02_material_preflight_20260829T205137.log` è effimero e
non appartiene al review set canonico.

## Provenance D190 e DLL

Il gate storico ha verificato al commit D190:

```text
LICENSE=BSD-2-Clause
LICENSE_BLOB=42fd7050a89d195cacb4b002f91a2f679a8b5285
COPYRIGHT=Copyright (c) 2026 sorguido
poc/goodix5125/tools/binding_reference/crypto_reference.py blob=98c45c87c91b5d3e64e003788df31b5c3d8fb12e
poc/goodix5125/tools/binding_reference/pe_parser.py blob=c2f6451308f1f0e78942c02b46daa3b85b061577
poc/goodix5125/tools/binding_reference/runtime.py blob=9e6643e7c77fcc53947b87cca22ef9eb565fb95c
poc/goodix5125/tools/binding_reference/known_answers.py blob=eb804cc713f90f9b0ba0d5bcbb9516b5525e76a5
```

Il binder LGPL è un adattamento nativo delimitato della reference BSD e usa le
API EVP/OpenSSL 3. L'estrattore PE GPL è anch'esso un adattamento bounded:
legge la DLL esclusivamente come byte inerti, impone hash e RVA canonici,
verifica unicità/forma delle istruzioni e pulisce i seed. Non esistono
`LoadLibrary`, `dlopen`, Wine, subprocess o mapping eseguibili.

```text
DLL=analysis/D230/work/GoodixExport/gfusb.dll
DLL_SIZE=5771496
DLL_SHA256=904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2
DLL_LOADED_OR_EXECUTED=false
D190_FIVE_INDEPENDENT_KATS=PASS
```

## Boundary dei materiali protetti

La policy produttiva è fissa a uid 0 e mode 0600. Ogni file viene aperto
read-only con `O_CLOEXEC|O_NOFOLLOW`, verificato via `fstat` prima e dopo la
lettura e accettato soltanto se tipo, owner, mode, device/inode e lunghezza
sono coerenti. Il manifest, il container da 88 byte e CONFIG90 sono hash-pinned;
il container deve avere magic `G5125POC` e PSK nei byte 24..55. CONFIG90 deve
soddisfare hash, finalizer e quattro correlazioni DAC ordinate.

Il loader possiede una sola copia PSK e una sola copia validator; la sessione
duplica solo ciò che deve sopravvivere al rilascio dell'owner esterno. Scratch,
PSK, validator, CONFIG90 e intermedi D190 sono cancellati esplicitamente prima
del `g_free`. Gli observer di test leggono i buffer soltanto prima del free.

```text
NATIVE_PROTECTED_MATERIAL_LOADER_HOST_ONLY_PROVEN=true
PROTECTED_MATERIAL_NEGATIVE_MATRIX=PASS
PRODUCTION_MATERIAL_POLICY_UID=0
PRODUCTION_MATERIAL_POLICY_MODE=0600
PROJECT_OWNED_ZEROIZATION=PROVEN_TO_IMPLEMENTATION_BOUNDARY
OPENSSL_INTERNAL_ZEROIZATION=NOT_ASSERTED
E4_DERIVED_FROM_SAME_PSK_AS_TLS=true
PERSISTENT_E4_VALIDATOR_CREATED=false
```

### Preflight autentico operatore — 29 agosto 2026

L'operatore ha eseguito una sola volta `--material-preflight-only` dalla root
canonica del repository. I privilegi host sono serviti esclusivamente a leggere
i file protetti `root:root 0600`; non costituiscono autorizzazione USB/live.

Il launcher proveniva dalla preparazione host-only immediatamente precedente:

```text
D278_02_NORMAL=PASS
D278_02_ASAN_UBSAN=PASS
D278_02_LIVE_HARNESS_BUILD=PASS
D278_02_SELF_TEST=PASS
D278_02_TEST_COUNT=62
LAUNCHER_SHA256=3ef04925dd440c8c6d1f14d1e764e99a10355f4d205c90529df4ad30d22deacb
```

Il preflight autentico ha restituito:

```text
failure_stage=NONE
preflight_passed=true
failure_class=none
e4_binding_match=true
project_secret_zeroized=true
PREFLIGHT_RC=0
usb_open_attempt_count=0
usb_open_count=0
usb_claim_count=0
real_usb_submit_count=0
command_count=0
tls_handshake_count=0
persistent_device_write_count=0
retry_count=0
device_reset_count=0
current_live_authorized=false
```

Il PASS prova che il percorso produttivo di caricamento/verifica dei materiali
autentici e il binder D190 producono il binding E4 atteso usando il materiale
reale già preservato. Non prova che un E4 sia stato inviato dal nuovo percorso
nativo, né che il sensore lo abbia accettato, né che il TLS nativo abbia
handshakato sul target.

I campi generici `reached_phase=A8`, `backend_drained=false` e
`terminal_cleanup_completed=false` non descrivono un cleanup live incompleto:
la modalità preflight non avvia il backend/session lifecycle USB.

## Harness e watchdog

`GoodixD278Harness` compone gli oggetti reali `GoodixSecureSession`,
`GoodixUsbRouter`, `GoodixTlsServer` e `GoodixFpiUsbBackend`. Il test seam
sostituisce soltanto la completion fisica: protocollo e TLS non sono simulati.
Il percorso positivo attraversa esattamente:

```text
A8,E4,A2_1,CHIP_82,OTP_A6,A2_2,MODE_70,
DAC_220,DAC_236,DAC_238,DAC_23A,CONFIG_90,D1,TLS,STOP
```

Ogni progresso di fase invalida il timer precedente e arma il limite della
nuova fase sul main context GLib. A8, CONFIG90/pre-D1 e TLS sono coperti da
timeout deterministici reali; callback scadute o terminali non possono
produrre USB o avanzamento. STOP/cancel applicano il fence, poi si attende il
drain prima di liberare sessione, backend e router.

Lo stato delle tre modalità è ora:

```text
--self-test                     EXECUTED_HOST_ONLY_PASS
--material-preflight-only       EXECUTED_OPERATOR_AUTHENTIC_PASS_ZERO_USB
--live-exact-secure-session     BUILD_ONLY_NOT_EXECUTED
```

Il live path carica e valida i materiali prima della creazione del contesto
GUsb, seleziona esattamente un `27c6:5125`, apre/reclama una sola volta, usa una
sola generation e garantisce release/close dopo drain. La sua presenza e il
PASS del preflight non costituiscono autorizzazione live.

## Evidenza eseguibile host-only

Il runner principale `libfprint-driver/tests/run_goodix_d278_02_test.sh` è
stato eseguito due volte consecutivamente nell'SDK Freedesktop 25.08 offline.
Ogni invocazione esegue 62 casi normali e gli stessi 62 sotto ASAN/UBSAN,
compila il binding libfprint/GUsb completo e avvia `--self-test`.

```text
D278_02_TEST_COUNT_PER_BINARY_RUN=62
D278_02_NORMAL=62/62 PASS per invocazione
D278_02_ASAN_UBSAN=62/62 PASS per invocazione
D278_02_PRINCIPAL_RUNNER_INVOCATIONS=2
D278_02_TOTAL_CASE_EXECUTIONS=248
D278_02_LIVE_HARNESS_BUILD=PASS
D278_02_SELF_TEST=PASS_EXPECTED_A8_WATCHDOG_TERMINAL
PRODUCTION_POLICY_CANONICAL_PIN_MATRIX=PASS
```

I 62 casi sono 6 D190, 6 PE, 23 material-loader, 7 preflight-observability e
20 harness/watchdog/telemetria. LeakSanitizer resta disabilitato perché il
confine Flatpak/bwrap non rende disponibile ptrace; ASAN address checks e UBSAN
sono attivi.

Regressioni finali host-only:

```text
D278_01=10/10 normal + 10/10 ASAN/UBSAN PASS
D276_04=5/5 normal + 5/5 ASAN/UBSAN PASS
D276_02_FPIMAGE=15/15 normal + 15/15 ASAN/UBSAN PASS
D276_03_ROUTER=8/8 normal + 8/8 ASAN/UBSAN PASS
D277_HOST_ONLY=15/15 normal + 15/15 ASAN/UBSAN PASS
D277_LIVE_HARNESS=BUILD_ONLY_NOT_EXECUTED
```

## Invarianti finali

```text
MATERIAL_INVALID_BLOCKS_BEFORE_USB_OPEN=PASS
SYNTHETIC_SINGLE_OPEN_CLAIM_EPOCH=PASS
PHYSICAL_RECEIVE_OWNER_COUNT=1
MAX_PHYSICAL_IN_OUTSTANDING=1
MAX_PHYSICAL_OUT_OUTSTANDING=1
SECOND_READER_API_PATH=ABSENT
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
A0_FIXED64=false
B0_FIXED64=true
B0_ZERO_TAIL=true
TLS_RECORD_PACING_MS=10
D4_REACHABLE=false
APPLICATION_DATA_COUNT=0
FINGER_PATH_NOT_EXERCISED=true
IMAGE_PATH_NOT_EXERCISED=true
```

## Riesame metodologico pre-live

1. **Cambiamento materiale.** D277/02 provava sul target soltanto
   A8/A0/APP12509. D278/02 aggiunge boundary protetto nativo, binder PSK→E4
   alimentato dalla stessa PSK del TLS, composizione completa e watchdog per
   fase; il preflight autentico ha ora confermato che il materiale reale supera
   tale boundary con `e4_binding_match=true` e zero USB.
2. **Ipotesi live.** Con gli stessi materiali autentici già preflightati,
   APP12509 avanzerà nel nuovo percorso nativo
   `A8→E4 MATCH→A2→82→A6→A2→70→80×4→90→D1→TLS 1.2 PSK ESTABLISHED→STOP`,
   senza D4 né stato persistente.
3. **Policy al primo fallimento.** Stop immediato; registrazione della prima
   fase e classe redatta; zero retry/reopen/reset; drain e zeroizzazione;
   ritorno ad AI-PM; nessun secondo tentativo equivalente senza nuova
   decisione metodologica.

Il prossimo boundary è una review pre-live del live-critical set e della
procedura operatore. Qualunque esecuzione reale richiede un nuovo SHA completo
approvato esplicitamente e una nuova autorizzazione single-shot dell'Utente.
Il `sudo` necessario sul terminale operatore resta una responsabilità umana
separata e non viene delegato a Codex/AI.

```text
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_THEN_EXPLICITLY_AUTHORIZED_SINGLE_SHOT_NATIVE_TARGET_SECURE_SESSION
LIVE_EXECUTION_PERFORMED=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
CURRENT_LIVE_AUTHORIZED=false
```
