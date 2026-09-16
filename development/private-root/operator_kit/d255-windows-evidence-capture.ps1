# SPDX-License-Identifier: GPL-2.0-or-later
# D255 prepares one operator-authorized Windows OEM evidence capture.
[CmdletBinding()]
param(
    [switch]$SelfTestOnly,
    [switch]$PreflightOnly,
    [switch]$PreAuthorizationSimulationOnly,
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$TsharkPath = "",
    [string[]]$CaptureInterface = @(),
    [string]$Authorization = "",
    [ValidateRange(90, 1800)][int]$CaptureDurationSeconds = 300,
    [string[]]$OemLogPath = @(),
    [string[]]$CacheRoot = @(),
    [string]$VmGuestReadyConfirmation = "",
    [string]$AccountPrerequisiteConfirmation = "",
    [string]$WindowsHelloPinState = "",
    [string]$FingerprintSetupPinRequirement = "",
    [ValidateSet("ABSENT", "PRESENT")][string]$SimulationOemLogState = "ABSENT"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ExpectedAuthorization = "--i-authorize-one-d255-windows-oem-evidence-capture"
$ExpectedVmGuestReadyConfirmation = "VM_WINDOWS_RUNNING_GOODIX_ABSENT_FROM_GUEST"
$ExpectedAccountPrerequisiteConfirmation = "SIGNIN_OPTIONS_CHECKED_NO_NEW_PIN_CHANGE"
$AllowedWindowsHelloPinStates = @(
    "ALREADY_CONFIGURED",
    "NOT_CONFIGURED",
    "UNKNOWN",
    "NOT_REQUIRED_BY_CURRENT_ACCOUNT_POLICY"
)
$AllowedFingerprintSetupPinRequirements = @("REQUIRED", "NOT_REQUIRED", "UNKNOWN")
$TargetVidPidPattern = "VID_27C6&PID_5125"
$script:AuthorizationConsumed = $false
$script:RunDirectory = $null
$script:MarkerPath = $null
$script:CaptureProcess = $null
$script:CaptureProcessHandle = $null
$script:CapturePath = $null
$script:CaptureArgumentsRedacted = $null
$script:CaptureStdoutPath = $null
$script:CaptureStderrPath = $null

function Fail-D255 {
    param([Parameter(Mandatory = $true)][string]$Message)
    if (-not $script:AuthorizationConsumed) {
        Write-Output "D255_AUTHORIZATION_CONSUMED=false"
    }
    throw "D255_FAIL_CLOSED: $Message"
}

function Get-UtcStamp {
    return [DateTime]::UtcNow.ToString("o")
}

function Get-D255Sha256HexForString {
    param([Parameter(Mandatory = $true)][string]$Value)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        $digest = $sha256.ComputeHash($bytes)
        return [BitConverter]::ToString($digest).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }
}

function Get-D255RelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$ChildPath
    )
    $baseFull = [System.IO.Path]::GetFullPath($BasePath)
    $childFull = [System.IO.Path]::GetFullPath($ChildPath)
    $separator = [string][System.IO.Path]::DirectorySeparatorChar
    $basePrefix = $baseFull
    if (-not $basePrefix.EndsWith($separator, [StringComparison]::Ordinal)) {
        $basePrefix += $separator
    }
    if (-not $childFull.StartsWith($basePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw [InvalidOperationException]::new("child path is outside RunDirectory")
    }
    $relative = $childFull.Substring($basePrefix.Length)
    if ([string]::IsNullOrWhiteSpace($relative)) {
        throw [InvalidOperationException]::new("child path does not name an item below RunDirectory")
    }
    $canonical = $relative.Replace([System.IO.Path]::DirectorySeparatorChar, "/")
    if ([System.IO.Path]::AltDirectorySeparatorChar -ne [System.IO.Path]::DirectorySeparatorChar) {
        $canonical = $canonical.Replace([System.IO.Path]::AltDirectorySeparatorChar, "/")
    }
    if ($canonical.Split("/") -contains "..") {
        throw [InvalidOperationException]::new("relative path contains traversal")
    }
    return $canonical
}

function Test-D255PathAvailable {
    param([Parameter(Mandatory = $true)][string]$Path)
    return -not (Test-Path -LiteralPath $Path)
}

function Get-D255AvailabilityStatus {
    param([Parameter(Mandatory = $true)][int]$SourceCount)
    if ($SourceCount -gt 0) { return "PRESENT" }
    return "ABSENT"
}

function Write-D255JsonArray {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Rows,
        [Parameter(Mandatory = $true)][string]$Path
    )
    if ($Rows.Count -eq 0) {
        Set-Content -LiteralPath $Path -Encoding UTF8 -Value "[]"
        return
    }
    ConvertTo-Json -InputObject $Rows -Depth 5 |
        Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-D255RuntimeInfo {
    $version = $PSVersionTable.PSVersion
    $clrVersion = "not-reported"
    if ($PSVersionTable.ContainsKey("CLRVersion")) {
        $clrVersion = [string]$PSVersionTable["CLRVersion"]
    }
    $supported = (($version.Major -eq 5 -and $version.Minor -ge 1) -or $version.Major -ge 7)
    if (-not $supported) {
        Fail-D255 "PowerShell runtime must be Windows PowerShell 5.1 or PowerShell 7+"
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        Fail-D255 "D255 Windows kit must run on Windows"
    }
    return [ordered]@{
        powershell_edition = [string]$PSVersionTable.PSEdition
        powershell_version = $version.ToString()
        clr_version = $clrVersion
        platform = [Environment]::OSVersion.VersionString
        compatibility = "WINDOWS_POWERSHELL_5_1_OR_POWERSHELL_7_PLUS"
    }
}

function New-D255ClockAnchor {
    param([Parameter(Mandatory = $true)][string]$Phase)
    $utc = [DateTimeOffset]::UtcNow
    $local = $utc.ToLocalTime()
    return [ordered]@{
        schema = "D255_WINDOWS_RUN_CLOCK_V1"
        phase = $Phase
        utc_iso = $utc.ToString("o")
        local_iso_with_offset = $local.ToString("o")
        utc_offset_minutes = [int]$local.Offset.TotalMinutes
        windows_timezone_id = [TimeZoneInfo]::Local.Id
        year = $local.Year
        month = $local.Month
        day = $local.Day
        tick_source = "DateTimeOffset.UtcNow"
        environment_tick_count = [Environment]::TickCount
    }
}

function Test-D255PreAttachReadinessState {
    param(
        [Parameter(Mandatory = $true)][bool]$ProcessAlive,
        [Parameter(Mandatory = $true)][int]$GuestTargetCount
    )
    return ($ProcessAlive -and $GuestTargetCount -eq 0)
}

