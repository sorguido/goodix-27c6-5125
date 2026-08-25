# SPDX-License-Identifier: GPL-2.0-or-later
# D274/01 OFFLINE PRELIVE ONLY. Real capture is source-hard-disabled.
[CmdletBinding()]
param(
    [switch]$SelfTestOnly,
    [switch]$PreflightOnly,
    [switch]$PreAuthorizationSimulationOnly,
    [switch]$IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$script:D274RealCaptureCapability = 0
$script:D274HardDisabled = $true
$script:HostCaptureDeadlineSeconds = 180
$script:ExpectedTarget = "VID_27C6&PID_5125"
$script:MarkerOrder = @(
    "PREFLIGHT_COMPLETE", "CAPTURE_PROCESS_STARTED", "VM_USB_ATTACH_BEGIN",
    "VM_USB_ATTACH_END", "TARGET_APP12509_CONFIRMED", "OEM_UI_READY",
    "FIRST_FINGER_PROMPT", "FIRST_FINGER_DOWN_OPERATOR_CONFIRMED",
    "FIRST_FINGER_UP_OPERATOR_CONFIRMED", "SECOND_FINGER_PROMPT",
    "SECOND_FINGER_DOWN_OPERATOR_CONFIRMED", "SECOND_B0_OBSERVED",
    "CAPTURE_STOP_REQUESTED", "CAPTURE_PROCESS_STOPPED", "OFFLINE_VALIDATION_PENDING"
)

function Fail-D274([string]$Message) {
    throw "D274_FAIL_CLOSED: $Message"
}

function Get-D274RepositoryRoot {
    return [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
}

function Test-D274MarkerOrder([string[]]$Markers) {
    $previous = -1
    foreach ($marker in $Markers) {
        $index = [Array]::IndexOf($script:MarkerOrder, $marker)
        if ($index -lt 0 -or $index -le $previous) { return $false }
        $previous = $index
    }
    return $true
}

function Get-D274TsharkPath {
    $command = Get-Command tshark.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    $candidate = Join-Path $env:ProgramFiles "Wireshark\tshark.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return $null
}

function Test-D274PrivateOutputRoot([string]$Root) {
    # Fail-closed privacy contract for the future fingerprint-raw destination.
    # A writable root is NOT sufficient: it must also be private. This check
    # never mutates ACLs, junctions or symlinks (D274/01 stays pre-live).
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        New-Item -ItemType Directory -Path $Root -Force | Out-Null
    }
    $item = Get-Item -LiteralPath $Root -ErrorAction Stop
    $resolved = $item.FullName
    # Reparse points, junctions and symlinks are not accepted as private roots.
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        return $false
    }
    # Canonical location: <repository-root>\captures exactly.
    $repository = Get-D274RepositoryRoot
    $expected = Join-Path $repository "captures"
    if ($resolved.TrimEnd("\").ToLower() -ne $expected.TrimEnd("\").ToLower()) {
        return $false
    }
    # ACL must be evaluable and must not grant read/write/modify/full-control to
    # generic well-known principals. Host administrative principals (SYSTEM,
    # Administrators) and the current user remain allowed per host policy. The
    # Read right is included because ReadAndExecute/ReadData are granted through
    # it; the band check therefore intercepts them too. Identity is normalized to
    # a SID so the check is robust on localized Windows builds. A SID
    # translation failure is fail-closed (the root is not accepted as private).
    $acl = $null
    try { $acl = Get-Acl -Path $resolved -ErrorAction Stop } catch { return $false }
    if ($null -eq $acl) { return $false }
    $wellKnownSids = @(
        "S-1-1-0",       # Everyone
        "S-1-5-32-545",  # BUILTIN\Users
        "S-1-5-11",      # Authenticated Users
        "S-1-5-32-546"   # Guests
    )
    $badRights = ([System.Security.AccessControl.FileSystemRights]::Read) -bor
                 ([System.Security.AccessControl.FileSystemRights]::Write) -bor
                 ([System.Security.AccessControl.FileSystemRights]::Modify) -bor
                 ([System.Security.AccessControl.FileSystemRights]::FullControl)
    foreach ($ace in $acl.Access) {
        if ($ace.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { continue }
        if (($ace.FileSystemRights -band $badRights) -eq 0) { continue }
        try {
            $sid = $ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier])
        } catch {
            return $false  # FAIL_CLOSED: SID translation failed
        }
        if ($wellKnownSids -contains $sid.Value) { return $false }
    }
    $probe = Join-Path $resolved (".d274-write-probe-{0}" -f [Guid]::NewGuid().ToString("N"))
    try {
        [System.IO.File]::WriteAllText($probe, "offline-preflight")
        return (Test-Path -LiteralPath $probe -PathType Leaf)
    } finally {
        if (Test-Path -LiteralPath $probe) { Remove-Item -LiteralPath $probe -Force }
    }
}

function Invoke-D274SelfTest {
    if ($PSVersionTable.PSVersion.Major -lt 5) { Fail-D274 "PowerShell 5.1 compatibility gate failed" }
    if ($script:D274RealCaptureCapability -ne 0 -or -not $script:D274HardDisabled) {
        Fail-D274 "source hard-disable invariant failed"
    }
    if (-not (Test-D274MarkerOrder -Markers $script:MarkerOrder)) {
        Fail-D274 "marker lifecycle contract failed"
    }
    if (Test-D274MarkerOrder -Markers @("VM_USB_ATTACH_END", "VM_USB_ATTACH_BEGIN")) {
        Fail-D274 "out-of-order marker fixture accepted"
    }
    [ordered]@{
        schema = "D274_POWERSHELL_SELFTEST_V1"
        result = "PASS"
        powershell_5_1_compatible_surface = $true
        d274_real_capture_capability = 0
        d274_hard_disabled = $true
        marker_lifecycle = "PASS"
        host_capture_deadline_seconds = $script:HostCaptureDeadlineSeconds
        hardware_action_count = 0
        capture_start_count = 0
        finger_prompt_count = 0
    } | ConvertTo-Json -Depth 4
}

