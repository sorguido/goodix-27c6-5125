<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/35 — valutazione offline protetta ATTEMPT02

## Stato e confine autorizzativo

Il kit è predisposto per una sola analisi offline dei 43 frame cifrati già
presenti nella capture OEM ATTEMPT02. **Non autorizza né esegue da solo la
lettura della PSK.** La preparazione approvata, il grant e la run richiedono
prima l'approvazione esplicita dell'Utente su uno SHA Git completo.

Il kit non enumera, apre, reclama o invia comandi al sensore; non avvia
`fprintd`; non esegue enrollment e non richiede che il device sia collegato.
La futura autorizzazione riguarda esclusivamente una lettura one-shot del file
protetto già provisionato:

```text
/var/lib/goodix-5125-poc/transport-material.bin
```

La PSK viene usata solo in memoria per autenticare/decrittare la capture. Non
vengono persistiti PSK, plaintext, raster, template o conteggi per singolo
frame. Le copie mutabili owned sono azzerate; non si afferma la zeroizzazione
provabile di ogni copia interna/transitoria del runtime Python, OpenSSL o NBIS.

## Incertezza chiusa dalla singola analisi

L'output confronta 48 varianti sul dataset OEM già acquisito:

- mapping 12-bit production, min/max frame-local e p01/p99 robusto;
- otto trasformazioni geometriche;
- polarità normale/invertita;
- aggregati separati per 1 baseline, 21 frame primari e 21 ausiliari.

Serve a distinguere se il fallimento live D279/29 sia compatibile con una
trasformazione host inadeguata oppure persista anche sui frame OEM. Non prova
qualità di una futura acquisizione Linux, ergonomia del contatto, robustezza
multi-action o stato sensor-side.

## Preflight consentito prima del Human Gate

Come utente normale:

```bash
./operator_kit/d279-35-offline-protected-evaluation/run-d279-35.sh \
  --offline-preflight
```

Il preflight esegue le suite D279/31–35 e costruisce/testa il NBIS pinned in un
sandbox Flatpak senza rete su dati esclusivamente sintetici. Non legge il
layout `/var/lib`, non accede a USB e non produce raster reali.

## Procedura solo dopo approvazione esplicita

Sostituire `<SHA_APPROVATO>` esclusivamente con lo SHA completo approvato nel
Human Gate. Preparare come utente normale uno snapshot Git immutabile:

```bash
./operator_kit/d279-35-offline-protected-evaluation/run-d279-35.sh \
  --prepare-approved-analysis <SHA_APPROVATO>
```

Annotare `PREPARED_BUILD_DIR`. Il comando verifica branch `development`, HEAD,
`origin/development`, worktree critical pulito e costruisce il helper NBIS dal
solo `git archive` dello SHA. Non legge ancora la PSK.

Creare poi un grant one-shot in una directory privata:

```bash
mkdir -m 700 /tmp/goodix-d279-35-grant
./operator_kit/d279-35-offline-protected-evaluation/run-d279-35.sh \
  --write-grant <SHA_APPROVATO> /tmp/goodix-d279-35-grant/grant.env
```

Solo entro la medesima autorizzazione, avviare manualmente:

```bash
sudo ./operator_kit/d279-35-offline-protected-evaluation/run-d279-35.sh \
  --run-approved-analysis <PREPARED_BUILD_DIR> \
  --grant /tmp/goodix-d279-35-grant/grant.env
```

Il `sudo` è visibile perché la directory production è correttamente
`root:root 0700`. Il grant viene consumato atomicamente **prima** di esaminare o
aprire il file protetto. Il marker resta in
`/var/tmp/goodix-d279-35-consumed-grants/`.

## Stop condition e failure

Non esiste retry automatico. Se il processo fallisce, viene interrotto o non
produce `AUTHENTIC_AGGREGATE_READY`:

- non ripetere il comando;
- non creare un secondo grant;
- non modificare o copiare il materiale protetto;
- conservare `operator.log` e l'eventuale `summary.json`;
- tornare alla review PM.

Non è applicata una deadline alla computazione NBIS: eventuali deadline sono
comunque soltanto bound host-side e non avrebbero alcun significato
device-side. In questo step il device non viene raggiunto.

## Output

La directory risultato è privata e viene restituita all'utente che ha invocato
`sudo`:

```text
/var/tmp/goodix-d279-35-results/<UTC>-<SHA12>/
```

Contiene:

- `operator.log`, con soli marker e failure class;
- `summary.json`, solo in caso di successo, con gli aggregati delle 48
  varianti e i guardrail privacy/safety.

Non pubblicare automaticamente questi file. Consegnarli al PM per la review
evidence-first; l'eventuale passo successivo verrà deciso soltanto dopo aver
integrato il risultato nel manuale canonico.

