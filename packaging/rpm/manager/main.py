#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Goodix Manager: unprivileged Qt client for a fixed PolicyKit helper."""
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from threading import Event

from PySide6.QtCore import QObject, Property, QProcess, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtQuickControls2 import QQuickStyle

# The launcher uses isolated mode; load only the adjacent installed, root-owned module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import LATEST_API, MESSAGES, REPOSITORY, LocalPackage, NoCompatibleRelease, Release, Status, version_tuple
import diagnostics as diagnostic_tools
from reader import ReaderSession

HELPER = '/usr/libexec/goodix-manager-helper'
MAX_REPLY = 512 * 1024


class DiagnosticWorker(QThread):
    """Only unprivileged, bounded collectors run here; results cross by value."""
    result = Signal(int, dict)

    def __init__(self, generation, task, cancel, parent):
        super().__init__(parent)
        self.generation, self.task, self.cancel = generation, task, cancel

    def run(self):
        try:
            value = self.task(self.cancel)
        except Exception:
            # Neither exceptions nor subprocess output cross the UI boundary.
            value = {'checks': [], 'overview': 'No new diagnostic results are available', 'generatedAt': '',
                     'reportReady': False, 'reportError': 'Diagnostic data could not be collected.'}
        self.result.emit(self.generation, value)


