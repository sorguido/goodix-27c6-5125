# D279/48 — confronto offline protetto Rockytkg / NBIS / SIGFM

## Scopo e limite dell'esperimento

Il kit esegue una sola rilettura protetta offline dei 43 raster ATTEMPT02 con
ordine già provato `baseline,(primary,auxiliary)*21`. Confronta, senza tuning:

- R0 storico: signed baseline delta, normalizzazione e resize x2 verso NBIS,
  preso dal summary autentico D279/46;
- R1: pipeline comune Rockytkg esatta a 80×64 (`2048 + raw - baseline`, clamp
  12-bit, flat-field r=12, stretch percentile 1/99), con lo stesso identico
  raster inviato separatamente a NBIS e SIGFM;
- R2: R1 più unsharp Rockytkg esatto (`boost=0.8`, `sigma=1.5`), ancora con lo
  stesso identico raster inviato ai due extractor.

La pipeline immagine viene compilata direttamente da
`Rockytkg/src/goodix_imgproc.c` preservato, non reimplementata. SIGFM viene
compilato dal fork preservato e usa OpenCV/SIFT. NBIS usa il target Fedora 44
libfprint 1.94.100 pinned. I risultati contengono soltanto aggregati per ruolo,
conteggi di feature/gate e score same-session bidirezionali. La doppia
direzione evita di assumere simmetria dei matcher.

ATTEMPT02 rappresenta un solo contesto sessione/dito e non include controlli
different-finger. Il risultato non può quindi provare FAR/FRR, accuratezza,
soglie production o sicurezza biometrica. Il B0 è usato come riferimento
sperimentale: non è dichiarato equivalente alla vera no-finger baseline di
Rockytkg.

## Safety, privacy e dipendenze

La PSK production viene letta una sola volta in memoria come root, dopo il
consumo del grant, per decrittare la cattura già esistente. Non vengono
esportati PSK, plaintext, raster, minutiae, keypoint, descriptor o template.
Il solo prodotto biometrico ammesso è `summary.json` aggregate-only;
`operator.log` contiene telemetria operativa.

Il kit non enumera né apre USB, non invia comandi al sensore e non avvia
fprintd. Gli helper sono sottoposti a controlli source/symbol/runtime che
escludono entry point USB/TLS/production. Il timeout di 20 minuti è
esclusivamente un safety bound host-side: non implica alcuna proprietà o
quiescenza device-side. Sender, allowlist e guardrail sulla persistenza
sensor-side restano invariati e fuori da questa run.

OpenCV 4.13.0 viene scaricato come insieme di RPM Fedora 44 con NEVRA e SHA-256
fissati, estratto in `/tmp` e copiato nella build privata: non viene installato
alcun pacchetto di sistema. Le dipendenze transitive Fedora già presenti
(`tbb`, `flexiblas`, backend `flexiblas-netlib` e `libstdc++`) sono accettate
soltanto con le versioni x86_64 fissate dal kit; FlexiBLAS resta nel layout di sistema perché
una copia isolata della sola shared library perderebbe il proprio backend.
La compilazione usa l'SDK Flatpak 25.08 senza rete; il solo link finale usa il
driver GCC host per la compatibilità glibc Fedora 44. La fase di download
richiede rete ma non privilegi.

## Prerequisiti e Human Gate

Occorrono:

- branch `development` pulito;
- `HEAD == origin/development`;
- Fedora 44 x86_64 con `dnf`, `rpm2cpio`, `cpio`, GCC link driver;
- Flatpak user `org.freedesktop.Sdk//25.08`;
- SHA completo esplicitamente approvato;
- un grant nuovo per l'operazione esatta:

```text
D279_48_ONE_OFFLINE_PROTECTED_ROCKY_NBIS_SIGFM_COMPARISON
```

Tutte le autorizzazioni precedenti, inclusa D279/46, sono consumate. Il grant
D279/48 è one-shot; retry e seconda lettura sono esclusi.

## Procedura operatore

Prima del Human Gate, da utente normale:

```bash
operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/run-d279-48.sh --offline-preflight
operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/run-d279-48.sh --prepare-approved-analysis SHA_COMPLETO
```

Il preflight verifica test, build, hash sorgenti/RPM, KAT R1/R2, NBIS e SIGFM
reali, identità dell'input consegnato ai matcher e assenza di seam live. La
preparazione produce una directory privata `/tmp/goodix-d279-48-approved.*`
legata allo SHA e stampa il comando successivo.

Solo dopo l'autorizzazione esplicita, creare manualmente una directory privata
e il grant, quindi avviare l'unica run con il comando stampato dal kit. `sudo`
compare soltanto nel percorso manualmente avviato dall'operatore. Il grant
viene consumato prima della lettura protetta; SHA, hash, metadata, collisioni,
file aggiunti allo snapshot e secondo uso falliscono chiusi.

Gli output sono in
`/var/tmp/goodix-d279-48-results/<timestamp>-<sha12>/`. Copiare fuori soltanto
`summary.json` e `operator.log`. Non ripetere la run, neppure dopo un failure,
senza un nuovo Human Gate.

## Interpretazione successiva (AI-PM)

Il summary resta `PENDING_AUTHENTIC_AGGREGATE_REVIEW_A_B_C_OR_D`. La review
classificherà l'evidenza come:

- A: preprocessing Rockytkg salva NBIS;
- B: SIGFM supera materialmente NBIS sullo stesso input;
- C: entrambi falliscono, spostando il blocker a monte;
- D: entrambi funzionano, riportando la scelta sul piano architetturale.

Il kit non auto-seleziona una classe e non modifica il percorso production.
