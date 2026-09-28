# SPDX-License-Identifier: GPL-2.0-or-later
"""Unelevated capture helper. USBPcap and TASKKILL request their own UAC.

Raw stdout never enters the status channel. TASKKILL is attempted once, including
on cancellation/error; the parent bounds this helper's UAC/cleanup lifetime.
"""
import ctypes
from ctypes import wintypes as w
import ntpath
from pathlib import Path
import subprocess
import sys
import threading
import time
from .capture import LIMIT, pcap_header
from .diagnostics import Failure, require, safe_lifecycle_status
from .files import real_path
from .windows import INTERFACE, normal_user

STOP_SECONDS = 5
TASKKILL_SECONDS = 15
STOP_BUDGET_SECONDS = 90  # Includes interactive UAC; no retry on timeout.
TASKKILL_PARAMETERS = '/F /T /IM USBPcapCMD.exe'
_REPORT_LOCK = threading.Lock()


def report(value):
    require(safe_lifecycle_status(value), 'CAPTURE_PROCESS_FAILED')
    with _REPORT_LOCK:
        try:
            print(value, flush=True)
            return True
        except (OSError, ValueError):
            # A broken status pipe must not prevent the single cleanup attempt.
            return False


def usbpcap_present(kernel, deadline):
    """Toolhelp process-name comparison only; never log names, paths or PIDs."""
    class Entry(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD),
                    ('heap', ctypes.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                    ('parent', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD),
                    ('name', w.WCHAR * 260)]
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        function = getattr(kernel, name)
        function.argtypes, function.restype = [w.HANDLE, ctypes.POINTER(Entry)], w.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    require(snapshot not in (None, 0, ctypes.c_void_p(-1).value), 'CAPTURE_PROCESS_FAILED')
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        for _ in range(65536):
            require(time.monotonic() < deadline, 'CAPTURE_PROCESS_FAILED')
            if not found:
                require(ctypes.get_last_error() == 18, 'CAPTURE_PROCESS_FAILED')  # NO_MORE_FILES
                return False
            if entry.name.casefold() == 'usbpcapcmd.exe':
                return True
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        raise Failure('CAPTURE_PROCESS_FAILED')
    finally:
        require(kernel.CloseHandle(snapshot), 'CAPTURE_PROCESS_FAILED')


