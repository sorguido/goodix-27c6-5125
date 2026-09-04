<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/03 — registrazione USB production Fedora 44/libfprint 1.94.100 con NBIS

## Esito

```text
D279_03_OUTCOME=READY
ADVANCEMENT=MATERIAL_ARCHITECTURAL_OR_REPOSITORY_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS_OFFLINE
PRODUCTION_USB_ID_27C6_5125_REGISTERED=true
LIBFPRINT_1_94_100_PRODUCTION_SHAPED_BUILD=PASS
EXTRACTOR_DECISION=NBIS
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
FPIMAGE_PPMM_ASSIGNED=false
NBIS_BIOMETRICALLY_VALIDATED=false
FPRINTD_OPERATIONAL_PATH_PROVEN=false
CURRENT_LIVE_AUTHORIZED=false
```

D279/03 chiude il boundary di registrazione e build lasciato da D279/02. Non
chiude ancora open/claim, acquisizione tramite fprintd o validazione biometrica.

## Baseline e scope

```text
branch=development
D279_03_BASELINE=3c8b846c4dd0ffbb493f11590f3c5d6c7f647692
origin/development=3c8b846c4dd0ffbb493f11590f3c5d6c7f647692
initial_worktree=CLEAN
TARGET_OS=Fedora_44_x86_64
TARGET_LIBFPRINT_VERSION=1.94.100
TARGET_LIBFPRINT_REFERENCE=reference/libfprint-fedora44-1.94.100/source
REAL_TARGET_COMPATIBILITY_GATE=PASS
```

Il task è interamente offline. Non ha installato la libreria, aperto USB,
contattato fprintd, letto materiale protetto o eseguito comandi sensor-reaching.
La closure D278/14 non è stata riaperta.

## Delta implementato

Il registry standard libfprint genera ora il tipo
`fpi_device_goodix_27c6_5125_get_type()` da `supported_drivers`. Il relativo
`FpIdEntry` contiene soltanto `27c6:5125` e il terminatore; non modifica né
confligge con la tabella `goodixmoc`.

Il tipo registrato è la sottoclasse USB già introdotta e provata durante
D278/14. Essa riusa la stessa istanza `GoodixDeviceContext`, lo stesso backend,
router, TLS e lifecycle della classe canonica: non sono stati creati registrar,
stack USB o state machine paralleli. La classe base resta virtuale e disponibile
solo ai test host-only.

Il target 1.94.100 compila i sorgenti canonici da `libfprint-driver/` con
`GOODIX_LIBFPRINT_1_94_100_NBIS`: questo omette esclusivamente la riga SIGFM,
assente nell'API target. Non porta SIGFM, OpenCV o nuovi tipi print. La
dipendenza OpenSSL già usata dal TLS nativo è dichiarata tramite l'helper Meson
esistente.

Il gate locale `goodix_fpimage_pipeline_check_ppmm_requirement()` restituisce
ora `OK` per NBIS in coerenza con D279/02. Lo stato semantico resta
`GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN` e nessun valore viene scritto in
`FpImage::ppmm`: la quality radius non è fisicamente calibrata, ma non blocca
extract/match nel call-flow 1.94.100.

## Verifica production-shaped

Il runner riproducibile è:

```text
libfprint-driver/tests/run_goodix_fedora44_registration_test.sh
```

Usa il Freedesktop SDK 25.08 senza rete. Poiché sull'host Fedora è installato
`libgusb-0.4.9` ma non `libgusb-devel`, il runner fornisce soltanto le
dichiarazioni ABI necessarie e collega il vero `/usr/lib64/libgusb.so.2.0.10`.
Questa è una limitazione ambientale del build host, non uno stub runtime nel
prodotto. I target verificati sono la libreria condivisa `fprint-2` e
`fprint-list-supported-devices`; la generazione GIR completa richiederebbe
anche `GUsb-1.0.gir`, non installato.

Verifiche passate:

- configurazione Meson della reference esatta con
  `-Ddrivers=goodix_27c6_5125`;
- compilazione del core NBIS, dei sorgenti Goodix canonici, di
  `libfprint-2.so.2.0.0` e del tool registry;
- presenza della macro NBIS target nelle compile commands;
- presenza del simbolo `fpi_device_goodix_27c6_5125_get_type` nella libreria;
- registry generato con un solo tipo Goodix target;
- output esatto `27c6:5125 | Goodix 27c6:5125 Fingerprint Sensor` una volta;
- test pipeline D270/D279 e suite `FpImageDevice` normale + ASan/UBSan;
- regressione offline dei guardrail del workflow D278/14;
- `git diff --check`.

La build segnala warning `-Wswitch-enum` storici nelle state machine Goodix; non
sono nuovi, non sono errori e non riguardano registrazione/API target.

## Safety e limiti della closure

```text
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
REAL_SECRET_READ_COUNT=0
FPRINTD_CONTACT_COUNT=0
LIVE_EXECUTION_PERFORMED=false
PERSISTENT_DEVICE_WRITE_COUNT=0
FACTORY_STATE_MUTATION=0
WIRE_PROTOCOL_SEMANTICS_CHANGED=false
SECOND_USB_BACKEND_CREATED=false
SECOND_USB_ROUTER_CREATED=false
SECOND_TLS_STACK_CREATED=false
CUSTOM_PARALLEL_DRIVER_REGISTRY_CREATED=false
```

La registrazione e la build non equivalgono a operatività production. La
callback `img_open` corrente conserva ancora il comportamento host-only e non
lega autonomamente il `GoodixDeviceContext` al lifecycle protetto completo.
Pertanto non è autorizzata alcuna installazione o prova fprintd/live sulla base
di questo step.

```text
RESIDUAL_BLOCKER_OR_RISK=PRODUCTION_FPIMAGEDEVICE_OPEN_CLOSE_MUST_BIND_THE_EXISTING_D278_CONTEXT_TO_USB_CLAIM_PROTECTED_MATERIAL_AND_SECURE_SESSION_WITHOUT_OPERATOR_HARNESS_OR_DUPLICATE_STACK
NEXT_PRIMARY_BOUNDARY=OFFLINE_FEDORA44_FPIMAGEDEVICE_PRODUCTION_OPEN_CLOSE_BINDING_DESIGN_AND_IMPLEMENTATION
```

## Review AI-PM

La review separata ha riesaminato diff, Meson target, registry generato,
metadata della sottoclasse USB, gate NBIS/ppmm, provenance, guardrail D278 e
claim documentali. Il limite tra registrazione compilabile e lifecycle fprintd
ancora non operativo è esplicito; non sono emersi scope creep, stack duplicati
o claim live non provati.

```text
D279_03_AI_PM_REVIEW=PASS
D279_03_CORRECTIVE_REQUIRED=false
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_3c8b846c4dd0ffbb493f11590f3c5d6c7f647692_PLUS_CURRENT_DEVELOPMENT_DIFF_PLUS_analysis/D279/D279_03_offline_fedora44_production_usb_registration_NBIS.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_docs/LICENSING_AND_PROVENANCE.md_PLUS_LIBFPRINT_DRIVER_AND_TARGET_MESON_FILES
```
