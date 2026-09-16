# D279/42 — valutazione offline protetta baseline-delta

## Scopo e rischio

Il kit esegue una sola rilettura protetta offline di ATTEMPT02 per confrontare
il controllo `frame_minmax x2` con la sottrazione pixel-per-pixel del frame
no-finger iniziale, in entrambe le polarità, prima dello stesso NBIS pinned.
Serve a verificare se il fixed field nasconde minutiae; non modifica production.

La run legge la PSK production solo in memoria come root e decritta i 43 raster
già catturati. Non esporta PSK, plaintext, raster, quality map o template:
l'unico output ammesso è un JSON aggregate-only. Non enumera/apre USB, non
avvia fprintd e non raggiunge il sensore.

## Prerequisiti e Human Gate

Occorrono branch `development` pulito, `HEAD == origin/development`, SHA completo
esplicitamente approvato e grant one-shot per l'operazione esatta:

```text
D279_42_ONE_OFFLINE_PROTECTED_BASELINE_DELTA_EVALUATION
```

L'autorizzazione deve essere nuova: D279/35, D279/37 e D279/39 sono consumate.
Retry e seconda lettura sono esclusi.

## Procedura operatore

Eseguire prima, senza privilegi:

```bash
operator_kit/d279-42-offline-protected-baseline-delta/run-d279-42.sh --offline-preflight
operator_kit/d279-42-offline-protected-baseline-delta/run-d279-42.sh --prepare-approved-analysis SHA_COMPLETO
```

Dopo l'approvazione esplicita creare una directory privata e il grant, quindi
avviare manualmente l'unica run con il comando stampato dal kit. `sudo` compare
solo in questo percorso manuale. Il kit consuma il grant prima della lettura
protetta e fallisce chiuso su SHA, hash, metadata, collisione o secondo uso.

Gli output sono in `/var/tmp/goodix-d279-42-results/<timestamp>-<sha12>/`.
Al termine copiare fuori soltanto `summary.json` e `operator.log`. Non ripetere
la run, anche in caso di failure, senza un nuovo Human Gate esplicito.
