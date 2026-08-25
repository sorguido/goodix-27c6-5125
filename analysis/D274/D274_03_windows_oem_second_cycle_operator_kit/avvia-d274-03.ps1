# SPDX-License-Identifier: GPL-2.0-or-later
# Launcher D274/03 compatibile con Windows PowerShell Desktop 5.1.
[CmdletBinding()]
param(
    [switch]$SelfTestOnly,
    [switch]$PreflightOnly,
    [switch]$PreAuthorizationSimulationOnly,
    [switch]$AutorizzoUnaSolaCatturaD27403
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$script:HostCaptureDeadlineSeconds = 180
$script:ExpectedTarget = "VID_27C6&PID_5125"

function Fail-D274([string]$Message) { throw "D274_03_FAIL_CLOSED: $Message" }

function Get-D274RepositoryRoot {
    $root = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>&1 | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0) { Fail-D274 "repository Git non individuabile" }
    return [System.IO.Path]::GetFullPath($root.Trim())
}

function Get-D274TsharkPath {
    $command = Get-Command tshark.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    $candidate = Join-Path $env:ProgramFiles "Wireshark\tshark.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return $null
}

function Get-D274UsbPcapInterfaces([string]$Tshark) {
    return @(& $Tshark -D 2>&1 | Where-Object { $_ -match "USBPcap" })
}

function Get-D274UsbPcapInterfaceSelector([string]$DiscoveryLine) {
    $match = [regex]::Match($DiscoveryLine, '^\s*(\d+)\.')
    if (-not $match.Success) { return $null }
    return $match.Groups[1].Value
}

function Test-D274PrivateOutputRoot([string]$Root, [string]$RepositoryRoot) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        New-Item -ItemType Directory -Path $Root -Force | Out-Null
    }
    $item = Get-Item -LiteralPath $Root -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
    $expected = [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot "captures\D274_03"))
    if ([System.IO.Path]::GetFullPath($item.FullName).TrimEnd("\").ToLower() -ne $expected.TrimEnd("\").ToLower()) { return $false }
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
    $probe = Join-Path $item.FullName (".d274-03-prova-{0}" -f [Guid]::NewGuid().ToString("N"))
    try {
        [System.IO.File]::WriteAllText($probe, "verifica-offline")
        return (Test-Path -LiteralPath $probe -PathType Leaf)
    } finally {
        if (Test-Path -LiteralPath $probe) { Remove-Item -LiteralPath $probe -Force }
    }
}

function Invoke-D274SelfTest {
    if ($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) {
        Fail-D274 "è richiesto Windows PowerShell Desktop 5.1"
    }
    $required = @(
        "invoke-d274-03-live-once.ps1", "collect-d274-03-results.ps1",
        "d274_03_postprocess_second_cycle.py", "d274_03_observe_second_b0.py",
        "run-d274-03-native-qualification.ps1",
        "collect-d274-03-native-qualification-results.ps1",
        "D274_03_evidence_schema.json",
        "D274_03_live_authority.json", "D274_03_OPERATOR_README_IT.md"
    )
    $missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $_) -PathType Leaf) })
    if ($missing.Count -ne 0) { Fail-D274 ("file mancanti: " + ($missing -join ", ")) }
    $authority = Get-Content -LiteralPath (Join-Path $PSScriptRoot "D274_03_live_authority.json") -Raw | ConvertFrom-Json
    if ($authority.baseline_approved -ne $false -or $authority.approved_for_capture -ne $false -or $authority.live_authorized -ne $false) {
        Fail-D274 "il template authority offline non è chiuso"
    }
    [ordered]@{
        schema = "D274_03_SELFTEST_V1"
        result = "PASS"
        operator_language = "ITALIAN"
        source_contains_future_live_path = $true
        live_path_executed = $false
        live_path_authorized = $false
        host_capture_deadline_seconds = $script:HostCaptureDeadlineSeconds
        automatic_retry_count = 0
        real_capture_count = 0
        real_usb_open_count = 0
        real_finger_interaction_count = 0
        real_goodix_command_count = 0
    } | ConvertTo-Json -Depth 4
}

