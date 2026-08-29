# D278/01 — catena secure-session nativa host-only

```text
OUTCOME=READY_PASS_HOST_ONLY
ADVANCEMENT=NEW_NATIVE_LGPL_SECURE_SESSION_IMPLEMENTATION_AND_HOST_ONLY_EXECUTABLE_EVIDENCE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=NATIVE_SECURE_SESSION_TARGET_PROVEN_FALSE;TARGET_CONFIG90_RAW_MATERIAL_NOT_READABLE_IN_CURRENT_ENVIRONMENT;TARGET_TYPED_RESPONSE_RAW_MATERIAL_NOT_EMBEDDED;GITHUB_ACTIONS_CONFIRMATION_PENDING;NO_LIVE_AUTHORIZATION
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_2a5701620230ef93d677a72dab6013c6cbef7238_PLUS_WORKING_TREE_REVIEW_analysis/D278_AND_LIBFPRINT_DRIVER_D278_FILES_AND_CI_AND_MANUAL
```

## Baseline, scope e risultato

La baseline iniziale era pulita, su `main`, con HEAD esatto
`2a5701620230ef93d677a72dab6013c6cbef7238`. D278/01 non ha enumerato, aperto,
reclamato o contattato il sensore e non ha eseguito il launcher live D277.

La nuova state machine LGPL impone:

```text
A8 -> E4 -> A2_1 -> CHIP_82 -> OTP_A6 -> A2_2 -> MODE_70
-> DAC_220 -> DAC_236 -> DAC_238 -> DAC_23A -> CONFIG_90
-> D1 -> B0/TLS 1.2 PSK -> TLS ESTABLISHED -> STOP
```

Non esistono D4, retry, recovery, reopen o reset nel vocabolario del modulo.
Ogni fase A0 avanza solo dopo il contratto logico completo e dopo il completion
OUT corrispondente. D1 ammette come prima classe soltanto B0; un A0 da D1 in
poi è terminale. Un frame ulteriore dopo `STOP` è respinto e porta al fence
terminale senza emettere comandi.

## Architettura implementata

- `goodix_a0_protocol.[ch]`: codec A0 indipendente con type, length LE16, tag
  esterno, length interno, checksum additivo e coordinata speciale D1
  wire-control `D1` / checksum-control `D0`. I vettori A8, E4 e D1 sono
  byte-exact.
- `goodix_secure_session.[ch]`: state machine ordinata, policy ACK specifica
  per fase, typed-response gates, boundary materiale, integrazione del vero
  `GoodixTlsServer`, coda B0 per record e scheduler pacing generazionale.
- `GoodixDeviceContext`: owner della sessione, del router, del backend e della
  generation; gli A0/B0 del solo reader vengono inoltrati alla sessione. Il
  completion receive ri-arma al massimo un IN fisico finché la sessione lo
  richiede.
- `GoodixFpiUsbBackend`: un solo OUT fisico in flight, completion callback
  generation-captured e drain invariato. Un secondo OUT concorrente è
  respinto, anche nella stessa generation.

Gli A0 sono inviati alla loro lunghezza logica, senza padding del protocol
layer. Ogni record TLS è racchiuso in un B0 distinto, spezzato in submission
fisiche da 64 byte; la tail dell'ultimo chunk è inizializzata a zero. Fra
record B0 distinti il scheduler richiede 10 ms. Il test seam non dorme: registra
l'azione temporale e la rilascia deterministicamente. La produzione usa un
`GSource` cancellabile posseduto dalla sessione, con generation ricontrollata.

## Contratti di risposta e materiali

La policy ACK verificata è:

```text
A8: status 01 oppure 07
E4..90: status esattamente 01
D1: nessun ACK A0
```

I gate typed coprono identity APP12509 esatta, prefisso/validator E4, lunghezza
e SHA-256 indipendenti per A2/82/A6 e body `90=0100`. Il boundary materiale
richiede inoltre quattro DAC correlati alla config, CONFIG_90 da 224 byte con
SHA-256/finalizer/correlazione e PSK lunga esattamente 32 byte prima di poter
creare la sessione.

I pin target canonici restano quelli di D232:

```text
E4=1fa642d3f190e7074d1db201aa32ee8f34e41d69d55797158b9480affb3d0b87
A2=39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5
82=82537d2c108887baef128b47ad401fc888d54b184673b1fc23811d79ab6d5703
A6=d7e81a415aa5e7b0168c9a632756d1dc8b7b47346cc0a44dc68796f854c2b92b
CONFIG90=e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82
CONFIG90_FINALIZER=519a
```

