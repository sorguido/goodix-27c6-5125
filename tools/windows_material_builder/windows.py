# SPDX-License-Identifier: GPL-2.0-or-later
"""Windows integration. Only explicit install() performs a network request."""
import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import subprocess
import sys
import uuid
from .diagnostics import Failure, require
from .files import private_directory, read_regular, real_path, write_new

VERSION = '1.5.4.0'
INSTALLER = 'USBPcapSetup-1.5.4.0.exe'
RELEASE = 'https://github.com/desowin/usbpcap/releases/tag/' + VERSION
URL = 'https://github.com/desowin/usbpcap/releases/download/' + VERSION + '/' + INSTALLER
SHA256 = '87a7edf9bbbcf07b5f4373d9a192a6770d2ff3add7aa1e276e82e38582ccb622'
INSTALLER_SIZE = 195040
INTERFACE = re.compile(r'\\\\\.\\USBPcap[1-9][0-9]*')


def normal_user():
    require(os.name == 'nt' and sys.maxsize > 2**32, 'PLATFORM_UNSUPPORTED')
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.IsUserAnAdmin.restype = w.BOOL
    require(not shell.IsUserAnAdmin(), 'PLATFORM_UNSUPPORTED')


def powershell(script, code='TARGET_QUERY_FAILED'):
    require(os.name == 'nt', 'PLATFORM_UNSUPPORTED')
    exe = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        result = subprocess.run([str(exe), '-NoProfile', '-NonInteractive', '-Command',
                                 "$ErrorActionPreference='Stop';" + script],
                                capture_output=True, timeout=20, creationflags=0x08000000)
        require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, code)
        return result.stdout.decode('utf-8-sig').strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        raise Failure(code) from None


def boot_identity():
    value = powershell('(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString("o")')
    require(bool(re.fullmatch(r'[0-9T:.Z+\-]{20,40}', value)), 'TARGET_QUERY_FAILED')
    return value


def baseline_report():
    """Read only OS product/version/build; unavailable metadata never gates capture."""
    fields = {'Caption': 'UNKNOWN', 'Version': 'UNKNOWN', 'BuildNumber': 'UNKNOWN'}
    try:
        data = json.loads(powershell(
            '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;'
            'Get-CimInstance Win32_OperatingSystem | '
            'Select-Object Caption,Version,BuildNumber | ConvertTo-Json -Compress'))
        if isinstance(data, dict):
            for key in fields:
                value = data.get(key)
                pattern = r'[\w .()+-]{1,120}' if key == 'Caption' else r'[0-9.]{1,32}'
                if isinstance(value, str) and re.fullmatch(pattern, value):
                    fields[key] = value
    except (Failure, OSError, ValueError):
        pass
    return (f'Windows product: {fields["Caption"]}\nWindows version: {fields["Version"]}\n'
            f'Windows build: {fields["BuildNumber"]}\nPython version: {platform.python_version()}\n'
            'USBPcap 1.5.4.0 is project-pinned; live qualification is pending for this Windows VM baseline.')


def target_count():
    value = powershell(r"@(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^USB\\VID_27C6&PID_5125\\' }).Count")
    require(value.isdigit(), 'TARGET_QUERY_FAILED')
    return int(value)


def require_detached():
    require(target_count() == 0, 'TARGET_PRESENT_BEFORE_CAPTURE')


