[CmdletBinding(DefaultParameterSetName = 'Invalid')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'RealExport')][switch]$RealExport,
    [Parameter(Mandatory = $true, ParameterSetName = 'Preflight')][switch]$RealExportPreflight,
    [Parameter(Mandatory = $true, ParameterSetName = 'SelfTest')][switch]$SelfTest,
    [Parameter(Mandatory = $true, ParameterSetName = 'Fixture')][string]$FixturePath,
    [Parameter(Mandatory = $true, ParameterSetName = 'RealExport')]
    [Parameter(Mandatory = $true, ParameterSetName = 'SelfTest')]
    [Parameter(Mandatory = $true, ParameterSetName = 'Fixture')][string]$OutputPath,
    [Parameter(ParameterSetName = 'RealExport')][string]$ConsentPhrase
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$CanonicalCache = 'C:\ProgramData\Goodix\Goodix_Cache.bin'
$RequiredConsent = 'I_AUTHORIZE_D191_LOCAL_DPAPI_EXPORT'
$TransferLength = 88

if (-not $RealExportPreflight) {
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class D191Dpapi {
  const int CRYPTPROTECT_LOCAL_MACHINE = 4;
  [StructLayout(LayoutKind.Sequential)] struct BLOB { public int cbData; public IntPtr pbData; }
  [DllImport("crypt32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  static extern bool CryptProtectData(ref BLOB input, string description, ref BLOB entropy,
    IntPtr reserved, IntPtr prompt, int flags, out BLOB output);
  [DllImport("crypt32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  static extern bool CryptUnprotectData(ref BLOB input, IntPtr description, ref BLOB entropy,
    IntPtr reserved, IntPtr prompt, int flags, out BLOB output);
  [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr value);
  static BLOB In(byte[] value) {
    BLOB result = new BLOB(); result.cbData = value.Length;
    result.pbData = Marshal.AllocHGlobal(value.Length); Marshal.Copy(value, 0, result.pbData, value.Length);
    return result;
  }
  static byte[] Out(BLOB value) { byte[] result = new byte[value.cbData]; Marshal.Copy(value.pbData, result, 0, value.cbData); return result; }
  static void Clear(ref BLOB value, bool local) {
    if (value.pbData == IntPtr.Zero) return;
    for (int i=0; i<value.cbData; i++) Marshal.WriteByte(value.pbData, i, 0);
    if (local) LocalFree(value.pbData); else Marshal.FreeHGlobal(value.pbData);
    value.pbData = IntPtr.Zero; value.cbData = 0;
  }
  public static byte[] ProtectLocalMachine(byte[] plain, byte[] entropy) {
    BLOB p=In(plain), e=In(entropy), o=new BLOB();
    try { if (!CryptProtectData(ref p, null, ref e, IntPtr.Zero, IntPtr.Zero, CRYPTPROTECT_LOCAL_MACHINE, out o)) throw new Win32Exception(); return Out(o); }
    finally { Clear(ref p,false); Clear(ref e,false); Clear(ref o,true); }
  }
  public static byte[] Unprotect(byte[] cipher, byte[] entropy) {
    BLOB c=In(cipher), e=In(entropy), o=new BLOB();
    try { if (!CryptUnprotectData(ref c, IntPtr.Zero, ref e, IntPtr.Zero, IntPtr.Zero, 0, out o)) throw new Win32Exception(); return Out(o); }
    finally { Clear(ref c,false); Clear(ref e,false); Clear(ref o,true); }
  }
}
public static class D194CacheReader {
  const uint GENERIC_READ = 0x80000000;
  const uint FILE_SHARE_READ = 0x00000001;
  const uint OPEN_EXISTING = 3;
  const uint FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000;
  const uint FILE_ATTRIBUTE_DIRECTORY = 0x00000010;
  const uint FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400;
  [StructLayout(LayoutKind.Sequential)] struct BY_HANDLE_FILE_INFORMATION {
    public uint FileAttributes;
    public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
    public uint VolumeSerialNumber;
    public uint FileSizeHigh;
    public uint FileSizeLow;
    public uint NumberOfLinks;
    public uint FileIndexHigh;
    public uint FileIndexLow;
  }
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern SafeFileHandle CreateFileW(string name, uint access, uint share,
    IntPtr security, uint creation, uint flags, IntPtr template);
  [DllImport("kernel32.dll", SetLastError=true)]
  static extern bool GetFileInformationByHandle(SafeFileHandle handle, out BY_HANDLE_FILE_INFORMATION information);
  public static byte[] ReadCanonical(string path, long minimumExclusive, long maximumInclusive) {
    SafeFileHandle handle = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, IntPtr.Zero,
      OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, IntPtr.Zero);
    if (handle.IsInvalid) { throw new Win32Exception(Marshal.GetLastWin32Error(), "canonical cache open failed"); }
    byte[] result = null;
    bool completed = false;
    try {
      BY_HANDLE_FILE_INFORMATION information;
      if (!GetFileInformationByHandle(handle, out information)) { throw new Win32Exception(Marshal.GetLastWin32Error(), "canonical cache metadata failed"); }
      if ((information.FileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0) { throw new IOException("canonical cache directory rejected"); }
      if ((information.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0) { throw new IOException("canonical cache reparse point rejected"); }
      long length = ((long)information.FileSizeHigh << 32) | information.FileSizeLow;
      if (length <= minimumExclusive || length > maximumInclusive || length > Int32.MaxValue) { throw new IOException("canonical cache size rejected"); }
      result = new byte[(int)length];
      using (FileStream stream = new FileStream(handle, FileAccess.Read, 4096, false)) {
        int offset = 0;
        while (offset < result.Length) {
          int count = stream.Read(result, offset, result.Length - offset);
          if (count == 0) { throw new EndOfStreamException("canonical cache short read"); }
          offset += count;
        }
        if (stream.ReadByte() != -1) { throw new IOException("canonical cache trailing growth rejected"); }
      }
      completed = true;
      return result;
    } finally {
      handle.Dispose();
      if (!completed && result != null) { Array.Clear(result, 0, result.Length); }
    }
  }
}
'@
}

function Clear-Bytes([byte[]]$Value) { if ($null -ne $Value) { [Array]::Clear($Value, 0, $Value.Length) } }
function Get-Sha256([byte[]]$Value) { $Sha = [Security.Cryptography.SHA256]::Create(); try { return $Sha.ComputeHash($Value) } finally { $Sha.Dispose() } }
function Get-Hex([byte[]]$Value) { return ([BitConverter]::ToString($Value) -replace '-', '').ToLowerInvariant() }
function Test-FixedEqual([byte[]]$A, [byte[]]$B) { if ($A.Length -ne $B.Length) { return $false }; $D = 0; for ($I=0; $I -lt $A.Length; $I++) { $D = $D -bor ($A[$I] -bxor $B[$I]) }; return $D -eq 0 }
function Get-RandomBytes([int]$Length) { [byte[]]$Value = New-Object byte[] $Length; $Rng = [Security.Cryptography.RandomNumberGenerator]::Create(); try { $Rng.GetBytes($Value) } finally { $Rng.Dispose() }; return $Value }

function Get-D191Entropy([byte[]]$Trailer) {
    if ($Trailer.Length -ne 8) { throw 'trailer must be exactly 8 bytes' }
    $NonZero = 0; foreach ($Byte in $Trailer) { $NonZero = $NonZero -bor $Byte }
    if ($NonZero -eq 0) { throw 'zero trailer rejected fail-closed' }
    $Sha = [Security.Cryptography.SHA256]::Create()
    [byte[]]$H1 = $null; [byte[]]$H2 = $null; [byte[]]$EntropyInput = New-Object byte[] 32
    try {
        $H1 = $Sha.ComputeHash($Trailer)
        [Array]::Copy($H1, 0, $EntropyInput, 0, 16)
        [byte[]]$Mix = @(0x04,0xe0,0xb0,0xf3,0xf5,0x59,0x84,0x17,0xdd,0xe2,0x98,0xe4,0x67,0xc7,0x95,0xf7)
        [Array]::Copy($Mix, 0, $EntropyInput, 16, 16)
        $H2 = $Sha.ComputeHash($EntropyInput)
        [byte[]]$Entropy = New-Object byte[] 48
        [Array]::Copy($H1, 16, $Entropy, 0, 16); [Array]::Copy($H2, 0, $Entropy, 16, 32)
        return $Entropy
    } finally { $Sha.Dispose(); Clear-Bytes $H1; Clear-Bytes $H2; Clear-Bytes $EntropyInput }
}

function New-TransferRecord([byte[]]$Secret) {
    if ($Secret.Length -ne 32) { throw 'DPAPI plaintext must be exactly 32 bytes' }
    $NonZero = 0; foreach ($Byte in $Secret) { $NonZero = $NonZero -bor $Byte }
    if ($NonZero -eq 0) { throw 'zero DPAPI plaintext rejected fail-closed' }
    [byte[]]$Record = New-Object byte[] $TransferLength
    [Text.Encoding]::ASCII.GetBytes('G5125XFR').CopyTo($Record, 0)
    [BitConverter]::GetBytes([uint16]1).CopyTo($Record, 8)
    [BitConverter]::GetBytes([uint16]0).CopyTo($Record, 10)
    [BitConverter]::GetBytes([uint16]0x27c6).CopyTo($Record, 12)
    [BitConverter]::GetBytes([uint16]0x5125).CopyTo($Record, 14)
    [BitConverter]::GetBytes([uint16]32).CopyTo($Record, 16)
    [BitConverter]::GetBytes([uint16]0).CopyTo($Record, 18)
    [BitConverter]::GetBytes([uint32]32).CopyTo($Record, 20)
    [Array]::Copy($Secret, 0, $Record, 24, 32)
    $Digest = Get-Sha256 $Record[0..55]
    [Array]::Copy($Digest, 0, $Record, 56, 32); Clear-Bytes $Digest
    return $Record
}

function Assert-TransferRecord([byte[]]$Record) {
    if ($Record.Length -ne $TransferLength -or [Text.Encoding]::ASCII.GetString($Record,0,8) -cne 'G5125XFR') { throw 'transfer shape rejected' }
    if ([BitConverter]::ToUInt16($Record,8) -ne 1 -or [BitConverter]::ToUInt16($Record,10) -ne 0 -or
        [BitConverter]::ToUInt16($Record,12) -ne 0x27c6 -or [BitConverter]::ToUInt16($Record,14) -ne 0x5125 -or
        [BitConverter]::ToUInt16($Record,16) -ne 32 -or [BitConverter]::ToUInt16($Record,18) -ne 0 -or
        [BitConverter]::ToUInt32($Record,20) -ne 32) { throw 'transfer header rejected' }
    $Expected = Get-Sha256 $Record[0..55]
    [byte[]]$Actual = $Record[56..87]
    try { if (-not (Test-FixedEqual $Expected $Actual)) { throw 'transfer digest rejected' } }
    finally { Clear-Bytes $Expected; Clear-Bytes $Actual }
}

function Assert-OutputPath([string]$Path) {
    if (-not [IO.Path]::IsPathRooted($Path)) { throw 'output path must be absolute' }
    if (Test-Path -LiteralPath $Path) { throw 'output path already exists' }
    $Lower = [IO.Path]::GetFullPath($Path).ToLowerInvariant()
    foreach ($Marker in @('onedrive','dropbox','google drive','icloud','sharepoint')) {
        if ($Lower.Contains($Marker)) { throw 'known cloud-sync output path rejected' }
    }
    $Parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $Parent -PathType Container)) { throw 'output parent missing' }
    $Component = Get-Item -LiteralPath $Parent -Force
    while ($null -ne $Component) {
        if (($Component.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'output directory chain reparse point rejected' }
        $ComponentLower = $Component.FullName.ToLowerInvariant()
        foreach ($Marker in @('onedrive','dropbox','google drive','icloud','sharepoint')) {
            if ($ComponentLower.Contains($Marker)) { throw 'known cloud-sync directory chain rejected' }
        }
        $Component = $Component.Parent
    }
}

function Set-PrivateAcl([string]$Path) {
    $Acl = New-Object Security.AccessControl.FileSecurity
    $Acl.SetAccessRuleProtection($true, $false)
    $Current = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $System = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
    foreach ($Identity in @($Current, $System)) {
        $Acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($Identity, 'FullControl', 'Allow')))
    }
    Set-Acl -LiteralPath $Path -AclObject $Acl
}

