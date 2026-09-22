# SPDX-License-Identifier: GPL-2.0-or-later
"""Mock-only D-Bus orchestration checks: no GI, bus, service or USB execution."""
import ast
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r3_open_close", HERE / "r3_open_close.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class OpenClose(unittest.TestCase):
    def setUp(self):
        self.connection = Mock()
        self.methods = []
        self.fail = None
        self.path = "/net/reactivated/Fprint/Device/0"
        self.connection.call_sync.side_effect = self.call
        self.gio = SimpleNamespace(
            BusType=SimpleNamespace(SYSTEM=1),
            DBusCallFlags=SimpleNamespace(NO_AUTO_START=1, ALLOW_INTERACTIVE_AUTHORIZATION=2),
            DBusConnectionFlags=SimpleNamespace(AUTHENTICATION_CLIENT=1, MESSAGE_BUS_CONNECTION=2),
            dbus_address_get_for_bus_sync=Mock(return_value="synthetic-system-bus"),
            DBusConnection=SimpleNamespace(new_for_address_sync=Mock(return_value=self.connection)))
        self.glib = SimpleNamespace(Variant=lambda kind, value: (kind, value),
                                    VariantType=SimpleNamespace(new=lambda kind: kind))
        self.markers = []

    def call(self, destination, path, interface, method, parameters, reply, flags, timeout, cancellable):
        self.methods.append(method)
        self.assertEqual(destination, h.SERVICE)
        self.assertEqual(flags, 3)
        self.assertEqual(timeout, 15000)
        self.assertIsNone(cancellable)
        if method == self.fail:
            raise RuntimeError("private diagnostic must never be printed")
        if method == "GetDefaultDevice":
            self.assertEqual((path, interface, parameters, reply),
                             (h.MANAGER, h.SERVICE + ".Manager", None, "(o)"))
            return SimpleNamespace(unpack=lambda: (self.path,))
        self.assertEqual((path, interface, reply), (self.path, h.DEVICE_IFACE, "()"))
        self.assertEqual(parameters, ("(s)", ("",)) if method == "Claim" else None)
        return SimpleNamespace(unpack=lambda: ())

    def run_session(self, report=None):
        h.run_session(self.gio, self.glib, report or self.markers.append)

    def test_same_single_system_bus_connection_and_exact_three_methods(self):
        self.run_session()
        self.assertEqual(self.methods, ["GetDefaultDevice", "Claim", "Release"])
        self.gio.dbus_address_get_for_bus_sync.assert_called_once_with(1, None)
        self.gio.DBusConnection.new_for_address_sync.assert_called_once_with(
            "synthetic-system-bus", 3, None, None)
        self.connection.close_sync.assert_called_once_with(None)
        self.assertEqual(len(self.markers), 3)

    def test_no_claim_when_enumeration_fails(self):
        self.fail = "GetDefaultDevice"
        with self.assertRaises(h.GateError):
            self.run_session()
        self.assertEqual(self.methods, ["GetDefaultDevice"])
        self.connection.close_sync.assert_called_once_with(None)

    def test_no_retry_or_release_after_failed_claim(self):
        self.fail = "Claim"
        with self.assertRaises(h.GateError) as caught:
            self.run_session()
        self.assertEqual(caught.exception.stage, "CLAIM")
        self.assertEqual(self.methods, ["GetDefaultDevice", "Claim"])
        self.connection.close_sync.assert_called_once_with(None)

    def test_release_failure_is_not_retried(self):
        self.fail = "Release"
        with self.assertRaises(h.GateError) as caught:
            self.run_session()
        self.assertEqual(caught.exception.stage, "RELEASE")
        self.assertEqual(self.methods, ["GetDefaultDevice", "Claim", "Release"])
        self.connection.close_sync.assert_called_once_with(None)

    def test_release_after_successful_claim_despite_local_failure_or_interrupt(self):
        for failure in (RuntimeError, KeyboardInterrupt):
            with self.subTest(failure=failure):
                self.methods.clear()
                self.connection.close_sync.reset_mock()
                def report(marker):
                    if marker.startswith("R3_LIVE_CLAIM="):
                        raise failure("local failure after Claim")
                with self.assertRaises(failure):
                    self.run_session(report)
                self.assertEqual(self.methods, ["GetDefaultDevice", "Claim", "Release"])
                self.connection.close_sync.assert_called_once_with(None)

    def test_invalid_path_stops_before_claim(self):
        self.path = "/unexpected/object"
        with self.assertRaises(h.GateError):
            self.run_session()
        self.assertEqual(self.methods, ["GetDefaultDevice"])

    def test_failed_connection_does_not_retry(self):
        self.gio.DBusConnection.new_for_address_sync.side_effect = RuntimeError("connect failed")
        with self.assertRaises(RuntimeError):
            self.run_session()
        self.gio.DBusConnection.new_for_address_sync.assert_called_once()
        self.assertEqual(self.methods, [])
        self.connection.close_sync.assert_not_called()

    def test_no_dbus_calls_when_vm_guard_fails(self):
        with patch.object(h.subprocess, "run", return_value=SimpleNamespace(returncode=1)), \
                patch.object(h, "emit") as report, patch.object(h, "run_session") as session:
            self.assertEqual(h.main(), 1)
            session.assert_not_called()
            report.assert_called_once_with("R3_OPEN_CLOSE=STOP_VM_REQUIRED")

    def test_remote_error_is_bounded_and_raw_error_is_never_printed(self):
        for remote in ("net.reactivated.Fprint.Error.Internal", "unsafe\ncontents", "x" * 161):
            with self.subTest(remote=remote):
                self.gio.DBusError = SimpleNamespace(get_remote_error=lambda _error: remote)
                with patch.object(h.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                        patch.object(h.signal, "signal"), patch.object(h, "emit") as report, \
                        patch.object(h, "run_session", side_effect=h.GateError("CLAIM", RuntimeError("secret"))), \
                        patch.object(sys, "argv", ["helper"]), \
                        patch.dict(sys.modules, {"gi": SimpleNamespace(require_version=lambda *_args: None),
                                                "gi.repository": SimpleNamespace(Gio=self.gio, GLib=self.glib)}):
                    self.assertEqual(h.main(), 1)
                markers = [call.args[0] for call in report.call_args_list]
                self.assertEqual(markers[-1], "R3_OPEN_CLOSE=FAIL STAGE=CLAIM")
                self.assertFalse(any("secret" in marker or "\n" in marker for marker in markers))
                self.assertEqual(len(markers), 2 if remote.startswith("net.") else 1)

    def test_static_method_allowlist_and_no_live_loops(self):
        tree = ast.parse((HERE / "r3_open_close.py").read_text())
        strings = [node.value for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        self.assertFalse(any(part in value for value in strings
                             for part in ("Verify", "Enroll", "Delete", "Capture")))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "invoke"]
        self.assertCountEqual([node.args[2].value for node in calls],
                              ["GetDefaultDevice", "Claim", "Release"])
        self.assertFalse(any(isinstance(node, (ast.For, ast.While, ast.AsyncFor))
                             for node in ast.walk(tree)))


class DocumentedChecks(unittest.TestCase):
    def test_shell_and_python_snippet_syntax(self):
        text = (HERE / "R3_LIVE_OPEN_CLOSE_VM.md").read_text()
        for block in re.findall(r"```bash\n(.*?)\n```", text, re.S):
            result = subprocess.run(["bash", "-n"], input=block, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        for block in re.findall(r"<<'PY'\n(.*?)\nPY", text, re.S):
            ast.parse(block)

    def test_documented_journal_check_rejects_activation_missing_and_truncated_evidence(self):
        text = (HERE / "R3_LIVE_OPEN_CLOSE_VM.md").read_text()
        check = re.findall(r"<<'PY'\n(.*?)\nPY", text, re.S)[-1]
        # Derive the current log's keys from its source format, without running C.
        source = (HERE.parents[1] / "libfprint-driver/goodix_fpimage_device.c").read_text()
        start = source.index('"GOODIX_PRODUCTION_EPOCH_AUDIT action=')
        end = source.index('action_name != NULL', start)
        keys = re.findall(r"([a-z_0-9]+)=%", source[start:end])
        fields = dict.fromkeys(keys, '0')
        fields.update(action='FPI_DEVICE_ACTION_NONE', transport_epochs='1', drained='1', context_closed='1')
        audit = 'GOODIX_PRODUCTION_EPOCH_AUDIT ' + ' '.join(f'{key}={value}' for key, value in fields.items()) + '\n'
        cases = [(audit, True), ('', False), (audit * 2, False),
                 (audit.replace('real_submit=0', 'real_submit=1'), False),
                 (audit.replace('enroll_stages=0', 'enroll_stages=1'), False),
                 (audit.replace('action=FPI_DEVICE_ACTION_NONE', 'action=FPI_DEVICE_ACTION_ENROLL'), False),
                 (audit + 'ordinary line\n' * 200, False),
                 (audit + 'Suppressed 1 messages\n', False)]
        for marker in ('GOODIX_STOCK_CAPTURE_BEGIN', 'GOODIX_SIGFM_MATCH_AUDIT',
                       'GOODIX_LOGIN_READY', 'start enrollment device', 'Image device captured an image'):
            cases.append((audit + marker + '\n', False))
        with tempfile.TemporaryDirectory(prefix='goodix-r3-journal-test-') as tmp:
            log = Path(tmp) / 'synthetic.log'
            for data, accepted in cases:
                with self.subTest(data=data[-100:]):
                    log.write_text(data)
                    result = subprocess.run([sys.executable, '-B', '-', str(log)],
                                            input=check, text=True, capture_output=True)
                    self.assertEqual(result.returncode == 0, accepted, result.stderr)


if __name__ == "__main__":
    unittest.main()