def restrict_directory(path):
    sid = powershell('[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value', 'SOURCE_UNSAFE')
    require(bool(re.fullmatch(r'S-1-(?:[0-9]+-)+[0-9]+', sid)) and
            sid not in ('S-1-5-18', 'S-1-5-19', 'S-1-5-20'), 'SOURCE_UNSAFE')
    exe = Path(os.environ['SystemRoot']) / 'System32/icacls.exe'
    try:
        result = subprocess.run([str(exe), str(path), '/inheritance:r', '/grant:r',
                                 '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                                capture_output=True, timeout=15, creationflags=0x08000000)
        require(result.returncode == 0, 'SOURCE_UNSAFE')
    except (OSError, subprocess.SubprocessError):
        raise Failure('SOURCE_UNSAFE') from None


def app_directory():
    normal_user()
    # Known Folder API avoids Documents/Desktop/cloud-synced defaults.
    class GUID(ctypes.Structure):
        _fields_ = [('a', w.DWORD), ('b', w.WORD), ('c', w.WORD), ('d', ctypes.c_ubyte * 8)]
    guid = GUID.from_buffer_copy(uuid.UUID('f1b32785-6fba-4fcf-9d55-7b8e7f157091').bytes_le)
    shell, ole = ctypes.WinDLL('shell32'), ctypes.WinDLL('ole32')
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), w.DWORD, w.HANDLE, ctypes.POINTER(w.LPWSTR)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    out = w.LPWSTR()
    require(shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0, 'SOURCE_UNSAFE')
    try:
        root = real_path(Path(out.value)) / 'Goodix5125MaterialBuilder'
    finally:
        ole.CoTaskMemFree(out)
    if not root.exists():
        private_directory(root)
    else:
        real_path(root)
        restrict_directory(root)
    runs = root / 'runs'
    if not runs.exists():
        private_directory(runs)
    real_path(runs)
    return root


def recover_dpapi(cache):
    normal_user()
    require(8 < len(cache) <= 1024 * 1024 and any(cache[-8:]), 'DPAPI_RECOVERY_FAILED')
    h1 = hashlib.sha256(cache[-8:]).digest()
    h2 = hashlib.sha256(h1[:16] + bytes.fromhex('04e0b0f3f5598417dde298e467c795f7')).digest()
    cipher = ctypes.create_string_buffer(cache[:-8], len(cache) - 8)
    entropy = ctypes.create_string_buffer(h1[16:] + h2, 48)
    class Blob(ctypes.Structure):
        _fields_ = [('length', w.DWORD), ('data', ctypes.c_void_p)]
    source = Blob(len(cipher), ctypes.addressof(cipher))
    extra = Blob(48, ctypes.addressof(entropy))
    output = Blob()
    crypt, kernel = ctypes.WinDLL('crypt32', use_last_error=True), ctypes.WinDLL('kernel32')
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                                        ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype = w.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        require(crypt.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(extra), None,
                                        None, 1, ctypes.byref(output)), 'DPAPI_RECOVERY_FAILED')
        require(output.length == 32 and output.data, 'DPAPI_RECOVERY_FAILED')
        result = bytearray(ctypes.string_at(output.data, 32))
        require(any(result), 'DPAPI_RECOVERY_FAILED')
        return result
    finally:
        ctypes.memset(ctypes.addressof(cipher), 0, len(cipher))
        ctypes.memset(ctypes.addressof(entropy), 0, 48)
        if output.data:
            ctypes.memset(output.data, 0, output.length)
            kernel.LocalFree(output.data)


@dataclass(frozen=True)
class Prerequisites:
    executable: Path | None
    driver: bool
    version: str
    interfaces: tuple
    reboot_required: bool


def reboot_pending(root, boot):
    for path in root.glob('install-request-*.json'):
        try:
            value = json.loads(read_regular(path, 1024))
            require(set(value) == {'boot'} and isinstance(value['boot'], str), 'USBPCAP_REBOOT_REQUIRED')
            if value['boot'] == boot:
                return True
        except (ValueError, OSError):
            raise Failure('USBPCAP_REBOOT_REQUIRED') from None
    return False


def command(executable, *args):
    try:
        result = subprocess.run([str(executable), *args], capture_output=True, timeout=15,
                                creationflags=0x08000000 if os.name == 'nt' else 0)
        require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, 'USBPCAP_VERSION_UNSUPPORTED')
        return result.stdout.decode('utf-8', errors='replace')
    except (OSError, subprocess.SubprocessError):
        raise Failure('USBPCAP_VERSION_UNSUPPORTED') from None


