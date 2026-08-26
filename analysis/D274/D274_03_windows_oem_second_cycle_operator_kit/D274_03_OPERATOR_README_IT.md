# D274/03 — Kit Operatore Windows/OEM one-shot

## Stato di questo package

Il package ha superato review AI-PM e qualificazione nativa offline. La
baseline Git è formalmente approvata, ma il package non è approvato per una
cattura reale e non è autorizzato al live.

```text
D274_03_CORRECTIVE_IMPLEMENTED_OFFLINE=true
D274_03_POWERSHELL51_ENCODING_CORRECTIVE=IMPLEMENTED_OFFLINE
D274_03_POWERSHELL51_BOM_CORRECTIVE=PASS
D274_03_PS1_ENCODING=UTF8_WITH_BOM
D274_03_FIRST_NATIVE_QUALIFICATION_RESULT=FAIL_PARSE_BEFORE_RUNTIME
D274_03_FIRST_NATIVE_QUALIFICATION_GOODIX_PRESENT=false
D274_03_FIRST_NATIVE_QUALIFICATION_POWERSHELL=5.1.26100.8655
D274_03_FIRST_NATIVE_QUALIFICATION_HARDWARE_TOUCHED=false
D274_03_POST_BOM_NATIVE_QUALIFICATION_RESULT=FAIL_REPOSITORY_STAGE
D274_03_POST_BOM_NATIVE_QUALIFICATION_POWERSHELL_51=PASS
D274_03_POST_BOM_GIT_EXIT_DIRECT=0
D274_03_POST_BOM_GIT_EXIT_PIPE=-1
D274_03_POST_BOM_NATIVE_QUALIFICATION_HARDWARE_TOUCHED=false
D274_03_LASTEXITCODE_CORRECTIVE=PASS_OFFLINE
D274_03_WINDOWS_NATIVE_QUALIFICATION=PASS_OPERATOR_SUPPLIED
WINDOWS_NATIVE_PACKAGE_SHA256=5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87
WINDOWS_NATIVE_PACKAGE_BYTES_REHASHED_BY_AGENT=false
BASELINE_APPROVAL_BLOCKED_PENDING_NATIVE_QUALIFICATION=false
D274_03_FREEZE_REVIEW=PASS
D274_03_BASELINE_APPROVAL_REVIEW_PENDING=false
D274_03_BASELINE_APPROVED=true
D274_03_APPROVED_BASELINE_FULL_SHA=ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5
APPROVED_FOR_CAPTURE=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
```

Il record canonico separato `../D274_03_baseline_approval.json` approva
esclusivamente il commit completo
`ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5`. Il sorgente contiene un percorso
futuro di cattura passiva, ma il template runtime
`D274_03_live_authority.json` resta invariato con tutti i gate a `false`, SHA
`null` e authorization ID `null`. La baseline approval non viene letta dal
runner come authority live e il flag del launcher non la sostituisce.

Una futura esecuzione richiederà una decisione separata ed esplicita di
capture/live, un'authority one-shot dedicata, HEAD esatto, branch `main` e
live-critical set pulito. Fino ad allora `APPROVED_FOR_CAPTURE=false`,
`LIVE_AUTHORIZED=false` e `READY_FOR_LIVE=false`.

La qualificazione nativa finale è stata eseguita dall'operatore su Windows 11
Home build 26200 e Windows PowerShell Desktop 5.1.26100.8655, con Goodix
assente dal guest e senza runtime hardware, accesso USB, capture o marker.

La prima si è arrestata al parsing del runner di qualificazione su Windows
PowerShell 5.1.26100.8655, per encoding UTF-8 senza BOM degli script con testo
italiano/non-ASCII. Tutti gli script PowerShell 5.1 del package sono ora UTF-8
con BOM e il parsing 5.1 è confermato superato in nativo.

La seconda è entrata in runtime: lo stage `powershell_51` era PASS, ma la run è
fallita allo stage `repository_and_goodix_absence` con `repository Git non
individuabile` pur essendo il repository individuabile. In Windows PowerShell
5.1 `$LASTEXITCODE` non è affidabile quando il comando nativo viene inglobato in
una pipeline: la stessa invocazione Git dà `EXIT_DIRECT=0` da sola e
`EXIT_PIPE=-1` dentro `| Select-Object -First 1`. Gli script ora catturano
l'exit code nativo immediatamente, prima di trasformare l'output.

La run finale post-corrective ha chiuso tutti gli stage a PASS, inclusi selector
5.1, preflight, simulazione pre-authority, gate assenza same-run, ordine causale,
authority false e privacy contract observer/postprocessor. Il collector ha
riportato SHA-256
`5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87` e
privacy scan PASS. Il package Windows non è presente su questo host Linux:
l'hash è quindi operator-supplied e non è stato ricalcolato dall'agente.

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

