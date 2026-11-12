#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Render Qt system palettes in-process; no host theme, network or privilege changes."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parent))
from main import Controller, load_interface
from model import Status
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QMetaObject, QPointF, QRect, QSize, QTimer, qInstallMessageHandler
from PySide6.QtGui import QColor, QPalette
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def system_palette(dark):
    """Representative KDE light/dark roles, applied only to this test process."""
    colors = {
        'Window': '#202326' if dark else '#eff0f1',
        'WindowText': '#eff0f1' if dark else '#232629',
        'Base': '#141618' if dark else '#ffffff',
        'AlternateBase': '#292c30' if dark else '#f7f7f7',
        'Text': '#eff0f1' if dark else '#232629',
        'Button': '#31363b' if dark else '#eff0f1',
        'ButtonText': '#eff0f1' if dark else '#232629',
        'Highlight': '#3daee9', 'HighlightedText': '#141618',
        'ToolTipBase': '#31363b' if dark else '#eff0f1',
        'ToolTipText': '#eff0f1' if dark else '#232629',
        'Mid': '#5f6266' if dark else '#b8b9ba',
        'Dark': '#141618' if dark else '#888a8c',
        'Light': '#46494d' if dark else '#ffffff',
        'Shadow': '#000000',
    }
    palette = QPalette()
    for role, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ('WindowText', 'Text', 'ButtonText'):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role),
                         QColor('#85898d' if dark else '#777a7d'))
    return palette


def contrast(first, second):
    def luminance(color):
        channels = [color.redF(), color.greenF(), color.blueF()]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    first, second = sorted((luminance(first), luminance(second)))
    return (second + 0.05) / (first + 0.05)


