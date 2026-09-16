# D274/03 corrective — gate causale, policy PIN, stop wire-driven e qualificazione nativa

```text
OUTCOME=READY — OFFLINE_CORRECTIVE_IMPLEMENTED_FOR_AI_PM_REVIEW;BASELINE_APPROVAL_BLOCKED
ADVANCEMENT=OFFLINE_IMPLEMENTATION_AND_SYNTHETIC_EVIDENCE;NO_DEVICE_SIDE_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS — PYTHON_PATHS_AND_STATIC_NATIVE_PACKAGE;WINDOWS_POWERSHELL_5_1_EXECUTION_PENDING
RESIDUAL_BLOCKER_OR_RISK=WINDOWS_NATIVE_QUALIFICATION_REQUIRED_NOT_YET_EXECUTED;NO_BASELINE_OR_CAPTURE_APPROVAL
CANONICAL_DOCUMENTATION=UPDATED — HIGH_STATE,ROADMAP,D274_03_AUTHORITY_PIN_WIRE_FINALIZATION_NATIVE_GATE
BUNDLE=analysis/D274/D274_03_corrective_bundle.zip
```

## Correzioni implementate

- Il runner verifica `VID_27C6&PID_5125` assente via PnP nella stessa
  invocazione live. L'ordine sorgente verificato è
  `same_run_gate < marker < capture < attach < finger`; discovery indisponibile
  o target presente falliscono chiuso senza mutazioni PnP o apertura Goodix.
- `EXISTING_PIN_AUTHENTICATION` è distinto dalle categorie terminali di
  creazione/modifica PIN, account, credenziali, prerequisiti inattesi e commit.
  Il valore PIN resta esclusivamente nella UI Windows e non è gestito dal Kit.
- `SECONDO_OK` è rimosso. Un observer Python metadata-only legge passivamente il
  pcapng in crescita, tollera il trailing block incompleto e segnala il boundary
  esatto `rearm ACK → IRQ2 → 0x22 → ACK01 → secondo B0`.
- Il segnale wire causa lo stop bounded di TShark. Il raw deve essere presente e
  non vuoto; SHA-256 è calcolato dopo la terminazione. Il postprocessor strict
  hash-gated deve recuperare lo stesso frame terminale. La perdita viene
  classificata `CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE` senza retry.
- È pronto il package innocuo Windows PowerShell 5.1 con runner e collector
  nativi. Verifica modalità offline, selector, gate same-run, authority false,
  TShark/USBPcap, ACL, privacy, lingua e assenza di marker/capture/prompt dito.

## Verifica offline

```text
D274_03_TESTS=PASS_34_OF_34
D274_01_REGRESSION_TESTS=PASS_30_OF_30
PY_COMPILE=PASS
JSON_VALIDATION=PASS
OBSERVER_CLI=PASS
POSTPROCESSOR_CLI=PASS
GIT_DIFF_CHECK=PASS
WINDOWS_POWERSHELL_5_1_RUNTIME=NOT_AVAILABLE_CURRENT_LINUX_HOST
D274_03_WINDOWS_NATIVE_QUALIFICATION=REQUIRED_NOT_YET_EXECUTED
```

Le fixture provano trigger non anticipato, trailing pcapng incompleto, wrong
IRQ/ACK/B0, deadline, terzo ciclo, raw vuoto/mancante/troncato e perdita del
terminale dopo un segnale observer positivo. La capture storica D263 resta
`MISSING_SECOND_IRQ2` e non diventa evidenza del secondo ciclo target.

## Stato e safety

```text
D274_03_SAME_RUN_GOODIX_ABSENCE_GATE=REQUIRED_BEFORE_MARKER_CAPTURE_ATTACH_FINGER
D274_03_EXISTING_PIN_AUTHENTICATION_POLICY=ALLOWED_NON_MUTATING_WINDOWS_UI_ONLY
D274_03_PIN_VALUE_HANDLED_BY_KIT=false
D274_03_SECOND_B0_STOP_TRIGGER=WIRE_DRIVEN
D274_03_CAPTURE_FINALIZATION_CONTRACT=FINAL_RAW_READABLE_HASH_GATED_TERMINAL_FRAME_RECOVERED
D274_03_WINDOWS_NATIVE_QUALIFICATION=REQUIRED_NOT_YET_EXECUTED
BASELINE_APPROVAL_BLOCKED_PENDING_NATIVE_QUALIFICATION=true
D274_03_BASELINE_APPROVED=false
APPROVED_FOR_CAPTURE=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED
REAL_CAPTURE_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_GOODIX_COMMAND_COUNT=0
AUTOMATIC_RETRY_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

D274/02 resta `CLOSED/PASS`; nessun suo artefatto runtime è stato modificato o
riaperto. Nessuna capture reale, interazione dito, apertura USB, comando Goodix,
provisioning o write persistente è stata eseguita.

## Git

```text
initial_branch=development
initial_full_head=86c9b8d0cf16e7ec9d4fbdd20a51735c3cadd8de
final_branch=development
final_head=86c9b8d0cf16e7ec9d4fbdd20a51735c3cadd8de
commit_created=false
git_status=DIRTY_EXPECTED_D274_03_CORRECTIVE_STEP_LOCAL_CHANGES_ONLY
unexpected_files=NONE
```
