# SPDX-License-Identifier: GPL-2.0-or-later
# D279/10 passive full Windows OEM enrollment observation. PowerShell 5.1.
[CmdletBinding()]
param(
    [switch]$SelfTestOnly,
    [switch]$NativeQualificationOnly,
    [switch]$AutorizzoEnrollmentOemCompletoD27910,
    [string]$AuthorityPath = (Join-Path $PSScriptRoot "D279_10_live_authority.json")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$script:ExpectedTarget = "VID_27C6&PID_5125"
$script:CaptureProcess = $null
$script:ObserverProcess = $null
$script:CaptureStarted = $false
$script:CaptureStopped = $false
$script:TargetAttached = $false
$script:WizardStarted = $false
$script:EnrollmentCompleted = $false
$script:ContactCount = 0
$script:RunRoot = $null
$script:RawRoot = $null
$script:SanitizedRoot = $null
$script:AttemptStatus = $null
$script:Pcap = $null
$script:Critical = @(
    "operator_kit/d279-10-third-acquisition-observe/run-d279-10.ps1",
    "operator_kit/d279-10-third-acquisition-observe/d279_10_third_cycle.py",
    "operator_kit/d279-10-third-acquisition-observe/d279_10_observer.py",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py"
)

function Fail-D279([string]$Message) {
    throw "D279_10_FAIL_CLOSED: $Message"
}

function Stop-D279Observer {
    if ($null -ne $script:ObserverProcess -and -not $script:ObserverProcess.HasExited) {
        Stop-Process -Id $script:ObserverProcess.Id -ErrorAction SilentlyContinue
        $script:ObserverProcess.WaitForExit(5000) | Out-Null
    }
}

function Stop-D279Capture {
    if ($null -ne $script:CaptureProcess -and -not $script:CaptureProcess.HasExited) {
        Stop-Process -Id $script:CaptureProcess.Id -ErrorAction SilentlyContinue
        if (-not $script:CaptureProcess.WaitForExit(10000)) { return $false }
    }
    if ($null -ne $script:CaptureProcess) {
        $script:CaptureStopped = $script:CaptureProcess.HasExited
    }
    return $script:CaptureStopped
}

function Read-D279Menu([string]$Title, [hashtable]$Options) {
    Write-Host ""
    Write-Host $Title
    foreach ($key in @($Options.Keys | Sort-Object)) {
        Write-Host ("{0} - {1}" -f $key, $Options[$key])
    }
    $raw = (Read-Host "Scelta numerica").Trim()
    $value = 0
    if (-not [int]::TryParse($raw, [ref]$value) -or -not $Options.ContainsKey($value)) {
        Fail-D279 "risposta non numerica o non ammessa"
    }
    return $value
}

function Write-D279JsonOnce([string]$Path, [object]$Document) {
    $json = $Document | ConvertTo-Json -Depth 12
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json + "`n")
    $stream = $null
    try {
        $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Get-D279RepositoryRoot {
    $rootOutput = & git -C $PSScriptRoot rev-parse --show-toplevel 2>&1
    if ($LASTEXITCODE -ne 0) { Fail-D279 "repository Git non individuabile" }
    $root = ([string](@($rootOutput) | Select-Object -First 1)).Trim()
    if ([string]::IsNullOrWhiteSpace($root)) { Fail-D279 "repository Git vuoto" }
    return [System.IO.Path]::GetFullPath($root)
}

function Get-D279Python {
    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) { return $command.Source }
    }
    return $null
}

function Get-D279Tshark {
    $command = Get-Command tshark.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    $candidate = Join-Path $env:ProgramFiles "Wireshark\tshark.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return $null
}

