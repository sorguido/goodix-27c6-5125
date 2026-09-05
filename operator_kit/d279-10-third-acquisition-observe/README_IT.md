# D279/10 — capture passiva del primo enrollment OEM completo

## Stato

Il Kit è stato ripianificato e verificato soltanto offline. Non è autorizzato
al live. Il template `D279_10_live_authority.json` è interamente chiuso e la
qualificazione nativa Windows della nuova versione è ancora pendente.

```text
D279_10_KIT_STATUS=READY_OFFLINE_PENDING_WINDOWS_NATIVE_QUALIFICATION
FULL_OEM_ENROLLMENT_AUTHORIZED=false
HOST_VM_ENROLLMENT_MUTATION_ACCEPTED=true
POSSIBLE_SENSOR_SIDE_TEMPLATE_PERSISTENCE_ACCEPTED=false
SNAPSHOT_PRERUN_CONFIRMED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

Il launcher non contiene sender Goodix. Avvia soltanto USBPcap/TShark e un
observer Python metadata-only; sono vietati retry automatici. La capture parte
prima del collegamento e prosegue fino alla conferma reale dell’UI Windows che
l’impronta è registrata, più cinque secondi di tail terminale. Il numero di
contatti non è predefinito. Il terzo B0 è registrato come milestone, ma non
ferma observer o capture.

## Rischio sensor-side: esito della review

Lo snapshot risolve la mutazione host-side della VM, inclusa la prima impronta
Windows Hello, ma non può ripristinare il sensore. Le evidenze versionate
provano che le famiglie `0xE0`, `0xA4`, `0xF0`, `0xF4` hanno capacità
persistenti/manutentive. Inoltre la superficie statica di `gfusb.dll` contiene
entrypoint e messaggi PBA quali `HwAddOrUpdateTemplate`, `HwDeleteTemplate` e
“write a template to flash”. Non è però disponibile una prova target-local che
separi con certezza il completamento ordinario WBDI/Windows Hello da ogni
percorso di persistenza template sensor-side; il traffico applicativo può
anche essere cifrato.

Di conseguenza l’assenza nel pcap delle famiglie note non autorizza il claim
“nessuna mutazione sensor-side”. Il finalizer segnala le famiglie visibili, ma
mantiene il rischio non escluso. Il percorso live pretende perciò una decisione
esplicita sul campo
`possible_sensor_side_template_persistence_accepted`; il template resta
`false`. Non impostarlo autonomamente.

## Snapshot ed evidenze

La procedura preferita è:

1. preparare e qualificare repository e Kit nella VM;
2. creare lo snapshot pre-run con il target ancora assente;
3. fornire una authority per-attempt distinta;
4. eseguire una sola invocazione, senza retry interno;
5. prima di qualsiasi restore, esportare **fuori dalla VM e fuori dal disco
   coperto dallo snapshot** entrambe le directory indicate dal launcher:

   ```text
   captures/D279_10/<attempt_id>/raw/
   captures/D279_10/<attempt_id>/sanitized/
   ```

6. verificare l’export, poi applicare l’eventuale restore.

Il raw contiene il pcapng autentico e il journal append-only dell’observer; è
privato e non condivisibile senza audit. `sanitized/` contiene eventi operatore,
risultato observer, stato dell’attempt e, in caso di successo, evidenza
metadata-only. Un restore prima dell’export perde entrambe le directory.

## Attempt e riuso del Kit

Non esiste più un marker globale. Ogni authority live deve avere un
`authorized_attempt_id` nuovo nel formato `D27910_...`. Il runner crea
`captures/D279_10/<attempt_id>/` e `attempt.lock` con semantica CreateNew: un
ID già esistente viene rifiutato senza cancellare o sovrascrivere nulla.

Dopo un failure il medesimo Kit può essere avviato manualmente in una nuova
invocazione, solo con una nuova authority/autorizzazione e un nuovo attempt ID.
Il launcher non effettua mai retry. `attempt_status.json` classifica:

- `RERUN_WITHOUT_RESTORE_REASONABLE` soltanto se il failure avviene prima di
  attach e avvio wizard;
- `RESTORE_SNAPSHOT_REQUIRED_STATE_UNCERTAIN` dopo attach o avvio wizard;
- `RESTORE_SNAPSHOT_REQUIRED_BEFORE_ANOTHER_FIRST_ENROLLMENT` dopo una
  conclusione reale, perché la VM non è più nello stato “prima impronta”.

La classificazione è prudenziale e non sostituisce l’export delle evidenze.

## Input numerici e workflow

Ogni `Read-Host` passa da un unico menu numerico breve, ristampato a ogni
richiesta. L’operatore non deve digitare descrizioni libere.

- snapshot: `1` conferma, `0` stop;
- attach: `1` collegato, `0` stop;
- setup: `1` pronto, `2` autenticazione con PIN esistente, `3` anomalia,
  `0` stop;
- dopo ogni contatto: `1` la UI ne richiede un altro, `2` la UI conferma
  realmente la registrazione, `3` anomalia, `0` stop.

Il PIN esistente va inserito solo nell’UI Windows. Creazione/modifica di PIN o
credenziali è una condizione terminale. Non indicare `2` finché Windows non ha
mostrato una conferma reale di registrazione.

## Failure e stop condition

Il runner fallisce chiuso su authority/baseline/branch errati, live-critical
set sporco, target presente al preflight, dipendenze mancanti, tentativo già
esistente, capture/observer terminati, prerequisiti inattesi, output collision
o finalizzazione incoerente. Il cleanup tenta sempre l’arresto di observer e
TShark. Nessun failure provoca un nuovo attach, un nuovo contatto o un retry.

La sola stop condition di successo è:

```text
CONFERMA_REALE_UI_WINDOWS
+ CAPTURE_TAIL_HOST_5S
+ PCAP_FINALIZZATO_E_HASH_VERIFICATO
```

Il default libfprint di cinque stage non viene usato come evidenza OEM.

## Verifiche offline e qualificazione nativa

La suite sintetica non usa hardware né capture autentiche:

```bash
python3 -m unittest -v analysis/D279/test_d279_10_third_acquisition_kit.py
```

La qualificazione nativa richiede Windows PowerShell Desktop 5.1, Python,
TShark e una sola interfaccia USBPcap, con target assente, branch `development`
e live-critical set pulito. Non avvia la capture e non presenta prompt dito.

PowerShell 5.1 può promuovere a `NativeCommandError` lo stderr ordinario di un
programma nativo quando `$ErrorActionPreference` è `Stop`, anche con exit code
zero. Il runner usa quindi un wrapper ristretto alla singola invocazione: porta
temporaneamente la preference a `Continue`, cattura stdout/stderr, salva
`$LASTEXITCODE` e ripristina sempre `Stop` in `finally`. La qualificazione prova
prima sia `stderr + exit 0` sia un exit intenzionale `7`; solo dopo esegue la
suite e ne verifica l’exit code reale.

Comandi:

```powershell
cd operator_kit\d279-10-third-acquisition-observe
.\run-d279-10.ps1 -SelfTestOnly
.\run-d279-10.ps1 -NativeQualificationOnly
```

L'accettazione già concessa della mutazione host-side è registrata nel template
ma non autorizza il live. Non eseguire `-AutorizzoEnrollmentOemCompletoD27910`:
mancano baseline full-SHA approvata, authority per-attempt e decisione esplicita
sul rischio sensor-side.
