<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/29 — prima enrollment production one-shot

## Stato del kit

Il kit è predisposto per una sola action enrollment sul Goodix USB
`27c6:5125`, ma **non autorizza alcuna run live**. La preparazione live, la
creazione del grant e l'esecuzione richiedono prima l'approvazione umana
esplicita del commit SHA completo indicato dal PM.

Invarianti:

```text
factory_firmware_and_persistent_state_must_remain_untouched
ACTION_ATTEMPT_MAX=1
OPERATOR_RETRY_COUNT=0
SECOND_ACTION_COUNT=0
REOPEN_COUNT=0
BIOMETRIC_TEMPLATE_SAVED=false
```

L'assenza delle famiglie persistenti note nell'allowlist del sender è un
guardrail software. Non dimostra l'assenza di effetti persistenti sensor-side
non ancora compresi.

## Scopo della singola run

La run chiude esclusivamente le incertezze non più risolvibili offline:

- attraversamento reale del grafo production USB fino a enrollment;
- forma, orientamento, qualità e sufficienza biometrica delle immagini reali;
- comportamento reale del sensore lungo i 21 stage target-local.

Non prova robustezza multi-action, retry, cancel/reactivation nello stesso open
epoch, fprintd, packaging/install-tree, verify o PAM.

## Prerequisiti

- checkout canonico sul branch `development`, allo SHA completo approvato e
  già pubblicato su `origin/development`;
- live-critical set pulito;
- Freedesktop SDK 25.08 Flatpak installato per il build offline;
- esattamente un Goodix `27c6:5125` disponibile durante la run;
- materiale production già provisionato nel layout protetto
  `/var/lib/goodix-5125-poc` secondo D279/07;
- nessun processo concorrente che usi il lettore (`fprintd` incluso);
- approvazione umana one-shot per lo SHA e l'operazione
  `D279_29_ONE_SHOT_ENROLLMENT`.

L'agente AI non esegue `sudo`, non accede al materiale protetto e non avvia la
run live.

Prima della run l'operatore deve arrestare manualmente `fprintd` se attivo. Il
launcher rifiuta l'esecuzione se rileva ancora un processo `fprintd`; non lo
arresta né lo riavvia automaticamente. Dopo la run non riavviare il servizio
prima della review dei risultati, perché una nuova attivazione potrebbe
costituire un ulteriore accesso hardware non autorizzato.

## Preflight offline

Questa è l'unica modalità eseguibile prima del Human Gate:

```bash
./operator_kit/d279-29-one-shot-enrollment/run-d279-29.sh --offline-preflight
```

Compila la libreria production esatta con NBIS nativo e un client marcato
`UNAPPROVED_FOR_LIVE`. Il self-test deve rifiutarsi prima di creare
`FpContext`, quindi senza enumerazione o accesso USB.

## Procedura dopo approvazione esplicita

Sostituire `<SHA_APPROVATO>` esclusivamente con lo SHA completo comunicato e
approvato nel Human Gate. Eseguire come utente normale:

```bash
./operator_kit/d279-29-one-shot-enrollment/run-d279-29.sh \
  --prepare-approved-live <SHA_APPROVATO>
```

Annotare `PREPARED_BUILD_DIR`. Il build nasce da `git archive` dello SHA, non
dal worktree. Il launcher ricontrolla branch, HEAD, `origin/development`, set
live-critical e hash degli artefatti.

Creare una sola volta il grant in una directory privata dell'operatore:

```bash
mkdir -m 700 /tmp/goodix-d279-29-grant
./operator_kit/d279-29-one-shot-enrollment/run-d279-29.sh \
  --write-grant <SHA_APPROVATO> /tmp/goodix-d279-29-grant/grant.env
```

Solo a questo punto, e solo per la singola autorizzazione ricevuta, l'operatore
può avviare manualmente:

```bash
sudo ./operator_kit/d279-29-one-shot-enrollment/run-d279-29.sh \
  --run-approved-live <PREPARED_BUILD_DIR> \
  --grant /tmp/goodix-d279-29-grant/grant.env
```

Il `sudo` è intenzionalmente visibile e resta un'azione manuale dell'Utente.
Il grant è legato in modo deterministico a SHA e operazione; viene consumato
atomicamente prima di materiale protetto, enumerazione e USB. Non cancellare
il marker in `/var/tmp/goodix-d279-29-consumed-grants/`.

## Durante l'enrollment

Usare sempre l'indice destro:

1. appoggiare il dito quando compare `AZIONE_OPERATORE=METTI...`;
2. dopo ogni `STAGE_COMPLETATO=n/21`, togliere il dito, attendere un istante e
   riposizionare lo stesso dito;
3. non cambiare dito e non lanciare altri comandi sul sensore;
4. attendere `ENROLLMENT_SUCCEEDED=true` e `CLOSE_SUCCEEDED=true`.

Il client invoca `fp_device_enroll_sync()` una sola volta. Un errore/retry di
stage cancella immediatamente l'action: il client non ritenta. Il template
NBIS risultante resta soltanto in memoria e non viene serializzato.

Il client legge dopo il close un audit production sanitizzato e read-only:
contatori USB, comandi/ACK, handshake TLS, progressione enrollment,
retry/reopen/reset/clear-halt, famiglie persistenti note e stato del cleanup
host. L'accessor non espone payload e non può inviare comandi o modificare lo
stato del driver. Le seam sintetiche di open/claim e submit sono escluse a
compile-time dalla libreria production, inclusi i setter low-level del backend.

## Stop condition

Premere `Ctrl+C` una sola volta solo se necessario. Esiste anche un limite di
600 secondi lato host. Entrambi chiedono cancellazione e cleanup; un ulteriore
limite esterno può terminare il processo se il cleanup non completa.

In qualunque caso di errore, timeout, segnale, kill, close fallita o output
ambiguo:

- non ripetere il comando;
- non creare un altro grant;
- non inferire timeout, inattività o quiescenza del sensore;
- non avviare una seconda action né un reopen nella stessa run;
- conservare integralmente la directory risultati e tornare al PM.

Il rilascio dell'interfaccia e la distruzione dell'open epoch sono tentati dal
percorso `fp_device_close_sync()`. Un'interruzione forzata lascia comunque lo
stato device-side epistemicamente ignoto.

## Output

I risultati sono scritti con permessi privati in:

```text
/var/tmp/goodix-d279-29-results/<UTC>-<SHA12>/
```

Contengono `operator.log` e `summary.env`. Non contengono raster, template
biometrici, PSK, CONFIG90, FDT raw o altri secret. Dopo la run copiare questi
due file nel canale concordato senza modificarli; non pubblicarli.

`operator.log` deve contenere `PRODUCTION_AUDIT_AVAILABLE=true` e il blocco
`AUDIT_*`. I valori descrivono soltanto osservazioni host-side. In particolare,
un contatore persistente noto pari a zero non dimostra assenza assoluta di
effetti persistenti sensor-side, e una deadline/cancellazione non dimostra
timeout o quiescenza del dispositivo.
