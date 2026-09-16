from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis.D245.d245_operator_dry_run import (
    run,
    verify_historical_launcher_integrity,
    verify_sealed_baseline,
    verify_unseal_runtime_reseal,
)
from analysis.D245.d245_preflight import (
    D245_MARKER_NAME,
    d245_runtime_paths,
    offline_sandbox_preflight,
)
from src.goodix5125_d232_offline import parse_a0


REPOSITORY = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY / "operator_kit/d245-live-tls-once.sh"
CONTRACT = REPOSITORY / "analysis/D245/D245_A8_E4_contract.json"


class D245PreconditionClosureTests(unittest.TestCase):
    def test_p1_p3_p4_contract_and_byte_exact_a8(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            contract["provenance"]["D245_D179_PRIMARY_RUNTIME_ARTIFACTS_STATUS"],
            "PURGED_UNAVAILABLE_IN_CURRENT_REPOSITORY",
        )
        self.assertEqual(
            contract["provenance"]["D245_A8_CURRENT_LOCAL_CORPUS_CORROBORATION"],
            "PASS",
        )
        self.assertEqual(
            contract["epistemic_classification"]["D245_A8_INITIALIZER_STATUS"],
            "NOT_PROVEN",
        )
        self.assertEqual(contract["a8"]["response_authorizing_statuses"], [1, 7])
        self.assertEqual(contract["a8"]["response_reads_after_authorized_ack"], 1)
        self.assertEqual(
            contract["a8"]["other_status_policy"],
            "FAIL_CLOSED_WITHOUT_SECOND_RESPONSE_READ",
        )
        self.assertNotIn("terminal_status_without_response", contract["a8"])
        frame = bytes.fromhex(contract["a8"]["request_hex"])
        self.assertEqual(frame.hex(), "a00600a6a803000000ff")
        self.assertEqual(len(frame), 10)
        self.assertEqual((parse_a0(frame).control, parse_a0(frame).body), (0xA8, b"\x00\x00"))
        self.assertEqual(
            verify_sealed_baseline()["D245_SEALED_BASELINE_AFTER_RENAME_STATUS"],
            "MATCH",
        )

    def test_unseal_runtime_matrix_and_reseal_are_closed_offline(self):
        closure = verify_unseal_runtime_reseal()
        self.assertEqual(closure["patch_apply"], "PASS_WITHOUT_OFFSET")
        self.assertEqual(closure["source_reseal"], "PASS_WITHOUT_OFFSET")
        self.assertEqual(closure["sealed_sha256"], closure["final_sealed_sha256"])
        matrix = closure["runtime_matrix"]
        self.assertEqual(matrix["status"], "PASS")
        self.assertEqual(
            matrix["happy_cases"],
            [
                "A8_ACK_01_VALID_RESPONSE_PASS",
                "A8_ACK_07_VALID_RESPONSE_PASS",
            ],
        )
        self.assertEqual(matrix["a8_ack01_valid_response_e4_count"], 1)
        self.assertEqual(matrix["a8_ack07_valid_response_e4_count"], 1)
        self.assertEqual(matrix["a8_ack07_response_timeout_e4_count"], 0)
        self.assertEqual(matrix["a8_ack07_response_malformed_e4_count"], 0)
        self.assertEqual(matrix["a8_ack07_wrong_control_e4_count"], 0)
        self.assertEqual(matrix["a8_ack07_fw12508_e4_count"], 0)
        self.assertEqual(matrix["a8_ack07_fw12510_e4_count"], 0)
        self.assertEqual(matrix["a8_ack01_fw_mismatch_e4_count"], 0)
        self.assertEqual(matrix["other_ack_status_second_in_count"], 0)
        self.assertEqual(matrix["other_ack_status_e4_count"], 0)
        self.assertEqual(matrix["a8_ack07_valid_response_extra_frame_e4_count"], 0)
        self.assertEqual(matrix["a8_out_timeout_e4_count"], 0)
        self.assertEqual(matrix["a8_in_timeout_e4_count"], 0)
        self.assertEqual(matrix["server_flight_usb_chunk_lengths"], [64, 64, 64])
        self.assertEqual(matrix["server_flight_pacing_count"], 2)
        self.assertEqual(matrix["retry_count"], matrix["d4_count"])
        self.assertEqual(matrix["real_usb_access"], 0)

    def test_durable_closure_ingests_d244_and_never_executes_live_io(self):
        with tempfile.TemporaryDirectory(prefix="d245-test-report-") as directory:
            destination = Path(directory) / "closure.json"
            report = run(destination)
            self.assertEqual(report, json.loads(destination.read_text(encoding="utf-8")))
        self.assertTrue(report["D245_D244_LIVE_RESULT_INGESTED"])
        self.assertTrue(report["D245_D244_E4_OUT_COMPLETED"])
        self.assertTrue(report["D245_D244_E4_IN_TIMEOUT"])
        self.assertEqual(report["D244_SENSOR_ELECTRICAL_POWER_CYCLE_STATUS"], "NOT_PROVEN")
        self.assertEqual(report["D245_EXECUTABLE_CLOSURE_GATE"], "PASS")
        self.assertEqual(report["live_usb_execution"], "NOT_PERFORMED")
        self.assertEqual(report["real_tls_handshake"], 0)
        self.assertEqual(report["D245_HISTORICAL_LAUNCHER_INTEGRITY"], "RESTORED")
        self.assertEqual(report["D245_HISTORICAL_LAUNCHER_MUTATION_COUNT"], 0)
        self.assertEqual(
            report["D245_LIVE_BASELINE_APPROVAL_STATUS"],
            "LIVE_BASELINE_APPROVAL_PENDING_USER_REVIEW",
        )

    def test_historical_launchers_match_their_canonical_bundles_byte_exactly(self):
        integrity = verify_historical_launcher_integrity()
        self.assertEqual(integrity["D245_HISTORICAL_LAUNCHER_INTEGRITY"], "RESTORED")
        self.assertEqual(integrity["D245_HISTORICAL_LAUNCHER_MUTATION_COUNT"], 0)
        self.assertEqual(len(integrity["files"]), 5)
        self.assertTrue(all(row["status"] == "MATCH" for row in integrity["files"]))

    def test_fprintd_initial_state_is_not_a_sufficient_explanation(self):
        expected = {
            "D241": ("active", "pass"),
            "D242": ("active", "timeout"),
            "D243": ("active", "timeout"),
            "D244": ("inactive", "timeout"),
        }
        for step, (state, outcome) in expected.items():
            report = json.loads(
                (REPOSITORY / f"analysis/{step}/{step}_operator_live_stdout.json").read_text()
            )
            self.assertEqual(report["fprintd_initial_state"], state)
            if outcome == "pass":
                self.assertEqual(report["runtime_psk_e4_binding_status"], "match")
            else:
                self.assertEqual(report["abort_class"], outcome)

    def test_d245_namespace_and_offline_preflight_do_not_touch_real_marker(self):
        paths = d245_runtime_paths()
        self.assertEqual(paths.single_use_marker.name, D245_MARKER_NAME)
        self.assertEqual(paths.report_directory.name, "d245-results")
        with tempfile.TemporaryDirectory(prefix="d245-preflight-test-") as directory:
            report = offline_sandbox_preflight(Path(directory))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["usb_open_count"], 0)
        self.assertEqual(report["goodix_command_count"], 0)

    def test_launcher_requires_distinct_authorization_and_dry_run_passes(self):
        syntax = subprocess.run(["bash", "-n", str(LAUNCHER)], cwd=REPOSITORY, capture_output=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr.decode())
        denied = subprocess.run([str(LAUNCHER)], cwd=REPOSITORY, text=True, capture_output=True)
        self.assertEqual(denied.returncode, 64)
        self.assertIn("EXPLICIT_D245_SINGLE_RUN_AUTHORIZATION_REQUIRED", denied.stderr)
        dry = subprocess.run(
            [str(LAUNCHER), "--offline-dry-run"], cwd=REPOSITORY, text=True, capture_output=True
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("D245_RESULT=PASS", dry.stdout)
        self.assertIn("D245_LIVE_USB_EXECUTION=NOT_PERFORMED", dry.stdout)


if __name__ == "__main__":
    unittest.main()
