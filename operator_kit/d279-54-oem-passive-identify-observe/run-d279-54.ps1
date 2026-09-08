# SPDX-License-Identifier: GPL-2.0-or-later
# D279/54 passive Windows OEM identify observation. PowerShell Desktop 5.1.
[CmdletBinding()]
param(
    [switch]$SelfTestOnly,
    [switch]$NativeQualificationOnly,
    [switch]$AutorizzoIdentifyOemPassivoD27954,
    [string]$AuthorityPath = (Join-Path $PSScriptRoot "D279_54_live_authority.json")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$script:ExpectedTarget = "VID_27C6&PID_5125"
$script:CaptureProcess = $null
$script:CaptureStarted = $false
$script:CaptureStopped = $false
$script:TargetAttached = $false
$script:VerificationStarted = $false
$script:VerificationCompleted = $false
$script:VerificationResult = "NOT_STARTED"
$script:RunRoot = $null
$script:RawRoot = $null
$script:SanitizedRoot = $null
$script:AttemptStatus = $null
$script:Pcap = $null
$script:Critical = @(
    "operator_kit/d279-54-oem-passive-identify-observe/run-d279-54.ps1",
    "operator_kit/d279-54-oem-passive-identify-observe/README_IT.md",
    "operator_kit/d279-54-oem-passive-identify-observe/D279_54_live_authority.json"
)

function Fail-D27954([string]$Message) {
    throw "D279_54_FAIL_CLOSED: $Message"
}

function Read-D27954Menu([string]$Title, [hashtable]$Options) {
    Write-Host ""
    Write-Host $Title
    foreach ($key in @($Options.Keys | Sort-Object)) {
        Write-Host ("{0} - {1}" -f $key, $Options[$key])
    }
    $raw = (Read-Host "Scelta numerica").Trim()
    $value = 0
    if (-not [int]::TryParse($raw, [ref]$value) -or
        -not $Options.ContainsKey($value)) {
        Fail-D27954 "risposta non numerica o non ammessa"
    }
    return $value
}

function Write-D27954JsonOnce([string]$Path, [object]$Document) {
    $json = $Document | ConvertTo-Json -Depth 10
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json + "`n")
    $stream = $null
    try {
        $stream = [System.IO.File]::Open(
            $Path, [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Get-D27954RepositoryRoot {
    $output = & git -C $PSScriptRoot rev-parse --show-toplevel 2>&1
    if ($LASTEXITCODE -ne 0) { Fail-D27954 "repository Git non individuabile" }
    $root = ([string](@($output) | Select-Object -First 1)).Trim()
    if ([string]::IsNullOrWhiteSpace($root)) { Fail-D27954 "Git root vuota" }
    return [System.IO.Path]::GetFullPath($root)
}

function Get-D27954Tshark {
    $command = Get-Command tshark.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    $candidate = Join-Path $env:ProgramFiles "Wireshark\tshark.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return $null
}

function Invoke-D27954NativeCaptured(
    [string]$Executable, [string[]]$Arguments) {
    $saved = $ErrorActionPreference
    $captured = @()
    $code = $null
    try {
        $ErrorActionPreference = "Continue"
        $captured = @(& $Executable @Arguments 2>&1)
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
    }
    if ($null -eq $code) { Fail-D27954 "exit code nativo non disponibile" }
    return [pscustomobject]@{
        ExitCode = [int]$code
        Output = @($captured | ForEach-Object { [string]$_ })
    }
}

function Get-D27954UsbPcapSelector([string]$Tshark) {
    $result = Invoke-D27954NativeCaptured $Tshark @("-D")
    if ($result.ExitCode -ne 0) { Fail-D27954 "tshark -D fallito" }
    $interfaces = @($result.Output | Where-Object { $_ -match "USBPcap" })
    if ($interfaces.Count -ne 1) {
        Fail-D27954 "interfaccia USBPcap assente o ambigua"
    }
    $match = [regex]::Match([string]$interfaces[0], '^\s*(\d+)\.')
    if (-not $match.Success) { Fail-D27954 "selector USBPcap non ricavabile" }
    return $match.Groups[1].Value
}

function Get-D27954TargetCount {
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D27954 "Get-PnpDevice non disponibile"
    }
    $target = [regex]::Escape($script:ExpectedTarget)
    return @(Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { $_.InstanceId -match $target }).Count
}

function Assert-D27954TargetAbsent {
    if ((Get-D27954TargetCount) -ne 0) {
        Fail-D27954 "GOODIX_PRESENT_IN_GUEST=true; il target deve essere assente"
    }
}

function Test-D27954PrivateRoot([string]$Root) {
    $item = Get-Item -LiteralPath $Root -ErrorAction Stop
    if (($item.Attributes -band
         [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
    try { $acl = Get-Acl -Path $item.FullName -ErrorAction Stop }
    catch { return $false }
    $broad = @("S-1-1-0", "S-1-5-32-545", "S-1-5-11", "S-1-5-32-546")
    $rights = ([System.Security.AccessControl.FileSystemRights]::Read) -bor
              ([System.Security.AccessControl.FileSystemRights]::Write) -bor
              ([System.Security.AccessControl.FileSystemRights]::Modify) -bor
              ([System.Security.AccessControl.FileSystemRights]::FullControl)
    foreach ($ace in $acl.Access) {
        if ($ace.AccessControlType -ne
            [System.Security.AccessControl.AccessControlType]::Allow) { continue }
        if (($ace.FileSystemRights -band $rights) -eq 0) { continue }
        try {
            $sid = $ace.IdentityReference.Translate(
                [System.Security.Principal.SecurityIdentifier])
        } catch { return $false }
        if ($broad -contains $sid.Value) { return $false }
    }
    return $true
}

function Read-D27954Authority([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail-D27954 "authority assente"
    }
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if (($item.Attributes -band
         [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Fail-D27954 "authority symlink/reparse non ammessa"
    }
    $authority = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($authority.schema -ne "D279_54_LIVE_AUTHORITY_V1") {
        Fail-D27954 "schema authority non valido"
    }
    return $authority
}

function Stop-D27954Capture {
    if ($null -ne $script:CaptureProcess -and
        -not $script:CaptureProcess.HasExited) {
        Stop-Process -Id $script:CaptureProcess.Id -ErrorAction SilentlyContinue
        if (-not $script:CaptureProcess.WaitForExit(10000)) { return $false }
    }
    if ($null -ne $script:CaptureProcess) {
        $script:CaptureStopped = $script:CaptureProcess.HasExited
    }
    return $script:CaptureStopped
}

function Get-D27954RestoreClassification {
    if ($script:VerificationStarted) {
        return "RESTORE_SNAPSHOT_REQUIRED_AFTER_OEM_IDENTIFY"
    }
    if ($script:TargetAttached) {
        return "RESTORE_SNAPSHOT_REQUIRED_STATE_UNCERTAIN"
    }
    return "RERUN_WITHOUT_RESTORE_REASONABLE"
}

function Write-D27954AttemptStatus([string]$Result, [string]$FailureClass) {
    if ($null -eq $script:AttemptStatus -or
        (Test-Path -LiteralPath $script:AttemptStatus)) { return }
    $hash = $null
    if ($null -ne $script:Pcap -and
        (Test-Path -LiteralPath $script:Pcap -PathType Leaf)) {
        $fileHash = Get-FileHash -Algorithm SHA256 -LiteralPath $script:Pcap
        $hash = $fileHash.Hash.ToLowerInvariant()
    }
    Write-D27954JsonOnce $script:AttemptStatus ([ordered]@{
        schema = "D279_54_ATTEMPT_STATUS_V1"
        attempt_id = (Split-Path $script:RunRoot -Leaf)
        result = $Result
        failure_class = $FailureClass
        target_attached = $script:TargetAttached
        verification_started = $script:VerificationStarted
        verification_completed = $script:VerificationCompleted
        verification_result = $script:VerificationResult
        capture_started = $script:CaptureStarted
        capture_stopped = $script:CaptureStopped
        capture_sha256 = $hash
        automatic_retry_count = 0
        rerun_classification = Get-D27954RestoreClassification
        export_before_snapshot_restore_raw = $script:RawRoot
        export_before_snapshot_restore_sanitized = $script:SanitizedRoot
    })
}

function Invoke-D27954SelfTest {
    if ($PSVersionTable.PSEdition -ne "Desktop" -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -lt 1) {
        Fail-D27954 "e richiesto Windows PowerShell Desktop 5.1"
    }
    foreach ($name in @("run-d279-54.ps1", "README_IT.md",
                         "D279_54_live_authority.json")) {
        $kitFile = Join-Path $PSScriptRoot $name
        if (-not (Test-Path -LiteralPath $kitFile -PathType Leaf)) {
            Fail-D27954 "file del kit mancante"
        }
    }
    $authority = Read-D27954Authority (
        Join-Path $PSScriptRoot "D279_54_live_authority.json")
    if ($authority.baseline_approved -ne $false -or
        $authority.approved_for_passive_capture -ne $false -or
        $authority.oem_identify_authorized -ne $false -or
        $authority.existing_oem_template_confirmed -ne $false -or
        $authority.possible_adaptive_template_persistence_accepted -ne $false -or
        $authority.snapshot_prerun_confirmed -ne $false -or
        $authority.live_authorized -ne $false -or
        $null -ne $authority.approved_full_commit_sha -or
        $null -ne $authority.authorized_attempt_id) {
        Fail-D27954 "il template authority versionato non e chiuso"
    }
    [ordered]@{
        schema = "D279_54_SELFTEST_V1"
        result = "PASS"
        authority_template_closed = $true
        live_path_executed = $false
        hardware_action_count = 0
        automatic_retry_count = 0
    } | ConvertTo-Json -Depth 4
}

function Assert-D27954Repository([string]$Root, [string]$ApprovedHead) {
    $head = ([string](& git -C $Root rev-parse HEAD 2>&1)).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') {
        Fail-D27954 "HEAD completo non leggibile"
    }
    $branch = ([string](& git -C $Root branch --show-current 2>&1)).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne "development") {
        Fail-D27954 "branch diverso da development"
    }
    if ($head -ne $ApprovedHead) { Fail-D27954 "HEAD diverso dalla baseline" }
    $critical = $script:Critical
    $dirty = @(& git -C $Root status --short -- @critical 2>&1)
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) {
        Fail-D27954 "live-critical set sporco"
    }
}

function Invoke-D27954NativeQualification {
    Invoke-D27954SelfTest | Out-Null
    Assert-D27954TargetAbsent
    $root = Get-D27954RepositoryRoot
    $head = ([string](& git -C $root rev-parse HEAD 2>&1)).Trim()
    Assert-D27954Repository $root $head
    $tshark = Get-D27954Tshark
    if ($null -eq $tshark) { Fail-D27954 "tshark.exe non disponibile" }
    $selector = Get-D27954UsbPcapSelector $tshark
    [ordered]@{
        schema = "D279_54_NATIVE_QUALIFICATION_V1"
        result = "PASS"
        head = $head
        usbpcap_selector = $selector
        goodix_present = $false
        capture_started = $false
        live_path_executed = $false
    } | ConvertTo-Json -Depth 4
}

if ($SelfTestOnly) {
    if ($NativeQualificationOnly -or $AutorizzoIdentifyOemPassivoD27954) {
        Fail-D27954 "modalita incompatibili"
    }
    Invoke-D27954SelfTest
    exit 0
}
if ($NativeQualificationOnly) {
    if ($AutorizzoIdentifyOemPassivoD27954) { Fail-D27954 "modalita incompatibili" }
    Invoke-D27954NativeQualification
    exit 0
}
if (-not $AutorizzoIdentifyOemPassivoD27954) {
    Fail-D27954 "live non autorizzato: usa prima SelfTestOnly/NativeQualificationOnly"
}

# Live path. Every gate below precedes capture and target attach.
$authority = Read-D27954Authority $AuthorityPath
if ($authority.baseline_approved -ne $true -or
    $authority.approved_for_passive_capture -ne $true -or
    $authority.oem_identify_authorized -ne $true -or
    $authority.existing_oem_template_confirmed -ne $true -or
    $authority.possible_adaptive_template_persistence_accepted -ne $true -or
    $authority.snapshot_prerun_confirmed -ne $true -or
    $authority.live_authorized -ne $true) {
    Fail-D27954 "authority per-attempt incompleta"
}
$approved = [string]$authority.approved_full_commit_sha
$attemptId = [string]$authority.authorized_attempt_id
if ($approved -notmatch '^[0-9a-f]{40}$') { Fail-D27954 "full SHA non valido" }
if ($attemptId -notmatch '^D27954_[A-Za-z0-9_-]+$') {
    Fail-D27954 "attempt ID non valido"
}
$root = Get-D27954RepositoryRoot
Assert-D27954Repository $root $approved
Assert-D27954TargetAbsent
$tshark = Get-D27954Tshark
if ($null -eq $tshark) { Fail-D27954 "tshark.exe non disponibile" }
$selector = Get-D27954UsbPcapSelector $tshark

$script:RunRoot = Join-Path $root ("captures\D279_54\" + $attemptId)
$script:RawRoot = Join-Path $script:RunRoot "raw"
$script:SanitizedRoot = Join-Path $script:RunRoot "sanitized"
if (Test-Path -LiteralPath $script:RunRoot) { Fail-D27954 "attempt gia esistente" }
New-Item -ItemType Directory -Path $script:RawRoot | Out-Null
New-Item -ItemType Directory -Path $script:SanitizedRoot | Out-Null
if (-not (Test-D27954PrivateRoot $script:RunRoot)) {
    Fail-D27954 "directory attempt non privata"
}
$lockPath = Join-Path $script:RunRoot "attempt.lock"
$lock = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
$lock.Dispose()
$script:Pcap = Join-Path $script:RawRoot "wire.pcapng"
$script:AttemptStatus = Join-Path $script:SanitizedRoot "attempt_status.json"
$eventsPath = Join-Path $script:SanitizedRoot "operator_events.json"
$captureStartedUtc = $null
$verificationStartedUtc = $null
$verificationCompletedUtc = $null
$captureStoppedUtc = $null

try {
    Write-Host "D279/54: capture passiva di una sola identify OEM Windows."
    Write-Host "Nessun retry, enrollment o sender Goodix e consentito."
    $script:CaptureProcess = Start-Process -FilePath $tshark -ArgumentList @(
        "-i", $selector, "-w", ('"{0}"' -f $script:Pcap), "-q") -PassThru
    $script:CaptureStarted = $true
    $captureStartedUtc = [DateTimeOffset]::UtcNow.ToString('o')
    Start-Sleep -Milliseconds 500
    if ($script:CaptureProcess.HasExited) { Fail-D27954 "capture arrestata all'avvio" }

    $attach = Read-D27954Menu "Collegamento target" @{
        1 = "Il solo sensore target e collegato alla VM"
        0 = "Stop"
    }
    if ($attach -ne 1) { Fail-D27954 "stop prima dell'attach" }
    $script:TargetAttached = $true
    Start-Sleep -Milliseconds 700
    if ((Get-D27954TargetCount) -ne 1) {
        Fail-D27954 "target assente o ambiguo dopo attach"
    }
    if ($script:CaptureProcess.HasExited) { Fail-D27954 "capture terminata" }

    $ready = Read-D27954Menu "Prerequisito Windows Hello" @{
        1 = "Esiste gia una impronta; sono pronto a bloccare Windows"
        2 = "Manca l'impronta o Windows propone enrollment/modifica PIN"
        0 = "Stop"
    }
    if ($ready -ne 1) { Fail-D27954 "template OEM preesistente non disponibile" }
    Write-Host "Premi Win+L, esegui UN SOLO contatto con il dito gia registrato,"
    Write-Host "poi torna a questa console senza ripetere il contatto."
    $script:VerificationStarted = $true
    $verificationStartedUtc = [DateTimeOffset]::UtcNow.ToString('o')
    $result = Read-D27954Menu "Esito dell'unico tentativo" @{
        1 = "Windows ha sbloccato con fingerprint"
        2 = "No-match o fallback PIN; nessun secondo contatto"
        3 = "Anomalia o UI non classificabile"
        0 = "Stop"
    }
    if ($result -eq 1) {
        $script:VerificationResult = "WINDOWS_UI_FINGERPRINT_SUCCESS"
        $script:VerificationCompleted = $true
    } elseif ($result -eq 2) {
        $script:VerificationResult = "WINDOWS_UI_NO_MATCH_OR_PIN_FALLBACK"
        Fail-D27954 "identify non riuscita; retry vietato"
    } else {
        $script:VerificationResult = "WINDOWS_UI_ANOMALY_OR_OPERATOR_STOP"
        Fail-D27954 "identify non classificabile; retry vietato"
    }
    $verificationCompletedUtc = [DateTimeOffset]::UtcNow.ToString('o')
    Start-Sleep -Seconds 5
    if ($script:CaptureProcess.HasExited) { Fail-D27954 "capture terminata nel tail" }
    if (-not (Stop-D27954Capture)) { Fail-D27954 "arresto capture fallito" }
    $captureStoppedUtc = [DateTimeOffset]::UtcNow.ToString('o')
    if (-not (Test-Path -LiteralPath $script:Pcap -PathType Leaf) -or
        (Get-Item -LiteralPath $script:Pcap).Length -le 0) {
        Fail-D27954 "pcap assente o vuoto"
    }
    $readback = Invoke-D27954NativeCaptured $tshark @("-r", $script:Pcap, "-c", "1")
    if ($readback.ExitCode -ne 0) { Fail-D27954 "pcap non leggibile" }
    $fileHash = Get-FileHash -Algorithm SHA256 -LiteralPath $script:Pcap
    $hash = $fileHash.Hash.ToLowerInvariant()
    Write-D27954JsonOnce $eventsPath ([ordered]@{
        schema = "D279_54_OPERATOR_EVENTS_V1"
        attempt_id = $attemptId
        capture_started_utc = $captureStartedUtc
        verification_started_utc = $verificationStartedUtc
        verification_completed_utc = $verificationCompletedUtc
        capture_stopped_utc = $captureStoppedUtc
        verification_attempt_count = 1
        verification_result = $script:VerificationResult
        terminal_tail_seconds = 5
        capture_sha256 = $hash
        automatic_retry_count = 0
    })
    Write-D27954AttemptStatus "PASS_UI_CONFIRMED" "NONE"
    Write-Host "D279_54_CAPTURE=PASS_UI_CONFIRMED"
    Write-Host ("D279_54_CAPTURE_SHA256={0}" -f $hash)
    Write-Host ("ESPORTA PRIMA DI QUALSIASI RESTORE RAW: {0}" -f $script:RawRoot)
    Write-Host ("ESPORTA PRIMA DI QUALSIASI RESTORE SANITIZED: {0}" -f $script:SanitizedRoot)
    exit 0
} catch {
    [void](Stop-D27954Capture)
    Write-D27954AttemptStatus "FAIL_CLOSED" ([string]$_.Exception.Message)
    Write-Error $_
    exit 1
} finally {
    [void](Stop-D27954Capture)
}