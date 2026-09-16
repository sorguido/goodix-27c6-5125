# D279/33 — composer ATTEMPT02 TLS → raster, chiusura sintetica

## Obiettivo

Comporre, senza leggere la PSK target e senza aggiungere un loader di secret,
l'audit hash-gated D279/31, la primitive TLS D279/32 e il decoder immagine
canonico locale. Il confine deve essere eseguibile sinteticamente e deve
rifiutare qualunque deviazione dal profilo TLS 1.2 pure-PSK non-EMS osservato
in ATTEMPT02.

## Implementazione

`d279_33_attempt02_in_memory_composer.py`:

- richiama l'audit D279/31 prima di estrarre i record reali;
- richiede esplicitamente assenza di EMS in ClientHello e ServerHello;
- ricostruisce il transcript dai quattro messaggi handshake in chiaro;
- fissa Finished client/server a sequence 0 e application-data client a
  sequence 1..43;
- autentica entrambe le Finished prima di rendere disponibili i plaintext;
- richiede 43 record application da 7717 byte e plaintext da 7693 byte;
- usa direttamente `core/post_d4.py::parse_image_payload` per checksum, CRC,
  unpacking 12-bit e mapping canonico 80×64;
- azzera su `close()` i `bytearray` plaintext e gli `array('H')` raster owned.

L'API richiede una PSK caller-owned mutabile e non la azzera: la futura
composizione con un loader protetto dovrà definire separatamente ownership,
lettura e cleanup del secret. Non esiste CLI, path di secret, export raster o
invocazione NBIS. Le copie interne/transitorie di Python e OpenSSL non sono
dichiarate provabilmente azzerate; l'esecuzione autentica dovrà inoltre essere
short-lived e non persistente.

## Verifica

La suite combinata D279/31–33 passa 11/11 test:

- il pcap ATTEMPT02 autentico viene validato ed estratto solo fino ai record
  cifrati, senza PSK e senza decrittazione;
- una sessione classic/non-EMS con PSK sintetica verifica entrambe le Finished,
  decifra due application record, valida due payload da 7693 byte e ottiene i
  raster canonici 80×64 attesi;
- una Finished server alterata fallisce chiusa;
- una PSK immutabile è respinta;
- close idempotente azzera i buffer owned.

```text
OUTCOME=READY_OFFLINE_ATTEMPT02_IN_MEMORY_COMPOSER
ADVANCEMENT=MATERIAL_EXECUTABLE_COMPOSITION_BOUNDARY
EXECUTABLE_CLOSURE=PASS_SYNTHETIC_AND_HASH_GATED_REAL_STRUCTURE
TESTS_D279_31_THROUGH_D279_33=11/11_PASS
REAL_CAPTURE_STRUCTURE_PARSED=true
TARGET_PSK_ACCESSED=false
ATTEMPT02_RECORDS_DECRYPTED=0
REAL_RASTER_DECODED=0
LIVE_OR_USB_ACTION_COUNT=0
SECRET_LOADER_PRESENT=false
RASTER_OR_TEMPLATE_EXPORT_PRESENT=false
PYTHON_OPENSSL_INTERNAL_COPY_ZEROIZATION_PROVEN=false
RESIDUAL_BLOCKER_OR_RISK=NBIS_VARIANT_EVALUATOR_AND_PROTECTED_INPUT_OPERATOR_BOUNDARY_NOT_YET_CLOSED
CANONICAL_DOCUMENTATION=GOODIX_MANUAL_D279_33
REVIEW_SET=GIT_NATIVE
```

## Confine successivo

Il prossimo step offline è un evaluator NBIS esatto Fedora 44/libfprint
1.94.100 con trasformazioni esplicite e output solo aggregato. Deve chiudersi
su raster sintetici e integrarsi con questo composer senza introdurre loader o
accesso al materiale protetto. Solo dopo review sarà corretto preparare il
percorso operatore separato per l'analisi autentica in memoria.

