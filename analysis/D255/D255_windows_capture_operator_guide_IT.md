# D255 — Guida operatore per la cattura di evidenze APP12509 nella VM Windows

## Stato e limiti di autorità

D255 ha preparato e testato questo kit esclusivamente offline. Non ha avviato una VM, aperto USB,
eseguito software Windows/OEM, avviato TShark o usato un dito. La review AI-PM non equivale
all'autorizzazione dell'operatore e, al momento, nessuna esecuzione è autorizzata.

```text
WINDOWS_EXECUTION_ENVIRONMENT=VIRTUAL_MACHINE
VM_USB_PASSTHROUGH_METHOD=OPERATOR_GUI_MANUAL_ATTACH
D255_OPERATOR_AUTHORIZATION_REQUIRED=true
D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true
D255_FINGER_INTERACTION_ALLOWED=false
D255_EXPECTED_FINGER_INTERACTION_COUNT=0
READY_FOR_OPERATOR_RUN=false
```

Il launcher non avvia né arresta mai la VM e non collega/scollega mai automaticamente il dispositivo USB.
Non eseguire enrollment, provisioning, operazioni firmware/IAP, sostituzione della PSK, disabilitazione/
riabilitazione del dispositivo, riavvio di servizi, manutenzione o modifiche all'account/PIN.
Conservare USB raw, log OEM, cache e topologia del guest in una directory privata esterna a Git.

> **Importante:** tutti i nomi di parametri, marker e valori nei blocchi di codice devono essere usati
> esattamente in inglese come riportati. Sono stringhe operative, non testo da tradurre.

## Confine account prima dell'attach

Con Goodix assente dal guest, Windows Hello Fingerprint può legittimamente risultare nascosto,
non disponibile o non configurabile. La disponibilità dell'interfaccia fingerprint **non è quindi un gate
prima dell'autorizzazione**. Prima dell'attach si controllano soltanto:

```text
VM_WINDOWS_RUNNING=true
GOODIX_PRESENT_IN_GUEST=false
SETTINGS_SIGNIN_OPTIONS_PAGE_ACCESSIBLE=true
CURRENT_VM_FINGERPRINT_ENROLLMENT=NOT_COMPLETED
NO_NEW_PIN_CREATION_ALLOWED=true
ACCOUNT_PREREQUISITES_READY=true
SENSOR_DEPENDENT_UI_AVAILABILITY=UNKNOWN_BEFORE_ATTACH
PREATTACH_FINGERPRINT_UI_REQUIRED=false
```

Classificare `WINDOWS_HELLO_PIN_STATE` esattamente con uno dei seguenti valori:

```text
ALREADY_CONFIGURED
NOT_CONFIGURED
UNKNOWN
NOT_REQUIRED_BY_CURRENT_ACCOUNT_POLICY
```

Classificare inoltre se la policy attuale dell'account richiede un PIN per configurare la fingerprint,
usando `REQUIRED`, `NOT_REQUIRED` oppure `UNKNOWN`.

Se il PIN è `NOT_CONFIGURED` e la policy è `REQUIRED`, il preflight deve fallire **prima**
dell'autorizzazione.

Non creare o modificare mai un PIN e non usare workaround tramite registro o account.

## Revisione metodologica prima di qualsiasi futura esecuzione

1. **Che cosa cambia?**  
   L'interfaccia di setup dipendente dal sensore viene verificata soltanto dopo il singolo attach,
   dopo la prova A8 APP12509 ottenuta dal wire e dopo il bootstrap passivo. Se la UI non è pronta,
   la run viene comunque conservata come evidenza bootstrap parziale.

2. **Quale ipotesi viene testata?**  
   Il cold attach può produrre evidenza bootstrap APP12509 anche se l'account Windows corrente
   non può entrare nel wizard fingerprint di Windows Hello. Se invece il wizard è disponibile,
   due sessioni di cancel senza dito possono aggiungere evidenza circoscritta sul lifecycle.

3. **Cosa fare se fallisce nello stesso punto?**  
   Conservare e sanitizzare la capture bootstrap già consumata, non riprovare e restituire
   l'evidenza ad AI-PM. Qualunque nuova strategia relativa a UI/account richiede un kit corretto,
   review, approvazione della baseline e una nuova autorizzazione esplicita.

## Stato iniziale richiesto e controllo sull'host

```text
VM_WINDOWS_RUNNING=true
GOODIX_PRESENT_ON_LINUX_HOST=true
GOODIX_PRESENT_IN_WINDOWS_GUEST=false
GUEST_USB_CAPTURE_RUNNING=false
D255_AUTHORIZATION_CONSUMED=false
```

L'operatore può individuare il dispositivo sull'host in sola lettura con:

