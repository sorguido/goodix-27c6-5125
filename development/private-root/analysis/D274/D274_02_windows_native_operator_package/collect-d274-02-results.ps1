# SPDX-License-Identifier: GPL-2.0-or-later
# D274/02 result collector. Windows PowerShell 5.1 only.
#
# Accepts ONLY the operator package results/ directory, verifies the presence
# allowlist, rejects unexpected files, performs a textual privacy scan, and
# produces a sanitized result ZIP + SHA256. It never includes pcap, raw ACL,
# registry, event log, screenshots, fingerprint data, B0, TLS, secrets, PSK,
# cache, DLL or firmware.
[CmdletBinding()]
param(
    [string]$ResultsDir = (Join-Path $PSScriptRoot "results")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$PackageRoot = $PSScriptRoot

# Allowlist of result files permitted in the bundle.
$AllowList = @(
    "D274_02_selftest.json",
    "D274_02_preflight.json",
    "D274_02_preauthorization_simulation.json",
    "D274_02_native_qualification_summary.json",
    "D274_02_environment.json",
    "D274_02_hard_disable_adversarial.json"
)

# Sanitized stderr files may be included ONLY on FAIL and ONLY if they pass the
# privacy scan. They must match this prefix/suffix.
$AllowedStderrPrefix = "D274_02_"
$AllowedStderrSuffix = "_stderr_sanitized.txt"

function Fail-D274Collect([string]$Message) {
    throw "D274_02_COLLECT_FAIL_CLOSED: $Message"
}

# Validate the supplied directory is EXACTLY the package results/ directory.
# Canonicalize both sides and require exact equality; a sibling path that merely
# shares the package prefix is rejected.
$resolvedResults = [System.IO.Path]::GetFullPath($ResultsDir)
$expectedResults = [System.IO.Path]::GetFullPath((Join-Path $PackageRoot "results"))
if ($resolvedResults -ne $expectedResults) {
    Fail-D274Collect ("ResultsDir must be exactly <package>/results; resolved '$resolvedResults' != expected '$expectedResults'")
}
if (-not (Test-Path -LiteralPath $resolvedResults -PathType Container)) {
    Fail-D274Collect "results directory not found"
}

# Enumerate and reject unexpected files.
$allFiles = @(Get-ChildItem -LiteralPath $resolvedResults -File | Select-Object -ExpandProperty Name)
$unexpected = @($allFiles | Where-Object { $_ -notin $AllowList -and -not ($_.StartsWith($AllowedStderrPrefix) -and $_.EndsWith($AllowedStderrSuffix)) })
if ($unexpected.Count -gt 0) {
    Fail-D274Collect ("unexpected file(s) in results/: " + ($unexpected -join ", "))
}

# Verify presence allowlist (the core result files must exist).
$missing = @($AllowList | Where-Object { -not (Test-Path -LiteralPath (Join-Path $resolvedResults $_) -PathType Leaf) })
if ($missing.Count -gt 0) {
    Fail-D274Collect ("missing required result file(s): " + ($missing -join ", "))
}

# Textual privacy scan. Second barrier: if any sensitive pattern is found, the
# bundle is refused (FAIL_CLOSED) and the offending file is NOT included.
$SensitivePatterns = @(
    'S-1-\d',                                   # SID (raw)
    '\b[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}\1[0-9A-Fa-f]{2}\1[0-9A-Fa-f]{2}\1[0-9A-Fa-f]{2}\1[0-9A-Fa-f]{2}\b', # MAC
    '\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',   # IPv4
    '[Cc]:\\Users\\',                           # user home path
    'HKEY_',                                    # registry
    '(?i)(password|passwd|secret|token|psk|private\s*key|product\s*key)' # credential tokens
)

function Test-PrivacyClean([string]$Path) {
    $text = [System.IO.File]::ReadAllText($Path)
    foreach ($pattern in $SensitivePatterns) {
        if ($text -match $pattern) { return $false }
    }
    return $true
}

# Stage allowed files for zipping.
$staging = Join-Path $env:TEMP ("d274_02_stage_" + [Guid]::NewGuid().ToString("N"))
if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging -Force | Out-Null
try {
    foreach ($file in $AllowList) {
        $src = Join-Path $resolvedResults $file
        if (-not (Test-PrivacyClean $src)) {
            Fail-D274Collect ("privacy scan failed for $file; refusing to package")
        }
        Copy-Item -LiteralPath $src -Destination (Join-Path $staging $file) -Force
    }
    # Optionally include sanitized stderr on FAIL, only if privacy-clean.
    $summaryPath = Join-Path $resolvedResults "D274_02_native_qualification_summary.json"
    $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
    if ($summary.result -ne "PASS") {
        $stderrCandidates = @(Get-ChildItem -LiteralPath $resolvedResults -File |
            Where-Object { $_.Name.StartsWith($AllowedStderrPrefix) -and $_.Name.EndsWith($AllowedStderrSuffix) })
        foreach ($cand in $stderrCandidates) {
            if (Test-PrivacyClean $cand.FullName) {
                Copy-Item -LiteralPath $cand.FullName -Destination (Join-Path $staging $cand.Name) -Force
            }
        }
    }

    $zipName = "D274_02_windows_native_qualification_results.zip"
    $zipPath = Join-Path $resolvedResults $zipName
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force

    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash
    $hashPath = Join-Path $resolvedResults ($zipName + ".sha256")
    Set-Content -LiteralPath $hashPath -Value $hash -Encoding ASCII

    [ordered]@{
        schema = "D274_02_COLLECT_RESULT_V1"
        result = "PASS"
        package = $zipName
        sha256 = $hash
        files = @(Get-ChildItem -LiteralPath $staging -File | Select-Object -ExpandProperty Name)
        privacy_scan = "PASS"
    } | ConvertTo-Json -Depth 4
} finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
