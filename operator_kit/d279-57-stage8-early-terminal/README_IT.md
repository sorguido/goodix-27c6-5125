<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/57 — enrollment SIGFM stage-8, terminale anticipato one-shot

## Stato e scopo

Il kit prepara una sola action enrollment sul Goodix USB `27c6:5125` per
verificare il confine sensor-side rimasto dopo D279/56: completare lo stage 8
fino all'IRQ finger-up `0x0200`, non inviare il successivo re-arm `0x32`, quindi
disattivare, drenare e chiudere l'open epoch.

Il kit **non autorizza la run live**. Preparazione live, grant ed esecuzione
richiedono prima l'approvazione umana esplicita del full SHA pubblicato su
`origin/development` per l'operazione:

```text
D279_57_STAGE8_EARLY_TERMINAL_ENROLLMENT
```

La run usa un cap fisso a 8, non la convergenza dinamica per duplicati. È la
composizione minima necessaria a isolare il boundary USB: D279/56 ha infatti
classificato come distinti tutti i primi otto sample ATTEMPT02. La policy
dinamica completa resta fuori scope finché il terminale anticipato APP12509
non è provato.

## Invarianti

```text
factory_firmware_and_persistent_state_must_remain_untouched
ACTION_ATTEMPT_MAX=1
OPERATOR_RETRY_COUNT=0
SECOND_ACTION_COUNT=0
REOPEN_COUNT=0
BIOMETRIC_TEMPLATE_SAVED=false
EXPECTED_ENROLLMENT_STAGE_COUNT=8
```

L'allowlist non contiene famiglie persistenti note. Questo è un guardrail
software, non una prova generale di assenza di effetti sensor-side ignoti.

## Cosa prova e cosa non prova

Un esito positivo deve mostrare otto progressi SIGFM reali, un solo terminale
del grafo, sette re-arm inter-stage, nessun re-arm dopo lo stage 8, audit
senza retry/famiglie persistenti note, backend drenato, release USB e close.

Non prova ancora la riutilizzabilità del sensore dopo il close: per quella
serve una successiva action in un nuovo open epoch, separata e nuovamente
autorizzata dopo la review D279/57. Non prova inoltre FAR/FRR, soglia SIGFM,
fprintd/PAM, installazione di sistema o convergenza dinamica.

## Prerequisiti

- branch `development`, HEAD pulito nel live-critical set e uguale al full SHA
  approvato e a `origin/development`;
- Freedesktop SDK 25.08 Flatpak;
- host Fedora con le versioni TBB/FlexiBLAS/libstdc++ attese dal kit;
- accesso ai repository Fedora per scaricare i cinque RPM OpenCV 4.13, tutti
  verificati contro il manifest SHA-256 versionato;
- esattamente un Goodix `27c6:5125` durante la run;
- materiale production già presente nel layout protetto
  `/var/lib/goodix-5125-poc`;
- nessun `fprintd` concorrente;
- approvazione one-shot dello SHA e dell'operazione D279/57.

L'AI non esegue `sudo`, non accede al materiale protetto e non avvia la run.

## Preflight offline

Prima del Human Gate è consentito soltanto:

```bash
./operator_kit/d279-57-stage8-early-terminal/run-d279-57.sh --offline-preflight
```

Il comando scarica gli RPM OpenCV hash-pinned, compila in `/tmp` la libreria
production SIGFM e il client con baseline `UNAPPROVED_FOR_LIVE`, verifica che
le seam di test non siano esportate e prova il rifiuto prima della creazione
di `FpContext`. Non enumera né apre USB.

## Procedura solo dopo approvazione esplicita

Come utente normale:

```bash
./operator_kit/d279-57-stage8-early-terminal/run-d279-57.sh \
  --prepare-approved-live <SHA_COMPLETO_APPROVATO>

mkdir -m 700 /tmp/goodix-d279-57-grant
./operator_kit/d279-57-stage8-early-terminal/run-d279-57.sh \
  --write-grant <SHA_COMPLETO_APPROVATO> \
  /tmp/goodix-d279-57-grant/grant.env
```

Annotare `PREPARED_BUILD_DIR`. Il build proviene da `git archive` dello SHA;
client, libfprint, libgusb e DSO OpenCV sono legati da manifest e hash. Solo a
quel punto l'operatore può eseguire manualmente:

```bash
sudo ./operator_kit/d279-57-stage8-early-terminal/run-d279-57.sh \
  --run-approved-live <PREPARED_BUILD_DIR> \
  --grant /tmp/goodix-d279-57-grant/grant.env
```

Il grant viene consumato atomicamente prima dell'accesso al materiale,
dell'enumerazione e dell'USB. Non cancellare il marker in
`/var/tmp/goodix-d279-57-consumed-grants/`.

## Durante la singola action

Usare sempre l'indice destro. Appoggiare il dito quando richiesto; dopo ogni
`STAGE_COMPLETATO=n/8` inferiore a 8, toglierlo, attendere un istante e
riposizionare lo stesso dito in una zona diversa. Non cambiare dito e non
avviare altri comandi.

Attendere `ENROLLMENT_SUCCEEDED=true`, `CLOSE_SUCCEEDED=true` e
`D279_57_STAGE8_TERMINAL_AUDIT_PASS=true`. Il template resta solo in memoria e
non viene serializzato o salvato.

## Stop condition

Qualunque errore di stage, timeout host, segnale, close fallita o audit non
conforme termina senza retry. Non creare un altro grant, non riaprire il
sensore, non avviare fprintd e non inferire quiescenza device-side. Conservare
la directory risultati e tornare alla review AI-PM.

Il limite di 600 secondi e l'eventuale kill esterno sono soltanto bound host:
non provano timeout o quiescenza del sensore.

## Output

```text
/var/tmp/goodix-d279-57-results/<UTC>-<SHA12>/operator.log
/var/tmp/goodix-d279-57-results/<UTC>-<SHA12>/summary.env
```

I file sono privati e non contengono raster, template, PSK, CONFIG90 o FDT raw.
Copiarli senza modificarli nel canale concordato per la review. Anche con
successo, non eseguire una seconda action: la prova di reusability è il
boundary successivo e richiede una nuova decisione esplicita.