function Test-D255FinalCaptureValidationState {
    param(
        [Parameter(Mandatory = $true)][bool]$ProcessExited,
        [Parameter(Mandatory = $true)][AllowNull()][object]$TsharkExitCode,
        [Parameter(Mandatory = $true)][bool]$PcapngExists,
        [Parameter(Mandatory = $true)][long]$PcapngLength,
        [Parameter(Mandatory = $true)][int]$ReadableFrameCount
    )
    if (-not $ProcessExited) { return "FAIL_CLOSED" }
    $captureValid = ($PcapngExists -and $PcapngLength -gt 0 -and
        $ReadableFrameCount -ge 1)
    if ($null -eq $TsharkExitCode) {
        if ($captureValid) { return "PASS_WITH_EXIT_CODE_UNAVAILABLE" }
        return "FAIL_CLOSED"
    }
    if ($TsharkExitCode -isnot [int] -and $TsharkExitCode -isnot [long]) {
        return "FAIL_CLOSED"
    }
    if ([long]$TsharkExitCode -ne 0 -or -not $captureValid) {
        return "FAIL_CLOSED"
    }
    return "PASS"
}

function Get-D255CaptureExitCode {
    if ($null -eq $script:CaptureProcess -or -not $script:CaptureProcess.HasExited) {
        return $null
    }
    try {
        $value = $script:CaptureProcess.ExitCode
        if ($null -eq $value) { return $null }
        return [int]$value
    } catch {
        return $null
    }
}

function ConvertTo-D255RedactedDiagnosticText {
    param([AllowEmptyString()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return "UNAVAILABLE" }
    $redacted = $Value
    $redactions = @(
        [pscustomobject]@{ value = $script:RunDirectory; replacement = "<run-directory>" }
        [pscustomobject]@{ value = $script:CapturePath; replacement = "<capture-output>" }
        [pscustomobject]@{ value = $TsharkPath; replacement = "<tshark-executable>" }
    )
    foreach ($item in $redactions) {
        if (-not [string]::IsNullOrWhiteSpace([string]$item.value)) {
            $redacted = $redacted.Replace([string]$item.value, [string]$item.replacement)
        }
    }
    $redacted = ($redacted -replace "[\r\n\t]+", " ").Trim()
    if ($redacted.Length -gt 1024) {
        $redacted = $redacted.Substring($redacted.Length - 1024)
    }
    return $redacted
}

function Get-D255CaptureDiagnosticStream {
    param([AllowEmptyString()][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return "UNAVAILABLE"
    }
    try {
        return ConvertTo-D255RedactedDiagnosticText -Value (Get-Content -LiteralPath $Path -Raw -ErrorAction Stop)
    } catch {
        return "UNREADABLE"
    }
}

function Get-D255CaptureOutputPathState {
    if ([string]::IsNullOrWhiteSpace($script:CapturePath) -or
        -not (Test-Path -LiteralPath $script:CapturePath -PathType Leaf)) {
        return "exists=false,length=UNAVAILABLE"
    }
    try {
        return "exists=true,length=$((Get-Item -LiteralPath $script:CapturePath -ErrorAction Stop).Length)"
    } catch {
        return "exists=true,length=UNREADABLE"
    }
}

function Get-D255CaptureFailureDetail {
    param([Parameter(Mandatory = $true)][string]$Reason)
    $exitCode = "UNAVAILABLE"
    $processState = "NOT_STARTED"
    if ($null -ne $script:CaptureProcess) {
        try { $script:CaptureProcess.Refresh() } catch { }
        if ($script:CaptureProcess.HasExited) {
            $processState = "EXITED"
            $observedExitCode = Get-D255CaptureExitCode
            if ($null -ne $observedExitCode) { $exitCode = [string]$observedExitCode }
        } else {
            $processState = "RUNNING"
        }
    }
    $reasonRedacted = ConvertTo-D255RedactedDiagnosticText -Value $Reason
    $stdout = Get-D255CaptureDiagnosticStream -Path $script:CaptureStdoutPath
    $stderr = Get-D255CaptureDiagnosticStream -Path $script:CaptureStderrPath
    return ($reasonRedacted + "; process_state=$processState; exit_code=$exitCode; " +
        "command_arguments=$script:CaptureArgumentsRedacted; output_path_state=$(Get-D255CaptureOutputPathState); " +
        "stdout=$stdout; stderr=$stderr")
}

function Fail-D255Capture {
    param([Parameter(Mandatory = $true)][string]$Reason)
    Fail-D255 (Get-D255CaptureFailureDetail -Reason $Reason)
}

function Assert-CaptureActive {
    if ($null -eq $script:CaptureProcess -or $script:CaptureProcess.HasExited) {
        Fail-D255Capture "capture duration elapsed or capture process failed before operator phases completed"
    }
}

function Write-OperatorMarker {
    param(
        [Parameter(Mandatory = $true)][string]$Event,
        [string]$Detail = ""
    )
    $safeDetail = $Detail -replace "[\r\n\t]", " "
    Add-Content -LiteralPath $script:MarkerPath -Encoding UTF8 -Value "$(Get-UtcStamp)`t$Event`t$safeDetail"
}

function Read-HelloSetupUiResult {
    $choices = [System.Collections.ObjectModel.Collection[System.Management.Automation.Host.ChoiceDescription]]::new()
    $choices.Add([System.Management.Automation.Host.ChoiceDescription]::new(
        "&Ready waiting for finger", "READY_WAITING_FOR_FINGER"))
    $choices.Add([System.Management.Automation.Host.ChoiceDescription]::new(
        "UI &unavailable", "UI_UNAVAILABLE"))
    $choices.Add([System.Management.Automation.Host.ChoiceDescription]::new(
        "&New PIN required", "NEW_PIN_REQUIRED"))
    $choices.Add([System.Management.Automation.Host.ChoiceDescription]::new(
        "Une&xpected prerequisite", "UNEXPECTED_PREREQUISITE"))
    $selected = $Host.UI.PromptForChoice(
        "D255 post-attach Windows Hello gate",
        "Classify the setup UI exactly. Do not touch the sensor, create/change a PIN, retry, or use another UI path.",
        $choices,
        -1
    )
    return @(
        "READY_WAITING_FOR_FINGER",
        "UI_UNAVAILABLE",
        "NEW_PIN_REQUIRED",
        "UNEXPECTED_PREREQUISITE"
    )[$selected]
}

function Get-TargetDevices {
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D255 "Get-PnpDevice is unavailable"
    }
    return @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object {
        $_.InstanceId -match $TargetVidPidPattern
    })
}

function Assert-SingleGuestTarget {
    $targets = @(Get-TargetDevices)
    if ($targets.Count -ne 1) {
        Fail-D255 "D255_EVIDENCE_VALIDITY=INVALID_VM_USB_TOPOLOGY_CHANGE"
    }
    return $targets[0]
}

function Get-GuestPnpTopology {
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D255 "Get-PnpDevice is unavailable"
    }
    return @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Sort-Object -Property InstanceId |
        ForEach-Object {
            [ordered]@{
                class = [string]$_.Class
                friendly_name = [string]$_.FriendlyName
                instance_id = [string]$_.InstanceId
                status = [string]$_.Status
            }
        })
}

function Write-GuestTopologySnapshot {
    param([Parameter(Mandatory = $true)][string]$Stage)
    $rows = @(Get-GuestPnpTopology)
    [ordered]@{
        schema = "D255_GUEST_PNP_TOPOLOGY_V1"
        stage = $Stage
        timestamp_utc = Get-UtcStamp
        target_vid_pid = "27c6:5125"
        target_present_count = @($rows | Where-Object { $_.instance_id -match $TargetVidPidPattern }).Count
        devices = $rows
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $script:RunDirectory "guest_topology_${Stage}.json") -Encoding UTF8
}

