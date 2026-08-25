# SPDX-License-Identifier: GPL-2.0-or-later
# Collector metadata-only D274/03, compatibile con Windows PowerShell 5.1.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SanitizedRunDirectory)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

function Fail-D274Collect([string]$Message) { throw "D274_03_COLLECT_FAIL_CLOSED: $Message" }

$resolved = [System.IO.Path]::GetFullPath($SanitizedRunDirectory)
$repository = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>&1 | Select-Object -First 1).Trim()
if ($LASTEXITCODE -ne 0) { Fail-D274Collect "repository Git non individuabile" }
$allowedParent = [System.IO.Path]::GetFullPath((Join-Path $repository "captures\D274_03"))
if (-not $resolved.StartsWith($allowedParent + [System.IO.Path]::DirectorySeparatorChar)) {
    Fail-D274Collect "la directory risultati non appartiene a captures/D274_03"
}
if (-not (Test-Path -LiteralPath $resolved -PathType Container)) { Fail-D274Collect "directory risultati assente" }
$files = @(Get-ChildItem -LiteralPath $resolved -File)
if ($files.Count -ne 1 -or $files[0].Name -ne "D274_03_second_cycle_evidence.json") {
    Fail-D274Collect "la directory deve contenere solo l'evidenza sanitizzata prevista"
}
$text = [System.IO.File]::ReadAllText($files[0].FullName)
$forbidden = @('"raw"\s*:', '"payload"\s*:', '"plaintext"\s*:', '"image"\s*:',
               '"raster"\s*:', '"pixel"\s*:', '"psk"\s*:', '"secret"\s*:')
foreach ($pattern in $forbidden) {
    if ($text -match $pattern) { Fail-D274Collect "privacy scan fallito" }
}
$document = $text | ConvertFrom-Json
if ($document.privacy_payload_exported -ne $false -or
    $document.biometric_plaintext_exported -ne $false -or
    $document.biometric_hash_exported -ne $false -or
    $document.secret_material_exported -ne $false) {
    Fail-D274Collect "flag privacy non validi"
}
$zipPath = Join-Path $resolved "D274_03_sanitized_results.zip"
if (Test-Path -LiteralPath $zipPath) { Fail-D274Collect "bundle risultati già esistente" }
Compress-Archive -LiteralPath $files[0].FullName -DestinationPath $zipPath
$sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
Set-Content -LiteralPath ($zipPath + ".sha256") -Value $sha -Encoding ASCII
Write-Host "Raccolta completata: il bundle contiene soltanto metadata sanitizzati."
Write-Host "NON includere la capture raw nel materiale di review pubblicabile."
[ordered]@{schema="D274_03_COLLECT_RESULT_V1"; result="PASS"; package=$zipPath; sha256=$sha; privacy_scan="PASS"} | ConvertTo-Json -Depth 3
