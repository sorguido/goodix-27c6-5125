<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/11 — modello enrollment parametrico host-only

## Esito

Il primo delta successivo all'analisi ATTEMPT02 introduce
`goodix_enrollment_model.[ch]`: un oracle C LGPL metadata-only, privo di
backend USB/TLS e di qualunque sender. Il modello riproduce esattamente le tre
forme osservate — prima transizione con NAV, transizioni intermedie ripetute e
transizione terminale senza re-arm — senza modificare il lifecycle D275 né i
vfunc production, dove l'enrollment resta respinto prima di ogni submit.
`goodix_enrollment_pipeline.[ch]` lo compone poi con la pipeline canonica per
costruire e consegnare un `FpImage` soltanto per ciascun B0 primario.

```text
OUTCOME=READY_OFFLINE_MODEL
ADVANCEMENT=MATERIAL_ARCHITECTURAL_ADVANCEMENT
ATTEMPT02_OBSERVED_SUCCESSFUL_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
MODEL_REQUIRED_STAGE_COUNT=EXPLICIT_PARAMETER_MINIMUM_2
PROFILES_TESTED=2,3,21
PRODUCTION_ENROLLMENT_ENABLED=false
SENSOR_REACHING_CODE_CHANGED=false
PRIMARY_FPIMAGE_DELIVERY_PROFILES=2,3,21
AUXILIARY_B0_FPIMAGE_DELIVERY_COUNT=0
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Contratto

Il callback di avanzamento viene emesso soltanto dopo la sequenza primaria
`IRQ2 → 0x22 → ACK → primary B0`. Ogni stage deve poi chiudere la propria
transizione prima che il modello accetti il successivo IRQ2. Nel profilo
ATTEMPT02:

1. lo stage 1 usa `0x34/IRQ0200 → 0x20/B0 → 0x32 → 0x50/NAV → 0x32`;
2. gli stage intermedi usano
   `0x34 → 0x36/IRQ0100 → 0x20/B0 → 0x34/IRQ0200 → 0x32`;
3. lo stage configurato come ultimo usa la stessa forma ripetuta, ma termina a
   IRQ0200 senza re-arm.

Un evento fuori ordine rende terminale l'istanza e non introduce retry. Il
minimo di due stage non è una legge OEM: è il limite del solo profilo modellato,
che necessita sia della forma iniziale sia di quella terminale osservata. Il
conteggio richiesto resta sempre un input esplicito; il modulo non contiene un
default nascosto pari a 21.

Il B0 cifrato successivo a `0x20` è contato e consumato come transizione
protocol-internal, ma non genera callback stage. Questa classificazione non
stabilisce che il suo contenuto sia inutile: eventuali ruoli in quality,
template o NBIS rimangono non determinabili dalla capture cifrata.

## Verifica ed executable closure

`tests/run_goodix_d279_11_enrollment_model_test.sh` compila il modulo con
warning strict e lo esegue normal e ASan/UBSan nell'SDK Freedesktop già
qualificato, senza rete. I sei casi coprono profili 2/3/21, separazione del B0
ausiliario, mismatch fail-closed con diagnostica expected/actual, rifiuto del
callback con e senza `GError`, stabilità dell'audit dopo completion e rifiuto
di una configurazione che inventerebbe una forma single-stage non osservata.
L'audit sorgente e simboli esclude dipendenze USB, TLS, core GPL e sender.
Quattro casi ulteriori costruiscono e consegnano 2/3/21 sequenze di veri
`FpImage`, rifiutano un raster associato al B0 ausiliario, propagano il failure
del consumer e provano che un primary fuori ordine non alloca alcuna immagine.
La build production-shaped Fedora 44 compila entrambi i moduli contro
libfprint 1.94.100 con NBIS e mantiene registry e zero-enumeration verdi.

```text
D279_11_TESTS=6/6_PASS_NORMAL;6/6_PASS_ASAN_UBSAN
D279_11_FPIMAGE_TESTS=4/4_PASS_NORMAL;4/4_PASS_ASAN_UBSAN
CONFIGURABLE_STAGE_PROFILES=PASS_2_3_21
PRIMARY_B0_LIBFPRINT_STAGE_ACCOUNTING=PASS
AUXILIARY_B0_STAGE_ACCOUNTING=ZERO
UNEXPECTED_EVENT_FAIL_CLOSED=PASS
EXECUTABLE_CLOSURE=PASS_HOST_ONLY_ZERO_SENDER
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
REAL_TARGET_COMPATIBILITY=PASS_BUILD_API_ABI_ONLY
```

## Confine residuo

Il modello non decodifica payload, non genera comandi e non decide la
configurazione production del numero di stage. La seam consegna veri oggetti
`FpImage`, ma non attraversa ancora la state machine enrollment completa di
`FpImageDevice` né l'estrazione NBIS. Il successivo passo offline è quindi una
fixture framework completa e parametrica, mantenendo il gate production.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_PARAMETRIC_FPIMAGEDEVICE_NBIS_ENROLLMENT_FIXTURE
```
