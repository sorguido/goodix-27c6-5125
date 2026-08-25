# SPDX-License-Identifier: GPL-2.0-or-later
# Percorso futuro live D274/03: cattura passiva USBPcap/TShark, nessun comando Goodix.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RepositoryRoot,
    [Parameter(Mandatory=$true)][string]$AuthorityPath,
    [Parameter(Mandatory=$true)][string]$TsharkPath,
    [Parameter(Mandatory=$true)][string]$UsbPcapInterface,
    [switch]$NativeQualificationOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$script:CaptureProcess = $null
$script:ObserverProcess = $null
$script:CaptureStarted = $false
$script:CaptureStopped = $false
$script:ExpectedTarget = "VID_27C6&PID_5125"

function Stop-D274Capture {
    if ($null -ne $script:CaptureProcess -and -not $script:CaptureProcess.HasExited) {
        Stop-Process -Id $script:CaptureProcess.Id -ErrorAction SilentlyContinue
        if (-not $script:CaptureProcess.WaitForExit(10000)) { return $false }
    }
    if ($null -ne $script:CaptureProcess) {
        $script:CaptureStopped = $script:CaptureProcess.HasExited
    }
    return $script:CaptureStopped
}

function Stop-D274Observer {
    if ($null -ne $script:ObserverProcess -and -not $script:ObserverProcess.HasExited) {
        Stop-Process -Id $script:ObserverProcess.Id -ErrorAction SilentlyContinue
        $script:ObserverProcess.WaitForExit(5000) | Out-Null
    }
}

function Fail-D274Live([string]$Message) {
    Stop-D274Observer
    Stop-D274Capture | Out-Null
    throw "D274_03_FAIL_CLOSED: $Message"
}

function Read-D274Exact([string]$Prompt, [string[]]$Allowed) {
    $answer = (Read-Host $Prompt).Trim().ToUpperInvariant()
    if ($Allowed -notcontains $answer) {
        Fail-D274Live ("risposta non ammessa: " + $answer)
    }
    return $answer
}

function Get-D274Python {
    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) { return $command.Source }
    }
    return $null
}

function Assert-D274GoodixAbsentSameRun {
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D274Live "Get-PnpDevice non disponibile: impossibile verificare l'assenza Goodix nella stessa invocazione"
    }
    $escapedTarget = [regex]::Escape($script:ExpectedTarget)
    $targets = @(Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { $_.InstanceId -match $escapedTarget })
    if ($targets.Count -ne 0) {
        Fail-D274Live "GOODIX_PRESENT_IN_GUEST=true; il target deve essere assente prima del marker e della cattura"
    }
    return $true
}

function Read-D274SetupReady {
    $terminal = @(
        "NEW_PIN_REQUIRED", "PIN_CREATION_UI", "PIN_MUTATION_UI",
        "ACCOUNT_MUTATION_UI", "CREDENTIAL_MUTATION_UI",
        "UNEXPECTED_PREREQUISITE", "ENROLLMENT_COMMIT_UI", "STOP"
    )
    $state = Read-D274Exact "Apri il candidato Configura Windows Hello senza confermare modifiche. Digita PRONTO, EXISTING_PIN_AUTHENTICATION oppure una categoria terminale documentata" (@("PRONTO", "EXISTING_PIN_AUTHENTICATION") + $terminal)
    if ($state -eq "EXISTING_PIN_AUTHENTICATION") {
        Write-Host "Se Windows chiede il PIN già configurato solo per verificare la tua identità, inseriscilo direttamente nella finestra di Windows. Il Kit non deve conoscerlo né registrarlo. Se Windows propone di creare o modificare il PIN, fermati."
        $state = Read-D274Exact "Dopo la sola verifica identità nella UI Windows, digita PRONTO oppure una categoria terminale documentata" (@("PRONTO") + $terminal)
    }
    if ($state -ne "PRONTO") { Fail-D274Live ("condizione UI terminale: " + $state) }
}

