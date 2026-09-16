# SPDX-License-Identifier: GPL-2.0-or-later
<#
.SYNOPSIS
Export the existing Goodix 27c6:5125 Windows DPAPI transport material.

.DESCRIPTION
User-facing wrapper around the recovered and reviewed DPAPI exporter core.
It never prints the reader secret. The real export creates an 88-byte
G5125XFR staging record; finalize that record on Linux with
Finalize-Goodix5125TransportMaterial.py.

.EXAMPLE
.\Export-Goodix5125TransportMaterial.ps1 -Preflight

.EXAMPLE
.\Export-Goodix5125TransportMaterial.ps1 -SelfTest

.EXAMPLE
.\Export-Goodix5125TransportMaterial.ps1 -OutputPath C:\GoodixMaterialWork\transport-material.xfr
#>
[CmdletBinding(DefaultParameterSetName = 'Export')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Preflight')]
    [switch]$Preflight,

    [Parameter(Mandatory = $true, ParameterSetName = 'SelfTest')]
    [switch]$SelfTest,

    [Parameter(Mandatory = $true, ParameterSetName = 'Export')]
    [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Core = Join-Path $PSScriptRoot '_Export-Goodix5125TransportMaterial.Core.ps1'
if (-not (Test-Path -LiteralPath $Core -PathType Leaf)) {
    throw "exporter core not found: $Core"
}

if ($Preflight) {
    & $Core -RealExportPreflight
    return
}

if ($SelfTest) {
    $TemporaryOutput = Join-Path ([IO.Path]::GetTempPath()) (
        'goodix5125-selftest-' + [Guid]::NewGuid().ToString('N') + '.xfr'
    )
    try {
        & $Core -SelfTest -OutputPath $TemporaryOutput
    } finally {
        if (Test-Path -LiteralPath $TemporaryOutput) {
            Remove-Item -LiteralPath $TemporaryOutput -Force
        }
    }
    return
}

& $Core -RealExport -OutputPath $OutputPath `
    -ConsentPhrase 'I_AUTHORIZE_D191_LOCAL_DPAPI_EXPORT'
