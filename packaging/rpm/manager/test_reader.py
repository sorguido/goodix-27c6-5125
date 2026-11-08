#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline reader state-machine and real Qt/private-bus adapter tests."""
import importlib.util
from contextlib import contextmanager
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PySide6.QtCore import QCoreApplication
from reader import (DEVICE_IFACE, MANAGER_IFACE, MAX_ATTEMPTS, ReaderSession,
                    QtFprintTransport, TARGET_NAME)

APP = QCoreApplication.instance() or QCoreApplication([])
PATH = '/net/reactivated/Fprint/Device/0'


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.pending = []
        self.closed = False
        self.callback = None

    def call(self, path, interface, method, arguments, callback):
        assert not self.closed
        self.calls.append((path, interface, method, arguments))
        self.pending.append((method, callback))

    def reply(self, method, values=None, error=None):
        name, callback = self.pending.pop(0)
        assert name == method, (name, method)
        callback(error, values or [])

    def subscribe(self, path, callback):
        self.callback = callback
        return True

    def close(self):
        self.closed = True

    def emit(self, result, done=True):
        self.callback(result, done)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.transports = []

        def factory():
            value = FakeTransport()
            self.transports.append(value)
            return value

        self.reader = ReaderSession(transport_factory=factory)
        self.addCleanup(self.reader.shutdown)

    def begin(self, *, claimed=True, started=True):
        self.assertTrue(self.reader.start(True))
        transport = self.transports[-1]
        transport.reply('GetDevices', [[PATH]])
        transport.reply('Get', [TARGET_NAME])
        if claimed:
            transport.reply('Claim')
        if claimed and started:
            transport.reply('VerifyStart')
        return transport

    def clean(self, transport):
        self.assertTrue(self.reader.view['busy'])
        transport.reply('VerifyStop')
        self.assertTrue(self.reader.view['busy'])
        transport.reply('Release')
        self.assertFalse(self.reader.view['busy'])
        self.assertTrue(transport.closed)

    def test_construction_and_no_consent_are_inert(self):
        self.assertEqual(self.transports, [])
        self.assertFalse(self.reader.start(False))
        self.assertFalse(self.reader.start(1))
        self.assertEqual(self.transports, [])
        self.assertEqual(self.reader.view['attempts'], 0)

    def test_match_stops_and_releases_then_permanently_blocks(self):
        transport = self.begin()
        self.assertEqual(self.reader.view['state'], 'verifying')
        transport.emit('verify-match')
        self.clean(transport)
        self.assertEqual(self.reader.view['state'], 'match')
        self.assertFalse(self.reader.start(True))
        self.assertEqual(len(self.transports), 1)
        self.assertEqual([entry[2] for entry in transport.calls],
                         ['GetDevices', 'Get', 'Claim', 'VerifyStart', 'VerifyStop', 'Release'])
        self.assertEqual(transport.calls[2][3], [''])
        self.assertEqual(transport.calls[3][3], ['any'])

    def test_three_explicit_no_matches_never_fourth(self):
        for count in range(1, MAX_ATTEMPTS + 1):
            transport = self.begin()
            transport.emit('verify-no-match')
            self.clean(transport)
            self.assertEqual(self.reader.view['attempts'], count)
            self.assertEqual(len(self.transports), count)
        self.assertFalse(self.reader.start(True))
        self.assertFalse(self.reader.view['canStart'])

    def test_each_retry_status_ends_attempt_even_when_not_done(self):
        for result in ('verify-retry-scan', 'verify-swipe-too-short',
                       'verify-finger-not-centered', 'verify-remove-and-retry',
                       'verify-too-fast'):
            with self.subTest(result=result):
                reader = ReaderSession(transport_factory=FakeTransport)
                reader.start(True)
                t = reader.transport
                t.reply('GetDevices', [[PATH]])
                t.reply('Get', [TARGET_NAME])
                t.reply('Claim')
                t.reply('VerifyStart')
                t.emit(result, False)
                t.reply('VerifyStop')
                t.reply('Release')
                self.assertEqual(reader.view['state'], 'retry')
                self.assertEqual(reader.view['attempts'], 1)
                self.assertFalse(reader.view['busy'])
                self.assertEqual(sum(c[2] == 'VerifyStart' for c in t.calls), 1)
                reader.shutdown()

    def test_wrong_or_ambiguous_target_never_claimed(self):
        self.reader.start(True)
        t = self.transports[-1]
        t.reply('GetDevices', [[PATH]])
        t.reply('Get', ['Another fingerprint reader'])
        self.assertTrue(t.closed)
        self.assertFalse(any(call[2] == 'Claim' for call in t.calls))
        self.reader.start(True)
        t = self.transports[-1]
        t.reply('GetDevices', [[PATH, PATH + '1']])
        t.reply('Get', [TARGET_NAME])
        t.reply('Get', [TARGET_NAME])
        self.assertTrue(t.closed)
        self.assertFalse(any(call[2] == 'Claim' for call in t.calls))

    def test_malformed_device_lists_fail_closed(self):
        for values in ([['/not/fprint']], [[PATH, PATH]], ['not an array'], [[]], []):
            reader = ReaderSession(transport_factory=FakeTransport)
            reader.start(True)
            transport = reader.transport
            transport.reply('GetDevices', values)
            self.assertEqual(reader.view['state'], 'unavailable')
            self.assertFalse(any(c[2] == 'Claim' for c in transport.calls))
            self.assertTrue(transport.closed)
            reader.shutdown()

    def test_cancel_claim_pending_closes_connection_and_ignores_late_reply(self):
        t = self.begin(claimed=False)
        self.reader.cancel()
        self.assertTrue(t.closed)
        t.reply('Claim')
        self.assertEqual(self.reader.view['state'], 'cancelled')
        self.assertFalse(any(c[2] == 'VerifyStart' for c in t.calls))

    def test_cancel_start_pending_charges_attempt_and_ignores_late_reply(self):
        t = self.begin(started=False)
        self.reader.cancel()
        t.reply('VerifyStart')
        t.emit('verify-match')
        self.assertEqual(self.reader.view['state'], 'cancelled')
        self.assertEqual(self.reader.view['attempts'], 1)
        self.assertTrue(t.closed)

    def test_cancel_during_capture_waits_for_cleanup(self):
        t = self.begin()
        self.reader.cancel()
        self.clean(t)
        self.assertEqual(self.reader.view['state'], 'cancelled')

    def test_permission_denied_never_issues_verification(self):
        t = self.begin(claimed=False)
        t.reply('Claim', error='permission_denied')
        self.assertEqual(self.reader.view['state'], 'permission_denied')
        self.assertEqual(self.reader.view['attempts'], 0)
        self.assertTrue(t.closed)

    def test_verify_start_failure_releases_claim(self):
        t = self.begin(started=False)
        t.reply('VerifyStart', error='no_prints')
        t.reply('Release')
        self.assertEqual(self.reader.view['state'], 'no_prints')
        self.assertTrue(t.closed)

    def test_cleanup_errors_close_connection_and_block_retry(self):
        for failed in ('VerifyStop', 'Release'):
            reader = ReaderSession(transport_factory=FakeTransport)
            reader.start(True)
            t = reader.transport
            t.reply('GetDevices', [[PATH]])
            t.reply('Get', [TARGET_NAME])
            t.reply('Claim')
            t.reply('VerifyStart')
            t.emit('verify-no-match')
            if failed == 'Release':
                t.reply('VerifyStop')
            t.reply(failed, error='error')
            self.assertTrue(t.closed)
            self.assertEqual(reader.view['state'], 'cleanup_error')
            self.assertFalse(reader.start(True))
            reader.shutdown()

    def test_disconnected_does_not_send_stop_or_release(self):
        t = self.begin()
        calls = len(t.calls)
        t.emit('verify-disconnected')
        self.assertEqual(len(t.calls), calls)
        self.assertTrue(t.closed)
        self.assertFalse(self.reader.start(True))

    def test_timeout_and_shutdown_close_pending_connections(self):
        t = self.begin(claimed=False)
        self.reader.timeout()
        t.reply('Claim')
        self.assertEqual(self.reader.view['state'], 'timeout')
        self.assertTrue(t.closed)
        self.assertFalse(self.reader.start(True))
        other = ReaderSession(transport_factory=FakeTransport)
        other.start(True)
        pending = other.transport
        other.shutdown()
        pending.reply('GetDevices', [[PATH]])
        self.assertTrue(pending.closed)
        self.assertFalse(other.start(True))

    def test_early_and_duplicate_statuses_do_not_replay_start_or_cleanup(self):
        t = self.begin(started=False)
        t.emit('verify-match')
        t.reply('VerifyStart')
        t.emit('verify-no-match')
        self.clean(t)
        self.assertEqual(self.reader.view['state'], 'match')
        self.assertEqual(sum(c[2] == 'VerifyStop' for c in t.calls), 1)

    def test_unknown_status_does_not_export_untrusted_text(self):
        t = self.begin()
        t.emit('PSK=SECRET_UNKNOWN_EVENT', False)
        self.clean(t)
        self.assertNotIn('SECRET', str(self.reader.view))
        self.assertFalse(self.reader.start(True))

    def test_missing_status_subscription_does_not_claim(self):
        self.reader.start(True)
        t = self.transports[-1]
        t.subscribe = lambda *args: False
        t.reply('GetDevices', [[PATH]])
        t.reply('Get', [TARGET_NAME])
        self.assertTrue(t.closed)
        self.assertFalse(any(c[2] == 'Claim' for c in t.calls))

    def test_method_timeout_closes_pending_connection_and_blocks(self):
        t = self.begin(claimed=False)
        t.reply('Claim', error='timeout')
        self.assertTrue(t.closed)
        self.assertEqual(self.reader.view['state'], 'timeout')
        self.assertFalse(self.reader.start(True))

    def test_transport_failure_does_not_leave_busy_state(self):
        def unavailable():
            raise RuntimeError('DO_NOT_EXPORT')
        self.reader.transport_factory = unavailable
        self.reader.start(True)
        self.assertFalse(self.reader.view['busy'])
        self.assertNotIn('DO_NOT_EXPORT', str(self.reader.view))


