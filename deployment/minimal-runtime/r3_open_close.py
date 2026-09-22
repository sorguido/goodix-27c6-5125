#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Human VM gate: one stock-fprintd Claim/Release on a private system-bus connection."""
import re
import signal
import subprocess
import sys

SERVICE = "net.reactivated.Fprint"
MANAGER = "/net/reactivated/Fprint/Manager"
DEVICE_IFACE = "net.reactivated.Fprint.Device"
TIMEOUT_MS = 15000


class GateError(Exception):
    def __init__(self, stage, cause=None):
        super().__init__(stage)
        self.stage = stage
        self.cause = cause


def emit(marker):
    print(marker, flush=True)


def one_open_close(connection, gio, glib, report=emit):
    """No retry: a confirmed Claim owns exactly one finally-path Release."""
    claimed = False
    flags = gio.DBusCallFlags.NO_AUTO_START | gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION

    def invoke(path, interface, method, parameters, reply):
        try:
            return connection.call_sync(SERVICE, path, interface, method,
                                        parameters, glib.VariantType.new(reply),
                                        flags, TIMEOUT_MS, None)
        except Exception as error:
            raise GateError(method.upper(), error) from None

    try:
        result = invoke(MANAGER, SERVICE + ".Manager", "GetDefaultDevice", None, "(o)")
        path, = result.unpack()
        if not re.fullmatch(r"/net/reactivated/Fprint/Device/[0-9]+", path):
            raise GateError("DEVICE_PATH")
        report("R3_LIVE_ENUMERATION=PASS")
        invoke(path, DEVICE_IFACE, "Claim", glib.Variant("(s)", ("",)), "()")
        claimed = True  # Set before local reporting so its failure still releases.
        report("R3_LIVE_CLAIM=PASS CLAIM_CALLS=1")
    finally:
        if claimed:
            # This is the only Release call site, including failure cleanup.
            invoke(path, DEVICE_IFACE, "Release", None, "()")
            report("R3_LIVE_RELEASE=PASS RELEASE_CALLS=1")


def run_session(gio, glib, report=emit):
    connection = None
    try:
        address = gio.dbus_address_get_for_bus_sync(gio.BusType.SYSTEM, None)
        connection = gio.DBusConnection.new_for_address_sync(
            address, gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
            gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
        one_open_close(connection, gio, glib, report)
    finally:
        if connection is not None:
            connection.close_sync(None)


def interrupted(_signum, _frame):
    raise KeyboardInterrupt


def main():
    # This guard runs before importing Gio or creating any D-Bus connection.
    try:
        vm = subprocess.run(["systemd-detect-virt", "--vm", "--quiet"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        vm = False
    if not vm:
        emit("R3_OPEN_CLOSE=STOP_VM_REQUIRED")
        return 1
    if len(sys.argv) != 1:
        emit("R3_OPEN_CLOSE=STOP_NO_ARGUMENTS_ALLOWED")
        return 1
    signal.signal(signal.SIGTERM, interrupted)
    gio = None
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        gio = Gio
        run_session(Gio, GLib)
    except (Exception, KeyboardInterrupt) as error:
        stage = error.stage if isinstance(error, GateError) else "LOCAL_OR_CONNECTION"
        remote = None
        if gio is not None and isinstance(error, GateError) and error.cause is not None:
            try:
                remote = gio.DBusError.get_remote_error(error.cause)
            except (TypeError, ValueError):
                pass
        if remote and re.fullmatch(r"[A-Za-z0-9_.]{1,160}", remote):
            emit("R3_REMOTE_ERROR=" + remote)
        emit("R3_OPEN_CLOSE=FAIL STAGE=" + stage)
        return 1
    emit("R3_OPEN_CLOSE=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
