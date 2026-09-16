<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/22 — callback contact enrollment ordinati

## Esito

`GoodixEnrollmentPostTlsEvents` può notificare finger-down/finger-up validati
senza aggiungere un sender. Il callback è opzionale per mantenere riusabile il
modello e deve essere installato prima di qualsiasi input.

```text
OUTCOME=READY_OFFLINE_ORDERED_CONTACT_CALLBACKS
ADVANCEMENT=LIBFPRINT_CONTACT_ORDERING_SEAM
CONFIGURABLE_STAGE_PROFILES=2;3;21
ATTEMPT02_OBSERVED_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
PRODUCTION_ENROLLMENT_ENABLED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Ordering

- IRQ2 strutturalmente valido e accettato dall'adapter precede la notifica
  finger-down;
- ogni IRQ0200 accettato precede la notifica finger-up;
- nello stage terminale l'accettazione IRQ0200 consegna prima il `FpImage`
  primario già decodificato e differito, quindi notifica finger-up;
- l'estrazione libfprint resta asincrona, quindi finger-up può precederne la
  conclusione senza violare lo stato `AWAIT_FINGER_OFF`;
- nessun dato IRQ viene convertito in immagine.

Un callback che rifiuta l'evento causa failure terminale dell'event layer,
preserva l'errore del consumer e non introduce retry.

```text
D279_14_TO_22_TESTS=10/10_PASS_NORMAL;10/10_PASS_ASAN_UBSAN
CONTACT_DOWN_COUNT_PER_PROFILE=REQUIRED_STAGE_COUNT
CONTACT_UP_COUNT_PER_PROFILE=REQUIRED_STAGE_COUNT
TERMINAL_IMAGE_BEFORE_FINGER_UP=PASS
CONTACT_CALLBACK_REJECTION=TERMINAL_FAIL_CLOSED
AUTOMATIC_RETRY_COUNT=0
INBOUND_LAYER_A0_BUILD_COUNT=0
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
```

Il B0 ausiliario continua a essere consegnato completo e invariato al callback
opaco. Questa seam non stabilisce che il payload sia inutile a quality,
template o NBIS; la sua semantica resta non determinata.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_CONTEXT_FIRST_ARM_HANDOFF_TO_PARAMETRIC_ENROLLMENT_GRAPH_ORCHESTRATION_WITH_GATE
```