function Test-D274PrivateOutputRoot([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        New-Item -ItemType Directory -Path $Root -Force | Out-Null
    }
    $item = Get-Item -LiteralPath $Root -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
    $acl = $null
    try { $acl = Get-Acl -Path $item.FullName -ErrorAction Stop } catch { return $false }
    $wellKnownSids = @("S-1-1-0", "S-1-5-32-545", "S-1-5-11", "S-1-5-32-546")
    $badRights = ([System.Security.AccessControl.FileSystemRights]::Read) -bor
                 ([System.Security.AccessControl.FileSystemRights]::Write) -bor
                 ([System.Security.AccessControl.FileSystemRights]::Modify) -bor
                 ([System.Security.AccessControl.FileSystemRights]::FullControl)
    foreach ($ace in $acl.Access) {
        if ($ace.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { continue }
        if (($ace.FileSystemRights -band $badRights) -eq 0) { continue }
        try { $sid = $ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]) } catch { return $false }
        if ($wellKnownSids -contains $sid.Value) { return $false }
    }
    return $true
}

# Gate autoritativo: il template distribuito ha tutti i flag false. Nessuna
# opzione CLI può sostituire questa authority separatamente revisionata.
$authority = Get-Content -LiteralPath $AuthorityPath -Raw | ConvertFrom-Json
if ($authority.schema -ne "D274_03_LIVE_AUTHORITY_V1") { Fail-D274Live "schema authority non valido" }
if ($NativeQualificationOnly) {
    if ($authority.baseline_approved -ne $false -or
        $authority.approved_for_capture -ne $false -or
        $authority.live_authorized -ne $false) {
        Fail-D274Live "la qualificazione innocua richiede il template authority chiuso"
    }
    Assert-D274GoodixAbsentSameRun | Out-Null
    [ordered]@{
        schema = "D274_03_SAME_RUN_ABSENCE_GATE_QUALIFICATION_V1"
        result = "PASS"
        goodix_present_in_guest = $false
        same_run_goodix_absence_gate = "PASS_NATIVE"
        marker_created = $false
        capture_started = $false
        finger_prompt_presented = $false
        real_usb_open_count = 0
    } | ConvertTo-Json -Depth 3
    exit 0
}
if ($authority.baseline_approved -ne $true) { Fail-D274Live "baseline non approvata" }
if ($authority.approved_for_capture -ne $true) { Fail-D274Live "capture non approvata" }
if ($authority.live_authorized -ne $true) { Fail-D274Live "live non autorizzato" }
$approvedSha = [string]$authority.approved_full_commit_sha
if ($approvedSha -notmatch '^[0-9a-f]{40}$') { Fail-D274Live "SHA completo approvato assente o non valido" }
$authorizationId = [string]$authority.one_shot_authorization_id
if ($authorizationId -notmatch '^[A-Za-z0-9_-]{12,80}$') { Fail-D274Live "identificatore one-shot non valido" }

$head = (& git -C $RepositoryRoot rev-parse HEAD 2>&1 | Select-Object -First 1).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $approvedSha) { Fail-D274Live "HEAD diverso dalla baseline approvata" }
$branch = (& git -C $RepositoryRoot branch --show-current 2>&1 | Select-Object -First 1).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne "main") { Fail-D274Live "branch diversa da main" }

$critical = @(
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/avvia-d274-03.ps1",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/invoke-d274-03-live-once.ps1",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/collect-d274-03-results.ps1",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_observe_second_b0.py",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/D274_03_evidence_schema.json"
)
& git -C $RepositoryRoot diff --quiet $approvedSha -- @critical
if ($LASTEXITCODE -ne 0) { Fail-D274Live "live-critical set diverso dalla baseline approvata" }
$criticalStatus = @(& git -C $RepositoryRoot status --porcelain -- @critical)
if ($LASTEXITCODE -ne 0 -or $criticalStatus.Count -ne 0) {
    Fail-D274Live "live-critical set sporco o non tracciato"
}

