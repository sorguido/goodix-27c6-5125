# SPDX-License-Identifier: GPL-2.0-or-later
# D255 prepares one operator-authorized Windows OEM evidence capture.
[CmdletBinding()]
param(
    [switch]$PreflightOnly,
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [Parameter(Mandatory = $true)][string]$TsharkPath,
    [Parameter(Mandatory = $true)][string]$CaptureInterface,
    [string]$Authorization = "",
    [ValidateRange(90, 1800)][int]$CaptureDurationSeconds = 300,
    [string[]]$OemLogPath = @(),
    [string[]]$CacheRoot = @(),
    [switch]$AllowReentryFinger,
    [switch]$TargetMustInitiallyBeAbsent = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ExpectedAuthorization = "--i-authorize-one-d255-windows-oem-evidence-capture"
$TargetVidPidPattern = "VID_27C6&PID_5125"

function Fail-D255 {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "D255_FAIL_CLOSED: $Message"
}

function Get-UtcStamp {
    return [DateTime]::UtcNow.ToString("o")
}

function Assert-CaptureActive {
    if ($script:CaptureProcess.HasExited) {
        Fail-D255 "capture duration elapsed or capture process failed before operator phases completed"
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

function Get-TargetDevices {
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D255 "Get-PnpDevice is unavailable"
    }
    return @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object {
        $_.InstanceId -match $TargetVidPidPattern
    })
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
    param([string[]]$Roots)
    $files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    foreach ($root in $Roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Length -eq 13520 -or
                $_.Name -match "(?i)(goodix|base|cache|wbdi|finger|nav|image)"
            } |
            ForEach-Object { $files.Add($_) }
    }
    return @($files | Sort-Object -Property FullName -Unique)
}

function Resolve-OemLogCandidates {
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($path in $OemLogPath) {
        if ($path) { $candidates.Add($path) }
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
        [Parameter(Mandatory = $true)][string[]]$Roots,
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
    @($rows) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $snapshotPath -Encoding UTF8
    return $snapshotPath
}

function Copy-OemLogs {
    param([Parameter(Mandatory = $true)][string]$RawDirectory)
    $logDirectory = Join-Path $RawDirectory "oem_logs"
    New-Item -ItemType Directory -Path $logDirectory -ErrorAction Stop | Out-Null
    $candidates = @(Resolve-OemLogCandidates)
    if ($candidates.Count -eq 0) { Fail-D255 "no readable OEM/WBDI log source was identified" }
    $index = 0
    foreach ($path in $candidates) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            Fail-D255 "configured OEM log is unreadable: $path"
        }
        $destination = Join-Path $logDirectory ("oem_{0:D3}.log" -f $index)
        Copy-Item -LiteralPath $path -Destination $destination -ErrorAction Stop
        $index += 1
    }
}

