from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis.D241.d241_preflight import report_directory_status
from analysis.D242.d242_operator_dry_run import run, verify_unseal_reseal
from analysis.D242.d242_preflight import (
    D242_MARKER_NAME,
    HISTORICAL_MARKER_NAMES,
    marker_namespace_status,
    offline_sandbox_preflight,
)
from src.goodix5125_d235_entrypoint import ProductionRuntimePaths


REPOSITORY = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY / "operator_kit/d242-live-tls-once.sh"


class D242OperatorKitTests(unittest.TestCase):
    def test_marker_namespace_is_new_and_historical_markers_are_benign(self):
        paths = ProductionRuntimePaths.system_default()
        self.assertEqual(paths.single_use_marker.name, D242_MARKER_NAME)
        self.assertEqual(paths.report_directory.name, "d242-results")
        with tempfile.TemporaryDirectory(prefix="d242-markers-") as directory:
            store = Path(directory)
            for name in HISTORICAL_MARKER_NAMES:
                (store / name).write_text("historical\n", encoding="ascii")
            first = marker_namespace_status(store)
            self.assertTrue(first["d242_marker_absent"])
            self.assertFalse(first["historical_markers_blocking"])
            (store / D242_MARKER_NAME).write_text("consumed\n", encoding="ascii")
            self.assertFalse(marker_namespace_status(store)["d242_marker_absent"])

    def test_result_directory_lifecycle_is_strict_and_preflight_is_offline(self):
        with tempfile.TemporaryDirectory(prefix="d242-preflight-") as directory:
            root = Path(directory)
            report = offline_sandbox_preflight(root)
            reports = root / "var/lib/goodix-5125-poc/d242-results"
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["report_directory"]["pass"])
            self.assertEqual(report["usb_open_count"], 0)
            reports.chmod(0o755)
            self.assertFalse(
                report_directory_status(reports, owner_uid=os.getuid())["pass"]
            )

    def test_seal_unseal_round_trip_is_coherent(self):
        result = verify_unseal_reseal()
        self.assertEqual(result["patch_apply"], "PASS")
        self.assertEqual(result["reseal_rollback"], "PASS")
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
        self.assertIn("EXPLICIT_D242_AUTHORIZATION_ARGUMENT_REQUIRED", denied.stderr)

    def test_executable_closure_end_to_end_is_redacted_and_has_no_live_io(self):
        with tempfile.TemporaryDirectory(prefix="d242-test-closure-") as directory:
            output = Path(directory) / "closure.json"
            report = run(output)
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report, persisted)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["live_usb_execution"], "NOT_PERFORMED")
        self.assertEqual(report["real_secret_read_count"], 0)
        self.assertEqual(report["d4_count"], 0)
        self.assertEqual(report["application_data_count"], 0)
        serialized = json.dumps(report, sort_keys=True)
        for forbidden in ("raw_tls", "raw_b0", "raw_usb", "psk_value", "session_id_value"):
            self.assertNotIn(forbidden, serialized.lower())


if __name__ == "__main__":
    unittest.main()
