from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis.D244.d244_dependency_gate import verify_dependencies
from analysis.D244.d244_fresh_state import assess_fresh_state
from analysis.D244.d244_operator_dry_run import run, verify_unseal_reseal
from analysis.D244.d244_preflight import (
    D244_MARKER_NAME,
    d244_runtime_paths,
    offline_sandbox_preflight,
)


REPOSITORY = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY / "operator_kit/d244-live-tls-once.sh"


class D244FreshStateControlTests(unittest.TestCase):
    def test_d242_and_d243_live_reports_are_hash_verified_primary_evidence(self):
        report = verify_dependencies()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["report_count"], 2)
        self.assertTrue(
            all(row["status"] == "PRIMARY_LOCAL_EVIDENCE_VERIFIED" for row in report["reports"])
        )

    def test_runtime_namespace_is_d244_without_mutating_sealed_defaults(self):
        paths = d244_runtime_paths()
        self.assertEqual(paths.single_use_marker.name, D244_MARKER_NAME)
        self.assertEqual(paths.report_directory.name, "d244-results")
        self.assertEqual(
            paths.checkpoint_report.name, "d244-live-pre-restore.json"
        )

    def test_preflight_fixture_is_offline_and_historical_markers_are_benign(self):
        with tempfile.TemporaryDirectory(prefix="d244-preflight-") as directory:
            report = offline_sandbox_preflight(Path(directory))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["usb_open_count"], 0)
        self.assertEqual(report["goodix_command_count"], 0)
        self.assertFalse(
            report["historical_markers_case"]["historical_markers_blocking"]
        )

    def test_fresh_boot_requires_changed_boot_id_and_operator_confirmation(self):
        baseline, current = "1" * 32, "2" * 32
        valid = assess_fresh_state(
            baseline_boot_id=baseline,
            current_boot_id=current,
            uptime_seconds=10,
            journal_boot_ids=(baseline, current),
            operator_confirmed=True,
        )
        self.assertTrue(valid["D244_FRESH_BOOT_DOCUMENTED"])
        self.assertTrue(valid["D244_FRESH_STATE_CONTROL_VALID"])
        self.assertFalse(valid["D244_SENSOR_POWER_CYCLE_ELECTRICALLY_PROVEN"])
        unconfirmed = assess_fresh_state(
            baseline_boot_id=baseline,
            current_boot_id=current,
            uptime_seconds=10,
            operator_confirmed=False,
        )
        same_boot = assess_fresh_state(
            baseline_boot_id=baseline,
            current_boot_id=baseline,
            uptime_seconds=10,
            operator_confirmed=True,
        )
        self.assertFalse(unconfirmed["D244_FRESH_STATE_CONTROL_VALID"])
        self.assertFalse(same_boot["D244_FRESH_STATE_CONTROL_VALID"])

    def test_fresh_boot_missing_metadata_cases_are_explicit(self):
        uptime_only = assess_fresh_state(
            baseline_boot_id=None,
            current_boot_id=None,
            uptime_seconds=10,
            operator_confirmed=True,
        )
        unavailable = assess_fresh_state(
            baseline_boot_id=None,
            current_boot_id=None,
            uptime_seconds=None,
            operator_confirmed=True,
        )
        self.assertEqual(uptime_only["D244_FRESH_BOOT_EVIDENCE"], "uptime")
        self.assertFalse(uptime_only["D244_FRESH_BOOT_DOCUMENTED"])
        self.assertEqual(unavailable["D244_FRESH_BOOT_EVIDENCE"], "unavailable")
        self.assertFalse(unavailable["D244_FRESH_STATE_CONTROL_VALID"])

    def test_unseal_patch_changes_namespace_and_reseals_byte_exactly(self):
        report = verify_unseal_reseal()
        self.assertEqual(report["patch_apply"], "PASS_WITHOUT_OFFSET")
        self.assertEqual(report["reseal_rollback"], "PASS_WITHOUT_OFFSET")
        self.assertEqual(report["sealed_sha256"], report["final_sealed_sha256"])

    def test_launcher_requires_explicit_shutdown_power_on_confirmation(self):
        syntax = subprocess.run(
            ["bash", "-n", str(LAUNCHER)], cwd=REPOSITORY, capture_output=True
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr.decode())
        denied = subprocess.run(
            [str(LAUNCHER)], cwd=REPOSITORY, text=True, capture_output=True
        )
        self.assertEqual(denied.returncode, 64)
        self.assertIn("EXPLICIT_D244_FRESH_STATE_AUTHORIZATION_REQUIRED", denied.stderr)

    def test_closure_proves_direction_wire_durability_and_safety(self):
        with tempfile.TemporaryDirectory(prefix="d244-closure-test-") as directory:
            output = Path(directory) / "closure.json"
            report = run(output)
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report, persisted)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["e4_wire"]["D244_E4_LOGICAL_WIRE_MATCH"])
        direction = report["transport"]["timeout_direction_semantics"]
        self.assertEqual(direction["out_timeout_command_count"], 0)
        self.assertEqual(direction["in_timeout_command_count"], 1)
        self.assertEqual(direction["classification"], "IN_CONFIRMED_AFTER_OUT_COMPLETION")
        durability = report["e4_timeout_durability"]
        self.assertEqual(
            durability["durable_checkpoint_before_restore"]["report_publish_count"], 1
        )
        self.assertEqual(durability["final_report_after_restore"]["report_publish_count"], 2)
        self.assertEqual(report["retry_count"], 0)
        self.assertEqual(report["d4_count"], 0)
        self.assertEqual(report["application_data_count"], 0)
        self.assertEqual(report["persistent_write_family_count"], 0)
        self.assertEqual(report["live_usb_execution"], "NOT_PERFORMED")


if __name__ == "__main__":
    unittest.main()