$captureRoot = Join-Path $RepositoryRoot "captures\D274_03"
if (-not (Test-Path -LiteralPath $captureRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $captureRoot -Force | Out-Null
}
$captureItem = Get-Item -LiteralPath $captureRoot
if (($captureItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    Fail-D274Live "la radice capture è un reparse point"
}
if (-not (Test-D274PrivateOutputRoot -Root $captureRoot)) {
    Fail-D274Live "la radice capture non soddisfa il contratto privacy ACL"
}

# Gate causale della stessa invocazione live. Deve precedere marker, capture,
# attach e qualunque prompt dito; non modifica PnP e non apre il device.
Assert-D274GoodixAbsentSameRun | Out-Null

$marker = Join-Path $captureRoot "D274_03_ONE_SHOT_CONSUMED.marker"
$markerStream = $null
try {
    $markerStream = [System.IO.File]::Open($marker, [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $markerText = "authorization_id=$authorizationId`napproved_sha=$approvedSha`nconsumed_utc=$([DateTimeOffset]::UtcNow.ToString('o'))`n"
    $markerBytes = [System.Text.Encoding]::UTF8.GetBytes($markerText)
    $markerStream.Write($markerBytes, 0, $markerBytes.Length)
    $markerStream.Flush()
} catch {
    Fail-D274Live "marker one-shot già esistente o non creabile; nessun retry consentito"
} finally {
    if ($null -ne $markerStream) { $markerStream.Dispose() }
}

$runRoot = Join-Path $captureRoot $authorizationId
$rawRoot = Join-Path $runRoot "raw"
$resultRoot = Join-Path $runRoot "sanitized"
if (Test-Path -LiteralPath $runRoot) { Fail-D274Live "output one-shot già esistente" }
New-Item -ItemType Directory -Path $rawRoot -Force | Out-Null
New-Item -ItemType Directory -Path $resultRoot -Force | Out-Null
$rawCapture = Join-Path $rawRoot "wire.pcapng"
$observerSignal = Join-Path $rawRoot "observer_second_b0_signal.json"
$evidenceOutput = Join-Path $resultRoot "D274_03_second_cycle_evidence.json"
$python = Get-D274Python
if ($null -eq $python) { Fail-D274Live "Python non disponibile per observer e sanitizzazione offline" }

Write-Host ""
Write-Host "D274/03 — cattura OEM one-shot del secondo ciclo"
Write-Host "NON toccare il sensore finché non viene richiesto."
Write-Host "È ammessa solo l'autenticazione con il PIN già configurato nella UI Windows; sono vietati creazione/modifica PIN, account/credenziali e completamento enrollment."
Write-Host "Non esiste alcun retry automatico: questa authority viene consumata ora."

$arguments = @("-i", $UsbPcapInterface, "-a", "duration:180", "-q", "-w", ('"{0}"' -f $rawCapture))
try {
    $script:CaptureProcess = Start-Process -FilePath $TsharkPath -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $script:CaptureStarted = $true
    Start-Sleep -Milliseconds 800
    if ($script:CaptureProcess.HasExited) { Fail-D274Live "il processo di cattura si è arrestato all'avvio" }

    $observer = Join-Path $PSScriptRoot "d274_03_observe_second_b0.py"
    $observerArguments = @(
        ('"{0}"' -f $observer), "--pcap", ('"{0}"' -f $rawCapture),
        "--signal-output", ('"{0}"' -f $observerSignal),
        "--deadline-seconds", "180", "--poll-milliseconds", "100"
    )
    $script:ObserverProcess = Start-Process -FilePath $python -ArgumentList $observerArguments -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 200
    if ($script:ObserverProcess.HasExited) { Fail-D274Live "observer wire passivo arrestato all'avvio" }

    $attach = Read-D274Exact "Collega ora il solo sensore target alla VM. Digita COLLEGATO oppure STOP" @("COLLEGATO", "STOP")
    if ($attach -eq "STOP") { Fail-D274Live "stop richiesto dall'operatore prima dell'attach" }
    Start-Sleep -Milliseconds 700
    $escapedTarget = [regex]::Escape($script:ExpectedTarget)
    $targets = @(Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { $_.InstanceId -match $escapedTarget })
    if ($targets.Count -ne 1) { Fail-D274Live "target assente o ambiguo dopo l'attach" }

    Read-D274SetupReady
    Write-Host "Appoggia il dito per il PRIMO ciclo e sollevalo appena richiesto dalla UI OEM."
    $first = Read-D274Exact "Dopo aver sollevato il dito, digita PRIMO_OK, INATTESO oppure STOP" @("PRIMO_OK", "INATTESO", "STOP")
    if ($first -ne "PRIMO_OK") { Fail-D274Live ("primo ciclo non confermato: " + $first) }
    $secondReady = Read-D274Exact "Quando la UI richiede il secondo dito, digita SECONDO_DITO_RICHIESTO; per qualunque prerequisito o mutazione usa la categoria terminale documentata" @(
        "SECONDO_DITO_RICHIESTO", "NEW_PIN_REQUIRED", "PIN_CREATION_UI",
        "PIN_MUTATION_UI", "ACCOUNT_MUTATION_UI", "CREDENTIAL_MUTATION_UI",
        "UNEXPECTED_PREREQUISITE", "ENROLLMENT_COMMIT_UI", "STOP")
    if ($secondReady -ne "SECONDO_DITO_RICHIESTO") { Fail-D274Live ("condizione UI terminale: " + $secondReady) }
    Write-Host "Appoggia il dito per il SECONDO ciclo. Il Kit osserverà il wire: non certificare manualmente il B0 e non eseguire un terzo contatto."
    if (-not $script:ObserverProcess.WaitForExit(185000)) {
        Fail-D274Live "SECOND_B0_OBSERVER_DEADLINE; AUTOMATIC_RETRY_COUNT=0"
    }
    if ($script:ObserverProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $observerSignal -PathType Leaf)) {
        Fail-D274Live "observer wire non ha osservato il secondo B0 entro la deadline; AUTOMATIC_RETRY_COUNT=0"
    }
    $signal = Get-Content -LiteralPath $observerSignal -Raw | ConvertFrom-Json
    if ($signal.status -ne "SECOND_FINGERPRINT_B0_OBSERVED" -or $signal.stop_trigger -ne "WIRE_DRIVEN") {
        Fail-D274Live "segnale observer terminale non valido"
    }
    if (-not (Stop-D274Capture)) { Fail-D274Live "CAPTURE_PROCESS_STOP_TIMEOUT" }
    Write-Host "Secondo B0 osservato. NON toccare più il sensore e NON completare l'enrollment."
} finally {
    Stop-D274Observer
    Stop-D274Capture | Out-Null
}

if (-not (Test-Path -LiteralPath $rawCapture -PathType Leaf)) { Fail-D274Live "file capture mancante" }
if ((Get-Item -LiteralPath $rawCapture).Length -le 0) { Fail-D274Live "file capture vuoto" }
$rawHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $rawCapture).Hash.ToLowerInvariant()
$postprocessor = Join-Path $PSScriptRoot "d274_03_postprocess_second_cycle.py"
$postOutput = @(& $python $postprocessor --pcap $rawCapture --expected-sha256 $rawHash --output $evidenceOutput --observer-signal $observerSignal 2>&1)
if ($LASTEXITCODE -ne 0) { Fail-D274Live ("boundary non chiuso: " + (($postOutput | Select-Object -Last 1) -replace '[\r\n]', ' ')) }
$evidence = Get-Content -LiteralPath $evidenceOutput -Raw | ConvertFrom-Json
if ($evidence.boundary_status -ne "OBSERVED_COMPLETE" -or $evidence.stop_reason -ne "SECOND_FINGERPRINT_B0") {
    Fail-D274Live "evidenza sanitizzata non chiude il boundary"
}

Write-Host "SUCCESSO: osservato il secondo B0 fingerprint strutturale; cattura già arrestata."
Write-Host "NON rilanciare il Kit. Consegnare solo i metadata sanitizzati alla review AI-PM."
[ordered]@{
    schema = "D274_03_LIVE_RUN_SUMMARY_V1"
    result = "PASS"
    capture_started = $script:CaptureStarted
    capture_stopped = $script:CaptureStopped
    same_run_goodix_absence_gate = "PASS_BEFORE_MARKER_CAPTURE_ATTACH_FINGER"
    second_b0_stop_trigger = "WIRE_DRIVEN"
    capture_finalization_contract = "FINAL_RAW_READABLE_HASH_GATED_TERMINAL_FRAME_RECOVERED"
    automatic_retry_count = 0
    goodix_manual_command_count = 0
    enrollment_commit_authorized = $false
    account_mutation_authorized = $false
    pin_mutation_authorized = $false
    pin_value_handled_by_kit = $false
    third_cycle_authorized = $false
    sanitized_evidence = $evidenceOutput
} | ConvertTo-Json -Depth 4