function Write-Manifest {
    $files = [System.Collections.Generic.List[object]]::new()
    Get-ChildItem -LiteralPath $script:RunDirectory -File -Recurse -Force |
        Where-Object { $_.Name -notin @("input_manifest.json", "input_manifest.json.sha256") } |
        Sort-Object -Property FullName |
        ForEach-Object {
            $relative = [System.IO.Path]::GetRelativePath($script:RunDirectory, $_.FullName).Replace("\", "/")
            $role = "metadata"
            if ($relative -eq "raw/wire.pcapng") { $role = "wire" }
            elseif ($relative -eq "operator_markers.tsv") { $role = "markers" }
            elseif ($relative -like "raw/oem_logs/*") { $role = "oem_log" }
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
        schema = "D255_WINDOWS_EVIDENCE_INPUT_MANIFEST_V1"
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

if (-not (Test-Path -LiteralPath $TsharkPath -PathType Leaf)) {
    Fail-D255 "TShark executable not found"
}
if ($CaptureInterface -match '["\r\n]') { Fail-D255 "invalid capture interface characters" }
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
if ($oemLogCandidates.Count -eq 0) {
    Fail-D255 "no readable OEM/WBDI log source was identified"
}
if (Test-Path -LiteralPath $OutputRoot -PathType Leaf) {
    Fail-D255 "OutputRoot names a file"
}
$interfaceLines = @(& $TsharkPath -D 2>&1)
if ($LASTEXITCODE -ne 0) { Fail-D255 "tshark interface enumeration failed" }
$escapedInterface = [regex]::Escape($CaptureInterface)
$interfacePattern = "(?i)(?<![A-Za-z0-9_.-])$escapedInterface(?![A-Za-z0-9_.-])"
$interfaceMatches = @($interfaceLines | Where-Object { $_ -match $interfacePattern })
if ($interfaceMatches.Count -ne 1) {
    Fail-D255 "capture interface selector is absent or ambiguous"
}
$tsharkVersion = [string](@(& $TsharkPath --version 2>&1)[0])
if ($LASTEXITCODE -ne 0) { Fail-D255 "tshark version query failed" }
$outputFullPath = [System.IO.Path]::GetFullPath($OutputRoot)
$outputDrive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($outputFullPath))
$freeBytes = $outputDrive.AvailableFreeSpace
if ($freeBytes -lt 1073741824) { Fail-D255 "less than 1 GiB free at OutputRoot" }

$initialTargets = @(Get-TargetDevices)
if ($TargetMustInitiallyBeAbsent -and $initialTargets.Count -ne 0) {
    Fail-D255 "target must be detached from the Windows guest before cold-attach capture"
}
if (-not $TargetMustInitiallyBeAbsent -and $initialTargets.Count -ne 1) {
    Fail-D255 "target selector is absent or ambiguous"
}

$preflight = [ordered]@{
    schema = "D255_WINDOWS_PREFLIGHT_V1"
    result = "PASS"
    timestamp_utc = Get-UtcStamp
    target_present_count = $initialTargets.Count
    target_must_initially_be_absent = [bool]$TargetMustInitiallyBeAbsent
    capture_interface = $CaptureInterface
    capture_interface_match = [string]$interfaceMatches[0]
    tshark_path = (Resolve-Path -LiteralPath $TsharkPath).Path
    tshark_version = $tsharkVersion
    capture_duration_seconds = $CaptureDurationSeconds
    oem_log_source_count = $oemLogCandidates.Count
    authorization_required_for_live_capture = $true
    no_device_action_performed = $true
}

if ($PreflightOnly) {
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    $preflightPath = Join-Path $OutputRoot "D255_preflight_only.json"
    if (Test-Path -LiteralPath $preflightPath) { Fail-D255 "preflight output collision" }
    $preflight | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $preflightPath -Encoding UTF8
    Write-Output "D255_PREFLIGHT_ONLY=PASS"
    Write-Output "D255_HARDWARE_ACTION_COUNT=0"
    exit 0
}

if ($Authorization -cne $ExpectedAuthorization) {
    Fail-D255 "exact one-run authorization string missing or wrong"
}

$runId = "D255_{0}_{1}" -f ([DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")), ([Guid]::NewGuid().ToString("N").Substring(0, 8))
$script:RunDirectory = Join-Path $OutputRoot $runId
if (Test-Path -LiteralPath $script:RunDirectory) { Fail-D255 "run output collision" }
New-Item -ItemType Directory -Path $script:RunDirectory -ErrorAction Stop | Out-Null
$rawDirectory = Join-Path $script:RunDirectory "raw"
New-Item -ItemType Directory -Path $rawDirectory -ErrorAction Stop | Out-Null
$script:MarkerPath = Join-Path $script:RunDirectory "operator_markers.tsv"
Set-Content -LiteralPath $script:MarkerPath -Encoding UTF8 -Value "timestamp_utc`tevent`tdetail"
$preflight.no_device_action_performed = $true
$preflight | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $script:RunDirectory "preflight.json") -Encoding UTF8
@{
    schema = "D255_AUTHORIZATION_CONSUMED_V1"
    consumed_utc = Get-UtcStamp
    authorization_sha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($Authorization))).ToLowerInvariant()
    repeat_forbidden_without_new_authorization = $true
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:RunDirectory "authorization_consumed.json") -Encoding UTF8
Write-OperatorMarker -Event "AUTHORIZATION_CONSUMED" -Detail "one run only"

$cacheRoots = Resolve-CacheRoots
Write-FileSnapshot -Stage "before" -Roots $cacheRoots -RawDirectory $rawDirectory | Out-Null
$capturePath = Join-Path $rawDirectory "wire.pcapng"
$captureArguments = "-i `"$CaptureInterface`" -a duration:$CaptureDurationSeconds -q -w `"$capturePath`""
$capture = Start-Process -FilePath $TsharkPath -ArgumentList $captureArguments -PassThru -NoNewWindow
$script:CaptureProcess = $capture
Start-Sleep -Seconds 2
Assert-CaptureActive
Write-OperatorMarker -Event "CAPTURE_STARTED" -Detail "capture already active before cold attach"

try {
    Write-OperatorMarker -Event "COLD_ATTACH_BEGIN" -Detail "operator GUI action follows"
    Read-Host "Attach the existing 27c6:5125 USB device to the Windows VM using the reviewed VM GUI, then press Enter"
    Assert-CaptureActive
    Write-OperatorMarker -Event "COLD_ATTACH_END"
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $targets = @(Get-TargetDevices)
        if ($targets.Count -eq 1) { break }
        if ($targets.Count -gt 1) { Fail-D255 "target became ambiguous after attach" }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($targets.Count -ne 1) { Fail-D255 "target did not appear after cold attach" }
    Write-OperatorMarker -Event "TARGET_PRESENT" -Detail $targets[0].InstanceId

    Read-Host "Open the normal Windows Hello recognition prompt. Do not touch the sensor. Press Enter only when it is visibly waiting for a fingerprint"
    Assert-CaptureActive
    Write-OperatorMarker -Event "ARM_OBSERVED_NO_FINGER" -Detail "operator UI observation"
    Write-OperatorMarker -Event "CANCEL_NO_FINGER_BEGIN"
    Read-Host "Cancel the normal Windows Hello prompt without touching the sensor, then press Enter"
    Assert-CaptureActive
    Write-OperatorMarker -Event "CANCEL_NO_FINGER_END"

    Write-OperatorMarker -Event "REENTRY_BEGIN"
    Read-Host "Reopen the normal Windows Hello recognition prompt without touching the sensor, then press Enter when it is ready"
    Assert-CaptureActive
    Write-OperatorMarker -Event "REENTRY_READY_NO_FINGER" -Detail "operator UI observation"
    if ($AllowReentryFinger) {
        Write-OperatorMarker -Event "REENTRY_FINGER_BEGIN" -Detail "normal OEM recognition only"
        Read-Host "Only if no-finger re-entry was insufficient, complete one normal recognition event, then press Enter"
        Assert-CaptureActive
        Write-OperatorMarker -Event "REENTRY_FINGER_END"
    }
    Write-OperatorMarker -Event "REENTRY_END"
    Write-OperatorMarker -Event "OPERATOR_PHASES_COMPLETE"
    Wait-Process -Id $capture.Id
    if ($capture.ExitCode -ne 0) { Fail-D255 "capture process failed" }
    Write-OperatorMarker -Event "CAPTURE_STOPPED" -Detail "duration boundary reached"

    if (-not (Test-Path -LiteralPath $capturePath -PathType Leaf)) { Fail-D255 "capture output missing" }
    if ((Get-Item -LiteralPath $capturePath).Length -le 0) { Fail-D255 "capture output empty" }
    Copy-OemLogs -RawDirectory $rawDirectory
    Write-FileSnapshot -Stage "after" -Roots $cacheRoots -RawDirectory $rawDirectory | Out-Null
    Write-Manifest
    Write-Output "D255_CAPTURE_RESULT=CAPTURED_PENDING_OFFLINE_VALIDATION"
    Write-Output "D255_RUN_DIRECTORY=$script:RunDirectory"
    Write-Output "D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true"
} catch {
    Write-OperatorMarker -Event "RUN_FAILED" -Detail $_.Exception.Message
    if (-not $capture.HasExited) {
        Write-Warning "Capture remains bounded by its duration; no automatic hardware retry will occur."
    }
    throw
}
