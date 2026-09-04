<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/08 — binding production `img_open` / `img_close`

## Esito

```text
D279_08_OUTCOME=READY_OFFLINE
ADVANCEMENT=MATERIAL_ARCHITECTURAL_AND_REPOSITORY_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_OPEN_CLOSE_AND_FEDORA44_BUILD
REAL_TARGET_COMPATIBILITY=PASS_API_ABI_AND_LAYOUT_PREREQUISITES
PRODUCTION_RUNTIME_MATERIAL_OWNED_PER_OPEN_EPOCH=true
PRODUCTION_USB_INTERFACE_0_CLAIMED_PER_OPEN_EPOCH=true
PRODUCTION_ACTIVATION_SECURE_GRAPH_WIRED=false
FPRINTD_OPERATIONAL_PATH_PROVEN=false
```

Baseline: `9d601d2db2848b624c6345dd5b2ad545704d6bbd` sul branch `development`, con gate layout D279/07 chiuso
`PASS` sul target Fedora 44 e SELinux `Enforcing`.

## Delta implementato

La sottoclasse USB registrata ora distingue il proprio `img_open` dal shell
virtuale host-only. Nel path production:

1. libfprint apre il `GUsbDevice` prima della vfunc, come imposto dal core
   1.94.100;
2. all'ingresso di `img_open`, il driver carica i cinque path production
   tramite il solo `GoodixRuntimeMaterial` D279/06;
3. conserva owner, secure view non-owning, FDT12 e audit nel medesimo
   `GoodixDeviceContext` della open epoch;
4. soltanto dopo il successo del materiale reclama l'interfaccia USB 0;
5. completa open senza submit, protocollo o TLS.

Il requisito iniziale «materiale prima di USB open» non è compatibile con il
lifecycle standard: `fp_device_open()` chiama direttamente
`g_usb_device_open()` prima della vfunc del driver. La sequenza minima corretta
e target-compatible è quindi `core USB open → material load → interface-0
claim`, con `REAL_USB_SUBMIT=0` fino alla futura activation.

Su `img_close`, cancellation/failure e finalizer, il driver recinta il grafo,
rilascia l'eventuale claim una sola volta, cancella descriptor e FDT locali,
libera l'owner e infine lascia al core la chiusura del `GUsbDevice`. Un nuovo
open sullo stesso `FpDevice` crea un contesto e un owner distinti. Failure di
material load non raggiunge il claim; failure di claim o cancellation dopo il
load libera l'owner; failure di release viene propagato ma non impedisce il
cleanse/free del materiale.

Le seam pubbliche sono esclusivamente punti di iniezione offline per acquire /
free e claim / release. Con callback `NULL`, il path registrato usa sempre i
cinque path D279/07 e le API reali libgusb. Il shell virtuale continua a non
caricare file né chiamare USB.

## Verifiche

La suite `test_goodix_fpimage_device` ora contiene 21 test per build. I tre
test D279/08 provano:

- ordine acquire prima del claim e release prima del free;
- owner e claim presenti per tutta la open epoch;
- due open/close consecutivi sullo stesso oggetto con due owner distinti;
- propagazione e teardown per failure di acquire, claim e release;
- cancellation immediatamente dopo acquire: nessun claim, owner liberato;
- il core USB open precede necessariamente l'acquire e il core close segue il
  teardown del driver.

```text
FPIMAGE_DEVICE_NORMAL=21/21_PASS
FPIMAGE_DEVICE_ASAN_UBSAN=21/21_PASS
D279_08_FOCUSED_FAILURE_NORMAL=PASS
D279_08_FOCUSED_FAILURE_ASAN_UBSAN=PASS
RUNTIME_MATERIAL_NORMAL=9/9_PASS
RUNTIME_MATERIAL_ASAN_UBSAN=9/9_PASS
FEDORA44_LIBFPRINT_1_94_100_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
REGISTERED_USB_ID=27c6:5125_EXACTLY_ONCE
REAL_PRODUCTION_INPUT_READ_BY_AI=false
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
FPRINTD_EXECUTED=false
LIVE_EXECUTION_PERFORMED=false
```

## Limite e prossimo boundary

D279/08 non rende ancora operativo il path fprintd. La activation della
sottoclasse USB usa ancora l'arm host-only e non consuma secure view/FDT per
avviare pre-session RX sync, secure session e post-TLS lifecycle. Il prossimo
delta autonomo deve collegare questi oggetti con seam asincrone e test
sintetici, senza installare il driver né eseguire USB reale.

```text
RESIDUAL_BLOCKER_OR_RISK=PRODUCTION_ACTIVATION_DOES_NOT_START_EXISTING_SECURE_AND_POST_TLS_GRAPH
NEXT_PRIMARY_BOUNDARY=OFFLINE_PRODUCTION_ACTIVATION_SECURE_GRAPH_BINDING
NEXT_LIVE_PREREQUISITE=SEPARATE_OPERATOR_KIT_BASELINE_REVIEW_AND_EXPLICIT_ONE_SHOT_AUTHORIZATION
REVIEW_SET=BASELINE_9d601d2_PLUS_FINAL_DEVELOPMENT_COMMIT_PLUS_D279_08_REPORT_PLUS_LIBFPRINT_DRIVER_DIFF_PLUS_MANUAL
```
