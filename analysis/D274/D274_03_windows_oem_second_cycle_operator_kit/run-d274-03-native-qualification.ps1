# SPDX-License-Identifier: GPL-2.0-or-later
# Qualificazione OFFLINE innocua D274/03 per Windows PowerShell Desktop 5.1.
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$PackageRoot = $PSScriptRoot
$Launcher = Join-Path $PackageRoot "avvia-d274-03.ps1"
$Runner = Join-Path $PackageRoot "invoke-d274-03-live-once.ps1"
$Authority = Join-Path $PackageRoot "D274_03_live_authority.json"
$ResultsDir = Join-Path $PackageRoot "native_qualification_results"
$ExpectedTarget = "VID_27C6&PID_5125"
$CaptureRoot = $null
$stages = [ordered]@{}
$failedStage = $null
$failureDetail = $null
$overall = "PASS"
$preflightJson = $null
$targets = $null

function Fail-D274Native([string]$Message) { throw "D274_03_NATIVE_FAIL_CLOSED: $Message" }

function Sanitize-D274([string]$Text) {
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    $value = $Text.Replace($PackageRoot, "<PACKAGE_ROOT>")
    $value = [regex]::Replace($value, '[A-Za-z]:\\Users\\[^\\]+', '<USER_PATH>')
    $value = [regex]::Replace($value, 'S-1-\d[\d-]*', '<SID>')
    if ($value.Length -gt 2048) { $value = $value.Substring(0, 2048) }
    return $value
}

