# D279/10 — osservazione passiva del terzo edge

## Stato e scopo

Questo Kit e stato preparato offline ma non e autorizzato al live. Il template
`D279_10_live_authority.json` ha tutti i gate a `false`; il flag del launcher
non puo sostituire una authority separata.

```text
D279_10_KIT_STATUS=READY_OFFLINE_PENDING_WINDOWS_NATIVE_QUALIFICATION
BASELINE_APPROVED=false
PASSIVE_CAPTURE_APPROVED=false
THIRD_CONTACT_AUTHORIZED=false
POSSIBLE_HOST_ENROLLMENT_MUTATION_ACCEPTED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
REAL_USB_EXECUTION=false
```

La futura run osserverebbe passivamente con USBPcap/TShark il traffico prodotto
dal driver OEM Windows. Il Kit non contiene un sender Goodix e non apre il
sensore. Il boundary richiesto e:

```text
secondo B0
-> release 0x34 / ACK / IRQ 0x0200
-> 0x20 / ACK / B0 discard
-> 0x50 / ACK / NAV
-> re-arm 0x32 / ACK
-> terzo IRQ 0x0002
-> 0x22 / ACK status esatto 0x01
-> terzo B0 fingerprint strutturale
-> STOP wire-driven
```

Polling FDT `0x36`/IRQ `0x0100` e housekeeping non appartenenti al lifecycle
possono essere interposti; un evento lifecycle fuori ordine o malformed causa
`FAIL_CLOSED`. Il finalizer rilegge il pcapng finalizzato, verifica SHA-256 e
richiede lo stesso frame terminale dell'observer. Un quarto lifecycle non e
accettato. Anche un failure/deadline dell'observer produce soltanto un segnale
metadata-only con la classe diagnostica, che il runner mostra all'operatore.

## Perche il metodo e diverso

1. L'ultima prova Linux si fermava deliberatamente al secondo B0; questa e una
   osservazione OEM passiva e prolunga il confine fino al terzo B0.
2. L'ipotesi nuova e che release-tail e re-arm si ripetano dopo la seconda
   immagine nella stessa sessione TLS.
3. Se la sequenza non si chiude, la capture viene arrestata senza retry e si
   analizzano i metadata della singola run prima di qualunque replan.

## Rischio non risolto

Non e provato quanti contatti richieda Windows Hello/OEM prima di persistere un
enrollment nell'account. Il terzo contatto potrebbe quindi causare una
mutazione host-side prima che l'arresto del capture possa chiudere la UI. Il
runner non nasconde questo rischio: per il live pretende esplicitamente
`possible_host_enrollment_mutation_accepted=true` oltre all'autorizzazione del
terzo contatto. Senza tale accettazione la run fallisce prima del marker.

Questo Kit non autorizza mutazioni sensor-side: restano vietati provisioning,
ClearApp, flash/IAP, OTP/factory write, cambio persistente di modalita o
comandi Goodix manuali.

## Verifiche offline disponibili

La suite Linux sintetica (14 test) non accede a capture autentiche o hardware:

```bash
python3 -m unittest -v analysis/D279/test_d279_10_third_acquisition_kit.py
```

La qualificazione nativa richiede Windows PowerShell Desktop 5.1, Python,
Wireshark/TShark e una sola interfaccia USBPcap. Il target deve essere assente
dal guest. Non avvia capture, non crea marker e non mostra prompt dito:

```powershell
cd operator_kit\d279-10-third-acquisition-observe
.\run-d279-10.ps1 -SelfTestOnly
.\run-d279-10.ps1 -NativeQualificationOnly
```

La qualificazione nativa non e ancora stata eseguita. Non eseguire la modalita
`-AutorizzoUnaSolaOsservazioneD27910`: manca sia una baseline full-SHA approvata
sia una authority live one-shot.

## Contratto della futura run

- branch esatto `development`, HEAD uguale al full SHA approvato;
- live-critical set Git pulito e byte-identico alla baseline;
- target assente nella stessa invocazione prima di marker/capture/attach;
- marker `captures/D279_10/D279_10_ONE_SHOT_CONSUMED.marker` creato con
  `CreateNew` e mai riusato o cancellato;
- un solo attach, tre contatti al massimo, zero retry e zero quarto contatto;
- PIN esistente ammesso soltanto nella UI Windows; il Kit non lo legge;
- creazione/modifica PIN, account/credential mutation, prerequisito inatteso o
  UI di commit prima del terzo edge causano stop;
- deadline host 300 s, che non prova alcun timeout device;
- cleanup sempre tenta stop observer e TShark;
- raw autentico soltanto in `captures/D279_10/<authorization-id>/raw/`;
- output condivisibile soltanto metadata-only in `sanitized/`.

I metadata non includono body B0, plaintext TLS, immagini, raster, pixel, hash
biometrici, PSK/secret o valore PIN. Dopo PASS o FAIL non rilanciare. Chiudere
la UI, scollegare il passthrough dalla VM e consegnare soltanto il JSON
sanitizzato; il raw resta nel repository privato per una review espressamente
autorizzata.