PRIVATE_SERVICE = r'''
import asyncio, sys
from dbus_next import Message
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next.constants import PropertyAccess
class Manager(ServiceInterface):
    def __init__(self): super().__init__('net.reactivated.Fprint.Manager')
    @method()
    def GetDevices(self) -> 'ao': return ['/net/reactivated/Fprint/Device/0']
class Device(ServiceInterface):
    def __init__(self): super().__init__('net.reactivated.Fprint.Device')
    @dbus_property(access=PropertyAccess.READ, name='name')
    def device_name(self) -> 's': return 'Goodix 27c6:5125 Fingerprint Sensor'
    @method()
    async def Claim(self, username: 's'):
        assert username == ''
        if len(sys.argv) > 2: await asyncio.sleep(.5)
    @method()
    def VerifyStart(self, finger: 's'):
        assert finger == 'any'
        asyncio.get_running_loop().call_later(.05, self.VerifyStatus, 'verify-match', True)
    @method()
    def VerifyStop(self): pass
    @method()
    def Release(self): pass
    @signal()
    def VerifyStatus(self, result: 's', done: 'b') -> 'sb': return [result, done]
async def main():
    bus = await MessageBus(bus_address=sys.argv[1]).connect()
    claimed_peer = [None]
    def observe(message):
        if message.interface == 'net.reactivated.Fprint.Device' and message.member == 'Claim':
            claimed_peer[0] = message.sender
            print('CLAIM_RECEIVED', flush=True)
        if (message.interface == 'org.freedesktop.DBus' and message.member == 'NameOwnerChanged'
            and message.body[0] == claimed_peer[0] and message.body[2] == ''):
            print('PEER_DISCONNECTED', flush=True)
    bus.add_message_handler(observe)
    await bus.call(Message(destination='org.freedesktop.DBus', path='/org/freedesktop/DBus',
        interface='org.freedesktop.DBus', member='AddMatch', signature='s',
        body=["type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged'"]))
    bus.export('/net/reactivated/Fprint/Manager', Manager())
    bus.export('/net/reactivated/Fprint/Device/0', Device())
    await bus.request_name('net.reactivated.Fprint')
    print('READY', flush=True)
    await asyncio.Future()
asyncio.run(main())
'''


