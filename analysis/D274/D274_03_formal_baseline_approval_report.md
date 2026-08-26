# D274/03 — Formal baseline approval

```text
OUTCOME=PASS — FORMAL_BASELINE_APPROVAL_RECORDED_OFFLINE
ADVANCEMENT=GOVERNANCE_AUTHORITY_STATE_CHANGED;NO_DEVICE_SIDE_ADVANCEMENT
EXECUTABLE_CLOSURE=NOT_APPLICABLE — NO_RUNTIME_OR_LIVE_CRITICAL_FILE_CHANGED
RESIDUAL_BLOCKER_OR_RISK=SEPARATE_EXPLICIT_ONE_SHOT_CAPTURE_LIVE_AUTHORIZATION_REQUIRED
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D274/D274_03_formal_baseline_approval_bundle.zip;SHA256_IN_EXTERNAL_SIDECAR
```

## Baseline verificata e decisione

Prima di ogni modifica sono stati verificati:

```text
BRANCH=main
INITIAL_HEAD=ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5
ORIGIN_MAIN=ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5
HEAD_VS_ORIGIN_MAIN_DIVERGENCE=0_LEFT_0_RIGHT
INITIAL_WORKTREE=CLEAN
```

La review AI-PM del freeze correttivo è PASS e la Windows native qualification
è PASS operator-supplied. La baseline formalmente approvata è esclusivamente:

```text
D274_03_APPROVED_BASELINE_FULL_SHA=ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5
WINDOWS_NATIVE_PACKAGE_SHA256=5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87
FREEZE_BUNDLE_SHA256=d7e5db36a0efec05ab33c82c221beb42c91aea4772a059764930ead5d8ed1d6b
```

## Modello di authority

È stato scelto un record canonico separato,
`analysis/D274/D274_03_baseline_approval.json`, perché l'approvazione della
baseline è una decisione di governance distinta dalla futura authority live.
Il record fissa il full SHA e le provenance della qualification/freeze, ma
mantiene capture, live e ready false e non crea alcun authorization ID.

`D274_03_live_authority.json` e tutti i file live-critical sono rimasti
byte-invariati rispetto alla baseline approvata. Il runner non legge il nuovo
record come authority runtime e continua a richiedere separatamente
`baseline_approved=true`, `approved_for_capture=true`, `live_authorized=true`
e un one-shot ID valido nel live-authority. Il template distribuito conserva
tutti questi gate a false/null. Il ramo `-NativeQualificationOnly`, che richiede
esplicitamente il template chiuso, non è stato degradato.

## File modificati o aggiunti

```text
Goodix 27c6 5125 manuale tecnico.md
analysis/D274/D274_03_baseline_approval.json
analysis/D274/D274_03_formal_baseline_approval_bundle_manifest.json
analysis/D274/D274_03_formal_baseline_approval_execution_manifest.json
analysis/D274/D274_03_formal_baseline_approval_report.md
analysis/D274/D274_03_formal_baseline_approval_test_results.json
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_kit_manifest.json
analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_OPERATOR_README_IT.md
analysis/D274/test_d274_03_second_cycle_operator_kit.py
```

Bundle e sidecar sono output generati dello stesso step e sono elencati nel
manifest del bundle.

## Verifica offline

```text
D274_03_OPERATOR_KIT_TESTS=PASS_49_OF_49
D274_POSTPROCESS_MULTIFRAME_TESTS=PASS_30_OF_30
TOTAL_PERTINENT_D274_TESTS=PASS_79_OF_79
JSON_VALIDATION=PASS
OBSERVER_CLI_HELP=PASS
POSTPROCESSOR_CLI_HELP=PASS
LIVE_CRITICAL_SET_VS_APPROVED_SHA=BYTE_IDENTICAL
LIVE_AUTHORITY_TEMPLATE_CHANGED=false
RUNTIME_CHANGED=false
WINDOWS_POWERSHELL_5_1_NATIVE_RUNTIME=NOT_AVAILABLE_ON_LINUX_HOST
```

Non è stato simulato un nuovo PASS nativo. La qualification acquisita resta
provenance operatore.

## Factory-preserving e stato finale

Nessun hardware è stato collegato o aperto dall'agente. Nessuna capture, marker,
interazione dito, comando Goodix, retry o scrittura persistente è stata eseguita.
Non sono stati introdotti flash, IAP, ClearApp, provisioning, OTP, overwrite
PSK, enrollment commit o mutazioni account/PIN/credenziali. Non sono stati
eseguiti commit, push, merge, rebase, reset, amend o switch di branch.

```text
D274_03_BASELINE_APPROVAL=PASS
D274_03_BASELINE_APPROVED=true
D274_03_APPROVED_BASELINE_FULL_SHA=ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5
APPROVED_FOR_CAPTURE=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
ONE_SHOT_AUTHORIZATION_ID=null
REAL_CAPTURE_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_GOODIX_COMMAND_COUNT=0
AUTOMATIC_RETRY_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
NEXT_BOUNDARY=SEPARATE_CAPTURE_LIVE_AUTHORIZATION_DECISION
```
