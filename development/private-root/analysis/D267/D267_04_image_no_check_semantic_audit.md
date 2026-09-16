# D267/04 — Audit semantico image `0x88` e corrective condizionale

## Esito

```text
OUTCOME=D267_04_IMAGE_NO_CHECK_SEMANTIC_CORRECTIVE_READY_OFFLINE
SEMANTIC_CORRECTIVE_GATE=PASS
OEM_0X88_SEMANTICS=VERIFIED_NO_CHECK_ADDITIVE
OEM_IMAGE_PATH_APPLICABILITY=VERIFIED_REACHABLE_MAJOR_2_DATA_PLUS_5_LENGTH_MINUS_6
ROCKYTKG_CORROBORATION=YES_NOT_PRIMARY
TARGET_D267_01_TRAILER=UNKNOWN
DECODER_SEMANTIC_CHANGE=YES
DECODER_SEMANTIC_CHANGE_SCOPE=IMAGE_ADDITIVE_CHECKSUM_0X88_ONLY
IMAGE_RECORD_CRC_POLICY_CHANGE=NO
WIRE_CHANGE=NO
EXECUTABLE_CLOSURE=PASS
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

L'audit locale supera il gate: il marker `0x88` è direttamente collegato al
parser del plaintext post-TLS e il medesimo buffer raggiunge il ramo image
`major == 2`. È stato quindi applicato il corrective minimo image-specific.
Questo risultato non ricostruisce il trailer della run D267/01, che non fu
conservato e resta sconosciuto.

## Fonti locali esaminate

- `analysis/D230/work/GoodixExport/gfusb_static_refs/function_18005f098_non_b0_dispatch.txt`
- `analysis/D230/work/GoodixExport/gfusb_static_refs/recv_tls_windows.txt`
- `analysis/D230/work/GoodixExport/gfusb_static_refs/device_parser_windows.txt`
- `analysis/D230/work/GoodixExport/gfusb_static_refs/usb_parser_continuous_18005e840_18005f120.txt`
- `analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt`, necessario
  per seguire senza interruzioni il callback post-TLS e il ramo major 2
- `Rockytkg/PROVENANCE.md` e `Rockytkg/src/goodix_capture.c:223-268`

Gli artefatti D209/D210 non sono presenti nel repository corrente e non sono
re-queryable come evidenza primaria.

## Call-flow e data-flow OEM

```text
USB parser
  0x18005ef1a: major del frame == 0xB
  0x18005efd0: consegna body al TLS engine (0x18003f0a8)
  0x18005efd5: callback application-data 0x1800211c8

callback application-data
  0x180021271..0x18002129e: alloca buffer e ottiene plaintext/lunghezza
                           tramite 0x180058128
  0x1800213f3..0x1800213fd: passa buffer e lunghezza a 0x18005f098

parser 0x18005f098
  0x18005f171..0x18005f21c: estrae control/major/subclass dal byte 0
  0x18005f2d6..0x18005f305: declared length = byte1 | byte2 << 8
  0x18005f3ff..0x18005f44f: copia declared-length byte da buffer+3
  0x18005f4e5..0x18005f4f9: legge payload[declared_length-1]
  0x18005f4fe..0x18005f51f: 0x88 salta il verifier e forza successo
  0x18005f500..0x18005f519: trailer ordinario usa 0x180059390
  0x18005f599..0x18005f653: conserva metadata e puntatore dello stesso buffer
  0x18005f65c..0x18005f710: dispatch sul major (nibble alto control)
  0x18005f76e: ramo major 2
  0x18005f7aa..0x18005f7e5: lunghezza = declared_length - 6;
                           puntatore = payload data + 5
  0x18005f80d..0x18005f81f: consumer callback(record, length)
