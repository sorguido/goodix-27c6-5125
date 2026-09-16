# D267/02 — localizzazione offline di `first_image_decode_failed`

## Esito

```text
OUTCOME=D267_02_DECODE_FAILURE_BOUNDED_BUT_NOT_LOCALIZED
ADVANCEMENT=LIVE_IRQ2_0x22_B0_BOUNDARY_PROVEN_DECODE_FAILURE_BOUNDED_OFFLINE
EXECUTABLE_CLOSURE=PASS_FOR_POST_LIVE_ANALYSIS
READY_FOR_DECODE_CORRECTIVE_REVIEW=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

Il punto software che emette la failure è localizzato esattamente; non è
invece recuperabile dall'evidenza disponibile quale dei predicati interni del
parser sia fallito. Il runtime appiattisce deliberatamente ogni eccezione di
`parse_image_payload()` nello stesso
`RuntimeFailure("first_image_decode_failed")` senza conservarne tipo, stage o
metadata sanitizzati.

## Call-chain production completa

1. `operator_kit/d267-first-image-once.sh` risolve la Git root e invoca
   `tools/d267_live_first_image_once.py` con il solo flag live esatto.
2. `tools/d267_live_first_image_once.py:275-316` verifica lo SHA, crea
   `D267ProductionDependencies` e chiama
   `run_d267_first_image_candidate()`.
3. `core/d267_first_image_operator.py:360-426` consuma l'intent, attraversa i
   guardrail, crea il coordinator e chiama
   `PersistentRuntimeCoordinator.run(terminal_mode=STOP_AFTER_FIRST_IMAGE)`.
4. `core/d267_first_image_operator.py:230-254` costruisce
   `CtypesLibusbBackend -> LibusbRuntimeTransport -> SharedFrameRouter ->
   _RouterEventSource -> PersistentRuntimeCoordinator`.
5. `core/persistent_runtime.py:243-280` mantiene una sola sessione USB/TLS,
   completa cold-start, handshake, D4, AF e fresh-FDT, quindi entra in
   `_run_first_image_terminal_boundary()`.
6. `core/persistent_runtime.py:378-426` riceve IRQ2, invia esattamente un
   `0x22 [01 00]` fixed64 zero-tail e valida l'ACK.
7. `core/persistent_runtime.py:428-436` riceve il primo frame command-side,
   valida outer B0 e passa il solo body TLS a
   `application_session.consume_application_record()`.
8. `core/tls_b0.py:109-135` alimenta l'input BIO della sessione già
   handshaked, autentica/decritta e restituisce un `bytearray` plaintext non
   vuoto.
9. `core/persistent_runtime.py:437-444` passa
   `bytes(plaintext)` a `core.post_d4.parse_image_payload()`. Qualunque
   eccezione viene catturata, il buffer mutabile è azzerato e nasce
   `RuntimeFailure:first_image_decode_failed`.
10. `core/post_d4.py:347-356` applica framing/payload/image guards e delega il
    record a `decode_image_record()`; quest'ultimo chiama l'unico codec
    `src/goodix5125_cleanroom.py:72-85`.

Il valore passato al decoder non è il frame B0 intero né il TLS ciphertext:
è il plaintext applicativo restituito dalla stessa `SSLObject` retained.
Poiché una failure TLS avrebbe prodotto
`RuntimeFailure:first_image_b0_consumption_failed`, la failure osservata
implica, per call-flow della baseline eseguita, che outer B0 e consumo TLS
abbiano superato i loro gate e che sia esistito plaintext non vuoto. Questa è
un'inferenza code+live, non un dump del plaintext.

## Predicato esatto e formato atteso

La fixture che passa ha esattamente questa struttura:

```text
plaintext applicativo totale = 7693 byte
  control                     = 1 byte, cmd0 == 2
  declared v19                = 7690 (little-endian)
  data                        = 7689 byte
    image metadata prefix     = 5 byte, data[0] != 0xAA
    image record              = 7684 byte
      packed12                = 7680 byte
      CRC-32/MPEG-2 trailer   = 4 byte
  additive checksum           = 1 byte
