<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/15 — reassembly B0 bounded e delivery ausiliaria opaca

## Esito

Il binding inbound ora accetta chunk plaintext TLS e ricompone esattamente un
messaggio B0 in base alla lunghezza dichiarata, con bound assoluto 8192 byte.
Nel slot primario impone il contratto decoder target-local di 7693 byte,
verifica framing/checksum/CRC tramite `goodix_image_decode_plaintext()` e
inoltra solo il raster canonico. Nel slot ausiliario non applica il decoder:
consegna invece il messaggio completo e invariato a un callback obbligatorio,
poi registra la transizione protocol-internal.

L'uguaglianza osservata in ATTEMPT02 tra le lunghezze wire cifrate dei B0
primari e ausiliari (`7726`) è evidenza compatibile, ma non prova da sola una
lunghezza plaintext universale. Per questo l'ausiliario resta dichiarato-
length e bounded, non fissato a 7693. Non viene formulata alcuna conclusione
sulla sua utilità per quality, template o NBIS.

```text
OUTCOME=READY_OFFLINE_B0_PLAINTEXT_DELIVERY
ADVANCEMENT=BOUNDED_TLS_PLAINTEXT_TO_ITERATIVE_MODEL_PATH
PRIMARY_B0_PLAINTEXT_LENGTH=7693_TARGET_LOCAL_DECODER_CONTRACT
AUXILIARY_B0_MAX_PLAINTEXT_LENGTH=8192
AUXILIARY_B0_CONTENT_DELIVERY=OPAQUE_UNCHANGED_REQUIRED_CALLBACK
AUXILIARY_B0_APPLICATION_SEMANTICS=UNDETERMINED
PRODUCTION_ENROLLMENT_ENABLED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Failure model e verifica

Il buffer viene azzerato dopo consegna o errore e alla distruzione. Chunk
vuoti, overflow, lunghezza nulla, dichiarazione oltre il bound, lunghezza
primaria diversa da 7693, decode primario fallito, callback ausiliario fallito
e qualunque A0/prepare/commit durante un B0 parziale falliscono chiuso. Non
esistono retry automatici.

La regressione divide sia primario sia ausiliario in tre chunk. Il primario
usa un record sintetico CRC-valido; l'ausiliario ha trailer volutamente non
valido come immagine e arriva invariato al callback, provando che non viene
silenziosamente reinterpretato o scartato. Una lunghezza primaria errata è
respinta prima del decode.

```text
D279_14_15_TESTS=5/5_PASS_NORMAL;5/5_PASS_ASAN_UBSAN
FRAGMENTED_PRIMARY_REASSEMBLY=PASS
PRIMARY_IMAGE_DECODE_COUNT=1
FRAGMENTED_AUXILIARY_REASSEMBLY=PASS
AUXILIARY_OPAQUE_DELIVERY_COUNT=1
AUXILIARY_CONTENT_UNCHANGED=PASS
INVALID_PRIMARY_DECLARED_LENGTH=FAIL_CLOSED
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
RETRY_COUNT=0
A0_FRAME_BUILD_COUNT=0
SUBMIT_COUNT=0
EXECUTABLE_CLOSURE=PASS_INBOUND_ONLY_ZERO_SENDER
```

La build production-shaped passa con registry standard e NBIS, senza warning
nuovi nel binding e senza enumerazione/open/claim/submit USB.

## Confine residuo

L'intero percorso inbound post-TLS è ora componibile con il modello iterativo.
Manca il confine outbound: serializzare il comando preparato in A0/fixed64 e
definire un contratto transazionale di submit/ACK, inizialmente verificato solo
con backend sintetico e mantenendo il gate production.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_ENROLLMENT_OUTBOUND_SERIALIZATION_AND_SUBMIT_CONTRACT_WITH_PRODUCTION_GATE
```