def geometry_checks(app, args):
    """First show uses real 3.1.1 content; later operations retain geometry."""
    import main as manager
    font = app.font()
    font.setPointSizeF(font.pointSizeF() * args.font_scale)
    app.setFont(font)
    records = []
    for name, state, remote in (('absent', 'absent', 'unavailable'),
                                ('installed', 'installed', 'current'),
                                ('update', 'installed', 'available')):
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            backend = Controller()
        backend.status = Status.parse({'schema': 1, 'state': state, 'runtime_version': '3.1.1' if state == 'installed' else None,
            'payload_version': '3.1.1', 'package_version': '3.1.1-3.fc44', 'sensor_present': None,
            'message_code': 'up_to_date' if state == 'installed' else 'not_installed'})
        backend.notice = 'The installed driver matches the local payload.' if state == 'installed' else 'The driver has not been activated.'
        backend.public_status = lambda: (remote, 'A new public package is available.' if remote == 'available' else 'No compatible public update is available.')
        backend.release = SimpleNamespace(package_version='3.1.2-1.fc44')
        backend.remote_state = remote
        engine = QQmlApplicationEngine()
        engine.addImportPath('/usr/lib64/qt6/qml')
        engine.rootContext().setContextProperty('backend', backend)
        load_interface(engine)
        window = engine.rootObjects()[0]
        changes = []
        window.heightChanged.connect(lambda: changes.append(window.height()))
        QTest.qWait(250)
        assert window.property('initialHomeFitDone') and window.isVisible()
        content = window.property('homeContentHeight')
        chrome = window.property('homeChromeHeight')
        maximum = window.property('homeScreenLimit')
        assert maximum <= app.primaryScreen().availableGeometry().height() - 24
        desired = math.ceil(content + chrome + window.property('homeBottomMargin'))
        expected = max(window.minimumHeight(), min(maximum, desired))
        assert abs(window.height() - expected) <= 2, (name, window.height(), expected, content, chrome)
        notice = window.findChild(QObject, 'managerHomeNotice')
        gap = window.height() - notice.mapToScene(QPointF(0, notice.height())).y()
        if desired <= maximum:
            assert 12 <= gap <= 72, (name, gap)
        home = window.findChild(QObject, 'managerHome')
        record = {'state': name, 'initial_height': window.height(), 'content_height': content,
                  'chrome_height': chrome, 'bottom_gap': gap, 'screen_limit': maximum,
                  'initial_height_changes': list(changes), 'font_scale': args.font_scale}
        if args.render_dir:
            args.render_dir.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(args.render_dir / ('home-initial-' + name + '.png')))
        window.setWidth(560)
        window.setHeight(max(window.minimumHeight(), window.height() - 80))
        QTest.qWait(150)
        manual = window.height()
        changes.clear()
        backend.notice = 'A changing status with more detail. ' * 5
        backend.changed.emit()
        QTest.qWait(150)
        assert window.height() == manual
        window.setProperty('requestedAction', 'update')
        dialog = next(item for item in window.findChildren(QObject) if item.property('title') == 'Apply the local update?')
        QMetaObject.invokeMethod(dialog, 'open')
        QTest.qWait(100)
        assert window.height() == manual
        QMetaObject.invokeMethod(dialog, 'close')
        for _ in range(3):
            QMetaObject.invokeMethod(window.findChild(QObject, 'openDiagnosticCenter'), 'clicked')
            QTest.qWait(150)
            page = window.findChild(QObject, 'diagnosticPage')
            assert page is not None and window.height() == manual
            expression = QQmlExpression(QQmlEngine.contextForObject(page), page, 'showScreen("checks"); undefined')
            expression.evaluate()
            assert not expression.hasError(), expression.error().toString()
            with patch.object(manager.diagnostic_tools, 'collect_checks', return_value={'checks': [], 'overview': 'Synthetic collection complete', 'generatedAt': ''}):
                backend.run_diagnostics()
                for _wait in range(100):
                    QTest.qWait(10)
                    if not backend.diagnostics['busy']:
                        break
                assert not backend.diagnostics['busy']
            expression = QQmlExpression(QQmlEngine.contextForObject(window), window, 'void pageStack.pop()')
            expression.evaluate()
            assert not expression.hasError(), expression.error().toString()
            for _wait in range(300):
                QTest.qWait(10)
                if window.findChild(QObject, 'diagnosticPage') is None:
                    break
            assert window.findChild(QObject, 'diagnosticPage') is None, 'Removed diagnostic page must be destroyed'
            assert window.height() == manual
        assert not changes, changes
        expression = QQmlExpression(QQmlEngine.contextForObject(home), home, 'flickable.contentHeight > flickable.height')
        overflowing, _undefined = expression.evaluate()
        assert not expression.hasError() and overflowing, 'Small window must scroll overflowing content'
        record['manual_height_preserved'] = manual
        records.append(record)
        window.hide()
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, 'void pageStack.clear()')
        expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        backend.shutdown()
        backend.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    print('PASS_GEOMETRY ' + json.dumps(records, sort_keys=True))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-dir', type=Path)
    parser.add_argument('--initial-palette', choices=('light', 'dark'), default='light')
    parser.add_argument('--geometry', action='store_true')
    parser.add_argument('--font-scale', type=float, default=1.0)
    args = parser.parse_args()
    Controller.refresh = lambda self: None
    Controller.check_releases = lambda self: None
    qInstallMessageHandler(lambda kind, context, message: print('Qt:', message, file=sys.stderr))
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    app.setPalette(system_palette(args.initial_palette == 'dark'))
    if args.geometry:
        return geometry_checks(app, args)
    backend = Controller()
    backend.status = Status.parse({'schema': 1, 'state': 'installed', 'runtime_version': '3.0.0',
                                   'payload_version': '3.1.0', 'package_version': '3.1.0-1.fc44',
                                   'sensor_present': False, 'message_code': 'update_available'})
    backend.notice = 'A newer verified local payload is ready to apply.'
    backend.remote_state = 'unavailable'
    backend.remote_message = 'Check unavailable · local actions remain available'
    engine = QQmlApplicationEngine()
    engine.addImportPath('/usr/lib64/qt6/qml')
    engine.rootContext().setContextProperty('backend', backend)
    load_interface(engine)
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    assert window.metaObject().indexOfProperty('themeChoice') == -1
    assert not any('ComboBox' in obj.metaObject().className() for obj in window.findChildren(QObject))
    window.setProperty('requestedAction', 'update')
    dialog = next(obj for obj in window.findChildren(QObject)
                  if obj.property('title') == 'Apply the local update?')
    apply_button = next(obj for obj in window.findChildren(QObject)
                        if obj.property('text') == 'Apply Update')
    notice_label = next(obj for obj in window.findChildren(QObject)
                        if obj.property('text') == backend.notice)
    spinner = window.findChild(QObject, 'driverBusyIndicator')
    assert not any('ProgressBar' in obj.metaObject().className() for obj in window.findChildren(QObject))
    indicator = window.findChild(QObject, 'softwareUpdatesIndicator')
    results = {}
    spinner_frames = {}
    failures = []

    def save(name, dark):
        expected = system_palette(dark)
        for name_in_qml, role in [('surfaceColor', 'Window'), ('cardColor', 'Base'), ('inkColor', 'Text')]:
            assert window.property(name_in_qml) == expected.color(getattr(QPalette.ColorRole, role)), name_in_qml
        assert notice_label.property('color') == expected.color(QPalette.ColorRole.WindowText)
        assert indicator.property('color') == expected.color(QPalette.ColorRole.Mid)
        assert spinner.property('visible') == backend.busy
        assert spinner.property('running') == backend.busy
        assert spinner.width() == spinner.height() == 44
        if not backend.busy:
            assert apply_button.property('contentItem').property('color') == expected.color(QPalette.ColorRole.ButtonText)
        assert contrast(window.property('inkColor'), window.property('cardColor')) >= 7
        assert contrast(window.property('inkColor'), window.property('surfaceColor')) >= 7
        picture = window.grabWindow()
        assert not picture.isNull()
        if backend.busy:
            position = spinner.mapToScene(QPointF(0, 0)).toPoint()
            bounds = QRect(position, QSize(44, 44))
            assert picture.rect().contains(bounds), 'Active spinner must fit the window'
            spinner_frames[name] = picture.copy(bounds)
        if args.render_dir:
            args.render_dir.mkdir(parents=True, exist_ok=True)
            assert picture.save(str(args.render_dir / ('manager-' + name + '.png')))
        results[name] = picture

    # Each step runs against the same open QML window. QApplication.setPalette
    # exercises Qt's palette-change signal, without changing KDE settings.
    steps = [
        lambda: save('startup', args.initial_palette == 'dark'),
        lambda: app.setPalette(system_palette(False)),
        lambda: save('light', False),
        lambda: QMetaObject.invokeMethod(dialog, 'open'),
        lambda: save('light-dialog', False),
        lambda: app.setPalette(system_palette(True)),
        lambda: save('dark-dialog-live', True),
        lambda: QMetaObject.invokeMethod(dialog, 'close'),
        lambda: save('dark', True),
        lambda: set_busy(True),
        lambda: save_disabled('dark-disabled', True),
        lambda: save_disabled('dark-disabled-next-frame', True),
        lambda: app.setPalette(system_palette(False)),
        lambda: save_disabled('light-disabled-live', False),
        lambda: set_busy(False),
        lambda: save('light-live', False),
        lambda: compact(),
        lambda: save('compact-light', False),
        lambda: app.setPalette(system_palette(True)),
        lambda: save('compact-dark-live', True),
        lambda: set_busy(True),
        lambda: save_disabled('compact-dark-active', True),
        lambda: app.setPalette(system_palette(False)),
        lambda: save_disabled('compact-light-active', False),
        lambda: set_busy(False),
    ]

    def set_busy(value):
        backend.busy = value
        backend.operation = 'update' if value else ''
        backend.notice = 'Applying the local driver update…' if value else 'A newer verified local payload is ready to apply.'
        backend.changed.emit()

    def save_disabled(name, dark):
        assert apply_button.property('enabled') is False
        expected = system_palette(dark)
        disabled_text = expected.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText)
        assert disabled_text != expected.color(QPalette.ColorRole.ButtonText)
        assert apply_button.property('contentItem').property('color') == disabled_text
        save(name, dark)

    def compact():
        window.setWidth(520)
        window.setHeight(560)

    def advance():
        try:
            if not steps:
                app.quit()
                return
            steps.pop(0)()
            QTimer.singleShot(150, advance)
        except Exception as error:
            failures.append(error)
            app.quit()

    QTimer.singleShot(250, advance)
    QTimer.singleShot(8000, app.quit)
    app.exec()
    if failures:
        raise failures[0]
    assert not steps and len(results) == 13, 'Incomplete render sequence'
    assert spinner_frames['dark-disabled'] != spinner_frames['dark-disabled-next-frame'], 'Native spinner must animate'
    assert results['light'] != results['dark'], 'System palettes must differ'
    # Focus moves after the confirmation dialog; compare the restored background,
    # while save() already checked every bound palette role after the live change.
    assert results['light'].pixelColor(4, 100) == results['light-live'].pixelColor(4, 100)
    assert results['compact-light'].width() == 520
    print('PASS: system light/dark, live palette changes, dialogs, disabled controls, animated 44px spinner and compact QML render; no host theme, privileged or network changes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
