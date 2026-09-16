# D267/03 — Decode observability corrective

## Esito

```text
OUTCOME=READY — D267_03_DECODE_DIAGNOSTIC_CORRECTIVE_READY_OFFLINE
ADVANCEMENT=NEW_OFFLINE_DIAGNOSTIC_CAPABILITY
EXECUTABLE_CLOSURE=PASS
OBSERVABILITY_CHANGE=YES
DECODER_SEMANTIC_CHANGE=NO
WIRE_CHANGE=NO
0X88_DIAGNOSTICALLY_RECOGNIZED=true
0X88_BYPASS_ENABLED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

Lo step è interamente offline. Non sono stati aperti USB, letti secret,
eseguiti TLS/device reali, creati marker, modificato fprintd o raggiunte
famiglie di scrittura persistente.

## Delta implementato

- `core/post_d4.py`: `ImageDecodeDiagnostic` e osservazione metadata-only lungo
  gli stessi predicati preesistenti di `parse_image_payload()`;
- `core/persistent_runtime.py`: conservazione del record sanitizzato dopo il
  decode e prima/dopo la zeroizzazione del plaintext;
- `core/d267_first_image_operator.py`: conservazione di `runtime_audit` anche
  nel report fail-closed;
- `tools/d267_live_first_image_once.py`: esposizione immediata del record nel
  summary e uso del nuovo manifest D267/03 non approvato;
- test D267/03 e regressioni D263/D266 aggiornati;
- manuale canonico aggiornato organicamente.

Il manifest storico `analysis/D266/D266_03_live_critical_manifest.json` non è
stato modificato. Il nuovo `analysis/D267/D267_03_live_critical_manifest.json`
descrive il current live-critical set con `baseline_approved=false`.

## Schema diagnostico sanitizzato

```text
decode_stage
plaintext_length
declared_payload_length
control_or_major_class
is_pov_notification
payload_trailer_class
payload_checksum_match
image_record_length
image_record_crc_match
exception_class
raster_shape_if_success
```

I campi non raggiunti sono `null`. Il record non contiene B0, TLS plaintext,
image bytes, raster/pixel, dati biometrici, PSK/secret o hash di materiale
sensibile. La failure esterna resta
`RuntimeFailure:first_image_decode_failed`; stage e classe interni restano
disponibili nell'audit/report.

## Matrice sintetica

| Caso | Stage/classe distintiva | Esito |
| --- | --- | --- |
| valid 7693-byte frame | `successful_raster_decode`, shape `80x64` | PASS |
| plaintext/envelope troncato | `plaintext_envelope` / `TruncatedFrame` | PASS |
| declared length mismatch | `declared_length` / `LengthMismatch` | PASS |
| control/major inatteso | `control_major` / `UnexpectedControl` | PASS |
| POV notification | `pov_notification` / `UnexpectedEvent` | PASS |
| checksum ordinario errato | `payload_checksum`, trailer `OTHER` | PASS |
| trailer `0x88` errato | `payload_checksum`, trailer `0X88`, `ChecksumMismatch` | PASS |
| image record length 7683 | `image_record_length` / `LengthMismatch` | PASS |
| image record CRC errato | `image_record_crc` / `ImageCrcError` | PASS |

La fixture valida conserva il contratto sintetico noto:
`7693 → declared 7690 → data 7689 → prefix 5 + record 7684 → packed12 7680 +
CRC 4 → 5120 sample → 80x64`.

## Audit `0x88`

- **verificato nel Python corrente**: `parse_payload()` accetta `0x88` solo se
  coincide con il checksum additivo calcolato; il test D267/03 con `0x88`
  forzato fallisce ancora in `ChecksumMismatch:payload_checksum`;
- **osservato nel materiale statico locale**:
  `analysis/D230/work/GoodixExport/gfusb_static_refs/function_18005f098_non_b0_dispatch.txt`
  confronta il trailer con `0x88` e salta la verifica additiva in quel ramo;
- **corroborato da implementazione terza**: Rockytkg commit preservato
  `227eba219fa9e3fbac5bd59aca79f624f67cd11b`,
  `src/goodix_capture.c:248-251`, applica un no-check `0x88` al payload immagine.

DLL/Rockytkg non provano che APP12509 abbia prodotto `0x88` in D267/01. Il
trailer live non fu conservato; l'ipotesi target-specific resta `MEDIUM`.

## Invarianza semantica e wire

I gate sono ancora eseguiti nello stesso ordine e sollevano le stesse classi:
header, declared length, checksum additivo, major image, lunghezza data/record,
POV e CRC-32/MPEG-2. Non esiste alcun ramo di acceptance alternativo.

Le suite mirate/invarianza provano inoltre:

- USB/session policy, TLS ownership e FDT/IRQ routing invariati;
- D4 e physical policy invariati;
- esattamente un `0x22`, payload logico `22 03 00 01 00 84` e fixed64 zero-tail
  operativo invariati;
- ACK `0x22` ancora obbligatoriamente validato;
- primo B0 consumato dallo stesso retained TLS object;
- zero retry/recovery/reopen, zero write persistenti e nessun comando
  post-image vietato;
- plaintext ancora azzerato sul decode failure.

## Eseguibilità e regressione

- matrice/regr. decoder/authority: 56/56 PASS;
- suite di invarianza runtime/router: 39/39 PASS;
- operator dry-run reale da `/tmp`: PASS, tutti i contatori sensor-reaching a
  zero, `BASELINE_APPROVED=false`, `LIVE_AUTHORIZED=false`;
- discovery generale: 314 test, 310 PASS, 1 FAIL e 3 ERROR nelle quattro classi
  storiche D261/pytest già documentate; nessun nuovo failure attribuibile a
  D267/03. `pytest` resta non installato.

## Evidenza residua e decision boundary

Gli artefatti D209/D210 non sono presenti nel repository e non sono
re-queryable; il formato 7693/major image 2 è qui verificato come contratto
sintetico corrente, non come nuova verifica dei raw storici. D267/03 non può
ricostruire il predicato interno della run D267/01 già consumata.

Il prossimo confine è la disponibilità di nuova evidenza prodotta da un path
che includa questa diagnostica, previa review e autorizzazioni separate. Senza
nuova evidenza non cambia la ranking: `0x88` `MEDIUM`, framing/lunghezze e CRC
`MEDIUM-LOW`, control/POV e concatenazione TLS `LOW`.

### Riesame metodologico pre-live

1. **Cosa cambia realmente?** La prossima eventuale run non sarebbe una
   ripetizione opaca: conserverebbe il predicato sanitizzato esatto.
2. **Quale ipotesi viene testata?** Quale classe tra framing/lunghezza,
   checksum/`0x88`, control/POV e CRC ha causato D267/01.
3. **Se fallisse ancora nello stesso punto?** Usare il record diagnostico per
   decidere il corrective di classe; se il record mancasse, fermarsi e
   correggere il plumbing di reporting senza ripetere hardware.

Questo riesame non costituisce approvazione di baseline né autorizzazione live.

`RESIDUAL_BLOCKER_OR_RISK=EXACT_D267_01_INNER_FAILURE_PREDICATE_STILL_UNOBSERVED_WITHOUT_NEW_EVIDENCE`

