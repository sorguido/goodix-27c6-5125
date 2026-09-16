#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hardware-free source and authority tests for the D279/54 operator kit."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d279-54-oem-passive-identify-observe"
SCRIPT = KIT / "run-d279-54.ps1"
AUTHORITY = KIT / "D279_54_live_authority.json"


class D27954KitTests(unittest.TestCase):
    def test_authority_template_is_closed(self) -> None:
        self.assertEqual(json.loads(AUTHORITY.read_text(encoding="utf-8")), {
            "schema": "D279_54_LIVE_AUTHORITY_V1",
            "baseline_approved": False,
            "approved_for_passive_capture": False,
            "oem_identify_authorized": False,
            "existing_oem_template_confirmed": False,
            "possible_adaptive_template_persistence_accepted": False,
            "snapshot_prerun_confirmed": False,
            "live_authorized": False,
            "approved_full_commit_sha": None,
            "authorized_attempt_id": None,
        })

    def test_source_is_ascii_and_passive(self) -> None:
        source = SCRIPT.read_text(encoding="ascii")
        lowered = source.lower()
        self.assertEqual(source.count("Read-Host"), 1)
        self.assertIn("tshark.exe", lowered)
        self.assertIn("get-pnpdevice", lowered)
        for forbidden in (
            "libusb", "pyusb", "g_usb_device_bulk", "submit_out",
            "clearapp", "iap", "write_key", "fp_device_enroll",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_gate_order_and_single_attempt(self) -> None:
        source = SCRIPT.read_text(encoding="ascii")
        live = source.index("# Live path.")
        authority = source.index("$authority = Read-D27954Authority", live)
        repository = source.index("Assert-D27954Repository", authority)
        absent = source.index("Assert-D27954TargetAbsent", repository)
        capture = source.index("Start-Process -FilePath $tshark", absent)
        attach = source.index("$script:TargetAttached = $true", capture)
        verify = source.index("$script:VerificationStarted = $true", attach)
        self.assertLess(live, authority)
        self.assertLess(authority, repository)
        self.assertLess(repository, absent)
        self.assertLess(absent, capture)
        self.assertLess(capture, attach)
        self.assertLess(attach, verify)
        self.assertIn("[System.IO.FileMode]::CreateNew", source)
        self.assertIn("Test-D27954PrivateRoot $script:RunRoot", source)
        self.assertIn("authority symlink/reparse non ammessa", source)
        self.assertIn("verification_attempt_count = 1", source)
        self.assertIn("automatic_retry_count = 0", source)
        self.assertNotIn("while (", source)

    def test_outputs_tail_restore_and_closed_default(self) -> None:
        source = SCRIPT.read_text(encoding="ascii")
        self.assertIn("Start-Sleep -Seconds 5", source)
        self.assertIn("raw\\wire.pcapng", source.replace(
            '$script:Pcap = Join-Path $script:RawRoot "wire.pcapng"',
            "raw\\wire.pcapng"))
        self.assertIn("operator_events.json", source)
        self.assertIn("attempt_status.json", source)
        self.assertIn("RESTORE_SNAPSHOT_REQUIRED_AFTER_OEM_IDENTIFY", source)
        self.assertIn("ESPORTA PRIMA DI QUALSIASI RESTORE RAW", source)
        self.assertIn("if (-not $AutorizzoIdentifyOemPassivoD27954)", source)


if __name__ == "__main__":
    unittest.main()
