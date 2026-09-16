# D279/42 — baseline-delta NBIS e operator boundary

## Decisione metodologica

Prima di fusion, accumulo o sharpening, il prossimo esperimento minimo testa
il fixed field già misurabile: ATTEMPT02 contiene un B0 no-finger iniziale e 42
B0 fingerprint correttamente alternati. La sottrazione del background prima
della normalizzazione è un metodo comune nel corpus libfprint (Elan) ed è anche
presente nel corpus Goodix Rockytkg; quest'ultimo è solo corroborazione terza,
non prova target-specific e non ne è stato copiato codice.

La matrice contiene solo:

- controllo D279/39 `frame_minmax x2`;
- `frame - baseline`, poi min/max signed e x2;
- `baseline - frame`, poi min/max signed e x2.

Il baseline sottratto da sé diventa costante e resta un controllo negativo.
Non introduce ppmm, flat-field, sharpening, fusion o decisioni production.

## Closure offline e safety

L'evaluator conserva solo gli stessi aggregati D279/39 per i ruoli corretti.
Il kit costruisce il medesimo helper test-only pinned, usa snapshot Git e hash,
consuma il grant prima della lettura protetta e ammette un solo output JSON.
Il preflight esegue 31 test Python, build normale e ASan/UBSan, più build da
snapshot. Nessun helper ha entry point USB; produzione, sender e allowlist non
sono modificati. I timeout restano bound del processo host offline.

Kit: `operator_kit/d279-42-offline-protected-baseline-delta/`.

## Human Gate

La singola incertezza è se la rimozione del fixed field aumenti le minutiae
finali e/o il loro supporto A/B rispetto al controllo, senza rendere positiva
la baseline. Serve una nuova rilettura/decryption in-memory di ATTEMPT02.

```text
OPERATION=D279_42_ONE_OFFLINE_PROTECTED_BASELINE_DELTA_EVALUATION
RUN_COUNT=1
RETRY_AUTHORIZED=false
SECOND_PROTECTED_READ_AUTHORIZED=false
USB_OR_LIVE_AUTHORIZED=false
PERSISTED_OUTPUT=AGGREGATE_SUMMARY_JSON_ONLY
D279_35_AUTHORIZATION_CONSUMED=true
D279_37_AUTHORIZATION_CONSUMED=true
D279_39_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
```

```text
OUTCOME=READY_FOR_HUMAN_GATE_ONE_OFFLINE_PROTECTED_BASELINE_DELTA_EVALUATION
ADVANCEMENT=NEW_PREPROCESSING_HYPOTHESIS_AND_OPERATOR_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=PASS_OFFLINE_ONLY
D279_42_PREFLIGHT_TESTS=31/31_PASS
D279_42_NORMAL_AND_ASAN_UBSAN=PASS
D279_42_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
PRODUCTION_PATH_CHANGED=false
```