class Controller(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.status = Status()
        self.busy = False
        self.operation = ''
        self.notice = 'Verifying installed software…'
        self.remote_message = 'Checking public releases…'
        self.release = None
        self.local_package = None
        self.network = QNetworkAccessManager(self)
        self.reply = None
        self.network_timeout = QTimer(self)
        self.network_timeout.setSingleShot(True)
        self.network_timeout.timeout.connect(lambda: self.reply.abort() if self.reply is not None else None)
        self.remote_body = bytearray()
        self.process = None
        self.output = bytearray()
        self.output_overflow = False
        self.last_result = ''
        self.status_observed_at = ''
        self.last_operation = {}
        self._diagnostic_data = {
            'checks': [], 'overview': 'No checks have been run yet', 'generatedAt': '',
            'reportText': '', 'reportTitle': '', 'reportSummary': '',
            'reportReady': False, 'reportError': '',
        }
        self._diagnostic_thread = None
        self._diagnostic_cancel = None
        self._diagnostic_generation = 0
        self._shutdown_requested = False
        self.reader = ReaderSession(self)
        self.reader.changed.connect(self.changed)
        self.remote_state = 'checking'
        self.package_version = 'Not verified'
        try:
            package = json.loads(Path('/usr/lib/goodix-manager/package.json').read_text())
            version_tuple(package['version'])
            if type(package['release']) is not int or package['release'] < 1 or package['fedora'] != 44 or package['arch'] != 'x86_64':
                raise ValueError('invalid metadata')
            self.package_version = f"{package['version']}-{package['release']}.fc44"
        except (OSError, KeyError, TypeError, ValueError):
            pass
        QTimer.singleShot(0, self.refresh)
        QTimer.singleShot(0, self.check_releases)

    @Property('QVariantMap', notify=changed)
    def view(self):
        state = self.status
        remote_state, remote_message = self.public_status()
        remote = remote_state == 'available'
        sensor = ('Connected' if state.sensor_present else 'Not connected') if state.sensor_present is not None else 'Not checked'
        return {
            'busy': self.busy, 'operation': self.operation,
            'diagnosticBusy': self.diagnostics['busy'],
            'title': state.title, 'state': state.state, 'notice': self.notice,
            'runtime': state.runtime_version or ('Not installed' if state.state == 'absent' else
                        'Earlier driver · version unknown' if state.state == 'legacy' else
                        'Unknown version' if state.message_code == 'version_unknown' else 'Not verified'),
            'payload': state.payload_version or 'Not verified',
            'package': state.package_version or self.package_version,
            'sensor': sensor, 'action': state.action,
            'upgradeLegacy': state.state == 'legacy' and state.action == 'update',
            'canRemove': state.state in {'installed', 'legacy'} or state.message_code in {'version_unknown', 'source_mismatch'},
            'remoteMessage': remote_message, 'remoteState': remote_state,
            'remoteAvailable': remote, 'remoteChecking': self.remote_state == 'checking',
            'remoteVersion': self.release.package_version if remote else '',
            'rebootRequired': state.reboot_required,
            'enrollmentRequired': state.enrollment_required,
        }

    def public_status(self):
        if self.remote_state != 'available':
            return self.remote_state, self.remote_message
        if self.local_package is None:
            return 'unavailable', 'Check unavailable · local Manager package could not be verified'
        if self.release.newer_than(self.local_package):
            return 'available', 'New public package: ' + self.release.package_version
        return 'current', 'Manager package is current · latest compatible public package: ' + self.release.package_version

    @Slot()
    def refresh(self):
        self.run('status')

    @Slot(str)
    def perform(self, action):
        if action == self.status.action or action == 'remove' and (self.status.state in {'installed', 'legacy'} or self.status.message_code in {'version_unknown', 'source_mismatch'}):
            self.run(action)

    def run(self, action):
        if self._shutdown_requested or self.busy or self.diagnostics['busy'] or action not in {'status', 'install', 'update', 'remove'}:
            return
        self.invalidate_diagnostic_report()
        self.busy = True
        self.operation = action
        self.notice = {'status': 'Verifying installed software…', 'install': 'Installing the local driver payload…',
                       'update': 'Applying the local driver update…', 'remove': 'Removing the driver…'}[action]
        self.output = bytearray()
        self.output_overflow = False
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        # Discard stderr; raw privileged output is never rendered or copied.
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.start('/usr/bin/pkexec', [HELPER, action])
        self.changed.emit()

    def read_output(self):
        chunk = bytes(self.process.readAllStandardOutput())
        if len(self.output) + len(chunk) > MAX_REPLY:
            self.output_overflow = True
            self.output.clear()
        if not self.output_overflow:
            self.output.extend(chunk)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.finish_invalid('helper_unavailable')

    def finish_invalid(self, code):
        self.status = Status(message_code=code)
        self.status_observed_at = ''
        if self.operation in {'install', 'update', 'remove'}:
            self.last_operation = {'action': self.operation, 'result': 'failed',
                                   'message_code': code,
                                   'observedAt': datetime.now(timezone.utc).isoformat(timespec='seconds')}
        self.local_package = None
        self.notice = MESSAGES[code]
        self.busy = False
        self.last_result = code
        self.changed.emit()

    def finished(self, code, exit_status):
        self.read_output()
        try:
            if self.output_overflow or exit_status != QProcess.ExitStatus.NormalExit:
                raise ValueError('incomplete output')
            data = json.loads(self.output)
            status = Status.parse(data)
            result = data.get('result')
            if result not in {'success', 'failed', 'rolled_back', 'blocked'}:
                raise ValueError('invalid result')
            if code != 0 and result == 'success':
                raise ValueError('contradictory exit status')
            self.status = status
            try:
                self.local_package = LocalPackage.from_status(status)
            except ValueError:
                self.local_package = None
            self.last_result = result
            self.status_observed_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
            if self.operation != 'status':
                self.last_operation = {'action': self.operation, 'result': result,
                                       'message_code': status.message_code,
                                       'observedAt': self.status_observed_at}
            self.notice = MESSAGES[status.message_code]
            if result == 'rolled_back':
                self.notice = MESSAGES['rolled_back']
            elif result in {'failed', 'blocked'} and status.message_code == 'ready':
                self.notice = MESSAGES[result]
            self.busy = False
            self.changed.emit()
        except (ValueError, TypeError, KeyError):
            self.finish_invalid('authorization_failed' if code in {126, 127} else 'invalid_response')
        finally:
            self.output.clear()
            self.process.deleteLater()
            self.process = None

    @Slot()
    def check_releases(self):
        if self.reply is not None:
            return
        self.remote_state = 'checking'
        self.remote_message = 'Checking public releases…'
        self.remote_body.clear()
        request = QNetworkRequest(QUrl(LATEST_API))
        request.setRawHeader(b'Accept', b'application/vnd.github+json')
        request.setRawHeader(b'User-Agent', b'Goodix-Manager')
        request.setTransferTimeout(8000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self.reply = self.network.get(request)
        self.network_timeout.start(8000)
        self.reply.readyRead.connect(self.read_remote)
        self.reply.finished.connect(self.remote_finished)
        self.changed.emit()

    def read_remote(self):
        chunk = bytes(self.reply.readAll())
        if len(self.remote_body) + len(chunk) > MAX_REPLY:
            self.reply.abort()
            return
        self.remote_body.extend(chunk)

    def remote_finished(self):
        self.network_timeout.stop()
        reply = self.reply
        self.read_remote()
        try:
            if (reply.error() != QNetworkReply.NetworkError.NoError or
                    reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 200):
                raise ValueError('network check unavailable')
            self.release = Release.parse(json.loads(self.remote_body))
            self.remote_state = 'available'
            self.remote_message = 'Latest public release: ' + self.release.version
        except NoCompatibleRelease:
            self.release = None
            self.remote_state = 'no-compatible'
            self.remote_message = 'No compatible public release · local actions remain available'
        except (ValueError, TypeError, KeyError):
            self.release = None
            self.remote_state = 'unavailable'
            self.remote_message = 'Check unavailable · local actions remain available'
        finally:
            self.remote_body.clear()
            reply.deleteLater()
            self.reply = None
            self.changed.emit()

    @Slot()
    def documents(self):
        QDesktopServices.openUrl(QUrl(REPOSITORY))

    @Slot()
    def report_bug(self):
        QDesktopServices.openUrl(QUrl(REPOSITORY + '/issues/new?template=01-bug-report.yml'))

    @Slot(bool)
    def open_release(self, download):
        if self.release and self.local_package and self.public_status()[0] == 'available':
            QDesktopServices.openUrl(QUrl(self.release.asset_url if download else self.release.page_url))

    @Slot()
    def copy_diagnostics(self):
        diagnostics = self.status.diagnostic() + '\nOperation result: ' + self.last_result + '\nRelease check: ' + self.public_status()[0]
        QGuiApplication.clipboard().setText(diagnostics)

    @Property('QVariantMap', notify=changed)
    def diagnostics(self):
        reader = self.reader.view
        return {**self._diagnostic_data,
                'readerState': reader['state'], 'readerMessage': reader['message'],
                'readerBusy': reader['busy'], 'readerAttempts': reader['attempts'],
                'readerCanStart': reader['canStart'],
                'busy': self._diagnostic_thread is not None or reader['busy'],
                'collecting': self._diagnostic_thread is not None,
                'installationTimeAvailable': diagnostic_tools.installation_reference(self._diagnostic_snapshot()) is not None,
                'statusObservedAt': self.status_observed_at,
                'lastOperation': dict(self.last_operation)}

    @Slot()
    def invalidate_diagnostic_report(self):
        self._diagnostic_generation += 1
        if self._diagnostic_cancel is not None:
            self._diagnostic_cancel.set()
        self._diagnostic_data.update(reportReady=False, reportText='', reportTitle='',
                                     reportSummary='', reportError='')
        self.changed.emit()

    def _start_diagnostic_worker(self, task):
        if self._shutdown_requested or self.busy or self.diagnostics['busy']:
            return False
        self.invalidate_diagnostic_report()
        self._clear_diagnostic_results('Collecting new diagnostic evidence…')
        cancel = Event()
        self._diagnostic_cancel = cancel
        worker = DiagnosticWorker(self._diagnostic_generation, task, cancel, self)
        self._diagnostic_thread = worker
        worker.result.connect(self._receive_diagnostic_result)
        worker.finished.connect(self._diagnostic_worker_finished)
        worker.start()
        self.changed.emit()
        return True

    @Slot(int, dict)
    def _receive_diagnostic_result(self, generation, value):
        if (generation != self._diagnostic_generation or self._diagnostic_cancel is None or
                self._diagnostic_cancel.is_set()):
            return
        for key in self._diagnostic_data:
            if key in value:
                self._diagnostic_data[key] = value[key]
        if value.get('reportError') and not value.get('checks'):
            self._clear_diagnostic_results('No new diagnostic results are available')
        self.changed.emit()

    def _clear_diagnostic_results(self, overview):
        self._diagnostic_data.update(checks=[], overview=overview, generatedAt='')

    def _diagnostic_snapshot(self):
        if not self.status_observed_at and not self.last_operation:
            return None
        return {'status': self.status if self.status_observed_at else None,
                'observedAt': self.status_observed_at,
                'lastOperation': dict(self.last_operation)}

    @Slot()
    def _diagnostic_worker_finished(self):
        if self._diagnostic_cancel is not None and self._diagnostic_cancel.is_set():
            self._clear_diagnostic_results('Collection cancelled. No new diagnostic results are available.')
            self._diagnostic_data['reportError'] = 'Collection was cancelled. No new report was created.'
        worker, self._diagnostic_thread = self._diagnostic_thread, None
        self._diagnostic_cancel = None
        if worker is not None:
            worker.deleteLater()
        self.changed.emit()

    @Slot()
    def run_diagnostics(self):
        snapshot = self._diagnostic_snapshot()
        self._start_diagnostic_worker(lambda cancel: diagnostic_tools.collect_checks(status_snapshot=snapshot, cancel=cancel))

    @Slot(str, str, bool, bool, str, str)
    def create_diagnostic_report(self, profile, time_window, extended, consent, since='', until=''):
        if self._shutdown_requested or self.busy or self.diagnostics['busy']:
            return
        if consent is not True:
            self.invalidate_diagnostic_report()
            self._clear_diagnostic_results('No new diagnostic results are available')
            self._diagnostic_data['reportError'] = 'Consent is required before collecting a report.'
            self.changed.emit()
            return
        snapshot = self._diagnostic_snapshot()
        self._start_diagnostic_worker(lambda cancel: diagnostic_tools.collect_report(
            profile, time_window, extended, consent, since, until, status_snapshot=snapshot, cancel=cancel))

    @Slot()
    def copy_diagnostic_report(self):
        if self._diagnostic_data['reportReady'] and not self.diagnostics['busy']:
            QGuiApplication.clipboard().setText(self._diagnostic_data['reportText'])

    @Slot()
    def save_diagnostic_report(self):
        if not self._diagnostic_data['reportReady'] or self.diagnostics['busy']:
            return
        destination, _ = QFileDialog.getSaveFileName(None, 'Save diagnostic report',
            'goodix-diagnostic-report.txt', 'Text report (*.txt)')
        if not destination:
            return
        try:
            diagnostic_tools.save_report(destination, self._diagnostic_data['reportText'])
            self._diagnostic_data['reportError'] = 'Report saved locally with private permissions.'
        except (OSError, ValueError):
            self._diagnostic_data['reportError'] = 'Report could not be saved. Choose a new file in a writable folder.'
        self.changed.emit()

    @Slot(bool)
    def start_reader_test(self, consent):
        if self._shutdown_requested or self.busy or self.diagnostics['busy']:
            return
        self.invalidate_diagnostic_report()
        self.reader.start(consent)

    @Slot()
    def cancel_reader_test(self):
        self.reader.cancel()

    @Slot()
    def cancel_diagnostics(self):
        self.invalidate_diagnostic_report()
        self._clear_diagnostic_results('No new diagnostic results are available')
        self.reader.cancel()
        self.changed.emit()

    @Property(bool, notify=changed)
    def closeReady(self):
        return self._shutdown_requested and not self.busy and not self.diagnostics['busy']

    @Slot(result=bool)
    def request_close(self):
        """Defer window destruction until its worker and reader are released."""
        if self.busy:
            return False
        self._shutdown_requested = True
        self.invalidate_diagnostic_report()
        self.reader.shutdown()
        self.changed.emit()
        return self.closeReady

    @Slot()
    def shutdown(self):
        # aboutToQuit also covers an application-level quit rather than a window
        # close. The production collector bounds commands and checks cancellation;
        # joining here prevents destruction of a running QThread after Qt exits.
        self._shutdown_requested = True
        self.invalidate_diagnostic_report()
        self.reader.shutdown()
        if self._diagnostic_thread is not None:
            self._diagnostic_thread.wait()


def load_interface(engine):
    # RPM builds normalize mtimes. Read current bytes so an older on-disk QML
    # cache cannot survive a package update; the base URL preserves relative assets.
    path = Path(__file__).with_name('Main.qml')
    diagnostic_path = path.with_name('DiagnosticPage.qml')
    # The second page has the same reproducible-package mtime risk. Compile
    # current bytes here as well, while keeping page instantiation on demand.
    diagnostic_component = QQmlComponent(engine, engine)
    diagnostic_component.setData(diagnostic_path.read_bytes(), QUrl.fromLocalFile(str(diagnostic_path)))
    engine._diagnostic_component = diagnostic_component
    engine.rootContext().setContextProperty('diagnosticComponent', diagnostic_component)
    engine.loadData(path.read_bytes(), QUrl.fromLocalFile(str(path)))


def main():
    if os.geteuid() == 0:
        print('Goodix Manager must run as a regular desktop user.', file=sys.stderr)
        return 1
    QQuickStyle.setStyle('Fusion')
    app = QApplication(sys.argv)
    app.setApplicationName('Goodix Manager')
    app.setOrganizationName('Goodix')
    app.setDesktopFileName('io.github.sorguido.GoodixManager')
    app.setWindowIcon(QIcon(str(Path(__file__).with_name('io.github.sorguido.GoodixManager.svg'))))
    engine = QQmlApplicationEngine()
    engine.addImportPath('/usr/lib64/qt6/qml')
    controller = Controller()
    app.aboutToQuit.connect(controller.shutdown)
    engine.rootContext().setContextProperty('backend', controller)
    load_interface(engine)
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
