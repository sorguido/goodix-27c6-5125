# SPDX-License-Identifier: GPL-2.0-or-later
"""Private console owner for USBPcap. No DPAPI, hypervisor or USB commands.

Started unelevated by capture_session with CREATE_NEW_CONSOLE. Only USBPcap's
own capture worker requests UAC. A console key event requests its normal exit.
The control pipe carries only STOP; all capture output goes directly to raw.
"""
import ctypes
from ctypes import wintypes as w
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from .capture import LIMIT, pcap_header
from .diagnostics import Failure, require, safe_lifecycle_status
from .files import real_path
from .windows import INTERFACE, normal_user


def own_process_job():
    """Kill capture descendants if the control worker crashes or is stopped.

    The handle intentionally lives until process exit; explicitly closing a job
    containing ourselves would terminate us before the final status is flushed.
    """
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', w.DWORD), ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t),
                    ('active', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('schedule', w.DWORD)]
    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                    ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                    ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    require(job, 'CAPTURE_PROCESS_FAILED')
    limits = Extended()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    require(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)), 'CAPTURE_PROCESS_FAILED')
    require(kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()), 'CAPTURE_PROCESS_FAILED')
    return job


class Key(ctypes.Structure):
    _fields_ = [('down', w.BOOL), ('repeat', w.WORD), ('key', w.WORD),
                ('scan', w.WORD), ('character', w.WCHAR), ('state', w.DWORD)]


class Event(ctypes.Union):
    _fields_ = [('key', Key), ('padding', ctypes.c_byte * 16)]


class Record(ctypes.Structure):
    _fields_ = [('kind', w.WORD), ('event', Event)]


def quit_console(console):
    import msvcrt
    record = Record()
    record.kind = 1
    record.event.key = Key(True, 1, ord('Q'), 0, 'q', 0)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.WriteConsoleInputW.argtypes = [w.HANDLE, ctypes.POINTER(Record), w.DWORD, ctypes.POINTER(w.DWORD)]
    kernel.WriteConsoleInputW.restype = w.BOOL
    written = w.DWORD()
    require(kernel.WriteConsoleInputW(msvcrt.get_osfhandle(console.fileno()), ctypes.byref(record),
                                     1, ctypes.byref(written)) and written.value == 1, 'CAPTURE_PROCESS_FAILED')


_REPORT_LOCK = threading.Lock()


def report(value):
    require(safe_lifecycle_status(value), 'CAPTURE_PROCESS_FAILED')
    with _REPORT_LOCK:
        print(value, flush=True)


def stop_request(stop, received):
    try:
        command = sys.stdin.buffer.readline(16)
        # The parent's text-mode pipe translates LF to CRLF on Windows.
        if command in (b'STOP\n', b'STOP\r\n'):
            received.set()
            report('STOP_RECEIVED')
        else:
            report('CONTROL_EOF' if not command else 'CONTROL_INVALID')
    finally:
        stop.set()


def probe_launch_handles(raw, stderr):
    """Observe upstream's file-query predicate on the actual launch handles."""
    for label, stream in (('STDOUT', raw), ('STDERR', stderr)):
        result = 'UNKNOWN'
        try:
            import msvcrt
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.c_void_p]
            kernel.GetFileInformationByHandle.restype = w.BOOL
            # BY_HANDLE_FILE_INFORMATION: 13 DWORDs; never report its contents.
            info = (w.DWORD * 13)()
            redirected = kernel.GetFileInformationByHandle(
                msvcrt.get_osfhandle(stream.fileno()), ctypes.byref(info))
            result = 'REDIRECTED' if redirected else 'NOT_REDIRECTED'
        except Exception:
            # Diagnostic failure must not replace or prevent orderly shutdown.
            pass
        report('LAUNCH_' + label + '_' + result)