def detect(root):
    normal_user()
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\USBPcap',
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            version = winreg.QueryValueEx(key, 'DisplayVersion')[0]
            uninstall = winreg.QueryValueEx(key, 'UninstallString')[0]
        require(isinstance(uninstall, str) and uninstall.startswith('"') and uninstall.endswith('"'),
                'USBPCAP_VERSION_UNSUPPORTED')
        executable = real_path(Path(uninstall[1:-1]).parent / 'USBPcapCMD.exe')
    except FileNotFoundError:
        return Prerequisites(None, False, '', (), reboot_pending(root, boot_identity()))
    except OSError:
        raise Failure('USBPCAP_NOT_INSTALLED') from None
    require(version == VERSION, 'USBPCAP_VERSION_UNSUPPORTED')
    # Verify installed image versions without trusting a PATH lookup.
    # Only a registry-qualified absolute path is invoked.
    require(executable.is_file(), 'USBPCAP_NOT_INSTALLED')
    version_text = command(executable, '--extcap-version')
    require('{version=' + VERSION + '}' in version_text, 'USBPCAP_VERSION_UNSUPPORTED')
    value = powershell("$d=Get-CimInstance Win32_SystemDriver -Filter \"Name='USBPcap'\";"
                       "if($null -eq $d){'ABSENT'}else{$d.State}", 'USBPCAP_NOT_INSTALLED')
    driver = value == 'Running'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Services\USBPcap') as key:
            image = winreg.QueryValueEx(key, 'ImagePath')[0]
        # No script interpolation of registry paths. Driver version is read
        # using the native version resource API.
        image = image.removeprefix('\\??\\').replace('\\SystemRoot\\', os.environ['SystemRoot'] + '\\')
        if image.lower().startswith('system32\\'):
            image = str(Path(os.environ['SystemRoot']) / image)
        require(file_version(real_path(image.strip('"'))) == VERSION, 'USBPCAP_VERSION_UNSUPPORTED')
    except OSError:
        raise Failure('USBPCAP_NOT_INSTALLED') from None
    text = command(executable, '--extcap-interfaces')
    interfaces = tuple(re.findall(r'^interface \{value=([^}]+)\}', text, re.M))
    require(all(INTERFACE.fullmatch(i) for i in interfaces) and len(set(interfaces)) == len(interfaces),
            'USBPCAP_INTERFACE_AMBIGUOUS')
    return Prerequisites(executable, driver, version, interfaces, reboot_pending(root, boot_identity()) or not driver)


def file_version(path):
    lib = ctypes.WinDLL('version', use_last_error=True)
    lib.GetFileVersionInfoSizeW.argtypes = [w.LPCWSTR, ctypes.POINTER(w.DWORD)]
    lib.GetFileVersionInfoSizeW.restype = w.DWORD
    lib.GetFileVersionInfoW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p]
    lib.GetFileVersionInfoW.restype = w.BOOL
    lib.VerQueryValueW.argtypes = [ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.UINT)]
    lib.VerQueryValueW.restype = w.BOOL
    unused = w.DWORD()
    size = lib.GetFileVersionInfoSizeW(str(path), ctypes.byref(unused))
    require(0 < size <= 1024 * 1024, 'USBPCAP_VERSION_UNSUPPORTED')
    buf = ctypes.create_string_buffer(size)
    require(lib.GetFileVersionInfoW(str(path), 0, size, buf), 'USBPCAP_VERSION_UNSUPPORTED')
    pointer, length = ctypes.c_void_p(), w.UINT()
    require(lib.VerQueryValueW(buf, '\\', ctypes.byref(pointer), ctypes.byref(length)) and length.value >= 52,
            'USBPCAP_VERSION_UNSUPPORTED')
    values = ctypes.cast(pointer, ctypes.POINTER(w.DWORD))
    require(values[0] == 0xfeef04bd, 'USBPCAP_VERSION_UNSUPPORTED')
    return '.'.join(str(v) for v in (values[2] >> 16, values[2] & 65535, values[3] >> 16, values[3] & 65535))