function Invoke-D274PreAuthorizationSimulation {
    $synthetic = @(
        "PREFLIGHT_COMPLETE", "CAPTURE_PROCESS_STARTED", "VM_USB_ATTACH_BEGIN",
        "VM_USB_ATTACH_END", "TARGET_APP12509_CONFIRMED", "OEM_UI_READY",
        "FIRST_FINGER_PROMPT", "FIRST_FINGER_DOWN_OPERATOR_CONFIRMED",
        "FIRST_FINGER_UP_OPERATOR_CONFIRMED", "SECOND_FINGER_PROMPT",
        "SECOND_FINGER_DOWN_OPERATOR_CONFIRMED", "SECOND_B0_OBSERVED",
        "CAPTURE_STOP_REQUESTED", "CAPTURE_PROCESS_STOPPED", "OFFLINE_VALIDATION_PENDING"
    )
    if (-not (Test-D274MarkerOrder -Markers $synthetic)) {
        Fail-D274 "synthetic lifecycle rejected"
    }
    [ordered]@{
        schema = "D274_PREAUTHORIZATION_SIMULATION_V1"
        result = "PASS"
        fixture = "SYNTHETIC_MARKERS_ONLY_NO_PACKET_EVIDENCE_CLAIM"
        authorization_consumed = $false
        real_capture_started = $false
        real_usb_open_count = 0
        real_finger_interaction_count = 0
        enrollment_commit_authorized = $false
        account_mutation_authorized = $false
        pin_mutation_authorized = $false
    } | ConvertTo-Json -Depth 4
}

function Invoke-D274Preflight {
    $root = Get-D274RepositoryRoot
    $captureRoot = Join-Path $root "captures"
    $postprocessor = Join-Path $root "analysis\D274\d274_postprocess_multiframe_evidence.py"
    $conflictMarker = Join-Path $captureRoot "D274_ACTIVE.marker"
    $tshark = Get-D274TsharkPath
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) {
        Fail-D274 "Windows PowerShell 5.1 is required"
    }
    if ($null -eq $tshark) { Fail-D274 "TShark is unavailable" }
    $version = & $tshark --version 2>&1 | Select-Object -First 1
    $interfaces = @(& $tshark -D 2>&1 | Where-Object { $_ -match "USBPcap" })
    if ($interfaces.Count -lt 1) { Fail-D274 "USBPcap interface discovery failed" }
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        Fail-D274 "Get-PnpDevice unavailable"
    }
    $targets = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match $script:ExpectedTarget })
    if ($targets.Count -ne 0) { Fail-D274 "Goodix must be absent from guest before capture" }
    if (-not (Test-D274PrivateOutputRoot -Root $captureRoot)) {
        Fail-D274 "private output root privacy/accessibility contract failed"
    }
    if (Test-Path -LiteralPath $conflictMarker) { Fail-D274 "conflicting D274 marker exists" }
    if (-not (Test-Path -LiteralPath $postprocessor -PathType Leaf)) {
        Fail-D274 "offline postprocessor unavailable"
    }
    $utc = [DateTimeOffset]::UtcNow.ToString("o")
    if ([DateTimeOffset]::Parse($utc).Offset -ne [TimeSpan]::Zero) { Fail-D274 "UTC marker failed" }
    [ordered]@{
        schema = "D274_WINDOWS_PREFLIGHT_V1"
        result = "PASS"
        powershell = $PSVersionTable.PSVersion.ToString()
        tshark_path = $tshark
        tshark_version = [string]$version
        usbpcap_interface_count = $interfaces.Count
        goodix_absent_from_guest_before_capture = $true
        single_target_after_attach_gate = "DEFINED_NOT_EXECUTED_PRELIVE"
        output_root = $captureRoot
        output_root_private_writable = $true
        output_root_privacy = "PASS_PRIVATE_CONTRACT"
        conflicting_marker = $false
        utc_marker = $utc
        host_capture_deadline_seconds = $script:HostCaptureDeadlineSeconds
        host_deadline_policy = "EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM"
        device_timeout_claim = "UNKNOWN"
        postprocessor_available = $true
        sensor_dependent_ui_availability = "UNKNOWN_BEFORE_ATTACH"
        authorization_consumed = $false
        hardware_action_count = 0
    } | ConvertTo-Json -Depth 5
}

$selected = @($SelfTestOnly, $PreflightOnly, $PreAuthorizationSimulationOnly,
              $IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture) |
    Where-Object { $_ }
if ($selected.Count -ne 1) { Fail-D274 "select exactly one mode" }

if ($IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture) {
    # This is intentionally before TShark discovery, USB attach, any prompt or
    # any hardware-affecting action. No flag, environment or config bypasses it.
    Fail-D274 "HARD_DISABLED_D274_01; D274_REAL_CAPTURE_CAPABILITY=0"
}
if ($SelfTestOnly) { Invoke-D274SelfTest; exit 0 }
if ($PreflightOnly) { Invoke-D274Preflight; exit 0 }
if ($PreAuthorizationSimulationOnly) { Invoke-D274PreAuthorizationSimulation; exit 0 }