function Assert-PrivateAcl([string]$Path) {
    $Acl = Get-Acl -LiteralPath $Path
    if (-not $Acl.AreAccessRulesProtected) { throw 'output ACL inheritance is not protected' }
    if ($Acl.Access.Count -ne 2) { throw 'output ACL rule count rejected' }
    $Current = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $Allowed = @($Current, 'S-1-5-18')
    foreach ($Rule in $Acl.Access) {
        $RuleSid = $Rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($Rule.IsInherited -or $Rule.AccessControlType -ne 'Allow' -or $Allowed -notcontains $RuleSid -or
            (($Rule.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -ne [Security.AccessControl.FileSystemRights]::FullControl)) {
            throw 'output ACL contains unexpected principal rights or inherited rule'
        }
    }
}

function Write-AtomicPrivate([string]$Path, [byte[]]$Bytes, [ref]$Created) {
    $Temporary = Join-Path (Split-Path -Parent $Path) ('.d191-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $Stream = [IO.FileStream]::new($Temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write,
            [IO.FileShare]::None, 4096, [IO.FileOptions]::WriteThrough)
        try { $Stream.Write($Bytes, 0, $Bytes.Length); $Stream.Flush($true) } finally { $Stream.Dispose() }
        Set-PrivateAcl $Temporary
        [IO.File]::Move($Temporary, $Path)
        $Created.Value = $true
    } finally { if (Test-Path -LiteralPath $Temporary) { Remove-Item -LiteralPath $Temporary -Force } }
}