def elevated_taskkill():
    class ShellInfo(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('mask', w.ULONG), ('hwnd', w.HWND), ('verb', w.LPCWSTR),
                    ('file', w.LPCWSTR), ('parameters', w.LPCWSTR), ('directory', w.LPCWSTR),
                    ('show', ctypes.c_int), ('instance', w.HINSTANCE), ('idlist', ctypes.c_void_p),
                    ('class_name', w.LPCWSTR), ('class_key', w.HKEY), ('hotkey', w.DWORD),
                    ('icon', w.HANDLE), ('process', w.HANDLE)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    ole = ctypes.WinDLL('ole32', use_last_error=True)
    for name, args, result in (
            ('GetSystemDirectoryW', [w.LPWSTR, w.UINT], w.UINT),
            ('WaitForSingleObject', [w.HANDLE, w.DWORD], w.DWORD),
            ('GetExitCodeProcess', [w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
            ('CloseHandle', [w.HANDLE], w.BOOL)):
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    shell.ShellExecuteExW.argtypes, shell.ShellExecuteExW.restype = [ctypes.POINTER(ShellInfo)], w.BOOL
    ole.CoInitializeEx.argtypes, ole.CoInitializeEx.restype = [ctypes.c_void_p, w.DWORD], ctypes.c_long
    ole.CoUninitialize.argtypes, ole.CoUninitialize.restype = [], None
    directory = ctypes.create_unicode_buffer(32768)
    length = kernel.GetSystemDirectoryW(directory, len(directory))
    require(0 < length < len(directory) and ntpath.isabs(directory.value), 'CAPTURE_PROCESS_FAILED')
    info = ShellInfo()
    info.size = ctypes.sizeof(info)
    # NOCLOSEPROCESS | NOASYNC | FLAG_NO_UI | NO_CONSOLE. Security UI still appears.
    info.mask = 0x40 | 0x100 | 0x400 | 0x8000
    info.verb, info.file = 'runas', ntpath.join(directory.value, 'taskkill.exe')
    info.parameters, info.directory, info.show = TASKKILL_PARAMETERS, directory.value, 0
    require(ole.CoInitializeEx(None, 2) in (0, 1), 'CAPTURE_PROCESS_FAILED')
    try:
        report('TASKKILL_REQUESTED')
        if not shell.ShellExecuteExW(ctypes.byref(info)):
            report('TASKKILL_ELEVATION_CANCELLED' if ctypes.get_last_error() == 1223 else 'TASKKILL_LAUNCH_FAILED')
            raise Failure('CAPTURE_PROCESS_FAILED')
        require(info.process, 'CAPTURE_PROCESS_FAILED')
        report('TASKKILL_STARTED')
        if kernel.WaitForSingleObject(info.process, TASKKILL_SECONDS * 1000) != 0:
            report('TASKKILL_WAIT_FAILED')
            raise Failure('CAPTURE_PROCESS_FAILED')
        code = w.DWORD()
        require(kernel.GetExitCodeProcess(info.process, ctypes.byref(code)), 'CAPTURE_PROCESS_FAILED')
        report('TASKKILL_EXIT=' + str(code.value))
        report('USBPCAP_VERIFY')
        deadline = time.monotonic() + STOP_SECONDS
        while usbpcap_present(kernel, deadline):
            if time.monotonic() >= deadline:
                report('USBPCAP_REMAINS')
                raise Failure('CAPTURE_PROCESS_FAILED')
            time.sleep(0.05)
        report('USBPCAP_ABSENT')
    finally:
        try:
            if info.process:
                require(kernel.CloseHandle(info.process), 'CAPTURE_PROCESS_FAILED')
        finally:
            ole.CoUninitialize()


def read_command(expected):
    command = sys.stdin.buffer.readline(16)
    return command in (expected + b'\n', expected + b'\r\n'), command


def stop_request(stop, received):
    try:
        valid, command = read_command(b'STOP')
        if valid:
            received.set()
            report('STOP_RECEIVED')
        else:
            report('CONTROL_EOF' if not command else 'CONTROL_INVALID')
    finally:
        stop.set()


def capture(exe, interface, raw_path):
    normal_user()
    require(read_command(b'START')[0], 'CAPTURE_PROCESS_FAILED')
    report('STARTING')
    require(INTERFACE.fullmatch(interface), 'USBPCAP_INTERFACE_AMBIGUOUS')
    real_path(exe)
    real_path(raw_path.parent)
    require(not raw_path.exists(), 'CAPTURE_PROCESS_FAILED')
    stop, received = threading.Event(), threading.Event()
    threading.Thread(target=stop_request, args=(stop, received), daemon=True).start()
    with open(raw_path, 'xb', buffering=0) as raw:
        process = subprocess.Popen([str(exe), '-d', interface, '--capture-from-new-devices',
                                    '-s', '65535', '-o', '-'], stdin=subprocess.DEVNULL, stdout=raw,
                                   stderr=subprocess.DEVNULL, close_fds=True)
        try:
            start, ready = time.monotonic(), False
            try:
                while not stop.wait(0.1):
                    require(process.poll() is None, 'CAPTURE_PROCESS_FAILED')
                    elapsed = time.monotonic() - start
                    size = raw_path.stat().st_size
                    require(size <= LIMIT and elapsed <= 240, 'CAPTURE_PROCESS_FAILED')
                    if not ready:
                        require(elapsed < 60, 'CAPTURE_PROCESS_FAILED')
                        if size >= 24:
                            with open(raw_path, 'rb') as check:
                                pcap_header(check.read(24))
                            ready = True
                            require(report('READY'), 'CAPTURE_PROCESS_FAILED')
                # Check before initiating TASKKILL, including the STOP/poll race.
                require(received.is_set() and ready and process.poll() is None, 'CAPTURE_PROCESS_FAILED')
            finally:
                # Same single stop for normal completion, cancel, control EOF and
                # early native failure. Cleanup never converts an earlier error.
                elevated_taskkill()
                code = process.wait(timeout=STOP_SECONDS)
                report('CHILD_EXIT=' + str(code))
        finally:
            # Windows Popen owns this native handle; close explicitly after wait.
            process._handle.Close()
        report('CAPTURE_HANDLES_CLOSED')
        raw.flush()
    report('RAW_CLOSED')


def main():
    try:
        require(len(sys.argv) == 4, 'CAPTURE_PROCESS_FAILED')
        capture(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
        return 0
    except Exception:
        report('FAILED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