```bash
lsusb -d 27c6:5125
```

e può ispezionare l'esatto device node con:

```bash
fuser
```

Non usare `sudo`, non terminare eventuali processi che lo detengono, non arrestare `fprintd`
e non modificare ownership o permessi.

Separatamente, nel guest Windows, confermare che:

```powershell
Get-PnpDevice -PresentOnly
```

non mostri alcun dispositivo con:

```text
VID_27C6&PID_5125
```

## Self-test e preflight nel guest

Per prima cosa eseguire il self-test, che non usa hardware:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -SelfTestOnly `
  -OutputRoot "D:\Goodix-D255-SelfTest"
```

Risultato atteso:

```text
D255_POWERSHELL_SELFTEST=PASS
```

con:

- hardware action count uguale a zero;
- autorizzazione non consumata.

Successivamente aprire:

**Impostazioni → Account → Opzioni di accesso**

soltanto quanto basta per classificare lo stato account/PIN.

Non richiedere e non tentare di aprire in questa fase **Riconoscimento dell'impronta digitale**.

Elencare poi le interfacce di cattura con:

```powershell
tshark -D
```

Selezionare:

- l'unica interfaccia USBPcap, se ce n'è una sola;
- oppure tutte le interfacce candidate contemporaneamente, se non è possibile determinare
  prima dell'attach quale controller USB virtuale riceverà il passthrough.

Non indovinare mai arbitrariamente una singola interfaccia tra più candidate.

### Esempio di preflight con PIN già configurato

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -PreflightOnly `
  -OutputRoot "D:\Goodix-D255-Raw" `
  -TsharkPath "C:\Program Files\Wireshark\tshark.exe" `
  -CaptureInterface "USBPcap1" `
  -VmGuestReadyConfirmation "VM_WINDOWS_RUNNING_GOODIX_ABSENT_FROM_GUEST" `
  -AccountPrerequisiteConfirmation "SIGNIN_OPTIONS_CHECKED_NO_NEW_PIN_CHANGE" `
  -WindowsHelloPinState "ALREADY_CONFIGURED" `
  -FingerprintSetupPinRequirement "UNKNOWN"
```

Risultato atteso:

```text
D255_PREFLIGHT_ONLY=PASS
```

con:

- prerequisiti account pronti;
- disponibilità della UI del sensore ancora classificata come sconosciuta prima dell'attach;
- hardware action count uguale a zero;
- autorizzazione non consumata.

I log OEM/WBDI sono fonti di evidenza opzionali. Se non ne viene individuato
alcuno, il report deve mostrare `OEM_LOG_STATUS=ABSENT` e il preflight deve
proseguire. Se esistono, la discovery automatica o un `-OemLogPath` esplicito
mantengono gli snapshot before/after e riportano `OEM_LOG_STATUS=PRESENT`. La
cache Goodix è classificata separatamente come
`GOODIX_CACHE_STATUS=PRESENT|ABSENT`. Un path log o cache fornito esplicitamente
ma illeggibile continua invece a far fallire il preflight prima
dell'autorizzazione.

## Singola esecuzione autorizzata — NON attualmente autorizzata

> **NON ESEGUIRE QUESTA SEZIONE ORA.**  
> Questa è la procedura prevista per il futuro run singolo, ma al momento serve soltanto per studio.

Solo dopo:

1. review AI-PM positiva;
2. approvazione dell'esatto commit SHA live-critical;
3. nuova autorizzazione esplicita per **una singola run**;

lo stesso comando potrà essere eseguito senza `-PreflightOnly` e aggiungendo:

```powershell
  -CaptureDurationSeconds 300 `
  -Authorization "--i-authorize-one-d255-windows-oem-evidence-capture"
