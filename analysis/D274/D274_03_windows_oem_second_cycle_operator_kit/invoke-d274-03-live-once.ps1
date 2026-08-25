# SPDX-License-Identifier: GPL-2.0-or-later
# Percorso futuro live D274/03: cattura passiva USBPcap/TShark, nessun comando Goodix.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RepositoryRoot,
    [Parameter(Mandatory=$true)][string]$AuthorityPath,
    [Parameter(Mandatory=$true)][string]$TsharkPath,
    [Parameter(Mandatory=$true)][string]$UsbPcapInterface
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$script:CaptureProcess = $null
$script:CaptureStarted = $false
$script:CaptureStopped = $false

function Stop-D274Capture {
    if ($null -ne $script:CaptureProcess -and -not $script:CaptureProcess.HasExited) {
        Stop-Process -Id $script:CaptureProcess.Id -ErrorAction SilentlyContinue
        $script:CaptureProcess.WaitForExit(10000) | Out-Null
    }
    $script:CaptureStopped = $true
}

function Fail-D274Live([string]$Message) {
    Stop-D274Capture
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
if ($LASTEXITCODE -ne 0 -or $branch -ne "development") { Fail-D274Live "branch diversa da development" }

$critical = @(
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/avvia-d274-03.ps1",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/invoke-d274-03-live-once.ps1",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/collect-d274-03-results.ps1",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py",
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
$evidenceOutput = Join-Path $resultRoot "D274_03_second_cycle_evidence.json"

Write-Host ""
Write-Host "D274/03 — cattura OEM one-shot del secondo ciclo"
Write-Host "NON toccare il sensore finché non viene richiesto."
Write-Host "Sono vietati nuovo PIN, modifiche account/credenziali e completamento enrollment."
Write-Host "Non esiste alcun retry automatico: questa authority viene consumata ora."

$arguments = @("-i", $UsbPcapInterface, "-a", "duration:180", "-q", "-w", ('"{0}"' -f $rawCapture))
try {
    $script:CaptureProcess = Start-Process -FilePath $TsharkPath -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $script:CaptureStarted = $true
    Start-Sleep -Milliseconds 800
    if ($script:CaptureProcess.HasExited) { Fail-D274Live "il processo di cattura si è arrestato all'avvio" }

    $attach = Read-D274Exact "Collega ora il solo sensore target alla VM. Digita COLLEGATO oppure STOP" @("COLLEGATO", "STOP")
    if ($attach -eq "STOP") { Fail-D274Live "stop richiesto dall'operatore prima dell'attach" }
    Start-Sleep -Milliseconds 700
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D274Live "Get-PnpDevice non disponibile"
    }
    $targets = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "VID_27C6&PID_5125" })
    if ($targets.Count -ne 1) { Fail-D274Live "target assente o ambiguo dopo l'attach" }

    $ui = Read-D274Exact "Apri il candidato Configura Windows Hello senza confermare modifiche. Digita PRONTO, PIN, ACCOUNT, CREDENZIALI, COMMIT, INATTESO oppure STOP" @("PRONTO", "PIN", "ACCOUNT", "CREDENZIALI", "COMMIT", "INATTESO", "STOP")
    if ($ui -ne "PRONTO") { Fail-D274Live ("condizione UI terminale: " + $ui) }
    Write-Host "Appoggia il dito per il PRIMO ciclo e sollevalo appena richiesto dalla UI OEM."
    $first = Read-D274Exact "Dopo aver sollevato il dito, digita PRIMO_OK, INATTESO oppure STOP" @("PRIMO_OK", "INATTESO", "STOP")
    if ($first -ne "PRIMO_OK") { Fail-D274Live ("primo ciclo non confermato: " + $first) }
    Write-Host "Appoggia il dito per il SECONDO ciclo. Non eseguire un terzo contatto."
    $second = Read-D274Exact "Quando la UI OEM conferma il secondo campione, digita SECONDO_OK; se mostra PIN, ACCOUNT, CREDENZIALI, COMMIT o altro, scegli quel termine oppure STOP" @("SECONDO_OK", "PIN", "ACCOUNT", "CREDENZIALI", "COMMIT", "INATTESO", "STOP")
    if ($second -ne "SECONDO_OK") { Fail-D274Live ("secondo ciclo non confermato: " + $second) }
    Stop-D274Capture
    Write-Host "Cattura arrestata. NON toccare più il sensore e NON completare l'enrollment."
} finally {
    Stop-D274Capture
}

if (-not (Test-Path -LiteralPath $rawCapture -PathType Leaf)) { Fail-D274Live "file capture mancante" }
$rawHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $rawCapture).Hash.ToLowerInvariant()
$python = Get-D274Python
if ($null -eq $python) { Fail-D274Live "Python non disponibile per la sanitizzazione offline" }
$postprocessor = Join-Path $PSScriptRoot "d274_03_postprocess_second_cycle.py"
$postOutput = @(& $python $postprocessor --pcap $rawCapture --expected-sha256 $rawHash --output $evidenceOutput 2>&1)
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
    automatic_retry_count = 0
    goodix_manual_command_count = 0
    enrollment_commit_authorized = $false
    account_mutation_authorized = $false
    pin_mutation_authorized = $false
    third_cycle_authorized = $false
    sanitized_evidence = $evidenceOutput
} | ConvertTo-Json -Depth 4
