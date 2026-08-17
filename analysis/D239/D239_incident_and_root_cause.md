# D239 — incidente D238 e root cause

Data audit: 2026-08-16

## Classificazione

```text
OPERATOR_KIT_PREFLIGHT_INVOCATION_FAILURE
NO_LIVE_USB_EXECUTION
```

Il tentativo autorizzato D238 si è arrestato alla prima importazione del
preflight con `ModuleNotFoundError: No module named 'src'`. Il launcher eseguiva
direttamente:

```text
python3 analysis/D236/d236_preflight.py
```

In questa modalità Python inserisce nel module search path la directory dello
script, non garantisce la root del repository e non può quindi risolvere il
package top-level `src` quando `PYTHONPATH` non la contiene.

## Ordine di esecuzione e impatto

L'ordine fail-closed del launcher D238 era:

1. esecuzione del preflight Python;
2. validazione del report preflight;
3. verifica del marker di autorizzazione;
4. backup e unseal temporaneo;
5. claim del marker;
6. singola invocazione dell'entrypoint live.

Il fallimento è avvenuto durante l'import del modulo, prima dell'ingresso in
`main()`. Ne segue che il tentativo non ha raggiunto unseal, check o claim del
marker, import/esecuzione dell'entrypoint live, `libusb_init`, USB open o
comandi Goodix. Il report D236 preesistente non fu rigenerato dal tentativo e
non può esserne usato come evidenza.

La directory `/var/lib/goodix-5125-poc` è risultata non ispezionabile
dall'utente non privilegiato (mode `0700` e accesso negato). Non sono stati
usati `sudo` o altri privilegi per aggirare il limite. L'ordine del codice
dimostra comunque che il tentativo fallito non raggiunse il marker.

Lo stato Git mostra il corpus D230–D239 come non tracciato rispetto al piccolo
HEAD pubblico. Non sono state alterate né rimosse modifiche locali. Le due
sorgenti live risultano ancora sealed:

```text
src/goodix5125_d233_backend.py
  SHA-256 7727128ee27337b70ba48eac31b8640c888b76560387363e4eff0c167d993f5b
src/goodix5125_d235_entrypoint.py
  SHA-256 38e857a14bd416808b9ae2df7c4101809879e4732b6e001ce29d11bd731dd555
```

## Correzione D239

Il nuovo launcher fornisce a ogni entrypoint Python dipendente dal repository
un contesto esplicito e deterministico:

```text
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}"
PYTHONDONTWRITEBYTECODE=1
```

Il preflight espone un probe d'import offline e il launcher aggiunge un vero
percorso `--offline-dry-run-pre-usb`. Quest'ultimo usa input esclusivamente
sintetici, compone gli oggetti production e si arresta a un fence esplicito
prima dell'inizializzazione libusb. Il ramo live non può selezionare il seam
offline e richiede preventivamente un report dry-run PASS corrente e
hash-validato.

La patch di unseal D239 è byte-identica a quella D238. Non sono stati modificati
sequenza di protocollo, payload, ACK/response policy, timeout, retry,
single-use semantics, identity/topology gates, opcode vietati o recovery.

## Esito

```text
OPERATOR_KIT_DRY_RUN_PRE_USB=PASS
LIVE_USB_EXECUTION=NOT_PERFORMED
```

Il gate permanente impedisce di considerare il kit pronto per review se il
report manca, è fallito, è stale oppure non conserva tutti i contatori live a
zero. PASS autorizza soltanto la review, non un'esecuzione hardware.
