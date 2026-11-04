#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""PASS_SYNTHETIC S1/S4/S5: network reply -> parser -> comparison -> visible QML.

The future release is a public-safe fixture, not an assertion that it exists.
Only Qt network/process/browser boundaries are replaced. Production controller,
parsers, properties, signal delivery, QML actions and safety gates execute as-is.
No real request, helper, package transaction, signature or backend apply is tested.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as manager
from model import LATEST_API, REPOSITORY
from PySide6.QtCore import QByteArray, QIODevice, QMetaObject, QObject, QProcess, QTimer
from PySide6.QtGui import QColor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

FUTURE = json.loads(Path(__file__).with_name('fixtures').joinpath('future-release.json').read_text())
RENDER_DIR = None


def status(**changes):
    data = {'schema': 1, 'state': 'installed', 'runtime_version': '3.0.0',
            'payload_version': '3.0.0', 'package_version': '3.0.0-7.fc44',
            'sensor_present': False, 'message_code': 'up_to_date', 'result': 'success',
            'reboot_required': False, 'enrollment_required': False}
    data.update(changes)
    return data


def release(version='3.0.1', revision=1):
    data = copy.deepcopy(FUTURE)
    old_tag, tag = 'v3.0.1', 'v' + version
    data['tag_name'] = tag
    data['html_url'] = data['html_url'].replace(old_tag, tag)
    name = f'goodix-manager-{version}-{revision}.fc44.x86_64.rpm'
    data['assets'][0]['name'] = name
    data['assets'][0]['browser_download_url'] = REPOSITORY + '/releases/download/' + tag + '/' + name
    return data


class SyntheticReply(QNetworkReply):
    def __init__(self, request, scenario, parent):
        super().__init__(parent)
        self.scenario = scenario
        body = scenario.get('body', FUTURE)
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.offset = 0
        self.setRequest(request)
        self.setUrl(request.url())
        self.setAttribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute, scenario.get('http', 200))
        self.open(QIODevice.OpenModeFlag.ReadOnly)
        error = scenario.get('error', QNetworkReply.NetworkError.NoError)
        if error != QNetworkReply.NetworkError.NoError:
            self.setError(error, 'synthetic transport failure')
        if not scenario.get('stall'):
            QTimer.singleShot(5, self.deliver)

    def readData(self, maximum):
        chunk = self.body[self.offset:self.offset + maximum]
        self.offset += len(chunk)
        return chunk

    def bytesAvailable(self):
        return len(self.body) - self.offset + super().bytesAvailable()

    def deliver(self):
        if self.isFinished():
            return
        self.readyRead.emit()
        if self.isFinished():
            return
        self.setFinished(True)
        self.finished.emit()

    def abort(self):
        self.setError(QNetworkReply.NetworkError.OperationCanceledError, 'synthetic timeout/abort')
        self.deliver()


class SyntheticNetwork(QNetworkAccessManager):
    scenario = {}
    calls = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.replies = []  # Keep Python overrides alive until the manager is destroyed.

    def createRequest(self, operation, request, outgoing_data=None):
        assert operation == QNetworkAccessManager.Operation.GetOperation
        assert request.url().toString() == LATEST_API
        assert not request.hasRawHeader('Authorization')
        assert outgoing_data is None
        type(self).calls.append(request.url().toString())
        reply = SyntheticReply(request, copy.deepcopy(type(self).scenario), self)
        self.replies.append(reply)
        return reply


class SyntheticProcess(QProcess):
    delay_ms = 0
    responses = {}
    calls = []

    def start(self, program, arguments):
        assert program == '/usr/bin/pkexec'
        assert len(arguments) == 2 and arguments[0] == manager.HELPER
        action = arguments[1]
        assert action in type(self).responses, 'Unexpected helper action: ' + action
        type(self).calls.append(action)
        response = copy.deepcopy(type(self).responses[action])
        self.output = json.dumps(response).encode()
        self.exit_value = 0 if response['result'] == 'success' else 1
        if type(self).delay_ms is not None:
            QTimer.singleShot(type(self).delay_ms, self.complete)

    def readAllStandardOutput(self):
        chunk, self.output = self.output, b''
        return QByteArray(chunk)

    def complete(self):
        self.readyReadStandardOutput.emit()
        self.finished.emit(self.exit_value, QProcess.ExitStatus.NormalExit)


class NetworkUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QQuickStyle.setStyle('Fusion')
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(manager, 'QNetworkAccessManager', SyntheticNetwork).start()
        patch.object(manager, 'QProcess', SyntheticProcess).start()
        self.open_url = patch.object(manager.QDesktopServices, 'openUrl', return_value=True).start()
        SyntheticNetwork.scenario = {}
        SyntheticNetwork.calls = []
        SyntheticProcess.responses = {'status': status()}
        SyntheticProcess.calls = []
        SyntheticProcess.delay_ms = 0
        self.clients = []

    def tearDown(self):
        for controller, engine, window in self.clients:
            window.hide()
            controller.network_timeout.stop()
            engine.deleteLater()
            controller.deleteLater()
        self.app.processEvents()

    def wait_for(self, predicate):
        end = time.monotonic() + 2
        while time.monotonic() < end:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.002)
        self.fail('Qt synthetic operation did not complete')

    def client(self, local=None, scenario=None, wait=True):
        SyntheticProcess.responses['status'] = local or status()
        SyntheticNetwork.scenario = scenario or {}
        controller = manager.Controller()
        engine = QQmlApplicationEngine()
        engine.addImportPath('/usr/lib64/qt6/qml')
        engine.rootContext().setContextProperty('backend', controller)
        manager.load_interface(engine)
        self.assertTrue(engine.rootObjects())
        window = engine.rootObjects()[0]
        self.clients.append((controller, engine, window))
        if wait:
            self.wait_for(lambda: not controller.busy and controller.reply is None
                          and controller.remote_state != 'checking')
        return controller, window

    def item(self, window, text):
        # Palette objects also expose a `text` property, as QColor rather than a label.
        return next(obj for obj in window.findChildren(QObject)
                    if isinstance(value := obj.property('text'), str) and value == text)

    def capture(self, window, name):
        if RENDER_DIR:
            settled = time.monotonic() + 0.25
            self.wait_for(lambda: time.monotonic() >= settled)
            self.app.processEvents()
            RENDER_DIR.mkdir(parents=True, exist_ok=True)
            self.assertTrue(window.grabWindow().save(str(RENDER_DIR / (name + '.png'))))

    def assert_banner(self, controller, window, package='3.0.1-1.fc44'):
        self.assertEqual(controller.view['remoteState'], 'available')
        self.assertTrue(controller.view['remoteAvailable'])
        self.assertTrue(self.item(window, 'Software Updates').property('visible'))
        self.assertTrue(self.item(window, 'New public package: ' + package).property('visible'))
        for label in ('Download RPM', 'Release notes'):
            self.assertTrue(self.item(window, label).property('visible'))
        QMetaObject.invokeMethod(self.item(window, 'Download RPM'), 'clicked')
        self.assertEqual(self.open_url.call_args.args[0].toString(), controller.release.asset_url)
        QMetaObject.invokeMethod(self.item(window, 'Release notes'), 'clicked')
        self.assertEqual(self.open_url.call_args.args[0].toString(), controller.release.page_url)

    def test_future_release_visible_for_every_runtime_state(self):
        scenarios = {
            'installed': status(),
            'historical-known': status(runtime_version='3.0.0'),
            'version-unknown': status(state='blocked', runtime_version=None,
                                      message_code='version_unknown', result='blocked'),
            'legacy': status(state='legacy', runtime_version=None,
                             message_code='legacy_upgrade_available', enrollment_required=True),
            'absent': status(state='absent', runtime_version=None, message_code='not_installed'),
            'source-mismatch': status(state='blocked', message_code='source_mismatch', result='blocked'),
            'newer-runtime': status(runtime_version='3.2.0', message_code='downgrade_blocked'),
        }
        for name, local in scenarios.items():
            with self.subTest(state=name):
                controller, window = self.client(local)
                self.assert_banner(controller, window)
                if name == 'version-unknown':
                    self.assertTrue(self.item(window, 'Unknown version').property('visible'))
                elif name == 'legacy':
                    self.assertTrue(self.item(window, 'Earlier driver · version unknown').property('visible'))
                if name in ('version-unknown', 'source-mismatch', 'newer-runtime'):
                    self.assertEqual(controller.view['action'], '')
                    controller.perform('update')
                    self.assertNotIn('update', SyntheticProcess.calls)
                self.capture(window, 'future-' + name)
        self.assertEqual(SyntheticNetwork.calls, [LATEST_API] * len(scenarios))

    def test_release_before_verified_status_updates_banner_without_second_request(self):
        SyntheticProcess.delay_ms = 100
        controller, window = self.client(status(state='blocked', runtime_version=None,
                                               message_code='version_unknown', result='blocked'), wait=False)
        self.wait_for(lambda: controller.release is not None)
        self.assertTrue(controller.busy)
        self.assertIsNone(controller.local_package)
        self.assertFalse(controller.view['remoteAvailable'])
        self.wait_for(lambda: not controller.busy)
        self.assert_banner(controller, window)
        self.assertEqual(SyntheticNetwork.calls, [LATEST_API])
        self.assertEqual(controller.view['action'], '')

    def test_legacy_upgrade_confirmation_preserves_enrollment_warning(self):
        controller, window = self.client(status(state='legacy', runtime_version=None,
                                               message_code='legacy_upgrade_available', enrollment_required=True))
        upgrade = self.item(window, 'Upgrade to 3.0.0')
        self.assertTrue(upgrade.property('enabled'))
        QMetaObject.invokeMethod(upgrade, 'clicked')
        self.app.processEvents()
        dialog = next(obj for obj in window.findChildren(QObject) if obj.property('title') == 'Upgrade to 3.0.0?')
        self.assertTrue(dialog.property('visible'))
        text = dialog.property('contentItem').property('text')
        self.assertIn('enroll every finger again', text)
        self.assertIn('Historical templates and pairing state are preserved', text)
        self.assertEqual(SyntheticProcess.calls, ['status'])
        self.capture(window, 'legacy-confirmation')
        QMetaObject.invokeMethod(dialog, 'close')

    def test_package_transition_exposes_apply_without_implicit_mutation(self):
        controller, window = self.client(status(payload_version='3.0.1', package_version='3.0.1-1.fc44',
                                               message_code='update_available'))
        self.assertEqual(controller.view['runtime'], '3.0.0')
        self.assertEqual(controller.view['action'], 'update')
        self.assertTrue(self.item(window, 'Apply Update').property('enabled'))
        self.assertEqual(SyntheticProcess.calls, ['status'])
        self.assertEqual(controller.view['remoteState'], 'current')
        self.capture(window, 'new-package-old-runtime')
        # The helper boundary result is synthetic; canonical apply is exercised
        # separately by backend tests, not claimed by this GUI contract test.
        SyntheticProcess.responses['update'] = status(runtime_version='3.0.1', payload_version='3.0.1',
                                                      package_version='3.0.1-1.fc44', message_code='installed')
        controller.perform('update')
        self.wait_for(lambda: not controller.busy)
        self.assertEqual(controller.view['runtime'], '3.0.1')
        self.assertEqual(controller.view['action'], '')

    def test_packaging_revision_and_no_downgrade(self):
        for version, revision, expected in [('3.0.0', 8, 'available'), ('3.0.0', 7, 'current'),
                                            ('3.0.0', 6, 'current'), ('2.9.9', 99, 'current')]:
            with self.subTest(version=version, revision=revision):
                controller, window = self.client(scenario={'body': release(version, revision)})
                self.assertEqual(controller.view['remoteState'], expected)
                self.assertEqual(controller.view['action'], '')
                self.assertEqual(self.item(window, 'Download RPM').property('visible'), expected == 'available')

    def test_301_manager_discovers_next_release_with_old_or_current_runtime(self):
        for runtime in ('3.0.0', '3.0.1'):
            with self.subTest(runtime=runtime):
                controller, window = self.client(
                    status(runtime_version=runtime, payload_version='3.0.1',
                           package_version='3.0.1-1.fc44',
                           message_code='update_available' if runtime == '3.0.0' else 'up_to_date'),
                    {'body': release('3.0.2')})
                self.assert_banner(controller, window, '3.0.2-1.fc44')
                self.assertEqual(controller.view['action'], 'update' if runtime == '3.0.0' else '')
                self.assertNotIn('update', SyntheticProcess.calls)

    def test_api_failures_are_unavailable_and_local_actions_survive(self):
        cases = [{'http': code} for code in (403, 404, 429)] + [
            {'error': QNetworkReply.NetworkError.HostNotFoundError},
            {'error': QNetworkReply.NetworkError.TimeoutError}, {'body': b'{broken json'},
            {'body': dict(FUTURE, tag_name='main')}, {'body': dict(FUTURE, draft='false')},
            {'body': dict(FUTURE, tag_name=None)}, {'body': dict(FUTURE, html_url='https://evil.test/release')},
            {'body': b'x' * (manager.MAX_REPLY + 1)}]
        for case in cases:
            with self.subTest(case=case):
                controller, window = self.client(status(state='absent', runtime_version=None), case)
                self.assertEqual(controller.view['remoteState'], 'unavailable')
                self.assertIn('Check unavailable', controller.view['remoteMessage'])
                self.assertFalse(self.item(window, 'Download RPM').property('visible'))
                self.assertTrue(self.item(window, 'Install').property('enabled'))
                controller.copy_diagnostics()
                self.assertIn('Release check: unavailable', self.app.clipboard().text())

    def test_incompatible_incomplete_and_untrusted_assets(self):
        cases = []
        for change in ({'draft': True}, {'prerelease': True}, {'assets': []}):
            cases.append((dict(FUTURE, **change), 'no-compatible'))
        for name in ('goodix-manager-3.0.1-1.src.rpm', 'goodix-manager-3.0.1-1.fc45.x86_64.rpm',
                     'goodix-manager-3.0.1-1.fc44.aarch64.rpm'):
            data = copy.deepcopy(FUTURE)
            data['assets'][0]['name'] = name
            cases.append((data, 'no-compatible'))
        for change, expected in [({'state': 'new'}, 'no-compatible'), ({'size': 0}, 'no-compatible'),
                                 ({'browser_download_url': 'https://evil.test/update.rpm'}, 'unavailable')]:
            data = copy.deepcopy(FUTURE)
            data['assets'][0].update(change)
            cases.append((data, expected))
        duplicate = copy.deepcopy(FUTURE)
        duplicate['assets'].append(copy.deepcopy(duplicate['assets'][0]))
        cases.append((duplicate, 'unavailable'))
        for data, expected in cases:
            with self.subTest(expected=expected, data=data):
                controller, window = self.client(scenario={'body': data})
                self.assertEqual(controller.view['remoteState'], expected)
                self.assertFalse(self.item(window, 'Download RPM').property('visible'))
                self.assertTrue(self.item(window, 'Remove').property('enabled'))
                controller.open_release(True)
                self.open_url.assert_not_called()

    def test_timeout_and_check_again_without_parallel_requests(self):
        controller, window = self.client(scenario={'stall': True}, wait=False)
        self.wait_for(lambda: controller.reply is not None and not controller.busy)
        self.assertTrue(controller.view['remoteChecking'])
        controller.check_releases()
        self.assertEqual(len(SyntheticNetwork.calls), 1)
        controller.network_timeout.timeout.emit()
        self.wait_for(lambda: controller.reply is None)
        self.assertEqual(controller.view['remoteState'], 'unavailable')
        SyntheticNetwork.scenario = {'body': FUTURE}
        QMetaObject.invokeMethod(self.item(window, 'Check again'), 'clicked')
        self.wait_for(lambda: controller.reply is None and controller.remote_state != 'checking')
        self.assertEqual(len(SyntheticNetwork.calls), 2)
        self.assert_banner(controller, window)

    def test_unverified_package_does_not_use_display_metadata_for_comparison(self):
        controller, window = self.client(status(state='blocked', result='blocked', runtime_version=None,
                                               payload_version='', package_version='', message_code='integrity_failed'))
        self.assertIsNone(controller.local_package)
        self.assertEqual(controller.view['remoteState'], 'unavailable')
        self.assertFalse(self.item(window, 'Download RPM').property('visible'))
        controller.open_release(True)
        self.open_url.assert_not_called()

    def test_update_indicator_and_labels_follow_public_result_only(self):
        cases = {
            'current': {'body': release('3.0.0', 7)},
            'available': {'body': FUTURE},
            'checking': {'stall': True},
            'no-compatible': {'body': dict(FUTURE, assets=[])},
            'unavailable': {'error': QNetworkReply.NetworkError.HostNotFoundError},
        }
        for expected, scenario in cases.items():
            with self.subTest(state=expected):
                controller, window = self.client(scenario=scenario, wait=expected != 'checking')
                self.wait_for(lambda: not controller.busy)
                self.assertEqual(controller.view['remoteState'], expected)
                indicator = window.findChild(QObject, 'softwareUpdatesIndicator')
                color = {'current': QColor('#27ae60'), 'available': QColor('#e5a24b')}.get(
                    expected, window.property('lineColor'))
                self.assertEqual(indicator.property('color'), color)
                self.assertTrue(self.item(window, 'Software Updates').property('visible'))
                self.assertTrue(self.item(window, 'This RPM').property('visible'))
                self.assertTrue(self.item(window, controller.view['remoteMessage']).property('visible'))
                labels = [obj.property('text') for obj in window.findChildren(QObject)]
                for old in ('Local payload', 'Public releases', 'USB reader', 'Not connected'):
                    self.assertNotIn(old, labels)
                for label in ('Download RPM', 'Release notes'):
                    self.assertEqual(self.item(window, label).property('visible'), expected == 'available')
                self.assertEqual(self.item(window, 'Check again').property('enabled'), expected != 'checking')
                if expected in ('checking', 'no-compatible', 'unavailable'):
                    self.assertNotEqual(color, QColor('#27ae60'))
                    self.assertNotIn('current', controller.view['remoteMessage'].lower())
                self.capture(window, 'indicator-' + expected)

    def test_driver_spinner_and_cleanup_for_all_lifecycle_results(self):
        cases = {
            'install': ('install', status(state='absent', runtime_version=None, message_code='not_installed')),
            'update': ('update', status(runtime_version='2.9.0', message_code='update_available')),
            'legacy': ('update', status(state='legacy', runtime_version=None,
                                       message_code='legacy_upgrade_available', enrollment_required=True)),
            'remove': ('remove', status()),
        }
        for name, (action, local) in cases.items():
            for result in ('success', 'failed', 'blocked', 'rolled_back'):
                with self.subTest(action=name, result=result):
                    SyntheticProcess.delay_ms = 0
                    controller, window = self.client(local)
                    spinner = window.findChild(QObject, 'driverBusyIndicator')
                    self.assertFalse(spinner.property('visible'))
                    self.assertFalse(spinner.property('running'))
                    self.assertFalse(any('ProgressBar' in obj.metaObject().className()
                                         for obj in window.findChildren(QObject)))
                    SyntheticProcess.responses[action] = status(result=result, message_code='ready')
                    SyntheticProcess.delay_ms = None  # Complete only after inspecting the active UI.
                    controller.perform(action)
                    self.app.processEvents()
                    self.assertTrue(spinner.property('visible'))
                    self.assertTrue(spinner.property('running'))
                    self.assertTrue(self.item(window, controller.notice).property('visible'))
                    self.assertTrue(self.item(window, 'Do not close Goodix Manager or interrupt the operation.').property('visible'))
                    for label in ('Verify status', 'Remove', 'Upgrade to 3.0.0' if name == 'legacy'
                                  else 'Apply Update' if name == 'update' else 'Install'):
                        self.assertFalse(self.item(window, label).property('enabled'))
                    self.assertNotIn('%', controller.notice)
                    if result == 'success':
                        self.capture(window, 'spinner-' + name)
                    self.assertFalse(window.close(), 'Lifecycle must reject closing the window')
                    busy_dialog = next(obj for obj in window.findChildren(QObject)
                                       if obj.property('title') == 'Operation in progress')
                    self.assertTrue(busy_dialog.property('visible'))
                    QMetaObject.invokeMethod(busy_dialog, 'close')
                    controller.process.complete()
                    self.wait_for(lambda: not controller.busy)
                    self.assertFalse(spinner.property('visible'))
                    self.assertFalse(spinner.property('running'))
                    self.assertFalse(self.item(window, 'Do not close Goodix Manager or interrupt the operation.').property('visible'))
                    self.assertTrue(self.item(window, controller.notice).property('visible'))
                    self.assertTrue(self.item(window, 'Verify status').property('enabled'))
                    self.assertEqual(controller.last_result, result)
                    controller.copy_diagnostics()
                    self.assertIn('Operation result: ' + result, self.app.clipboard().text())
                    self.assertIn('"sensor_present": false', self.app.clipboard().text())
                    self.assertTrue(window.close(), 'Completed operation must allow closing')

    def test_status_spinner_and_failed_process_cleanup(self):
        controller, window = self.client(status(state='absent', runtime_version=None))
        spinner = window.findChild(QObject, 'driverBusyIndicator')
        SyntheticProcess.delay_ms = None
        controller.refresh()
        self.app.processEvents()
        self.assertTrue(controller.busy)
        self.assertTrue(spinner.property('visible'))
        self.assertTrue(spinner.property('running'))
        self.assertFalse(self.item(window, 'Do not close Goodix Manager or interrupt the operation.').property('visible'))
        controller.process.complete()
        self.wait_for(lambda: not controller.busy)
        self.assertFalse(spinner.property('visible'))
        self.assertFalse(spinner.property('running'))
        SyntheticProcess.responses['install'] = status()
        controller.perform('install')
        self.assertTrue(spinner.property('visible'))
        self.assertTrue(spinner.property('running'))
        controller.process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        self.app.processEvents()
        self.assertFalse(controller.busy)
        self.assertFalse(spinner.property('visible'))
        self.assertFalse(spinner.property('running'))
        self.assertTrue(self.item(window, controller.notice).property('visible'))
        self.assertEqual(controller.last_result, 'helper_unavailable')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-dir', type=Path)
    options, remaining = parser.parse_known_args()
    RENDER_DIR = options.render_dir
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