function Invoke-D274PowerShell([string]$File, [string]$Arguments) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$File`" $Arguments"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $process = [System.Diagnostics.Process]::Start($psi)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    return [ordered]@{exit_code=$process.ExitCode; stdout=$stdout; stderr=$stderr}
}

function Assert-D274Pass([bool]$Condition, [string]$Message) {
    if (-not $Condition) { Fail-D274Native $Message }
}

function Get-D274ArtifactCounts {
    if ($null -eq $CaptureRoot -or -not (Test-Path -LiteralPath $CaptureRoot -PathType Container)) {
        return [ordered]@{pcapng=0; one_shot_marker=0}
    }
    return [ordered]@{
        pcapng = @(Get-ChildItem -LiteralPath $CaptureRoot -Recurse -File -Filter "*.pcapng" -ErrorAction Stop).Count
        one_shot_marker = @(Get-ChildItem -LiteralPath $CaptureRoot -Recurse -File -Filter "D274_03_ONE_SHOT_CONSUMED.marker" -ErrorAction Stop).Count
    }
}

function Get-D274Tshark {
    $command = Get-Command tshark.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    $candidate = Join-Path $env:ProgramFiles "Wireshark\tshark.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return $null
}

if (-not (Test-Path -LiteralPath $ResultsDir -PathType Container)) {
    New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null
}
$existing = @(Get-ChildItem -LiteralPath $ResultsDir -File | Where-Object { $_.Name -ne ".gitkeep" })
if ($existing.Count -ne 0) { Fail-D274Native "risultati già presenti; non rilanciare la qualificazione" }

try {
    $failedStage = "powershell_51"
    Assert-D274Pass ($PSVersionTable.PSEdition -eq "Desktop" -and
        $PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -ge 1) "è richiesto Windows PowerShell Desktop 5.1"
    $stages[$failedStage] = "PASS"

    $failedStage = "repository_and_goodix_absence"
    # Windows PowerShell 5.1: $LASTEXITCODE non è affidabile se il comando
    # nativo viene inglobato in una pipeline. Con Select-Object -First 1 la
    # pipeline upstream viene interrotta e l'exit code osservato diventa -1
    # anche quando Git riesce. L'exit code va quindi catturato subito dopo
    # l'invocazione nativa e solo dopo si trasforma l'output.
    $repositoryOutput = & git -C $PackageRoot rev-parse --show-toplevel 2>&1
    $gitExitCode = $LASTEXITCODE
    Assert-D274Pass ($gitExitCode -eq 0) "repository Git non individuabile"
    $repository = ([string](@($repositoryOutput) | Select-Object -First 1)).Trim()
    Assert-D274Pass (-not [string]::IsNullOrWhiteSpace($repository)) "repository Git vuoto"
    $CaptureRoot = Join-Path $repository "captures\D274_03"
    Assert-D274Pass ($null -ne (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) "Get-PnpDevice non disponibile"
    $escapedTarget = [regex]::Escape($ExpectedTarget)
    $targets = @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object { $_.InstanceId -match $escapedTarget })
    Assert-D274Pass ($targets.Count -eq 0) "FAIL_CLOSED_GOODIX_PRESENT_BEFORE_NATIVE_QUALIFICATION"
    $before = Get-D274ArtifactCounts
    $stages[$failedStage] = "PASS"

    $failedStage = "selftest"
    $selftest = Invoke-D274PowerShell $Launcher "-SelfTestOnly"
    Assert-D274Pass ($selftest.exit_code -eq 0) "SelfTestOnly fallito"
    $selftestJson = $selftest.stdout | ConvertFrom-Json
    Assert-D274Pass ($selftestJson.result -eq "PASS") "SelfTestOnly non ha restituito PASS"
    $stages[$failedStage] = "PASS"

    $failedStage = "powershell_51_selector"
    $zero = Invoke-D274PowerShell $Launcher ""
    $multiple = Invoke-D274PowerShell $Launcher "-SelfTestOnly -PreAuthorizationSimulationOnly"
    Assert-D274Pass ($zero.exit_code -ne 0 -and $multiple.exit_code -ne 0) "selector 0/2 modalità non fail-closed"
    Assert-D274Pass (("$($zero.stdout)`n$($zero.stderr)$($multiple.stdout)`n$($multiple.stderr)") -match "selezionare esattamente una modalità") "selector PowerShell 5.1 non raggiunto"
    $stages[$failedStage] = "PASS"

    $failedStage = "preflight"
    $preflight = Invoke-D274PowerShell $Launcher "-PreflightOnly"
    Assert-D274Pass ($preflight.exit_code -eq 0) "PreflightOnly fallito"
    $preflightJson = $preflight.stdout | ConvertFrom-Json
    Assert-D274Pass ($preflightJson.goodix_absent_from_guest -eq $true -and $preflightJson.output_root_private -eq $true) "preflight Goodix/ACL non valido"
    Assert-D274Pass ($preflightJson.usbpcap_interface_count -eq 1 -and $preflightJson.usbpcap_interface_selector_valid -eq $true) "contratto USBPcap/selector non valido"
    $stages[$failedStage] = "PASS"

    $failedStage = "preauthorization_simulation"
    $preauth = Invoke-D274PowerShell $Launcher "-PreAuthorizationSimulationOnly"
    Assert-D274Pass ($preauth.exit_code -eq 0) "PreAuthorizationSimulationOnly fallito"
    $preauthJson = $preauth.stdout | ConvertFrom-Json
    Assert-D274Pass ($preauthJson.authority_rejected_for_live -eq $true -and $preauthJson.marker_created -eq $false) "simulazione pre-authority non chiusa"
    $stages[$failedStage] = "PASS"

    $failedStage = "same_run_goodix_absence_gate"
    $sameRunArgs = "-RepositoryRoot `"$repository`" -AuthorityPath `"$Authority`" -TsharkPath `"QUALIFICATION_ONLY`" -UsbPcapInterface `"QUALIFICATION_ONLY`" -NativeQualificationOnly"
    $sameRun = Invoke-D274PowerShell $Runner $sameRunArgs
    Assert-D274Pass ($sameRun.exit_code -eq 0) "same-run Goodix absence gate non eseguito"
    $sameRunJson = $sameRun.stdout | ConvertFrom-Json
    Assert-D274Pass ($sameRunJson.same_run_goodix_absence_gate -eq "PASS_NATIVE" -and $sameRunJson.marker_created -eq $false -and $sameRunJson.capture_started -eq $false) "same-run gate non innocuo"
    $stages[$failedStage] = "PASS"

    $failedStage = "causal_source_order"
    $runnerSource = [System.IO.File]::ReadAllText($Runner)
    $gateAt = $runnerSource.IndexOf("Assert-D274GoodixAbsentSameRun | Out-Null", $runnerSource.IndexOf("# Gate causale"))
    $markerAt = $runnerSource.IndexOf("[System.IO.FileMode]::CreateNew")
    $captureAt = $runnerSource.IndexOf("Start-Process -FilePath $TsharkPath")
    $attachAt = $runnerSource.IndexOf("Collega ora il solo sensore")
    $fingerAt = $runnerSource.IndexOf("Appoggia il dito per il PRIMO ciclo")
    Assert-D274Pass ($gateAt -ge 0 -and $gateAt -lt $markerAt -and $markerAt -lt $captureAt -and $captureAt -lt $attachAt -and $attachAt -lt $fingerAt) "ordine causale same-run/marker/capture/attach/dito non valido"
    $stages[$failedStage] = "PASS"

    $failedStage = "authority_false_adversarial"
    $adversarial = Invoke-D274PowerShell $Launcher "-AutorizzoUnaSolaCatturaD27403"
    $adversarialText = "$($adversarial.stdout)`n$($adversarial.stderr)"
    Assert-D274Pass ($adversarial.exit_code -ne 0 -and $adversarialText -match "baseline non approvata") "authority false non ha bloccato il flag nominale live"
    Assert-D274Pass ($adversarialText -notmatch "Collega ora|Appoggia il dito|Secondo B0 osservato") "prompt hardware raggiunto con authority false"
    $stages[$failedStage] = "PASS"

    $failedStage = "source_privacy_language_and_runtime_contract"
    $launcherSource = [System.IO.File]::ReadAllText($Launcher)
    $observerSource = [System.IO.File]::ReadAllText((Join-Path $PackageRoot "d274_03_observe_second_b0.py"))
    foreach ($token in @("EXISTING_PIN_AUTHENTICATION", "NEW_PIN_REQUIRED", "PIN_CREATION_UI", "PIN_MUTATION_UI", "ACCOUNT_MUTATION_UI", "CREDENTIAL_MUTATION_UI", "UNEXPECTED_PREREQUISITE", "ENROLLMENT_COMMIT_UI")) {
        Assert-D274Pass ($runnerSource.Contains($token)) ("categoria UI mancante: " + $token)
    }
    Assert-D274Pass ($runnerSource -notmatch 'Read-Host[^\r\n]*(pin|password|secret)') "il Kit sembra richiedere un valore PIN/secret"
    Assert-D274Pass ($runnerSource -notmatch 'ConvertTo-SecureString|Get-Credential') "API credenziali non ammessa"
    Assert-D274Pass ($observerSource -notmatch 'libusb|pyusb|decode.*image') "observer fuori contratto passivo metadata-only"
    Assert-D274Pass ($observerSource.Contains('"biometric_plaintext_exported": False')) "observer non dichiara il gate plaintext=false"
    Assert-D274Pass ($runnerSource.Contains("Secondo B0 osservato. NON toccare più il sensore")) "avviso wire-driven italiano mancante"
    Assert-D274Pass ($runnerSource -notmatch "SECONDO_OK") "stop ancora dipendente da conferma umana"
    Assert-D274Pass ($launcherSource.Contains('Get-D274UsbPcapInterfaces') -and $launcherSource.Contains('Get-D274UsbPcapInterfaceSelector') -and $preflightJson.tshark_version.Length -gt 0) "contratto TShark/USBPcap non verificato"
    $stages[$failedStage] = "PASS"

    $failedStage = "no_real_capture_or_marker"
    $after = Get-D274ArtifactCounts
    Assert-D274Pass ($after.pcapng -eq $before.pcapng -and $after.one_shot_marker -eq $before.one_shot_marker) "la qualificazione ha creato capture o marker"
    $stages[$failedStage] = "PASS"
    $failedStage = $null
} catch {
    $overall = "FAIL"
    if ($null -eq $failedStage) { $failedStage = "initialization" }
    $stages[$failedStage] = "FAIL"
    $failureDetail = Sanitize-D274 $_.Exception.Message
}

