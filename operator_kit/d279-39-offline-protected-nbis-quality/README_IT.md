# D279/39 — valutazione offline protetta del supporto quality NBIS

Questo kit prepara una sola valutazione offline dei 43 frame ATTEMPT02 già
acquisiti. Non enumera né apre USB, non avvia fprintd e non raggiunge il
sensore. La nuova ipotesi è strettamente una: il segnale minutiae osservato con
resize deve essere sostenuto dalla quality-map NBIS, non soltanto da falsi
positivi che compaiono anche sulla baseline.

La matrice mantiene orientamento `identity` e polarità `normal`, usa i tre
mapping D279/34 e prova fattori spaziali 1/2/3. Il fattore 1 bypassa
l'interpolazione ed è il controllo esatto delle corrispondenti varianti D279/35.
I ruoli usano l'ordine corretto provato in D279/38:
`baseline,(primary,auxiliary)*21`. L'output contiene soltanto min/mediana/max e
numero di valori non-zero, separati per ruolo, per: totale minutiae, soglie
reliability, livelli 0..4 della quality-map e proporzioni A/B. Non salva raster,
quality-map, template o metriche per-frame.

Con `ppmm=0`, uguale al path production corrente, le soglie reliability
riflettono i tier della quality-map ma non una reliability grayscale a scala
fisica. Il risultato non potrà quindi inventare il `ppmm` del sensore né provare
da solo matching, fusion o readiness production.

## Stato di autorizzazione

Le autorizzazioni D279/35 e D279/37 sono consumate e non possono essere
riusate. Le fasi
`--offline-preflight` e `--prepare-approved-analysis` non leggono protected
material. `--write-grant` e soprattutto `--run-approved-analysis` potranno
essere usate solo dopo un nuovo Human Gate che nomini il full SHA e autorizzi
esattamente:

```text
D279_39_ONE_OFFLINE_PROTECTED_NBIS_QUALITY_EVALUATION
```

L'autorizzazione non include USB/live, retry, una seconda lettura, modifica o
copia del transport, persistenza di raster/template o operazioni sul sensore.

## Procedura dopo il futuro Human Gate

Da utente normale, nel clone pulito su `development` e sullo SHA approvato:

```bash
operator_kit/d279-39-offline-protected-nbis-quality/run-d279-39.sh --offline-preflight
operator_kit/d279-39-offline-protected-nbis-quality/run-d279-39.sh --prepare-approved-analysis SHA_COMPLETO
```

La seconda istruzione stampa la directory preparata e il grant id atteso. Solo
dopo aver verificato che coincidano con il gate, creare il grant in una
directory privata `0700` e avviare manualmente l'unica run con `sudo`:

```bash
operator_kit/d279-39-offline-protected-nbis-quality/run-d279-39.sh --write-grant SHA_COMPLETO /percorso/privato/grant
sudo operator_kit/d279-39-offline-protected-nbis-quality/run-d279-39.sh --run-approved-analysis /tmp/goodix-d279-39-approved.XXXXXX --grant /percorso/privato/grant
```

Stop condition: qualunque mismatch di SHA, branch, origin, hash, metadata,
helper, output o grant. Non correggere e non riprovare: conservare il log e
riportare l'esito. Il grant viene consumato prima dell'accesso al transport,
anche se la valutazione fallisce.

Gli output vengono creati in
`/var/tmp/goodix-d279-39-results/<timestamp>-<sha12>/`. Al termine conservare
`operator.log` e, solo in caso di successo, `summary.json`. La directory
preparata in `/tmp` può essere eliminata manualmente dopo aver copiato gli
output; nessun cleanup deve cancellare il marker di consumo.
