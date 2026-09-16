# D274/03 — Preparazione OFFLINE Kit Windows/OEM secondo ciclo

```text
OUTCOME=READY_FOR_AI_PM_REVIEW
ADVANCEMENT=NON_HARDWARE_ARCHITECTURAL_AND_EXECUTABLE_PRELIVE_PREPARATION;NO_NEW_DEVICE_EVIDENCE
EXECUTABLE_CLOSURE=PASS_OFFLINE_PYTHON_EXECUTION_POWERSHELL51_STATIC_CONTRACT
RESIDUAL_BLOCKER_OR_RISK=WINDOWS_NATIVE_D274_03_NOT_EXECUTED;BASELINE_REVIEW_PENDING;CAPTURE_NOT_APPROVED;SECOND_TARGET_CYCLE_NOT_OBSERVED
CANONICAL_DOCUMENTATION=UPDATED_HIGH_LEVEL_ROADMAP_D274_02_HISTORY_D274_03_BOUNDARY
BUNDLE=analysis/D274/D274_03_windows_oem_second_cycle_prelive_bundle.zip
```

## Esito

È stata creata una nuova authority D274/03 separata da D274/01 e D274/02. Il
Kit è pronto per review AI-PM, non per il live. Tutta la superficie operatore è
in italiano. Il sorgente contiene un percorso futuro live-capable, ma il
template authority consegnato ha baseline/capture/live a `false` e nessun SHA;
il runner verifica inoltre HEAD, branch, live-critical set, ACL privata e
marker one-shot atomico prima di poter avviare TShark.

Il percorso futuro non invia comandi Goodix. Avvia un solo processo di cattura
passiva USBPcap/TShark bounded a 180 secondi; il traffico viene prodotto dal
workflow candidato `WINDOWS_HELLO_SETUP_CANDIDATE_NO_COMMIT`. PIN, account,
credenziali, commit enrollment, workflow inatteso, terzo ciclo e retry sono
terminali e non autorizzati.

## Riesame metodologico

1. D274/02 qualificava nativamente un package hard-disabled; D274/03 prepara
   la nuova authority one-shot del secondo ciclo, senza eseguire hardware ora.
2. L'ipotesi nuova è: ACK re-arm `0x32` → nuovo finger-down OEM → IRQ `0x0002`
   → `0x22` → ACK echo `0x22`, status `0x01` → secondo B0 fingerprint.
3. Un failure futuro non abilita retry: review offline del raw e
   classificazione UI / IRQ2 / dispatch `0x22` / ACK / B0. Una nuova run
   richiederà metodo sostanzialmente diverso, review e autorizzazione nuove.

## Boundary e privacy

Il matcher conserva il lifecycle precedente per distinguere il re-arm dal
primo arm, ma il nuovo successo termina al secondo B0. Il B0 usa il contratto
strutturale già chiuso: outer 7726, declared 7722, TLS application-data
`17 03 03` con lunghezza big-endian coerente. Nessun decode immagine è richiesto.

L'evidence JSON strict esporta soltanto frame index, direzione, wrapper,
control/IRQ/ACK, lunghezze, classe TLS esterna, delta intra-run, stop reason e
conteggi. Raw, B0 content, plaintext, immagine, raster, pixel, hash biometrici,
PSK e secret non entrano nel risultato o nel bundle step-local.

## Verifica

- 22/22 test D274/03 PASS, inclusi success e tutti i failure richiesti.
- 30/30 test regression D274/01 PASS.
- La capture storica D263 resta `MISSING_SECOND_IRQ2` e non è promossa.
- Schema/manifest/authority JSON validi; `git diff --check` PASS.
- Windows PowerShell 5.1 non è disponibile sull'host Linux corrente: nessuna
  esecuzione nativa D274/03 è dichiarata. I pattern condivisi sono quelli già
  qualificati nativamente in D274/02; questa non è approvazione live.

## Cleanup D274/02

Il manuale separa ora tre snapshot: prima run FAIL source-scan, seconda run FAIL
`.Count`, terza run PASS. Nessun blocco mescola più `SELFTEST_RUNTIME=FAIL` con
`D274_02_WINDOWS_NATIVE_QUALIFICATION=PASS`; i vecchi next-boundary sono marcati
storici o sostituiti dal boundary corrente. D274/02 resta CLOSED/PASS.

```text
D274_02_TECHNICAL_REGRESSION=false
D274_02_REOPEN_REQUIRED=false
D274_02_MANUAL_HISTORICAL_STATE_CLEANUP=COMPLETED
D274_03_PRELIVE_OPERATOR_KIT=READY_FOR_AI_PM_REVIEW
D274_03_OPERATOR_LANGUAGE=ITALIAN
D274_03_REAL_CAPTURE_CAPABILITY=0_CURRENT_AUTHORITY_TEMPLATE
D274_03_BASELINE_APPROVED=false
APPROVED_FOR_CAPTURE=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED
REAL_CAPTURE_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
AUTOMATIC_RETRY_COUNT=0
SOURCE_CONTAINS_FUTURE_LIVE_PATH=true
LIVE_PATH_EXECUTED=false
LIVE_PATH_AUTHORIZED=false
```

## Git hygiene

```text
initial_branch=development
initial_full_head=e6ef633d6140a316adf773beb9e3cbe2bd7bc14f
final_branch=development
final_head=e6ef633d6140a316adf773beb9e3cbe2bd7bc14f
commit_created=false
git_status=DIRTY_EXPECTED_D274_03_STEP_LOCAL_CHANGES_ONLY
unexpected_files=NONE
```

Changed files:

```text
Goodix 27c6 5125 manuale tecnico.md
analysis/D274/D274_03_execution_manifest.json
analysis/D274/D274_03_test_results.json
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_OPERATOR_README_IT.md
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_evidence_schema.json
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_kit_manifest.json
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_live_authority.json
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/avvia-d274-03.ps1
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/collect-d274-03-results.ps1
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/invoke-d274-03-live-once.ps1
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/raw/.gitkeep
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/results/.gitkeep
analysis/D274/D274_03_windows_oem_second_cycle_prelive_bundle.zip
analysis/D274/D274_03_windows_oem_second_cycle_prelive_bundle.zip.sha256
analysis/D274/D274_03_windows_oem_second_cycle_prelive_bundle_manifest.json
analysis/D274/D274_03_windows_oem_second_cycle_prelive_report.md
analysis/D274/test_d274_03_second_cycle_operator_kit.py
```
