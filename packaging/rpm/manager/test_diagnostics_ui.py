#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline Controller/Qt contracts; all collectors, buses and save dialogs are fake."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as manager
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal, QPointF, QTimer, Qt
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from test_ui import system_palette

QQuickStyle.setStyle('Fusion')
RENDER_DIR = None


class FakeReader(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = {'busy': False, 'state': 'idle', 'message': 'Ready to check the reader', 'attempts': 0, 'canStart': True, 'canNewTest': False}
        self.calls = []

    def start(self, consent):
        self.calls.append(consent)
        self.view.update(busy=consent, state='checking' if consent else 'unavailable',
                         message='Waiting for a finger' if consent else 'Consent required')
        self.changed.emit()

    def cancel(self):
        self.view.update(busy=False, state='cancelled', message='Test cancelled')
        self.changed.emit()

    def shutdown(self):
        self.cancel()

    def new_test(self):
        if not self.view.get('canNewTest') or self.view['busy']:
            return False
        self.view.update(state='idle', attempts=0, canStart=True, canNewTest=False)
        self.changed.emit()
        return True


def report_result(**updates):
    result = {'checks': [], 'overview': 'Some checks could not be completed',
              'generatedAt': '2026-11-08T12:00:00Z', 'reportReady': True,
              'reportText': 'OFFLINE SYNTHETIC REPORT\nNo host data collected.\n',
              'reportTitle': 'System status', 'reportSummary': 'Read-only synthetic evidence.',
              'reportError': ''}
    result.update(updates)
    return result


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(manager.Controller, 'refresh', lambda self: None).start()
        patch.object(manager.Controller, 'check_releases', lambda self: None).start()
        patch.object(manager, 'ReaderSession', FakeReader).start()
        self.collect_checks = patch.object(manager.diagnostic_tools, 'collect_checks',
                                           return_value=report_result(reportReady=False, reportText='')).start()
        self.collect_report = patch.object(manager.diagnostic_tools, 'collect_report',
                                           return_value=report_result()).start()
        self.controller = manager.Controller()
        self.app.processEvents()  # Consume only the neutralized startup callbacks.

    def tearDown(self):
        self.controller.cancel_diagnostics()
        self.wait(lambda: self.controller._diagnostic_thread is None)
        self.controller.deleteLater()
        self.app.processEvents()

    def wait(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.002)
        self.fail('Synthetic Qt operation did not complete')

    def create_report(self):
        self.controller.create_diagnostic_report('system', 'current', False, True, '', '')
        self.wait(lambda: not self.controller.diagnostics['busy'])

    def test_opening_controller_does_not_collect_or_access_reader(self):
        self.collect_checks.assert_not_called()
        self.collect_report.assert_not_called()
        self.assertEqual(self.controller.reader.calls, [])
        self.assertFalse(self.controller.diagnostics['reportReady'])

    def test_report_requires_consent_even_with_direct_slot_call(self):
        self.controller.create_diagnostic_report('login', 'previous', True, False, '', '')
        self.collect_report.assert_not_called()
        self.assertFalse(self.controller.diagnostics['reportReady'])
        self.assertIn('Consent', self.controller.diagnostics['reportError'])

    def test_options_change_or_cancel_discards_previous_export(self):
        self.create_report()
        self.assertTrue(self.controller.diagnostics['reportReady'])
        self.controller.invalidate_diagnostic_report()
        self.assertFalse(self.controller.diagnostics['reportReady'])
        self.assertEqual(self.controller.diagnostics['reportText'], '')
        self.create_report()
        self.controller.cancel_diagnostics()
        self.assertFalse(self.controller.diagnostics['reportReady'])

    def test_worker_is_async_and_cancellation_discards_late_result(self):
        started, release = Event(), Event()
        def slow(**kwargs):
            started.set()
            release.wait(2)
            return report_result()
        self.collect_checks.side_effect = slow
        self.controller.run_diagnostics()
        try:
            self.assertTrue(self.controller.diagnostics['busy'])
            self.assertTrue(started.wait(.5))
            self.controller.run_diagnostics()
            self.controller.start_reader_test(True)
            self.assertEqual(self.controller.reader.calls, [])
            self.controller.run('status')
            self.assertIsNone(self.controller.process)
            self.controller.cancel_diagnostics()
        finally:
            release.set()
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertFalse(self.controller.diagnostics['reportReady'])
        self.assertEqual(self.collect_checks.call_count, 1)

    def test_lifecycle_and_reader_exclude_collectors(self):
        self.controller.busy = True
        self.controller.run_diagnostics()
        self.controller.start_reader_test(True)
        self.assertFalse(self.controller.diagnostics['busy'])
        self.assertEqual(self.controller.reader.calls, [])
        self.controller.busy = False
        self.controller.start_reader_test(True)
        self.assertTrue(self.controller.diagnostics['busy'])
        self.controller.run_diagnostics()
        self.collect_checks.assert_not_called()
        self.controller.cancel_reader_test()
        self.assertFalse(self.controller.diagnostics['busy'])

    def test_copy_and_save_require_fresh_preview_and_use_private_writer(self):
        with patch.object(manager.QFileDialog, 'getSaveFileName', return_value=('/fake/new.txt', '')) as dialog, \
             patch.object(manager.diagnostic_tools, 'save_report') as save:
            self.controller.save_diagnostic_report()
            dialog.assert_not_called()
            self.create_report()
            self.controller.copy_diagnostic_report()
            self.assertIn('OFFLINE SYNTHETIC', self.app.clipboard().text())
            self.controller.save_diagnostic_report()
            save.assert_called_once_with('/fake/new.txt', self.controller.diagnostics['reportText'])
            self.controller.invalidate_diagnostic_report()
            self.controller.save_diagnostic_report()
            self.assertEqual(dialog.call_count, 1)

    def test_save_dialog_cancel_and_existing_file_failure_are_safe(self):
        self.create_report()
        with patch.object(manager.QFileDialog, 'getSaveFileName', return_value=('', '')), \
             patch.object(manager.diagnostic_tools, 'save_report') as save:
            self.controller.save_diagnostic_report()
            save.assert_not_called()
        with patch.object(manager.QFileDialog, 'getSaveFileName', return_value=('/fake/existing.txt', '')), \
             patch.object(manager.diagnostic_tools, 'save_report', side_effect=FileExistsError):
            self.controller.save_diagnostic_report()
            self.assertIn('Choose a new file', self.controller.diagnostics['reportError'])
            self.assertTrue(self.controller.diagnostics['reportReady'])

    def test_exceptions_do_not_export_internal_output(self):
        self.collect_checks.side_effect = RuntimeError('PROTECTED_TOKEN_MUST_NOT_ESCAPE')
        self.controller.run_diagnostics()
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertFalse(self.controller.diagnostics['reportReady'])
        self.assertNotIn('PROTECTED_TOKEN', str(self.controller.diagnostics))
        self.assertIn('could not be collected', self.controller.diagnostics['reportError'])

    def test_cached_status_and_operation_keep_time_and_original_code(self):
        self.controller.status_observed_at = '2026-11-08T12:00:00+00:00'
        self.controller.last_operation = {'action': 'install', 'result': 'failed',
            'message_code': 'operation_failed', 'observedAt': '2026-11-08T11:50:00+00:00'}
        self.create_report()
        snapshot = self.collect_report.call_args.kwargs['status_snapshot']
        self.assertIs(snapshot['status'], self.controller.status)
        self.assertEqual(snapshot['observedAt'], '2026-11-08T12:00:00+00:00')
        self.assertEqual(snapshot['lastOperation']['message_code'], 'operation_failed')
        self.assertNotIn('Cached software', self.controller.diagnostics['reportText'])

    def test_close_waits_for_worker_and_discards_late_result(self):
        started, release = Event(), Event()
        def slow(**kwargs):
            started.set()
            release.wait(2)
            return report_result()
        self.collect_checks.side_effect = slow
        self.controller.run_diagnostics()
        try:
            self.assertTrue(started.wait(.5))
            self.assertFalse(self.controller.request_close())
            self.assertFalse(self.controller.closeReady)
            self.assertTrue(self.controller._diagnostic_cancel.is_set())
            self.controller.start_reader_test(True)
            self.assertEqual(self.controller.reader.calls, [])
        finally:
            release.set()
        self.wait(lambda: self.controller.closeReady)
        self.assertIsNone(self.controller._diagnostic_thread)
        self.assertFalse(self.controller.diagnostics['reportReady'])

    def test_close_releases_pending_reader_and_refuses_lifecycle_close(self):
        self.controller.busy = True
        self.assertFalse(self.controller.request_close())
        self.assertFalse(self.controller._shutdown_requested)
        self.controller.busy = False
        self.controller.start_reader_test(True)
        self.assertTrue(self.controller.diagnostics['readerBusy'])
        with patch.object(self.controller.reader, 'shutdown', wraps=self.controller.reader.shutdown) as shutdown:
            self.assertTrue(self.controller.request_close())
            shutdown.assert_called_once()
        self.assertFalse(self.controller.diagnostics['readerBusy'])
        self.assertTrue(self.controller.closeReady)

    def test_new_failure_denial_and_cancel_clear_previous_check_results(self):
        previous = report_result(checks=[{'id': 'service', 'title': 'Fingerprint service',
            'outcome': 'pass', 'summary': 'Package configuration checked', 'detail': 'Previous result', 'code': 'service_checked'}],
            overview='Previous completed checks')
        self.collect_checks.return_value = previous
        self.controller.run_diagnostics()
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertTrue(self.controller.diagnostics['checks'])
        self.collect_checks.side_effect = RuntimeError('PRIVATE_FAILURE_DETAIL')
        self.controller.run_diagnostics()
        self.assertEqual(self.controller.diagnostics['checks'], [])
        self.assertEqual(self.controller.diagnostics['generatedAt'], '')
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertIn('No new', self.controller.diagnostics['overview'])
        self.assertIn('could not be collected', self.controller.diagnostics['reportError'])
        self.assertNotIn('PRIVATE_FAILURE', str(self.controller.diagnostics))
        for action in ('denied', 'invalid', 'cancel'):
            self.controller._diagnostic_data.update(previous)
            if action == 'denied':
                self.controller.create_diagnostic_report('login', 'current', False, False, '', '')
            elif action == 'invalid':
                self.collect_report.return_value = {'reportReady': False, 'reportText': '', 'reportError': 'Invalid time selection.'}
                self.controller.create_diagnostic_report('login', 'custom', False, True, 'invalid', '')
                self.wait(lambda: not self.controller.diagnostics['busy'])
            else:
                self.controller.cancel_diagnostics()
            self.assertEqual(self.controller.diagnostics['checks'], [], action)
            self.assertEqual(self.controller.diagnostics['generatedAt'], '', action)
            self.assertFalse(self.controller.diagnostics['reportReady'], action)

    def test_installation_time_requires_a_valid_session_install_or_update(self):
        self.assertFalse(self.controller.diagnostics['installationTimeAvailable'])
        now = datetime.now(timezone.utc)
        def operation(action='install', stamp=None):
            return {'action': action, 'result': 'failed', 'message_code': 'operation_failed',
                    'observedAt': stamp or (now - timedelta(minutes=5)).isoformat()}
        for action in ('install', 'update'):
            self.controller.last_operation = operation(action)
            self.assertTrue(self.controller.diagnostics['installationTimeAvailable'], action)
        for item in (operation('remove'), operation(stamp='malformed'),
                     operation(stamp=(now + timedelta(seconds=1)).isoformat())):
            self.controller.last_operation = item
            self.assertFalse(self.controller.diagnostics['installationTimeAvailable'], item)

    def test_local_date_time_rejects_clock_gaps_folds_and_preserves_range_contract(self):
        convert = lambda y, m, d, h, minute: manager.local_report_time(y, m, d, h, minute, 'Europe/Rome')
        self.assertTrue(convert(2026, 3, 29, 2, 30)['error'], 'Spring gap must not silently move to 03:30')
        self.assertTrue(convert(2026, 10, 25, 2, 30)['error'], 'Autumn fold must not choose one offset')
        self.assertTrue(convert(2026, 2, 30, 12, 0)['error'])
        self.assertIn('+01:00', convert(2026, 11, 10, 12, 0)['iso'])
        self.assertIn('+02:00', convert(2026, 7, 10, 12, 0)['iso'])
        now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        for start, end in (((2026, 11, 10, 12, 0), (2026, 11, 10, 13, 0)),
                           ((2026, 11, 10, 23, 0), (2026, 11, 11, 1, 0)),
                           ((2026, 11, 10, 12, 0), (2026, 11, 11, 12, 0))):
            manager.diagnostic_tools.time_arguments('custom', convert(*start)['iso'], convert(*end)['iso'], now)
        for start, end in (((2026, 11, 10, 13, 0), (2026, 11, 10, 12, 0)),
                           ((2026, 11, 10, 12, 0), (2026, 11, 11, 12, 1)),
                           ((2026, 11, 12, 12, 0), (2026, 11, 12, 15, 0))):
            with self.assertRaises(ValueError):
                manager.diagnostic_tools.time_arguments('custom', convert(*start)['iso'], convert(*end)['iso'], now)


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        ControllerTests.setUp(self)
        self.controller.status = manager.Status.parse({'schema': 1, 'state': 'installed',
            'runtime_version': '3.0.1', 'payload_version': '3.0.1', 'package_version': '3.0.1-4.fc44',
            'sensor_present': None, 'message_code': 'up_to_date'})
        self.controller.notice = 'The installed driver matches the local payload.'
        self.controller.remote_state = 'current'
        self.controller.remote_message = 'Manager package is current · latest compatible public package: 3.0.1-4.fc44'
        self.app.setPalette(system_palette(True))
        self.engine = QQmlApplicationEngine()
        self.engine.addImportPath('/usr/lib64/qt6/qml')
        self.engine.rootContext().setContextProperty('backend', self.controller)
        manager.load_interface(self.engine)
        self.assertTrue(self.engine.rootObjects())
        self.window = self.engine.rootObjects()[0]
        self.wait(lambda: self.window.property('initialHomeFitDone'))
        self.window.setWidth(1040)
        self.window.setHeight(900)
        QTest.qWait(200)

    def tearDown(self):
        self.window.hide()
        clear = QQmlExpression(QQmlEngine.contextForObject(self.window), self.window, 'void pageStack.clear()')
        clear.evaluate()
        self.assertFalse(clear.hasError(), clear.error().toString())
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.engine.deleteLater()
        self.app.processEvents()
        ControllerTests.tearDown(self)

    wait = ControllerTests.wait
    create_report = ControllerTests.create_report

    def item(self, name):
        item = self.window.findChild(QObject, name)
        if item is None:
            # Repeater delegates belong to a visual parent without necessarily
            # belonging to its QObject tree. Traverse in QML so PySide does not
            # wrap every private inline type from successive temporary engines.
            source = '''(function() {
                const pending = [contentItem, Controls.Overlay.overlay];
                while (pending.length) {
                    const candidate = pending.pop();
                    if (candidate.objectName === %s) return candidate;
                    for (const child of candidate.children) pending.push(child);
                }
                return null;
            })()''' % json.dumps(name)
            expression = QQmlExpression(QQmlEngine.contextForObject(self.window), self.window, source)
            item, _undefined = expression.evaluate()
            self.assertFalse(expression.hasError(), expression.error().toString())
        self.assertIsNotNone(item, name)
        return item

    def click(self, name):
        item = self.item(name)
        self.assertTrue(item.property('enabled'), name + ' is disabled')
        self.assertTrue(item.property('visible'), name + ' is hidden')
        page = self.window.findChild(QObject, 'diagnosticPage')
        if page is not None and name not in ('reportConsent', 'createReport', 'cancelConsent'):
            viewport = page.property('scrollViewport')
            point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
            if viewport is not None and (point.y() < 100 or point.y() > self.window.height() - 35):
                viewport.setProperty('contentY', max(0, viewport.property('contentY') + point.y() - self.window.height() / 2))
                QTest.qWait(70)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        self.assertTrue(0 <= point.x() < self.window.width() and 0 <= point.y() < self.window.height(),
                        name + ' outside viewport: ' + str((point.x(), point.y(), self.window.width(), self.window.height())))
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        QTest.qWait(100)

    def open_center(self):
        self.click('openDiagnosticCenter')
        self.wait(lambda: self.window.findChild(QObject, 'diagnosticPage') is not None)
        QTest.qWait(300)
        return self.item('diagnosticPage')

    def screen(self):
        return self.item('diagnosticPage').property('screen')

    def qml_value(self, source):
        page = self.item('diagnosticPage')
        expression = QQmlExpression(QQmlEngine.contextForObject(page), page, source)
        value, _undefined = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def visual_value(self, name, attribute):
        # Inline QML type metadata belongs to its temporary engine. Read scalar
        # values without creating Python wrappers for those private types.
        return self.qml_value('''(function() {
            const pending = [page, Controls.Overlay.overlay];
            while (pending.length) {
                const candidate = pending.pop();
                if (candidate.objectName === %s) return candidate[%s];
                for (const child of candidate.children) pending.push(child);
            }
            throw new Error("Missing visual item");
        })()''' % (json.dumps(name), json.dumps(attribute)))

    def choose_time(self, index):
        self.click('reportTime')
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        for _ in range(index):
            QTest.keyClick(self.window, Qt.Key.Key_Down)
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        QTest.qWait(100)
        self.assertEqual(self.item('reportTime').property('currentIndex'), index)

    def snapshot(self, name):
        QTest.qWait(150)
        image = self.window.grabWindow()
        self.assertFalse(image.isNull())
        if RENDER_DIR:
            RENDER_DIR.mkdir(parents=True, exist_ok=True)
            self.assertTrue(image.save(str(RENDER_DIR / (name + '.png'))))

    def test_navigation_checks_and_back_without_automatic_collection(self):
        self.snapshot('01-manager-dark')
        self.open_center()
        self.assertEqual(self.screen(), 'dashboard')
        self.collect_checks.assert_not_called()
        self.collect_report.assert_not_called()
        self.snapshot('02-overview-dark')
        self.click('chooseChecks')
        self.assertEqual(self.screen(), 'checks')
        self.click('check-driver')
        self.assertTrue(self.item('detail-driver').property('visible'))
        self.snapshot('03-checks-dark')
        self.click('diagnosticBack')
        self.click('chooseProblem')
        self.assertEqual(self.screen(), 'choose')
        self.snapshot('04-problems-dark')
        for name, profile in [('problemInstall', 'install'), ('problemLogin', 'login'),
                              ('problemRecognition', 'recognition'), ('problemOther', 'other')]:
            self.click(name)
            self.assertEqual(self.screen(), 'prepare')
            self.assertEqual(self.item('diagnosticPage').property('profile'), profile)
            self.click('diagnosticBack')
        self.click('diagnosticBack')
        self.click('diagnosticBack')
        QTest.qWait(300)
        self.assertTrue(self.item('openDiagnosticCenter').property('visible'))

    def test_privacy_cancel_escape_consent_preview_copy_save_and_invalidation(self):
        self.open_center()
        self.click('chooseProblem')
        self.click('problemLogin')
        self.snapshot('05-prepare-dark')
        self.click('continueReport')
        self.assertFalse(self.item('createReport').property('enabled'))
        self.snapshot('06-consent-dark')
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        QTest.qWait(100)
        self.collect_report.assert_not_called()
        self.click('continueReport')
        self.click('cancelConsent')
        self.collect_report.assert_not_called()
        self.click('continueReport')
        self.click('reportConsent')
        self.click('createReport')
        self.wait(lambda: self.screen() == 'preview')
        self.assertTrue(self.controller.diagnostics['reportReady'])
        self.collect_report.assert_called_once()
        self.assertEqual(self.collect_report.call_args.args[:4], ('login', 'current', False, True))
        self.snapshot('07-preview-dark')
        self.click('copyReport')
        self.assertIn('OFFLINE SYNTHETIC', self.app.clipboard().text())
        with patch.object(manager.QFileDialog, 'getSaveFileName', return_value=('/fake/new-report.txt', '')), \
             patch.object(manager.diagnostic_tools, 'save_report') as save:
            self.click('saveReport')
            save.assert_called_once()
        self.click('previewBack')
        self.assertEqual(self.screen(), 'prepare')
        self.assertFalse(self.controller.diagnostics['reportReady'])
        self.click('extendedDetails')
        self.choose_time(4)
        self.assertTrue(self.qml_value('reportSince.visible'))
        self.assertTrue(self.qml_value('reportUntil.visible'))

    def test_real_collector_issue55_to_qml_preview_excludes_hostile_raw_data(self):
        from test_diagnostics import Fixtures, SERVICE, event
        from diagnostics import Result
        fixture = Fixtures()
        fixture.results[('/usr/bin/rpm', '-V', '--noscripts', '--nodeps', 'libfprint')] = Result(1, 'missing     /usr/lib64/libfprint-2.so.2\n')
        service_args = ('/usr/bin/systemctl', 'show', 'fprintd.service', '--property=LoadState,ActiveState,SubState,FragmentPath,ExecStart,DropInPaths,Environment')
        fixture.results[service_args] = Result(stdout=SERVICE.replace('DropInPaths=', 'DropInPaths=/etc/systemd/system/fprintd.service.d/keepalive.conf'))
        original = fixture.run
        def command(args, timeout=5):
            if args[0] == '/usr/bin/journalctl':
                return Result(stdout=event('PRIVATE_HOSTILE_MARKER psk=DO_NOT_EXPORT'))
            return original(args, timeout)
        fixture.run = command
        def collect(*args, **kwargs):
            return fixture.collector(cancel=kwargs.pop('cancel', None)).report(*args, **kwargs)
        self.collect_report.side_effect = collect
        self.open_center()
        self.click('chooseProblem')
        self.click('problemInstall')
        self.choose_time(0)
        self.click('continueReport')
        self.click('reportConsent')
        self.click('createReport')
        self.wait(lambda: self.screen() == 'preview')
        text = self.item('reportPreview').property('text')
        self.assertIn('service_override_unrecognized', text)
        self.assertIn('libfprint_missing_files', text)
        self.assertNotIn('PRIVATE_HOSTILE_MARKER', text)
        self.assertNotIn('DO_NOT_EXPORT', text)
        self.assertNotIn('Installation not activated', text)
        override = self.item('finding-detail-service')
        missing = self.item('finding-detail-components')
        self.assertTrue(override.property('visible'))
        self.assertTrue(missing.property('visible'))
        self.assertIn('keepalive.conf', override.property('text'))
        self.assertIn('missing files', missing.property('text'))
        self.snapshot('07-preview-issue55-real-collector-dark')

    def test_reader_requires_consent_and_cancel_is_explicit(self):
        self.open_center()
        self.click('chooseReader')
        self.assertEqual(self.screen(), 'test')
        self.assertFalse(self.item('readerStart').property('enabled'))
        self.assertEqual(self.controller.reader.calls, [])
        self.snapshot('08-reader-dark')
        self.click('readerConsent')
        self.click('readerStart')
        self.assertEqual(self.controller.reader.calls, [True])
        self.assertTrue(self.controller.diagnostics['readerBusy'])
        self.assertFalse(self.item('diagnosticBack').property('enabled'))
        self.click('readerCancel')
        self.assertFalse(self.controller.diagnostics['readerBusy'])
        self.controller.reader.view.update(state='timeout', canStart=False, message='The reader test timed out.')
        self.controller.reader.changed.emit()
        self.app.processEvents()
        self.assertEqual(self.item('readerHeading').property('text'), 'Reader test stopped')
        self.assertFalse(self.item('readerStart').property('enabled'))
        self.click('diagnosticBack')
        self.assertEqual(self.screen(), 'dashboard')

    def test_reader_new_session_requires_clean_release_new_consent_and_no_automatic_request(self):
        from reader import ReaderSession, TARGET_NAME
        from test_reader import FakeTransport, PATH
        transports = []
        def factory():
            transport = FakeTransport()
            transports.append(transport)
            return transport
        self.controller.reader.shutdown()
        self.controller.reader = ReaderSession(self.controller, transport_factory=factory)
        self.controller.reader.changed.connect(self.controller.changed)
        self.open_center()
        self.click('chooseReader')
        self.click('readerConsent')
        self.click('readerStart')
        transport = transports[0]
        for method, values in (('GetDevices', [[PATH]]), ('Get', [TARGET_NAME]), ('Claim', []), ('VerifyStart', [])):
            transport.reply(method, values)
        transport.emit('verify-match')
        self.assertFalse(self.controller.new_reader_test(), 'Pending cleanup must not reset')
        transport.reply('VerifyStop')
        transport.reply('Release')
        self.app.processEvents()
        self.assertFalse(self.item('readerStart').property('enabled'))
        self.assertTrue(self.item('readerNewTest').property('enabled'))
        self.snapshot('18-reader-match-new-session-dark')
        self.click('readerNewTest')
        self.assertEqual(len(transports), 1)
        self.assertEqual(self.controller.reader.view['attempts'], 0)
        self.assertFalse(self.item('readerConsent').property('checked'))
        self.assertFalse(self.item('readerStart').property('enabled'))
        self.click('readerConsent')
        self.click('readerStart')
        self.assertEqual(len(transports), 2)
        self.controller.reader.timeout()
        self.app.processEvents()
        self.assertFalse(self.item('readerNewTest').property('visible'))
        self.assertFalse(self.controller.new_reader_test())
        self.click('diagnosticBack')
        self.click('chooseReader')
        self.assertFalse(self.item('readerStart').property('enabled'))
        self.assertEqual(len(transports), 2, 'Page re-entry must not replay requests')

    def test_custom_calendar_local_time_to_real_bounded_collector_and_dst(self):
        from test_diagnostics import Fixtures
        fixture = Fixtures()
        self.collect_report.side_effect = lambda *args, **kwargs: fixture.collector(cancel=kwargs.pop('cancel', None)).report(*args, **kwargs)
        with patch.object(manager.QTimeZone, 'systemTimeZoneId', return_value=b'Europe/Rome'):
            self.open_center()
            self.click('chooseProblem')
            self.click('problemLogin')
            self.choose_time(4)
            def select(name, day, hour, minute, month=10):
                self.qml_value('%s.selectedDate = new Date(2026, %d, %d); %s.hour = %d; %s.minute = %d; undefined' %
                               (name, month, day, name, hour, name, minute))
                self.app.processEvents()
            def choose_day(name):
                self.assertTrue(self.visual_value(name, 'visible'))
                self.assertTrue(self.visual_value(name, 'enabled'))
                point = self.qml_value('''(function() {
                    const pending = [Controls.Overlay.overlay];
                    while (pending.length) {
                        const item = pending.pop();
                        if (item.objectName === %s) return item.mapToItem(null, item.width / 2, item.height / 2);
                        for (const child of item.children) pending.push(child);
                    }
                    return null;
                })()''' % json.dumps(name))
                self.assertIsNotNone(point)
                self.assertTrue(0 <= point.x() < self.window.width() and 0 <= point.y() < self.window.height())
                QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint())
                QTest.qWait(100)
            select('reportSince', 7, 22, 0)
            select('reportUntil', 8, 0, 0)
            self.click('reportSinceDate')
            self.assertTrue(self.item('reportSinceCalendar').property('visible'))
            self.snapshot('19-calendar-dark')
            choose_day('reportSinceDay-2026-10-6')
            self.assertIn('2026-11-06', self.qml_value('reportSince.iso'))
            self.item('reportSinceHour').forceActiveFocus()
            QTest.keyClick(self.window, Qt.Key.Key_Up)
            self.item('reportSinceMinute').forceActiveFocus()
            QTest.keyClick(self.window, Qt.Key.Key_Up)
            self.app.processEvents()
            self.assertIn('T23:01:00', self.qml_value('reportSince.iso'))
            self.click('reportSinceDate')
            choose_day('reportSinceDay-2026-10-7')
            self.click('continueReport')
            self.assertFalse(self.item('createReport').property('enabled'))
            self.click('reportConsent')
            self.click('createReport')
            self.wait(lambda: self.screen() == 'preview')
            args = self.collect_report.call_args.args
            self.assertEqual(args[1], 'custom')
            self.assertEqual(args[4:6], ('2026-11-07T23:01:00+01:00', '2026-11-08T00:00:00+01:00'))
            self.click('previewBack')
            select('reportSince', 29, 2, 30, 2)
            self.assertFalse(self.item('continueReport').property('enabled'))
            self.assertIn('does not exist', self.item('reportSinceError').property('text'))
            select('reportSince', 25, 2, 30, 9)
            self.assertIn('occurs twice', self.item('reportSinceError').property('text'))
            self.assertFalse(self.controller.diagnostics['reportReady'])
            select('reportSince', 7, 10, 0)
            select('reportUntil', 8, 10, 1)
            self.click('continueReport')
            self.click('reportConsent')
            self.click('createReport')
            self.wait(lambda: not self.controller.diagnostics['busy'])
            self.assertFalse(self.controller.diagnostics['reportReady'])
            self.assertIn('24 hours', self.controller.diagnostics['reportError'])
            self.app.setPalette(system_palette(False))
            self.window.setWidth(560)
            self.snapshot('20-custom-time-compact-light')

    def test_denied_report_and_light_compact_render(self):
        self.collect_report.return_value = report_result(reportReady=False, reportText='', reportError='History is unavailable: permission denied.')
        self.open_center()
        self.click('chooseProblem')
        self.click('problemLogin')
        self.click('continueReport')
        self.click('reportConsent')
        self.click('createReport')
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertEqual(self.screen(), 'prepare')
        self.assertFalse(self.controller.diagnostics['reportReady'])
        self.snapshot('09-history-denied-dark')
        self.app.setPalette(system_palette(False))
        self.snapshot('10-prepare-light')
        self.assertEqual(self.window.property('surfaceColor'), system_palette(False).color(system_palette(False).ColorRole.Window))
        self.window.setWidth(520)
        self.window.setHeight(560)
        QTest.qWait(150)
        self.snapshot('11-prepare-compact-light')
        self.click('diagnosticBack')
        self.click('diagnosticBack')
        self.app.setPalette(system_palette(True))
        self.snapshot('12-overview-compact-dark')

    def test_window_close_waits_for_collection_and_cancels_late_preview(self):
        started, release = Event(), Event()
        def slow(**kwargs):
            started.set()
            release.wait(2)
            return report_result()
        self.collect_checks.side_effect = slow
        self.open_center()
        self.click('overviewRunChecks')
        self.assertTrue(started.wait(.5))
        try:
            self.assertFalse(self.window.close())
            self.assertTrue(self.window.property('closePending'))
            self.assertTrue(self.controller._diagnostic_cancel.is_set())
        finally:
            release.set()
        self.wait(lambda: self.controller.closeReady)
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.controller.diagnostics['reportReady'])

    def test_native_page_stack_pop_during_collection_cancels_removed_page(self):
        def destruction_events(item):
            events = []
            item.destroyed.connect(lambda: events.append(True))
            return events
        started, release = Event(), Event()
        def slow(**kwargs):
            started.set()
            release.wait(2)
            return report_result()
        self.collect_checks.side_effect = slow
        self.open_center()
        removed = destruction_events(self.item('diagnosticPage'))
        self.click('overviewRunChecks')
        self.assertTrue(started.wait(.5))
        try:
            QTest.keyClick(self.window, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
            # The window manager's Back shortcut varies across KDE versions.
            # Exercise the same native PageRow pop even when that shortcut is
            # not mapped by this offscreen platform.
            if not self.controller._diagnostic_cancel.is_set():
                expression = QQmlExpression(QQmlEngine.contextForObject(self.window), self.window, 'void pageStack.pop()')
                expression.evaluate()
                self.assertFalse(expression.hasError(), expression.error().toString())
            QTest.qWait(400)
            self.assertTrue(self.controller._diagnostic_cancel.is_set(), 'Native back must cancel work from the removed diagnostic page')
            self.assertEqual(len(removed), 1, 'Popped diagnostic pages must be destroyed')
        finally:
            release.set()
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertFalse(self.controller.diagnostics['reportReady'])
        self.assertTrue(self.item('openDiagnosticCenter').property('visible'))
        for _ in range(3):
            self.open_center()
            removed = destruction_events(self.item('diagnosticPage'))
            expression = QQmlExpression(QQmlEngine.contextForObject(self.window), self.window, 'void pageStack.pop()')
            expression.evaluate()
            self.assertFalse(expression.hasError(), expression.error().toString())
            self.wait(lambda: len(removed) == 1)
            self.assertFalse([item for item in self.window.findChildren(QObject)
                              if item.objectName() == 'diagnosticPage'])

    def test_installation_time_missing_available_and_invalid_follow_real_ui(self):
        self.open_center()
        self.click('chooseProblem')
        self.click('problemInstall')
        combo = self.item('reportTime')
        self.assertEqual(combo.property('count'), 5)
        self.assertEqual(combo.property('currentIndex'), 0)
        self.assertTrue(self.item('installationTimeNotice').property('visible'))
        self.snapshot('13-install-time-unavailable-dark')
        self.click('continueReport')
        self.click('reportConsent')
        self.click('createReport')
        self.wait(lambda: self.screen() == 'preview')
        self.assertEqual(self.collect_report.call_args.args[1], 'current')
        self.click('previewBack')
        self.click('diagnosticBack')
        operation = {'action': 'update', 'result': 'failed', 'message_code': 'operation_failed',
                     'observedAt': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        self.controller.last_operation = operation
        self.controller.changed.emit()
        self.click('problemInstall')
        self.assertEqual(combo.property('count'), 6)
        self.assertEqual(combo.property('currentIndex'), 5)
        self.assertFalse(self.item('installationTimeNotice').property('visible'))
        self.snapshot('14-install-time-available-dark')
        # A reference can become unavailable while this same preparation form
        # remains open. The active selection must become a usable alternative.
        self.controller.last_operation = {}
        self.controller.changed.emit()
        self.app.processEvents()
        self.assertEqual(combo.property('count'), 5)
        self.assertEqual(combo.property('currentIndex'), 0)
        self.assertTrue(self.item('installationTimeNotice').property('visible'))
        self.controller.last_operation = operation
        self.controller.changed.emit()
        self.app.processEvents()
        self.choose_time(5)
        self.click('continueReport')
        self.click('reportConsent')
        self.click('createReport')
        self.wait(lambda: self.screen() == 'preview')
        self.assertEqual(self.collect_report.call_args.args[1], 'installation')
        for item in (dict(operation, action='remove'), dict(operation, observedAt='malformed'),
                     dict(operation, observedAt=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())):
            self.click('previewBack')
            self.click('diagnosticBack')
            self.controller.last_operation = item
            self.controller.changed.emit()
            self.click('problemInstall')
            self.assertEqual(combo.property('count'), 5)
            self.assertEqual(combo.property('currentIndex'), 0)
            self.assertTrue(self.item('installationTimeNotice').property('visible'))
            self.click('continueReport')
            self.click('reportConsent')
            self.click('createReport')
            self.wait(lambda: self.screen() == 'preview')
            self.assertEqual(self.collect_report.call_args.args[1], 'current')

    def test_failed_recollection_drops_previous_green_results_and_icons_are_vectors(self):
        previous = report_result(checks=[{'id': 'service', 'title': 'Fingerprint service',
            'outcome': 'pass', 'summary': 'Service configuration checked', 'detail': 'Previous result', 'code': 'service_checked'}],
            overview='Previous successful check')
        self.collect_checks.return_value = previous
        self.open_center()
        self.click('overviewRunChecks')
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertEqual(self.item('overviewFinding').property('text'), 'Previous successful check')
        self.collect_checks.side_effect = RuntimeError('PRIVATE_NEW_FAILURE')
        self.click('overviewRunChecks')
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertIn('No new', self.item('overviewFinding').property('text'))
        self.assertEqual(self.controller.diagnostics['checks'], [])
        self.assertEqual(self.controller.diagnostics['generatedAt'], '')
        self.snapshot('15-recollection-failed-dark')
        for name in ('diagnostic-pulse', 'fingerprint', 'gear', 'layers', 'usb', 'checklist', 'flask'):
            self.assertTrue(self.visual_value('diagnosticIcon-' + name, 'valid'), name)
            self.assertTrue(self.visual_value('diagnosticIcon-' + name, 'isMask'), name)
            self.assertIn('/diagnostic-icons/' + name + '.svg', str(self.visual_value('diagnosticIcon-' + name, 'source')))
        self.click('chooseChecks')
        self.assertIn('No new', self.visual_value('checksNotice', 'message'))
        self.assertIn('could not be collected', self.item('checksNotice').property('message'))
        for key, absent in [('service', 'D-Bus'), ('security', 'labels')]:
            self.click('check-' + key)
            detail = self.item('detail-' + key).property('text')
            self.assertNotIn(absent, detail)
        self.snapshot('16-checks-recollection-failed-dark')
        self.click('diagnosticBack')
        self.controller._diagnostic_data.update(previous)
        self.controller.changed.emit()
        self.app.processEvents()
        # The real idle ReaderSession.cancel does not emit changed. The
        # Controller itself must notify the view after clearing old evidence.
        with patch.object(self.controller.reader, 'cancel', return_value=None):
            self.controller.cancel_diagnostics()
        self.app.processEvents()
        self.assertIn('No new', self.item('overviewFinding').property('text'))
        self.assertEqual(self.controller.diagnostics['checks'], [])
        # A local 24px contact sheet makes the approved PNG's icon stroke style
        # directly reviewable without modifying or extracting any reference image.
        assets = sorted(Path(__file__).with_name('diagnostic-icons').glob('*.svg'))
        self.assertEqual(len(assets), 14)
        for dark in (True, False):
            sheet = QImage(560, 240, QImage.Format.Format_ARGB32_Premultiplied)
            sheet.fill(QColor('#202326' if dark else '#eff0f1'))
            painter = QPainter(sheet)
            painter.setPen(QColor('#eff0f1' if dark else '#232629'))
            for index, asset in enumerate(assets):
                renderer = QSvgRenderer(str(asset))
                self.assertTrue(renderer.isValid(), asset.name)
                tile = QImage(24, 24, QImage.Format.Format_ARGB32_Premultiplied)
                tile.fill(Qt.GlobalColor.transparent)
                ink = QPainter(tile)
                renderer.render(ink)
                ink.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                ink.fillRect(tile.rect(), QColor('#8ed8f5' if dark else '#086da2'))
                ink.end()
                x, y = (index % 4) * 140 + 12, (index // 4) * 60 + 12
                painter.drawImage(x, y, tile)
                painter.drawText(x, y + 43, asset.stem)
            painter.end()
            if RENDER_DIR:
                self.assertTrue(sheet.save(str(RENDER_DIR / ('17-icons-24px-' + ('dark' if dark else 'light') + '.png'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-dir', type=Path)
    args, remaining = parser.parse_known_args()
    RENDER_DIR = args.render_dir
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
