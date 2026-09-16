#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name(
    "d279_31_attempt02_tls_reconstruction_feasibility.py"
)
SPEC = importlib.util.spec_from_file_location("d279_31_feasibility_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


def b0(payload: bytes, *, direction: str = "device_to_host") -> SimpleNamespace:
    tls = bytes((payload[0], 0x03, 0x03)) + len(payload[1:]).to_bytes(2, "big") + payload[1:]
    raw = bytes((0xB0,)) + len(tls).to_bytes(2, "little") + b"\x00" + tls
    return SimpleNamespace(
        outer=0xB0,
        truncated=False,
        raw=raw,
        packet_index=7,
        direction=direction,
    )


class Attempt02TlsFeasibilityTests(unittest.TestCase):
    def test_single_tls_record_parser_is_exact(self) -> None:
        record = AUDIT.parse_single_tls_record(b0(b"\x17abc"))
        self.assertEqual(record.content_type, 0x17)
        self.assertEqual(record.fragment, b"abc")
        malformed = b0(b"\x17abc")
        malformed.raw += b"\x00"
        with self.assertRaisesRegex(AUDIT.FeasibilityError,
                                    "B0_NOT_EXACTLY_ONE_TLS_RECORD"):
            AUDIT.parse_single_tls_record(malformed)

    def test_handshake_parser_rejects_type_and_length_mismatch(self) -> None:
        body = b"abc"
        record = AUDIT.parse_single_tls_record(
            b0(b"\x16" + b"\x01" + len(body).to_bytes(3, "big") + body)
        )
        self.assertEqual(AUDIT.parse_handshake(record, 0x01), body)
        with self.assertRaisesRegex(AUDIT.FeasibilityError,
                                    "UNEXPECTED_HANDSHAKE_TYPE"):
            AUDIT.parse_handshake(record, 0x02)

    @unittest.skipUnless(AUDIT.CAPTURE.is_file(), "private attempt evidence absent")
    def test_hash_gated_attempt02_has_complete_passive_inputs_except_psk(self) -> None:
        result = AUDIT.analyze(AUDIT.CAPTURE)
        self.assertTrue(result["handshake"]["complete_from_client_hello_through_both_finished"])
        self.assertEqual(result["application_records"]["device_to_host_count"], 43)
        self.assertEqual(result["record_sequence_assignment"]["client_application_sequence_last"], 43)
        self.assertEqual(
            result["passive_reconstruction"]["feasibility"],
            "FEASIBLE_WITH_AUTHORIZED_TARGET_PSK",
        )
        self.assertTrue(result["passive_reconstruction"]["protected_psk_required"])
        self.assertFalse(result["handshake"]["client_hello"]["extended_master_secret_offered"])
        self.assertFalse(result["handshake"]["server_hello"]["extended_master_secret_selected"])
        self.assertFalse(result["passive_reconstruction"]["psk_accessed"])
        self.assertEqual(result["passive_reconstruction"]["records_decrypted"], 0)
        self.assertFalse(any(result["privacy"].values()))


if __name__ == "__main__":
    unittest.main()
