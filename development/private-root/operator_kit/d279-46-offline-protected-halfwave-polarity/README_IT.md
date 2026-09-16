# D279/46 — completamento offline protetto della polarità half-wave

## Scopo e rischio

Il kit esegue una sola rilettura protetta offline di ATTEMPT02. Mantiene il
controllo signed D279/44 e misura esclusivamente le due polarità half-wave non
ancora coperte: deviazione conservata scura su fondo bianco per entrambi i
supporti `frame > baseline` e `baseline > frame`, sempre con min/max, identity,
resize x2 e NBIS pinned.

La run separa supporto di segno e polarità d'uscita. Non introduce pesi,
dead-zone, percentile clipping, sharpening, fusion, matching o modifiche
production. Il controllo signed deve riprodurre esattamente il blocco `groups`
degli aggregati D279/44 oppure la run fallisce chiusa.

La PSK production viene letta una sola volta in memoria come root per
decrittare i 43 raster già catturati. PSK, plaintext, raster, metriche
per-frame, quality-map e template non vengono esportati. Il solo prodotto
biometrico ammesso è il JSON aggregate-only; `operator.log` contiene soltanto
telemetria operativa. Il kit non enumera/apre USB, non avvia fprintd e non
raggiunge il sensore.

## Prerequisiti e Human Gate

Occorrono branch `development` pulito, `HEAD == origin/development`, SHA
completo esplicitamente approvato e un grant nuovo per l'operazione esatta:

```text
D279_46_ONE_OFFLINE_PROTECTED_HALFWAVE_POLARITY_COMPLETION_EVALUATION
```

D279/35, D279/37, D279/39, D279/42 e D279/44 sono consumate. Retry e seconda
lettura sono esclusi.

## Procedura operatore

Prima del gate, senza privilegi:

```bash
operator_kit/d279-46-offline-protected-halfwave-polarity/run-d279-46.sh --offline-preflight
operator_kit/d279-46-offline-protected-halfwave-polarity/run-d279-46.sh --prepare-approved-analysis SHA_COMPLETO
```

Dopo l'autorizzazione esplicita, creare manualmente directory privata e grant,
quindi avviare l'unica run usando il comando stampato dal kit. `sudo` compare
solo nel percorso manuale dell'operatore. Il grant viene consumato prima della
lettura protetta; SHA, hash, metadata, collisioni e secondo uso falliscono
chiuso.

Gli output sono in `/var/tmp/goodix-d279-46-results/<timestamp>-<sha12>/`.
Copiare fuori soltanto `summary.json` e `operator.log`. Non ripetere la run,
anche in caso di failure, senza un nuovo Human Gate.