function Resolve-CacheRoots {
    $roots = [System.Collections.Generic.List[string]]::new()
    foreach ($root in $CacheRoot) {
        if ($root) { $roots.Add($root) }
    }
    foreach ($candidate in @(
        (Join-Path $env:ProgramData "Goodix"),
        (Join-Path $env:ProgramData "Goodix Fingerprint"),
        (Join-Path $env:ProgramData "Goodix Fingerprint Driver"),
        (Join-Path $env:SystemRoot "System32\config\systemprofile\AppData\Local\Goodix")
    )) {
        if ($candidate -and -not $roots.Contains($candidate)) { $roots.Add($candidate) }
    }
    return @($roots)
}

function Get-TargetedFiles {
    param([AllowEmptyCollection()][string[]]$Roots = @())
    $files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    foreach ($root in $Roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Extension -notmatch "(?i)^\.log$" -and
                ($_.Length -eq 13520 -or
                 $_.Name -match "(?i)(goodix|base|cache|wbdi|finger|nav|image)")
            } |
            ForEach-Object { $files.Add($_) }
    }
    return @($files | Sort-Object -Property FullName -Unique)
}

function Resolve-OemLogCandidates {
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($path in $OemLogPath) {
        if ($path) { $candidates.Add([System.IO.Path]::GetFullPath($path)) }
    }
    foreach ($root in Resolve-CacheRoots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "(?i)(wbdi|goodix).*\.log$" } |
            ForEach-Object { $candidates.Add($_.FullName) }
    }
    return @($candidates | Sort-Object -Unique)
}

function Write-FileSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Roots,
        [Parameter(Mandatory = $true)][string]$RawDirectory
    )
    $copyDirectory = Join-Path $RawDirectory "cache_$Stage"
    New-Item -ItemType Directory -Path $copyDirectory -ErrorAction Stop | Out-Null
    $rows = [System.Collections.Generic.List[object]]::new()
    foreach ($file in Get-TargetedFiles -Roots $Roots) {
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $copyName = "$hash.bin"
        $copyPath = Join-Path $copyDirectory $copyName
        if (-not (Test-Path -LiteralPath $copyPath)) {
            Copy-Item -LiteralPath $file.FullName -Destination $copyPath -ErrorAction Stop
        }
        $aclSummary = "unavailable"
        try {
            $acl = Get-Acl -LiteralPath $file.FullName -ErrorAction Stop
            $aclSummary = "owner=$($acl.Owner);protected=$($acl.AreAccessRulesProtected)"
        } catch { }
        $rows.Add([ordered]@{
            stage = $Stage
            full_path = $file.FullName
            size = $file.Length
            sha256 = $hash
            creation_time_utc = $file.CreationTimeUtc.ToString("o")
            modification_time_utc = $file.LastWriteTimeUtc.ToString("o")
            acl_summary = $aclSummary
            raw_copy = "raw/cache_$Stage/$copyName"
        })
    }
    $snapshotPath = Join-Path $script:RunDirectory "cache_${Stage}_metadata.json"
    Write-D255JsonArray -Rows @($rows) -Path $snapshotPath
    return $snapshotPath
}

function Write-OemLogSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Candidates,
        [Parameter(Mandatory = $true)][string]$RawDirectory
    )
    $logDirectory = Join-Path $RawDirectory "oem_logs_$Stage"
    New-Item -ItemType Directory -Path $logDirectory -ErrorAction Stop | Out-Null
    $rows = [System.Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $Candidates.Count; $index += 1) {
        $path = $Candidates[$index]
        $exists = Test-Path -LiteralPath $path -PathType Leaf
        $row = [ordered]@{
            source_index = $index
            stage = $Stage
            full_path = $path
            exists = [bool]$exists
            size = $null
            sha256 = $null
            modification_time_utc = $null
            raw_copy = $null
        }
        if ($exists) {
            $file = Get-Item -LiteralPath $path -ErrorAction Stop
            $copyName = "oem_{0:D3}.log" -f $index
            $copyPath = Join-Path $logDirectory $copyName
            Copy-Item -LiteralPath $path -Destination $copyPath -ErrorAction Stop
            $row.size = (Get-Item -LiteralPath $copyPath -ErrorAction Stop).Length
            $row.sha256 = (Get-FileHash -LiteralPath $copyPath -Algorithm SHA256).Hash.ToLowerInvariant()
            $row.modification_time_utc = $file.LastWriteTimeUtc.ToString("o")
            $row.raw_copy = "raw/oem_logs_$Stage/$copyName"
        } elseif ($Stage -eq "before") {
            Fail-D255 "configured OEM log became unreadable before authorization: $path"
        }
        $rows.Add($row)
    }
    $metadataPath = Join-Path $script:RunDirectory "oem_logs_${Stage}_metadata.json"
    Write-D255JsonArray -Rows @($rows) -Path $metadataPath
    return $metadataPath
}

function Invoke-D255PreAuthorizationEvidenceSetup {
    param(
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Preflight,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$OemLogCandidates,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$CacheRoots,
        [Parameter(Mandatory = $true)][string]$RawDirectory,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$CaptureInterfaces,
        [Parameter(Mandatory = $true)][int]$DurationSeconds
    )
    if ($CaptureInterfaces.Count -eq 0) {
        Fail-D255 "pre-authorization setup requires at least one capture interface"
    }
    Write-OemLogSnapshot -Stage "before" -Candidates $OemLogCandidates -RawDirectory $RawDirectory | Out-Null
    Write-FileSnapshot -Stage "before" -Roots $CacheRoots -RawDirectory $RawDirectory | Out-Null
    $Preflight["runtime"] = Get-D255RuntimeInfo
    $Preflight | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $script:RunDirectory "preflight.json") -Encoding UTF8
    Write-OperatorMarker -Event "ACCOUNT_PREREQUISITES_CHECKED" -Detail "Sign-in options accessible; PIN state=$WindowsHelloPinState; no PIN change"
    $capturePath = Join-Path $RawDirectory "wire.pcapng"
    $captureSelectors = @($CaptureInterfaces | ForEach-Object { "-i `"$_`"" }) -join " "
    return [ordered]@{
        capture_path = $capturePath
        capture_arguments = "$captureSelectors -a duration:$DurationSeconds -q -w `"$capturePath`""
    }
}

