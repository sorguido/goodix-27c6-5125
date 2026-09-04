<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/05 — reader privato degli input runtime

## Esito

```text
D279_05_OUTCOME=READY
ADVANCEMENT=NEW_PRODUCTION_FILESYSTEM_BOUNDARY_IMPLEMENTED
EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_FILES
PRIVATE_INPUT_READER_LGPL=true
OUTPUT_PUBLICATION=ATOMIC_AFTER_BOTH_INPUTS_VALIDATE
AUTHENTIC_PROTECTED_INPUTS_EXECUTED=false
CURRENT_LIVE_AUTHORIZED=false
```

Sulla baseline D279/04 `8f11ad0997451ff1ce06f8daf8dabe41f694cca8`,
D279/05 collega i provider PE/FDT a un reader read-only fail-closed di due path
espliciti. Non sceglie path d'installazione, non legge i tre input
PSK/CONFIG/manifest e non modifica ancora `img_open`.

## Contratto implementato

`goodix_runtime_extract_inputs_from_files()`:

- accetta esclusivamente un path PE e un path cache forniti dal caller;
- richiede regular file con uid, mode `0600` e size esatti;
- usa `O_RDONLY|O_CLOEXEC|O_NOFOLLOW`;
- confronta `dev`, `ino`, size, mtime nanosecond, uid e mode via `fstat` prima
  e dopo la lettura;
- valida prima il PE, poi la cache, senza pubblicare output parziali;
- azzera tutti gli output su ogni failure;
- cancella esplicitamente ogni buffer PE/cache allocato;
- non ricerca directory, non segue symlink e non possiede API di write.

La policy production impone uid 0/mode 0600 e size PE 5.771.496; la policy di
test sostituisce solo l'uid con quello corrente per file sintetici temporanei.
I path production restano intenzionalmente non scelti.

## Verifica

`libfprint-driver/tests/run_goodix_runtime_inputs_test.sh` esegue ora sette
test normali e sette ASan/UBSan. Oltre ai cinque D279/04, verifica:

- roundtrip atomico da due file sintetici mode 0600;
- mutazione metadata tramite seam post-read, rifiutata con output tutti zero e
  buffer allocato osservato come cancellato.

```text
D279_05_RUNTIME_INPUTS_NORMAL=PASS
D279_05_RUNTIME_INPUTS_ASAN_UBSAN=PASS
REAL_PRODUCTION_SECRET_READ=false
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
```

La successiva build Fedora 44 production-shaped compila lo stesso sorgente.
Non è stato aperto alcun input autentico durante test o review.

## Safety e limite

```text
REAL_SECRET_READ_COUNT=0
REAL_PRIVATE_CACHE_READ_COUNT=0
REAL_CANONICAL_PE_READ_COUNT=0
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
FACTORY_STATE_MUTATION=0
```

Il prossimo confine è la composizione ownership-only: un owner della open epoch
deve conservare `GoodixTargetMaterial`, view secure e FDT12, legare i seed al
binder, garantire cleanse/free e fornire al `GoodixDeviceContext` dati validi
fino a close. Solo dopo quella closure offline si può progettare il claim e
start asincrono production. Installazione o esecuzione fprintd restano Human
Gate separati.

```text
RESIDUAL_BLOCKER_OR_RISK=OPEN_EPOCH_MATERIAL_OWNER_AND_FPIMAGEDEVICE_BINDING_NOT_IMPLEMENTED
NEXT_PRIMARY_BOUNDARY=OFFLINE_OPEN_EPOCH_MATERIAL_OWNER_COMPOSITION
NEXT_LIVE_PREREQUISITE=SEPARATE_OPERATOR_KIT_BASELINE_REVIEW_AND_EXPLICIT_ONE_SHOT_AUTHORIZATION
```

## Review AI-PM

La review ha verificato la policy production, le classi d'errore redatte,
l'assenza di path/discovery/write, l'atomicità degli output, la copertura del
failure post-read, il cleanse audit e i sanitizer. Il delta non attraversa il
firewall GPL/LGPL e non promuove alcun claim live.

```text
D279_05_AI_PM_REVIEW=PASS
D279_05_CORRECTIVE_REQUIRED=false
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_8f11ad0997451ff1ce06f8daf8dabe41f694cca8_PLUS_CURRENT_DEVELOPMENT_DIFF_PLUS_analysis/D279/D279_05_offline_private_runtime_input_reader.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_docs/LICENSING_AND_PROVENANCE.md_PLUS_libfprint-driver/goodix_runtime_inputs.[ch]
```
