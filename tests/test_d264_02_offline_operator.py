# SPDX-License-Identifier: GPL-2.0-or-later
"""Executable-closure tests for the D264/02 offline-only operator path."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "operator_kit/d264-first-image-offline.sh"


class D264OfflineOperatorTests(unittest.TestCase):
    def run_launcher(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (str(LAUNCHER), *arguments), cwd="/tmp", text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )

    def test_default_preserves_arm_ack_boundary(self) -> None:
        completed = self.run_launcher()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["terminal_boundary"], "STOP_AFTER_FDT_ARM_ACK")
        self.assertFalse(report["explicit_first_image_opt_in"])
        self.assertFalse(report["first_image_received"])
        self.assertNotIn("0x22", report["command_trace"])

    def test_explicit_first_image_reaches_public_coordinator(self) -> None:
        completed = self.run_launcher("--stop-after-first-image")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["terminal_boundary"], "STOP_AFTER_FIRST_IMAGE")
        self.assertEqual(report["first_image_irq2_timeout_ms"], 15000)
        self.assertEqual(report["physical_0x22_policy"], "FIXED64_ZERO_TAIL")
        self.assertTrue(report["first_image_received"])
        self.assertEqual(report["command_trace"].count("0x22"), 1)
        for forbidden in ("0x34", "0xa2", "0x70"):
            self.assertNotIn(forbidden, report["command_trace"])
        audit = report["runtime_audit"]
        self.assertEqual(audit["transport_cleanup_count"], 1)
        self.assertEqual(audit["tls_close_count"], 1)
        self.assertEqual(audit["retry_count"], 0)
        self.assertEqual(audit["persistent_device_write_count"], 0)
        for counter in ("REAL_USB_OPEN_COUNT", "REAL_TLS_HANDSHAKE_COUNT", "REAL_SENSOR_COMMAND_COUNT"):
            self.assertEqual(report[counter], 0)
        self.assertFalse(report["READY_FOR_LIVE"])

    def test_invalid_selection_fails_before_entrypoint(self) -> None:
        completed = self.run_launcher("--unknown")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("FAIL_CLOSED", completed.stderr)

    def test_multiple_selection_fails_closed(self) -> None:
        completed = self.run_launcher("--stop-after-first-image", "--stop-after-fdt-arm-ack")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
