# D278/02 — native target-material boundary e harness secure-session live-capable

```text
OUTCOME=READY_PASS_HOST_ONLY_PRELIVE
ADVANCEMENT=NEW_NATIVE_TARGET_MATERIAL_BOUNDARY_AND_LIVE_CAPABLE_SECURE_SESSION_HARNESS_HOST_ONLY_PROVEN
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=TARGET_PROTECTED_MATERIAL_PREFLIGHT_NOT_EXECUTED;NATIVE_SECURE_SESSION_TARGET_UNPROVEN_BEYOND_A8_A0;NEXT_LIVE_BASELINE_SHA_NOT_APPROVED;CURRENT_LIVE_AUTHORIZED_FALSE
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_94a61c69c6f31d1ace196549c96c1e2410c598d2_PLUS_STEP_LOCAL_GIT_DIFF
```

## Risultato e confine probatorio

D278/02 aggiunge il boundary nativo per i materiali target, il binder D190
PSK→validator E4, l’estrattore PE read-only, l’orchestratore single-generation
con watchdog per fase e un eseguibile che compila sia il percorso sintetico sia
il binding libfprint/GUsb destinato a una futura run live. In questo step sono
stati eseguiti soltanto test host-only e `--self-test`.

Le classi di evidenza restano separate:

- `HISTORICAL_PROVENANCE`: commit D190
  `b475a6eca72e340816779afae917334a6146c986`, sorgenti BSD-2-Clause e cinque
  validator noti indipendenti;
- `D277_02_TARGET_PROOF`: soltanto A8/A0/identity APP12509 sul target;
- `D278_01_HOST_ONLY_PROOF`: catena sintetica A8→STOP con peer OpenSSL TLS 1.2
  PSK reale, incluso il correttivo D1→TLS già revisionato, passato in CI e
  confluito su main;
- `D278_02_NEW_HOST_ONLY_PROOF`: binder, parser PE, loader, composizione,
  watchdog, drain e telemetria provati con materiali sintetici;
- `TARGET_UNPROVEN`: nessuna prova target E4, pre-D1, D1 o TLS è stata
  prodotta.

```text
TARGET_PROTECTED_MATERIAL_PREFLIGHT_EXECUTED=false
LIVE_EXECUTION_PERFORMED=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
CURRENT_LIVE_AUTHORIZED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
USB_OPEN_COUNT=0
USB_CLAIM_COUNT=0
```

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

Il binder LGPL è un adattamento nativo delimitato della reference BSD e usa
le API EVP/OpenSSL 3. L’estrattore PE GPL è anch’esso un adattamento bounded:
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
duplica solo ciò che deve sopravvivere al rilascio dell’owner esterno. Scratch,
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

Il protected store reale non è stato letto e `--material-preflight-only` non è
stato eseguito.

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

Il launcher GPL offre tre modalità, ma in D278/02 è stata eseguita soltanto la
prima:

```text
--self-test                     EXECUTED_HOST_ONLY
--material-preflight-only       NOT_EXECUTED
--live-exact-secure-session     BUILD_ONLY_NOT_EXECUTED
```

Il live path carica e valida i materiali prima della creazione del contesto
GUsb, seleziona esattamente un 27c6:5125, apre/reclama una sola volta, usa una
sola generation e garantisce release/close dopo drain. La sua presenza non è
autorizzazione live.

## Evidenza eseguibile

Il runner principale `libfprint-driver/tests/run_goodix_d278_02_test.sh` è
stato eseguito due volte consecutivamente nell’SDK Freedesktop 25.08 offline.
Ogni invocazione esegue 54 casi normali e gli stessi 54 sotto ASAN/UBSAN,
compila il binding libfprint/GUsb completo e avvia `--self-test`. In totale:

```text
D278_02_TEST_COUNT_PER_BINARY_RUN=54
D278_02_NORMAL=54/54 PASS per invocazione
D278_02_ASAN_UBSAN=54/54 PASS per invocazione
D278_02_PRINCIPAL_RUNNER_INVOCATIONS=2
D278_02_TOTAL_CASE_EXECUTIONS=216
D278_02_LIVE_HARNESS_BUILD=PASS
D278_02_SELF_TEST=PASS_EXPECTED_A8_WATCHDOG_TERMINAL
```

I 54 casi sono 6 D190, 6 PE, 22 material-loader e 20
harness/watchdog/telemetria. LeakSanitizer resta disabilitato perché il confine
Flatpak/bwrap non rende disponibile ptrace; ASAN address checks e UBSAN sono
attivi.

Regressioni finali:

```text
D278_01=10/10 normal + 10/10 ASAN/UBSAN PASS
D276_04=5/5 normal + 5/5 ASAN/UBSAN PASS
D276_02_FPIMAGE=15/15 normal + 15/15 ASAN/UBSAN PASS
D276_03_ROUTER=8/8 normal + 8/8 ASAN/UBSAN PASS
D277_HOST_ONLY=15/15 normal + 15/15 ASAN/UBSAN PASS
D277_LIVE_HARNESS=BUILD_ONLY_NOT_EXECUTED
```

## Invarianti finali host-only

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

## Riesame metodologico pre-live preparato

1. **Cambiamento materiale.** D277/02 provava sul target soltanto
   A8/A0/APP12509. D278/02 aggiunge boundary protetto nativo, binder PSK→E4
   alimentato dalla stessa PSK del TLS, composizione completa e watchdog per
   fase.
2. **Ipotesi live.** Con materiali autentici e validati, APP12509 avanzerà
   A8→E4 MATCH→A2→82→A6→A2→70→80×4→90→D1→TLS 1.2 PSK ESTABLISHED→STOP,
   senza D4 né stato persistente.
3. **Policy al primo fallimento.** Stop immediato; registrazione della prima
   fase e classe redatta; zero retry/reopen/reset; drain e zeroizzazione;
   ritorno ad AI-PM; nessun secondo tentativo equivalente senza nuova
   decisione metodologica.

Questo riesame è preparatorio e non autorizza una run. Prima di qualunque live
servono review AI-PM, SHA completo della baseline live approvato esplicitamente
e autorizzazione single-shot separata.
