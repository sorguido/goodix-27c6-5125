#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Minimal PolicyKit authority for the isolated D281/01 private test bus.

This is deliberately unusable on the real system bus.  It authorizes only the
three fprintd actions needed by the synthetic integration test.
"""

from __future__ import annotations

import os
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


BUS_NAME = "org.freedesktop.PolicyKit1"
OBJECT_PATH = "/org/freedesktop/PolicyKit1/Authority"
AUTHORITY = "org.freedesktop.PolicyKit1.Authority"
ALLOWED_ACTIONS = {
    "net.reactivated.fprint.device.enroll",
    "net.reactivated.fprint.device.setusername",
    "net.reactivated.fprint.device.verify",
}


class Authority(dbus.service.Object):
    @dbus.service.method(
        AUTHORITY,
        in_signature="(sa{sv})sa{ss}us",
        out_signature="(bba{ss})",
    )
    def CheckAuthorization(
        self, subject, action_id, details, flags, cancellation_id
    ):
        del subject, details, flags, cancellation_id
        action = str(action_id)
        authorized = action in ALLOWED_ACTIONS
        print(f"D281_01_POLKIT_ACTION={action} AUTHORIZED={str(authorized).lower()}", flush=True)
        return authorized, False, dbus.Dictionary({}, signature="ss")

    @dbus.service.method(
        "org.freedesktop.DBus.Properties",
        in_signature="ss",
        out_signature="v",
    )
    def Get(self, interface_name, property_name):
        if str(interface_name) != AUTHORITY:
            raise dbus.exceptions.DBusException(
                "unknown interface", name="org.freedesktop.DBus.Error.InvalidArgs"
            )
        properties = {
            "BackendName": dbus.String("D281 private-bus test authority"),
            "BackendVersion": dbus.String("1"),
            "BackendFeatures": dbus.UInt32(0),
        }
        try:
            return properties[str(property_name)]
        except KeyError as error:
            raise dbus.exceptions.DBusException(
                "unknown property", name="org.freedesktop.DBus.Error.InvalidArgs"
            ) from error

    @dbus.service.method(
        "org.freedesktop.DBus.Properties",
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface_name):
        if str(interface_name) != AUTHORITY:
            return dbus.Dictionary({}, signature="sv")
        return dbus.Dictionary(
            {
                "BackendName": dbus.String("D281 private-bus test authority"),
                "BackendVersion": dbus.String("1"),
                "BackendFeatures": dbus.UInt32(0),
            },
            signature="sv",
        )


def main() -> int:
    address = os.environ.get("DBUS_SYSTEM_BUS_ADDRESS", "")
    if os.environ.get("D281_01_PRIVATE_BUS") != "1":
        print("D281_01_POLKIT_MOCK=REFUSED_MISSING_PRIVATE_BUS_MARKER", file=sys.stderr)
        return 2
    if not address.startswith("unix:path=/tmp/"):
        print("D281_01_POLKIT_MOCK=REFUSED_NON_TMP_BUS", file=sys.stderr)
        return 2

    DBusGMainLoop(set_as_default=True)
    bus = dbus.bus.BusConnection(address)
    name = dbus.service.BusName(BUS_NAME, bus=bus, do_not_queue=True)
    Authority(name, OBJECT_PATH)
    print("D281_01_POLKIT_MOCK=READY", flush=True)
    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
