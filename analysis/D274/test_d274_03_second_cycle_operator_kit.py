#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixture sintetiche e gate offline per il Kit D274/03."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit"
MODULE = KIT / "d274_03_postprocess_second_cycle.py"
SPEC = importlib.util.spec_from_file_location("d274_03_postprocessor", MODULE)
assert SPEC is not None and SPEC.loader is not None
D274 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = D274
SPEC.loader.exec_module(D274)


def a0(control: int, body: bytes = b"") -> bytes:
    inner_len = len(body) + 1
    checksum = (0xAA - ((control & 0xFE) + (inner_len & 0xFF)
                       + (inner_len >> 8) + sum(body))) & 0xFF
    inner = body + bytes([checksum])
    raw = bytes([0xA0, 0, 0, 0, control]) + inner_len.to_bytes(2, "little") + inner
    return raw[:1] + (len(raw) - 4).to_bytes(2, "little") + raw[3:]


def fingerprint_b0(total: int = 7726) -> bytes:
    declared = total - 4
    tls_len = declared - 5
    tls = b"\x17\x03\x03" + tls_len.to_bytes(2, "big") + bytes(tls_len)
    return b"\xB0" + declared.to_bytes(2, "little") + b"\x00" + tls


def alert_b0() -> bytes:
    tls = b"\x15\x03\x03\x00\x02\x02\x01"
    return b"\xB0" + len(tls).to_bytes(2, "little") + b"\x00" + tls


def nav() -> bytes:
    return a0(0x50, bytes(2409))


def descriptor() -> bytes:
    return b"\x12\x01\x00\x02\x00\x00\x00\x40\xc6\x27\x25\x51\x00\x01\x01\x02\x03\x01"


def usbpcap(payload: bytes, bus: int, device: int, endpoint: int,
            transfer: int = 3, info: int | None = None) -> bytes:
    raw = bytearray(27)
    struct.pack_into("<H", raw, 0, 27)
    struct.pack_into("<H", raw, 14, 9)
    raw[16] = (1 if endpoint & 0x80 else 0) if info is None else info
    struct.pack_into("<H", raw, 17, bus)
    struct.pack_into("<H", raw, 19, device)
    raw[21] = endpoint
    raw[22] = transfer
    struct.pack_into("<I", raw, 23, len(payload))
    return bytes(raw) + payload


def block(kind: int, body: bytes) -> bytes:
    padding = bytes((-len(body)) % 4)
    length = 12 + len(body) + len(padding)
    return struct.pack("<II", kind, length) + body + padding + struct.pack("<I", length)


def pcapng(rows: list[tuple[float, bytes]]) -> bytes:
    shb = block(0x0A0D0D0A, b"\x4d\x3c\x2b\x1a\x01\x00\x00\x00" + b"\xff" * 8)
    idb = block(1, struct.pack("<HHI", 249, 0, 65535) + struct.pack("<HH", 0, 0))
    epbs = []
    for timestamp, raw in rows:
        ticks = int(round(timestamp * 1_000_000))
        body = struct.pack("<IIIII", 0, ticks >> 32, ticks & 0xFFFFFFFF,
                           len(raw), len(raw)) + raw
        epbs.append(block(6, body))
    return shb + idb + b"".join(epbs)