function Invoke-D255PreAuthorizationSimulation {
    if (-not [string]::IsNullOrWhiteSpace($Authorization)) {
        Fail-D255 "authorization must not be supplied to the offline pre-authorization simulation"
    }
    if (-not [string]::IsNullOrWhiteSpace($TsharkPath)) {
        Fail-D255 "TsharkPath must not be supplied to the offline pre-authorization simulation"
    }
    if ($CaptureInterface.Count -ne 0 -or $OemLogPath.Count -ne 0 -or $CacheRoot.Count -ne 0) {
        Fail-D255 "real capture interfaces and evidence paths are forbidden in the offline pre-authorization simulation"
    }
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    $simulationId = "D255_PREAUTH_SIM_{0}" -f ([Guid]::NewGuid().ToString("N"))
    $script:RunDirectory = Join-Path $OutputRoot $simulationId
    if (-not (Test-D255PathAvailable -Path $script:RunDirectory)) {
        Fail-D255 "pre-authorization simulation output collision"
    }
    New-Item -ItemType Directory -Path $script:RunDirectory -ErrorAction Stop | Out-Null
    $rawDirectory = Join-Path $script:RunDirectory "raw"
    New-Item -ItemType Directory -Path $rawDirectory -ErrorAction Stop | Out-Null
    $script:MarkerPath = Join-Path $script:RunDirectory "operator_markers.tsv"
    Set-Content -LiteralPath $script:MarkerPath -Encoding UTF8 -Value "timestamp_utc`tevent`tdetail"

    $fixtureRoot = Join-Path $script:RunDirectory "synthetic_input"
    New-Item -ItemType Directory -Path $fixtureRoot -ErrorAction Stop | Out-Null
    Set-Content -LiteralPath (Join-Path $fixtureRoot "Goodix_Cache.bin") -Encoding ASCII -Value "D255 synthetic cache fixture; no device data"
    $oemLogCandidates = @()
    if ($SimulationOemLogState -ceq "PRESENT") {
        $fixtureLog = Join-Path $fixtureRoot "goodix-synthetic.log"
        Set-Content -LiteralPath $fixtureLog -Encoding ASCII -Value "D255 synthetic OEM log fixture; no device data"
        $oemLogCandidates = @($fixtureLog)
    }
    $cacheRoots = @($fixtureRoot)
    $cacheCandidates = @(Get-TargetedFiles -Roots $cacheRoots)
    $preflight = [ordered]@{
        schema = "D255_WINDOWS_PREAUTH_SIMULATION_V1"
        result = "PASS"
        oem_log_source_count = $oemLogCandidates.Count
        oem_log_status = Get-D255AvailabilityStatus -SourceCount $oemLogCandidates.Count
        goodix_cache_source_count = $cacheCandidates.Count
        goodix_cache_status = Get-D255AvailabilityStatus -SourceCount $cacheCandidates.Count
        runtime = $null
        authorization_required_for_live_capture = $true
        authorization_consumed = $false
        real_capture_started = $false
        real_usb_open_count = 0
        real_hardware_action_count = 0
    }
    $setup = Invoke-D255PreAuthorizationEvidenceSetup `
        -Preflight $preflight `
        -OemLogCandidates $oemLogCandidates `
        -CacheRoots $cacheRoots `
        -RawDirectory $rawDirectory `
        -CaptureInterfaces @("USBPcap_SIMULATED") `
        -DurationSeconds $CaptureDurationSeconds
    Write-FileSnapshot -Stage "empty_roots_audit" -Roots @() -RawDirectory $rawDirectory | Out-Null

    $oemMetadata = Get-Content -LiteralPath (Join-Path $script:RunDirectory "oem_logs_before_metadata.json") -Raw
    if ($SimulationOemLogState -ceq "ABSENT" -and $oemMetadata.Trim() -cne "[]") {
        Fail-D255 "empty OEM-log simulation did not serialize an empty JSON array"
    }
    if ($SimulationOemLogState -ceq "PRESENT" -and
        -not (Test-Path -LiteralPath (Join-Path $rawDirectory "oem_logs_before\oem_000.log") -PathType Leaf)) {
        Fail-D255 "present OEM-log simulation did not snapshot the synthetic log"
    }
    if ($cacheCandidates.Count -ne 1 -or
        -not (Test-Path -LiteralPath (Join-Path $script:RunDirectory "cache_before_metadata.json") -PathType Leaf)) {
        Fail-D255 "pre-authorization simulation did not snapshot the synthetic cache"
    }
    $emptyCacheMetadata = Get-Content -LiteralPath (Join-Path $script:RunDirectory "cache_empty_roots_audit_metadata.json") -Raw
    if ($emptyCacheMetadata.Trim() -cne "[]" -or @(Get-TargetedFiles -Roots @()).Count -ne 0) {
        Fail-D255 "empty cache-root collection did not produce an empty snapshot"
    }
    if ($script:AuthorizationConsumed -or $null -ne $script:CaptureProcess -or
        (Test-Path -LiteralPath $setup.capture_path -PathType Leaf)) {
        Fail-D255 "pre-authorization simulation crossed the authorization/capture boundary"
    }
    [ordered]@{
        schema = "D255_WINDOWS_PREAUTH_SIMULATION_RESULT_V1"
        result = "PASS"
        oem_log_state = $SimulationOemLogState
        shared_setup_function = "Invoke-D255PreAuthorizationEvidenceSetup"
        authorization_consumed = $false
        real_capture_started = $false
        real_usb_open_count = 0
        real_hardware_action_count = 0
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $script:RunDirectory "preauthorization_simulation_result.json") -Encoding UTF8
    if ($SimulationOemLogState -ceq "ABSENT") {
        Write-Output "EMPTY_OEM_LOG_CANDIDATES_BINDING=PASS"
    } else {
        Write-Output "PRESENT_OEM_LOG_SNAPSHOT=PASS"
    }
    Write-Output "AUTHORIZATION_CONSUMED=false"
    Write-Output "REAL_CAPTURE_STARTED=false"
    Write-Output "REAL_USB_OPEN_COUNT=0"
    Write-Output "REAL_HARDWARE_ACTION_COUNT=0"
    Write-Output "EMPTY_CACHE_ROOTS_BINDING=PASS"
}

function Write-Manifest {
    $files = [System.Collections.Generic.List[object]]::new()
    Get-ChildItem -LiteralPath $script:RunDirectory -File -Recurse -Force |
        Where-Object { $_.Name -notin @("input_manifest.json", "input_manifest.json.sha256") } |
        Sort-Object -Property FullName |
        ForEach-Object {
            $relative = Get-D255RelativePath -BasePath $script:RunDirectory -ChildPath $_.FullName
            $role = "metadata"
            if ($relative -eq "raw/wire.pcapng") { $role = "wire" }
            elseif ($relative -eq "operator_markers.tsv") { $role = "markers" }
            elseif ($relative -eq "run_clock.json") { $role = "clock_anchor" }
            elseif ($relative -eq "run_clock_end.json") { $role = "clock_end" }
            elseif ($relative -eq "guest_topology_before_attach.json") { $role = "guest_topology_before" }
            elseif ($relative -eq "guest_topology_after_attach.json") { $role = "guest_topology_after_attach" }
            elseif ($relative -eq "guest_topology_after_capture.json") { $role = "guest_topology_after_capture" }
            elseif ($relative -like "raw/oem_logs_before/*") { $role = "oem_log_before" }
            elseif ($relative -like "raw/oem_logs_after/*") { $role = "oem_log_after" }
            elseif ($relative -like "raw/cache_before/*") { $role = "cache_before" }
            elseif ($relative -like "raw/cache_after/*") { $role = "cache_after" }
            $files.Add([ordered]@{
                path = $relative
                role = $role
                size = $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            })
        }
    $manifest = [ordered]@{
        schema = "D255_WINDOWS_EVIDENCE_INPUT_MANIFEST_V3"
        created_utc = Get-UtcStamp
        target = "27c6:5125"
        expected_firmware = "GF_ST411SEC_APP_12509"
        raw_evidence_local_only = $true
        files = @($files)
    }
    $manifestPath = Join-Path $script:RunDirectory "input_manifest.json"
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$manifestPath.sha256" -Encoding ASCII -Value "$manifestHash  input_manifest.json"
}

