<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/04 — provider LGPL degli input runtime PE/FDT

## Esito

```text
D279_04_OUTCOME=READY
ADVANCEMENT=NEW_PRODUCTION_RUNTIME_PREREQUISITE_IMPLEMENTED
EXECUTABLE_CLOSURE=PASS_OFFLINE
PE_PRODUCER_PROVIDER_LGPL=true
FDT_SEED_PROVIDER_LGPL=true
PRODUCTION_PINS_COMPILED=true
AUTHENTIC_PROTECTED_INPUTS_EXECUTED=false
FPRINTD_OPERATIONAL_PATH_PROVEN=false
CURRENT_LIVE_AUTHORIZED=false
```

D279/04 elimina il gap computazionale tra il driver LGPL e i due input che
prima venivano prodotti soltanto dal glue GPL dell'operator harness: i seed
D190 ricavati dal PE canonico e il seed FDT12 ricavato dalla cache canonica.
Non implementa ancora il reader filesystem né il binding `img_open/img_close`.

## Baseline e scope

```text
branch=development
D279_04_BASELINE=c48acb4bacfb6a3ccfd2c45b60733be1ce4075db
initial_worktree=CLEAN
TARGET_OS=Fedora_44_x86_64
TARGET_LIBFPRINT_VERSION=1.94.100
REAL_USB_ACCESS=0
REAL_PRODUCTION_SECRET_READ=0
```

Lo step è interamente offline. Non apre file autentici, non legge PSK/cache
private, non enumera o apre USB, non installa libfprint e non contatta fprintd.
Le prove runtime usano esclusivamente PE e cache sintetici in memoria.

## Implementazione

`libfprint-driver/goodix_runtime_inputs.[ch]` espone due trasformazioni pure su
byte caller-owned:

- PE hash-pinned e bounded: header DOS/PE, massimo 96 sezioni, mapping RVA
  esclusivamente in intervalli file-backed, pattern produttore unico e output
  di due seed da sei byte;
- cache FDT hash-pinned: layout esatto, CRC-32/MPEG-2 stored little-endian,
  binding hash OTP64, FDT12 a offset 64 e rifiuto del seed tutto-zero.

Ogni failure azzera gli output. I seed produttore hanno una API di cleanse
esplicita; hash e scratch interni vengono cancellati. Le classi di errore sono
stabili e redatte. Il modulo non contiene API filesystem, USB, discovery,
subprocess, mapping eseguibile o scrittura e non offre fallback sintetici in
policy production.

La source map Meson Fedora 44 ora compila, nello stesso driver registrato,
anche `goodix_d190_binder.c`, `goodix_target_material.c` e
`goodix_runtime_inputs.c`. Questo prova la compatibilità di build del futuro
grafo production senza dichiararlo già collegato al lifecycle.

## Provenance e firewall GPL/LGPL

La porzione PE è adattata direttamente dalla reference project-owned
BSD-2-Clause al commit
`b475a6eca72e340816779afae917334a6146c986`, path
`poc/goodix5125/tools/binding_reference/pe_parser.py`, blob
`c2f6451308f1f0e78942c02b46daa3b85b061577`. Copyright e provenance sono
preservati; il successivo port GPL `tools/goodix_d190_pe.c` non è la fonte
licensing del nuovo modulo.

La porzione FDT è nuova espressione locale basata sui fatti di formato già
canonizzati D255/D261. Non copia il provider filesystem, l'orchestrazione o il
reporting GPL. Il ledger canonico è aggiornato.

## Verifiche

```text
libfprint-driver/tests/run_goodix_runtime_inputs_test.sh
```

La suite contiene cinque test sia normali sia ASan/UBSan:

- estrazione PE e cleanse;
- hash PE errato e pattern duplicato fail-closed;
- estrazione FDT sintetica;
- CRC, OTP binding e FDT assente fail-closed;
- forma esatta delle policy production.

Risultati:

```text
D279_04_RUNTIME_INPUTS_NORMAL=PASS
D279_04_RUNTIME_INPUTS_ASAN_UBSAN=PASS
D279_03_FEDORA44_LIBFPRINT_1_94_100_BUILD=PASS
D279_03_STANDARD_DRIVER_REGISTRY=PASS
PRODUCTION_USB_ID_27C6_5125_REGISTERED=true
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
LIVE_EXECUTION_PERFORMED=false
```

La build 1.94.100 segnala soltanto i warning `-Wswitch-enum` storici; nessun
warning proviene dal nuovo provider. Il piccolo guard su `_GNU_SOURCE` evita
la ridefinizione quando Meson fornisce già la stessa feature macro.

## Limiti e prossimo boundary

La trasformazione su byte è ora disponibile nel dominio giusto, ma nessun
caller production possiede ancora in modo atomico:

1. reader read-only/no-follow con metadata e TOCTOU check per DLL/cache;
2. `GoodixTargetMaterial` e relative view per tutta la open epoch;
3. FDT12 per `GoodixPostTlsMaterial`;
4. cleanup/cleanse su ogni failure e su `img_close`;
5. claim/release della sola interfaccia USB 0 nel lifecycle libfprint.

```text
RESIDUAL_BLOCKER_OR_RISK=PRODUCTION_FILESYSTEM_OWNERSHIP_AND_FPIMAGEDEVICE_OPEN_CLOSE_BINDING_NOT_IMPLEMENTED
NEXT_PRIMARY_BOUNDARY=OFFLINE_PRODUCTION_INPUT_FILE_READER_AND_OPEN_EPOCH_OWNERSHIP
NEXT_LIVE_PREREQUISITE=SEPARATE_OPERATOR_KIT_BASELINE_REVIEW_AND_EXPLICIT_ONE_SHOT_AUTHORIZATION
```

## Review AI-PM

La review separata ha verificato il diff, la compatibilità licensing della
fonte BSD, la separazione dal glue GPL, i vettori sintetici, gli output
fail-closed, l'assenza di API I/O/USB nel nuovo modulo e la compilazione nella
reference esatta. Non sono stati letti input autentici e nessun claim live è
stato promosso.

```text
D279_04_AI_PM_REVIEW=PASS
D279_04_CORRECTIVE_REQUIRED=false
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_c48acb4bacfb6a3ccfd2c45b60733be1ce4075db_PLUS_CURRENT_DEVELOPMENT_DIFF_PLUS_analysis/D279/D279_04_offline_lgpl_runtime_input_providers.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_docs/LICENSING_AND_PROVENANCE.md_PLUS_LIBFPRINT_DRIVER_AND_TARGET_MESON_FILES
```
