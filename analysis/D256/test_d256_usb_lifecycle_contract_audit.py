#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Minimal D256 tests against the real hash-gated D255 evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import d256_usb_lifecycle_contract_audit as audit


class D256AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = audit.find_repo_root(Path(__file__).parent)
        cls.raw = cls.repo / audit.RUN_RELATIVE_RAW
        cls.raw_before = (audit.sha256_file(cls.raw), cls.raw.stat().st_size, cls.raw.stat().st_mtime_ns)
        cls.tmp = tempfile.TemporaryDirectory(prefix="d256-test-")
        cls.output = Path(cls.tmp.name)
        cls.decision = audit.audit(cls.repo, cls.output)
        with (cls.output / "D256_usb_timeline.csv").open(encoding="utf-8", newline="") as stream:
            cls.rows = list(csv.DictReader(stream))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_known_usbpcap_decode_direction_endpoint_transfer(self):
        row = next(item for item in self.rows if item["frame"] == "12")
        self.assertEqual(row["usbpcap_function_numeric"], "0x0008")
        self.assertEqual(row["function_semantic_class"], "CONTROL_TRANSFER")
        self.assertEqual(row["endpoint"], "0x80")
        self.assertEqual(row["direction"], "DEVICE_TO_HOST")
        self.assertEqual(row["transfer_type"], "2:CONTROL")

    def test_unknown_function_is_not_guessed(self):
        self.assertEqual(audit.function_semantic(0xFFFF), "SEMANTICS_UNRESOLVED")

    def test_marker_order_and_zero_packet_cancel_interval(self):
        window = self.decision["lifecycle_contract"]["window"]
        self.assertEqual(window["last_pre_cancel_arm_frame"], 198)
        self.assertEqual(window["cancel_interval_target_packet_count"], 0)
        self.assertEqual(window["new_arm_frame"], 214)
        self.assertEqual(window["new_arm_ack_frame"], 216)

    def test_same_device_continuity_is_not_disarm(self):
        observations = self.decision["lifecycle_contract"]["observations"]
        result = self.decision["lifecycle_contract"]["decision"]
        self.assertTrue(observations["same_bus_device"])
        self.assertFalse(observations["reenumeration_observed"])
        self.assertFalse(result["PRIOR_ARM_DISARM_PROVEN"])
        self.assertTrue(result["NEW_FDT_ARM_ACCEPTED_ON_REENTRY"])

    def test_0x50_and_0x97_are_known_not_new_restore_controls(self):
        controls = self.decision["controls"]
        self.assertEqual(controls["0x50"]["occurrence_count"], 1)
        self.assertIn("KNOWN_D230", controls["0x50"]["classification"])
        self.assertEqual(controls["0x97"]["occurrence_count"], 1)
        self.assertIn("SETDRIVERSTATE", controls["0x97"]["classification"])
        self.assertTrue(all("LIFECYCLE_RESTORE" in row["classification"] for row in controls.values()))

    def test_sanitizer_exports_no_private_payload(self):
        forbidden = (
            "aeaebfbfa4a4b2b2a7a7b3b3", "fb8d6c5bfb7f",
            "SYNTHETIC_SECRET_NEVER_EXPORT", "payload_hex",
        )
        for path in self.output.iterdir():
            text = path.read_text(encoding="utf-8").lower()
            for marker in forbidden:
                self.assertNotIn(marker.lower(), text, f"private marker leaked in {path.name}")
        self.assertEqual(len(self.rows), 206)
        self.assertFalse(self.decision["safety"]["otp_raw_exported"])
        self.assertFalse(self.decision["safety"]["raw_payload_exported"])

    def test_d255_bootstrap_regression_fields_remain_precise(self):
        bootstrap = self.decision["bootstrap"]
        self.assertTrue(bootstrap["BOOTSTRAP_CACHE_LAYOUT_TARGET_VALID"])
        self.assertTrue(bootstrap["BOOTSTRAP_CACHE_OTP_BOUND"])
        self.assertTrue(bootstrap["BOOTSTRAP_CACHE_FDT12_EQUALS_FIRST_WIRE_SEED"])
        self.assertFalse(bootstrap["BOOTSTRAP_SEED_DATAFLOW_CAUSALITY_PROVEN"])

    def test_raw_hash_size_and_mtime_unchanged(self):
        after = (audit.sha256_file(self.raw), self.raw.stat().st_size, self.raw.stat().st_mtime_ns)
        self.assertEqual(self.raw_before, after)
        self.assertEqual(after[0], audit.EXPECTED_RAW_SHA256)


if __name__ == "__main__":
    unittest.main()