```

Tutti i gate relativi a:

- assenza del device nel guest;
- interfaccia di capture;
- account;
- path;
- spazio disco;
- path log/cache esplicitamente configurati;
- clock;
- topologia;
- runtime;

devono essere superati **prima** che l'autorizzazione venga consumata.

La sola assenza di log OEM o cache viene registrata, ma non è un gate
live-critical.

Dopo la prova che la capture è realmente partita, eseguire **esattamente un singolo attach manuale
host → VM tramite GUI**.

Non fare detach/re-attach.

L'ordine delle evidenze successivamente imposto da marker e wire è:

```text
VM_GUEST_READY
GUEST_TOPOLOGY_BEFORE
ACCOUNT_PREREQUISITES_CHECKED
CAPTURE_STARTED
VM_USB_ATTACH_BEGIN
VM_USB_ATTACH_END
GUEST_27C6_5125_PRESENT
A8_APP12509_PROVEN              # derived from exact target wire response
PASSIVE_BOOTSTRAP_SETTLED
HELLO_SETUP_UI_CHECK_BEGIN
```

Solo a questo punto aprire:

**Impostazioni → Account → Opzioni di accesso → Riconoscimento dell'impronta digitale (Windows Hello) → Configura/Aggiungi un'impronta**

senza toccare il sensore.

Il launcher presenta una scelta chiusa tra quattro sole opzioni:

```text
READY_WAITING_FOR_FINGER
UI_UNAVAILABLE
NEW_PIN_REQUIRED
UNEXPECTED_PREREQUISITE
```

### Caso `READY_WAITING_FOR_FINGER`

Solo `READY_WAITING_FOR_FINGER` permette di proseguire con due cancellazioni senza dito:

```text
HELLO_SETUP_UI_READY
OEM_SESSION_BEGIN
OEM_WAITING_NO_FINGER
CANCEL_NO_FINGER_BEGIN
CANCEL_NO_FINGER_END
REENTRY_BEGIN
REENTRY_WAITING_NO_FINGER
REENTRY_CANCEL_BEGIN
REENTRY_CANCEL_END
REENTRY_END
```

Durante l'intera sequenza:

**NON TOCCARE MAI IL SENSORE.**

### Tutti gli altri casi

Qualunque altra scelta è terminale per la fase restore.

Non:

- creare un PIN;
- cambiare account;
- cambiare percorso UI;
- eseguire recognition;
- toccare il sensore;
- scollegare il dispositivo;
- riprovare;
- riaprire il wizard.

La run resta consumata, ma TShark viene lasciato arrivare al termine della durata limitata prevista.

Il launcher richiede quindi:

- uscita TShark con codice zero;
- file non vuoto;
- lettura di verifica riuscita di almeno un frame;

prima di emettere:

```text
D255_RUN_RESULT=PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE
D255_RESTORE_PHASE_RESULT=WINDOWS_HELLO_SETUP_PREREQUISITE_MISSING_AFTER_ATTACH
BOOTSTRAP_EVIDENCE_PRESERVED=true
RESTORE_EVIDENCE_ACQUIRED=false
RESTORE_CLOSED=false
PARTIAL_CAPTURE_STOP_METHOD=BOUNDED_CAPTURE_TIMER_EXHAUSTED
PARTIAL_CAPTURE_FILE_VALIDATION=TSHARK_EXIT_ZERO_NONEMPTY_PCAPNG
```

In altre parole: anche se Windows Hello non fosse utilizzabile, **la parte bootstrap già catturata viene conservata**.

## Post-processing offline e semantica del restore

La run privata deve essere elaborata soltanto da Linux e fuori dal repository:

```bash
python3 analysis/D255/d255_postprocess_windows_evidence.py \
  --run-dir /external/private/D255_RUN \
  --manifest /external/private/D255_RUN/input_manifest.json \
  --manifest-sha256 MANIFEST_SHA256_FROM_SIDECAR \
  --output-dir /tmp/D255_sanitized
```

Il postprocessor accetta sia risultati completi sia risultati parziali.

### Risultato parziale

Un risultato con UI non disponibile:

- non richiede i marker cancel/re-entry;
- richiede comunque capture avviata prima dell'attach;
- richiede un singolo episodio descriptor;
- richiede prova PnP nel guest;
- richiede A8 APP12509 esatto.

Conserva comunque l'analisi di:

- bootstrap;
- cache;
- primo `0x36`;

e dichiara assenza di evidenza restore.

### Risultato completo

In una run completa, una re-entry OEM riuscita oppure l'accettazione di un nuovo arm `0x32`
prova soltanto che **la re-entry è possibile**.

Non prova che il precedente FDT arm sia stato realmente disarmato.

Il risultato sanitizzato riporta separatamente:

- cancel host;
- sequenza wire;
- close del device;
- D0Exit/D0Entry;
- re-entry;
- accettazione del nuovo arm;
- eventuale prova di cancel device-side;
- lifetime del precedente arm;
- classe dell'evidenza restore;

e mantiene:

```text
DEVICE_FDT_DISARM_PROVEN=false
RESTORE_CLOSED=false
RESTORE_CLOSURE_DECISION=AI_PM_REVIEW_REQUIRED
```

Quindi la decisione finale sul restore resta deliberatamente affidata alla review AI-PM
dell'evidenza reale.

## Invariante zero-finger

Qualunque presenza, nella finestra operatore, di:

```text
IRQ 0x0002
0x22 [01 00]
```

oppure di un image path correlato di dimensione compatibile con una fingerprint
**invalida l'evidenza restore**.

Nessun risultato autorizza automaticamente un retry.
