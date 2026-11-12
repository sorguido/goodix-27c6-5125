# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit, bounded fprintd verification; no enrollment or direct sensor I/O.

Construction is inert. Each attempt owns a separate D-Bus connection, so closing
it also drops ownership if a Claim reply is lost or arrives after cancellation.
Tests inject a transport and never connect to the system bus.
"""
import re
import uuid

from PySide6.QtCore import QObject, QTimer, Signal, Slot, SLOT
from PySide6.QtDBus import (QDBusArgument, QDBusConnection, QDBusMessage,
                           QDBusObjectPath, QDBusPendingCallWatcher, QDBusVariant)

SERVICE = 'net.reactivated.Fprint'
MANAGER_PATH = '/net/reactivated/Fprint/Manager'
MANAGER_IFACE = 'net.reactivated.Fprint.Manager'
DEVICE_IFACE = 'net.reactivated.Fprint.Device'
TARGET_NAME = 'Goodix 27c6:5125 Fingerprint Sensor'
DEVICE_PATH = re.compile(r'/net/reactivated/Fprint/Device/[0-9]{1,8}\Z')
METHOD_TIMEOUT_MS = 6000
ATTEMPT_TIMEOUT_MS = 30000
MAX_ATTEMPTS = 3
RETRY_RESULTS = {'verify-retry-scan', 'verify-swipe-too-short',
                 'verify-finger-not-centered', 'verify-remove-and-retry',
                 'verify-too-fast'}


def _plain(value):
    """Decode only the simple D-Bus types used by this interface."""
    if isinstance(value, QDBusVariant):
        return _plain(value.variant())
    if isinstance(value, QDBusObjectPath):
        return value.path()
    if isinstance(value, QDBusArgument):
        # PySide does not automatically demarshal `ao`; asVariant() returns
        # another QDBusArgument for this array. Read the actual object-path
        # elements with the documented stream operator instead.
        if value.currentSignature() != 'ao':
            raise ValueError('unsupported D-Bus argument')
        argument = QDBusArgument(value)
        argument.beginArray()
        paths = []
        while not argument.atEnd():
            if len(paths) >= 16 or argument.currentSignature() != 'o':
                raise ValueError('unsupported device array')
            path = QDBusObjectPath()
            argument >> path
            paths.append(path.path())
        argument.endArray()
        return paths
    if isinstance(value, (list, tuple)) and len(value) <= 16:
        return [_plain(item) for item in value]
    if type(value) in {str, bool, int}:
        return value
    raise ValueError('unsupported D-Bus value')


class QtFprintTransport(QObject):
    """Asynchronous Qt adapter. An explicit address is for private-bus tests."""
    status = Signal(str, bool)

    def __init__(self, parent=None, *, address=None):
        super().__init__(parent)
        self.name = 'goodix-reader-' + uuid.uuid4().hex
        target = address if address is not None else QDBusConnection.BusType.SystemBus
        self.bus = QDBusConnection.connectToBus(target, self.name)
        self.closed = False
        self.watchers = set()
        self.path = None

    def call(self, path, interface, method, arguments, callback):
        if self.closed or not self.bus.isConnected():
            callback('unavailable', [])
            return
        message = QDBusMessage.createMethodCall(SERVICE, path, interface, method)
        message.setArguments(arguments)
        watcher = QDBusPendingCallWatcher(self.bus.asyncCall(message, METHOD_TIMEOUT_MS), self)
        self.watchers.add(watcher)

        def finished(call):
            self.watchers.discard(call)
            reply = call.reply()
            call.deleteLater()
            if self.closed:
                return
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                suffix = reply.errorName().rsplit('.', 1)[-1]
                code = {'PermissionDenied': 'permission_denied',
                        'AccessDenied': 'permission_denied',
                        'AlreadyInUse': 'in_use', 'NoEnrolledPrints': 'no_prints',
                        'NoSuchDevice': 'no_device', 'NoReply': 'timeout',
                        'Timeout': 'timeout', 'Disconnected': 'disconnected',
                        'ServiceUnknown': 'unavailable',
                        'NameHasNoOwner': 'unavailable'}.get(suffix, 'error')
                callback(code, [])
                return
            try:
                values = [_plain(value) for value in reply.arguments()]
            except (ValueError, TypeError, RuntimeError):
                callback('invalid_response', [])
                return
            callback(None, values)

        watcher.finished.connect(finished)

    def subscribe(self, path, callback):
        if self.closed:
            return False
        self.path = path
        self.status.connect(callback)
        # PySide's published annotation says bytes, but its actual binding
        # accepts the str produced by SLOT(), as exercised on a private bus.
        return self.bus.connect(SERVICE, path, DEVICE_IFACE, 'VerifyStatus',
                                self, SLOT('_receive_status(QString,bool)'))

    @Slot(str, bool)
    def _receive_status(self, result, done):
        if not self.closed:
            # Unknown strings never leave the session's fixed message catalog.
            self.status.emit(result[:128], done)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.path:
            self.bus.disconnect(SERVICE, self.path, DEVICE_IFACE, 'VerifyStatus',
                                self, SLOT('_receive_status(QString,bool)'))
        QDBusConnection.disconnectFromBus(self.name)
        # Drop the wrapper too: Qt keeps a connection alive while a named
        # connection copy is referenced. Pending watchers must not keep their
        # reply callback/session graph alive after a cancelled attempt.
        self.bus = QDBusConnection('')
        for watcher in self.watchers:
            watcher.finished.disconnect()
            watcher.deleteLater()
        self.watchers.clear()


class ReaderSession(QObject):
    """One physical outcome per click, at most three per explicit session."""
    changed = Signal()

    def __init__(self, parent=None, *, transport_factory=None):
        super().__init__(parent)
        self.transport_factory = transport_factory or QtFprintTransport
        self.transport = None
        self.attempts = 0
        self.state = 'idle'
        self.message = 'Ready for an explicit reader test. No test has been run.'
        self.busy = False
        self.blocked = False
        self.uncertain = False
        self.restart_ready = False
        self.phase = 'idle'
        self.epoch = 0
        self.path = None
        self.claimed = False
        self.started = False
        self.outcome = 'error'
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)

    @property
    def view(self):
        return {'busy': self.busy, 'state': self.state, 'message': self.message,
                'attempts': self.attempts,
                'canStart': not self.busy and not self.blocked and self.attempts < MAX_ATTEMPTS,
                'canNewTest': not self.busy and not self.uncertain and self.restart_ready}

    def new_test(self):
        """Reset only a safely completed session; never create a connection."""
        if not self.view['canNewTest']:
            return False
        self.epoch += 1
        self.attempts = 0
        self.blocked = self.restart_ready = False
        self.outcome = 'error'
        self._set('idle', 'Ready for a new test. Give consent and select Start when you are ready.')
        return True

    def _block_uncertain(self):
        self.blocked = self.uncertain = True
        self.restart_ready = False

    def _set(self, state, message):
        self.state, self.message = state, message
        self.changed.emit()

    def start(self, consent):
        if self.busy or self.blocked or self.attempts >= MAX_ATTEMPTS:
            return False
        if consent is not True:
            self._set('consent_required', 'Confirm the reader test and possible first-use pairing before starting.')
            return False
        self.busy = True
        self.restart_ready = False
        self.epoch += 1
        self.path = None
        self.claimed = self.started = False
        self.phase = 'discovering'
        self._set('starting', 'Looking for the supported Goodix reader…')
        self.timer.start(ATTEMPT_TIMEOUT_MS)
        try:
            self.transport = self.transport_factory()
            self._call(MANAGER_PATH, MANAGER_IFACE, 'GetDevices', [], self._devices)
        except Exception:
            self._finish('unavailable', 'The fingerprint service is unavailable.')
        return True

    def _call(self, path, interface, method, arguments, callback):
        epoch, phase = self.epoch, self.phase

        def reply(error, values):
            if epoch != self.epoch or not self.busy or phase != self.phase:
                return
            if error in {'timeout', 'disconnected'}:
                self._block_uncertain()
                self._finish(error, 'The reader connection was lost or timed out. No further test will be started.')
                return
            callback(error, values)

        try:
            self.transport.call(path, interface, method, arguments, reply)
        except Exception:
            self._block_uncertain()
            self._finish('error', 'The reader request could not be completed safely.')

    def _devices(self, error, values):
        if error:
            self._fail(error)
            return
        if (len(values) != 1 or not isinstance(values[0], list) or len(values[0]) > 16
                or any(type(path) is not str or not DEVICE_PATH.fullmatch(path) for path in values[0])
                or len(set(values[0])) != len(values[0])):
            self._finish('unavailable', 'The fingerprint service returned an unsupported device list.')
            return
        self.paths = list(values[0])
        self.matches = []
        self._next_name()

    def _next_name(self):
        if not self.paths:
            if len(self.matches) != 1:
                self._finish('unavailable', 'Exactly one supported Goodix reader is required for this test.')
                return
            self.path = self.matches[0]
            epoch = self.epoch
            try:
                subscribed = self.transport.subscribe(
                    self.path, lambda result, done: self._status(epoch, result, done))
            except Exception:
                subscribed = False
            if not subscribed:
                self._finish('unavailable', 'Reader status notifications are unavailable.')
                return
            self.phase = 'claiming'
            self._call(self.path, DEVICE_IFACE, 'Claim', [''], self._claim)
            return
        path = self.paths.pop(0)

        def name(error, values):
            if error or len(values) != 1 or type(values[0]) is not str:
                self._finish('unavailable', 'The reader identity could not be verified.')
                return
            if values[0] == TARGET_NAME:
                self.matches.append(path)
            self._next_name()

        self._call(path, 'org.freedesktop.DBus.Properties', 'Get', [DEVICE_IFACE, 'name'], name)

    def _claim(self, error, values):
        if error:
            if error not in {'permission_denied', 'in_use', 'no_device', 'no_prints'}:
                self._block_uncertain()
            self._fail(error)
            return
        if values:
            self._block_uncertain()
            self._finish('error', 'The reader claim could not be confirmed safely.')
            return
        self.claimed = True
        self.phase = 'starting'
        self.attempts += 1
        # Charge before issuing the request: a lost reply must not permit a
        # fourth physical attempt or an automatic replay.
        self.started = True
        self._set('starting', 'Starting one fingerprint verification attempt…')
        self._call(self.path, DEVICE_IFACE, 'VerifyStart', ['any'], self._started)

    def _started(self, error, values):
        if error:
            self.outcome = error
            if error not in {'permission_denied', 'in_use', 'no_device', 'no_prints'}:
                self._block_uncertain()
                self._stop()
                return
            self.started = False
            self._release()
            return
        if values:
            self._block_uncertain()
            self.outcome = 'error'
            self._stop()
            return
        self.phase = 'verifying'
        self._set('verifying', 'Place your finger on the reader. This test ends after one result.')

    def _status(self, epoch, result, done):
        if epoch != self.epoch or not self.busy or self.phase not in {'starting', 'verifying'}:
            return
        if result == 'verify-disconnected':
            # fprintd explicitly forbids further device calls after this status.
            self._block_uncertain()
            self._finish('disconnected', 'The reader disconnected. No further test will be started.')
            return
        if result == 'verify-match':
            self.outcome = 'match'
            self.blocked = True
        elif result == 'verify-no-match':
            self.outcome = 'no_match'
        elif result in RETRY_RESULTS:
            self.outcome = 'retry'
        else:
            self.outcome = 'error'
            self._block_uncertain()
        self._stop()

    def _stop(self):
        self.phase = 'stopping'
        self._set('cleaning', 'Stopping verification and releasing the reader…')

        def stopped(error, values):
            if error or values:
                self._block_uncertain()
                self._finish('cleanup_error', 'Reader cleanup could not be confirmed. The connection was closed; no further test will be started.')
                return
            self.started = False
            self._release()

        self._call(self.path, DEVICE_IFACE, 'VerifyStop', [], stopped)

    def _release(self):
        self.phase = 'releasing'

        def released(error, values):
            if error or values:
                self._block_uncertain()
                self._finish('cleanup_error', 'Reader release could not be confirmed. The connection was closed; no further test will be started.')
                return
            self.claimed = False
            self.restart_ready = (not self.uncertain and
                                  (self.outcome == 'match' or
                                   (self.attempts >= MAX_ATTEMPTS and self.outcome in {'no_match', 'retry', 'cancelled'})))
            messages = {
                'match': 'Fingerprint matched. This does not guarantee a future login; testing is complete.',
                'no_match': 'The scan completed without a match. A new attempt requires your explicit action.',
                'retry': 'The scan was incomplete. The attempt was stopped; a new attempt requires your explicit action.',
                'cancelled': 'The reader test was cancelled and the reader released.',
                'permission_denied': 'Fingerprint verification was not authorized.',
                'no_prints': 'No enrolled fingerprint is available. This test does not enroll fingerprints.',
                'in_use': 'The reader is in use by another application.',
            }
            text = messages.get(self.outcome, 'The reader test failed. Its cause has not been established.')
            if self.attempts >= MAX_ATTEMPTS and self.outcome != 'match':
                text += ' The three-attempt limit has been reached.'
            self._finish(self.outcome, text)

        self._call(self.path, DEVICE_IFACE, 'Release', [], released)

    def _fail(self, code):
        messages = {'permission_denied': 'Reader access was not authorized.',
                    'in_use': 'The reader is in use by another application.',
                    'no_device': 'No fingerprint reader is available.',
                    'no_prints': 'No enrolled fingerprint is available.'}
        self._finish(code if code in messages else 'unavailable',
                     messages.get(code, 'The fingerprint service is unavailable.'))

    def _finish(self, state, message):
        self.timer.stop()
        self.epoch += 1
        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:
                self._block_uncertain()
                state, message = 'cleanup_error', 'The reader connection could not be closed safely. Restarting this test is unavailable.'
            if isinstance(self.transport, QObject):
                self.transport.deleteLater()
            self.transport = None
        self.claimed = self.started = False
        self.busy = False
        self.phase = 'idle'
        if self.uncertain:
            message += ' A new test is unavailable because the reader state is uncertain.'
        self._set(state, message)

    def cancel(self):
        if not self.busy:
            return
        self.outcome = 'cancelled'
        if self.phase == 'verifying':
            self._stop()
        elif self.phase not in {'stopping', 'releasing'}:
            # A pending Claim/VerifyStart is ambiguous: sever its dedicated
            # connection rather than sending a racing Release or replaying it.
            if self.phase in {'claiming', 'starting'}:
                self._block_uncertain()
            self._finish('cancelled', 'The reader test was cancelled; its private connection was closed.')

    def timeout(self):
        if self.busy:
            self._block_uncertain()
            self._finish('timeout', 'The reader test timed out. Its connection was closed; no further test will be started.')

    def shutdown(self):
        self._block_uncertain()
        if self.busy:
            self._finish('cancelled', 'The reader connection was closed on application exit.')
