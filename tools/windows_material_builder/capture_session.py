# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded capture workflow; one explicit start, one manual attachment."""
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from . import windows
from .capture import analyze
from .diagnostics import Failure, require, safe_lifecycle_status
from .files import create_run, write_new

ROOT = Path(__file__).resolve().parents[2]
ATTACH_SECONDS = 90
SETTLE_SECONDS = 30
EXTENDED_SETTLE_SECONDS = 60
MISSING_CODES = frozenset(name + "_MISSING" for name in ("A2", "CHIP82", "A6"))


def can_extend(evidence, settle_seconds):
    """Only analyze() results have already passed target, APP and container gates."""
    return (settle_seconds == SETTLE_SECONDS and bool(evidence.codes) and
            set(evidence.codes) <= MISSING_CODES)


class CaptureProcess:
    def __init__(self, executable, interface, raw):
        self.executable, self.interface, self.raw = executable, interface, raw
        self.process = None
        self.events = queue.Queue()
        self.trace = []
        self.trace_lock = threading.Lock()
        self.reader = None

    def note(self, value):
        value = value if safe_lifecycle_status(value) else 'STATUS_INVALID'
        with self.trace_lock:
            if len(self.trace) < 64:
                self.trace.append(value)

    def start(self, cancel):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'tools.windows_material_builder.capture_worker',
             str(self.executable), self.interface, str(self.raw)], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup, text=True)
        def read():
            process = self.process
            ended = False
            try:
                for _ in range(64):
                    line = process.stdout.readline(80)
                    if not line:
                        ended = True
                        break
                    value = line.strip()
                    if not line.endswith('\n') or not safe_lifecycle_status(value):
                        self.note('STATUS_INVALID')
                        self.events.put('FAILED')
                        break
                    self.note(value)
                    if value in ('READY', 'STOPPED', 'FAILED'):
                        self.events.put(value)
                else:
                    self.note('STATUS_INVALID')
                    self.events.put('FAILED')
            except (OSError, ValueError):
                self.note('STATUS_INVALID')
                self.events.put('FAILED')
            finally:
                process.stdout.close()
                if ended:
                    self.note('EOF')
                    self.events.put('EOF')
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            require(not cancel.is_set(), 'CAPTURE_CANCELLED')
            require(self.process.poll() is None, 'CAPTURE_PROCESS_FAILED')
            try:
                event = self.events.get(timeout=0.1)
            except queue.Empty:
                continue
            require(event == 'READY', 'CAPTURE_PROCESS_FAILED')
            return
        raise Failure('CAPTURE_PROCESS_FAILED')

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def stop(self):
        if self.process is None:
            return
        process = self.process
        try:
            require(process.poll() is None, 'CAPTURE_PROCESS_FAILED')
            process.stdin.write('STOP\n')
            process.stdin.flush()
            self.note('PARENT_STOP_SENT')
            process.stdin.close()
            try:
                code = process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                self.note('PARENT_WAIT_TIMEOUT')
                raise Failure('CAPTURE_PROCESS_FAILED') from None
            self.note('WORKER_EXIT=' + str(code))
            require(code == 0, 'CAPTURE_PROCESS_FAILED')
            messages = []
            # Wait for the status reader, not merely process exit.
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    event = self.events.get(timeout=0.1)
                    messages.append(event)
                    if event == 'EOF':
                        break
                except queue.Empty:
                    continue
            if 'EOF' not in messages:
                self.note('PARENT_STATUS_TIMEOUT')
            require('STOPPED' in messages and 'EOF' in messages and 'FAILED' not in messages,
                    'CAPTURE_PROCESS_FAILED')
        except (OSError, subprocess.SubprocessError):
            raise Failure('CAPTURE_PROCESS_FAILED') from None
        finally:
            try:
                if process.poll() is None:
                    self.note('PARENT_TERMINATE')
                    process.terminate()
                    process.wait(timeout=5)
            finally:
                try:
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                finally:
                    if self.reader:
                        self.reader.join(timeout=2)
                    if process.returncode is not None:
                        self.note('WORKER_EXIT=' + str(process.returncode))
                    self.process = None
                    with self.trace_lock:
                        trace = '\n'.join(self.trace) + '\n'
                    write_new(self.raw.parent.parent / 'diagnostics/lifecycle.txt', trace.encode('ascii'))


def acquire(root, prerequisites, chosen, mapped, cancel, update, *, process_type=CaptureProcess,
            clock=time.monotonic, pause=time.sleep, settle_seconds=SETTLE_SECONDS):
    require(settle_seconds in (SETTLE_SECONDS, EXTENDED_SETTLE_SECONDS), 'CAPTURE_PROCESS_FAILED')
    interface = windows.choose_interface(prerequisites, chosen, mapped)
    windows.require_detached()
    run = create_run(root / 'runs')
    raw = run / 'raw/oem-init.pcap'
    update('RUN', run)
    process = process_type(prerequisites.executable, interface, raw)
    error = None
    try:
        update('STARTING', None)
        process.start(cancel)
        require(process.alive(), 'CAPTURE_PROCESS_FAILED')
        # A target arriving during startup/UAC is too early; require new run.
        windows.require_detached()
        update('ATTACH', None)
        deadline = clock() + ATTACH_SECONDS
        while True:
            require(not cancel.is_set(), 'CAPTURE_CANCELLED')
            require(process.alive(), 'CAPTURE_PROCESS_FAILED')
            count = windows.target_count()
            require(count <= 1, 'TARGET_WRONG_IDENTITY')
            if count == 1:
                break
            require(clock() < deadline, 'TARGET_NOT_OBSERVED')
            pause(0.5)
        deadline = clock() + settle_seconds
        update('SETTLING', settle_seconds)
        while clock() < deadline:
            require(not cancel.is_set(), 'CAPTURE_CANCELLED')
            require(process.alive(), 'CAPTURE_PROCESS_FAILED')
            require(windows.target_count() == 1, 'TARGET_WRONG_IDENTITY')
            pause(0.5)
    except Failure as failure:
        error = failure
    except Exception:
        error = Failure('CAPTURE_PROCESS_FAILED')
    finally:
        try:
            process.stop()
        except Exception:
            if error is None:
                error = Failure('CAPTURE_PROCESS_FAILED')
    if error:
        write_new(run / 'diagnostics/result.txt', error.diagnostic.text().encode('utf-8'))
        raise error
    update('ANALYZING', None)
    try:
        evidence = analyze(raw)
        report = '\n'.join(evidence.codes) if evidence.codes else 'CAPTURE_EVIDENCE=PASS'
        write_new(run / 'diagnostics/capture.txt', report.encode('ascii'))
        return run, evidence
    except Failure as failure:
        write_new(run / 'diagnostics/result.txt', failure.diagnostic.text().encode('utf-8'))
        raise