function Invoke-D279NativeCaptured([string]$Executable, [string[]]$Arguments) {
    # Windows PowerShell Desktop 5.1 promotes redirected native stderr to a
    # NativeCommandError when the ambient preference is Stop.  Limit Continue
    # to the native invocation, capture both streams, preserve the real native
    # exit code, and restore the fail-closed preference even on exceptions.
    $savedErrorActionPreference = $ErrorActionPreference
    $captured = @()
    $nativeExitCode = $null
    try {
        $ErrorActionPreference = "Continue"
        $captured = @(& $Executable @Arguments 2>&1)
        $nativeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
    if ($null -eq $nativeExitCode) { Fail-D279 "exit code nativo non disponibile" }
    return [pscustomobject]@{
        ExitCode = [int]$nativeExitCode
        Output = @($captured | ForEach-Object { [string]$_ })
    }
}

function Get-D279UsbPcapSelector([string]$Tshark) {
    $interfaces = @(& $Tshark -D 2>&1 | Where-Object { $_ -match "USBPcap" })
    if ($interfaces.Count -ne 1) { Fail-D279 "interfaccia USBPcap assente o ambigua" }
    $match = [regex]::Match([string]$interfaces[0], '^\s*(\d+)\.')
    if (-not $match.Success) { Fail-D279 "selector USBPcap non ricavabile" }
    return $match.Groups[1].Value
}

function Assert-D279GoodixAbsentSameRun {
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D279 "Get-PnpDevice non disponibile"
    }
    $target = [regex]::Escape($script:ExpectedTarget)
    $devices = @(Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { $_.InstanceId -match $target })
    if ($devices.Count -ne 0) {
        Fail-D279 "GOODIX_PRESENT_IN_GUEST=true; il target deve essere assente"
    }
}

function Test-D279PrivateRoot([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        New-Item -ItemType Directory -Path $Root | Out-Null
    }
    $item = Get-Item -LiteralPath $Root -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
    try { $acl = Get-Acl -Path $item.FullName -ErrorAction Stop } catch { return $false }
    $broad = @("S-1-1-0", "S-1-5-32-545", "S-1-5-11", "S-1-5-32-546")
    $rights = ([System.Security.AccessControl.FileSystemRights]::Read) -bor
              ([System.Security.AccessControl.FileSystemRights]::Write) -bor
              ([System.Security.AccessControl.FileSystemRights]::Modify) -bor
              ([System.Security.AccessControl.FileSystemRights]::FullControl)
    foreach ($ace in $acl.Access) {
        if ($ace.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { continue }
        if (($ace.FileSystemRights -band $rights) -eq 0) { continue }
        try { $sid = $ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]) }
        catch { return $false }
        if ($broad -contains $sid.Value) { return $false }
    }
    return $true
}

function Read-D279Authority([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { Fail-D279 "authority assente" }
    $authority = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($authority.schema -ne "D279_10_LIVE_AUTHORITY_V2") { Fail-D279 "schema authority non valido" }
    return $authority
}

function Assert-D279LiveProcesses {
    if ($null -eq $script:CaptureProcess -or $script:CaptureProcess.HasExited) {
        Fail-D279 "capture terminata prima della conclusione UI"
    }
    if ($null -eq $script:ObserverProcess -or $script:ObserverProcess.HasExited) {
        Fail-D279 "observer terminato prima della conclusione UI"
    }
}

function Get-D279RestoreClassification {
    if ($script:EnrollmentCompleted) {
        return "RESTORE_SNAPSHOT_REQUIRED_BEFORE_ANOTHER_FIRST_ENROLLMENT"
    }
    if (-not $script:TargetAttached -and -not $script:WizardStarted) {
        return "RERUN_WITHOUT_RESTORE_REASONABLE"
    }
    return "RESTORE_SNAPSHOT_REQUIRED_STATE_UNCERTAIN"
}

function Write-D279AttemptStatus([string]$Result, [string]$FailureClass) {
    if ($null -eq $script:AttemptStatus -or (Test-Path -LiteralPath $script:AttemptStatus)) { return }
    $rawHash = $null
    if ($null -ne $script:Pcap -and (Test-Path -LiteralPath $script:Pcap -PathType Leaf)) {
        $rawHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $script:Pcap).Hash.ToLowerInvariant()
    }
    $document = [ordered]@{
        schema = "D279_10_ATTEMPT_STATUS_V2"
        attempt_id = (Split-Path $script:RunRoot -Leaf)
        result = $Result
        failure_class = $FailureClass
        target_attached = $script:TargetAttached
        wizard_started = $script:WizardStarted
        contact_count = $script:ContactCount
        enrollment_completed = $script:EnrollmentCompleted
        capture_started = $script:CaptureStarted
        capture_stopped = $script:CaptureStopped
        capture_sha256 = $rawHash
        automatic_retry_count = 0
        rerun_classification = Get-D279RestoreClassification
        export_before_snapshot_restore_raw = $script:RawRoot
        export_before_snapshot_restore_sanitized = $script:SanitizedRoot
    }
    Write-D279JsonOnce $script:AttemptStatus $document
}

