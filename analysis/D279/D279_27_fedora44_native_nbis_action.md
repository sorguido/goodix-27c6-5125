<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/27 — action enrollment con NBIS nativo Fedora 44

## Esito

```text
D279_27_OUTCOME=READY_OFFLINE_NATIVE_NBIS_ACTION
D279_27_BASELINE=ed7e5870a0db924b1087a9afaa920d822aa34b9c
TARGET_LIBFPRINT_VERSION=1.94.100
EXTRACTOR=NBIS_NATIVE
LIBFPRINT_ACTION_STAGE_COUNT=21
LIBFPRINT_PROGRESS_COUNT=21
LIBFPRINT_COMPLETION_COUNT=1
NBIS_MIN_MINUTIAE_IN_SYNTHETIC_FIXTURE=3
NORMAL_AND_ASAN_UBSAN=PASS
PRODUCTION_USB_REACHED=false
TARGET_BIOMETRICALLY_VALIDATED=false
LIVE_EXECUTION_PERFORMED=false
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_EXACT_TARGET_NATIVE_NBIS_ACTION
```

## Confine chiuso

La build esatta Fedora 44/libfprint 1.94.100 compila un test dedicato insieme
al driver registrato `goodix_27c6_5125`, al core target e alla libreria NBIS
statica target. Il test usa esclusivamente
`goodix_fpimage_device_new()`, cioè la classe virtuale host-only, e percorre
una vera `fp_device_enroll()` a 21 stage.

Per ogni stage il percorso osservato è:

```text
u16 Goodix 80x64
  -> goodix_fpimage_pipeline_new()
  -> FpImage target
  -> fpi_image_device_image_captured()
  -> fp_image_detect_minutiae()
  -> NBIS get_minutiae()
  -> FPI_PRINT_NBIS / XYT
  -> progress callback
```

La action produce 21 progress consecutivi, un solo completion callback, un
template finale `FPI_PRINT_NBIS` con 21 sample e ritorna `INACTIVE` prima del
close. La fixture ridotta produce tre minutiae per sample: questo è sufficiente
per dimostrare l'esecuzione e l'ownership del percorso, non la soglia di
matching né la qualità del sensore.

Il test rispetta l'ordine asincrono già modellato dal transcript D279/26:
release tail e finger-off precedono il risultato NBIS. Una prima versione del
solo test attendeva invece NBIS mantenendo il dito presente e ha raggiunto il
warning target `Deactivating image device while it is not idle` al ventunesimo
stage. Nessun codice runtime è stato cambiato per correggerlo; la fixture è
stata riallineata all'ordine production-shaped già esistente.

## Fixture e limiti probatori

L'input è `examples/prints/whorl.png` della reference libfprint, dichiarato
public domain da `examples/prints/README`. Cairo lo riduce deterministicamente
a 80x64 e il test lo rimappa nel dominio u16 0..4095 prima di attraversare
l'adapter Goodix reale.

Questa scelta verifica la meccanica NBIS sul formato e sulle dimensioni del
target, ma non è un'acquisizione APP12509. Non prova quindi:

- densità o qualità delle minutiae del sensore reale;
- polarità/orientamento naturale;
- successo del futuro enrollment live;
- FAR/FRR, matching o sufficienza Bozorth3 (la fixture ha meno di 10 minutiae);
- utilità biometrica dei B0 ausiliari.

`TARGET_BIOMETRICALLY_VALIDATED` resta pertanto `false` e tali incertezze sono
ormai hardware/biometriche, non risolvibili aggiungendo altre fixture host.

## Isolamento e safety

Il runner usa il Freedesktop SDK 25.08 con rete disabilitata. Un gate sorgente
respinge il test se compare `goodix_fpimage_device_new_for_usb`, una API GUsb o
enumerazione `FpContext`; il solo constructor ammesso è quello virtuale.
Nessuna USB reale viene enumerata, aperta, claimed o raggiunta.

Le deadline da 15/45 secondi delimitano esclusivamente un hang del processo
host offline. Non attestano e non implicano timeout o quiescenza device-side
dopo un'interruzione live.

Verifiche eseguite:

```text
./libfprint-driver/tests/run_goodix_fedora44_nbis_action_test.sh
D279_27_FEDORA44_NATIVE_NBIS_ACTION=PASS
D279_27_NORMAL_AND_ASAN_UBSAN=PASS
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
```

Le regressioni complete `run_goodix_fpimage_device_test.sh` (27/27 normale e
27/27 ASan/UBSan), `run_goodix_d279_11_enrollment_model_test.sh` e
`run_goodix_fedora44_registration_test.sh` restano verdi. Il gate production
enrollment e l'assenza di caller production della seam di configurazione non
sono cambiati.

## Confine successivo

Il prossimo e ultimo delta implementativo prima della review live-critical è
il binding minimo dell'action enrollment al percorso USB production per una
sola action per open epoch, senza retry né seconda action e con close terminale
su qualunque esito. D279/27 non abilita tale gate.

Multi-action nello stesso open epoch, reactivation, verify/fprintd e packaging
di sistema restano deliberatamente post-live.
