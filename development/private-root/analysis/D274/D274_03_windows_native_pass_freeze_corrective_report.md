# D274/03 — Windows native qualification PASS freeze corrective

```text
OUTCOME=READY_FOR_AI_PM_REVIEW — HOST_ONLY_CORRECTIVE_FREEZE_COMPLETE;BASELINE_NOT_APPROVED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED — WINDOWS_POWERSHELL_DESKTOP_5_1_ALL_STAGE_PASS_OPERATOR_SUPPLIED;NO_DEVICE_SIDE_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS — WINDOWS_NATIVE_OPERATOR_SUPPLIED_PLUS_LINUX_OFFLINE_REGRESSION
RESIDUAL_BLOCKER_OR_RISK=FORMAL_AI_PM_FREEZE_REVIEW_AND_SEPARATE_EXPLICIT_BASELINE_APPROVAL_REQUIRED_BEFORE_ANY_LIVE
CANONICAL_DOCUMENTATION=UPDATED — HIGH_STATE,ROADMAP,D274_03_WINDOWS_QUALIFICATION_AND_OPERATING_PROCESS
BUNDLE=analysis/D274/D274_03_windows_native_pass_freeze_corrective_bundle.zip;SHA256_IN_EXTERNAL_SIDECAR
```

## Evidenza nativa acquisita dall'operatore

La qualification finale è stata eseguita dall'operatore su Windows 11 Home
build 26200 con Windows PowerShell Desktop 5.1.26100.8655 e Goodix
`27c6:5125` assente dalla guest. Il summary fornito riporta PASS per tutti gli
stage, nessuna capture reale, nessuna apertura USB, nessuna interazione dito,
nessun comando Goodix, nessun retry e nessuna scrittura persistente.

```text
WINDOWS_NATIVE_QUALIFICATION=PASS_OPERATOR_SUPPLIED
WINDOWS_NATIVE_PACKAGE_SHA256=5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87
WINDOWS_NATIVE_PACKAGE_BYTES_REHASHED_BY_AGENT=false
WINDOWS_NATIVE_PRIVACY_SCAN=PASS_OPERATOR_SUPPLIED
WINDOWS_POWERSHELL_5_1_NATIVE_RUNTIME=NOT_AVAILABLE_ON_LINUX_HOST
```

Il package Windows non è materialmente presente nell'ambiente dell'agente. Lo
SHA-256 sopra è quindi registrato con provenance operatore e non dichiarato
come ricalcolato localmente.

## Due micro-fix consolidati

1. Nel gate `causal_source_order`, il literal cercato nel sorgente del runner
   usa apici singoli:

   ```powershell
   $captureAt = $runnerSource.IndexOf('Start-Process -FilePath $TsharkPath')
   ```

   Sotto `Set-StrictMode`, PowerShell 5.1 non tenta così di espandere nel
   processo di qualification la variabile `$TsharkPath` del sorgente ispezionato.

2. Il privacy contract è verificato nei suoi owner reali: l'observer importa e
   usa `inspect_growing_capture`; il postprocessor dichiara
   `"biometric_plaintext_exported": False`. L'observer non è stato modificato
   per duplicare artificialmente la costante.

Il runner PowerShell conserva il BOM `EF BB BF` e il contenuto è decodificabile
come UTF-8 con BOM senza mojibake.

## Regression guard e test

La suite D274/03 è stata estesa da 41 a 46 casi. I nuovi guard coprono literal
TShark non interpolato, ownership observer/postprocessor del privacy contract,
assenza di letture PIN/credenziali, assenza di invocazioni qualification per
USB/capture attive e authority/counter congelati. I guard preesistenti
continuano a coprire BOM di tutti i cinque `.ps1`, `$LASTEXITCODE` prima di
ogni trasformazione, same-run gate, marker one-shot e percorso passivo.

```text
D274_03_TESTS=PASS_46_OF_46
D274_POSTPROCESS_MULTIFRAME_TESTS=PASS_30_OF_30
TOTAL_PERTINENT_D274_TESTS=PASS_76_OF_76
OBSERVER_CLI_HELP=PASS
POSTPROCESSOR_CLI_HELP=PASS
JSON_VALIDATION=PASS
GIT_DIFF_CHECK=PASS
```

## Authority e safety invariati

```text
D274_03_BASELINE_APPROVED=false
APPROVED_FOR_CAPTURE=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
REAL_CAPTURE_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_GOODIX_COMMAND_COUNT=0
AUTOMATIC_RETRY_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
```

Il PASS nativo rimuove soltanto il blocker della qualification host-only. Il
nuovo processo operativo è: loop correttivo rapido con Goodix assente, freeze e
review formale dopo PASS, eventuale live one-shot solo dopo approvazione
separata della baseline. Nessuna baseline è stata promossa autonomamente.

## File modificati

```text
Goodix 27c6 5125 manuale tecnico.md
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_OPERATOR_README_IT.md
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_kit_manifest.json
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/run-d274-03-native-qualification.ps1
analysis/D274/test_d274_03_second_cycle_operator_kit.py
```

Gli altri file aggiunti in questo freeze sono report, risultati test, manifest
di esecuzione/bundle, ZIP e sidecar step-local.