function Invoke-D274Preflight {
    if ($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) {
        Fail-D274 "è richiesto Windows PowerShell Desktop 5.1"
    }
    $root = Get-D274RepositoryRoot
    $tshark = Get-D274TsharkPath
    if ($null -eq $tshark) { Fail-D274 "TShark non disponibile" }
    $version = & $tshark --version 2>&1 | Select-Object -First 1
    $interfaces = @(Get-D274UsbPcapInterfaces -Tshark $tshark)
    if ($interfaces.Count -ne 1) { Fail-D274 "interfaccia USBPcap assente o ambigua" }
    $interfaceSelector = Get-D274UsbPcapInterfaceSelector -DiscoveryLine ([string]$interfaces[0])
    if ($null -eq $interfaceSelector) { Fail-D274 "selector numerico USBPcap non ricavabile" }
    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) { Fail-D274 "Get-PnpDevice non disponibile" }
    $targets = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match $script:ExpectedTarget })
    if ($targets.Count -ne 0) { Fail-D274 "il target deve essere assente dal guest durante il preflight offline" }
    $captureRoot = Join-Path $root "captures\D274_03"
    if (-not (Test-D274PrivateOutputRoot -Root $captureRoot -RepositoryRoot $root)) {
        Fail-D274 "la radice capture privata non soddisfa il contratto ACL"
    }
    $authority = Get-Content -LiteralPath (Join-Path $PSScriptRoot "D274_03_live_authority.json") -Raw | ConvertFrom-Json
    [ordered]@{
        schema = "D274_03_PREFLIGHT_V1"
        result = "PASS"
        powershell_version = $PSVersionTable.PSVersion.ToString()
        tshark_path = $tshark
        tshark_version = [string]$version
        usbpcap_interface_count = $interfaces.Count
        usbpcap_interface_selector_valid = $true
        goodix_absent_from_guest = $true
        output_root_private = $true
        repository_root_resolved = $true
        host_capture_deadline_seconds = $script:HostCaptureDeadlineSeconds
        host_deadline_policy = "EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM"
        device_timeout_claim = "UNKNOWN"
        baseline_approved = [bool]$authority.baseline_approved
        approved_for_capture = [bool]$authority.approved_for_capture
        live_authorized = [bool]$authority.live_authorized
        real_capture_count = 0
        real_usb_open_count = 0
        real_goodix_command_count = 0
    } | ConvertTo-Json -Depth 4
}

function Invoke-D274PreAuthorizationSimulation {
    $authority = Get-Content -LiteralPath (Join-Path $PSScriptRoot "D274_03_live_authority.json") -Raw | ConvertFrom-Json
    if ($authority.baseline_approved -ne $false -or $authority.approved_for_capture -ne $false -or $authority.live_authorized -ne $false) {
        Fail-D274 "authority offline inattesa"
    }
    [ordered]@{
        schema = "D274_03_PREAUTHORIZATION_SIMULATION_V1"
        result = "PASS"
        authority_rejected_for_live = $true
        marker_created = $false
        authorization_consumed = $false
        source_contains_future_live_path = $true
        live_path_executed = $false
        live_path_authorized = $false
        enrollment_commit_authorized = $false
        account_mutation_authorized = $false
        pin_mutation_authorized = $false
        third_cycle_authorized = $false
        automatic_retry_count = 0
        real_capture_count = 0
        real_usb_open_count = 0
        real_finger_interaction_count = 0
        real_goodix_command_count = 0
    } | ConvertTo-Json -Depth 4
}

$selected = @(
    @($SelfTestOnly, $PreflightOnly, $PreAuthorizationSimulationOnly,
      $AutorizzoUnaSolaCatturaD27403) | Where-Object { $_ }
)
if ($selected.Count -ne 1) { Fail-D274 "selezionare esattamente una modalità" }

if ($SelfTestOnly) { Invoke-D274SelfTest; exit 0 }
if ($PreflightOnly) { Invoke-D274Preflight; exit 0 }
if ($PreAuthorizationSimulationOnly) { Invoke-D274PreAuthorizationSimulation; exit 0 }

# Il flag esplicito non è sufficiente: il runner applica authority, SHA/HEAD,
# live-critical set e marker single-use prima di avviare TShark.
$root = Get-D274RepositoryRoot
$tshark = Get-D274TsharkPath
if ($null -eq $tshark) { Fail-D274 "TShark non disponibile" }
$interfaces = @(Get-D274UsbPcapInterfaces -Tshark $tshark)
if ($interfaces.Count -ne 1) { Fail-D274 "interfaccia USBPcap assente o ambigua" }
$interfaceName = Get-D274UsbPcapInterfaceSelector -DiscoveryLine ([string]$interfaces[0])
if ($null -eq $interfaceName) { Fail-D274 "selector numerico USBPcap non ricavabile" }
& (Join-Path $PSScriptRoot "invoke-d274-03-live-once.ps1") `
    -RepositoryRoot $root `
    -AuthorityPath (Join-Path $PSScriptRoot "D274_03_live_authority.json") `
    -TsharkPath $tshark `
    -UsbPcapInterface $interfaceName
exit $LASTEXITCODE
