# D279/54 — capture passiva di una identify OEM Windows

## Stato e scopo

Questo kit prepara una sola osservazione USBPcap di una verifica fingerprint
Windows Hello già configurata. Non esegue enrollment, non contiene un sender
Goodix e non invia comandi Linux al sensore: avvia soltanto TShark/USBPcap,
verifica la presenza del target e registra le conferme numeriche
dell'operatore.

```text
D279_54_KIT_STATUS=READY_OFFLINE_PENDING_WINDOWS_NATIVE_QUALIFICATION_AND_HUMAN_GATE
OEM_IDENTIFY_AUTHORIZED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

Il template authority versionato è intenzionalmente chiuso. La sua presenza
non autorizza una run e nessuna baseline è auto-approvata.

## Perché serve

Il core libfprint/SIGFM supporta già una vera `fp_device_identify()` host-only,
ma il protocollo production conosciuto è enrollment-specific. Il lifecycle
target-proven D278/14 raggiunge `STOP` dopo due acquisizioni; non prova quale
sia la terminazione OEM di una singola identify. Una capture passiva del vero
workflow Windows è il modo minimo per osservare questo boundary senza
inventare una sequenza sensor-reaching Linux.

## Rischio e prerequisiti

Prerequisiti obbligatori:

- VM Windows con snapshot pre-run confermato e target inizialmente assente;
- una impronta Windows Hello OEM già registrata prima dello snapshot;
- Windows PowerShell Desktop 5.1, TShark e una sola interfaccia USBPcap;
- branch `development`, HEAD uguale al full SHA approvato e live-critical set
  pulito;
- authority per-attempt separata con tutte le conferme vere e un ID nuovo
  `D27954_...`;
- autorizzazione esplicita dell'Utente per quella singola run.

Anche una verifica ordinaria può aggiornare cache host o un template adattivo
sensor-side. Lo snapshot può ripristinare la VM, non lo stato interno del
sensore. L'accettazione di questo rischio è per-attempt e non autorizza flash,
IAP, ClearApp, provisioning, PSK/OTP/factory write, enrollment, delete o retry.

## Procedura futura, solo dopo autorizzazione

1. Con target assente, eseguire:

   ```powershell
   cd operator_kit\d279-54-oem-passive-identify-observe
   .\run-d279-54.ps1 -SelfTestOnly
   .\run-d279-54.ps1 -NativeQualificationOnly
   ```

2. Creare e verificare lo snapshot pre-run.
3. Preparare fuori dal template versionato una authority per-attempt con full
   SHA approvato e tutte le conferme richieste.
4. Avviare una sola volta:

   ```powershell
   .\run-d279-54.ps1 -AutorizzoIdentifyOemPassivoD27954 -AuthorityPath <authority.json>
   ```

5. Seguire soltanto i menu numerici. Dopo l'attach, bloccare Windows con
   `Win+L`, tentare una sola verifica fingerprint con il dito già registrato e
   tornare alla console senza ripetere il contatto.
6. Il runner conserva cinque secondi di tail, arresta la capture, ne verifica
   leggibilità e hash e termina.
7. Prima di qualsiasi restore, esportare fuori dalla VM e fuori dal disco
   coperto dallo snapshot entrambe le directory `raw/` e `sanitized/` indicate
   dal runner. Verificare l'export, poi ripristinare lo snapshot.

## Output e stop condition

Gli output sono attempt-scoped:

```text
captures/D279_54/<attempt_id>/raw/wire.pcapng
captures/D279_54/<attempt_id>/sanitized/operator_events.json
captures/D279_54/<attempt_id>/sanitized/attempt_status.json
```

Il raw è privato. Il materiale sanitizzato contiene solo tempi, risultato UI,
contatori host e hash; non contiene payload USB, immagini, template, PIN o
secret.

La run è single-shot. Qualunque no-match, PIN fallback, anomalia, processo
terminato, collisione output o failure chiude l'attempt senza retry. Un nuovo
tentativo richiede restore quando indicato, nuova authority, nuovo attempt ID
e nuova autorizzazione esplicita.