try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $osCaption = $os.Caption; $osBuild = $os.BuildNumber
} catch { $osCaption = $null; $osBuild = $null }
$tsharkPath = Get-D274Tshark
$environment = [ordered]@{
    schema = "D274_03_NATIVE_QUALIFICATION_ENVIRONMENT_V1"
    os_caption = $osCaption
    os_build = $osBuild
    powershell_edition = $PSVersionTable.PSEdition
    powershell_version = $PSVersionTable.PSVersion.ToString()
    tshark_path_class = $(if ($null -eq $tsharkPath) { "NOT_FOUND" } else { "FOUND" })
    usbpcap_interface_count = $(if ($null -ne $preflightJson) { $preflightJson.usbpcap_interface_count } else { $null })
    goodix_present_before_run = $(if ($null -ne $targets) { $targets.Count -ne 0 } else { $null })
}
$summary = [ordered]@{
    schema = "D274_03_NATIVE_QUALIFICATION_SUMMARY_V1"
    runtime_result_state = "WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR"
    result = $overall
    failed_stage = $failedStage
    failure_detail_sanitized = $failureDetail
    stages = $stages
    same_run_goodix_absence_gate = $(if ($stages["same_run_goodix_absence_gate"] -eq "PASS") { "PASS_NATIVE" } else { "NOT_PASSED" })
    powershell_51_selector = $(if ($stages["powershell_51_selector"] -eq "PASS") { "PASS_NATIVE" } else { "NOT_PASSED" })
    tshark_usbpcap_runtime_contract = $(if ($stages["preflight"] -eq "PASS") { "PASS_NATIVE_NO_CAPTURE" } else { "NOT_PASSED" })
    acl_privacy = $(if ($stages["preflight"] -eq "PASS") { "PASS_NATIVE" } else { "NOT_PASSED" })
    operator_language = "ITALIAN"
    pin_value_handled_by_kit = $false
    secret_or_pin_value_requested = $false
    real_capture_count = 0
    real_usb_open_count = 0
    real_finger_interaction_count = 0
    real_goodix_command_count = 0
    automatic_retry_count = 0
    persistent_device_write_count = 0
    baseline_approved = $false
    approved_for_capture = $false
    live_authorized = $false
    ready_for_live = $false
}
$environment | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $ResultsDir "D274_03_native_qualification_environment.json") -Encoding UTF8
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ResultsDir "D274_03_native_qualification_summary.json") -Encoding UTF8

Write-Host "D274/03 — qualificazione nativa innocua terminata."
Write-Host "NON rilanciare il runner e NON collegare il sensore."
Write-Host "Esegui ora: .\collect-d274-03-native-qualification-results.ps1"
if ($overall -ne "PASS") {
    Write-Error ("Primo failure allo stage: " + $failedStage)
    exit 1
}
exit 0
