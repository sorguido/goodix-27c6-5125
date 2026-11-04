#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Goodix Manager: unprivileged Qt client for a fixed PolicyKit helper."""
import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QObject, Property, QProcess, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle

# The launcher uses isolated mode; load only the adjacent installed, root-owned module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import LATEST_API, MESSAGES, REPOSITORY, LocalPackage, NoCompatibleRelease, Release, Status, version_tuple

HELPER = '/usr/libexec/goodix-manager-helper'
MAX_REPLY = 512 * 1024


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
        if self.busy or action not in {'status', 'install', 'update', 'remove'}:
            return
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
        QDesktopServices.openUrl(QUrl(REPOSITORY + '/issues'))

    @Slot(bool)
    def open_release(self, download):
        if self.release and self.local_package and self.public_status()[0] == 'available':
            QDesktopServices.openUrl(QUrl(self.release.asset_url if download else self.release.page_url))

    @Slot()
    def copy_diagnostics(self):
        diagnostics = self.status.diagnostic() + '\nOperation result: ' + self.last_result + '\nRelease check: ' + self.public_status()[0]
        QGuiApplication.clipboard().setText(diagnostics)


def load_interface(engine):
    # RPM builds normalize mtimes. Read current bytes so an older on-disk QML
    # cache cannot survive a package update; the base URL preserves relative assets.
    path = Path(__file__).with_name('Main.qml')
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
    engine.rootContext().setContextProperty('backend', controller)
    load_interface(engine)
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
