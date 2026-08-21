#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Dedicated offline unit tests for the D254 external-evidence parser."""

from __future__ import annotations

import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("d254_external_audit.py")
SPEC = importlib.util.spec_from_file_location("d254_external_audit", SCRIPT)
assert SPEC and SPEC.loader
D254 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D254)


def a0(control: int, body: bytes, physical: int | None = None) -> bytes:
    inner_len = len(body) + 1
    checksum = (0xAA - ((control & 0xFE) + (inner_len & 0xFF) +
                       (inner_len >> 8) + sum(body))) & 0xFF
    raw = bytearray(b"\xA0\x00\x00\x00")
    raw += bytes((control,)) + inner_len.to_bytes(2, "little") + body + bytes((checksum,))
    raw[1:3] = (len(raw) - 4).to_bytes(2, "little")
    if physical is not None:
        raw += bytes(physical - len(raw))
    return bytes(raw)


class D254ParserTests(unittest.TestCase):
    def test_learned_table_matches_all_three_corpora_examples(self):
        self.assertEqual(D254.learned_table("5e017f0147016f014f016d01"),
                         "80af80bf80a380b780a780b6")
        self.assertEqual(D254.learned_table("5e017f014901700150016f01"),
                         "80af80bf80a480b880a880b7")
        self.assertEqual(D254.learned_table("0b012301db0017010a013101"),
                         "80858091806d808b80858098")

    def test_a0_decode_preserves_logical_physical_boundary(self):
        packet = {"packet_index": 7, "timestamp_us": 10, "endpoint": 1,
                  "transfer": 3, "payload": a0(0x36, b"\x09\x01" + bytes(12), 64)}
        row = D254.decode_a0(packet)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["control"], 0x36)
        self.assertEqual(row["logical_length"], 22)
        self.assertEqual(row["physical_length"], 64)
        self.assertEqual(row["tail_nonzero_offsets"], [])

    def test_a0_checksum_corruption_fails_closed(self):
        payload = bytearray(a0(0x22, b"\x01\x00", 64))
        payload[9] ^= 1
        packet = {"packet_index": 1, "timestamp_us": 0, "endpoint": 1,
                  "transfer": 3, "payload": bytes(payload)}
        with self.assertRaisesRegex(AssertionError, "checksum"):
            D254.decode_a0(packet)

    def test_minimal_usbpcap_reader(self):
        payload = a0(0x20, b"\x01\x00", 64)
        pseudo = bytearray(27)
        struct.pack_into("<H", pseudo, 0, 27)
        pseudo[21] = 1
        pseudo[22] = 3
        packet = bytes(pseudo) + payload
        global_header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 249)
        record = struct.pack("<IIII", 1, 2, len(packet), len(packet)) + packet
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.pcap"
            path.write_bytes(global_header + record)
            rows = list(D254.iter_usbpcap(path))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["endpoint"], 1)
        self.assertEqual(D254.decode_a0(rows[0])["control"], 0x20)

    def test_matrix_cells_are_evidence_classed(self):
        result = {
            "issue63": {"fdt36_count": 22},
            "source_a": {
                "fdt_initial_seed_hex": "b3b3c3c3a8a8b5b5a8a8b7b7",
                "wbdi": {"fdt_manual_passes": [{"seed_table_hex": "afafbfbfa4a4b8b8a8a8b7b7"}]},
            },
        }
        matrix = D254.build_matrix(result)
        self.assertEqual(len(matrix["rows"]), 9)
        allowed = {"TARGET_CAPTURE", "OEM_LOG_CROSS_FAMILY", "THIRD_PARTY_CODE",
                   "THIRD_PARTY_CAPTURE", "ROCKY_LIVE_CORROBORATION", "UNKNOWN"}
        for row in matrix["rows"]:
            for column in matrix["columns"]:
                self.assertIn(row[column]["evidence_class"], allowed)


if __name__ == "__main__":
    unittest.main()
