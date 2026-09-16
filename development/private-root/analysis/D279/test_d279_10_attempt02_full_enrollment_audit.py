#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("d279_10_attempt02_full_enrollment_audit.py")
SPEC = importlib.util.spec_from_file_location("d279_10_attempt02_audit_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class Attempt02AuditTests(unittest.TestCase):
    def test_cycle_shapes_remain_exact_and_terminal_has_no_rearm(self) -> None:
        self.assertEqual(
            AUDIT.classify_cycle_shape(1, AUDIT.CYCLE1_SHAPE),
            "FIRST_CYCLE_NAV_TRANSITION",
        )
        self.assertEqual(
            AUDIT.classify_cycle_shape(20, AUDIT.REPEATED_SHAPE),
            "REPEATED_ACQUISITION_TRANSITION_WITH_REARM",
        )
        self.assertEqual(
            AUDIT.classify_cycle_shape(21, AUDIT.TERMINAL_SHAPE),
            "TERMINAL_ACQUISITION_TRANSITION_WITHOUT_REARM",
        )
        with self.assertRaisesRegex(AUDIT.AuditError, "UNEXPECTED_CYCLE_SHAPE_21"):
            AUDIT.classify_cycle_shape(21, AUDIT.REPEATED_SHAPE)

    def test_contact_delta_is_not_falsely_localized_without_timestamps(self) -> None:
        result = AUDIT.correlate_contacts({"contact_count": 22}, 21)
        self.assertEqual(
            result["operator_contact_without_complete_wire_acquisition_lifecycle_count"], 1
        )
        self.assertFalse(result["per_contact_timestamps_available"])
        self.assertFalse(result["specific_unmatched_contact_identifiable"])
        self.assertIn("NOT_TEMPORALLY_LOCALIZABLE", result["classification"])

    @unittest.skipUnless(AUDIT.ATTEMPT.is_dir(), "private attempt evidence absent")
    def test_hash_gated_private_attempt_reconstructs_complete_enrollment(self) -> None:
        result = AUDIT.analyze(ROOT)
        self.assertEqual(result["source_integrity"]["pcapng_packet_count"], 924)
        self.assertEqual(result["source_integrity"]["target_frame_count"], 442)
        self.assertEqual(result["cycle_shapes"]["primary_cycle_rows"][-1]["cycle"], 21)
        self.assertEqual(result["cycle_shapes"]["fingerprint_shape_b0_count"], 43)
        self.assertEqual(
            result["timeline"]["acquisition_window"]["primary_b0_to_next_irq2_ms"]["maximum_after_cycle"],
            9,
        )
        self.assertEqual(result["command_shape_observations"]["0x34_distinct_body_count"], 21)
        relations = result["command_shape_observations"]["fdt_table_derivation_relations"]
        self.assertTrue(relations["0x34_all_41_equal_same_stage_irq2_up_derivation"])
        self.assertTrue(relations["0x36_all_20_equal_previous_stage_irq0200_down_derivation"])
        self.assertTrue(relations["0x36_all_20_differ_from_same_stage_0x34_table"])
        self.assertTrue(relations["0x32_all_21_equal_same_stage_irq0200_down_derivation"])
        self.assertTrue(relations["cycle_1_two_0x32_share_table_but_have_distinct_timestamps"])
        self.assertFalse(relations["raw_table_bytes_exported"])
        self.assertEqual(result["timeline"]["terminal"]["post_ui_target_packet_count"], 0)
        self.assertEqual(result["observer_incremental_state"]["finalized_protocol_contradiction_count"], 0)
        self.assertFalse(result["content_bytes_exported"])


if __name__ == "__main__":
    unittest.main()
