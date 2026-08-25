# D274/03 — Kit Operatore Windows/OEM one-shot

## Stato di questo package

Il package è preparato esclusivamente per review AI-PM e qualificazione
offline. Non è approvato per una cattura reale.

```text
D274_03_PRELIVE_OPERATOR_KIT=READY_FOR_AI_PM_REVIEW
D274_03_BASELINE_APPROVED=false
APPROVED_FOR_CAPTURE=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
```

Il sorgente contiene un percorso futuro di cattura passiva, ma il file
`D274_03_live_authority.json` distribuito ha tutti i gate a `false`. Il flag del
launcher non sostituisce l'authority. Una futura esecuzione richiederà review,
commit SHA completo approvato, HEAD esatto, live-critical set pulito e
autorizzazione one-shot separata.

## Scopo limitato

La futura run dovrà osservare passivamente tramite USBPcap/TShark:

```text
ACK del re-arm 0x32
-> secondo IRQ 0x0002
-> secondo 0x22
-> ACK echo 0x22 e status 0x01
-> secondo B0 fingerprint strutturale
-> STOP
```

Il Kit non invia comandi Goodix: il traffico è prodotto esclusivamente dal
workflow OEM/Windows. Il secondo B0 è riconosciuto dalla forma strutturale già
chiusa (outer 7726, declared B0 7722, TLS application-data `17 03 03` con
lunghezza network-order coerente). Il contenuto non viene esportato né
decifrato. Il decode immagine non è necessario per questo boundary.

## Divieti operatore

- Non completare l'enrollment.
- Non creare o cambiare PIN.
- Non modificare account o credenziali.
- Non eseguire un terzo contatto.
- Non rilanciare il Kit dopo PASS o FAIL.
- Non tentare recovery o retry.
- Non usare provisioning, ClearApp, flash, IAP, PSK/OTP/factory write.
- Non inviare comandi Goodix con Python, libusb o altri strumenti.

Se Windows mostra una richiesta PIN, una mutazione account/credenziali, un
commit enrollment o un workflow inatteso, scegliere il relativo STOP nel
prompt del Kit senza confermare la UI.

## Modalità offline consentite ora

Aprire **Windows PowerShell Desktop 5.1** dalla root del repository. Il sensore
deve essere assente dal guest durante il preflight offline.

```powershell
cd analysis\D274\D274_03_windows_oem_second_cycle_operator_kit
.\avvia-d274-03.ps1 -SelfTestOnly
.\avvia-d274-03.ps1 -PreflightOnly
.\avvia-d274-03.ps1 -PreAuthorizationSimulationOnly
```

Queste modalità non avviano TShark in cattura, non aprono USB, non chiedono di
toccare il sensore e non consumano il marker one-shot.

Non eseguire ora:

```powershell
.\avvia-d274-03.ps1 -AutorizzoUnaSolaCatturaD27403
```

Con l'authority distribuita deve fallire chiuso prima dell'avvio della cattura.

## Stop e deadline

La deadline di 180 secondi è host-side e limita la capture. Non è una
dichiarazione sul timeout interno del sensore. I timestamp assoluti fra
sessioni di VM sospese non sono authority per la durata; valgono soltanto
l'ordine e i delta bounded della singola run.

La capture viene arrestata subito dopo la conferma operatore del secondo
contatto; il postprocessor verifica poi che il secondo B0 sia effettivamente
presente e che non esista evidenza di terzo ciclo. Qualunque mismatch chiude la
run in FAIL e non abilita un retry.

## Privacy e risultati

Il raw autentico resta sotto `captures/D274_03/<authorization-id>/raw/` nel
repository privato e non entra nei bundle pubblicabili. Il sanitizer produce
solo metadata di frame, direzione, wrapper, control/IRQ/ACK, lunghezze, classe
TLS esterna, ordine, delta intra-run, conteggi e stop reason.

Sono vietati nel risultato: B0 content, plaintext TLS, immagine, raster, pixel,
hash biometrici, PSK, secret, account e PIN.

Il collector accetta esclusivamente
`D274_03_second_cycle_evidence.json` dalla directory `sanitized/` della run e
rifiuta file inattesi o campi privacy-sensitive.

## Dopo una futura run

Non rilanciare. Consegnare alla review AI-PM il bundle sanitizzato e il suo
sidecar; mantenere il raw soltanto nel repository privato. In caso di FAIL la
review deve classificare il confine raggiunto: workflow/UI, secondo IRQ2,
secondo `0x22`, ACK oppure secondo B0. Una nuova run richiede una modifica
metodologica sostanziale, nuova review e nuova autorizzazione.
