# D274/02 — Pre-operator package preparation report (corrective in-place)

```text
THIS_BUNDLE_IS_OPERATOR_PACKAGE_PREPARATION_CORRECTIVE_IN_PLACE
IT_IS_NOT_WINDOWS_NATIVE_EXECUTION_EVIDENCE
```

## Scopo

D274/02 prepara un **pacchetto operator-run** per qualificare nativamente su
Windows le sole modalità innocue del Kit D274/01:

- `-SelfTestOnly`
- `-PreflightOnly`
- `-PreAuthorizationSimulationOnly`

L'AI esecutrice non dispone della VM Windows target e non finge alcuna
esecuzione nativa. Questa iterazione è un **corrective in-place** dello stesso
D274/02, successiva alla **prima vera esecuzione operatore Windows nativa** del
pacchetto. Quella run ha chiuso con `result=FAIL` allo `pre_gate`, causato da un
**falso positivo** del source scan: la regex generica `-f\s` ha scambiato
l'operatore di formattazione PowerShell (`-f [Guid]`) per il capture-filter di
TShark. Non è un failure dell'ambiente Windows: la review AI-PM ha identificato
il falso positivo. La run ha comunque chiuso correttamente i soli confini
raggiunti:

```text
WINDOWS_POWERSHELL51_RUNTIME=PASS
OPERATOR_PACKAGE_INTEGRITY_RUNTIME=PASS
FIRST_FAILURE_STOP_RUNTIME=PASS
FAIL_CORE_JSON_PRODUCTION_RUNTIME=PASS
```

La review AI-PM del pacchetto preparato aveva inoltre trovato cinque difetti
(A–E) più un hardening (F) e una lacuna di privacy, qui corretti e ri-testati.
La presente iterazione corregge ulteriormente il source-scan (context-aware
allowlist) e la verità dell'ACL dopo pre-gate fallito. Lo step chiude solo:

```text
D274_02_OPERATOR_PACKAGE=READY_FOR_AI_PM_REVIEW
D274_02_WINDOWS_NATIVE_EXECUTION=NOT_YET_PERFORMED
```

e NON chiude:

```text
D274_02_WINDOWS_NATIVE_QUALIFICATION=PASS
READY_FOR_CAPTURE=true
LIVE_AUTHORIZED=true
```

La qualificazione nativa reale avverrà quando l'operatore eseguirà il pacchetto
nella VM Windows e rispedirà il result bundle ad AI-PM.

## Baseline

```text
GIT_ROOT=/home/guido/Repository/goodix-27c6-5125_private
BRANCH=development
STARTING_HEAD=99369cdfcb266a912c4a76863b2935a948ec2fb1
STARTING_BASELINE_APPROVED=99369cdfcb266a912c4a76863b2935a948ec2fb1
BASELINE_ANCESTOR_CHECK=PASS
WORKTREE_STATUS=DIRTY_EXPECTED_D274_02_UNCOMMITTED_PREP_ONLY
D274_01_CORRECTIVE_FINAL_REVIEW=PASS
```

## Defect A — capture-root authority incoerente (RISOLTO)

