# D279/37 — valutazione offline protetta del resize spaziale

Questo kit prepara una sola valutazione offline dei 43 frame ATTEMPT02 già
acquisiti. Non enumera né apre USB, non avvia fprintd e non raggiunge il
sensore. La nuova ipotesi è strettamente una: l'immagine nativa 80×64 è troppo
piccola per NBIS e il resize bilineare pinned fattore 2 o 3 cambia in modo
discriminante le metriche aggregate.

La matrice mantiene orientamento `identity` e polarità `normal`, usa i tre
mapping D279/34 e prova fattori spaziali 1/2/3. Il fattore 1 bypassa
l'interpolazione ed è il controllo esatto delle corrispondenti varianti
D279/35. L'output contiene soltanto statistiche aggregate per baseline, 21
primarie e 21 ausiliarie; non salva raster, template o conteggi per-frame.

## Stato di autorizzazione

La vecchia autorizzazione D279/35 è consumata e non può essere riusata. Le fasi
`--offline-preflight` e `--prepare-approved-analysis` non leggono protected
material. `--write-grant` e soprattutto `--run-approved-analysis` potranno
essere usate solo dopo un nuovo Human Gate che nomini il full SHA e autorizzi
esattamente:

```text
D279_37_ONE_OFFLINE_PROTECTED_SPATIAL_RESIZE_EVALUATION
```

L'autorizzazione non include USB/live, retry, una seconda lettura, modifica o
copia del transport, persistenza di raster/template o operazioni sul sensore.

## Procedura dopo il futuro Human Gate

Da utente normale, nel clone pulito su `development` e sullo SHA approvato:

```bash
operator_kit/d279-37-offline-protected-spatial-resize/run-d279-37.sh --offline-preflight
operator_kit/d279-37-offline-protected-spatial-resize/run-d279-37.sh --prepare-approved-analysis SHA_COMPLETO
```

La seconda istruzione stampa la directory preparata e il grant id atteso. Solo
dopo aver verificato che coincidano con il gate, creare il grant in una
directory privata `0700` e avviare manualmente l'unica run con `sudo`:

```bash
operator_kit/d279-37-offline-protected-spatial-resize/run-d279-37.sh --write-grant SHA_COMPLETO /percorso/privato/grant
sudo operator_kit/d279-37-offline-protected-spatial-resize/run-d279-37.sh --run-approved-analysis /tmp/goodix-d279-37-approved.XXXXXX --grant /percorso/privato/grant
```

Stop condition: qualunque mismatch di SHA, branch, origin, hash, metadata,
helper, output o grant. Non correggere e non riprovare: conservare il log e
riportare l'esito. Il grant viene consumato prima dell'accesso al transport,
anche se la valutazione fallisce.

Gli output vengono creati in
`/var/tmp/goodix-d279-37-results/<timestamp>-<sha12>/`. Al termine conservare
`operator.log` e, solo in caso di successo, `summary.json`. La directory
preparata in `/tmp` può essere eliminata manualmente dopo aver copiato gli
output; nessun cleanup deve cancellare il marker di consumo.
