# SPDX-License-Identifier: GPL-2.0-or-later
# D274/02 OFFLINE / PRELIVE operator wrapper. Native Windows PowerShell 5.1 only.
#
# This script does NOT perform any real capture, USB attach, finger prompt,
# enrollment, credential/PIN/account mutation, or persistent device write.
# It runs only the three harmless D274/01 modes (-SelfTestOnly, -PreflightOnly,
# -PreAuthorizationSimulationOnly) plus native read-only safety gating, and
# produces machine-readable evidence for the operator to return to AI-PM.
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$script:D274RealCaptureCapability = 0
$script:D274HardDisabled = $true
$script:ExpectedTarget = "VID_27C6&PID_5125"
$script:ActiveMarkerName = "D274_ACTIVE.marker"
$script:RealCaptureStartCount = 0
$script:RealUsbOpenCount = 0
$script:HardwareActionCount = 0

$PackageRoot = $PSScriptRoot
$KitPath = Join-Path $PackageRoot "operator_kit\d274-windows-multiframe-evidence.ps1"

# Single authority for the captures root: the package-local captures/ directory.
# The copied D274/01 kit resolves its own canonical captures root as
# <parent of operator_kit>/captures = <package>/captures, i.e. the same location.
$CapturesRoot = [System.IO.Path]::GetFullPath((Join-Path $PackageRoot "captures"))
$ResultsDir = Join-Path $PackageRoot "results"
if (-not (Test-Path -LiteralPath $ResultsDir -PathType Container)) {
    New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null
}

# Canonical capture-root authority used for both the wrapper self-check and the
# kit-alignment assertion. There is exactly ONE expected path.
$ExpectedCapturesRoot = [System.IO.Path]::GetFullPath((Join-Path $PackageRoot "captures"))

function Fail-D274([string]$Message) {
    throw "D274_02_FAIL_CLOSED: $Message"
}