function Invoke-D255SelfTest {
    $runtime = Get-D255RuntimeInfo
    $known = Get-D255Sha256HexForString -Value "abc"
    if ($known -cne "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad") {
        Fail-D255 "SHA-256 known-answer test failed"
    }
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    $selfTestDirectory = Join-Path $OutputRoot ("D255_SELFTEST_{0}" -f ([Guid]::NewGuid().ToString("N")))
    if (-not (Test-D255PathAvailable -Path $selfTestDirectory)) { Fail-D255 "self-test output collision" }
    $base = Join-Path $selfTestDirectory "run"
    $childDirectory = Join-Path $base "nested"
    $sibling = Join-Path $selfTestDirectory "run2\item.bin"
    New-Item -ItemType Directory -Path $childDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path ([System.IO.Path]::GetDirectoryName($sibling)) -Force | Out-Null
    $child = Join-Path $childDirectory "item.bin"
    Set-Content -LiteralPath $child -Encoding ASCII -Value "collision-probe"
    if ((Get-D255RelativePath -BasePath $base -ChildPath $child) -cne "nested/item.bin") {
        Fail-D255 "relative path helper returned an unexpected value"
    }
    $siblingRejected = $false
    try {
        Get-D255RelativePath -BasePath $base -ChildPath $sibling | Out-Null
    } catch [InvalidOperationException] {
        $siblingRejected = $true
    }
    if (-not $siblingRejected) { Fail-D255 "relative path helper accepted a sibling prefix" }
    if (Test-D255PathAvailable -Path $child) {
        Fail-D255 "output collision probe did not reject an existing path"
    }
    if ((Get-D255AvailabilityStatus -SourceCount 0) -cne "ABSENT" -or
        (Get-D255AvailabilityStatus -SourceCount 1) -cne "PRESENT") {
        Fail-D255 "evidence source availability classification failed"
    }
    $missingCapturePath = Join-Path $selfTestDirectory "missing.pcapng"
    $zeroCapturePath = Join-Path $selfTestDirectory "zero.pcapng"
    [System.IO.File]::WriteAllBytes($zeroCapturePath, [byte[]]@())
    if ((Test-Path -LiteralPath $missingCapturePath) -or
        -not (Test-D255PreAttachReadinessState -ProcessAlive $true -GuestTargetCount 0)) {
        Fail-D255 "pre-attach readiness rejected a live process with a not-yet-created pcapng"
    }
    if (-not (Test-D255PreAttachReadinessState -ProcessAlive $true -GuestTargetCount 0) -or
        -not (Test-Path -LiteralPath $zeroCapturePath -PathType Leaf) -or
        (Get-Item -LiteralPath $zeroCapturePath).Length -ne 0) {
        Fail-D255 "pre-attach readiness rejected a live process with a zero-byte pcapng"
    }
    if (Test-D255PreAttachReadinessState -ProcessAlive $false -GuestTargetCount 0) {
        Fail-D255 "pre-attach readiness accepted an exited capture process"
    }
    if (Test-D255PreAttachReadinessState -ProcessAlive $true -GuestTargetCount 1) {
        Fail-D255 "pre-attach readiness accepted a target already present in the guest"
    }
    if ((Test-D255FinalCaptureValidationState -ProcessExited $true -TsharkExitCode 0 -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 1) -cne "PASS" -or
        (Test-D255FinalCaptureValidationState -ProcessExited $true -TsharkExitCode $null -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 1) -cne "PASS_WITH_EXIT_CODE_UNAVAILABLE" -or
        (Test-D255FinalCaptureValidationState -ProcessExited $true -TsharkExitCode $null -PcapngExists $false -PcapngLength 0 -ReadableFrameCount 0) -cne "FAIL_CLOSED" -or
        (Test-D255FinalCaptureValidationState -ProcessExited $true -TsharkExitCode $null -PcapngExists $true -PcapngLength 0 -ReadableFrameCount 0) -cne "FAIL_CLOSED" -or
        (Test-D255FinalCaptureValidationState -ProcessExited $true -TsharkExitCode $null -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 0) -cne "FAIL_CLOSED" -or
        (Test-D255FinalCaptureValidationState -ProcessExited $true -TsharkExitCode 7 -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 1) -cne "FAIL_CLOSED" -or
        (Test-D255FinalCaptureValidationState -ProcessExited $false -TsharkExitCode $null -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 1) -cne "FAIL_CLOSED") {
        Fail-D255 "final capture validation state contract failed"
    }
    $clockPath = Join-Path $selfTestDirectory "run_clock.json"
    $clock = New-D255ClockAnchor -Phase "SELFTEST"
    $clock | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $clockPath -Encoding UTF8
    $parsedClock = Get-Content -LiteralPath $clockPath -Raw | ConvertFrom-Json
    if ($parsedClock.schema -cne "D255_WINDOWS_RUN_CLOCK_V1" -or
        [DateTimeOffset]::Parse($parsedClock.utc_iso).Offset -ne [TimeSpan]::Zero -or
        [string]::IsNullOrWhiteSpace([string]$parsedClock.windows_timezone_id)) {
        Fail-D255 "clock anchor serialization/parsing failed"
    }
    [ordered]@{
        schema = "D255_POWERSHELL_SELFTEST_V1"
        result = "PASS"
        runtime = $runtime
        sha256_abc = $known
        relative_path = "nested/item.bin"
        sibling_prefix_rejected = $siblingRejected
        clock_anchor_parsed = $true
        json_serialization = "PASS"
        output_collision_semantics = "PASS"
        evidence_source_availability_semantics = "PASS"
        capture_preattach_process_only_readiness = "PASS"
        capture_missing_file_before_attach_allowed = -not (Test-Path -LiteralPath $missingCapturePath)
        capture_zero_byte_file_before_attach_allowed = $true
        capture_exited_process_before_attach_rejected = $true
        final_capture_validation_contract = "PASS"
        final_capture_exit_zero_result = "PASS"
        final_capture_exit_unavailable_result = "PASS_WITH_EXIT_CODE_UNAVAILABLE"
        final_capture_invalid_or_nonzero_result = "FAIL_CLOSED"
        hardware_action_count = 0
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $selfTestDirectory "selftest_result.json") -Encoding UTF8
    Write-Output "D255_POWERSHELL_SELFTEST=PASS"
    Write-Output "D255_CAPTURE_READINESS_SELFTEST=PASS"
    Write-Output "D255_HARDWARE_ACTION_COUNT=0"
    Write-Output "D255_AUTHORIZATION_CONSUMED=false"
}

$selectedModeCount = 0
if ($SelfTestOnly) { $selectedModeCount += 1 }
if ($PreflightOnly) { $selectedModeCount += 1 }
if ($PreAuthorizationSimulationOnly) { $selectedModeCount += 1 }
if ($selectedModeCount -gt 1) {
    Fail-D255 "SelfTestOnly, PreflightOnly and PreAuthorizationSimulationOnly are mutually exclusive"
}
if ($SelfTestOnly) {
    Invoke-D255SelfTest
    exit 0
}
if ($PreAuthorizationSimulationOnly) {
    Invoke-D255PreAuthorizationSimulation
    exit 0
}

