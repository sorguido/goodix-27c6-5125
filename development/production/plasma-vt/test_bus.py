#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline unit test only: never connect to the host system bus or a real VT."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
# dbus-run-session supplies a fresh private bus; do not fall back to systemBus.
address = os.environ['DBUS_SESSION_BUS_ADDRESS']
assert os.environ.get('DBUS_SYSTEM_BUS_ADDRESS') == address
bus = dbus.SessionBus()
names = [dbus.service.BusName(n, bus) for n in ('org.freedesktop.login1', 'org.freedesktop.systemd1')]
scenario = 'normal'
queries = 0


class Login(dbus.service.Object):
    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='ss', out_signature='v')
    def Get(self, iface, prop):
        assert iface == 'org.freedesktop.login1.Manager' and prop == 'NAutoVTs'
        if scenario == 'bus_error': raise dbus.DBusException('synthetic unavailable')
        return dbus.UInt32(12 if scenario == 'configuration_drift' else 6)


class Manager(dbus.service.Object):
    @dbus.service.method('org.freedesktop.systemd1.Manager', in_signature='s', out_signature='o')
    def GetUnit(self, unit):
        global queries
        if unit == 'getty@tty7.service': queries += 1
        assert any(unit.startswith(k+'@tty') for k in ('getty', 'autovt', 'kmsconvt'))
        if unit == 'getty@tty7.service' and (scenario in ('active_getty', 'pending_job', 'malformed_job') or (scenario == 'claim_during_open' and queries % 2 == 0)):
            return '/unit7'
        e = dbus.DBusException('synthetic unloaded unit')
        e._dbus_error_name = 'org.freedesktop.systemd1.NoSuchUnit'
        raise e


class Unit(dbus.service.Object):
    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='s', out_signature='a{sv}')
    def GetAll(self, iface):
        assert iface == 'org.freedesktop.systemd1.Unit'
        return {'ActiveState': 'active' if scenario in ('active_getty','claim_during_open') else 'inactive',
                'Job': dbus.String('invalid') if scenario == 'malformed_job' else dbus.Struct((dbus.UInt32(1 if scenario == 'pending_job' else 0),
                                    dbus.ObjectPath('/')), signature='uo')}


objects = [Login(bus, '/org/freedesktop/login1'), Manager(bus, '/org/freedesktop/systemd1'), Unit(bus, '/unit7')]
loop = GLib.MainLoop()
thread = threading.Thread(target=loop.run, daemon=True); thread.start()
base = (1 << 1) | (1 << 2) | (1 << 6) | (1 << 12)
cases = [
    ('freed_tty3_password', 'normal', base | (1 << 3), 7),
    ('freed_tty3_fingerprint', 'normal', base | (1 << 3), 7),
    ('freed_tty4_fingerprint', 'normal', base | (1 << 4), 7),
    ('getty_queued_but_tty_still_free', 'normal', base, 7),
    ('nonconflicting', 'normal', base, 7),
    ('occupied_7', 'normal', base | (1 << 7), 8),
    ('tty12_recovery_excluded', 'normal', 0xffff & ~((1 << 12) | (1 << 13)) | (1 << 12), 13),
    ('manual_getty_outside_auto_range', 'active_getty', base, 8),
    ('queued_job_outside_auto_range', 'pending_job', base, 8),
    ('claim_during_open', 'claim_during_open', base, 8),
    ('malformed_job', 'malformed_job', base, -1),
    ('no_free_console', 'normal', 0xffff, -1),
    ('configuration_drift', 'configuration_drift', base, -1),
    ('bus_error', 'bus_error', base, -1),
]
try:
    for label, scenario, mask, expected in cases:
        queries = 0
        subprocess.run([sys.argv[1], str(mask), str(expected)], check=True, timeout=15)
        print('SIMULATED_CONTRACT_TEST=PASS case='+label, flush=True)
finally:
    loop.quit(); thread.join(3)
print('REAL_TARGET_VT_KERNEL_TEST=PENDING_LIVE')