La futura invocazione live verifica nativamente che `VID_27C6&PID_5125` sia
assente dal guest **nella stessa invocazione**, prima di creare il marker,
avviare TShark, chiedere l'attach o mostrare prompt per il dito. Il gate
fallisce chiuso se `Get-PnpDevice` non è disponibile o se il target è presente;
non esegue detach/attach, mutazioni PnP o aperture USB Goodix.

## Divieti operatore

- Non completare l'enrollment.
- Non creare o cambiare PIN. Una normale verifica identità con il PIN già
  configurato è ammessa solo nella UI Windows.
- Non modificare account o credenziali.
- Non eseguire un terzo contatto.
- Non rilanciare il Kit dopo PASS o FAIL.
- Non tentare recovery o retry.
- Non usare provisioning, ClearApp, flash, IAP, PSK/OTP/factory write.
- Non inviare comandi Goodix con Python, libusb o altri strumenti.

Se Windows chiede il PIN già configurato solo per verificare la tua identità,
inseriscilo direttamente nella finestra di Windows. Il Kit non deve conoscerlo
né registrarlo. Se Windows propone di creare o modificare il PIN, fermati.

La categoria ammessa è `EXISTING_PIN_AUTHENTICATION`. Le categorie terminali
sono `NEW_PIN_REQUIRED`, `PIN_CREATION_UI`, `PIN_MUTATION_UI`,
`ACCOUNT_MUTATION_UI`, `CREDENTIAL_MUTATION_UI`, `UNEXPECTED_PREREQUISITE` ed
`ENROLLMENT_COMMIT_UI`. Il Kit non legge, chiede, registra o serializza mai il
valore PIN.

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

## Qualificazione nativa completata con Goodix assente

La procedura seguente è stata eseguita una volta dall'operatore su Windows
PowerShell Desktop 5.1, con Goodix assente:

```powershell
.\run-d274-03-native-qualification.ps1
.\collect-d274-03-native-qualification-results.ps1
```

La qualificazione esegue soltanto self-test, preflight, simulazione
pre-autorizzazione, selector PowerShell 5.1, gate same-run innocuo, controllo
ACL/lingua/privacy e invocazione avversaria con authority template false. Non
crea marker, non avvia una capture, non mostra prompt per il dito e non apre
Goodix. Il collector produce esclusivamente:

```text
native_qualification_results/D274_03_windows_native_qualification_results.zip
native_qualification_results/D274_03_windows_native_qualification_results.zip.sha256
```

La qualification è PASS operator-supplied; la freeze review AI-PM è PASS e la
baseline è formalmente approvata nel record separato. Il live resta vietato:
l'eventuale capture richiede una successiva autorizzazione esplicita e
one-shot, non implicata dall'approvazione della baseline.

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

L'operatore conferma soltanto che la UI richiede il secondo dito. Un observer
Python host-side legge passivamente il pcapng in crescita, ignora correttamente
il normale trailing block incompleto e non apre il device. Quando osserva la
sequenza fino al secondo B0 strutturale, notifica il runner e causa lo stop
bounded di TShark. `SECONDO_OK` non esiste più.

Dopo lo stop, il runner attende bounded la terminazione, richiede raw presente
e non vuoto, calcola SHA-256 solo sul file finalizzato e invoca il
postprocessor hash-gated in modalità strict. Il postprocessor finale resta
l'autorità: deve rileggere il pcapng e recuperare lo stesso frame terminale
indicato dall'observer. Se il terminale è perso durante la finalizzazione, il
failure è `CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE`; nessun retry è
permesso.

## Privacy e risultati

Il raw autentico resta sotto `captures/D274_03/<authorization-id>/raw/` nel
repository privato e non entra nei bundle pubblicabili. Il sanitizer produce
solo metadata di frame, direzione, wrapper, control/IRQ/ACK, lunghezze, classe
TLS esterna, ordine, delta intra-run, conteggi e stop reason.

Sono vietati nel risultato: B0 content, plaintext TLS, immagine, raster, pixel,
hash biometrici, PSK, secret, account e valore PIN. Observer, postprocessor e
collector esportano soltanto metadata/framing bounded.

Il collector accetta esclusivamente
`D274_03_second_cycle_evidence.json` dalla directory `sanitized/` della run e
rifiuta file inattesi o campi privacy-sensitive.

## Dopo una futura run

Non rilanciare. Consegnare alla review AI-PM il bundle sanitizzato e il suo
sidecar; mantenere il raw soltanto nel repository privato. In caso di FAIL la
review deve classificare il confine raggiunto: workflow/UI, secondo IRQ2,
secondo `0x22`, ACK oppure secondo B0. Una nuova run richiede una modifica
metodologica sostanziale, nuova review e nuova autorizzazione.
