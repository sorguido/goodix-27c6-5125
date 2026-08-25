# D274/02 — Pacchetto operatore per qualificazione nativa Windows (OFFLINE / PRELIVE)

**Questo pacchetto NON esegue alcuna capture reale, alcun attach USB, alcun
prompt per il dito, né alcuna mutazione di enrollment / account / PIN / credenziali.
È una qualificazione delle sole modalità innocue del Kit D274/01.**

L'AI esecutrice non dispone della VM Windows target: il pacchetto è preparato qui
e deve essere eseguito dall'operatore nella VM. Al termine l'operatore deve
rispedire ad AI-PM **solo** lo ZIP dei risultati (più il suo SHA256).

## Prerequisiti (nella VM Windows)

- VM Windows avviata.
- **Goodix NON attaccato alla VM** (il sensore `VID_27C6&PID_5125` deve essere assente dal guest).
- Nessuna UI di impronta aperta.
- Nessun enrollment in corso.
- Wireshark/TShark **e** USBPcap già installati.
- Windows PowerShell **5.1** (edizione *Desktop*, non PowerShell Core/pwsh).

## Esecuzione

Aprire **Windows PowerShell 5.1** e posizionarsi nella root del pacchetto
(la cartella che contiene questo file, `run-d274-02-native-qualification.ps1`
e `collect-d274-02-results.ps1`).

Abilitare l'esecuzione degli script **solo per il processo corrente** (non
persistente):

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

`Set-ExecutionPolicy -Scope Process Bypass` modifica la policy **soltanto per il
processo PowerShell corrente** e non ha effetto sul sistema né dopo la chiusura
della finestra. **Non** usare `-Scope LocalMachine`, `-Scope CurrentUser` o
`Set-ExecutionPolicy Unrestricted` in modo persistente: il pacchetto non ne ha
bisogno e non lo richiede.

Eseguire la qualificazione:

```powershell
.\run-d274-02-native-qualification.ps1
```

Lo script, in ordine:

1. verifica di essere su Windows PowerShell 5.1 (Desktop);
2. verifica che il sensore Goodix sia assente dal guest (gate fail-closed);
3. verifica che non esista un marker D274 attivo;
4. esegue `-SelfTestOnly`, `-PreflightOnly`, `-PreAuthorizationSimulationOnly`;
5. esegue il test nativo read-only sul comportamento ACL della cartella `captures/`;
6. esegue il test avversario hard-disable (il flag di autorizzazione deve fallire chiuso);
7. produce i file JSON in `results/`.

In caso di FAIL a uno stadio, lo script si ferma senza retry e scrive l'errore
letterale sanitizzato. **Non** riattaccare il dispositivo e **non** rilanciare
senza decisione di AI-PM/operatore.

## Dopo l'esecuzione

Raccogliere i risultati:

```powershell
.\collect-d274-02-results.ps1
```

Viene prodotto:

- `results/D274_02_windows_native_qualification_results.zip`
- `results/D274_02_windows_native_qualification_results.zip.sha256`

Lo ZIP contiene **solo**:

- `D274_02_selftest.json`
- `D274_02_preflight.json`
- `D274_02_preauthorization_simulation.json`
- `D274_02_native_qualification_summary.json`
- `D274_02_environment.json`
- `D274_02_hard_disable_adversarial.json`

eventuali stderr sanitizzati sono inclusi **solo** in caso di FAIL e solo se
privi di dati sensibili. Non contiene pcap, ACL raw, registry, event log,
screenshot, dati di impronta, B0, TLS, segreti, PSK, cache, DLL o firmware.

## Cosa rispedire ad AI-PM

L'operatore deve inviare ad AI-PM **soltanto**:

- `D274_02_windows_native_qualification_results.zip`
- `D274_02_windows_native_qualification_results.zip.sha256`

**Nessuna capture.** Non allegare pcap, log di sistema o materiale non richiesto.

## Sicurezza

- `D274_REAL_CAPTURE_CAPABILITY=0`
- `D274_HARD_DISABLED=true`
- `LIVE_AUTHORIZED=false`
- `READY_FOR_LIVE=false`

Il test avversario conferma che il flag nominale
`-IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture` fallisce immediatamente
con `HARD_DISABLED_D274_01`. Questo **non** è un'autorizzazione live.

## Struttura del pacchetto

```text
D274_02_windows_native_operator_package/
├── operator_kit/
│   └── d274-windows-multiframe-evidence.ps1   (copia byte-identica del Kit D274/01 approvato)
├── analysis/
│   └── D274/
│       └── d274_postprocess_multiframe_evidence.py  (copia byte-identica)
├── captures/                                   (destinazione privata, vuota)
├── results/                                    (prodotto dall'esecuzione)
├── run-d274-02-native-qualification.ps1
├── collect-d274-02-results.ps1
├── D274_02_operator_package_integrity.json   (manifest statico di integrità read-only)
└── D274_02_OPERATOR_README_IT.md
```

Prima di eseguire le modalità, il launcher verifica read-only il proprio
manifest di integrità (`D274_02_operator_package_integrity.json`): se un file
statico del pacchetto è stato alterato, la run fallisce chiusa senza produrre
alcuna capture. Il summary di run dichiara
`WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR` e
`NO_LIVE_CAPTURE_PERFORMED` (non "pending").