if ([string]::IsNullOrWhiteSpace($TsharkPath)) { Fail-D255 "TsharkPath is required outside SelfTestOnly" }
if ($CaptureInterface.Count -eq 0) { Fail-D255 "at least one CaptureInterface is required outside SelfTestOnly" }
if (-not (Test-Path -LiteralPath $TsharkPath -PathType Leaf)) {
    Fail-D255 "TShark executable not found"
}
foreach ($selector in $CaptureInterface) {
    if ([string]::IsNullOrWhiteSpace($selector) -or $selector -match '["\r\n]') {
        Fail-D255 "invalid capture interface selector"
    }
}
if ($VmGuestReadyConfirmation -cne $ExpectedVmGuestReadyConfirmation) {
    Fail-D255 "VM guest-ready/target-absence confirmation missing"
}
$initialTargets = @(Get-TargetDevices)
if ($initialTargets.Count -ne 0) {
    Fail-D255 "target must be detached from the Windows guest before cold-attach capture"
}
$interfaceLines = @(& $TsharkPath -D 2>&1)
if ($LASTEXITCODE -ne 0) { Fail-D255 "tshark interface enumeration failed" }
$usbPcapCandidates = @($interfaceLines | Where-Object { $_ -match "(?i)USBPcap" })
if ($usbPcapCandidates.Count -eq 0) { Fail-D255 "no USBPcap interface was detected" }
$interfaceMatches = [System.Collections.Generic.List[string]]::new()
foreach ($selector in $CaptureInterface) {
    $escapedInterface = [regex]::Escape($selector)
    $interfacePattern = "(?i)(?<![A-Za-z0-9_.-])$escapedInterface(?![A-Za-z0-9_.-])"
    $matches = @($usbPcapCandidates | Where-Object { $_ -match $interfacePattern })
    if ($matches.Count -ne 1) { Fail-D255 "capture interface selector is absent or ambiguous: $selector" }
    if (-not $interfaceMatches.Contains([string]$matches[0])) { $interfaceMatches.Add([string]$matches[0]) }
}
if ($usbPcapCandidates.Count -gt 1 -and $interfaceMatches.Count -ne $usbPcapCandidates.Count) {
    Fail-D255 "USBPCAP_INTERFACE_SELECTION=AMBIGUOUS; select every relevant USBPcap interface or stop"
}
if ($AccountPrerequisiteConfirmation -cne $ExpectedAccountPrerequisiteConfirmation) {
    Fail-D255 "account-level Sign-in options confirmation missing"
}
if ($AllowedWindowsHelloPinStates -cnotcontains $WindowsHelloPinState) {
    Fail-D255 "WINDOWS_HELLO_PIN_STATE must be classified explicitly"
}
if ($AllowedFingerprintSetupPinRequirements -cnotcontains $FingerprintSetupPinRequirement) {
    Fail-D255 "fingerprint setup PIN requirement must be classified explicitly"
}
if ($WindowsHelloPinState -ceq "NOT_CONFIGURED" -and
    $FingerprintSetupPinRequirement -ceq "REQUIRED") {
    Fail-D255 "WINDOWS_HELLO_SETUP_PREREQUISITE_MISSING_BEFORE_AUTHORIZATION; PIN creation/change is forbidden"
}
foreach ($path in $OemLogPath) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Fail-D255 "configured OEM log is unreadable: $path"
    }
}
foreach ($root in $CacheRoot) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        Fail-D255 "configured cache root is unreadable: $root"
    }
}
$oemLogCandidates = @(Resolve-OemLogCandidates)
$cacheRoots = @(Resolve-CacheRoots)
$cacheCandidates = @(Get-TargetedFiles -Roots $cacheRoots)
$oemLogStatus = Get-D255AvailabilityStatus -SourceCount $oemLogCandidates.Count
$cacheStatus = Get-D255AvailabilityStatus -SourceCount $cacheCandidates.Count
if (Test-Path -LiteralPath $OutputRoot -PathType Leaf) {
    Fail-D255 "OutputRoot names a file"
}
$tsharkVersion = [string](@(& $TsharkPath --version 2>&1)[0])
if ($LASTEXITCODE -ne 0) { Fail-D255 "tshark version query failed" }
$outputFullPath = [System.IO.Path]::GetFullPath($OutputRoot)
$outputDrive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($outputFullPath))
$freeBytes = $outputDrive.AvailableFreeSpace
if ($freeBytes -lt 1073741824) { Fail-D255 "less than 1 GiB free at OutputRoot" }

$preflight = [ordered]@{
    schema = "D255_WINDOWS_PREFLIGHT_V4"
    result = "PASS"
    timestamp_utc = Get-UtcStamp
    target_present_count = $initialTargets.Count
    target_must_initially_be_absent = $true
    vm_windows_running = $true
    guest_goodix_present_before_attach = $false
    no_existing_fingerprint_required = $true
    no_new_pin_creation_allowed = $true
    settings_signin_options_page_accessible = $true
    current_vm_fingerprint_enrollment = "NOT_COMPLETED"
    windows_hello_pin_state = $WindowsHelloPinState
    fingerprint_setup_pin_requirement = $FingerprintSetupPinRequirement
    account_prerequisites_ready = $true
    sensor_dependent_ui_availability = "UNKNOWN_BEFORE_ATTACH"
    preattach_fingerprint_ui_required = $false
    postattach_windows_ui_path = "WINDOWS_HELLO_SETUP_NO_FINGER"
    capture_interfaces = @($CaptureInterface)
    capture_interface_matches = @($interfaceMatches)
    usbpcap_candidate_count = $usbPcapCandidates.Count
    usbpcap_interface_selection = $(if ($usbPcapCandidates.Count -eq 1) { "UNAMBIGUOUS" } else { "CAPTURE_ALL" })
    tshark_path = (Resolve-Path -LiteralPath $TsharkPath).Path
    tshark_version = $tsharkVersion
    capture_duration_seconds = $CaptureDurationSeconds
    oem_log_source_count = $oemLogCandidates.Count
    oem_log_status = $oemLogStatus
    goodix_cache_source_count = $cacheCandidates.Count
    goodix_cache_status = $cacheStatus
    runtime = $null
    authorization_required_for_live_capture = $true
    authorization_consumed = $false
    no_device_action_performed = $true
}

if ($PreflightOnly) {
    $preflight["runtime"] = Get-D255RuntimeInfo
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    $preflightPath = Join-Path $OutputRoot "D255_preflight_only.json"
    if (-not (Test-D255PathAvailable -Path $preflightPath)) { Fail-D255 "preflight output collision" }
    $preflight | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $preflightPath -Encoding UTF8
    Write-Output "D255_PREFLIGHT_ONLY=PASS"
    Write-Output "ACCOUNT_PREREQUISITES_READY=true"
    Write-Output "WINDOWS_HELLO_PIN_STATE=$WindowsHelloPinState"
    Write-Output "SENSOR_DEPENDENT_UI_AVAILABILITY=UNKNOWN_BEFORE_ATTACH"
    Write-Output "OEM_LOG_STATUS=$oemLogStatus"
    Write-Output "OEM_LOG_SOURCE_COUNT=$($oemLogCandidates.Count)"
    Write-Output "GOODIX_CACHE_STATUS=$cacheStatus"
    Write-Output "GOODIX_CACHE_SOURCE_COUNT=$($cacheCandidates.Count)"
    Write-Output "D255_HARDWARE_ACTION_COUNT=0"
    Write-Output "D255_AUTHORIZATION_CONSUMED=false"
    exit 0
}

