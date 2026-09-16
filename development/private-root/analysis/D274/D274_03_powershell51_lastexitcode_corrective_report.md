# D274/03 micro-corrective — PowerShell 5.1 `$LASTEXITCODE` dopo pipeline Git

```text
OUTCOME=READY_FOR_AI_PM_REVIEW — OFFLINE_MICRO_CORRECTIVE_COMPLETE;NATIVE_RETRY_REQUIRED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED — POWERSHELL_5_1_LASTEXITCODE_PIPELINE_DEFECT_ISOLATED_AND_CORRECTED;NO_DEVICE_SIDE_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS_LINUX_OFFLINE_CORRECTIVE;WINDOWS_POWERSHELL_5_1_NATIVE_RETRY_REQUIRED
RESIDUAL_BLOCKER_OR_RISK=BASELINE_APPROVAL_BLOCKED_PENDING_FULL_NATIVE_QUALIFICATION_RETRY
CANONICAL_DOCUMENTATION=UPDATED — POST_BOM_NATIVE_FAILURE,LASTEXITCODE_ROOT_CAUSE,AUDIT_SCOPE,NATIVE_RETRY_STATE
BUNDLE=analysis/D274/D274_03_powershell51_lastexitcode_corrective_bundle.zip

GIT_CANONICAL_BRANCH=main
D274_03_LIVE_BRANCH_GATE=main
D274_03_POWERSHELL51_BOM_CORRECTIVE=PASS
D274_03_POST_BOM_NATIVE_QUALIFICATION_RESULT=FAIL_REPOSITORY_STAGE
D274_03_POST_BOM_NATIVE_QUALIFICATION_POWERSHELL_51=PASS
D274_03_POST_BOM_GIT_EXIT_DIRECT=0
D274_03_POST_BOM_GIT_EXIT_PIPE=-1
D274_03_LASTEXITCODE_CORRECTIVE=PASS_OFFLINE
D274_03_WINDOWS_NATIVE_QUALIFICATION=REQUIRED_RETRY_AFTER_LASTEXITCODE_CORRECTIVE
```

## Failure reale osservata

La prima qualification nativa post-BOM è stata eseguita su Windows 11 Home
build 26200, Windows PowerShell Desktop 5.1.26100.8655, con Goodix `27c6:5125`
assente dal guest.

Il corrective UTF-8 BOM è confermato dal campo: il parsing PowerShell 5.1
funziona e lo stage `powershell_51` ha dato PASS. È la prima run D274/03
realmente entrata in runtime.

La run è però fallita allo stage successivo:

```text
stage   = repository_and_goodix_absence
failure = D274_03_NATIVE_FAIL_CLOSED: repository Git non individuabile
```

Il repository era in realtà perfettamente individuabile. La diagnostica manuale
dell'Utente, nello stesso clone e nella stessa directory Kit, isola la causa:

```text
& git -C $PackageRoot rev-parse --show-toplevel
# C:/Users/<utente>/Documents/goodix-27c6-5125_private
EXIT_DIRECT=0

$repository = (& git -C $PackageRoot rev-parse --show-toplevel 2>&1 |
    Select-Object -First 1)
# REPOSITORY=[C:/Users/<utente>/Documents/goodix-27c6-5125_private]
EXIT_PIPE=-1
```

Stesso comando, stesso output corretto, exit code osservato diverso. In Windows
PowerShell 5.1 `Select-Object -First 1` interrompe la pipeline upstream: il
comando nativo non consegna il proprio exit code e `$LASTEXITCODE` diventa `-1`
anche quando Git riesce. Il gate leggeva quindi un exit code prodotto dalla
pipeline, non da Git, e falliva chiuso su un repository valido.

In quella run nessun controllo Goodix, ACL/privacy, TShark/USBPcap, selector
5.1, gate same-run, simulazione pre-authority o invocazione avversaria è stato
raggiunto. Nessun hardware è stato toccato, nessun USB aperto, nessuna capture o
marker creato.

## Correzione applicata

Idioma unico, PowerShell 5.1-safe:

1. comando nativo invocato **senza** pipeline;
2. exit code catturato nello statement immediatamente successivo, in variabile
   dedicata;
