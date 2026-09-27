# SPDX-License-Identifier: GPL-2.0-or-later
"""Unelevated capture helper, assigned to the parent's private job before START.

USBPcap alone requests UAC. Its stdout is the raw PCAP file. Normal STOP uses
an explicit termination result; the parent then empties the job and fsyncs raw.
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

STOP_EXIT_CODE = 0x47584350  # Private builder termination marker, not a native success code.
STOP_SECONDS = 5


class CaptureJob:
    """Parent-owned, unnamed, non-inheritable job; never contains the GUI owner."""
    def __init__(self):
        self.members = []
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', w.DWORD), ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t),
                        ('active', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('schedule', w.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
                ('CreateJobObjectW', [ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
                ('SetInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
                ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
                ('QueryInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
                ('TerminateJobObject', [w.HANDLE, w.UINT], w.BOOL),
                ('OpenProcess', [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
                ('QueryFullProcessImageNameW', [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)], w.BOOL),
                ('WaitForSingleObject', [w.HANDLE, w.DWORD], w.DWORD),
                ('CloseHandle', [w.HANDLE], w.BOOL)):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        require(self.handle, 'CAPTURE_PROCESS_FAILED')
        limits = Extended()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; neither breakaway flag is allowed.
        try:
            require(self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits),
                                                       ctypes.sizeof(limits)), 'CAPTURE_PROCESS_FAILED')
        except Exception:
            self.close()
            raise

    def assign(self, process):
        # The helper is blocked on START and cannot spawn USBPcap before assignment.
        require(self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)), 'CAPTURE_PROCESS_FAILED')

    def population(self):
        class Accounting(ctypes.Structure):
            _fields_ = [('times', ctypes.c_int64 * 4), ('faults', w.DWORD),
                        ('total', w.DWORD), ('active', w.DWORD), ('terminated', w.DWORD)]
        info = Accounting()
        require(self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(info),
                                                      ctypes.sizeof(info), None), 'CAPTURE_PROCESS_FAILED')
        return info.total, info.active

    def verify_members(self, helper_pid, executable):
        """Pin both native handles from this job only, before allowing attachment."""
        class Members(ctypes.Structure):
            _fields_ = [('assigned', w.DWORD), ('count', w.DWORD), ('ids', ctypes.c_size_t * 3)]
        require(self.population() == (3, 3), 'CAPTURE_PROCESS_FAILED')
        members = Members()
        require(self.kernel.QueryInformationJobObject(self.handle, 3, ctypes.byref(members),
                                                      ctypes.sizeof(members), None), 'CAPTURE_PROCESS_FAILED')
        require(members.assigned == members.count == 3 and len(set(members.ids)) == 3 and
                helper_pid in members.ids, 'CAPTURE_PROCESS_FAILED')
        expected = os.path.normcase(os.path.abspath(executable))
        for pid in members.ids:
            if pid == helper_pid:
                continue
            # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION. Never open by name
            # or enumerate system processes; PIDs come exclusively from our job.
            handle = self.kernel.OpenProcess(0x101000, False, pid)
            require(handle, 'CAPTURE_PROCESS_FAILED')
            self.members.append(handle)
            name, length = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
            require(self.kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)),
                    'CAPTURE_PROCESS_FAILED')
            require(os.path.normcase(os.path.abspath(name.value)) == expected, 'CAPTURE_PROCESS_FAILED')
        require(self.population() == (3, 3), 'CAPTURE_PROCESS_FAILED')

    def terminate(self):
        require(self.kernel.TerminateJobObject(self.handle, STOP_EXIT_CODE), 'CAPTURE_PROCESS_FAILED')
        deadline = time.monotonic() + STOP_SECONDS
        for handle in self.members:
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            require(self.kernel.WaitForSingleObject(handle, remaining_ms) == 0, 'CAPTURE_PROCESS_FAILED')
        while self.population()[1] != 0:
            require(time.monotonic() < deadline, 'CAPTURE_PROCESS_FAILED')
            time.sleep(0.025)

    def close(self):
        handle, self.handle = self.handle, None
        closed = True
        for member in self.members:
            closed = bool(self.kernel.CloseHandle(member)) and closed
        self.members.clear()
        if handle:
            closed = bool(self.kernel.CloseHandle(handle)) and closed
        require(closed, 'CAPTURE_PROCESS_FAILED')


_REPORT_LOCK = threading.Lock()


def report(value):
    require(safe_lifecycle_status(value), 'CAPTURE_PROCESS_FAILED')
    with _REPORT_LOCK:
        print(value, flush=True)


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


def intentional_stop(process):
    require(process.poll() is None, 'CAPTURE_PROCESS_FAILED')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
    kernel.TerminateProcess.restype = w.BOOL
    report('STOP_REASON_BUILDER_BOUNDED_TERMINATION')
    require(kernel.TerminateProcess(int(process._handle), STOP_EXIT_CODE), 'CAPTURE_PROCESS_FAILED')
    try:
        code = process.wait(timeout=STOP_SECONDS)
    except subprocess.TimeoutExpired:
        report('RELAY_WAIT_TIMEOUT')
        raise Failure('CAPTURE_PROCESS_FAILED') from None
    report('CHILD_EXIT=' + str(code))
    # A crash before/during the request is not accepted just because STOP was sent.
    require(code == STOP_EXIT_CODE, 'CAPTURE_PROCESS_FAILED')
    report('RELAY_TERMINATED')


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
    # The job owner handles cleanup on every exit, including broken control/status.
    # No inherited job handle can keep KILL_ON_JOB_CLOSE alive after owner exit.
    with open('CONIN$', 'r+b', buffering=0) as console, open(raw_path, 'xb', buffering=0) as raw:
        process = subprocess.Popen([str(exe), '-d', interface, '--capture-from-new-devices',
                                    '-s', '65535', '-o', '-'], stdin=console, stdout=raw,
                                   stderr=subprocess.DEVNULL, close_fds=True)
        start, ready = time.monotonic(), False
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
        require(received.is_set() and ready, 'CAPTURE_PROCESS_FAILED')
        intentional_stop(process)
    # Raw is closed here, but the parent fsyncs only after the entire job is empty.


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