# Centralized sanitization of any error/evidence string before it is written to a
# core result JSON. No raw package path, no raw user path, no SID/MAC/IP.
function Sanitize-String([string]$Text) {
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    $out = $Text
    $out = $out.Replace($PackageRoot, "<PACKAGE_ROOT>")
    $out = [regex]::Replace($out, 'C:\\Users\\[^\\]+', "<USER_PATH>")
    $out = [regex]::Replace($out, '[A-Za-z]:\\Users\\[^\\]+', "<USER_PATH>")
    $out = [regex]::Replace($out, '\\Users\\[^\\]+\\', "\<USER_PATH>\")
    $out = [regex]::Replace($out, 'S-1-\d[\d-]*', "<SID>")
    $out = [regex]::Replace($out, '\b[0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}\b', "<MAC>")
    $out = [regex]::Replace($out, '\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', "<IP>")
    return $out
}

# Accepts PSCustomObject (from ConvertFrom-Json), [ordered]/hashtable, or any
# serializable object. Compatible with Windows PowerShell 5.1; deliberately does
# NOT rely on the Windows PowerShell 5.1-unsupported AsHashtable switch.
function Write-D274JsonResult([string]$FileName, [object]$Object) {
    $path = Join-Path $ResultsDir $FileName
    $Object | ConvertTo-Json -Depth 6 -Compress:$false | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Write-SkippedResult([string]$FileName, [string]$Schema, [string]$Because) {
    Write-D274JsonResult $FileName ([ordered]@{
        schema = $Schema
        result = "SKIPPED"
        skipped_because = $Because
    })
}

# Records the FIRST failure only (authority): overall result, stage and a
# sanitized detail. Later failures never overwrite the first.
function Register-FirstFailure([string]$Stage, [string]$Message) {
    $script:overallResult = "FAIL"
    if ($null -eq $script:failedStage) { $script:failedStage = $Stage }
    if ($null -eq $script:failureDetail) { $script:failureDetail = (Sanitize-String $Message) }
}

# Builds a sanitized, bounded FAIL object from a subprocess result. Uses stderr
# if present, else stdout, then sanitizes and truncates to <= 2048 chars.
function New-D274SubprocessFailure([string]$Schema, [object]$Result) {
    $exitCode = 0
    $stdout = ""
    $stderr = ""
    if ($null -ne $Result) {
        $exitCode = $Result.exit_code
        $stdout = $Result.stdout
        $stderr = $Result.stderr
    }
    $raw = $stderr
    if ([string]::IsNullOrWhiteSpace($raw)) { $raw = $stdout }
    if ([string]::IsNullOrWhiteSpace($raw)) { $raw = ("exit_code " + $exitCode) }
    $bounded = $raw
    if ($null -ne $bounded -and $bounded.Length -gt 2048) { $bounded = $bounded.Substring(0, 2048) }
    return [ordered]@{
        schema = $Schema
        result = "FAIL"
        exit_code = $exitCode
        error_sanitized = (Sanitize-String $bounded)
    }
}

function Assert-WindowsPowerShell51 {
    if ($PSVersionTable.PSEdition -ne "Desktop") {
        Fail-D274 "requires Windows PowerShell Desktop edition (not PowerShell Core)"
    }
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) {
        Fail-D274 "requires Windows PowerShell 5.1"
    }
}

function Invoke-D274Subprocess([string]$ModeSwitch) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$KitPath`" $ModeSwitch"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    return [ordered]@{
        stdout = $stdout
        stderr = $stderr
        exit_code = $proc.ExitCode
    }
}

# Observes (does not gate) whether the Goodix target is present. Returns a boolean
# truth value, or throws if presence is not determinable. The caller decides the
# gate so that goodix_present_before_run is never a false negative/positive.
function Get-D274GoodixPresence {
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D274 "Get-PnpDevice unavailable; cannot determine Goodix presence"
    }
    $targets = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match $script:ExpectedTarget })
    return ($targets.Count -ne 0)
}

function Test-D274NoActiveMarker {
    $marker = Join-Path $CapturesRoot $script:ActiveMarkerName
    if (Test-Path -LiteralPath $marker) {
        Fail-D274 "active D274 marker present; offline qualification must not proceed"
    }
    return $true
}

function Get-D274TsharkDiscovery {
    $command = Get-Command tshark.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { $rawPath = $command.Source } else { $rawPath = $null }
    $tsharkPath = $null
    $tsharkVersion = $null
    $usbpcapCount = 0
    if ($null -ne $rawPath) {
        if ($rawPath -match "Wireshark") {
            $tsharkPath = "<PROGRAMFILES>/Wireshark/tshark.exe"
        } else {
            $tsharkPath = "<SYSTEM_PATH>/tshark.exe"
        }
        try {
            $ver = & $rawPath --version 2>&1 | Select-Object -First 1
            $tsharkVersion = [string]$ver
        } catch { $tsharkVersion = $null }
        try {
            $ifaces = @(& $rawPath -D 2>&1 | Where-Object { $_ -match "USBPcap" })
            $usbpcapCount = $ifaces.Count
        } catch { $usbpcapCount = 0 }
    }
    return [ordered]@{
        tshark_path = $tsharkPath
        tshark_version = $tsharkVersion
        usbpcap_interfaces_count = $usbpcapCount
    }
}

function Test-D274KitSourceContract {
    # Read-only source scan of the approved baseline kit. It must contain no
    # capture-start TShark arguments and no process spawn that could start a
    # real capture or attach hardware.
    $content = [System.IO.File]::ReadAllText($KitPath)
    $forbiddenCaptureArgs = @('-i\s', '-w\s', '-f\s', '-Y\s')
    foreach ($token in $forbiddenCaptureArgs) {
        if ($content -match $token) {
            Fail-D274 "kit source scan found forbidden capture argument token: $token"
        }
    }
    if ($content -match "Start-Process") {
        Fail-D274 "kit source scan found Start-Process"
    }
    if ($content -notmatch "HARD_DISABLED_D274_01") {
        Fail-D274 "kit source scan missing source hard-disable invariant"
    }
    return $true
}

# Read-only package integrity verification against the static manifest. The
# manifest records SHA-256 of the five static package files and the approved
# D274/01 baseline kit hash. This is a read-only gate; it never writes.
function Test-D274PackageIntegrity {
    $manifestPath = Join-Path $PackageRoot "D274_02_operator_package_integrity.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Fail-D274 "operator package integrity manifest missing"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($null -eq $manifest.files) { Fail-D274 "integrity manifest missing files list" }
    foreach ($entry in $manifest.files) {
        $full = Join-Path $PackageRoot $entry.path
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
            Fail-D274 ("integrity: missing file " + $entry.path)
        }
        $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $full).Hash
        if ($h -ne $entry.sha256) {
            Fail-D274 ("integrity: hash mismatch for " + $entry.path)
        }
    }
    $kitEntry = $manifest.approved_d274_01_baseline_sha256."operator_kit/d274-windows-multiframe-evidence.ps1"
    $kitActual = (Get-FileHash -Algorithm SHA256 -LiteralPath $KitPath).Hash
    if ($kitActual -ne $kitEntry) {
        Fail-D274 "integrity: approved D274/01 kit baseline hash mismatch"
    }
    return [ordered]@{
        integrity = "PASS"
        manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash
        approved_d274_01_kit_sha256 = $kitActual
    }
}

function Get-D274NativeAclMetadata {
    # Read-only ACL privacy metadata collection. Never mutates ACLs, junctions
    # or symlinks. Exports only sanitized booleans. Uses the single canonical
    # captures-root authority (package/captures), aligned with the copied kit.
    $item = Get-Item -LiteralPath $CapturesRoot -ErrorAction Stop
    $resolved = [System.IO.Path]::GetFullPath($item.FullName)
    $canonicalMatch = ($resolved.TrimEnd("\").TrimEnd("/").ToLower() -eq $ExpectedCapturesRoot.TrimEnd("\").TrimEnd("/").ToLower())
    $reparsePoint = (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
    $acl = $null
    $aclReadable = $false
    $broadEveryone = $false
    $broadBuiltinUsers = $false
    $broadAuthenticated = $false
    $broadGuests = $false
    try {
        $acl = Get-Acl -Path $resolved -ErrorAction Stop
        $aclReadable = $true
        $wellKnown = @{
            "S-1-1-0"   = ([ref]$broadEveryone)
            "S-1-5-32-545" = ([ref]$broadBuiltinUsers)
            "S-1-5-11"  = ([ref]$broadAuthenticated)
            "S-1-5-32-546" = ([ref]$broadGuests)
        }
        $badRights = ([System.Security.AccessControl.FileSystemRights]::Read) -bor
                     ([System.Security.AccessControl.FileSystemRights]::Write) -bor
                     ([System.Security.AccessControl.FileSystemRights]::Modify) -bor
                     ([System.Security.AccessControl.FileSystemRights]::FullControl)
        foreach ($ace in $acl.Access) {
            if ($ace.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { continue }
            if (($ace.FileSystemRights -band $badRights) -eq 0) { continue }
            try {
                $sid = $ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier])
            } catch { continue }
            if ($wellKnown.ContainsKey($sid.Value)) {
                $ref = $wellKnown[$sid.Value]
                $ref.Value = $true
            }
        }
    } catch { $aclReadable = $false }
    return [ordered]@{
        canonical_capture_root_match = $canonicalMatch
        reparse_point = $reparsePoint
        acl_readable = $aclReadable
        broad_everyone_read_or_stronger = $broadEveryone
        broad_builtin_users_read_or_stronger = $broadBuiltinUsers
        broad_authenticated_users_read_or_stronger = $broadAuthenticated
        broad_guests_read_or_stronger = $broadGuests
        write_probe_pass = $null
    }
}

function Test-D274HardDisableAdversarial {
    # Run the baseline kit with the nominal authorization flag in a SEPARATE
    # subprocess. PASS only if it exits non-zero, emits the expected
    # hard-disable message, starts no capture and performs no hardware action.
    $result = Invoke-D274Subprocess "-IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture"
    $combined = "$($result.stdout)`n$($result.stderr)"
    $observedMessage = ($combined -match "HARD_DISABLED_D274_01")
    $hardwareAction = ($combined -match "VM_USB_ATTACH|tshark.*-i |capture started")
    $passed = ($result.exit_code -ne 0) -and $observedMessage -and (-not $hardwareAction)
    return [ordered]@{
        schema = "D274_02_HARD_DISABLE_ADVERSARIAL_V1"
        result = $(if ($passed) { "PASS" } else { "FAIL" })
        subprocess_exit_code = $result.exit_code
        expected_hard_disable_message_observed = $observedMessage
        no_capture_started = (-not $hardwareAction)
        no_hardware_action = (-not $hardwareAction)
        d274_real_capture_capability = 0
        d274_hard_disabled = $true
        authorization_consumed = $false
        note = "This is a safety gate, not a live authorization."
    }
}