$runId = "D255_{0}_{1}" -f ([DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")), ([Guid]::NewGuid().ToString("N").Substring(0, 8))
$script:RunDirectory = Join-Path $OutputRoot $runId
if (-not (Test-D255PathAvailable -Path $script:RunDirectory)) { Fail-D255 "run output collision" }
New-Item -ItemType Directory -Path $script:RunDirectory -ErrorAction Stop | Out-Null
$rawDirectory = Join-Path $script:RunDirectory "raw"
New-Item -ItemType Directory -Path $rawDirectory -ErrorAction Stop | Out-Null
$script:MarkerPath = Join-Path $script:RunDirectory "operator_markers.tsv"
Set-Content -LiteralPath $script:MarkerPath -Encoding UTF8 -Value "timestamp_utc`tevent`tdetail"

# Pre-hardware setup: no authorization is consumed until every operation here
# has completed successfully.
$clockPath = Join-Path $script:RunDirectory "run_clock.json"
$clockAnchor = New-D255ClockAnchor -Phase "BEFORE_CAPTURE"
$clockAnchor | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $clockPath -Encoding UTF8
Write-OperatorMarker -Event "CLOCK_ANCHOR" -Detail "local offset and Windows timezone recorded"
Write-OperatorMarker -Event "VM_GUEST_READY" -Detail "VM already running; target absent from guest"
Write-GuestTopologySnapshot -Stage "before_attach"
Write-OperatorMarker -Event "GUEST_TOPOLOGY_BEFORE" -Detail "read-only PnP snapshot; 27c6:5125 absent"
$preAuthorizationSetup = Invoke-D255PreAuthorizationEvidenceSetup `
    -Preflight $preflight `
    -OemLogCandidates $oemLogCandidates `
    -CacheRoots $cacheRoots `
    -RawDirectory $rawDirectory `
    -CaptureInterfaces $CaptureInterface `
    -DurationSeconds $CaptureDurationSeconds
$capturePath = $preAuthorizationSetup.capture_path
$captureArguments = $preAuthorizationSetup.capture_arguments
$script:CapturePath = $capturePath
$script:CaptureArgumentsRedacted = "tshark <configured-executable> -i <configured-interface>x$($CaptureInterface.Count) -a duration:$CaptureDurationSeconds -q -w <capture-output>"
$script:CaptureStdoutPath = Join-Path $script:RunDirectory "tshark_stdout.txt"
$script:CaptureStderrPath = Join-Path $script:RunDirectory "tshark_stderr.txt"

if ($Authorization -cne $ExpectedAuthorization) {
    Fail-D255 "exact one-run authorization string missing or wrong"
}
$script:AuthorizationConsumed = $true
@{
    schema = "D255_AUTHORIZATION_CONSUMED_V3"
    consumed_utc = Get-UtcStamp
    authorization_sha256 = Get-D255Sha256HexForString -Value $Authorization
    pre_hardware_setup_complete = $true
    repeat_forbidden_without_new_authorization = $true
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:RunDirectory "authorization_consumed.json") -Encoding UTF8
Write-OperatorMarker -Event "AUTHORIZATION_CONSUMED" -Detail "one run only; pre-hardware setup complete"

try {
    try {
        $script:CaptureProcess = Start-Process -FilePath $TsharkPath -ArgumentList $captureArguments `
            -PassThru -NoNewWindow -RedirectStandardOutput $script:CaptureStdoutPath `
            -RedirectStandardError $script:CaptureStderrPath
        # Windows PowerShell 5.1 can lose ExitCode after Wait-Process when
        # -NoNewWindow or redirected streams are used.  Accessing Handle while
        # the process is alive preserves it when the runtime supports that path.
        $script:CaptureProcessHandle = $script:CaptureProcess.Handle
    } catch {
        Fail-D255Capture "capture process failed to start: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 2
    $captureAlive = ($null -ne $script:CaptureProcess -and -not $script:CaptureProcess.HasExited)
    $preAttachTargets = @(Get-TargetDevices)
    if (-not (Test-D255PreAttachReadinessState `
        -ProcessAlive $captureAlive -GuestTargetCount $preAttachTargets.Count)) {
        if (-not $captureAlive) {
            Fail-D255Capture "capture process exited during the pre-attach grace period"
        }
        Fail-D255Capture "target appeared in the guest before the authorized manual attach"
    }
    Write-OperatorMarker -Event "CAPTURE_PROCESS_STARTED" -Detail "TShark process active; target absent; pcapng materialization and frames not asserted"
    Write-OperatorMarker -Event "CAPTURE_STARTED" -Detail "compatibility marker: TShark process active before attach; pcapng existence/nonempty state not asserted"

    Write-OperatorMarker -Event "VM_USB_ATTACH_BEGIN" -Detail "single operator GUI action follows"
    Read-Host "Perform the single manual Goodix host-to-VM GUI attach now. Do not detach or re-attach. Press Enter after the GUI action completes"
    Assert-CaptureActive
    Write-OperatorMarker -Event "VM_USB_ATTACH_END"
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $targets = @(Get-TargetDevices)
        if ($targets.Count -eq 1) { break }
        if ($targets.Count -gt 1) { Fail-D255 "target became ambiguous after attach" }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($targets.Count -ne 1) { Fail-D255 "target did not appear after cold attach" }
    Write-GuestTopologySnapshot -Stage "after_attach"
    Write-OperatorMarker -Event "GUEST_27C6_5125_PRESENT" -Detail $targets[0].InstanceId

    Read-Host "Keep hands away from the sensor and wait for passive OEM initialization to settle. Press Enter only after the passive bootstrap has settled"
    Assert-CaptureActive
    Assert-SingleGuestTarget | Out-Null
    if (-not (Test-Path -LiteralPath $capturePath -PathType Leaf)) {
        Fail-D255Capture "capture output was not materialized after attach and passive bootstrap"
    }
    Write-OperatorMarker -Event "CAPTURE_OUTPUT_MATERIALIZED" -Detail "pcapng exists after attach; nonempty/readable validation remains final"
    Write-OperatorMarker -Event "PASSIVE_BOOTSTRAP_SETTLED" -Detail "operator-observed passive settle; A8 proof remains wire-derived"
    Write-OperatorMarker -Event "HELLO_SETUP_UI_CHECK_BEGIN" -Detail "post-attach sensor-dependent UI check"
    Write-Output "Open Settings > Accounts > Sign-in options > Fingerprint recognition (Windows Hello) > Set up/Add a fingerprint. Never touch the sensor or create/change a PIN."
    $helloUiResult = Read-HelloSetupUiResult
    if ($helloUiResult -ceq "READY_WAITING_FOR_FINGER") {
        Assert-CaptureActive
    } elseif ($script:CaptureProcess.HasExited) {
        $earlyExitCode = Get-D255CaptureExitCode
        if ($null -ne $earlyExitCode -and $earlyExitCode -ne 0) {
            Fail-D255Capture "partial bootstrap capture process failed before UI classification"
        }
    }
    Assert-SingleGuestTarget | Out-Null
    $runResult = "FULL_ZERO_FINGER_CANCEL_REENTRY"
    if ($helloUiResult -ceq "READY_WAITING_FOR_FINGER") {
        Write-OperatorMarker -Event "HELLO_SETUP_UI_READY" -Detail $helloUiResult
        Write-OperatorMarker -Event "OEM_SESSION_BEGIN" -Detail "OEM_UI_PATH=WINDOWS_HELLO_SETUP_NO_FINGER"
        Write-OperatorMarker -Event "OEM_WAITING_NO_FINGER" -Detail "operator UI observation; zero finger"
        Write-OperatorMarker -Event "CANCEL_NO_FINGER_BEGIN"
        Read-Host "Cancel the setup/add-fingerprint wizard without touching the sensor, then press Enter"
        Assert-CaptureActive
        Assert-SingleGuestTarget | Out-Null
        Write-OperatorMarker -Event "CANCEL_NO_FINGER_END"

        Write-OperatorMarker -Event "REENTRY_BEGIN"
        Read-Host "Reopen the same setup/add-fingerprint path without touching the sensor. Press Enter when it is waiting for a fingerprint"
        Assert-CaptureActive
        Assert-SingleGuestTarget | Out-Null
        Write-OperatorMarker -Event "REENTRY_WAITING_NO_FINGER" -Detail "operator UI observation; zero finger"
        Write-OperatorMarker -Event "REENTRY_CANCEL_BEGIN"
        Read-Host "Cancel the setup/add-fingerprint wizard again without touching the sensor, then press Enter"
        Assert-CaptureActive
        Assert-SingleGuestTarget | Out-Null
        Write-OperatorMarker -Event "REENTRY_CANCEL_END"
        Write-OperatorMarker -Event "REENTRY_END"
    } else {
        $partialMarker = @{
            "UI_UNAVAILABLE" = "HELLO_SETUP_UI_UNAVAILABLE"
            "NEW_PIN_REQUIRED" = "HELLO_SETUP_NEW_PIN_REQUIRED"
            "UNEXPECTED_PREREQUISITE" = "HELLO_SETUP_UNEXPECTED_PREREQUISITE"
        }[$helloUiResult]
        Write-OperatorMarker -Event $partialMarker -Detail $helloUiResult
        $runResult = "PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE"
        Write-Output "D255_RESTORE_PHASE_RESULT=WINDOWS_HELLO_SETUP_PREREQUISITE_MISSING_AFTER_ATTACH"
        Write-Output "BOOTSTRAP_EVIDENCE_PRESERVED=true"
        Write-Output "RESTORE_EVIDENCE_ACQUIRED=false"
        Write-Output "RESTORE_CLOSED=false"
        Write-Output "PARTIAL_CAPTURE_STOP_METHOD=BOUNDED_CAPTURE_TIMER_EXHAUSTED"
    }
    Write-OperatorMarker -Event "OPERATOR_PHASES_COMPLETE"
    Wait-Process -Id $script:CaptureProcess.Id
    $script:CaptureProcess.Refresh()
    if (-not $script:CaptureProcess.HasExited) {
        Fail-D255Capture "capture process did not exit at the duration boundary"
    }
    $tsharkExitCode = Get-D255CaptureExitCode
    if ($null -ne $tsharkExitCode -and $tsharkExitCode -ne 0) {
        Fail-D255Capture "capture process returned a non-zero exit code at the duration boundary"
    }

    if (-not (Test-Path -LiteralPath $capturePath -PathType Leaf)) { Fail-D255Capture "capture output missing at final validation" }
    $captureLength = (Get-Item -LiteralPath $capturePath).Length
    if ($captureLength -le 0) { Fail-D255Capture "capture output empty at final validation" }
    $captureValidation = @(& $TsharkPath -r $capturePath -c 1 -T fields -e frame.number 2>&1)
    $captureReadExitCode = $LASTEXITCODE
    $readableFrameCount = if ($captureReadExitCode -eq 0 -and $captureValidation -contains "1") { 1 } else { 0 }
    $finalCaptureResult = Test-D255FinalCaptureValidationState `
        -ProcessExited $script:CaptureProcess.HasExited -TsharkExitCode $tsharkExitCode `
        -PcapngExists $true -PcapngLength $captureLength `
        -ReadableFrameCount $readableFrameCount
    if ($finalCaptureResult -ceq "FAIL_CLOSED") {
        Fail-D255Capture "capture output is not a readable nonempty pcapng with at least one frame"
    }
    $tsharkExitCodeText = if ($null -eq $tsharkExitCode) { "UNAVAILABLE" } else { [string]$tsharkExitCode }
    Write-OperatorMarker -Event "CAPTURE_STOPPED" -Detail "duration boundary reached; TSHARK_EXIT_CODE=$tsharkExitCodeText; RESULT=$finalCaptureResult"
    Write-Output "TSHARK_EXIT_CODE=$tsharkExitCodeText"
    Write-Output "D255_FINAL_CAPTURE_VALIDATION=$finalCaptureResult"
    $clockEndPath = Join-Path $script:RunDirectory "run_clock_end.json"
    New-D255ClockAnchor -Phase "AFTER_CAPTURE" | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $clockEndPath -Encoding UTF8
    $finalTargets = @(Get-TargetDevices)
    if ($finalTargets.Count -ne 1) { Fail-D255 "D255_EVIDENCE_VALIDITY=INVALID_VM_USB_TOPOLOGY_CHANGE" }
    Write-GuestTopologySnapshot -Stage "after_capture"
    Write-OemLogSnapshot -Stage "after" -Candidates $oemLogCandidates -RawDirectory $rawDirectory | Out-Null
    Write-FileSnapshot -Stage "after" -Roots $cacheRoots -RawDirectory $rawDirectory | Out-Null
    Write-Manifest
    Write-Output "OEM_LOG_STATUS=$oemLogStatus"
    Write-Output "OEM_LOG_SOURCE_COUNT=$($oemLogCandidates.Count)"
    Write-Output "GOODIX_CACHE_STATUS=$cacheStatus"
    Write-Output "GOODIX_CACHE_SOURCE_COUNT=$($cacheCandidates.Count)"
    Write-Output "D255_RUN_RESULT=$runResult"
    if ($runResult -ceq "PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE") {
        Write-Output "PARTIAL_CAPTURE_FILE_VALIDATION=TSHARK_EXIT_ZERO_OR_UNAVAILABLE_NONEMPTY_READABLE_PCAPNG"
    }
    Write-Output "D255_CAPTURE_RESULT=CAPTURED_PENDING_OFFLINE_VALIDATION"
    Write-Output "D255_RUN_DIRECTORY=$script:RunDirectory"
    Write-Output "D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true"
} catch {
    if ($script:MarkerPath -and (Test-Path -LiteralPath $script:MarkerPath)) {
        Write-OperatorMarker -Event "RUN_FAILED" -Detail $_.Exception.Message
    }
    if ($null -ne $script:CaptureProcess -and -not $script:CaptureProcess.HasExited) {
        Write-Warning "Capture remains bounded by its duration; no automatic hardware retry will occur."
    }
    throw
}