def canonical_frames() -> list[tuple[str, bytes, int]]:
    return [
        ("a8", a0(0xA8, b"GF_ST411SEC_APP_12509\0"), 0x81),
        ("first_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
        ("first_0x22", a0(0x22, b"\x01\x00"), 0x01),
        ("first_0x22_ack", a0(0xB0, b"\x22\x01"), 0x81),
        ("first_b0", fingerprint_b0(), 0x81),
        ("first_0x34", a0(0x34, b"\x0a\x01" + bytes(12)), 0x01),
        ("first_0x34_ack", a0(0xB0, b"\x34\x01"), 0x81),
        ("first_irq0200", a0(0x34, b"\x00\x02" + bytes(12)), 0x81),
        ("post_up_0x20", a0(0x20, b"\x01\x00"), 0x01),
        ("post_up_0x20_ack", a0(0xB0, b"\x20\x01"), 0x81),
        ("post_up_b0", fingerprint_b0(), 0x81),
        ("post_up_0x50", a0(0x50), 0x01),
        ("post_up_0x50_ack", a0(0xB0, b"\x50\x01"), 0x81),
        ("post_0x50_nav", nav(), 0x81),
        ("rearm_0x32", a0(0x32, bytes(14)), 0x01),
        ("rearm_0x32_ack", a0(0xB0, b"\x32\x01"), 0x81),
        ("second_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
        ("second_0x22", a0(0x22, b"\x01\x00"), 0x01),
        ("second_0x22_ack", a0(0xB0, b"\x22\x01"), 0x81),
        ("second_b0", fingerprint_b0(), 0x81),
    ]


def replace(frames, label: str, raw: bytes, endpoint: int):
    index = next(i for i, row in enumerate(frames) if row[0] == label)
    frames[index] = (label, raw, endpoint)
    return frames


def remove(frames, label: str):
    return [row for row in frames if row[0] != label]


def make_capture(mutator=None, duration_scale: float = 1.0,
                 extra_descriptors: list[tuple[float, int, int]] | None = None) -> bytes:
    frames = canonical_frames()
    if mutator:
        frames = mutator(list(frames))
    rows = [(0.0, usbpcap(descriptor(), 1, 2, 0x80, transfer=2))]
    for timestamp, (_, raw, endpoint) in enumerate(frames, 1):
        rows.append((timestamp * 0.05 * duration_scale, usbpcap(raw, 1, 2, endpoint)))
    for timestamp, bus, device in extra_descriptors or []:
        rows.append((timestamp, usbpcap(descriptor(), bus, device, 0x80, transfer=2)))
    rows.sort(key=lambda row: row[0])
    return pcapng(rows)


class D27403Tests(unittest.TestCase):
    def run_capture(self, data: bytes) -> dict:
        with tempfile.TemporaryDirectory(prefix="d274-03-test-") as directory:
            path = Path(directory) / "fixture.pcapng"
            path.write_bytes(data)
            return D274.process_capture(path, hashlib.sha256(data).hexdigest(), synthetic=True)

    def failure(self, data: bytes) -> str:
        try:
            return self.run_capture(data)["failure_class"]
        except D274.EvidenceError as exc:
            return str(exc)

    def test_01_success_minimum_boundary_and_stop(self):
        result = self.run_capture(make_capture())
        self.assertEqual(result["boundary_status"], "OBSERVED_COMPLETE")
        self.assertEqual(result["stop_reason"], "SECOND_FINGERPRINT_B0")
        self.assertIsNone(result["failure_class"])
        self.assertFalse(result["third_cycle_observed"])
        self.assertEqual(result["counts"], {"irq0002": 2, "wire_0x22": 2,
                                             "fingerprint_b0": 3})
        self.assertNotIn('"payload"', json.dumps(result).lower())

    def test_02_missing_second_irq2(self):
        self.assertEqual(self.failure(make_capture(lambda rows: remove(rows, "second_irq2"))),
                         "MISSING_SECOND_IRQ2")

    def test_03_wrong_second_irq(self):
        self.assertEqual(self.failure(make_capture(lambda rows: replace(
            rows, "second_irq2", a0(0x32, b"\x03\x00" + bytes(12)), 0x81))),
            "WRONG_SECOND_IRQ")

    def test_04_missing_second_0x22(self):
        self.assertEqual(self.failure(make_capture(lambda rows: remove(rows, "second_0x22"))),
                         "MISSING_SECOND_0X22")

    def test_05_duplicate_second_0x22(self):
        def mutate(rows):
            index = next(i for i, row in enumerate(rows) if row[0] == "second_0x22_ack")
            rows.insert(index, ("duplicate", a0(0x22, b"\x01\x00"), 0x01))
            return rows
        self.assertEqual(self.failure(make_capture(mutate)), "DUPLICATE_SECOND_0X22")

    def test_06_wrong_ack_echo(self):
        self.assertEqual(self.failure(make_capture(lambda rows: replace(
            rows, "second_0x22_ack", a0(0xB0, b"\x20\x01"), 0x81))),
            "ACK_ECHO_MISMATCH")

    def test_07_ack_status_07(self):
        self.assertEqual(self.failure(make_capture(lambda rows: replace(
            rows, "second_0x22_ack", a0(0xB0, b"\x22\x07"), 0x81))),
            "ACK_STATUS_NOT_EXACT_0X01")

    def test_08_malformed_fingerprint_b0(self):
        def mutate(rows):
            bad = bytearray(fingerprint_b0())
            bad[1:3] = (8000).to_bytes(2, "little")
            return replace(rows, "second_b0", bytes(bad), 0x81)
        self.assertEqual(self.failure(make_capture(mutate)), "MALFORMED_B0")

    def test_09_wrong_b0_class(self):
        self.assertEqual(self.failure(make_capture(lambda rows: replace(
            rows, "second_b0", alert_b0(), 0x81))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")

    def test_10_third_cycle_evidence(self):
        def mutate(rows):
            rows.append(("third_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81))
            return rows
        self.assertEqual(self.failure(make_capture(mutate)), "THIRD_CYCLE_OBSERVED")

    def test_11_ambiguous_target(self):
        self.assertEqual(self.failure(make_capture(extra_descriptors=[(0.01, 1, 3)])),
                         "AMBIGUOUS_TARGET")

    def test_12_reenumeration(self):
        self.assertEqual(self.failure(make_capture(extra_descriptors=[(3.1, 1, 2)])),
                         "TARGET_REENUMERATION_OBSERVED")

    def test_13_wrong_firmware(self):
        self.assertEqual(self.failure(make_capture(lambda rows: replace(
            rows, "a8", a0(0xA8, b"GF_OTHER_APP\0"), 0x81))),
            "WRONG_OR_MISSING_FIRMWARE_APP12509")

    def test_14_capture_deadline(self):
        self.assertEqual(self.failure(make_capture(duration_scale=200)),
                         "CAPTURE_DEADLINE_EXCEEDED")

    def test_15_schema_violation_and_privacy_leak(self):
        result = self.run_capture(make_capture())
        bad = copy.deepcopy(result)
        bad["raw"] = "00"
        with self.assertRaisesRegex(D274.EvidenceError, "SCHEMA_ADDITIONAL_PROPERTY"):
            D274.validate_document(bad)
        bad = copy.deepcopy(result)
        bad["second_irq2_frame"]["frame"] = 1.5
        with self.assertRaisesRegex(D274.EvidenceError, "SCHEMA_ANYOF"):
            D274.validate_document(bad)

    def test_16_unauthorized_live_template(self):
        authority = json.loads((KIT / "D274_03_live_authority.json").read_text())
        self.assertFalse(authority["baseline_approved"])
        self.assertFalse(authority["approved_for_capture"])
        self.assertFalse(authority["live_authorized"])
        self.assertIsNone(authority["approved_full_commit_sha"])
        runner = (KIT / "invoke-d274-03-live-once.ps1").read_text()
        authority_gate = runner.index('if ($authority.baseline_approved -ne $true)')
        capture_start = runner.index("Start-Process -FilePath $TsharkPath")
        self.assertLess(authority_gate, capture_start)

    def test_17_stale_baseline_and_live_critical_gate(self):
        runner = (KIT / "invoke-d274-03-live-once.ps1").read_text()
        self.assertIn("^[0-9a-f]{40}$", runner)
        self.assertIn("$head -ne $approvedSha", runner)
        self.assertIn("git -C $RepositoryRoot diff --quiet $approvedSha -- @critical", runner)
        self.assertIn("git -C $RepositoryRoot status --porcelain -- @critical", runner)
        self.assertIn('$branch -ne "development"', runner)

    def test_18_reused_marker_fail_closed_and_no_retry(self):
        runner = (KIT / "invoke-d274-03-live-once.ps1").read_text()
        self.assertIn("[System.IO.FileMode]::CreateNew", runner)
        self.assertIn("marker one-shot già esistente", runner)
        self.assertNotRegex(runner, r"(?i)\bwhile\b|\bdo\s*\{")
        self.assertIn("automatic_retry_count = 0", runner)

    def test_19_passive_tshark_only_and_stop_contract(self):
        runner = (KIT / "invoke-d274-03-live-once.ps1").read_text()
        launcher = (KIT / "avvia-d274-03.ps1").read_text()
        lower = runner.lower()
        self.assertIn('"-a", "duration:180"', runner)
        self.assertIn('"-w"', runner)
        self.assertIn("Stop-D274Capture", runner)
        self.assertNotIn("libusb", lower)
        self.assertNotIn("pyusb", lower)
        self.assertNotIn("clearapp", lower)
        self.assertNotIn("provision", lower)
        self.assertNotIn("iap", lower)
        for source in (runner, launcher):
            source_lower = source.lower()
            self.assertIn("get-acl", source_lower)
            self.assertIn("accesscontroltype", source_lower)
            self.assertIn("securityidentifier", source_lower)
            self.assertIn("filesystemrights]::read", source_lower)
            self.assertNotIn("set-acl", source_lower)
            self.assertNotIn("icacls", source_lower)

    def test_20_operator_surface_is_italian(self):
        sources = "\n".join((KIT / name).read_text(encoding="utf-8") for name in (
            "avvia-d274-03.ps1", "invoke-d274-03-live-once.ps1",
            "collect-d274-03-results.ps1", "D274_03_OPERATOR_README_IT.md"))
        for phrase in ("NON toccare", "Appoggia il dito", "Cattura arrestata",
                       "Non completare", "nessun retry", "fallire chiuso"):
            self.assertIn(phrase.lower(), sources.lower())
        for english_instruction in ("touch the sensor", "select exactly one mode",
                                    "capture started", "do not retry", "run now"):
            self.assertNotIn(english_instruction, sources.lower())
        # Le stringhe rivolte all'operatore passano soltanto da questi tre cmdlet.
        operator_lines = [line for line in sources.splitlines()
                          if re.search(r"\b(Write-Host|Read-Host|throw)\b", line)]
        self.assertGreater(len(operator_lines), 12)

    def test_21_manifest_and_schema_are_strict(self):
        manifest = json.loads((KIT / "D274_03_kit_manifest.json").read_text())
        schema = json.loads((KIT / "D274_03_evidence_schema.json").read_text())
        self.assertEqual(manifest["operator_language"], "ITALIAN")
        self.assertFalse(manifest["automatic_retry_authorized"])
        self.assertFalse(manifest["third_cycle_authorized"])
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["frameMetadata"]["additionalProperties"])

    def test_22_historical_capture_does_not_close_second_cycle(self):
        path = ROOT / "analysis/D230/work/GoodixExport/rilevamento.pcapng"
        result = D274.process_capture(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                                      synthetic=True)
        self.assertEqual(result["boundary_status"], "NOT_OBSERVED_COMPLETE")
        self.assertEqual(result["failure_class"], "MISSING_SECOND_IRQ2")
        self.assertIsNotNone(result["rearm_0x32_ack_frame"])
        self.assertIsNone(result["second_b0_frame"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