# ---------------------------------------------------------------------------
# Main qualification flow
# ---------------------------------------------------------------------------

$stages = [ordered]@{}
$overallResult = "PASS"
$failedStage = $null
$failureDetail = $null
$goodixPresentBeforeRun = $null
$aclBehaviorTest = "NOT_YET_EXECUTED"
$adversarialTest = "NOT_YET_EXECUTED"
$aclMetadata = $null
$integrity = $null
$safetyPreGatePassed = $false

try {
    Assert-WindowsPowerShell51
    $stages["assert_windows_powershell_51"] = "PASS"

    $integrity = Test-D274PackageIntegrity
    $stages["package_integrity"] = "PASS"

    Test-D274KitSourceContract | Out-Null
    $stages["kit_source_contract"] = "PASS"

    # Observation first; gate second. If undeterminable, goodix_present_before_run
    # stays null (never a false negative).
    $goodixPresentBeforeRun = Get-D274GoodixPresence
    if ($goodixPresentBeforeRun) {
        Fail-D274 "FAIL_CLOSED_GOODIX_PRESENT_BEFORE_OFFLINE_QUALIFICATION"
    }
    $stages["goodix_absence_gate"] = "PASS"

    Test-D274NoActiveMarker | Out-Null
    $stages["no_active_marker_gate"] = "PASS"

    $safetyPreGatePassed = $true
} catch {
    Register-FirstFailure "pre_gate" $_.Exception.Message
    $stages["pre_gate"] = "FAIL"
}