@unittest.skipUnless(shutil.which('dbus-daemon') and importlib.util.find_spec('dbus_next'),
                     'private adapter test needs dbus-daemon and dbus-next')
class PrivateBusTests(unittest.TestCase):
    @contextmanager
    def private_bus(self, delayed_claim=False):
        runtime = tempfile.TemporaryDirectory(prefix='goodix-reader-bus-')
        daemon = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  env=dict(os.environ, XDG_RUNTIME_DIR=runtime.name))
        service = None
        try:
            self.assertTrue(select.select([daemon.stdout], [], [], 5)[0], 'private bus startup timed out')
            address = daemon.stdout.readline().strip()
            if not address.startswith('unix:'):
                error = daemon.stderr.read(4096) if daemon.poll() is not None else ''
                self.fail('Private bus startup failed (a socket-bind sandbox restriction requires '
                          'this isolated test to run outside that sandbox): ' + error)
            args = [sys.executable, '-c', PRIVATE_SERVICE, address]
            if delayed_claim:
                args.append('delay-claim')
            service = subprocess.Popen(args,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertTrue(select.select([service.stdout], [], [], 5)[0], 'fake service startup timed out')
            ready = service.stdout.readline().strip()
            self.assertEqual(ready, 'READY')
            yield address, service
        finally:
            for process in (service, daemon):
                if process:
                    process.terminate()
                    try:
                        process.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate(timeout=3)
            runtime.cleanup()

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(), 'private-bus expectation timed out')

    def test_actual_qt_object_path_array_variant_and_signal_binding(self):
        with self.private_bus() as (address, _service):
            reader = ReaderSession(transport_factory=lambda: QtFprintTransport(address=address))
            self.addCleanup(reader.shutdown)
            self.assertTrue(reader.start(True))
            self.wait_for(lambda: not reader.view['busy'])
            self.assertFalse(reader.view['busy'], reader.view)
            self.assertEqual(reader.view['state'], 'match', reader.view)
            self.assertEqual(reader.view['attempts'], 1)
            self.assertFalse(reader.view['canStart'])

    def test_pending_claim_cancel_actually_disconnects_peer(self):
        with self.private_bus(delayed_claim=True) as (address, service):
            reader = ReaderSession(transport_factory=lambda: QtFprintTransport(address=address))
            self.addCleanup(reader.shutdown)
            reader.start(True)
            self.wait_for(lambda: bool(select.select([service.stdout], [], [], 0)[0]))
            self.assertEqual(service.stdout.readline().strip(), 'CLAIM_RECEIVED')
            self.assertEqual(reader.phase, 'claiming')
            reader.cancel()
            self.assertFalse(reader.view['busy'])
            self.assertFalse(reader.view['canStart'])
            # This observes the actual private D-Bus daemon's owner loss,
            # independent of the fake transport.close assertion above.
            self.wait_for(lambda: bool(select.select([service.stdout], [], [], 0)[0]))
            self.assertEqual(service.stdout.readline().strip(), 'PEER_DISCONNECTED')
            self.assertEqual(reader.view['state'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