def choose_interface(prerequisites, chosen=None, mapped=False):
    require(prerequisites.executable is not None, 'USBPCAP_NOT_INSTALLED')
    require(not prerequisites.reboot_required, 'USBPCAP_REBOOT_REQUIRED')
    require(prerequisites.driver, 'USBPCAP_NOT_INSTALLED')
    options = prerequisites.interfaces
    require(bool(options), 'USBPCAP_INTERFACE_NONE')
    if len(options) == 1:
        return options[0]
    require(mapped and chosen in options, 'USBPCAP_INTERFACE_AMBIGUOUS')
    return chosen


def download_installer():
    # This is the sole application network boundary: no secrets are arguments.
    import urllib.request
    from urllib.parse import urlsplit
    class OfficialRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            dest = urlsplit(newurl)
            require(dest.scheme == 'https' and dest.hostname in
                    ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'),
                    'USBPCAP_HASH_OR_PROVENANCE_FAILURE')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    try:
        opener = urllib.request.build_opener(OfficialRedirect)
        with opener.open(URL, timeout=30) as response:
            data = response.read(INSTALLER_SIZE + 1)
        verify_installer(data)
        return data
    except Exception:
        raise Failure('USBPCAP_HASH_OR_PROVENANCE_FAILURE') from None


def verify_installer(data):
    require(len(data) == INSTALLER_SIZE and hashlib.sha256(data).hexdigest() == SHA256,
            'USBPCAP_HASH_OR_PROVENANCE_FAILURE')


def launch_installer(path):
    """Interactive UAC only; no /S and no accepted license on user's behalf."""
    class ShellInfo(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('mask', w.ULONG), ('hwnd', w.HWND), ('verb', w.LPCWSTR),
                    ('file', w.LPCWSTR), ('parameters', w.LPCWSTR), ('directory', w.LPCWSTR),
                    ('show', ctypes.c_int), ('instance', w.HINSTANCE), ('idlist', ctypes.c_void_p),
                    ('class_name', w.LPCWSTR), ('class_key', w.HKEY), ('hotkey', w.DWORD),
                    ('icon', w.HANDLE), ('process', w.HANDLE)]
    shell, kernel = ctypes.WinDLL('shell32', use_last_error=True), ctypes.WinDLL('kernel32')
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellInfo)]
    shell.ShellExecuteExW.restype = w.BOOL
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.WaitForSingleObject.restype = w.DWORD
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    kernel.GetExitCodeProcess.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    info = ShellInfo()
    info.size, info.mask, info.verb, info.file, info.show = ctypes.sizeof(info), 0x40, 'runas', str(path), 1
    require(shell.ShellExecuteExW(ctypes.byref(info)), 'USBPCAP_INSTALL_FAILED')
    try:
        while kernel.WaitForSingleObject(info.process, 1000) == 258:
            pass  # Runs in the GUI worker thread, never blocks Tk.
        code = w.DWORD()
        require(kernel.GetExitCodeProcess(info.process, ctypes.byref(code)) and code.value in (0, 3010),
                'USBPCAP_INSTALL_FAILED')
    finally:
        kernel.CloseHandle(info.process)


def install(root):
    normal_user()
    data = download_installer()
    directory = private_directory(root / ('installer-' + uuid.uuid4().hex))
    path = directory / INSTALLER
    write_new(path, data)
    verify_installer(read_regular(path, INSTALLER_SIZE, INSTALLER_SIZE))
    write_new(root / ('install-request-' + uuid.uuid4().hex + '.json'),
              json.dumps({'boot': boot_identity()}).encode('ascii'))
    launch_installer(path)
    return detect(root)