# SelfTestOnly
if ($overallResult -eq "PASS") {
    $r = $null
    try {
        $r = Invoke-D274Subprocess "-SelfTestOnly"
        if ($r.exit_code -ne 0) { throw ("self-test exit " + $r.exit_code) }
        Write-D274JsonResult "D274_02_selftest.json" ($r.stdout | ConvertFrom-Json)
        $stages["selftest"] = "PASS"
    } catch {
        Register-FirstFailure "selftest" $_.Exception.Message
        Write-D274JsonResult "D274_02_selftest.json" (New-D274SubprocessFailure "D274_POWERSHELL_SELFTEST_V1" $r)
    }
} else {
    $stages["selftest"] = "SKIPPED"
    Write-SkippedResult "D274_02_selftest.json" "D274_POWERSHELL_SELFTEST_V1" $failedStage
}

# PreflightOnly
if ($overallResult -eq "PASS") {
    $r = $null
    try {
        $r = Invoke-D274Subprocess "-PreflightOnly"
        if ($r.exit_code -ne 0) { throw ("preflight exit " + $r.exit_code) }
        $preflightObj = $r.stdout | ConvertFrom-Json
        # Sanitize imported kit evidence: the absolute output_root must not leak
        # the operator package location (e.g. a user-profile path). The semantic
        # facts (writable, privacy, counts, version) are preserved.
        $preflightObj.output_root = "<PACKAGE_ROOT>\captures"
        if ($preflightObj.PSObject.Properties.Match("tshark_path")) {
            $preflightObj.tshark_path = (Sanitize-String $preflightObj.tshark_path)
        }
        Write-D274JsonResult "D274_02_preflight.json" $preflightObj
        $stages["preflight"] = "PASS"
    } catch {
        Register-FirstFailure "preflight" $_.Exception.Message
        Write-D274JsonResult "D274_02_preflight.json" (New-D274SubprocessFailure "D274_WINDOWS_PREFLIGHT_V1" $r)
    }
} else {
    $stages["preflight"] = "SKIPPED"
    Write-SkippedResult "D274_02_preflight.json" "D274_WINDOWS_PREFLIGHT_V1" $failedStage
}

