#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline Controller/Qt contracts; all collectors, buses and save dialogs are fake."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as manager
from PySide6.QtCore import QObject, Signal, QPointF, QTimer, Qt
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_ui import system_palette

QQuickStyle.setStyle('Fusion')
RENDER_DIR = None


class FakeReader(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = {'busy': False, 'state': 'idle', 'message': 'Ready to check the reader', 'attempts': 0, 'canStart': True}
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
        self.window.setWidth(1040)
        self.window.setHeight(900)
        QTest.qWait(200)

    def tearDown(self):
        self.window.hide()
        self.engine.deleteLater()
        self.app.processEvents()
        ControllerTests.tearDown(self)

    wait = ControllerTests.wait
    create_report = ControllerTests.create_report

    def item(self, name):
        item = self.window.findChild(QObject, name)
        if item is None:
            # Repeater delegates belong to a visual parent without necessarily
            # belonging to its QObject tree. Follow actual rendered children.
            pending = [self.window.contentItem()]
            while pending:
                candidate = pending.pop()
                if candidate.objectName() == name:
                    item = candidate
                    break
                pending.extend(candidate.childItems())
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
        self.assertTrue(0 <= point.x() < self.window.width() and 0 <= point.y() < self.window.height(), name + ' outside viewport')
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        QTest.qWait(100)

    def open_center(self):
        self.click('openDiagnosticCenter')
        self.wait(lambda: self.window.findChild(QObject, 'diagnosticPage') is not None)
        QTest.qWait(300)
        return self.item('diagnosticPage')

    def screen(self):
        return self.item('diagnosticPage').property('screen')

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
        self.assertTrue(self.item('reportSince').property('visible'))
        self.assertTrue(self.item('reportUntil').property('visible'))

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
            QTest.keyClick(self.window, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
            # The window manager's Back shortcut varies across KDE versions.
            # Exercise the same native PageRow pop even when that shortcut is
            # not mapped by this offscreen platform.
            if not self.controller._diagnostic_cancel.is_set():
                expression = QQmlExpression(QQmlEngine.contextForObject(self.window), self.window, 'pageStack.pop()')
                expression.evaluate()
                self.assertFalse(expression.hasError(), expression.error().toString())
            QTest.qWait(400)
            self.assertTrue(self.controller._diagnostic_cancel.is_set(), 'Native back must cancel work from the removed diagnostic page')
        finally:
            release.set()
        self.wait(lambda: not self.controller.diagnostics['busy'])
        self.assertFalse(self.controller.diagnostics['reportReady'])
        self.assertTrue(self.item('openDiagnosticCenter').property('visible'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-dir', type=Path)
    args, remaining = parser.parse_known_args()
    RENDER_DIR = args.render_dir
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
