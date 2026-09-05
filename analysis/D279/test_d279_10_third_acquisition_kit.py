#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic, hardware-free tests for the replanned D279/10 kit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d279-10-third-acquisition-observe"
LEGACY_TEST_PATH = ROOT / "analysis/D274/test_d274_03_second_cycle_operator_kit.py"
ATTEMPT_ID = "D27910_SYNTHETIC_0001"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LEGACY = load("d279_10_legacy_fixture", LEGACY_TEST_PATH)
sys.path.insert(0, str(KIT))
TARGET = load("d279_10_target", KIT / "d279_10_third_cycle.py")
OBSERVER = load("d279_10_observer_test", KIT / "d279_10_observer.py")


def acquisition(number: int) -> list[tuple[str, bytes, int]]:
    return [
        (f"cycle{number}_irq2", LEGACY.a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
        (f"cycle{number}_0x22", LEGACY.a0(0x22, b"\x01\x00"), 0x01),
        (f"cycle{number}_0x22_ack", LEGACY.a0(0xB0, b"\x22\x01"), 0x81),
        (f"cycle{number}_b0", LEGACY.fingerprint_b0(), 0x81),
    ]


def capture(total_cycles: int = 4, extra=None) -> bytes:
    def mutate(rows):
        for number in range(3, total_cycles + 1):
            rows.extend(acquisition(number))
        if extra:
            rows = extra(rows)
        return rows
    return LEGACY.make_capture(mutate)


def operator_events(contact_count: int = 4, tail: float = 5.2) -> dict:
    return {
        "schema": "D279_10_OPERATOR_EVENTS_V2",
        "attempt_id": ATTEMPT_ID,
        "capture_started_utc": "1970-01-01T00:00:00Z",
        "wizard_started_utc": "1970-01-01T00:00:00.010000Z",
        "enrollment_completed_utc": "1970-01-01T00:00:01Z",
        "capture_stopped_utc": f"1970-01-01T00:00:0{1 + tail:.6f}Z",
        "contact_count": contact_count,
        "enrollment_completed": True,
        "terminal_tail_seconds": 5,
        "automatic_retry_count": 0,
    }


class D27910Tests(unittest.TestCase):
    def process(self, data: bytes, events: dict | None = None) -> dict:
        with tempfile.TemporaryDirectory(prefix="d279-10-") as directory:
            path = Path(directory) / "wire.pcapng"
            event_path = Path(directory) / "operator_events.json"
            path.write_bytes(data)
            event_path.write_text(json.dumps(events or operator_events()),
                                  encoding="utf-8")
            return TARGET.process_capture(
                path, hashlib.sha256(data).hexdigest(), event_path,
                ATTEMPT_ID, synthetic=True)

    def failure(self, data: bytes, events: dict | None = None) -> str:
        try:
            self.process(data, events)
        except TARGET.EvidenceError as exc:
            return str(exc)
        self.fail("capture unexpectedly passed")

    def test_full_enrollment_uses_ui_confirmation_not_third_b0_stop(self):
        result = self.process(capture(total_cycles=6), operator_events(6))
        self.assertEqual(result["boundary_status"],
                         "OBSERVED_COMPLETE_UI_CONFIRMED")
        self.assertEqual(result["wire_acquisition_cycle_count"], 6)
        self.assertTrue(result["third_b0_milestone_observed"])
        self.assertGreater(
            result["acquisition_cycles"][-1]["frames"]["fingerprint_b0"]["frame"],
            result["third_b0_milestone_frame"])

    def test_contact_count_is_not_assumed_or_required_to_equal_wire_count(self):
        result = self.process(capture(total_cycles=4), operator_events(7))
        self.assertEqual(result["operator_contact_count"], 7)
        self.assertEqual(result["wire_acquisition_cycle_count"], 4)
        self.assertFalse(result["operator_wire_count_equal"])

    def test_even_two_wire_cycles_can_close_when_ui_really_confirms(self):
        result = self.process(capture(total_cycles=2), operator_events(2))
        self.assertFalse(result["third_b0_milestone_observed"])
        self.assertIsNone(result["third_b0_milestone_frame"])

    def test_ui_completion_is_mandatory(self):
        events = operator_events()
        events["enrollment_completed"] = False
        self.assertEqual(self.failure(capture(), events),
                         "WINDOWS_UI_ENROLLMENT_NOT_CONFIRMED")

    def test_terminal_tail_is_mandatory(self):
        events = operator_events()
        events["capture_stopped_utc"] = "1970-01-01T00:00:05.999000Z"
        self.assertEqual(self.failure(capture(), events),
                         "TERMINAL_TAIL_TOO_SHORT")

    def test_hash_mismatch_fails_closed(self):
        data = capture()
        with tempfile.TemporaryDirectory(prefix="d279-10-hash-") as directory:
            path = Path(directory) / "wire.pcapng"
            event_path = Path(directory) / "events.json"
            path.write_bytes(data)
            event_path.write_text(json.dumps(operator_events()), encoding="utf-8")
            with self.assertRaisesRegex(TARGET.EvidenceError,
                                        "CAPTURE_SHA256_MISMATCH"):
                TARGET.process_capture(path, "0" * 64, event_path,
                                       ATTEMPT_ID, synthetic=True)

    def test_known_persistent_command_is_reported_metadata_only(self):
        def extra(rows):
            rows.append(("persistent_e0", LEGACY.a0(0xE0, b"\x01"), 0x01))
            return rows
        result = self.process(capture(extra=extra))
        self.assertEqual(result["known_persistent_command_families_observed"],
                         ["0xe0"])
        self.assertEqual(result["sensor_side_risk_assessment"],
                         "KNOWN_PERSISTENT_COMMAND_FAMILY_OBSERVED")

    def test_absence_of_known_family_does_not_claim_no_sensor_persistence(self):
        result = self.process(capture())
        self.assertIn("NOT_EXCLUDED", result["sensor_side_risk_assessment"])
        serialized = json.dumps(result).lower()
        for forbidden in ('"body"', '"payload"', '"plaintext"', '"image"',
                          '"psk"', '"pin_value"'):
            self.assertNotIn(forbidden, serialized)

    def test_malformed_candidate_is_counted_and_later_cycle_resynchronizes(self):
        def extra(rows):
            rows.extend([
                ("bad_irq", LEGACY.a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
                ("bad_ack", LEGACY.a0(0xB0, b"\x22\x07"), 0x81),
            ])
            rows.extend(acquisition(5))
            return rows
        result = self.process(capture(extra=extra), operator_events(5))
        self.assertEqual(result["wire_acquisition_cycle_count"], 5)
        self.assertEqual(result["protocol_contradiction_count"], 1)

    def test_observer_journals_third_milestone_but_stops_only_on_control(self):
        data = capture(total_cycles=4)
        with tempfile.TemporaryDirectory(prefix="d279-10-observer-") as directory:
            base = Path(directory)
            pcap = base / "wire.pcapng"
            journal = base / "journal.jsonl"
            stop = base / "stop.json"
            result_path = base / "result.json"
            pcap.write_bytes(data)
            stop.write_text("{}", encoding="utf-8")
            result = OBSERVER.observe(
                pcap, journal, stop, result_path, 1.0, 1)
            self.assertEqual(result["status"],
                             "STOP_REQUESTED_BY_RUNNER_AFTER_UI_AND_TAIL")
            self.assertEqual(result["wire_acquisition_cycle_count"], 4)
            self.assertTrue(result["third_b0_milestone_observed"])
            lines = [json.loads(row) for row in
                     journal.read_text(encoding="utf-8").splitlines()]
            milestone = next(row for row in lines
                             if row["event"] == "WIRE_MILESTONE")
            self.assertFalse(milestone["stop_triggered"])

    def test_output_collision(self):
        result = self.process(capture())
        with tempfile.TemporaryDirectory(prefix="d279-10-output-") as directory:
            output = Path(directory) / "result.json"
            output.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(TARGET.EvidenceError,
                                        "OUTPUT_COLLISION"):
                TARGET.write_once(output, result)

    def test_authority_template_is_closed_and_sensor_risk_is_explicit(self):
        authority = json.loads(
            (KIT / "D279_10_live_authority.json").read_text(encoding="utf-8"))
        self.assertEqual(authority, {
            "schema": "D279_10_LIVE_AUTHORITY_V2",
            "baseline_approved": False,
            "approved_for_passive_capture": False,
            "full_oem_enrollment_authorized": False,
            "host_vm_enrollment_mutation_accepted": True,
            "possible_sensor_side_template_persistence_accepted": False,
            "snapshot_prerun_confirmed": False,
            "live_authorized": False,
            "approved_full_commit_sha": None,
            "authorized_attempt_id": None,
        })

    def test_powershell_has_numeric_inputs_attempt_scope_and_restore_policy(self):
        source = (KIT / "run-d279-10.ps1").read_text(encoding="ascii")
        self.assertEqual(source.count("Read-Host"), 1)
        self.assertIn("function Read-D279Menu", source)
        self.assertIn("while (-not $script:EnrollmentCompleted)", source)
        self.assertIn("third_b0_is_milestone_only = $true", source)
        self.assertIn("authorized_attempt_id", source)
        self.assertIn("attempt.lock", source)
        self.assertIn("RERUN_WITHOUT_RESTORE_REASONABLE", source)
        self.assertIn("RESTORE_SNAPSHOT_REQUIRED_STATE_UNCERTAIN", source)
        self.assertIn("ESPORTA PRIMA DI QUALSIASI RESTORE RAW", source)
        self.assertIn("Start-Sleep -Seconds 5", source)
        self.assertNotIn("ONE_SHOT_CONSUMED", source)
        self.assertNotIn("THIRD_FINGERPRINT_B0_OBSERVED", source)
        self.assertNotIn("libusb", source.lower())

    def test_live_gate_order_precedes_capture_and_attach(self):
        source = (KIT / "run-d279-10.ps1").read_text(encoding="ascii")
        live = source.index("# Live path.")
        authority = source.index("$authority = Read-D279Authority", live)
        sensor_gate = source.index(
            "$authority.possible_sensor_side_template_persistence_accepted",
            authority)
        absence = source.index("Assert-D279GoodixAbsentSameRun", sensor_gate)
        attempt = source.index("$script:RunRoot =", absence)
        capture_start = source.index("Start-Process -FilePath $tshark", attempt)
        attach = source.index("Collegamento target", capture_start)
        self.assertLess(authority, sensor_gate)
        self.assertLess(sensor_gate, absence)
        self.assertLess(absence, attempt)
        self.assertLess(attempt, capture_start)
        self.assertLess(capture_start, attach)

    def test_live_critical_dependency_remains_pinned(self):
        source = (KIT / "run-d279-10.ps1").read_text(encoding="ascii")
        relative = (
            "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/"
            "d274_03_postprocess_second_cycle.py"
        )
        self.assertIn(relative, source)
        self.assertTrue((ROOT / relative).is_file())


if __name__ == "__main__":
    unittest.main()