Il wrapper risolveva `captures/` come `package\..\captures`, mentre il kit
copiato lo risolve come `package/captures` (parent di `operator_kit`). Ora entrambi
usano **un'unica authority**: `$ExpectedCapturesRoot = GetFullPath(Join-Path
$PackageRoot "captures")`. Il confronto `canonical_capture_root_match` usa il
resolved path esatto. `Get-D274NativeAclMetadata` non deriva più da
`PackageRoot\..`. Stato:

```text
D274_02_CAPTURE_ROOT_AUTHORITY=PACKAGE_ROOT_CAPTURES
D274_02_WRAPPER_KIT_CAPTURE_ROOT_ALIGNMENT=PASS
```

## Defect B — Write-D274JsonResult [hashtable] incompatibile (RISOLTO)

`ConvertFrom-Json` in Windows PowerShell 5.1 restituisce `PSCustomObject`, non
`hashtable`. Il parametro è ora `[object]$Object` (accetta `PSCustomObject`,
`[ordered]`, `hashtable`). Nessuna dipendenza da `-AsHashtable` (inesistente su
Windows PowerShell 5.1). Stato:

```text
D274_02_WRITE_JSON_RESULT_OBJECT_CONTRACT=PSOBJECT_PSCUSTOMOBJECT_HASHTABLE_ORDERED
D274_02_PSCUSTOMOBJECT_SERIALIZATION=PASS_PS51
D274_02_POWERSHELL51_ASHASHTABLE_DEPENDENCY=false
```

## Defect C — FAIL pre-gate non collezionabile (RISOLTO)

Qualunque esito produce ora i **sei core JSON**. Se un pre-gate fallisce, le
modalità non eseguite vengono scritte come `SKIPPED` con `skipped_because =
<first_failed_stage>`. Il primo failure resta authority (`failedStage` impostato
una sola volta); nessun retry. Stato:

```text
D274_02_FAIL_RESULT_COLLECTABILITY=PASS
D274_02_FIRST_FAILURE_AUTHORITY=PASS
D274_02_AUTOMATIC_RETRY_COUNT=0
```

## Defect D — runtime summary "pending operator run" (RISOLTO)

Il summary prodotto durante la operator run dichiara ora
`runtime_result_state = WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR`
e `NO_LIVE_CAPTURE_PERFORMED`. Il prep-bundle e il manuale continuano a dichiarare
`D274_02_WINDOWS_NATIVE_EXECUTION=NOT_YET_PERFORMED` finché l'operatore non esegue
realmente il package. Stato:

```text
D274_02_RUNTIME_SUMMARY_STATE=WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR_NO_LIVE_CAPTURE
```

## Defect E — operator_package_sha256 overclaim (RISOLTO)

`operator_package_sha256` conteneva lo SHA-256 del solo kit: un overclaim di
integrità. Ora esiste un **manifest di integrità statico**
`D274_02_operator_package_integrity.json` con path + SHA-256 dei cinque file
statici del pacchetto e degli SHA-256 baseline approvati D274/01; il wrapper lo
verifica read-only prima di eseguire. L'environment esporta
`operator_package_integrity`, `operator_package_manifest_sha256`,
`approved_d274_01_kit_sha256`. Stato:

```text
D274_02_OPERATOR_PACKAGE_INTEGRITY=PASS_STATIC_AND_RUNTIME_VERIFIABLE
D274_02_OPERATOR_PACKAGE_HASH_OVERCLAIM_REMOVED=true
```

## Hardening F — collector path authority (RISOLTO)

Il collector ora richiede uguaglianza canonica esatta:
`resolvedResults == GetFullPath(Join-Path $PackageRoot "results")`. Rimosso il
controllo prefix `StartsWith($resolvedPackage)`. Stato:

```text
D274_02_COLLECTOR_RESULTS_PATH_AUTHORITY=EXACT_PACKAGE_RESULTS
```

## Privacy del FAIL result (RAFFORZATA)

Funzione centralizzata `Sanitize-String`: sostituisce l'exact `$PackageRoot` con
`<PACKAGE_ROOT>`, `C:\Users\<seg>\...` con `<USER_PATH>`, e maschera
SID/MAC/IP. I campi `error` dei core JSON la usano; nessun raw stderr nei core
JSON. Il collector mantiene una seconda barriera `FAIL_CLOSED` di privacy scan: se
rileva dati sensibili, rifiuta lo ZIP. Stato:

```text
D274_02_FAIL_RESULT_PRIVACY=PASS_CENTRALIZED_SANITIZE_PLUS_COLLECTOR_SCAN
```

## Final corrective in-place (truthful FAIL evidence e path sanitization)

Revisione AI-PM ulteriore (sempre in-place, senza D274/03) ha corretto la
probatorietà del FAIL:

- **A — Goodix presence truthful**: `Get-D274GoodixPresence` osserva (booleano)
  separatamente dal gate. Se il target `VID_27C6&PID_5125` è presente il gate
  fallisce chiuso (`FAIL_CLOSED_GOODIX_PRESENT_BEFORE_OFFLINE_QUALIFICATION`) e
  `goodix_present_before_run=true`; se `Get-PnpDevice` non è disponibile la
  presenza è `null` (mai un falso negativo). Stato:
  `D274_02_GOODIX_PRESENCE_EVIDENCE_TRUTHFUL=PASS`.
- **B — first-failure detail**: `Register-FirstFailure` preserva
  `$failureDetail = Sanitize-String($_.Exception.Message)` al primo failure;
  il summary esporta `failed_stage` + `failure_detail_sanitized` (no stack trace).
  Stato: `D274_02_FIRST_FAILURE_DETAIL_PRESERVED=PASS_SANITIZED`.
- **C — subprocess diagnostics**: ogni FAIL di subprocess preserva `exit_code` e
  un `error_sanitized` bounded (<=2048 char) da stderr/stdout via `Sanitize-String`.
  Stato: `D274_02_SUBPROCESS_FAILURE_DIAGNOSTICS=PASS_SANITIZED_BOUNDED`.
- **D — imported evidence sanitization**: il `D274_WINDOWS_PREFLIGHT_V1` importato
  dal Kit ha `output_root` forzato a `<PACKAGE_ROOT>\captures` e `tshark_path`
  passato per `Sanitize-String` prima della serializzazione; i fatti semantici
  (`output_root_private_writable`, `output_root_privacy`, conteggi, versione) sono
  preservati. Ne consegue che un package copiato sotto user profile Windows
  (`C:\Users\<utente>\...`) resta collezionabile se il relativo ACL privacy gate
  passa. Stati: `D274_02_IMPORTED_KIT_EVIDENCE_PATH_SANITIZATION=PASS`,
  `D274_02_USER_PROFILE_PACKAGE_PATH_COLLECTABLE=true`.

Il collector resta seconda barriera (SID/MAC/IP/`C:\Users\`/HKEY_/credential);
non sono stati indeboliti i regex.

## Corrective in-place successivo — source-scan false positive e verità ACL (RISOLTO)

La prima operator-run Windows ha prodotto `result=FAIL` allo `pre_gate` con
`failure_detail_sanitized = D274_02_FAIL_CLOSED: kit source scan found forbidden
capture argument token: -f\s`. Root cause: la regex `-f\s` applicata all'intero
sorgente del Kit D274/01 collide con l'operatore di formattazione PowerShell
`(".d274-write-probe-{0}" -f [Guid]::NewGuid().ToString("N"))`. Corretto:

- **Source contract context-aware**: `Test-D274KitSourceContract` isola le sole
  righe che invocano realmente `& $tshark` e ammette solo le due forme
  discovery approvate (`& $tshark --version`, `& $tshark -D`); ogni altra
  invocazione `& $tshark` è rifiutata. L'operatore `-f` di PowerShell non è più
  un falso positivo. Restano rifiutati `Start-Process` e l'assenza di
  `HARD_DISABLED_D274_01`. Stato:
  `D274_02_TSHARK_SOURCE_CONTRACT=CONTEXT_AWARE_ALLOWLIST`,
  `D274_02_POWERSHELL_FORMAT_OPERATOR_FALSE_POSITIVE=false`.

Fixture verificate (offline, nel `prep_test_results`):
`powershell_format_operator_fixture` ACCEPTED; `tshark_version_fixture` e
`tshark_discovery_fixture` ACCEPTED; `tshark_capture_interface_fixture`,
`tshark_capture_write_fixture`, `tshark_capture_filter_fixture`,
`tshark_display_filter_fixture`, `Start-Process fixture` REJECTED.

- **Verità ACL dopo pre-gate fallito**: la prima run aveva registrato
  `windows_native_acl_behavior_test=FAIL` pur avendo il preflight `SKIPPED`
  (bug: `$aclPass` non definito nel ramo else). Ora, se il preflight non è PASS,
  l'ACL è `NOT_EXECUTED_DUE_PRIOR_FAILURE` (non FAIL). FAIL è usato solo quando il
  preflight ha realmente eseguito il gate privacy/accessibility o la raccolta ACL
  stessa è stata tentata come authority e il contract fallisce. Stato:
  `D274_02_ACL_RESULT_AFTER_SKIPPED_PREFLIGHT=NOT_EXECUTED_DUE_PRIOR_FAILURE`.

- **Collector UX**: il runner non crea lo ZIP; alla fine, sia in PASS sia in FAIL,
  stampa in italiano l'invito a eseguire `.\collect-d274-02-results.ps1`; in FAIL
  aggiunge che il FAIL sarà incluso nel bundle e di non tentare retry prima della
  review AI-PM. Gli exit code macchina sono preservati (PASS→0, FAIL→!=0).

- **Collector FAIL path**: il collector accetta il set dei sei core JSON anche da
  una run FAIL (es. `failed_stage=pre_gate`, resto `SKIPPED`) e produce
  `results.zip` + `.sha256` senza richiedere PASS. Stato:
  `D274_02_FAIL_RESULT_COLLECTOR_CONTRACT=PASS`.

- **TShark environment discovery non è authority**: il wrapper environment helper
  (PATH-only) è `NON_AUTHORITATIVE_DIAGNOSTIC`; il vero gate `-PreflightOnly`
  del Kit D274/01 (`$env:ProgramFiles\Wireshark\tshark.exe`) è
  `AUTHORITATIVE_GATE`. Lo `environment.json` ora esporta
  `tshark_discovery_role = NON_AUTHORITATIVE_DIAGNOSTIC`. La prima run aveva
  `tshark_path=null`/`usbpcap_interfaces_count=0` ma ciò NON prova assenza di
  TShark/USBPcap: il source-contract gate è fallito prima del preflight.

## Corrective finale post-review AI-PM — manifest integrità e allowlist esatta (RISOLTO)

La review AI-PM del bundle `64ddee56…` ha rilevato due blocchi risolti in questa
iterazione finale (sempre D274/02, nessun D274/03):

- **BLOCKER A — manifest di integrità stale**: il bundle precedente era stato
  costruito *prima* della rigenerazione del manifest, quindi conteneva gli hash
  obsoleti di runner e README. Alla seconda run Windows il gate
  `package_integrity` sarebbe fallito (`pre_gate -> package_integrity -> FAIL`)
  prima di raggiungere il fix del source-contract. Corretto rispettando l'ordine
  obbligatorio: freeze dei file statici → calcolo degli SHA-256 REALI dai file
  finali → rigenerazione di `D274_02_operator_package_integrity.json` → verifica
  indipendente manifest-vs-files → solo alla fine ZIP. La verifica reale sui file
  finali dal filesystem passa per ogni entry. Stati:
  `D274_02_FINAL_INTEGRITY_MANIFEST_SELF_CONSISTENT=PASS`,
  `D274_02_INTEGRITY_MANIFEST_GENERATED_AFTER_STATIC_FILES_FROZEN=true`,
  `D274_02_FINAL_RUNNER_HASH_MATCHES_MANIFEST=PASS`,
  `D274_02_FINAL_COLLECTOR_HASH_MATCHES_MANIFEST=PASS`,
  `D274_02_FINAL_README_HASH_MATCHES_MANIFEST=PASS`,
  `D274_02_FINAL_KIT_HASH_MATCHES_MANIFEST=PASS`,
  `D274_02_FINAL_POSTPROCESSOR_HASH_MATCHES_MANIFEST=PASS`.

- **HARDENING B — allowlist TShark esatta**: la regex precedente ancorava solo il
  prefisso, quindi `& $tshark --version -i USBPcap1` veniva accettata. Ora
  `Test-D274KitSourceContract` isola le righe `& $tshark`, rimuove
  redirection/pipeline (`2>&1`, `2>`, `>`, `|`) e richiede che gli argomenti
  effettivi siano **esattamente** `--version` o `-D`. Le due righe baseline
  restano accettate; le forme aumentate sono rifiutate. Stato:
  `D274_02_TSHARK_SOURCE_CONTRACT=CONTEXT_AWARE_EXACT_ALLOWLIST`,
  `D274_02_TSHARK_ALLOWLIST_TRAILING_ARGUMENT_ESCAPE=false`.

D274/01 resta **byte-identico** (kit `4b0b3b1c…bd`, postprocessor
`2867ff23…f37`); non cambia l'esito della prima operator run.

## Boundary D274/01 preservato

Il Kit D274/01 `operator_kit/d274-windows-multiframe-evidence.ps1` è baseline e
**non è stato modificato**. Le copie nel pacchetto sono **byte-identiche**
(SHA-256 `4b0b3b1c…bd` per il kit, `2867ff23…f37` per il postprocessor). Nessun
nuovo difetto D274/01 è emerso, quindi non è stato aperto
`D274_02_OPERATOR_PACKAGE=BLOCKED_BY_NEW_D274_01_DEFECT`.

```text
D274_01_OPERATOR_KIT_BYTE_IDENTITY=PASS_4b0b3b1c3f81a7a5874aa2d3a4b281c79ec03b0b1ab1c92cc11284bbee5bd9bd
D274_01_POSTPROCESSOR_BYTE_IDENTITY=PASS_2867ff23cb76297d9089b0840afa59e7a8222e5657e3fc1dc5d7774d6ca68f37
```

## Pacchetto operatore

```text
analysis/D274/D274_02_windows_native_operator_package/
├── operator_kit/d274-windows-multiframe-evidence.ps1   (byte-identical copy)
├── analysis/D274/d274_postprocess_multiframe_evidence.py  (byte-identical copy)
├── captures/                                            (destinazione privata vuota)
├── results/                                             (prodotto dall'operatore)
├── run-d274-02-native-qualification.ps1
├── collect-d274-02-results.ps1
├── D274_02_operator_package_integrity.json             (manifest integrità statico)
└── D274_02_OPERATOR_README_IT.md
```

## Controlli nativi previsti (non eseguiti qui)

- **Goodix absence gate**: `Get-PnpDevice -PresentOnly` deve confermare
  `VID_27C6&PID_5125` assente dal guest; altrimenti
  `FAIL_CLOSED_GOODIX_PRESENT_BEFORE_OFFLINE_QUALIFICATION`.
- **Native ACL behavior test**: il preflight nativo produce evidenza
  (`output_root_privacy == PASS_PRIVATE_CONTRACT`) e il wrapper aggiunge metadati
  read-only sanitizzati. Se il root non passa →
  `WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=FAIL` e qualification chiusa. Nessuna mutazione ACL.
- **TShark/USBPcap qualification**: solo discovery (`--version`, `-D`);
  `REAL_CAPTURE_START_COUNT=0`.
- **Hard-disable adversarial test**: esecuzione separata del flag nominale
  `-IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture`; PASS solo se
  `exit != 0`, messaggio `HARD_DISABLED_D274_01` osservato, nessuna capture,
  nessuna azione hardware. Eseguito solo se il safety pre-gate è passato;
  altrimenti registrato `SKIPPED`.
- **Package integrity gate**: il wrapper verifica read-only
  `D274_02_operator_package_integrity.json` prima di ogni esecuzione.

## Test obbligatori (risultati offline)

`git diff --check` sarà eseguito al momento del bundle. Tutti gli altri test
sono superati (vedi `D274_02_windows_native_qualification_prep_test_results.json`):
package_capture_root_authority, wrapper_kit_capture_root_alignment,
write_json_result_pscustomobject_compatible_source_contract,
no_convertfrom_json_as_hashtable_ps51_dependency, fail_result_six_core_files_model,
first_failure_stop_model, runtime_summary_not_pending_operator_run,
operator_package_hash_semantics, collector_exact_results_path,
privacy_fail_result_source_contract, D274_01_copy_byte_identity,
forbidden_capture_args_absent (ora CONTEXT_AWARE_EXACT_ALLOWLIST), hard_disable_preserved,
git_diff_check, baseline_approved_kit_source_contract, powershell_format_operator_fixture,
tshark_version_fixture, tshark_discovery_fixture, tshark_capture_interface_fixture,
tshark_capture_write_fixture, tshark_capture_filter_fixture, tshark_display_filter_fixture,
start_process_fixture, tshark_exact_version_fixture, tshark_exact_discovery_fixture,
tshark_allowlist_trailing_argument_escape, acl_after_skipped_preflight_not_false_fail,
acl_preflight_pass_yields_pass, acl_preflight_acl_failure_yields_fail,
fail_result_collector_contract, operator_console_guidance, environment_tshark_discovery_non_authoritative,
final_integrity_manifest_self_consistent, final_runner_hash_matches_manifest,
final_collector_hash_matches_manifest, final_readme_hash_matches_manifest,
final_kit_hash_matches_manifest, final_postprocessor_hash_matches_manifest, più
i test precedenti (py_compile, JSON parse, source guards, trailing whitespace,
bracket balance, package privacy scan).
`WINDOWS_NATIVE_POWERSHELL_TEST=NOT_AVAILABLE_IN_EXECUTOR_ENVIRONMENT`.

## Stato di preparazione

```text
D274_02_FIRST_WINDOWS_OPERATOR_RUN=FAIL_PRE_GATE_FALSE_POSITIVE_SOURCE_SCAN
D274_02_FIRST_WINDOWS_OPERATOR_RUN_ROOT_CAUSE=GENERIC_REGEX_-f_MATCHED_POWERSHELL_FORMAT_OPERATOR
WINDOWS_POWERSHELL51_RUNTIME=PASS
OPERATOR_PACKAGE_INTEGRITY_RUNTIME=PASS
FIRST_FAILURE_STOP_RUNTIME=PASS
FAIL_CORE_JSON_PRODUCTION_RUNTIME=PASS
NO_LIVE_CAPTURE_PERFORMED=true
REAL_CAPTURE_START_COUNT=0
REAL_USB_OPEN_COUNT=0
HARD_DISABLE_PRESERVED=true
D274_02_TSHARK_SOURCE_CONTRACT=CONTEXT_AWARE_EXACT_ALLOWLIST
D274_02_TSHARK_ALLOWLIST_TRAILING_ARGUMENT_ESCAPE=false
D274_02_POWERSHELL_FORMAT_OPERATOR_FALSE_POSITIVE=false
D274_02_FINAL_INTEGRITY_MANIFEST_SELF_CONSISTENT=PASS
D274_02_INTEGRITY_MANIFEST_GENERATED_AFTER_STATIC_FILES_FROZEN=true
D274_02_FINAL_RUNNER_HASH_MATCHES_MANIFEST=PASS
D274_02_FINAL_COLLECTOR_HASH_MATCHES_MANIFEST=PASS
D274_02_FINAL_README_HASH_MATCHES_MANIFEST=PASS
D274_02_FINAL_KIT_HASH_MATCHES_MANIFEST=PASS
D274_02_FINAL_POSTPROCESSOR_HASH_MATCHES_MANIFEST=PASS
D274_02_BUNDLE_MANIFEST_STATIC_RUNTIME_PATHS_ACCURATE=PASS
D274_02_ACL_RESULT_AFTER_SKIPPED_PREFLIGHT=NOT_EXECUTED_DUE_PRIOR_FAILURE
D274_02_FAIL_RESULT_COLLECTOR_CONTRACT=PASS
D274_02_ENVIRONMENT_TSHARK_DISCOVERY=NON_AUTHORITATIVE_DIAGNOSTIC
D274_01_PREFLIGHT_TSHARK_DISCOVERY=AUTHORITATIVE_GATE
D274_02_OPERATOR_PACKAGE=READY_FOR_AI_PM_REVIEW
D274_02_WINDOWS_NATIVE_EXECUTION=ONE_FAILED_PRE_GATE_RUN_OBSERVED
D274_02_WINDOWS_NATIVE_QUALIFICATION=NOT_YET_DETERMINED
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=NOT_YET_EXECUTED
D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=NOT_YET_EXECUTED
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

## Prossimo boundary

```text
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_D274_02_FINAL_INTEGRITY_CORRECTIVE
NEXT_BOUNDARY_PREREQUISITE=AI_PM_PASS_THEN_SECOND_WINDOWS_NATIVE_OFFLINE_OPERATOR_RUN
```

## Safety counters (run AI)

```text
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_WINDOWS_ACCOUNT_MUTATION_COUNT=0
REAL_WINDOWS_ENROLLMENT_COMMIT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
```
