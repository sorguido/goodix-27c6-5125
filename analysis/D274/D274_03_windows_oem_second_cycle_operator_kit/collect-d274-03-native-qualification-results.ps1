# SPDX-License-Identifier: GPL-2.0-or-later
# Collector metadata-only della qualificazione nativa D274/03.
[CmdletBinding()]
param([string]$ResultsDir = (Join-Path $PSScriptRoot "native_qualification_results"))

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

function Fail-D274NativeCollect([string]$Message) { throw "D274_03_NATIVE_COLLECT_FAIL_CLOSED: $Message" }

$expected = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "native_qualification_results"))
$resolved = [System.IO.Path]::GetFullPath($ResultsDir)
if ($resolved -ne $expected) { Fail-D274NativeCollect "ResultsDir deve essere esattamente la directory prevista" }
$allowed = @("D274_03_native_qualification_environment.json", "D274_03_native_qualification_summary.json")
$files = @(Get-ChildItem -LiteralPath $resolved -File | Where-Object { $_.Name -ne ".gitkeep" -and $_.Name -notlike "D274_03_windows_native_qualification_results.zip*" })
$unexpected = @($files | Where-Object { $_.Name -notin $allowed })
if ($unexpected.Count -ne 0) { Fail-D274NativeCollect "file inattesi nei risultati" }
$missing = @($allowed | Where-Object { -not (Test-Path -LiteralPath (Join-Path $resolved $_) -PathType Leaf) })
if ($missing.Count -ne 0) { Fail-D274NativeCollect ("file risultati mancanti: " + ($missing -join ", ")) }

$forbidden = @(
    'S-1-\d', '[A-Za-z]:\\Users\\', 'HKEY_',
    '"(pin_value|password_value|secret_value|psk_value|payload|plaintext|image|raster|pixel|biometric_hash)"\s*:'
)
foreach ($name in $allowed) {
    $text = [System.IO.File]::ReadAllText((Join-Path $resolved $name))
    foreach ($pattern in $forbidden) {
        if ($text -match $pattern) { Fail-D274NativeCollect ("privacy scan fallito per " + $name) }
    }
}

$stage = Join-Path $env:TEMP ("d274_03_native_stage_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
try {
    foreach ($name in $allowed) { Copy-Item -LiteralPath (Join-Path $resolved $name) -Destination (Join-Path $stage $name) }
    $zipName = "D274_03_windows_native_qualification_results.zip"
    $zipPath = Join-Path $resolved $zipName
    if (Test-Path -LiteralPath $zipPath) { Fail-D274NativeCollect "ZIP risultati già esistente; non sovrascrivere" }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath
    $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
    Set-Content -LiteralPath ($zipPath + ".sha256") -Value $sha -Encoding ASCII
    [ordered]@{schema="D274_03_NATIVE_COLLECT_RESULT_V1"; result="PASS"; package=$zipName; sha256=$sha; privacy_scan="PASS"} | ConvertTo-Json -Depth 3
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
