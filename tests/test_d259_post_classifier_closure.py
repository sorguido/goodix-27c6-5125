# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import unittest

from analysis.D259 import d259_minimal_replay as REPLAY
from analysis.D259 import d259_post_classifier_audit as AUDIT


REPO = Path(__file__).resolve().parents[1]


class D259PostClassifierClosureTests(unittest.TestCase):
    def test_hash_gates_and_complete_return_matrix(self):
        result = AUDIT.audit(REPO)
        self.assertEqual(result["hash_gates"]["gfusb_sha256"], AUDIT.EXPECTED_DLL_SHA256)
        self.assertEqual(
            result["hash_gates"]["d255_capture_sha256"],
            AUDIT.EXPECTED_D255_CAPTURE_SHA256,
        )
        rows = result["wire_rows"]
        self.assertEqual(len(rows), 10)
        self.assertEqual({row["classifier"] for row in rows}, {"NAV", "IMAGE"})
        for classifier in ("NAV", "IMAGE"):
            self.assertEqual(
                {row["return"] for row in rows if row["classifier"] == classifier},
                {"0", "1", "2", "3", "negative_or_other"},
            )

    def test_every_classifier_return_has_no_wire_or_recovery_effect(self):
        result = AUDIT.audit(REPO)
        for row in result["wire_rows"]:
            self.assertEqual(row["gf_update_all_base_result"], "1_SUCCESS")
            self.assertEqual(row["fdt_table_effect"], "NONE")
            self.assertEqual(row["final_0x32_payload_effect"], "NONE")
            self.assertEqual(row["additional_usb_commands"], "NONE")
            self.assertEqual(row["recovery_command"], "NONE")
            self.assertEqual(row["final_0x32_reachable"], "YES")
        classifier_recovery = result["recovery_rows"][0]
        self.assertEqual(classifier_recovery["a2_reentry"], 0)
        self.assertEqual(classifier_recovery["0x70_reentry"], 0)

    def test_cache_is_host_only_conditional_and_disabled_for_minimal_path(self):
        decisions = AUDIT.audit(REPO)["decisions"]
        self.assertEqual(decisions["OEM_CACHE_WRITE_BEFORE_FINAL_0x32"], "CONDITIONAL")
        self.assertFalse(decisions["OEM_CACHE_WRITE_AFTER_FINAL_0x32"])
        self.assertFalse(decisions["OEM_CACHE_WRITE_REQUIRED_FOR_FINAL_0x32"])
        self.assertFalse(decisions["OEM_CACHE_WRITE_REQUIRED_FOR_DEVICE_PROGRESS"])
        self.assertEqual(decisions["LINUX_FIRST_LIVE_CACHE_WRITE_POLICY"], "DISABLED")

    def test_full_minimal_replay_preserves_final_table_payload_and_safety(self):
        result = REPLAY.run(REPO)
        scenario = result["scenario"]
        self.assertTrue(scenario["requests_wire_exact_except_synthetic_b0_is_response_only"])
        self.assertEqual(
            scenario["target_command_trace"],
            ["0x36", "0x50", "0x36", "0x82", "0x20", "0x36", "0x32"],
        )
        self.assertTrue(scenario["delta_native_predicate_passed"])
        self.assertTrue(scenario["second_delta_native_predicate_passed"])
        self.assertTrue(scenario["baseline_b0_tls_consumed"])
        self.assertTrue(scenario["first_0x32_sent_once"])
        self.assertEqual(scenario["semantic_classifier_call_count"], 0)
        self.assertEqual(scenario["raster_decode_count"], 0)
        self.assertEqual(scenario["host_cache_write_count"], 0)
        self.assertEqual(scenario["automatic_retry_count"], 0)
        self.assertEqual(scenario["persistent_write_family_count"], 0)
        self.assertEqual(scenario["a2_reentry_injection"], 0)
        self.assertEqual(scenario["0x70_reentry_injection"], 0)
        self.assertEqual(scenario["timeouts_ms"], scenario["expected_timeouts_ms"])
        self.assertFalse(result["closure"]["READY_FOR_FDT_LIVE"])
        self.assertTrue(result["closure"]["READY_FOR_FDT_LIVE_REVIEW"])
        self.assertTrue(all(value == 0 for value in result["safety"].values()))


if __name__ == "__main__":
    unittest.main()