# PreAuthorizationSimulationOnly
if ($overallResult -eq "PASS") {
    $r = $null
    try {
        $r = Invoke-D274Subprocess "-PreAuthorizationSimulationOnly"
        if ($r.exit_code -ne 0) { throw ("preauth-simulation exit " + $r.exit_code) }
        Write-D274JsonResult "D274_02_preauthorization_simulation.json" ($r.stdout | ConvertFrom-Json)
        $stages["preauthorization_simulation"] = "PASS"
    } catch {
        Register-FirstFailure "preauthorization_simulation" $_.Exception.Message
        Write-D274JsonResult "D274_02_preauthorization_simulation.json" (New-D274SubprocessFailure "D274_PREAUTHORIZATION_SIMULATION_V1" $r)
    }
} else {
    $stages["preauthorization_simulation"] = "SKIPPED"
    Write-SkippedResult "D274_02_preauthorization_simulation.json" "D274_PREAUTHORIZATION_SIMULATION_V1" $failedStage
}

# Native ACL behavior test (observable from the preflight evidence plus a
# read-only wrapper metadata collection). Fail-closed; never mutates ACLs.
try {
    $aclMeta = Get-D274NativeAclMetadata
    if ($stages.Contains("preflight") -and $stages["preflight"] -eq "PASS") {
        $preflightJson = Get-Content -LiteralPath (Join-Path $ResultsDir "D274_02_preflight.json") -Raw | ConvertFrom-Json
        $aclMeta.write_probe_pass = ($preflightJson.output_root_private_writable -eq $true)
        $preflightPrivacyOk = ($preflightJson.output_root_privacy -eq "PASS_PRIVATE_CONTRACT")
    } else {
        $aclMeta.write_probe_pass = $false
        $preflightPrivacyOk = $false
    }
    $aclPass = (-not $aclMeta.reparse_point) -and $aclMeta.acl_readable -and
               (-not $aclMeta.broad_everyone_read_or_stronger) -and
               (-not $aclMeta.broad_builtin_users_read_or_stronger) -and
               (-not $aclMeta.broad_authenticated_users_read_or_stronger) -and
               (-not $aclMeta.broad_guests_read_or_stronger) -and
               $aclMeta.canonical_capture_root_match -and $preflightPrivacyOk
    $aclBehaviorTest = $(if ($aclPass) { "PASS" } else { "FAIL" })
    if ($aclPass -eq $false -and $overallResult -eq "PASS") {
        $overallResult = "FAIL"; if ($null -eq $failedStage) { $failedStage = "acl_behavior" }
    }
    $script:aclMetadata = $aclMeta
} catch {
    $aclBehaviorTest = "FAIL"
    Register-FirstFailure "acl_behavior" $_.Exception.Message
}

