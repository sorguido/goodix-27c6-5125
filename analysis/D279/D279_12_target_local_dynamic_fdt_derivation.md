<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/12 — derivazione FDT dinamica target-local

## Esito

L'audit hash-gated di ATTEMPT02 determina ora, senza esportare tabelle, le
relazioni per-ciclo necessarie al modello iterativo. Tutti i 41 body `0x34`
usano la trasformazione up dell'IRQ2 dello stesso stage; i 20 `0x36` dei cicli
2–21 usano la trasformazione down dell'IRQ0200 dello stage precedente; tutti i
21 `0x32` usano la trasformazione down dell'IRQ0200 dello stesso stage. Nei
cicli 2–21 i due `0x34` sono identici. I due `0x32` del primo ciclo condividono
la tabella, ma hanno timestamp distinti.

```text
OUTCOME=READY_OFFLINE_FDT_STATE
ADVANCEMENT=NEW_TARGET_LOCAL_PROTOCOL_RELATION_AND_IMPLEMENTATION
ATTEMPT02_OBSERVED_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
RAW_TABLE_BYTES_EXPORTED=false
CAPTURES_CHANGED=false
PRODUCTION_ENROLLMENT_ENABLED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Implementazione

`goodix_enrollment_fdt_state.[ch]` conserva soltanto la tabella up dello stage
corrente e l'ultima tabella down. Impone stage consecutivi e risolve materiale
solo secondo queste relazioni:

- `0x34(stage N) ← up(IRQ2 stage N)`;
- `0x36(stage N) ← down(IRQ0200 stage N−1)`, solo da N=2;
- `0x32(stage N) ← down(IRQ0200 stage N) + timestamp caller`.

Il modulo non interpreta i B0 ausiliari e non nega un loro possibile ruolo in
quality, template o NBIS. Non contiene parser A0, frame builder, backend,
retry o submit. Output e tabelle interne vengono azzerati; stage duplicati,
salti, tabelle non ancora disponibili e timestamp errati falliscono chiuso.

## Verifica

La regressione attraversa tutti i 21 stage osservati e verifica 21 derivazioni
up, 21 down, 20 riusi previous-stage per `0x36` e 21 risoluzioni current-stage
per `0x32`; un duplicato stage è terminale. Passa normale e ASan/UBSan. L'audit
autentico passa 3/3 e il JSON sanitizzato contiene soltanto relazioni booleane.

```text
D279_12_TESTS=2/2_PASS_NORMAL;2/2_PASS_ASAN_UBSAN
D279_10_HASH_GATED_AUDIT=3/3_PASS
FDT_RELATION_34_CURRENT_IRQ2_UP=41/41
FDT_RELATION_36_PREVIOUS_IRQ0200_DOWN=20/20
FDT_RELATION_32_CURRENT_IRQ0200_DOWN=21/21
EXECUTABLE_CLOSURE=PASS_HOST_ONLY_ZERO_SENDER
```

## Confine residuo

La derivazione e il body contract sono separati dal lifecycle production. Il
successivo passo offline è un adapter iterativo che li componga con il planner
e verifichi l'intera sequenza senza backend. Il vfunc enrollment e il sender
production restano disabilitati.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_ITERATIVE_ENROLLMENT_LIFECYCLE_ADAPTER_WITHOUT_BACKEND
```
