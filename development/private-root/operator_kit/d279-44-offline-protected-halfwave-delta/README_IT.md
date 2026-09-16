# D279/44 — valutazione offline protetta half-wave baseline-delta

## Scopo e rischio

Il kit esegue una sola rilettura protetta offline di ATTEMPT02. Confronta il
controllo signed `frame-baseline` D279/42 con le due rettifiche sensor-specifiche
`max(frame-baseline,0)` e `max(baseline-frame,0)`, sempre seguite da min/max e
resize x2 sullo stesso NBIS pinned.

La run stabilisce se scartare le deviazioni del segno opposto migliora le
minutiae nei tier NBIS B/A o A. Non prova che il B0 iniziale sia una calibrazione
OEM e non autorizza preprocessing production, fusion, enrollment o live.

La PSK production viene letta una sola volta in memoria come root per decrittare
i 43 raster già catturati. PSK, plaintext, raster, metriche per-frame,
quality-map e template non vengono esportati. Il solo prodotto biometrico
ammesso è il JSON aggregate-only; `operator.log` contiene soltanto telemetria
operativa. Il kit non enumera/apre USB, non avvia fprintd e non raggiunge il
sensore.

## Prerequisiti e Human Gate

Occorrono branch `development` pulito, `HEAD == origin/development`, SHA completo
esplicitamente approvato e un grant nuovo per l'operazione esatta:

```text
D279_44_ONE_OFFLINE_PROTECTED_HALFWAVE_DELTA_EVALUATION
```

D279/35, D279/37, D279/39 e D279/42 sono consumate. Retry e seconda lettura
sono esclusi.

## Procedura operatore

Prima del gate, senza privilegi:

```bash
operator_kit/d279-44-offline-protected-halfwave-delta/run-d279-44.sh --offline-preflight
operator_kit/d279-44-offline-protected-halfwave-delta/run-d279-44.sh --prepare-approved-analysis SHA_COMPLETO
```

Dopo l'autorizzazione esplicita, creare manualmente directory privata e grant,
quindi avviare l'unica run usando il comando stampato dal kit. `sudo` compare
solo nel percorso manuale dell'operatore. Il grant viene consumato prima della
lettura protetta; SHA, hash, metadata, collisioni e secondo uso falliscono
chiuso.

Gli output sono in `/var/tmp/goodix-d279-44-results/<timestamp>-<sha12>/`.
Copiare fuori soltanto `summary.json` e `operator.log`. Non ripetere la run,
anche in caso di failure, senza un nuovo Human Gate.