# Hard-disable adversarial test (safety gate). It runs only when the safety
# pre-gate passed; otherwise it is recorded as SKIPPED (not executed).
if ($safetyPreGatePassed) {
    try {
        $adv = Test-D274HardDisableAdversarial
        Write-D274JsonResult "D274_02_hard_disable_adversarial.json" $adv
        $adversarialTest = $adv.result
        if ($adv.result -ne "PASS" -and $overallResult -eq "PASS") {
            $overallResult = "FAIL"; if ($null -eq $failedStage) { $failedStage = "hard_disable_adversarial" }
        }
    } catch {
        $adversarialTest = "FAIL"
        Register-FirstFailure "hard_disable_adversarial" $_.Exception.Message
        Write-D274JsonResult "D274_02_hard_disable_adversarial.json" ([ordered]@{
            schema = "D274_02_HARD_DISABLE_ADVERSARIAL_V1"; result = "FAIL"
            error_sanitized = (Sanitize-String $_.Exception.Message)
        })
    }
} else {
    $stages["hard_disable_adversarial"] = "SKIPPED"
    Write-SkippedResult "D274_02_hard_disable_adversarial.json" "D274_02_HARD_DISABLE_ADVERSARIAL_V1" $failedStage
}

# Environment evidence (no sensitive metadata). Integrity-derived fields only;
# the static manifest hash is exported instead of an overclaimed package hash.
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $osCaption = $os.Caption
    $osVersion = $os.Version
    $osBuild = $os.BuildNumber
} catch {
    $osCaption = $null; $osVersion = $null; $osBuild = $null
}
$tshark = Get-D274TsharkDiscovery
$pythonStatus = "NOT_FOUND"
if (Get-Command python.exe -ErrorAction SilentlyContinue) { $pythonStatus = "FOUND" }
elseif (Get-Command py.exe -ErrorAction SilentlyContinue) { $pythonStatus = "FOUND" }
elseif (Get-Command python3.exe -ErrorAction SilentlyContinue) { $pythonStatus = "FOUND" }
$envEvidence = [ordered]@{
    schema = "D274_02_ENVIRONMENT_V1"
    os_caption = $osCaption
    os_version = $osVersion
    os_build = $osBuild
    powershell_edition = $PSVersionTable.PSEdition
    powershell_version = $PSVersionTable.PSVersion.ToString()
    tshark_path = $tshark.tshark_path
    tshark_version = $tshark.tshark_version
    usbpcap_interfaces_count = $tshark.usbpcap_interfaces_count
    python_command_status = $pythonStatus
    operator_package_integrity = $(if ($null -ne $integrity) { $integrity.integrity } else { "NOT_VERIFIED" })
    operator_package_manifest_sha256 = $(if ($null -ne $integrity) { $integrity.manifest_sha256 } else { $null })
    approved_d274_01_kit_sha256 = $(if ($null -ne $integrity) { $integrity.approved_d274_01_kit_sha256 } else { $null })
    goodix_present_before_run = $goodixPresentBeforeRun
    current_utc = [DateTimeOffset]::UtcNow.ToString("o")
}
Write-D274JsonResult "D274_02_environment.json" $envEvidence

# Summary (runtime result state). Declares the offline qualification was
# executed by the operator with no live capture; it is NOT a "pending" note.
$summary = [ordered]@{
    schema = "D274_02_NATIVE_QUALIFICATION_SUMMARY_V1"
    runtime_result_state = "WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR"
    result = $overallResult
    failed_stage = $failedStage
    failure_detail_sanitized = $failureDetail
    stages = $stages
    goodix_present_before_run = $goodixPresentBeforeRun
    windows_native_acl_behavior_test = $aclBehaviorTest
    acl_behavior_metadata = $script:aclMetadata
    d274_native_hard_disable_adversarial_test = $adversarialTest
    real_capture_start_count = $script:RealCaptureStartCount
    real_usb_open_count = $script:RealUsbOpenCount
    hardware_action_count = $script:HardwareActionCount
    d274_real_capture_capability = $script:D274RealCaptureCapability
    d274_hard_disabled = $script:D274HardDisabled
    live_authorized = $false
    ready_for_live = $false
    note = "WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR; NO_LIVE_CAPTURE_PERFORMED; d274_real_capture_capability=0"
}
Write-D274JsonResult "D274_02_native_qualification_summary.json" $summary

if ($overallResult -ne "PASS") {
    Write-Error "D274/02 native qualification FAILED at stage: $failedStage"
    exit 1
}
exit 0