```

Per il contratto corrente `declared_length=7690`, quindi il ramo major 2
consegna `7690-6=7684` byte a partire dal prefix image +5: esattamente il
record da 7680 byte packed12 più CRC-32/MPEG-2 da 4 byte.

## Classificazione probatoria

| Conclusione | Classe | Base |
| --- | --- | --- |
| Il B0 USB viene consegnato al TLS engine e il plaintext risultante viene passato a `0x18005f098` | VERIFICATO | call-flow continuo `0x18005ef1a → 0x18003f0a8 → 0x1800211c8 → 0x180058128 → 0x18005f098` |
| La lunghezza dichiarata deriva dai byte 1–2 e il payload inizia a byte 3 | OSSERVATO | istruzioni `0x18005f2d6..0x18005f305` e copia `0x18005f3ff..0x18005f44f` |
| `trailer == 0x88` significa no-check per la verifica additiva | VERIFICATO | confronto `0x18005f4f9`; ramo `0x18005f51f` forza successo senza chiamare `0x180059390`; gli altri trailer chiamano il verifier |
| Lo stesso payload viene classificato per major dopo la verifica trailer | VERIFICATO | struct costruita da stesso buffer e dispatch `0x18005f65c..0x18005f710` |
| Il ramo major 2 riceve `data+5` e `declared_length-6` | VERIFICATO | data-flow `0x18005f7aa..0x18005f81f` |
| Il ramo major 2 è applicabile al record immagine 7684 del protocollo corrente | VERIFICATO | major 2, offset +5 e lunghezza 7684 coincidono esattamente col contratto image locale; Rocky corrobora cmd0 2/v19-6 |
| Nome/simbolo esatto del callback OEM in `0x18059faf8` | NON_NOTO | il puntatore indiretto è osservato, ma non è disponibile un simbolo affidabile |
| Il trailer del plaintext D267/01 fosse `0x88` | NON_NOTO | trailer e metadata interni non furono conservati |
| `0x88` sia stata la causa reale di D267/01 | IPOTIZZATO | semanticamente possibile, ma non distinguibile dagli altri predicati persi |

Il parser OEM applica il check prima del dispatch e quindi la semantica è più
generale del solo image. Il corrective locale adotta deliberatamente lo scope
più stretto provato e necessario: solo il percorso image può usare il marker.

## Corroborazione Rockytkg

Lo snapshot locale ha provenance preservata al commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`. In
`Rockytkg/src/goodix_capture.c:223-268`, `parse_image_payload()` richiede cmd0
2, scarta POV `0xAA`, usa `data+5`/`v19-6` e salta la verifica quando il trailer
è `GF_NO_CHECK` (`0x88`). Questo è corroborativo e non è la base primaria del
gate target-specific. Non è stato copiato il successivo comportamento Rocky
che si limita a loggare un CRC record errato.

## Corrective implementato

`core/post_d4.py` conserva `parse_payload()` globalmente strict. Il solo
`parse_image_payload()` esegue, in ordine:

1. header e declared length;
2. classificazione `major == 2`;
3. lunghezza image data e record 7684;
4. rifiuto POV;
5. policy checksum additiva (`0x88` no-check, altrimenti match obbligatorio);
6. CRC-32/MPEG-2 obbligatorio del record;
7. decode raster `80x64`.

La diagnostica metadata-only aggiunge `payload_checksum_policy` con valori
`NOT_REACHED`, `ADDITIVE_VERIFIED` o `NO_CHECK_0X88_ACCEPTED`. Restano
disponibili `payload_trailer_class`, `payload_checksum_match`, `decode_stage`
ed `exception_class`; non vengono registrati raw, plaintext, image bytes,
pixel, raster, secret o hash sensibili.

## Verifica offline e invarianti

La matrice D267/04 10/10 copre additive valido, mismatch ordinario, no-check
`0x88`, CRC errato, major non-image, POV, declared length, record length,
parser generico strict e identità raster della fixture 7693. Le regressioni
mirate passano 66/66 e quelle runtime/wire 39/39. Il dry-run del Kit Operatore
da `/tmp` passa con baseline non approvata, nessuna capability live e tutti i
contatori reali a zero. La discovery completa conserva soltanto le quattro
failure class preesistenti note (1 FAIL, 3 ERROR); nessuna è D267/04.

```text
WIRE_CHANGE=NO
USB_PATH_CHANGE=NO
TLS_PATH_CHANGE=NO
FDT_IRQ_ROUTING_CHANGE=NO
COMMAND_22_CHANGE=NO
ACK_POLICY_CHANGE=NO
B0_OWNERSHIP_CHANGE=NO
RETRY_RECOVERY_CHANGE=NO
PERSISTENT_WRITE_REACHABILITY_CHANGE=NO
DECODER_SEMANTIC_CHANGE=YES
DECODER_SEMANTIC_CHANGE_SCOPE=IMAGE_ADDITIVE_CHECKSUM_0X88_ONLY
IMAGE_RECORD_CRC_POLICY_CHANGE=NO
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

Qualunque futuro test hardware richiede un gate separato: Kit Operatore
dedicato con messaggi/interazione in italiano, nuova baseline esplicitamente
approvata e nuova autorizzazione live. D267/04 non prepara né autorizza tale
esecuzione.
