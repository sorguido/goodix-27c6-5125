from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis.D241.d241_preflight import report_directory_status
from analysis.D242.d242_dependency_gate import verify_d241_dependencies
from analysis.D242.d242_operator_dry_run import run, verify_unseal_reseal
from analysis.D242.d242_preflight import (
    D242_MARKER_NAME,
    HISTORICAL_MARKER_NAMES,
    marker_namespace_status,
    offline_sandbox_preflight,
)
from src.goodix5125_d235_entrypoint import ProductionRuntimePaths


REPOSITORY = Path(__file__).resolve().parents[1]
HISTORICAL_REPOSITORY = Path("/home/guido/Repository/goodix-27c6-5125")
LAUNCHER = REPOSITORY / "operator_kit/d242-live-tls-once.sh"
OBSERVABILITY = REPOSITORY / "analysis/D242/d242_preflight_observability.py"


class D242OperatorKitTests(unittest.TestCase):
    def test_historical_renderer_preserves_specific_redacted_preflight_failure(self):
        backend = REPOSITORY / "src/goodix5125_d233_backend.py"
        entrypoint = REPOSITORY / "src/goodix5125_d235_entrypoint.py"
        before = (backend.read_bytes(), entrypoint.read_bytes())
        with tempfile.TemporaryDirectory(prefix="d242-observability-") as directory:
            root = Path(directory)
            marker = root / "d242-operator-invocation.marker"
            report_path = root / "synthetic-preflight-failure.json"
            report_path.write_text(
                json.dumps(
                    {
                        "schema": "d242-preflight-report-v1",
                        "status": "fail",
                        "phase": "PREFLIGHT",
                        "failure_class": "operator_identity",
                        "failures": ["operator_identity", "durable_report_path"],
                        "marker_namespace_status": {
                            "namespace": str(marker),
                            "d242_marker_absent": True,
                        },
                        "usb_open_count": 0,
                        "contains_secret": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            rendered = subprocess.run(
                [
                    "python3",
                    str(OBSERVABILITY),
                    "--report",
                    str(report_path),
                ],
                cwd=REPOSITORY,
                text=True,
                capture_output=True,
            )
            self.assertEqual(rendered.returncode, 0)
            self.assertIn("D242_PHASE=PREFLIGHT", rendered.stdout)
            self.assertIn("D242_FAILURE_CLASS=OPERATOR_IDENTITY", rendered.stdout)
            self.assertIn(
                "D242_PREFLIGHT_FAILURES=operator_identity,durable_report_path",
                rendered.stdout,
            )
            self.assertIn(f"D242_MARKER_PATH={marker}", rendered.stdout)
            self.assertIn("D242_USB_OPEN_COUNT=0", rendered.stdout)
            self.assertIn("D242_GOODIX_COMMAND_COUNT=0", rendered.stdout)
            self.assertIn("D242_REAL_SECRET_READ_COUNT=0", rendered.stdout)
            self.assertIn("D242_FPRINTD_MUTATION_COUNT=0", rendered.stdout)
            self.assertIn("D242_LIVE_MARKER_CREATE_COUNT=0", rendered.stdout)
            self.assertIn("D242_LIVE_USB_EXECUTION=NOT_STARTED", rendered.stdout)
            self.assertNotIn("D242_FAILURE_CLASS=PREFLIGHT_FAILED", rendered.stdout)
            self.assertFalse(marker.exists())
        self.assertEqual(before, (backend.read_bytes(), entrypoint.read_bytes()))

    def test_historical_renderer_classifies_missing_and_invalid_reports(self):
        with tempfile.TemporaryDirectory(prefix="d242-observability-errors-") as directory:
            root = Path(directory)
            missing = subprocess.run(
                ["python3", str(OBSERVABILITY), "--report", str(root / "missing.json")],
                cwd=REPOSITORY,
                text=True,
                capture_output=True,
            )
            self.assertEqual(missing.returncode, 0)
            self.assertIn("D242_FAILURE_CLASS=PREFLIGHT_REPORT_MISSING", missing.stdout)
            invalid_path = root / "invalid.json"
            invalid_path.write_text("not-json\n", encoding="ascii")
            invalid = subprocess.run(
                ["python3", str(OBSERVABILITY), "--report", str(invalid_path)],
                cwd=REPOSITORY,
                text=True,
                capture_output=True,
            )
            self.assertEqual(invalid.returncode, 0)
            self.assertIn("D242_FAILURE_CLASS=PREFLIGHT_REPORT_INVALID", invalid.stdout)

    def test_historical_d241_dependencies_are_byte_exact_and_fully_pinned(self):
        result = verify_d241_dependencies()
        self.assertEqual(result["behavior_relevant_dependency_count"], 2)
        self.assertEqual(result["pinned_dependency_count"], 2)
        self.assertEqual(result["unpinned_closure_dependency_count"], 0)
        self.assertEqual(
            {item["module_path"]: item["actual_sha256"] for item in result["modules"]},
            {
                "analysis/D241/d241_operator_dry_run.py": "0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f",
                "analysis/D241/d241_preflight.py": "6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7",
            },
        )

    def test_d242_marker_is_historical_after_d243_namespace_advance(self):
        paths = ProductionRuntimePaths.system_default()
        self.assertEqual(paths.single_use_marker.name, "d243-operator-invocation.marker")
        self.assertEqual(paths.report_directory.name, "d243-results")
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
        if REPOSITORY != HISTORICAL_REPOSITORY:
            self.assertEqual(denied.returncode, 65)
            self.assertIn("WRONG_REPOSITORY_CWD", denied.stderr)
            source = LAUNCHER.read_text(encoding="utf-8")
            self.assertIn("EXPLICIT_D242_AUTHORIZATION_ARGUMENT_REQUIRED", source)
            return
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