function Invoke-D279SelfTest {
    if ($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) {
        Fail-D279 "e richiesto Windows PowerShell Desktop 5.1"
    }
    $required = @("d279_10_third_cycle.py", "d279_10_observer.py",
        "D279_10_live_authority.json", "README_IT.md")
    $missing = @($required | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $_) -PathType Leaf)
    })
    if ($missing.Count -ne 0) { Fail-D279 ("file mancanti: " + ($missing -join ", ")) }
    $authority = Read-D279Authority (Join-Path $PSScriptRoot "D279_10_live_authority.json")
    if ($authority.baseline_approved -ne $false -or
        $authority.approved_for_passive_capture -ne $false -or
        $authority.full_oem_enrollment_authorized -ne $false -or
        $authority.host_vm_enrollment_mutation_accepted -ne $true -or
        $authority.possible_sensor_side_template_persistence_accepted -ne $true -or
        $authority.snapshot_prerun_confirmed -ne $false -or
        $authority.live_authorized -ne $false) {
        Fail-D279 "il template authority versionato non e chiuso"
    }
    [ordered]@{
        schema = "D279_10_SELFTEST_V2"
        result = "PASS"
        operator_inputs = "NUMERIC_ONLY"
        authority_template_closed = $true
        global_marker_present = $false
        attempt_scoped_create_new = $true
        live_path_executed = $false
        hardware_action_count = 0
        automatic_retry_count = 0
    } | ConvertTo-Json -Depth 4
}

function Invoke-D279NativeQualification {
    Invoke-D279SelfTest | Out-Null
    Assert-D279GoodixAbsentSameRun
    $root = Get-D279RepositoryRoot
    $headOutput = & git -C $root rev-parse HEAD 2>&1
    if ($LASTEXITCODE -ne 0) { Fail-D279 "HEAD non leggibile" }
    $head = ([string](@($headOutput) | Select-Object -First 1)).Trim()
    if ($head -notmatch '^[0-9a-f]{40}$') { Fail-D279 "HEAD completo non valido" }
    $branchOutput = & git -C $root branch --show-current 2>&1
    if ($LASTEXITCODE -ne 0) { Fail-D279 "branch non leggibile" }
    $branch = ([string](@($branchOutput) | Select-Object -First 1)).Trim()
    if ($branch -ne "development") { Fail-D279 "qualificazione ammessa solo su development" }
    $critical = $script:Critical
    $criticalStatus = @(& git -C $root status --porcelain -- @critical)
    if ($LASTEXITCODE -ne 0 -or $criticalStatus.Count -ne 0) {
        Fail-D279 "live-critical set sporco o non tracciato"
    }
    $python = Get-D279Python
    if ($null -eq $python) { Fail-D279 "Python non disponibile" }
    $tshark = Get-D279Tshark
    if ($null -eq $tshark) { Fail-D279 "TShark non disponibile" }
    $selector = Get-D279UsbPcapSelector $tshark

    $stderrProbe = Invoke-D279NativeCaptured $python @(
        "-c", "import sys; sys.stderr.write('D279_10_STDERR_PROBE\n')")
    if ($stderrProbe.ExitCode -ne 0 -or
        (($stderrProbe.Output -join "`n") -notmatch "D279_10_STDERR_PROBE")) {
        Fail-D279 "regressione PowerShell 5.1 stderr/exit-zero fallita"
    }
    $nonzeroProbe = Invoke-D279NativeCaptured $python @(
        "-c", "import sys; sys.exit(7)")
    if ($nonzeroProbe.ExitCode -ne 7) {
        Fail-D279 "regressione PowerShell 5.1 exit-nonzero fallita"
    }

    Push-Location $root
    try {
        $testResult = Invoke-D279NativeCaptured $python @(
            "-m", "unittest", "-q",
            "analysis.D279.test_d279_10_third_acquisition_kit")
    } finally { Pop-Location }
    if ($testResult.ExitCode -ne 0) {
        Fail-D279 ("test Python falliti: " + ($testResult.Output -join " "))
    }
    [ordered]@{
        schema = "D279_10_WINDOWS_NATIVE_QUALIFICATION_V3"
        result = "PASS"
        powershell = $PSVersionTable.PSVersion.ToString()
        repository_root_resolved = $true
        git_branch = $branch
        git_full_head = $head
        live_critical_set_clean = $true
        goodix_present_in_guest = $false
        tshark_present = $true
        usbpcap_selector = $selector
        synthetic_tests = "PASS"
        powershell_native_stderr_exit_zero_regression = "PASS"
        powershell_native_nonzero_exit_code_regression = "PASS"
        authority_template_closed = $true
        global_marker_created = $false
        capture_started = $false
        hardware_action_count = 0
        automatic_retry_count = 0
    } | ConvertTo-Json -Depth 4
}

