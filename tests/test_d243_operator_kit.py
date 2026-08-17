from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis.D243.d243_dependency_gate import verify_dependencies
from analysis.D243.d243_operator_dry_run import run, verify_unseal_reseal
from analysis.D243.d243_preflight import (
    D243_MARKER_NAME,
    HISTORICAL_MARKER_NAMES,
    marker_namespace_status,
    offline_sandbox_preflight,
)
from src.goodix5125_d235_entrypoint import ProductionRuntimePaths


REPOSITORY = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY / "operator_kit/d243-live-tls-once.sh"


class D243OperatorKitTests(unittest.TestCase):
    def test_d242_live_report_is_primary_local_hash_verified_evidence(self):
        result = verify_dependencies()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["unpinned_dependency_count"], 0)
        self.assertEqual(
            result["d242_live_report_status"],
            "PRIMARY_LOCAL_EVIDENCE_VERIFIED",
        )

    def test_marker_namespace_and_result_directory_are_d243(self):
        paths = ProductionRuntimePaths.system_default()
        self.assertEqual(paths.single_use_marker.name, D243_MARKER_NAME)
        self.assertEqual(paths.report_directory.name, "d243-results")
        with tempfile.TemporaryDirectory(prefix="d243-markers-") as directory:
            store = Path(directory)
            for name in HISTORICAL_MARKER_NAMES:
                (store / name).write_text("historical\n", encoding="ascii")
            first = marker_namespace_status(store)
            self.assertTrue(first["d243_marker_absent"])
            self.assertFalse(first["historical_markers_blocking"])
            (store / D243_MARKER_NAME).write_text("consumed\n", encoding="ascii")
            self.assertFalse(marker_namespace_status(store)["d243_marker_absent"])

    def test_preflight_fixture_is_offline_and_report_directory_is_strict(self):
        with tempfile.TemporaryDirectory(prefix="d243-preflight-") as directory:
            report = offline_sandbox_preflight(Path(directory))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["usb_open_count"], 0)
        self.assertEqual(report["goodix_command_count"], 0)

    def test_unseal_patch_applies_without_offset_and_reseals_byte_exactly(self):
        result = verify_unseal_reseal()
        self.assertEqual(result["patch_apply"], "PASS_WITHOUT_OFFSET")
        self.assertEqual(result["reseal_rollback"], "PASS_WITHOUT_OFFSET")
        self.assertEqual(result["sealed_sha256"], result["final_sealed_sha256"])

    def test_launcher_is_valid_and_requires_explicit_authorization(self):
        syntax = subprocess.run(
            ["bash", "-n", str(LAUNCHER)], cwd=REPOSITORY, capture_output=True
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr.decode())
        denied = subprocess.run(
            [str(LAUNCHER)], cwd=REPOSITORY, text=True, capture_output=True
        )
        self.assertEqual(denied.returncode, 64)
        self.assertIn("EXPLICIT_D243_AUTHORIZATION_ARGUMENT_REQUIRED", denied.stderr)

    def test_launcher_renders_specific_redacted_preflight_failure(self):
        with tempfile.TemporaryDirectory(prefix="d243-observability-") as directory:
            root = Path(directory)
            marker = root / D243_MARKER_NAME
            report_path = root / "synthetic-preflight-failure.json"
            report_path.write_text(
                json.dumps(
                    {
                        "schema": "d243-preflight-report-v1",
                        "status": "fail",
                        "failure_class": "operator_identity",
                        "failures": ["operator_identity", "durable_report_path"],
                        "marker_namespace_status": {"namespace": str(marker)},
                        "usb_open_count": 0,
                        "goodix_command_count": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(LAUNCHER),
                    "--offline-render-preflight-failure",
                    str(report_path),
                ],
                cwd=REPOSITORY,
                text=True,
                capture_output=True,
            )
        self.assertEqual(result.returncode, 69)
        self.assertIn("D243_FAILURE_CLASS=OPERATOR_IDENTITY", result.stderr)
        self.assertIn(
            "D243_PREFLIGHT_FAILURES=operator_identity,durable_report_path",
            result.stderr,
        )
        self.assertNotIn("D243_FAILURE_CLASS=PREFLIGHT_FAILED", result.stderr)

    def test_e4_timeout_report_is_durable_before_restore_and_final_after_restore(self):
        with tempfile.TemporaryDirectory(prefix="d243-test-closure-") as directory:
            output = Path(directory) / "closure.json"
            report = run(output)
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report, persisted)
        self.assertEqual(report["status"], "PASS")
        durability = report["e4_timeout_durability"]
        checkpoint = durability["durable_checkpoint_before_restore"]
        final = durability["final_report_after_restore"]
        self.assertTrue(durability["checkpoint_precedes_restore"])
        self.assertEqual(checkpoint["attempted_phase"], "E4")
        self.assertEqual(checkpoint["abort_class"], "timeout")
        self.assertEqual(checkpoint["command_count"], 1)
        self.assertEqual(checkpoint["usb_open_count"], 1)
        self.assertEqual(checkpoint["cleanup_count"], 1)
        self.assertTrue(checkpoint["secret_zeroized"])
        self.assertEqual(checkpoint["report_publish_count"], 1)
        self.assertEqual(final["report_publish_count"], 2)
        self.assertEqual(final["signal_restore_status"], "restored")
        self.assertEqual(durability["usb_release_count"], 1)
        self.assertEqual(durability["usb_close_count"], 1)
        self.assertEqual(durability["usb_exit_count"], 1)
        self.assertEqual(report["live_usb_execution"], "NOT_PERFORMED")
        self.assertEqual(report["real_secret_read_count"], 0)
        self.assertEqual(report["retry_count"], 0)
        self.assertEqual(report["d4_count"], 0)
        self.assertEqual(report["application_data_count"], 0)
        serialized = json.dumps(report, sort_keys=True).lower()
        for forbidden in ("raw_tls", "raw_b0", "raw_usb", "psk_value"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
