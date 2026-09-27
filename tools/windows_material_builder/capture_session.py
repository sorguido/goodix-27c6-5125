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
from .diagnostics import Failure, require
from .files import create_run, write_new

ROOT = Path(__file__).resolve().parents[2]
ATTACH_SECONDS = 90
SETTLE_SECONDS = 30


class CaptureProcess:
    def __init__(self, executable, interface, raw):
        self.executable, self.interface, self.raw = executable, interface, raw
        self.process = None
        self.events = queue.Queue()

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
            try:
                for line in process.stdout:
                    self.events.put(line.strip() if line.strip() in ('READY', 'STOPPED') else 'FAILED')
            finally:
                process.stdout.close()
                self.events.put('EOF')
        threading.Thread(target=read, daemon=True).start()
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
            process.stdin.close()
            require(process.wait(timeout=25) == 0, 'CAPTURE_PROCESS_FAILED')
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
            require('STOPPED' in messages and 'FAILED' not in messages, 'CAPTURE_PROCESS_FAILED')
        except (OSError, subprocess.SubprocessError):
            raise Failure('CAPTURE_PROCESS_FAILED') from None
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            self.process = None


def acquire(root, prerequisites, chosen, mapped, cancel, update, *, process_type=CaptureProcess,
            clock=time.monotonic, pause=time.sleep):
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
        deadline = clock() + SETTLE_SECONDS
        update('SETTLING', SETTLE_SECONDS)
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
