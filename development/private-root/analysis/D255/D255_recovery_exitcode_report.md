# D255 — Recovery ExitCode e consolidamento capture private

## Esito

La capture D255 è acquisita correttamente ed è stata finalizzata e
postprocessata offline. Il failure originale era limitato alla finalizzazione
host-side: Windows PowerShell 5.1 può esporre `$null` per `ExitCode` su un
oggetto restituito da `Start-Process -PassThru` quando sono usati
`-NoNewWindow` e/o redirect. Il comportamento è documentato nel bug
[PowerShell #5421](https://github.com/PowerShell/PowerShell/issues/5421); la
proprietà .NET è nominalmente `Int32` ed è valida dopo l'uscita del processo
([Microsoft `Process.ExitCode`](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.process.exitcode?view=netframework-4.8.1)).

Il launcher conserva ora anticipatamente il process handle e tratta comunque
l'ExitCode come nullable. Il pcap presente, non vuoto e leggibile con almeno un
frame è sempre obbligatorio; stderr `218 packets captured` resta solo
diagnostica. ExitCode numerico non-zero resta terminale.

## Recovery reale

```text
RUN=captures/D255_20260822T205631772Z_85c8c41f/
CAPTURE_ACQUISITION=SUCCEEDED
OPERATOR_PHASES=COMPLETED_ZERO_FINGER
PCAP_BYTES=27684
FRAME_COUNT=218
FIRST_FRAME=1
PCAP_SHA256=802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c
RAW_PCAP_MODIFIED=false
RECOVERY_RESULT=PASS_RECOVERED_READY_FOR_OFFLINE_POSTPROCESSING
RECOVERY_MANIFEST_SHA256=deb08f42b3fe4d3991f1e9bf9283e77fcf4f4c6f42383aa3c0efc82750dcedaa
POST_CAPTURE_STATE_SNAPSHOT=NOT_RECOVERABLE_RETROACTIVELY
```

`run_clock_end.json`, `guest_topology_after_capture.json`,
`cache_after_metadata.json`, `oem_logs_after_metadata.json` e il manifest
originale non furono prodotti prima del falso failure. Non sono stati
ricostruiti usando lo stato attuale. `recovery_manifest.json` e
`recovery_report.json` sono nuovi `RECOVERED_ARTIFACT`; wire, marker, clock
iniziale e topologie presenti restano `ORIGINAL_ARTIFACT`.

Il postprocessor reale passa con target APP12509, cold attach valido e
`VALID_ZERO_FINGER`. Osserva tre `0x36`, primo seed
`aeaebfbfa4a4b2b2a7a7b3b3`, `HOST_CACHE_WIRE_MATCH`, re-entry OEM e nuovo
`0x32` accettato. L'assenza di OEM log e snapshot after impone:

```text
RESTORE_MODEL=INCONCLUSIVE_OEM_TIME_CORRELATION
DEVICE_FDT_DISARM_PROVEN=false
RESTORE_CLOSED=false
RESTORE_CLOSURE_DECISION=AI_PM_REVIEW_REQUIRED
```

## Evidenze private

`captures/` non è ignorata da `.gitignore`. La capture D255 è già nella sede
canonica privata. La precedente capture reale
`analysis/D230/work/GoodixExport/rilevamento.pcapng`, SHA-256
`50071c0f...19c184b`, resta in sede storica perché più audit eseguibili, test e
manifest referenziano quel path: spostarla qui romperebbe la riproducibilità e
allargherebbe impropriamente D255. Le capture nello snapshot Rockytkg sono
fixture di terzi e non vengono spostate. L'inventario completo è in
`D255_private_capture_inventory.json`.

Il repository privato può versionare raw evidence sotto `captures/`; bundle ed
export pubblici devono escluderla. La futura pubblicazione richiede
sanitizzazione esplicita di contenuto e history e non esiste sync automatico.

## Safety e limiti

```text
OFFLINE=true
REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
NEW_LIVE_CAPTURE_REQUIRED=false
```

La suite D255 passa con 56 test. `pwsh` non è disponibile sull'host Linux:
l'handle-caching non è stato rieseguito nativamente dopo la patch, mentre la
semantica nullable e il recovery completo sono verificati offline. Questa
limitazione non richiede una nuova capture.