3. fail-closed valutato **sulla variabile catturata**;
4. solo dopo, l'output viene selezionato, normalizzato e validato non vuoto.

Nel runner di qualificazione (Task A):

```powershell
$repositoryOutput = & git -C $PackageRoot rev-parse --show-toplevel 2>&1
$gitExitCode = $LASTEXITCODE
Assert-D274Pass ($gitExitCode -eq 0) "repository Git non individuabile"
$repository = ([string](@($repositoryOutput) | Select-Object -First 1)).Trim()
Assert-D274Pass (-not [string]::IsNullOrWhiteSpace($repository)) "repository Git vuoto"
```

Il cast `[string]` rende la forma sicura anche sotto `Set-StrictMode -Version
2.0` quando l'output è vuoto: `[string]$null` è `''`, quindi `.Trim()` non
solleva e la validazione non-vuoto resta l'unico gate sul contenuto.

## Audit dei pattern analoghi (Task B)

Pattern cercato: comando nativo → pipeline/cmdlet → uso tardivo di
`$LASTEXITCODE`, su `git`, `tshark`, `python`, `USBPcapCMD` e altri processi
nativi, in tutti i cinque `.ps1` del Kit.

Corretti — 5 siti realmente vulnerabili, tutti su Git, tutti nella forma
`(& git … | Select-Object -First 1)` seguita da lettura di `$LASTEXITCODE`:

| file | sito | ruolo |
| --- | --- | --- |
| `run-d274-03-native-qualification.ps1` | repository toplevel | stage `repository_and_goodix_absence` (Task A) |
| `avvia-d274-03.ps1` | `Get-D274RepositoryRoot` | risoluzione root per preflight e live |
| `collect-d274-03-results.ps1` | repository toplevel | confine `captures/D274_03` del collector |
| `invoke-d274-03-live-once.ps1` | `rev-parse HEAD` | gate baseline approvata |
| `invoke-d274-03-live-once.ps1` | `branch --show-current` | gate branch `main` |

Auditati e **non** modificati, perché non vulnerabili allo stesso problema:

| sito | motivo |
| --- | --- |
| `invoke`: `& git diff --quiet $approvedSha -- @critical` | invocazione diretta senza pipeline; `$LASTEXITCODE` letto nello statement immediatamente successivo |
| `invoke`: `@(& git status --porcelain -- @critical)` | `@( … )` è array subexpression, non troncamento di pipeline: l'exit code di Git resta valido |
| `invoke`: `@(& $python $postprocessor … 2>&1)` | idem; il `Select-Object -Last 1` opera sulla variabile già materializzata e la condizione `if` è valutata prima del corpo |
| `avvia`: `& $Tshark -D … \| Where-Object`, `& $tshark --version \| Select-Object -First 1` | usano solo l'output e non leggono mai `$LASTEXITCODE`; il fail-closed è su conteggio interfacce/selector |
| `avvia`: `exit $LASTEXITCODE` dopo `& invoke-d274-03-live-once.ps1` | nessuna pipeline interposta; ogni failure del runner è terminante e non raggiunge quella riga |
| `run-native`: `Invoke-D274PowerShell` | usa `System.Diagnostics.Process.ExitCode`, non `$LASTEXITCODE` |
| observer/postprocessor Python | avviati con `Start-Process -PassThru` e valutati su `.ExitCode` |
| `collect-d274-03-native-qualification-results.ps1` | nessun comando nativo e nessun `$LASTEXITCODE` |

`USBPcapCMD` non è mai invocato direttamente dal Kit: la cattura passa
esclusivamente da TShark sull'interfaccia USBPcap.

Nessun refactoring generico è stato eseguito.

## Test anti-regressione (Task C)

`analysis/D274/test_d274_03_second_cycle_operator_kit.py` passa da 36 a 41 casi.
I cinque nuovi test sono strutturali sul sorgente PowerShell:

```text
test_37  exit code Git catturato nello statement subito dopo l'invocazione;
         invocazione priva di pipeline; fail-closed sulla variabile catturata;
         assenza del pattern fragile; validazione non-vuoto del repository
test_38  detector generico: nessun $LASTEXITCODE letto dopo una pipeline nativa
         in nessuno dei cinque .ps1, con guardia anti-vacuità sul pattern storico
test_39  coverage dei 5 siti corretti: invocazione senza pipeline e cattura
         immediata dell'exit code in variabile dedicata
test_40  gate live invariati: $headExitCode/$branchExitCode usati, HEAD vs
         baseline e branch main preservati, gate ancora prima di marker/capture
test_41  repository/root validati come non vuoti nei tre script che li risolvono
```

