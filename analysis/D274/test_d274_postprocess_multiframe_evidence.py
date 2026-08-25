#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic-only tests for the D274 offline postprocessor and operator kit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "analysis/D274/d274_postprocess_multiframe_evidence.py"
SPEC = importlib.util.spec_from_file_location("d274_postprocessor", MODULE_PATH)
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
    declared = len(raw) - 4
    return raw[:1] + declared.to_bytes(2, "little") + raw[3:]


def b0() -> bytes:
    body = b"\x17\x03\x03" + bytes(29)
    return b"\xB0" + len(body).to_bytes(2, "little") + b"\x00" + body


def nav(control: int = 0x50) -> bytes:
    return a0(control, bytes(2409))


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


def block(block_type: int, body: bytes) -> bytes:
    padding = bytes((-len(body)) % 4)
    length = 12 + len(body) + len(padding)
    return struct.pack("<II", block_type, length) + body + padding + struct.pack("<I", length)


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
    # label, raw, endpoint
    return [
        ("a8", a0(0xA8, b"GF_ST411SEC_APP_12509\0"), 0x81),
        ("first_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
        ("first_0x22", a0(0x22, b"\x01\x00"), 0x01),
        ("first_0x22_ack", a0(0xB0, b"\x22\x01"), 0x81),
        ("first_image_b0", b0(), 0x81),
        ("first_0x34", a0(0x34, b"\x0a\x01" + bytes(12)), 0x01),
        ("first_0x34_ack", a0(0xB0, b"\x34\x01"), 0x81),
        ("first_irq0200", a0(0x34, b"\x00\x02" + bytes(12)), 0x81),
        ("post_up_0x20", a0(0x20, b"\x01\x00"), 0x01),
        ("post_up_0x20_ack", a0(0xB0, b"\x20\x01"), 0x81),
        ("post_up_b0", b0(), 0x81),
        ("post_up_0x50", a0(0x50), 0x01),
        ("post_up_0x50_ack", a0(0xB0, b"\x50\x01"), 0x81),
        ("post_0x50_nav", nav(), 0x81),
        ("rearm_0x32", a0(0x32, bytes(14)), 0x01),
        ("rearm_0x32_ack", a0(0xB0, b"\x32\x01"), 0x81),
        ("second_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
        ("second_0x22", a0(0x22, b"\x01\x00"), 0x01),
        ("second_0x22_ack", a0(0xB0, b"\x22\x01"), 0x81),
        ("second_b0", b0(), 0x81),
    ]


def make_capture(mutator=None, duration_scale: float = 1.0,
                 extra_descriptors: list[tuple[float, int, int]] | None = None) -> bytes:
    frames = canonical_frames()
    if mutator:
        frames = mutator(list(frames))
    rows = [(0.0, usbpcap(descriptor(), 1, 2, 0x80, transfer=2))]
    for timestamp, (label, raw, endpoint) in enumerate(frames, 1):
        del label
        rows.append((timestamp * 0.05 * duration_scale,
                     usbpcap(raw, 1, 2, endpoint)))
    for timestamp, bus, device in extra_descriptors or []:
        rows.append((timestamp, usbpcap(descriptor(), bus, device, 0x80, transfer=2)))
    rows.sort(key=lambda item: item[0])
    return pcapng(rows)


def replace_label(frames, label: str, raw: bytes, endpoint: int):
    index = next(i for i, row in enumerate(frames) if row[0] == label)
    frames[index] = (label, raw, endpoint)
    return frames


def remove_label(frames, label: str):
    return [row for row in frames if row[0] != label]


class D274Tests(unittest.TestCase):
    def run_capture(self, data: bytes, markers: Path | None = None):
        with tempfile.TemporaryDirectory(prefix="d274-test-") as directory:
            path = Path(directory) / "fixture.pcapng"
            path.write_bytes(data)
            return D274.process_capture(path, hashlib.sha256(data).hexdigest(),
                                        "SYNTHETIC_TEST", markers, "SYNTHETIC")

    def failure(self, data: bytes) -> str:
        try:
            result = self.run_capture(data)
            return result["failure_class"]
        except D274.EvidenceError as exc:
            return str(exc)

    def test_01_happy_path_synthetic_pcap(self):
        result = self.run_capture(make_capture())
        self.assertEqual(result["result_class"], "SYNTHETIC_FIXTURE_PASS")
        self.assertIsNone(result["failure_class"])
        self.assertFalse(result["second_cycle_target_observed"])
        self.assertFalse(result["privacy_payload_exported"])
        serialized = json.dumps(result).lower()
        self.assertNotIn('"raw"', serialized)
        self.assertNotIn('"body"', serialized)

    def test_02_missing_second_irq2(self):
        self.assertEqual(self.failure(make_capture(lambda f: remove_label(f, "second_irq2"))),
                         "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST")

    def test_03_second_irq2_missing_0x22(self):
        self.assertEqual(self.failure(make_capture(lambda f: remove_label(f, "second_0x22"))),
                         "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST")

    def test_04_wrong_0x20(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "post_up_0x20", a0(0x21, b"\x01\x00"), 0x01))),
            "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST")

    def test_05_wrong_0x50(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "post_up_0x50", a0(0x52), 0x01))),
            "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST")

    def test_06_0x51_is_not_nav(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "post_0x50_nav", nav(0x51), 0x81))),
            "WIRE_0X51_IS_NOT_NAV")

    def test_07_ack_wrong_echo(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_0x22_ack", a0(0xB0, b"\x20\x01"), 0x81))),
            "ACK_ECHO_MISMATCH")

    def test_08_ack_wrong_status(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_0x22_ack", a0(0xB0, b"\x22\x07"), 0x81))),
            "ACK_STATUS_NOT_EXACT_0X01")

    def test_09_b0_before_second_0x22(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_0x22", b0(), 0x81))),
            "B0_BEFORE_SECOND_0X22")

    def test_10_third_cycle(self):
        def mutate(frames):
            frames.append(("third_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81))
            return frames
        self.assertEqual(self.failure(make_capture(mutate)), "THIRD_CYCLE_OBSERVED")

    def test_11_duplicate_0x22(self):
        def mutate(frames):
            index = next(i for i, row in enumerate(frames) if row[0] == "second_0x22_ack")
            frames.insert(index, ("duplicate_0x22", a0(0x22, b"\x01\x00"), 0x01))
            return frames
        self.assertEqual(self.failure(make_capture(mutate)), "DUPLICATE_SECOND_0X22")

    def test_12_duplicate_b0(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: f + [("duplicate_b0", b0(), 0x81)])), "DUPLICATE_SECOND_B0")

    def test_13_reenumeration(self):
        self.assertEqual(self.failure(make_capture(extra_descriptors=[(3.1, 1, 2)])),
                         "TARGET_REENUMERATION_OBSERVED")

    def test_14_second_target(self):
        self.assertEqual(self.failure(make_capture(extra_descriptors=[(0.1, 1, 3)])),
                         "SECOND_TARGET_OBSERVED")

    def test_15_truncated_pcap_metadata(self):
        self.assertEqual(self.failure(make_capture()[:-3]), "TRUNCATED_PCAP_METADATA")

    def test_16_malformed_a0(self):
        def mutate(frames):
            bad = bytearray(a0(0x22, b"\x01\x00")); bad[-1] ^= 1
            return replace_label(frames, "second_0x22", bytes(bad), 0x01)
        self.assertEqual(self.failure(make_capture(mutate)), "MALFORMED_A0")

    def test_17_malformed_b0(self):
        def mutate(frames):
            bad = bytearray(b0()); bad[1:3] = (100).to_bytes(2, "little")
            return replace_label(frames, "second_b0", bytes(bad), 0x81)
        self.assertEqual(self.failure(make_capture(mutate)), "MALFORMED_B0")

    def test_18_capture_deadline(self):
        self.assertEqual(self.failure(make_capture(duration_scale=200)),
                         "CAPTURE_DEADLINE_EXCEEDED")

    def test_19_marker_out_of_order(self):
        with tempfile.TemporaryDirectory(prefix="d274-markers-") as directory:
            marker = Path(directory) / "markers.tsv"
            marker.write_text("timestamp_utc\tevent\n2026-01-01T00:00:00Z\tVM_USB_ATTACH_END\n"
                              "2026-01-01T00:00:01Z\tVM_USB_ATTACH_BEGIN\n", encoding="utf-8")
            self.assertEqual(self.failure_with_markers(make_capture(), marker), "MARKER_OUT_OF_ORDER")

    def failure_with_markers(self, data: bytes, marker: Path) -> str:
        try:
            self.run_capture(data, marker)
        except D274.EvidenceError as exc:
            return str(exc)
        return "NO_FAILURE"

    def test_20_ui_terminal_before_second_finger(self):
        with tempfile.TemporaryDirectory(prefix="d274-markers-") as directory:
            marker = Path(directory) / "markers.tsv"
            marker.write_text("timestamp_utc\tevent\n"
                              "2026-01-01T00:00:00Z\tPREFLIGHT_COMPLETE\n"
                              "2026-01-01T00:00:01Z\tENROLLMENT_COMMIT_UI\n", encoding="utf-8")
            self.assertEqual(self.failure_with_markers(make_capture(), marker), "UI_TERMINAL_CONDITION")

    def test_21_hash_gate(self):
        with tempfile.TemporaryDirectory(prefix="d274-hash-") as directory:
            path = Path(directory) / "fixture.pcapng"
            path.write_bytes(make_capture())
            with self.assertRaisesRegex(D274.EvidenceError, "CAPTURE_HASH_MISMATCH"):
                D274.process_capture(path, "0" * 64, "UNKNOWN")

    def test_22_schema_and_powershell_static_contract(self):
        schema = json.loads((ROOT / "analysis/D274/D274_01_evidence_schema.json").read_text())
        self.assertIn("second_b0_frame", schema["required"])
        script = (ROOT / "operator_kit/d274-windows-multiframe-evidence.ps1").read_text()
        self.assertIn("$script:D274RealCaptureCapability = 0", script)
        self.assertIn("$script:D274HardDisabled = $true", script)
        self.assertIn("HARD_DISABLED_D274_01", script)
        self.assertNotIn("Start-Process", script)
        self.assertNotIn(" -w ", script)
        parameters = script.split("param(", 1)[1].split(")", 1)[0]
        for name in ("SelfTestOnly", "PreflightOnly", "PreAuthorizationSimulationOnly",
                     "IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture"):
            self.assertIn("$" + name, parameters)


if __name__ == "__main__":
    unittest.main(verbosity=2)