function Get-EnvironmentClass {
    try {
        $Computer = Get-CimInstance Win32_ComputerSystem
        $Identity = (($Computer.Manufacturer + ' ' + $Computer.Model)).ToLowerInvariant()
        foreach ($Marker in @('virtual','vmware','virtualbox','kvm','qemu','hyper-v','xen','parallels')) {
            if ($Identity.Contains($Marker)) { return 'virtualized' }
        }
        if (-not [string]::IsNullOrWhiteSpace($Identity)) { return 'physical' }
    } catch { }
    return 'unknown'
}

function Invoke-RealExportPreflight {
    $Present = Test-Path -LiteralPath $CanonicalCache
    $Regular = $false; $Reparse = $false; $Size = $null; $Bounded = $false
    $OwnerClass = 'unavailable'; $AclClass = 'unavailable'; $Blocker = $null
    if (-not $Present) {
        $Blocker = 'CACHE_NOT_FOUND'
    } else {
        try {
            $Item = Get-Item -LiteralPath $CanonicalCache -Force
            $Regular = -not $Item.PSIsContainer
            $Reparse = (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
            if ($Regular) { $Size = [long]$Item.Length; $Bounded = ($Size -gt 8 -and $Size -le 1048576) }
        } catch { $Blocker = 'CACHE_METADATA_UNAVAILABLE' }
        try {
            $Acl = Get-Acl -LiteralPath $CanonicalCache
            if (-not [string]::IsNullOrWhiteSpace($Acl.Owner)) { $OwnerClass = 'present-redacted' }
            if ($Acl.Access.Count -gt 0) { $AclClass = 'present-redacted' }
        } catch { }
        if ($null -eq $Blocker) {
            if (-not $Regular) { $Blocker = 'CACHE_NOT_REGULAR_CANDIDATE' }
            elseif ($Reparse) { $Blocker = 'CACHE_REPARSE_OBSERVED' }
            elseif (-not $Bounded) { $Blocker = 'CACHE_SIZE_REJECTED' }
            elseif ($OwnerClass -eq 'unavailable') { $Blocker = 'CACHE_OWNER_UNAVAILABLE' }
            elseif ($AclClass -eq 'unavailable') { $Blocker = 'CACHE_ACL_UNAVAILABLE' }
        }
    }
    $Ready = ($null -eq $Blocker)
    $Result = [ordered]@{
        success=$true; mode='real-export-preflight'; native_windows=$true
        powershell_version=$PSVersionTable.PSVersion.ToString(); environment_class=(Get-EnvironmentClass)
        physical_smbios_gate_used=$false; cache_present=$Present; cache_path_class='canonical-redacted'
        cache_regular_candidate=$Regular; cache_reparse_observed=$Reparse; cache_size=$Size
        cache_size_bounded=$Bounded; cache_owner_class=$OwnerClass; cache_acl_class=$AclClass
        cache_content_read=$false; dpapi_called=$false; secret_accessed=$false; sensor_required=$false
        ready_for_separate_real_export=$Ready
    }
    if ($null -ne $Blocker) { $Result['blocker'] = $Blocker }
    return [pscustomobject]$Result
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'native Windows is required' }
if ($PSCmdlet.ParameterSetName -eq 'Preflight') { Invoke-RealExportPreflight; return }
if ($PSCmdlet.ParameterSetName -eq 'Invalid') { throw 'select exactly one operation mode' }
Assert-OutputPath $OutputPath

[byte[]]$Secret = $null; [byte[]]$Entropy = $null; [byte[]]$Cache = $null; [byte[]]$Blob = $null; [byte[]]$Record = $null
$OutputCreated = $false; $OperationCompleted = $false; $Result = $null; $RollbackError = $null
try {
    if ($RealExport) {
        if ($ConsentPhrase -cne $RequiredConsent) { throw 'exact consent phrase required' }
        $Acl = Get-Acl -LiteralPath $CanonicalCache
        if ([string]::IsNullOrWhiteSpace($Acl.Owner) -or $Acl.Access.Count -eq 0) { throw 'cache owner/ACL unavailable' }
        $Cache = [D194CacheReader]::ReadCanonical($CanonicalCache, 8, 1048576)
        [byte[]]$Trailer = $Cache[($Cache.Length-8)..($Cache.Length-1)]
        $Entropy = Get-D191Entropy $Trailer; Clear-Bytes $Trailer
        $Blob = $Cache[0..($Cache.Length-9)]
        $Secret = [D191Dpapi]::Unprotect($Blob, $Entropy)
    } elseif ($SelfTest) {
        [byte[]]$Plain = Get-RandomBytes 32
        [byte[]]$Trailer = Get-RandomBytes 8
        try {
            $Entropy = Get-D191Entropy $Trailer
            $Blob = [D191Dpapi]::ProtectLocalMachine($Plain, $Entropy)
            $Secret = [D191Dpapi]::Unprotect($Blob, $Entropy)
            if (-not (Test-FixedEqual $Plain $Secret)) { throw 'DPAPI round-trip mismatch' }
            [byte[]]$Wrong = [byte[]]$Entropy.Clone(); $Wrong[0] = $Wrong[0] -bxor 1; $WrongFailed = $false
            try { $Unexpected = [D191Dpapi]::Unprotect($Blob, $Wrong); Clear-Bytes $Unexpected } catch { $WrongFailed = $true }
            finally { Clear-Bytes $Wrong }
            if (-not $WrongFailed) { throw 'wrong entropy unexpectedly accepted' }
            try { Get-D191Entropy (New-Object byte[] 8) | Out-Null; throw 'zero trailer unexpectedly accepted' } catch { if ($_.Exception.Message -notmatch 'zero trailer') { throw } }
        } finally { Clear-Bytes $Plain; Clear-Bytes $Trailer }
    } else {
        $Fixture = Get-Item -LiteralPath $FixturePath -Force
        if ($Fixture.PSIsContainer -or (($Fixture.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) -or $Fixture.Length -ne $TransferLength) { throw 'fixture rejected' }
        $Record = [IO.File]::ReadAllBytes($Fixture.FullName)
        if ([Text.Encoding]::ASCII.GetString($Record,0,8) -cne 'G5125XFR') { throw 'fixture transfer magic rejected' }
    }
    if ($null -eq $Record) { $Record = New-TransferRecord $Secret }
    Assert-TransferRecord $Record
    Write-AtomicPrivate $OutputPath $Record ([ref]$OutputCreated)
    if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) { throw 'output missing after atomic write' }
    Assert-PrivateAcl $OutputPath
    $RecordDigest = Get-Sha256 $Record; $Hash = Get-Hex $RecordDigest; Clear-Bytes $RecordDigest
    $Result = [pscustomobject]@{ success=$true; mode=$(if($RealExport){'real-dpapi'}elseif($SelfTest){'native-self-test'}else{'synthetic-fixture'}); output_size=$TransferLength; transfer_sha256=$Hash; cache_owner_class=$(if($RealExport){'present-redacted'}else{'not-applicable'}); acl_class='protected-current-user-and-system'; secret_disclosed=$false }
    $OperationCompleted = $true
} finally {
    if ($OutputCreated -and ($SelfTest -or -not $OperationCompleted) -and (Test-Path -LiteralPath $OutputPath)) {
        try {
            Remove-Item -LiteralPath $OutputPath -Force
            if (Test-Path -LiteralPath $OutputPath) { throw 'output remains after cleanup' }
        } catch { $RollbackError = 'sensitive output rollback failed: ' + $_.Exception.Message }
    }
    Clear-Bytes $Record; Clear-Bytes $Secret; Clear-Bytes $Entropy; Clear-Bytes $Blob; Clear-Bytes $Cache
    if ($null -ne $RollbackError) { throw $RollbackError }
}
$Result
