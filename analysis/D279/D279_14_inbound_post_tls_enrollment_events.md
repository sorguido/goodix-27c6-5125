<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/14 — binding inbound post-TLS enrollment

## Esito

`goodix_enrollment_post_tls_events.[ch]` collega eventi A0 post-TLS completi e
già decifrati all'adapter iterativo, senza introdurre alcun percorso outbound.
Il binding è guidato dall'evento atteso e accetta soltanto:

- ACK B0 con echo esatto e status `0x01`;
- IRQ2 come control `0x32`, IRQ `0x0002`, flags `0x003f`;
- IRQ0100 come control `0x36`, IRQ `0x0100`, flags `0x003f`;
- IRQ0200 come control `0x34`, IRQ `0x0200`, flags zero;
- NAV con la forma OEM no-check target-observed 2417/2410, control esatto
  `0x50`, prefisso body `0x50 0x01` e marker finale `0x88`.

Il raster primario già decodificato e l'osservazione del B0 ausiliario opaco
entrano tramite API separate. Il B0 ausiliario resta protocol-internal nel
modello iniziale, senza alcuna conclusione sul suo possibile ruolo in quality,
template o NBIS.

```text
OUTCOME=READY_OFFLINE_INBOUND_POST_TLS_EVENT_BINDING
ADVANCEMENT=EXECUTABLE_POST_TLS_TO_ITERATIVE_MODEL_BINDING
CONFIGURABLE_STAGE_PROFILES=2;3;21
ATTEMPT02_OBSERVED_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
PRODUCTION_ENROLLMENT_ENABLED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Verifica

La regressione sintetizza frame A0 semanticamente equivalenti, percorre
l'intero lifecycle per 2, 3 e 21 stage e verifica i conteggi target-local:
125 ACK, 21 IRQ2, 20 IRQ0100, 21 IRQ0200, un NAV, 21 B0 primari e 21 B0
ausiliari. Echo errato e flags IRQ errati falliscono chiuso. Test normal e
ASan/UBSan passano; il sorgente inbound non dipende da builder, fixed64,
backend o submit.

```text
D279_14_TESTS=3/3_PASS_NORMAL;3/3_PASS_ASAN_UBSAN
ATTEMPT02_INBOUND_A0_COUNT=188
ATTEMPT02_ACK_COUNT=125
ATTEMPT02_IRQ_COUNT=62
ATTEMPT02_NAV_COUNT=1
WRONG_ACK=FAIL_CLOSED
WRONG_IRQ_FLAGS=FAIL_CLOSED
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
RETRY_COUNT=0
A0_FRAME_BUILD_COUNT=0
SUBMIT_COUNT=0
EXECUTABLE_CLOSURE=PASS_INBOUND_ONLY_ZERO_SENDER
```

La build production-shaped compila il binding con registry standard e NBIS,
senza enumerazione/open/claim/submit USB. Il corrective di review rende
esaustivo lo switch degli ACK: non restano warning nuovi D279/14; gli unici
`switch-enum` sono preesistenti in secure-session/post-TLS.

## Confine residuo

Il callback TLS production consegna chunk plaintext, mentre questo binding
richiede A0 completi o raster già decodificati. Il prossimo step offline deve
aggiungere un reassembler/classifier B0 bounded che decodifichi solo il B0
primario completo e inoltri quello ausiliario come evento opaco, ancora senza
backend o sender.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_B0_PLAINTEXT_REASSEMBLY_AND_TYPED_DELIVERY_ZERO_SENDER
```