$selected = @(@($SelfTestOnly, $NativeQualificationOnly,
    $AutorizzoEnrollmentOemCompletoD27910) | Where-Object { $_ })
if ($selected.Count -ne 1) { Fail-D279 "selezionare esattamente una modalita" }
if ($SelfTestOnly) { Invoke-D279SelfTest; exit 0 }
if ($NativeQualificationOnly) { Invoke-D279NativeQualification; exit 0 }

# Live path. The separately supplied authority remains per-attempt and one-shot.
$authority = Read-D279Authority $AuthorityPath
if ($authority.baseline_approved -ne $true) { Fail-D279 "baseline non approvata" }
if ($authority.approved_for_passive_capture -ne $true) { Fail-D279 "capture passiva non approvata" }
if ($authority.full_oem_enrollment_authorized -ne $true) { Fail-D279 "enrollment OEM completo non autorizzato" }
if ($authority.host_vm_enrollment_mutation_accepted -ne $true) {
    Fail-D279 "mutazione enrollment nella VM non accettata"
}
if ($authority.possible_sensor_side_template_persistence_accepted -ne $true) {
    Fail-D279 "rischio non escluso di persistenza template sensor-side non accettato"
}
if ($authority.snapshot_prerun_confirmed -ne $true) {
    Fail-D279 "snapshot VM pre-run con repository e kit qualificato non confermato"
}
if ($authority.live_authorized -ne $true) { Fail-D279 "live non autorizzato" }
$approvedSha = [string]$authority.approved_full_commit_sha
$attemptId = [string]$authority.authorized_attempt_id
if ($approvedSha -notmatch '^[0-9a-f]{40}$') { Fail-D279 "SHA completo approvato non valido" }
if ($attemptId -notmatch '^D27910_[A-Za-z0-9_-]{8,64}$') { Fail-D279 "attempt_id non valido" }

$root = Get-D279RepositoryRoot
$headOutput = & git -C $root rev-parse HEAD 2>&1
if ($LASTEXITCODE -ne 0) { Fail-D279 "HEAD non leggibile" }
$head = ([string](@($headOutput) | Select-Object -First 1)).Trim()
if ($head -ne $approvedSha) { Fail-D279 "HEAD diverso dalla baseline approvata" }
$branchOutput = & git -C $root branch --show-current 2>&1
if ($LASTEXITCODE -ne 0) { Fail-D279 "branch non leggibile" }
$branch = ([string](@($branchOutput) | Select-Object -First 1)).Trim()
if ($branch -ne "development") { Fail-D279 "branch diversa da development" }
$critical = $script:Critical
& git -C $root diff --quiet $approvedSha -- @critical
if ($LASTEXITCODE -ne 0) { Fail-D279 "live-critical set diverso dalla baseline" }
$criticalStatus = @(& git -C $root status --porcelain -- @critical)
if ($LASTEXITCODE -ne 0 -or $criticalStatus.Count -ne 0) { Fail-D279 "live-critical set sporco" }

$python = Get-D279Python
if ($null -eq $python) { Fail-D279 "Python non disponibile" }
$tshark = Get-D279Tshark
if ($null -eq $tshark) { Fail-D279 "TShark non disponibile" }
$usbPcap = Get-D279UsbPcapSelector $tshark
Assert-D279GoodixAbsentSameRun

$captureRoot = Join-Path $root "captures\D279_10"
if (-not (Test-D279PrivateRoot $captureRoot)) { Fail-D279 "radice capture non privata" }
$script:RunRoot = Join-Path $captureRoot $attemptId
if (Test-Path -LiteralPath $script:RunRoot) {
    Fail-D279 "attempt_id gia usato; scegliere una nuova authority per-attempt"
}
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$attemptLock = Join-Path $script:RunRoot "attempt.lock"
Write-D279JsonOnce $attemptLock ([ordered]@{
    schema = "D279_10_ATTEMPT_LOCK_V2"
    attempt_id = $attemptId
    approved_full_commit_sha = $approvedSha
    created_utc = [DateTimeOffset]::UtcNow.ToString('o')
})
$script:RawRoot = Join-Path $script:RunRoot "raw"
$script:SanitizedRoot = Join-Path $script:RunRoot "sanitized"
New-Item -ItemType Directory -Path $script:RawRoot | Out-Null
New-Item -ItemType Directory -Path $script:SanitizedRoot | Out-Null
$script:AttemptStatus = Join-Path $script:SanitizedRoot "attempt_status.json"
$script:Pcap = Join-Path $script:RawRoot "wire.pcapng"
$journal = Join-Path $script:RawRoot "observer_journal.jsonl"
$stopControl = Join-Path $script:RawRoot "observer_stop_control.json"
$observerResult = Join-Path $script:SanitizedRoot "observer_result.json"
$operatorEvents = Join-Path $script:SanitizedRoot "operator_events.json"
$evidence = Join-Path $script:SanitizedRoot "D279_10_full_enrollment_evidence.json"

