#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic, hardware-free tests for the D279/10 passive observer kit."""

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


def third_suffix() -> list[tuple[str, bytes, int]]:
    return [
        ("second_release_0x34", LEGACY.a0(0x34, b"\x0a\x01" + bytes(12)), 0x01),
        ("second_release_0x34_ack", LEGACY.a0(0xB0, b"\x34\x01"), 0x81),
        ("second_release_irq0200", LEGACY.a0(0x34, b"\x00\x02" + bytes(12)), 0x81),
        ("second_release_0x20", LEGACY.a0(0x20, b"\x01\x00"), 0x01),
        ("second_release_0x20_ack", LEGACY.a0(0xB0, b"\x20\x01"), 0x81),
        ("second_release_b0", LEGACY.fingerprint_b0(), 0x81),
        ("second_release_0x50", LEGACY.a0(0x50), 0x01),
        ("second_release_0x50_ack", LEGACY.a0(0xB0, b"\x50\x01"), 0x81),
        ("second_release_nav", LEGACY.nav(), 0x81),
        ("third_rearm_0x32", LEGACY.a0(0x32, bytes(14)), 0x01),
        ("third_rearm_0x32_ack", LEGACY.a0(0xB0, b"\x32\x01"), 0x81),
        ("third_irq2", LEGACY.a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
        ("third_0x22", LEGACY.a0(0x22, b"\x01\x00"), 0x01),
        ("third_0x22_ack", LEGACY.a0(0xB0, b"\x22\x01"), 0x81),
        ("third_b0", LEGACY.fingerprint_b0(), 0x81),
    ]


def capture(mutator=None) -> bytes:
    def append(rows):
        rows.extend(third_suffix())
        return mutator(rows) if mutator else rows
    return LEGACY.make_capture(append)


def remove(rows, label):
    return [row for row in rows if row[0] != label]


def replace(rows, label, raw, endpoint):
    return LEGACY.replace(rows, label, raw, endpoint)


class D27910Tests(unittest.TestCase):
    def process(self, data: bytes) -> dict:
        with tempfile.TemporaryDirectory(prefix="d279-10-") as directory:
            path = Path(directory) / "wire.pcapng"
            path.write_bytes(data)
            return TARGET.process_capture(
                path, hashlib.sha256(data).hexdigest(), synthetic=True)

    def failure(self, data: bytes) -> str:
        try:
            self.process(data)
        except TARGET.EvidenceError as exc:
            return str(exc)
        self.fail("capture unexpectedly passed")

    def test_success_exact_repeated_release_and_third_edge(self):
        result = self.process(capture())
        self.assertEqual(result["boundary_status"], "OBSERVED_COMPLETE")
        self.assertEqual(result["stop_reason"], "THIRD_FINGERPRINT_B0")
        self.assertEqual(len(result["sequence_frames"]), 15)
        self.assertFalse(result["fourth_cycle_observed"])
        serialized = json.dumps(result).lower()
        for forbidden in ('"body"', '"payload"', '"plaintext"', '"image"',
                          '"psk"', '"pin"'):
            self.assertNotIn(forbidden, serialized)

    def test_missing_second_release_is_pending_boundary(self):
        self.assertEqual(
            self.failure(capture(lambda rows: remove(rows, "second_release_0x34"))),
            "THIRD_CYCLE_PROTOCOL_CONTRADICTION_AT_SECOND_RELEASE_0X34",
        )

    def test_malformed_second_release_shape_fails_closed(self):
        data = capture(lambda rows: replace(
            rows, "second_release_0x34", LEGACY.a0(0x34, bytes(14)), 0x01))
        self.assertEqual(
            self.failure(data),
            "THIRD_CYCLE_PROTOCOL_CONTRADICTION_AT_SECOND_RELEASE_0X34",
        )

    def test_missing_third_irq2(self):
        self.assertEqual(
            self.failure(capture(lambda rows: remove(rows, "third_irq2"))),
            "THIRD_CYCLE_PROTOCOL_CONTRADICTION_AT_THIRD_IRQ2",
        )

    def test_wrong_third_ack_status(self):
        data = capture(lambda rows: replace(
            rows, "third_0x22_ack", LEGACY.a0(0xB0, b"\x22\x07"), 0x81))
        self.assertEqual(
            self.failure(data),
            "THIRD_CYCLE_PROTOCOL_CONTRADICTION_AT_THIRD_0X22_ACK",
        )

    def test_non_lifecycle_fdt_polling_may_be_interposed(self):
        def mutate(rows):
            index = next(i for i, row in enumerate(rows)
                         if row[0] == "second_release_0x34")
            rows[index:index] = [
                ("fdt_0x36", LEGACY.a0(0x36, bytes(14)), 0x01),
                ("fdt_0x36_ack", LEGACY.a0(0xB0, b"\x36\x01"), 0x81),
                ("fdt_irq100", LEGACY.a0(0x36, b"\x00\x01" + bytes(12)), 0x81),
            ]
            return rows
        self.assertEqual(self.process(capture(mutate))["boundary_status"],
                         "OBSERVED_COMPLETE")

    def test_fourth_cycle_is_not_silently_accepted(self):
        def mutate(rows):
            rows.extend([
                ("fourth_irq2", LEGACY.a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
                ("fourth_0x22", LEGACY.a0(0x22, b"\x01\x00"), 0x01),
                ("fourth_0x22_ack", LEGACY.a0(0xB0, b"\x22\x01"), 0x81),
                ("fourth_b0", LEGACY.fingerprint_b0(), 0x81),
            ])
            return rows
        self.assertEqual(self.failure(capture(mutate)), "FOURTH_CYCLE_OBSERVED")

    def test_hash_mismatch(self):
        data = capture()
        with tempfile.TemporaryDirectory(prefix="d279-10-hash-") as directory:
            path = Path(directory) / "wire.pcapng"
            path.write_bytes(data)
            with self.assertRaisesRegex(TARGET.EvidenceError,
                                        "CAPTURE_SHA256_MISMATCH"):
                TARGET.process_capture(path, "0" * 64, synthetic=True)

    def test_growing_observer_pending_then_terminal(self):
        partial = LEGACY.make_capture()
        full = capture()
        with tempfile.TemporaryDirectory(prefix="d279-10-observer-") as directory:
            path = Path(directory) / "wire.pcapng"
            signal = Path(directory) / "signal.json"
            path.write_bytes(partial)
            state = TARGET.inspect_growing_capture(path)
            self.assertEqual(state["status"], "PENDING")
            path.write_bytes(full)
            result = OBSERVER.observe(path, signal, 1.0, 1)
            self.assertEqual(result["status"], "THIRD_FINGERPRINT_B0_OBSERVED")
            self.assertTrue(signal.is_file())

    def test_output_collision(self):
        data = capture()
        result = self.process(data)
        with tempfile.TemporaryDirectory(prefix="d279-10-output-") as directory:
            output = Path(directory) / "result.json"
            output.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(TARGET.EvidenceError,
                                        "OUTPUT_COLLISION"):
                TARGET.write_once(output, result)

    def test_finalizer_requires_exact_observer_terminal(self):
        data = capture()
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory(prefix="d279-10-final-") as directory:
            path = Path(directory) / "wire.pcapng"
            signal = Path(directory) / "signal.json"
            path.write_bytes(data)
            observed = TARGET.inspect_growing_capture(path)
            signal.write_text(json.dumps({
                "schema": "D279_10_WIRE_OBSERVER_SIGNAL_V1",
                **observed,
                "stop_trigger": "WIRE_DRIVEN",
                "automatic_retry_count": 0,
            }), encoding="utf-8")
            result = TARGET.process_capture(
                path, digest, synthetic=True, observer_signal=signal)
            self.assertEqual(result["terminal_frame"],
                             observed["terminal_frame"])
            tampered = json.loads(signal.read_text(encoding="utf-8"))
            tampered["terminal_frame"] += 1
            signal.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(TARGET.EvidenceError,
                                        "OBSERVER_SIGNAL_FINAL_MISMATCH"):
                TARGET.process_capture(
                    path, digest, synthetic=True, observer_signal=signal)

    def test_authority_template_and_powershell_gate_order(self):
        authority = json.loads(
            (KIT / "D279_10_live_authority.json").read_text(encoding="utf-8"))
        self.assertEqual(authority, {
            "schema": "D279_10_LIVE_AUTHORITY_V1",
            "baseline_approved": False,
            "approved_for_passive_capture": False,
            "third_contact_authorized": False,
            "possible_host_enrollment_mutation_accepted": False,
            "live_authorized": False,
            "approved_full_commit_sha": None,
            "one_shot_authorization_id": None,
        })
        source = (KIT / "run-d279-10.ps1").read_text(encoding="ascii")
        live_start = source.index("# Live path.")
        authority_gate = source.index("$authority = Read-D279Authority", live_start)
        absence_gate = source.index("Assert-D279GoodixAbsentSameRun", authority_gate)
        marker = source.index("[System.IO.File]::Open($marker", absence_gate)
        capture = source.index("Start-Process -FilePath $tshark", marker)
        attach = source.index("Collega il solo sensore", capture)
        finger = source.index("Esegui il PRIMO contatto", attach)
        self.assertLess(authority_gate, absence_gate)
        self.assertLess(absence_gate, marker)
        self.assertLess(marker, capture)
        self.assertLess(capture, attach)
        self.assertLess(attach, finger)
        self.assertIn('if ($branch -ne "development")', source)
        self.assertIn("possible_host_enrollment_mutation_accepted", source)
        self.assertNotIn("libusb", source.lower())
        self.assertNotRegex(source, r"(?i)control\s*0x[0-9a-f]+")

    def test_live_critical_dependency_is_pinned(self):
        source = (KIT / "run-d279-10.ps1").read_text(encoding="ascii")
        relative = (
            "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/"
            "d274_03_postprocess_second_cycle.py"
        )
        self.assertIn(relative, source)
        self.assertTrue((ROOT / relative).is_file())

    def test_observer_cli_writes_metadata_only_failure_signal(self):
        with tempfile.TemporaryDirectory(prefix="d279-10-failure-") as directory:
            pcap = Path(directory) / "missing.pcapng"
            signal = Path(directory) / "failure.json"
            saved = sys.argv
            try:
                sys.argv = ["d279_10_observer.py", "--pcap", str(pcap),
                            "--signal-output", str(signal),
                            "--deadline-seconds", "0"]
                self.assertEqual(OBSERVER.main(), 2)
            finally:
                sys.argv = saved
            failure = json.loads(signal.read_text(encoding="utf-8"))
            self.assertEqual(failure, {
                "schema": "D279_10_WIRE_OBSERVER_FAILURE_V1",
                "status": "FAIL_CLOSED",
                "failure_class": "THIRD_B0_OBSERVER_DEADLINE",
                "automatic_retry_count": 0,
            })


if __name__ == "__main__":
    unittest.main()
