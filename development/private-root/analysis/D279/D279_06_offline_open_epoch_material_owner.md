<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/06 — owner dei materiali della open epoch

## Esito

```text
D279_06_OUTCOME=READY
ADVANCEMENT=MATERIAL_ARCHITECTURAL_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_FULL_COMPOSITION
SINGLE_TARGET_MATERIAL_OWNER=true
SECURE_VIEW_NON_OWNING=true
FDT_SEED_SAME_OWNER=true
AUTHENTIC_PROTECTED_INPUTS_EXECUTED=false
FPRINTD_OPERATIONAL_PATH_PROVEN=false
```

D279/06 compone i boundary D278/02 e D279/04–05 in un solo owner LGPL destinato
alla futura open epoch. La baseline è
`91d62a6ef775f03ec6a38d1d6febb68d216aaa86` sul branch `development`, con
worktree iniziale pulito e allineato a `origin/development`.

## Ownership

`GoodixRuntimeMaterial`:

1. valida PE e cache prima di caricare PSK/CONFIG;
2. crea un solo `GoodixTargetMaterial`;
3. lega i due seed D190 tramite il binder esistente;
4. conserva un descrittore secure non-owning e una copia FDT12;
5. cancella immediatamente i seed produttore intermedi;
6. al free cancella descriptor e FDT12, poi fa liberare al singolo owner PSK,
   validator e CONFIG90.

I cinque path restano espliciti e caller-supplied. Non esiste discovery, path
production predefinito, fallback, USB, protocollo o secondo stack. Le view
copiate dal caller prendono in prestito lo storage e devono essere cancellate
dopo aver configurato il consumer e comunque prima del free dell'owner.

## Prova sintetica completa

La suite `run_goodix_runtime_inputs_test.sh` costruisce cinque file temporanei
0600 interamente sintetici: manifest, transport con PSK sintetica, CONFIG90,
PE e cache. Il validator atteso viene calcolato dal binder LGPL già verificato;
la prova riguarda composizione e ownership, non costituisce un nuovo oracle
crittografico.

La prova osserva:

- due input PE/cache letti e i due buffer azzerati;
- tre input target caricati, E4 binding match e view completa;
- FDT12 appartenente allo stesso owner;
- due cleanse dei seed produttore;
- un solo free dell'owner esterno e un solo free del target owner;
- PSK, validator, CONFIG90, descriptor e FDT cancellati al teardown.

```text
D279_06_RUNTIME_MATERIAL_NORMAL=PASS
D279_06_RUNTIME_MATERIAL_ASAN_UBSAN=PASS
TEST_COUNT_PER_BUILD=8
REAL_PRODUCTION_SECRET_READ=false
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
```

Il target Fedora 44 compila `goodix_runtime_material.c` nella libreria
production-shaped. La build conserva ID, registry e selezione NBIS D279/03.

## Limite e prossimo boundary

L'owner non è ancora istanziato dalla sottoclasse USB. `img_open` non sceglie
path, non carica materiali, non reclama interfaccia 0 e non avvia il grafo
secure-session; `img_close` non rilascia ancora un claim production. La scelta
dei path runtime e del modo in cui un pacchetto/operatore li installa coinvolge
materiale privato e deve restare separata dall'implementazione offline.

```text
RESIDUAL_BLOCKER_OR_RISK=FPIMAGEDEVICE_DOES_NOT_OWN_RUNTIME_MATERIAL_OR_USB_INTERFACE
NEXT_PRIMARY_BOUNDARY=OFFLINE_FPIMAGEDEVICE_PRODUCTION_OPEN_CLOSE_BINDING_WITH_INJECTED_PATHS_AND_USB_SEAMS
REAL_PATH_PROVISIONING=HUMAN_GATE
LIVE_EXECUTION=HUMAN_GATE
```

## Review AI-PM

La review ha verificato che le view non duplicano i secret, l'audit outlives
l'owner, tutti i failure convergono sul teardown, i seed intermedi vengono
cancellati sia in successo sia in errore, e il modulo non introduce USB o
protocollo. Test normali/sanitizer e build production-shaped sono la closure
eseguibile offline; non è dichiarata operatività fprintd.

```text
D279_06_AI_PM_REVIEW=PASS
D279_06_CORRECTIVE_REQUIRED=false
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_91d62a6ef775f03ec6a38d1d6febb68d216aaa86_PLUS_CURRENT_DEVELOPMENT_DIFF_PLUS_analysis/D279/D279_06_offline_open_epoch_material_owner.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_LIBFPRINT_DRIVER_RUNTIME_MATERIAL_AND_TESTS
```
