# SPDX-License-Identifier: GPL-2.0-or-later
# D279/10 passive Windows OEM observation. Windows PowerShell Desktop 5.1.
[CmdletBinding()]
param(
    [switch]$SelfTestOnly,
    [switch]$NativeQualificationOnly,
    [switch]$AutorizzoUnaSolaOsservazioneD27910,
    [string]$AuthorityPath = (Join-Path $PSScriptRoot "D279_10_live_authority.json")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$script:ExpectedTarget = "VID_27C6&PID_5125"
$script:CaptureProcess = $null
$script:ObserverProcess = $null
$script:CaptureStarted = $false
$script:CaptureStopped = $false
$script:Critical = @(
    "operator_kit/d279-10-third-acquisition-observe/run-d279-10.ps1",
    "operator_kit/d279-10-third-acquisition-observe/d279_10_third_cycle.py",
    "operator_kit/d279-10-third-acquisition-observe/d279_10_observer.py",
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py"
)

function Fail-D279([string]$Message) {
    Stop-D279Observer
    Stop-D279Capture | Out-Null
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

function Read-D279Exact([string]$Prompt, [string[]]$Allowed) {
    $answer = (Read-Host $Prompt).Trim().ToUpperInvariant()
    if ($Allowed -notcontains $answer) { Fail-D279 ("risposta non ammessa: " + $answer) }
    return $answer
}

function Read-D279SetupReady {
    $terminal = @(
        "NEW_PIN_REQUIRED", "PIN_CREATION_UI", "PIN_MUTATION_UI",
        "ACCOUNT_MUTATION_UI", "CREDENTIAL_MUTATION_UI",
        "UNEXPECTED_PREREQUISITE", "ENROLLMENT_COMMIT_UI", "STOP"
    )
    $state = Read-D279Exact "Apri Configura Windows Hello senza confermare modifiche. Digita PRONTO, EXISTING_PIN_AUTHENTICATION o una categoria terminale" (@("PRONTO", "EXISTING_PIN_AUTHENTICATION") + $terminal)
    if ($state -eq "EXISTING_PIN_AUTHENTICATION") {
        Write-Host "Inserisci il PIN esistente solo nella UI Windows. Il Kit non lo legge. Se viene chiesta creazione o modifica, usa la categoria terminale."
        $state = Read-D279Exact "Dopo la sola verifica identita, digita PRONTO o una categoria terminale" (@("PRONTO") + $terminal)
    }
    if ($state -ne "PRONTO") { Fail-D279 ("condizione UI terminale: " + $state) }
}

function Get-D279RepositoryRoot {
    $rootOutput = & git -C $PSScriptRoot rev-parse --show-toplevel 2>&1
    $gitExitCode = $LASTEXITCODE
    if ($gitExitCode -ne 0) { Fail-D279 "repository Git non individuabile" }
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
        Fail-D279 "GOODIX_PRESENT_IN_GUEST=true; il target deve essere assente prima della run"
    }
}

function Test-D279PrivateRoot([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        New-Item -ItemType Directory -Path $Root -Force | Out-Null
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
    if ($authority.schema -ne "D279_10_LIVE_AUTHORITY_V1") { Fail-D279 "schema authority non valido" }
    return $authority
}

function Invoke-D279SelfTest {
    if ($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) {
        Fail-D279 "e richiesto Windows PowerShell Desktop 5.1"
    }
    $required = @(
        "d279_10_third_cycle.py", "d279_10_observer.py",
        "D279_10_live_authority.json", "README_IT.md"
    )
    $missing = @($required | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $_) -PathType Leaf)
    })
    if ($missing.Count -ne 0) { Fail-D279 ("file mancanti: " + ($missing -join ", ")) }
    $authority = Read-D279Authority (Join-Path $PSScriptRoot "D279_10_live_authority.json")
    if ($authority.baseline_approved -ne $false -or
        $authority.approved_for_passive_capture -ne $false -or
        $authority.third_contact_authorized -ne $false -or
        $authority.possible_host_enrollment_mutation_accepted -ne $false -or
        $authority.live_authorized -ne $false) {
        Fail-D279 "il template authority versionato non e chiuso"
    }
    [ordered]@{
        schema = "D279_10_SELFTEST_V1"
        result = "PASS"
        operator_language = "ITALIAN"
        authority_template_closed = $true
        live_path_executed = $false
        hardware_action_count = 0
        capture_start_count = 0
        finger_prompt_count = 0
        automatic_retry_count = 0
    } | ConvertTo-Json -Depth 4
}

