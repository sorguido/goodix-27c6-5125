# D279/56 — replay offline protetto della policy enrollment dinamica

## Scopo già autorizzato

Questo kit risponde a una sola domanda: applicando ai 21 raster primari R2
autentici di ATTEMPT02 la policy dinamica Rockytkg esatta, a quale stage si
sarebbe fermata la selezione?

L'autorizzazione è già stata concessa all'origine nel documento
`D279_ENROLLMENT_POLICY_21_VS_ROCKY_DYNAMIC_REVIEW.md`, SHA-256
`9b93693a27eaa6456b1d72a13d0d61e9bd01a3cd0842ae6f9e5c530ec9c631f6`.
Non serve una nuova autorizzazione per la run o per retry tecnici dello stesso
studio. Questa autorizzazione non include live/USB, nuove acquisizioni,
installazioni, provisioning, modifiche PSK o uso di sudo da parte dell'AI.

Il comando con `sudo` deve quindi essere avviato manualmente dall'operatore:
serve soltanto per leggere il layout protetto già esistente. Non è una nuova
richiesta di consenso sullo studio.

## Privacy e output

PSK, record TLS, plaintext, raster R2, descriptor e template restano in memoria
e vengono cancellati best-effort dagli owner esistenti. L'unico file di
risultato è `summary.json`, contenente conteggi e classificazioni
`ACCEPT/DUPLICATE/CONVERGE`; non contiene MAD per-stage numeriche. Il validator
fallisce chiuso se compaiono campi per-stage diversi da indice e classe.

Il kit non enumera o apre USB, non avvia fprintd, non invia comandi e non
installa né scarica dipendenze. Compila soltanto il preprocessor R2 puro già
production e l'adapter stdin/stdout host-only.

## Procedura

Dal branch `development`, dopo il commit/push del kit:

```bash
operator_kit/d279-56-offline-protected-dynamic-enrollment/run-d279-56.sh --offline-preflight
SHA=$(git rev-parse HEAD)
operator_kit/d279-56-offline-protected-dynamic-enrollment/run-d279-56.sh --prepare-authorized-study "$SHA"
```

Il secondo comando stampa `PREPARED_DIRECTORY` e il comando esatto successivo.
Eseguire manualmente quello stampato, ad esempio:

```bash
sudo operator_kit/d279-56-offline-protected-dynamic-enrollment/run-d279-56.sh --run-authorized-study /tmp/goodix-d279-56-authorized.XXXXXX
```

Gli output vengono creati mode 0600 sotto:

```text
/var/tmp/goodix-d279-56-results/<timestamp>-<sha12>/
```

Riportare nel repository soltanto `summary.json` e `operator.log`. Non copiare
alcun file temporaneo, snapshot, materiale protetto o output diverso. In caso
di failure, il documento originario consente la correzione e il retry tecnico
nello stesso perimetro; non usare tale autorizzazione per ampliare lo studio.

## Interpretazione

Il risultato valida soltanto il comportamento del selettore sul dataset
single-session/same-finger ATTEMPT02. Non valida soglie production, FAR/FRR o
la sicurezza device-side di un terminale anticipato. Prima di ritirare `21`
nel runtime resta separatamente aperto `DYNAMIC_EARLY_TERMINAL_APP12509`.