def probe_console(process, console):
    """Bounded read-only snapshots; neither PIDs nor input characters are logged."""
    shared, pending = 'UNKNOWN', 'UNKNOWN'
    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetConsoleProcessList.argtypes = [ctypes.POINTER(w.DWORD), w.DWORD]
        kernel.GetConsoleProcessList.restype = w.DWORD
        processes = (w.DWORD * 32)()
        count = kernel.GetConsoleProcessList(processes, len(processes))
        if 0 < count <= len(processes):
            shared = 'SHARED' if process.pid in processes[:count] else 'NOT_SHARED'
    except Exception:
        pass
    try:
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.PeekConsoleInputW.argtypes = [w.HANDLE, ctypes.POINTER(Record), w.DWORD, ctypes.POINTER(w.DWORD)]
        kernel.PeekConsoleInputW.restype = w.BOOL
        records, count = (Record * 32)(), w.DWORD()
        if kernel.PeekConsoleInputW(msvcrt.get_osfhandle(console.fileno()), records,
                                    len(records), ctypes.byref(count)) and count.value <= len(records):
            if any(r.kind == 1 and r.event.key.down and r.event.key.character == 'q'
                   for r in records[:count.value]):
                pending = 'PENDING'
            elif count.value < len(records):
                pending = 'NOT_PENDING'
            # A full bounded snapshot cannot rule out q beyond its last record.
    except Exception:
        pass
    report('CHILD_CONSOLE_' + shared)
    report('CONSOLE_Q_' + pending)


def orderly_stop(process, console):
    report('STOP_CONSOLE_CHECK')
    probe_console(process, console)
    report('Q_REQUESTED')
    quit_console(console)
    report('Q_INJECTED')
    report('CHILD_WAIT')
    try:
        code = process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        report('CHILD_WAIT_TIMEOUT')
        report('TIMEOUT_CONSOLE_CHECK')
        probe_console(process, console)
        raise Failure('CAPTURE_PROCESS_FAILED') from None
    report('CHILD_EXIT=' + str(code))
    require(code == 0, 'CAPTURE_PROCESS_FAILED')


def capture(exe, interface, raw_path):
    report('STARTING')
    normal_user()
    job = own_process_job()
    require(INTERFACE.fullmatch(interface), 'USBPCAP_INTERFACE_AMBIGUOUS')
    real_path(exe)
    real_path(raw_path.parent)
    require(not raw_path.exists(), 'CAPTURE_PROCESS_FAILED')
    stop = threading.Event()
    received = threading.Event()
    threading.Thread(target=stop_request, args=(stop, received), daemon=True).start()
    process = None
    clean, ready = False, False
    with open('CONIN$', 'r+b', buffering=0) as console, \
            open(os.devnull, 'r+b', buffering=0) as stderr, open(raw_path, 'xb', buffering=0) as raw:
        try:
            probe_launch_handles(raw, stderr)
            process = subprocess.Popen([str(exe), '-d', interface, '--capture-from-new-devices',
                                        '-s', '65535', '-o', '-'], stdin=console, stdout=raw,
                                       stderr=stderr, close_fds=True)
            start = time.monotonic()
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
                        report('READY')
            require(received.is_set() and ready and process.poll() is None, 'CAPTURE_PROCESS_FAILED')
            orderly_stop(process, console)
            report('RAW_FLUSH')
            os.fsync(raw.fileno())
            report('RAW_FLUSHED')
            clean = True
        finally:
            if process is not None and process.poll() is None:
                try:
                    try:
                        report('CLEANUP_Q')
                    finally:
                        quit_console(console)
                        process.wait(timeout=5)
                except Exception:
                    # Emergency process cleanup is never accepted as success.
                    try:
                        report('CLEANUP_TERMINATE')
                    finally:
                        process.terminate()
                        process.wait(timeout=5)
            if process is not None and process.returncode is not None:
                report('CHILD_EXIT=' + str(process.returncode))
    require(clean, 'CAPTURE_PROCESS_FAILED')
    report('STOPPED')


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