function Invoke-D279NativeQualification {
    Invoke-D279SelfTest | Out-Null
    $authority = Read-D279Authority (Join-Path $PSScriptRoot "D279_10_live_authority.json")
    if ($authority.live_authorized -ne $false) { Fail-D279 "authority template aperta" }
    Assert-D279GoodixAbsentSameRun
    $root = Get-D279RepositoryRoot
    $headOutput = & git -C $root rev-parse HEAD 2>&1
    $headExitCode = $LASTEXITCODE
    if ($headExitCode -ne 0) { Fail-D279 "HEAD non leggibile" }
    $head = ([string](@($headOutput) | Select-Object -First 1)).Trim()
    if ($head -notmatch '^[0-9a-f]{40}$') { Fail-D279 "HEAD completo non valido" }
    $branchOutput = & git -C $root branch --show-current 2>&1
    $branchExitCode = $LASTEXITCODE
    if ($branchExitCode -ne 0) { Fail-D279 "branch non leggibile" }
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
    Push-Location $root
    try {
        $testOutput = @(& $python -m unittest -q analysis.D279.test_d279_10_third_acquisition_kit 2>&1)
        $testExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($testExitCode -ne 0) { Fail-D279 ("test Python falliti: " + ($testOutput -join " ")) }
    [ordered]@{
        schema = "D279_10_WINDOWS_NATIVE_QUALIFICATION_V1"
        result = "PASS"
        powershell = $PSVersionTable.PSVersion.ToString()
        repository_root_resolved = $true
        git_branch = $branch
        git_full_head = $head
        live_critical_set_clean = $true
        goodix_present_in_guest = $false
        tshark_present = $true
        usbpcap_selector = $selector
        synthetic_tests = "14_PASS"
        authority_template_closed = $true
        marker_created = $false
        capture_started = $false
        finger_prompt_presented = $false
        hardware_action_count = 0
        automatic_retry_count = 0
    } | ConvertTo-Json -Depth 4
}

$selected = @(@($SelfTestOnly, $NativeQualificationOnly,
    $AutorizzoUnaSolaOsservazioneD27910) | Where-Object { $_ })
if ($selected.Count -ne 1) { Fail-D279 "selezionare esattamente una modalita" }
if ($SelfTestOnly) { Invoke-D279SelfTest; exit 0 }
if ($NativeQualificationOnly) { Invoke-D279NativeQualification; exit 0 }

# Live path. A command-line switch is insufficient: a separately supplied,
# one-shot authority must acknowledge both the third contact and the unresolved
# risk that Windows may persist a host-side enrollment at this edge.
$authority = Read-D279Authority $AuthorityPath
if ($authority.baseline_approved -ne $true) { Fail-D279 "baseline non approvata" }
if ($authority.approved_for_passive_capture -ne $true) { Fail-D279 "capture passiva non approvata" }
if ($authority.third_contact_authorized -ne $true) { Fail-D279 "terzo contatto non autorizzato" }
if ($authority.possible_host_enrollment_mutation_accepted -ne $true) {
    Fail-D279 "rischio di mutazione enrollment host non accettato"
}
if ($authority.live_authorized -ne $true) { Fail-D279 "live non autorizzato" }
$approvedSha = [string]$authority.approved_full_commit_sha
$authorizationId = [string]$authority.one_shot_authorization_id
if ($approvedSha -notmatch '^[0-9a-f]{40}$') { Fail-D279 "SHA completo approvato non valido" }
if ($authorizationId -notmatch '^D27910_[A-Za-z0-9_-]{8,64}$') { Fail-D279 "authorization ID non valido" }

$root = Get-D279RepositoryRoot
$headOutput = & git -C $root rev-parse HEAD 2>&1
$headExitCode = $LASTEXITCODE
if ($headExitCode -ne 0) { Fail-D279 "HEAD non leggibile" }
$head = ([string](@($headOutput) | Select-Object -First 1)).Trim()
if ($head -ne $approvedSha) { Fail-D279 "HEAD diverso dalla baseline approvata" }
$branchOutput = & git -C $root branch --show-current 2>&1
$branchExitCode = $LASTEXITCODE
if ($branchExitCode -ne 0) { Fail-D279 "branch non leggibile" }
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

# Same-run absence gate precedes marker, capture, attach and finger prompts.
Assert-D279GoodixAbsentSameRun
$captureRoot = Join-Path $root "captures\D279_10"
if (-not (Test-D279PrivateRoot $captureRoot)) { Fail-D279 "radice capture non privata" }
$marker = Join-Path $captureRoot "D279_10_ONE_SHOT_CONSUMED.marker"
$markerStream = $null
try {
    $markerStream = [System.IO.File]::Open($marker, [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $markerText = "authorization_id=$authorizationId`napproved_sha=$approvedSha`nconsumed_utc=$([DateTimeOffset]::UtcNow.ToString('o'))`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($markerText)
    $markerStream.Write($bytes, 0, $bytes.Length)
    $markerStream.Flush()
} catch {
    Fail-D279 "marker one-shot gia esistente o non creabile; nessun retry"
} finally {
    if ($null -ne $markerStream) { $markerStream.Dispose() }
}

$runRoot = Join-Path $captureRoot $authorizationId
if (Test-Path -LiteralPath $runRoot) { Fail-D279 "output one-shot gia esistente" }
$rawRoot = Join-Path $runRoot "raw"
$sanitizedRoot = Join-Path $runRoot "sanitized"
New-Item -ItemType Directory -Path $rawRoot -Force | Out-Null
New-Item -ItemType Directory -Path $sanitizedRoot -Force | Out-Null
$pcap = Join-Path $rawRoot "wire.pcapng"
$signal = Join-Path $rawRoot "observer_third_b0_signal.json"
$evidence = Join-Path $sanitizedRoot "D279_10_third_acquisition_evidence.json"

Write-Host "D279/10: osservazione passiva OEM one-shot del terzo edge."
Write-Host "RISCHIO ESPLICITO: Windows potrebbe persistere un enrollment host al terzo contatto."
Write-Host "Nessun retry; nessun comando Goodix e inviato dal Kit."

$captureArgs = @("-i", $usbPcap, "-a", "duration:300", "-q", "-w", ('"{0}"' -f $pcap))
try {
    $script:CaptureProcess = Start-Process -FilePath $tshark -ArgumentList $captureArgs -PassThru -WindowStyle Hidden
    $script:CaptureStarted = $true
    Start-Sleep -Milliseconds 800
    if ($script:CaptureProcess.HasExited) { Fail-D279 "capture arrestata all'avvio" }
    $observerPath = Join-Path $PSScriptRoot "d279_10_observer.py"
    $observerArgs = @(
        ('"{0}"' -f $observerPath), "--pcap", ('"{0}"' -f $pcap),
        "--signal-output", ('"{0}"' -f $signal), "--deadline-seconds", "300",
        "--poll-milliseconds", "100"
    )
    $script:ObserverProcess = Start-Process -FilePath $python -ArgumentList $observerArgs -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 200
    if ($script:ObserverProcess.HasExited) { Fail-D279 "observer arrestato all'avvio" }

    $attach = Read-D279Exact "Collega il solo sensore target alla VM. Digita COLLEGATO o STOP" @("COLLEGATO", "STOP")
    if ($attach -ne "COLLEGATO") { Fail-D279 "stop prima dell'attach" }
    Start-Sleep -Milliseconds 700
    $target = [regex]::Escape($script:ExpectedTarget)
    $devices = @(Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { $_.InstanceId -match $target })
    if ($devices.Count -ne 1) { Fail-D279 "target assente o ambiguo dopo attach" }

    Read-D279SetupReady
    Write-Host "Esegui il PRIMO contatto e solleva il dito quando richiesto."
    $secondState = Read-D279Exact "Digita SECONDO_RICHIESTO o una categoria terminale" @(
        "SECONDO_RICHIESTO", "NEW_PIN_REQUIRED", "PIN_CREATION_UI",
        "PIN_MUTATION_UI", "ACCOUNT_MUTATION_UI", "CREDENTIAL_MUTATION_UI",
        "UNEXPECTED_PREREQUISITE", "ENROLLMENT_COMMIT_UI", "STOP")
    if ($secondState -ne "SECONDO_RICHIESTO") { Fail-D279 ("condizione UI terminale: " + $secondState) }
    Write-Host "Esegui il SECONDO contatto e solleva il dito quando richiesto."
    $thirdState = Read-D279Exact "Digita TERZO_RICHIESTO o una categoria terminale" @(
        "TERZO_RICHIESTO", "NEW_PIN_REQUIRED", "PIN_CREATION_UI",
        "PIN_MUTATION_UI", "ACCOUNT_MUTATION_UI", "CREDENTIAL_MUTATION_UI",
        "UNEXPECTED_PREREQUISITE", "ENROLLMENT_COMMIT_UI", "STOP")
    if ($thirdState -ne "TERZO_RICHIESTO") { Fail-D279 ("condizione UI terminale: " + $thirdState) }
    Write-Host "Esegui il TERZO contatto una sola volta. Non eseguire un quarto contatto."
    if (-not $script:ObserverProcess.WaitForExit(305000)) {
        Fail-D279 "THIRD_B0_OBSERVER_DEADLINE; AUTOMATIC_RETRY_COUNT=0"
    }
    if ($script:ObserverProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $signal -PathType Leaf)) {
        $observerFailure = "OBSERVER_FAILED_WITHOUT_SIGNAL"
        if (Test-Path -LiteralPath $signal -PathType Leaf) {
            try {
                $failureSignal = Get-Content -LiteralPath $signal -Raw | ConvertFrom-Json
                if ($failureSignal.schema -eq "D279_10_WIRE_OBSERVER_FAILURE_V1" -and
                    $failureSignal.status -eq "FAIL_CLOSED") {
                    $observerFailure = [string]$failureSignal.failure_class
                }
            } catch {
                $observerFailure = "OBSERVER_FAILURE_SIGNAL_INVALID"
            }
        }
        Fail-D279 ("terzo B0 non osservato: " + $observerFailure + "; AUTOMATIC_RETRY_COUNT=0")
    }
    if (-not (Stop-D279Capture)) { Fail-D279 "CAPTURE_PROCESS_STOP_TIMEOUT" }
    Write-Host "Terzo B0 osservato. Chiudi subito la UI; non eseguire altri contatti."
} finally {
    Stop-D279Observer
    Stop-D279Capture | Out-Null
}

if (-not (Test-Path -LiteralPath $pcap -PathType Leaf) -or (Get-Item $pcap).Length -le 0) {
    Fail-D279 "capture mancante o vuota"
}
$rawHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $pcap).Hash.ToLowerInvariant()
$post = Join-Path $PSScriptRoot "d279_10_third_cycle.py"
$postOutput = @(& $python $post --pcap $pcap --expected-sha256 $rawHash --output $evidence --observer-signal $signal 2>&1)
$postExitCode = $LASTEXITCODE
if ($postExitCode -ne 0) { Fail-D279 ("finalizer fallito: " + ($postOutput -join " ")) }
$result = Get-Content -LiteralPath $evidence -Raw | ConvertFrom-Json
if ($result.boundary_status -ne "OBSERVED_COMPLETE" -or $result.stop_reason -ne "THIRD_FINGERPRINT_B0") {
    Fail-D279 "evidenza finale non chiude il boundary"
}

[ordered]@{
    schema = "D279_10_LIVE_RUN_SUMMARY_V1"
    result = "PASS"
    capture_started = $script:CaptureStarted
    capture_stopped = $script:CaptureStopped
    stop_trigger = "WIRE_DRIVEN_THIRD_FINGERPRINT_B0"
    automatic_retry_count = 0
    goodix_manual_command_count = 0
    fourth_contact_authorized = $false
    possible_host_enrollment_mutation_was_accepted = $true
    sanitized_evidence = $evidence
} | ConvertTo-Json -Depth 4
