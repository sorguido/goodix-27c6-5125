# D279/44 — half-wave baseline-delta operator boundary

## Decisione metodologica

D279/42 ha mostrato un segnale positivo dalla sottrazione del B0, ma le due
polarità signed sono complementari dopo min/max e non costituiscono due repliche
indipendenti. Il successivo esperimento cambia realmente metodo: scarta la
deviazione del segno opposto prima della normalizzazione, come avviene con
convenzioni opposte nei driver libfprint Elan/Egis0570 e VFS7552.

La matrice minima contiene:

- controllo `frame-baseline` signed D279/42;
- `max(frame-baseline,0)`;
- `max(baseline-frame,0)`.

Tutte le varianti usano min/max post-delta, identity e resize x2 sul medesimo
NBIS pinned. Non introduce robust stretch, flat-field, sharpening, ppmm, fusion
o accumulo. Il B0 resta un riferimento sperimentale; la sua funzione OEM non è
assunta.

## Closure offline e safety

L'evaluator mantiene soltanto gli aggregati D279/39 sui ruoli corretti. I test
coprono rettifica, segno opposto, caso all-positive, baseline auto-sottratto,
contratti di range/shape e matrice completa. Il kit usa snapshot Git e hash
separati per evaluator D279/42 e D279/44, consuma il grant prima della lettura
protetta e valida fail-closed l'output.

La preflight esegue 37 test Python, build normale e ASan/UBSan del helper,
build da snapshot, source-seam checks e un passaggio end-to-end su 43 raster
sintetici non protetti attraverso evaluator e NBIS pinned. Nessun helper espone
entry point USB; production, sender e allowlist restano invariati. I timeout
sono esclusivamente safety bound del processo host offline.

Kit: `operator_kit/d279-44-offline-protected-halfwave-delta/`.

## Human Gate

La singola incertezza è se la rettifica half-wave aumenti i fingerprint frame
con minutiae nei tier NBIS B/A o A rispetto al delta signed, e quale segno sia
coerente con la cattura target. Serve una nuova rilettura/decryption in-memory
di ATTEMPT02.

```text
OPERATION=D279_44_ONE_OFFLINE_PROTECTED_HALFWAVE_DELTA_EVALUATION
RUN_COUNT=1
RETRY_AUTHORIZED=false
SECOND_PROTECTED_READ_AUTHORIZED=false
USB_OR_LIVE_AUTHORIZED=false
PERSISTED_BIOMETRIC_OUTPUT=AGGREGATE_SUMMARY_JSON_ONLY
D279_35_AUTHORIZATION_CONSUMED=true
D279_37_AUTHORIZATION_CONSUMED=true
D279_39_AUTHORIZATION_CONSUMED=true
D279_42_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
```

```text
OUTCOME=READY_FOR_HUMAN_GATE_ONE_OFFLINE_PROTECTED_HALFWAVE_DELTA_EVALUATION
ADVANCEMENT=NEW_SINGLE_FRAME_PREPROCESSING_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=PASS_OFFLINE_ONLY
D279_44_PREFLIGHT_TESTS=37/37_PASS
D279_44_NORMAL_AND_ASAN_UBSAN=PASS
D279_44_SYNTHETIC_END_TO_END=PASS
D279_44_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
PRODUCTION_PATH_CHANGED=false
```
