# SPDX-License-Identifier: GPL-2.0-or-later
"""D260 persistent runtime architecture and anti-overclaim tests."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from analysis.D260 import d260_offline_rehearsal as rehearsal
from core.persistent_runtime import D4_CANONICAL_REQUEST
from core.runtime_transport import B0_TLS_POLICY, D4_A0_POLICY, SubmissionMode


REPO = Path(__file__).resolve().parents[1]


class D260PersistentRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readiness = rehearsal.generate(REPO)
        cls.happy = rehearsal.run_scenario("happy")

    def test_one_runtime_retains_one_tls_session_through_d4_and_baseline(self):
        audit = self.happy["audit"]
        self.assertTrue(self.happy["passed"])
        self.assertEqual(audit["tls_server_session_object_count"], 1)
        self.assertEqual(audit["tls_server_handshake_count"], 1)
        self.assertFalse(audit["second_server_session_created"])
        self.assertFalse(audit["second_psk_provisioning"])
        self.assertEqual(audit["d4_tls_application_record_count"], 0)
        self.assertTrue(audit["baseline_b0_tls_consumed"])
        self.assertEqual(self.happy["result"]["tls_state_before_cleanup"], "APPLICATION_ACTIVE")
        self.assertEqual(audit["tls_close_count"], 1)

    def test_secret_boundary_is_one_synthetic_handoff_without_fallback(self):
        audit = self.happy["audit"]
        self.assertTrue(self.happy["secret_boundary_object_id_reused"])
        self.assertEqual(audit["secret_boundary_handoff_count"], 1)
        self.assertTrue(audit["secret_boundary_zeroized"])
        self.assertTrue(self.happy["synthetic_secret_only"])
        self.assertFalse(self.readiness["REAL_E4_VALIDATED_SECRET_USED"])
        self.assertFalse(self.readiness["NEW_RUNTIME_LIVE_SECRET_PROVEN"])
        self.assertEqual(self.readiness["PSK_FALLBACK_COUNT"], 0)

    def test_b0_handshake_bridge_and_physical_policies_are_explicit(self):
        submissions = self.happy["submissions"]
        b0 = [row for row in submissions if row["kind"] == "B0"]
        self.assertTrue(b0)
        self.assertTrue(all(row["policy"] == B0_TLS_POLICY.name for row in b0))
        self.assertTrue(all(row["physical_chunk_lengths"][-1] == 64 for row in b0))
        self.assertTrue(all(row["post_submit_pacing_ms"] == 10 for row in b0))
        self.assertEqual(self.readiness["B0_TLS_HANDSHAKE_BRIDGE_STATUS"], "PASS_OFFLINE_ARCHITECTURAL")
        self.assertEqual(self.readiness["REAL_TLS_TARGET_HANDSHAKE_COUNT"], 0)

    def test_d4_is_plain_a0_exactly_once_with_fixed64_policy(self):
        chunks = D4_A0_POLICY.materialize(D4_CANONICAL_REQUEST)
        self.assertEqual(len(D4_CANONICAL_REQUEST), 10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 64)
        self.assertEqual(chunks[0][:10], D4_CANONICAL_REQUEST)
        self.assertFalse(any(chunks[0][10:]))
        self.assertEqual(D4_A0_POLICY.pre_submit_pacing_ms, 20)
        self.assertEqual(D4_A0_POLICY.timeout_ms, 200)
        self.assertEqual(self.happy["audit"]["d4_send_count"], 1)

    def test_fdt_physical_tail_is_deferred_not_invented(self):
        fdt = [
            row for row in self.happy["submissions"]
            if row["control"] in {"0x20", "0x32", "0x36", "0x50", "0x82"}
        ]
        self.assertTrue(fdt)
        self.assertTrue(all(row["mode"] == SubmissionMode.ABSTRACT_LOGICAL_ONLY.value for row in fdt))
        self.assertEqual(
            self.readiness["PHYSICAL_SUBMISSION_CONTRACT_STATUS"],
            "ABSTRACT_OFFLINE_FOR_FDT_A0_WITH_EXACT_D4_AND_B0_TLS_POLICIES",
        )
        self.assertFalse(self.readiness["READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW"])

    def test_ack_and_three_irq100_events_use_separate_sources(self):
        irq = json.loads(
            (REPO / "analysis/D260/D260_eventsource_irq_evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(irq["ack_receive_path"], "RuntimeTransport.receive")
        self.assertEqual(irq["event_receive_path"], "EventSource.wait_event")
        self.assertEqual(self.happy["event_wait_count"], 3)
        self.assertTrue(irq["IRQ100_STAGE0_EXACTLY_ONCE"])
        self.assertTrue(irq["IRQ100_STAGE1_EXACTLY_ONCE"])
        self.assertTrue(irq["IRQ100_STAGE2_EXACTLY_ONCE"])

    def test_exact_minimal_fdt_trace_and_host_only_work_are_zero(self):
        audit = self.happy["audit"]
        self.assertEqual(
            audit["exact_fdt_command_trace"],
            ["0x36", "0x50", "0x36", "0x82", "0x20", "0x36", "0x32"],
        )
        self.assertTrue(audit["baseline_b0_consumed_before_stage2"])
        self.assertTrue(audit["second_native_delta_passed"])
        self.assertEqual(audit["classifier_call_count"], 0)
        self.assertEqual(audit["raster_decode_count"], 0)
        self.assertEqual(audit["host_cache_write_count"], 0)
        self.assertEqual(audit["retry_count"], 0)

    def test_all_required_failures_are_contained_without_recovery(self):
        matrix = json.loads(
            (REPO / "analysis/D260/D260_failure_containment_matrix.json").read_text(encoding="utf-8")
        )
        self.assertEqual(matrix["status"], "PASS")
        self.assertEqual({row["scenario"] for row in matrix["rows"]}, set(rehearsal.FAILURE_SCENARIOS))
        for row in matrix["rows"]:
            self.assertTrue(row["contained"], row["scenario"])
            self.assertEqual(row["retry_count"], 0)
            self.assertEqual(row["persistent_device_write_count"], 0)
            self.assertEqual(row["a2_special_recovery_count"], 0)
            self.assertEqual(row["0x70_special_recovery_count"], 0)
            self.assertEqual(row["transport_cleanup_count"], 1)
            self.assertEqual(row["tls_close_count"], 1)

    def test_historical_seals_and_launchers_are_unchanged(self):
        for relative, expected in rehearsal.SEALED_HASHES.items():
            self.assertEqual(rehearsal.sha256_file(REPO / relative), expected, relative)
        self.assertTrue(self.readiness["SRC_SEALED_UNCHANGED"])
        self.assertTrue(self.readiness["HISTORICAL_LIVE_LAUNCHERS_UNCHANGED"])
        self.assertTrue(self.readiness["HISTORICAL_LIVE_EVIDENCE_UNCHANGED"])

    def test_readiness_is_architecture_only(self):
        self.assertEqual(self.readiness["OUTCOME"], "READY")
        self.assertEqual(self.readiness["END_TO_END_OFFLINE_RUNTIME_REHEARSAL"], "PASS")
        self.assertEqual(self.readiness["FAILURE_CONTAINMENT_MATRIX"], "PASS")
        self.assertTrue(self.readiness["READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW"])
        self.assertFalse(self.readiness["READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW"])
        self.assertFalse(self.readiness["READY_FOR_FDT_LIVE_REVIEW"])
        self.assertFalse(self.readiness["READY_FOR_FDT_LIVE"])
        self.assertFalse(self.readiness["NEW_RUNTIME_LIVE_PROVEN"])
        for field in (
            "REAL_USB_OPEN_COUNT",
            "REAL_TLS_TARGET_HANDSHAKE_COUNT",
            "REAL_CAPTURE_COUNT",
            "REAL_HARDWARE_ACTION_COUNT",
            "REAL_COMMAND_SEND_COUNT",
            "PERSISTENT_WRITE_FAMILY_COUNT",
        ):
            self.assertEqual(self.readiness[field], 0)


if __name__ == "__main__":
    unittest.main()
