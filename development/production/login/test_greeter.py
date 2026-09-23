#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Private-bus test of the real startup barrier with a harmless fake child."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

binary = sys.argv[1]
bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
bus.up()
os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = bus.get_bus_address()
connection = Gio.DBusConnection.new_for_address_sync(
    bus.get_bus_address(), Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
    Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                     'RequestName', GLib.Variant('(su)', ('net.reactivated.Fprint', 0)),
                     None, Gio.DBusCallFlags.NONE, 1000, None)
xml = '''<node><interface name="net.reactivated.Fprint.Manager">
<method name="GetDefaultDevice"><arg type="o" direction="out"/></method></interface>
<interface name="net.reactivated.Fprint.Device"><method name="PrepareLogin">
<arg type="b" direction="out"/></method></interface></node>'''
info = Gio.DBusNodeInfo.new_for_xml(xml)
state = {}

def method(conn, sender, path, interface, name, args, invocation):
    if name == 'GetDefaultDevice':
        invocation.return_value(GLib.Variant('(o)', ('/test/device',)))
    else:
        state['calls'] += 1
        assert not state['marker'].exists(), 'UI exposed before preparation'
        def finish():
            assert not state['marker'].exists(), 'UI exposed during preparation'
            state['answered'] = True
            if state['ready'] is None:
                invocation.return_dbus_error('net.reactivated.Fprint.Error.Internal', 'daemon failed')
            else:
                invocation.return_value(GLib.Variant('(b)', (state['ready'],)))
            return False
        GLib.timeout_add(100, finish)

ids = [connection.register_object('/net/reactivated/Fprint/Manager', info.interfaces[0], method, None, None),
       connection.register_object('/test/device', info.interfaces[1], method, None, None)]
with tempfile.TemporaryDirectory(prefix='goodix-greeter-test-') as work:
    for ready in (True, False, None):
        marker = Path(work) / str(ready)
        state.update(marker=marker, ready=ready, calls=0, answered=False)
        proc = subprocess.Popen([binary], env={**os.environ, 'GOODIX_TEST_UI_MARKER': str(marker)},
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        end = GLib.get_monotonic_time() + 5_000_000
        while proc.poll() is None and GLib.get_monotonic_time() < end:
            GLib.MainContext.default().iteration(False)
            GLib.usleep(1000)
        if proc.poll() is None:
            proc.kill()
            raise AssertionError('greeter startup hung')
        stdout, stderr = proc.communicate()
        assert proc.returncode == 0, stderr
        assert marker.exists() and state['answered'] and state['calls'] == 1
        assert f'ready={int(bool(ready))} password_available=1'.encode() in stderr
for identity in ids:
    connection.unregister_object(identity)
connection.close_sync(None)
bus.down()
print('GREETER_BARRIER=PASS ready_before_UI=1 failure_starts_password_UI=1 retry=0')