raster risultante             = 5120 sample u16 = 80x64
```

`first_image_decode_failed` nasce se **qualsiasi** eccezione attraversa il
seguente blocco:

```text
try:
    raster = parse_image_payload(bytes(plaintext))
except Exception:
    zeroize(plaintext)
    raise RuntimeFailure("first_image_decode_failed")
```

Nel normale dominio del parser, le condizioni bounded sono:

| Stage | Predicato di rifiuto | Eccezione interna oggi scartata |
| --- | --- | --- |
| payload header | plaintext più corto di 4 byte | `TruncatedFrame:payload_header_truncated` |
| declared length | `declared < 1` oppure `len != declared + 3` | `LengthMismatch:payload_length:*` |
| payload checksum | trailer diverso dal checksum additivo calcolato | `ChecksumMismatch:payload_checksum` |
| image control | high nibble del control diverso da `2` | `UnexpectedControl:not_image:*` |
| image data size | `len(data) != 5 + 7684` | `LengthMismatch:image_payload_data_length:*` |
| POV guard | `data[0] == 0xAA` | `UnexpectedEvent:pov_notification_not_image` |
| record CRC | CRC-32/MPEG-2 dei primi 7680 byte diverso dal trailer | `ImageCrcError:image_crc` |

Il record-length gate del codec è ridondante sul path corrente dopo il gate
`len(data)==7689`: `data[5:]` misura necessariamente 7684 byte. Il failure
live è quindi ristretto ai gate della tabella, ma l'esatto row non è
registrato.

## Fixture/replay versus live

| Proprietà | Fixture/replay che passa | D267 live osservabile | Stato |
| --- | --- | --- | --- |
| outer B0 presente | synthetic boundary e capture APP12509 D263 | `FIRST_B0_COUNT=1` | live proven |
| TLS application plaintext prodotto | fixture identity TLS; adapter OpenSSL testato offline | inferito dalla failure successiva al distinct TLS-consumption catch | inferred, bytes non disponibili |
| outer B0 length | capture primaria storica: 7726 byte | non registrata | unknown live |
| plaintext length | 7693 byte | non registrata | unknown live |
| declared `v19` | 7690 | non registrato | unknown live |
| control high nibble | `2` (`0x20` fixture) | non registrato | unknown live |
| image metadata prefix | 5 byte, primo byte non `0xAA` | non registrato | unknown live |
| payload checksum | checksum additivo strict | non registrato | unknown live |
| image record length | 7684 byte | non registrata | unknown live |
| record CRC | PASS su fixture sintetica | non registrato | unknown live |
| raster | 5120 sample, `80x64` | `NOT_REACHED` | open |

La capture Windows APP12509 prova l'envelope B0/TLS da 7726 byte ma è cifrata;
non fornisce il plaintext D267. D255 non dispone del plaintext B0 nel confine
user-readable. Nessuna capture/replay versionata contiene quindi i byte
decrittati della run D267.

## Probe meccanico offline

Un micro-script temporaneo, non versionato e synthetic-only, ha verificato:

```text
valid plaintext length 7693 -> PASS, 5120 sample
stessa fixture con trailer payload forzato a 0x88 -> ChecksumMismatch:payload_checksum
record raw 7684 passato come payload -> LengthMismatch
outer B0 sintetico intero passato come payload -> LengthMismatch
payload troncato -> LengthMismatch
```

Ciò dimostra i confini del parser, non quale forma abbia avuto il plaintext
live.

## Ipotesi bounded ordinate

### H1 — mismatch della policy checksum/no-check (confidence: MEDIUM)

- `evidence_for`: `parse_payload()` Python è strict; la DLL locale
  `function_18005f098_non_b0_dispatch` accetta esplicitamente trailer `0x88`
  senza checksum additivo; `Rockytkg/src/goodix_capture.c` applica la stessa
  eccezione ai payload immagine; il probe prova che una fixture altrimenti
  valida con `0x88` fallisce esattamente dentro l'envelope osservato.
- `evidence_against`: D249 aveva consapevolmente escluso un bypass globale
  perché allora mancava prova che il subset immagine APP12509 lo usasse; il
  trailer D267 non è stato registrato.
- `missing_discriminating_evidence`: categoria del trailer live
  (`0x88`/checksum calcolato/altro) e booleano checksum valido, senza esporre
  byte del frame.

### H2 — mismatch di framing/header/lunghezza del plaintext (confidence: MEDIUM-LOW)

- `evidence_for`: il parser richiede esattamente 7693 byte, `v19=7690` e data
  7689; ogni variante viene appiattita nella failure osservata.
- `evidence_against`: la capture primaria storica da 7726 byte è coerente con
  il payload immagine atteso e il medesimo target/firmware; il percorso passa
  il body TLS, non il B0 intero.
- `missing_discriminating_evidence`: plaintext length, declared length,
  control nibble e numero di payload logici estratti.

### H3 — CRC-32/MPEG-2 del record live non conforme al codec corrente (confidence: MEDIUM-LOW)

- `evidence_for`: è l'ultimo gate reale dopo framing e qualunque mismatch
  produce la stessa failure; il test con record corrotto riproduce l'envelope.
- `evidence_against`: codec, ordine trailer, packed12 e transpose passano tutte
  le fixture/KAT; DLL/Rocky corroborano il formato 7684/7680+4 per type 12.
- `missing_discriminating_evidence`: booleano sanitizzato `record_crc_match`
  e record length, senza bytes/hash/pixel.

### H4 — control non-image o POV notification nel primo plaintext (confidence: LOW)

- `evidence_for`: entrambi sono rifiuti espliciti del parser.
- `evidence_against`: il frame segue IRQ2, `0x22` accettato e il primo B0 nella
  sequenza target storica è un'immagine; nessun fatto live ne registra però il
  control decrittato.
- `missing_discriminating_evidence`: sola classe sanitizzata
  `control_cmd0` e `pov_marker_present`.

### H5 — più payload plaintext concatenati da una singola feed TLS (confidence: LOW)

- `evidence_for`: l'adapter concatena ogni chunk restituito da `SSLObject.read`
  prima di chiamare un parser che accetta esattamente un payload.
- `evidence_against`: viene alimentato un solo B0/TLS record e la capture
  storica rappresenta un solo payload immagine in quel record.
- `missing_discriminating_evidence`: plaintext total length e conteggio
  bounded dei payload dichiarati.

L'ipotesi «il decoder riceve il B0 intero» è invece smentita dalla call-chain:
`parse_outer()` rimuove i quattro byte Goodix e il TLS consumer restituisce
plaintext prima della chiamata al parser immagine.

## Evidenza mancante e prossimo passo offline

Per scegliere una causa serve il metadata sanitizzato della run già consumata:

```text
inner_exception_class
decoder_stage
plaintext_length
declared_payload_length
control_cmd0
pov_marker_present
payload_trailer_is_0x88
payload_checksum_match
image_record_length
record_crc_match
```

Il report protetto corrente, anche se divenisse leggibile, è costruito dal
codice che conserva soltanto `failure_class`; non risulta che contenga questi
campi. Non esiste quindi evidenza offline capace di ricostruirli a posteriori.

`PROPOSED_OFFLINE_CORRECTIVE`: in uno step separato e revisionabile, sostituire
l'`except Exception` opaco con diagnostica tipizzata e sanitizzata per stage,
aggiungere fixture per checksum computato e marker `0x88`, lunghezze/header,
POV e CRC, e confrontare la policy image-specific con DLL/Rocky. Non cambiare
ancora il decoder né autorizzare live: prima va deciso da Utente+AI-PM quale
correttivo offline è giustificato.
