#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("d279_54_oem_identify_capture_audit.py")
SPEC = importlib.util.spec_from_file_location("d279_54_capture_audit_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class D27954CaptureAuditTests(unittest.TestCase):
    def test_authentic_capture_closes_single_acquisition_contract(self) -> None:
        result = AUDIT.analyze(ROOT)
        self.assertEqual(result["source_integrity"]["pcapng_packet_count"], 228)
        self.assertEqual(result["source_integrity"]["target_packet_count"], 216)
        self.assertEqual(result["source_integrity"]["target_protocol_frame_count"], 95)
        self.assertTrue(result["identify_action"]["single_touch_single_acquisition"])
        self.assertEqual(result["identify_action"]["post_touch_rearm_0x32_count"], 0)
        self.assertEqual(result["identify_action"]["terminal_protocol_event"], "NAV")
        self.assertEqual(result["terminal_observation"]["protocol_frames_after_ui_completion"], 0)
        self.assertEqual(result["terminal_observation"]["nonempty_target_packets_after_ui_completion"], 0)

    def test_output_is_metadata_only(self) -> None:
        result = AUDIT.analyze(ROOT)
        serialized = json.dumps(result, sort_keys=True).lower()
        for forbidden in ("raw", "body", "pixel", "descriptor", "psk", "secret_value"):
            self.assertNotIn(f'"{forbidden}"', serialized)
        self.assertFalse(result["privacy"]["raster_exported"])
        self.assertFalse(result["privacy"]["biometric_feature_or_template_exported"])

    def test_capture_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "captures" / "D279_54" / AUDIT.ATTEMPT_ID
            shutil.copytree(AUDIT.ATTEMPT, destination)
            capture = destination / "raw" / "wire.pcapng"
            data = bytearray(capture.read_bytes())
            data[-1] ^= 1
            capture.write_bytes(data)
            with self.assertRaisesRegex(AUDIT.AuditError, "CAPTURE_SHA256_MISMATCH"):
                AUDIT.analyze(root)


if __name__ == "__main__":
    unittest.main()