$captureStartedUtc = $null
$wizardStartedUtc = $null
$enrollmentCompletedUtc = $null
$captureStoppedUtc = $null
$failure = $null

try {
    Write-Host "D279/10: capture passiva dell'intero primo enrollment OEM."
    Write-Host "Zero sender Goodix e zero retry automatico."
    Write-Host "Il terzo B0 e una milestone e non arresta la capture."
    Write-Host "La VM puo mutare; lo snapshot non ripristina eventuale stato sensor-side."

    $snapshotChoice = Read-D279Menu "Snapshot pre-run" @{
        1 = "Snapshot VM creato con repository e kit gia qualificati"
        0 = "Stop"
    }
    if ($snapshotChoice -ne 1) { Fail-D279 "stop prima della capture" }

    $captureArgs = @("-i", $usbPcap, "-a", "duration:1200", "-q", "-w", ('"{0}"' -f $script:Pcap))
    $script:CaptureProcess = Start-Process -FilePath $tshark -ArgumentList $captureArgs -PassThru -WindowStyle Hidden
    $script:CaptureStarted = $true
    $captureStartedUtc = [DateTimeOffset]::UtcNow.ToString('o')
    Start-Sleep -Milliseconds 800
    if ($script:CaptureProcess.HasExited) { Fail-D279 "capture arrestata all'avvio" }

    $observerPath = Join-Path $PSScriptRoot "d279_10_observer.py"
    $observerArgs = @(
        ('"{0}"' -f $observerPath), "--pcap", ('"{0}"' -f $script:Pcap),
        "--journal-output", ('"{0}"' -f $journal),
        "--stop-control", ('"{0}"' -f $stopControl),
        "--result-output", ('"{0}"' -f $observerResult),
        "--deadline-seconds", "1200", "--poll-milliseconds", "100"
    )
    $script:ObserverProcess = Start-Process -FilePath $python -ArgumentList $observerArgs -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 200
    if ($script:ObserverProcess.HasExited) { Fail-D279 "observer arrestato all'avvio" }

    $attach = Read-D279Menu "Collegamento target" @{
        1 = "Il solo sensore target e collegato alla VM"
        0 = "Stop"
    }
    if ($attach -ne 1) { Fail-D279 "stop prima dell'attach" }
    $script:TargetAttached = $true
    Start-Sleep -Milliseconds 700
    $target = [regex]::Escape($script:ExpectedTarget)
    $devices = @(Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { $_.InstanceId -match $target })
    if ($devices.Count -ne 1) { Fail-D279 "target assente o ambiguo dopo attach" }
    Assert-D279LiveProcesses

    $setup = Read-D279Menu "Avvio wizard Windows Hello" @{
        1 = "Wizard pronto per il primo contatto"
        2 = "UI richiede autenticazione con PIN esistente"
        3 = "Prerequisito, creazione PIN o stato inatteso"
        0 = "Stop"
    }
    if ($setup -eq 2) {
        Write-Host "Inserisci il PIN esistente soltanto nella UI Windows."
        $setup = Read-D279Menu "Dopo autenticazione PIN" @{
            1 = "Wizard pronto per il primo contatto"
            3 = "Prerequisito, modifica credenziale o stato inatteso"
            0 = "Stop"
        }
    }
    if ($setup -ne 1) { Fail-D279 "wizard non pronto senza mutazioni credenziali" }
    $script:WizardStarted = $true
    $wizardStartedUtc = [DateTimeOffset]::UtcNow.ToString('o')

    while (-not $script:EnrollmentCompleted) {
        Assert-D279LiveProcesses
        $script:ContactCount += 1
        Write-Host ("Esegui il contatto numero {0} richiesto dalla UI e solleva il dito." -f $script:ContactCount)
        $state = Read-D279Menu "Stato UI dopo il contatto" @{
            1 = "La UI richiede un altro contatto"
            2 = "La UI conferma realmente l'impronta registrata"
            3 = "Errore, prerequisito o stato inatteso"
            0 = "Stop"
        }
        if ($state -eq 1) { continue }
        if ($state -eq 2) {
            $script:EnrollmentCompleted = $true
            $enrollmentCompletedUtc = [DateTimeOffset]::UtcNow.ToString('o')
            break
        }
        Fail-D279 "enrollment non concluso con conferma reale"
    }

    Write-Host "Conferma UI registrata. Capture tail terminale: 5 secondi."
    Start-Sleep -Seconds 5
    Assert-D279LiveProcesses
    Write-D279JsonOnce $stopControl ([ordered]@{
        schema = "D279_10_OBSERVER_STOP_CONTROL_V2"
        attempt_id = $attemptId
        reason = "WINDOWS_UI_CONFIRMED_AND_TERMINAL_TAIL_ELAPSED"
        created_utc = [DateTimeOffset]::UtcNow.ToString('o')
    })
    if (-not $script:ObserverProcess.WaitForExit(10000)) {
        Fail-D279 "observer non arrestato sul control file"
    }
    if ($script:ObserverProcess.ExitCode -ne 0) { Fail-D279 "observer finalizzato in failure" }
    if (-not (Stop-D279Capture)) { Fail-D279 "capture non arrestata" }
    $captureStoppedUtc = [DateTimeOffset]::UtcNow.ToString('o')

    Write-D279JsonOnce $operatorEvents ([ordered]@{
        schema = "D279_10_OPERATOR_EVENTS_V2"
        attempt_id = $attemptId
        capture_started_utc = $captureStartedUtc
        wizard_started_utc = $wizardStartedUtc
        enrollment_completed_utc = $enrollmentCompletedUtc
        capture_stopped_utc = $captureStoppedUtc
        contact_count = $script:ContactCount
        enrollment_completed = $true
        terminal_tail_seconds = 5
        automatic_retry_count = 0
    })
    if (-not (Test-Path -LiteralPath $script:Pcap -PathType Leaf) -or
        (Get-Item $script:Pcap).Length -le 0) { Fail-D279 "capture mancante o vuota" }
    $rawHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $script:Pcap).Hash.ToLowerInvariant()
    $post = Join-Path $PSScriptRoot "d279_10_third_cycle.py"
    $postOutput = @(& $python $post --pcap $script:Pcap --expected-sha256 $rawHash `
        --operator-events $operatorEvents --attempt-id $attemptId --output $evidence 2>&1)
    if ($LASTEXITCODE -ne 0) { Fail-D279 ("finalizer fallito: " + ($postOutput -join " ")) }
    $result = Get-Content -LiteralPath $evidence -Raw | ConvertFrom-Json
    if ($result.boundary_status -ne "OBSERVED_COMPLETE_UI_CONFIRMED") {
        Fail-D279 "evidenza finale non chiude l'enrollment UI"
    }
    Write-D279AttemptStatus "PASS" $null
} catch {
    $failure = $_.Exception.Message
    Stop-D279Observer
    Stop-D279Capture | Out-Null
    Write-D279AttemptStatus "FAIL" $failure
} finally {
    Stop-D279Observer
    Stop-D279Capture | Out-Null
}

Write-Host ("ESPORTA PRIMA DI QUALSIASI RESTORE RAW: " + $script:RawRoot)
Write-Host ("ESPORTA PRIMA DI QUALSIASI RESTORE SANITIZED: " + $script:SanitizedRoot)
if ($null -ne $failure) { throw $failure }

[ordered]@{
    schema = "D279_10_LIVE_RUN_SUMMARY_V2"
    result = "PASS"
    attempt_id = $attemptId
    capture_started = $script:CaptureStarted
    capture_stopped = $script:CaptureStopped
    completion_authority = "WINDOWS_UI_OPERATOR_NUMERIC_CONFIRMATION"
    operator_contact_count = $script:ContactCount
    third_b0_is_milestone_only = $true
    terminal_tail_seconds = 5
    automatic_retry_count = 0
    goodix_manual_command_count = 0
    rerun_classification = Get-D279RestoreClassification
    export_before_snapshot_restore_raw = $script:RawRoot
    export_before_snapshot_restore_sanitized = $script:SanitizedRoot
    sanitized_evidence = $evidence
} | ConvertTo-Json -Depth 4
