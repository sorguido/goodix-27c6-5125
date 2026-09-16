#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "analysis/D281/d281_01_disable_usb_context.patch"
RUNNER = ROOT / "analysis/D281/d281_01_fprintd_storage_integration.sh"
FLOW = ROOT / "analysis/D281/d281_01_private_bus_flow.sh"
POLKIT = ROOT / "analysis/D281/d281_01_private_polkit_mock.py"
RESULT = ROOT / "analysis/D281/D281_01_OFFLINE_RESULT.env"


class D281OfflineIntegrationContract(unittest.TestCase):
    def test_usb_context_creation_and_enumeration_are_both_compiled_out(self):
        text = PATCH.read_text()
        source = (
            ROOT
            / "reference/libfprint-fedora44-1.94.100/source/libfprint/fp-context.c"
        ).read_text()
        self.assertIn("D281_01_DISABLE_USB_CONTEXT", text)
        self.assertIn("g_usb_context_new", source)
        self.assertIn("g_usb_context_enumerate", source)
        self.assertGreaterEqual(text.count("#ifndef D281_01_DISABLE_USB_CONTEXT"), 2)
        self.assertIn("g_usb_context_(new|enumerate)", RUNNER.read_text())

    def test_build_is_network_unshared_and_virtual_only(self):
        text = RUNNER.read_text()
        self.assertIn("--unshare=network", text)
        self.assertIn("-Ddrivers=virtual_image", text)
        self.assertIn("die goodix_driver_present", text)
        self.assertIn("die usb_context_symbol_present", text)

    def test_private_bus_and_tmp_state_are_mandatory(self):
        flow = FLOW.read_text()
        mock = POLKIT.read_text()
        self.assertIn("unix:path=/tmp/", flow)
        self.assertIn('DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"', flow)
        self.assertIn('STATE_DIRECTORY="$D281_01_PROBE_ROOT/state"', flow)
        self.assertIn("REFUSED_NON_TMP_BUS", mock)

    def test_real_cli_reload_corruption_and_delete_are_in_scope(self):
        text = FLOW.read_text()
        for command in ("fprintd-enroll", "fprintd-list", "fprintd-verify", "fprintd-delete"):
            self.assertIn(f"/usr/bin/{command}", text)
        for marker in (
            "D281_01_RELOAD_VERIFY_MATCH_PASS=true",
            "D281_01_CORRUPT_VERIFY_REJECTED=true",
            "D281_01_DELETE_PASS=true",
        ):
            self.assertIn(marker, text)

    def test_mock_authorizes_only_required_fprintd_actions(self):
        text = POLKIT.read_text()
        actions = set(re.findall(r'"(net\.reactivated\.fprint\.device\.[a-z]+)"', text))
        self.assertEqual(
            actions,
            {
                "net.reactivated.fprint.device.enroll",
                "net.reactivated.fprint.device.setusername",
                "net.reactivated.fprint.device.verify",
            },
        )

    def test_committed_result_preserves_required_outcomes(self):
        values = {}
        for line in RESULT.read_text().splitlines():
            if line:
                key, value = line.split("=", 1)
                values[key] = value
        expected = {
            "D281_01_PRIVATE_BUS_FLOW": "PASS",
            "D281_01_OFFLINE_INTEGRATION": "PASS",
            "D281_01_DRIVER": "virtual_image",
            "D281_01_USB_CONTEXT_COMPILE_DISABLED": "true",
            "D281_01_REAL_USB_ENUMERATION_ATTEMPTED": "false",
            "D281_01_GOODIX_DRIVER_PRESENT": "false",
            "D281_01_RELOAD_VERIFY_MATCH_PASS": "true",
            "D281_01_CORRUPT_VERIFY_REJECTED": "true",
            "D281_01_DELETE_PASS": "true",
            "D281_01_REMAINING_STATE_FILE_COUNT": "0",
            "D281_01_REAL_SENSOR_ACCESSED": "false",
        }
        self.assertEqual({key: values[key] for key in expected}, expected)
        self.assertRegex(values["D281_01_STORED_FP3_SHA256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