`/var/lib/goodix-5125-poc/target-config-90.bin` non è leggibile nell'ambiente
corrente e i raw response target non vengono incorporati nei test. La prova
host-only usa un validator, risposte, CONFIG_90 e PSK esplicitamente sintetici,
con i quattro valori DAC canonici e tutte le stesse correlazioni/gate. Non
pretende di soddisfare gli hash target.

## Evidenza eseguibile

Runner: `libfprint-driver/tests/run_goodix_d278_secure_session_test.sh`.

Risultato locale di due invocazioni consecutive del runner nell'SDK
Freedesktop 25.08 offline; ciascuna invocazione ha prodotto:

```text
D278 normal:       9/9 PASS
D278 ASAN/UBSAN:   9/9 PASS
LeakSanitizer:     non disponibile sotto il boundary Flatpak/bwrap ptrace;
                   detect_leaks=0, address checks e UBSAN attivi
```

I nove gruppi esercitano vettori/malformed A0; happy path completo con peer
OpenSSL reale; ACK/status/echo/reorder; typed length/hash/prefix; classi A0/B0
inattese; tutti i material gate; single-OUT/stale generation/drain; cancel in
A8/E4/CONFIG_90/D1; completion sincrono del seam; risposta tipizzata duplicata;
PSK e identity errate. La happy path alterna ACK+typed coalesciuti, separati e
frammentati; valida ogni comando uscente in ordine, ricostruisce tutti i B0 dai
chunk fisici, verifica tail zero e rilascia il pacing senza sleep. Una seconda
happy path prova inoltre che il pacing resta attivo quando la telemetria audit
opzionale non viene fornita.

Prova TLS sintetica:

```text
protocol=TLSv1.2
cipher=PSK-AES128-GCM-SHA256
handshake_count=1
secret_handoff_count=1
project_secret_zeroized=true
second_project_secret_handoff_rejected=true
TLS_application_data_required=false
```

Regressioni eseguite dopo la patch:

```text
D276/02 FpImageDevice: 15/15 normal + 15/15 ASAN/UBSAN PASS
D276/03 router:         8/8 normal + 8/8 ASAN/UBSAN PASS
D276/04 TLS/backend:    5/5 normal + 5/5 ASAN/UBSAN PASS
D277 A8 host-only:     15/15 normal + 15/15 ASAN/UBSAN PASS
D277 live harness: build PASS, execution NOT PERFORMED
```

Il workflow `.github/workflows/d276-native-tls-usb-host-only.yml` esegue ora
due volte D278 normal+sanitizer e conserva i gate D276/D277. La conferma GitHub
Actions è `PENDING` perché D278/01 non crea commit né push.

## Safety e provenance

```text
D278_01_HOST_ONLY_RESULT=PASS
NATIVE_SECURE_SESSION_CHAIN_HOST_ONLY_PROVEN=true
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
NATIVE_PRE_D1_SEQUENCE_HOST_ONLY_PROVEN=true
NATIVE_D1_B0_TLS_TRANSITION_HOST_ONLY_PROVEN=true
NATIVE_TLS12_PSK_HANDSHAKE_HOST_ONLY_PROVEN=true
NATIVE_B0_FIXED64_EGRESS_HOST_ONLY_PROVEN=true
NATIVE_TLS_RECORD_PACING_HOST_ONLY_PROVEN=true
D4_REACHABLE=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
CURRENT_LIVE_AUTHORIZED=false
```

I nuovi file LGPL sono espressione locale indipendente basata su fatti neutrali
canonici, vettori D232/D245, API GLib/OpenSSL e API libfprint LGPL. Nessun
codice GPL di `tools/d277_native_a8_once.c`, `src/`, `core/` o Rockytkg è stato
copiato, adattato o tradotto. Il confronto con il serializer storico è stato
usato soltanto come oracle black-box per confermare fatti di framing già
canonizzati.

## Prossimo confine

```text
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_FOR_D278_02_SINGLE_SHOT_NATIVE_SECURE_SESSION_TARGET_VALIDATION
```

Questo non autorizza D278/02. Servono review AI-PM, riesame metodologico
pre-live, nuovo preflight permessi host e nuova autorizzazione esplicita.