Il detector non è vacuo: eseguito sui sorgenti pre-corrective di `HEAD` trova
esattamente i 5 siti vulnerabili, e 0 sui sorgenti corretti.

```text
DETECTOR_PRE_CORRECTIVE_FINDINGS=5
DETECTOR_POST_CORRECTIVE_FINDINGS=0
```

Gli hash del contenuto logico dei `.ps1` (contratto encoding introdotto dal
corrective BOM) sono aggiornati ai quattro script modificati; il quinto resta
invariato.

## Invarianti preservati

Non sono stati toccati: branch gate `main`, parser protocollo, ACK policy,
second-B0 observer, wire-driven STOP, finalizzazione raw, semantica same-run
Goodix absence, PIN policy, privacy, authority, marker single-use, semantica
TShark, percorso hardware/live. `D274_03_live_authority.json`,
`D274_03_evidence_schema.json`, `d274_03_postprocess_second_cycle.py` e
`d274_03_observe_second_b0.py` non sono modificati.

I gate live conservano la stessa semantica: HEAD deve coincidere con la baseline
approvata e la branch deve essere `main`. Il corrective rende affidabile la
lettura dell'exit code, non allenta il confronto.

```text
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

## Nota per la review AI-PM

Il live-critical set include `avvia-d274-03.ps1`,
`invoke-d274-03-live-once.ps1` e `collect-d274-03-results.ps1`, tutti toccati da
questo corrective. Non esiste una baseline approvata da invalidare
(`approved_full_commit_sha` è `null`): una futura approvazione dovrà riferirsi al
commit successivo a questo corrective.

## Verifica offline

```text
D274_03_TESTS=PASS_41_OF_41
D274_POSTPROCESS_MULTIFRAME_TESTS=PASS_30_OF_30
HISTORICAL_PRIVATE_CAPTURE_REGRESSION=PASS_EXPECTED_MISSING_SECOND_IRQ2
LASTEXITCODE_PIPELINE_AUDIT=PASS_5_PS1_FILES_0_FINDINGS
LASTEXITCODE_DETECTOR_ANTI_VACUITY=PASS_5_FINDINGS_ON_PRE_CORRECTIVE_SOURCES
POWERSHELL51_BOM_CHECK=PASS_5_OF_5
POWERSHELL51_UTF8_SIG_DECODE=PASS_5_OF_5
POWERSHELL51_MOJIBAKE_SCAN=PASS
POWERSHELL51_LOGICAL_CONTENT_AUDIT=PASS
POWERSHELL51_DELIMITER_BALANCE=PASS_5_OF_5
PYTHON_COMPILE=PASS
JSON_VALIDATION=PASS
OBSERVER_CLI_HELP=PASS
POSTPROCESSOR_CLI_HELP=PASS
GIT_DIFF_CHECK=PASS
WINDOWS_POWERSHELL_5_1_NATIVE_RUNTIME=NOT_AVAILABLE_ON_LINUX_HOST
```

L'host AI è Linux e non dispone di Windows PowerShell 5.1: il PASS è
esclusivamente offline e non qualifica il runtime nativo.

## Git e bundle

```text
initial_branch=session/agent_59ecced4-e271-493e-a559-76cfc54b88a8 (HEAD identico a main e origin/main)
initial_full_head=93a1a587be4d8ee167c393f8b1ce64a39cb90ef8
final_branch=session/agent_59ecced4-e271-493e-a559-76cfc54b88a8 (HEAD identico a main e origin/main)
final_head=93a1a587be4d8ee167c393f8b1ce64a39cb90ef8
commit_created=false
git_status=DIRTY_EXPECTED_D274_03_LASTEXITCODE_CORRECTIVE_ONLY
unexpected_files=NONE
ZIP_CRC=PASS
duplicates=0
path_traversal=0
unexpected_symlink=0
sidecar_external=true
```
