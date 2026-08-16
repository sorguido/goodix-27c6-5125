from __future__ import annotations

import os
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis.D241.d241_preflight import (
    D241_MARKER_NAME,
    HISTORICAL_MARKER_NAMES,
    marker_namespace_status,
    offline_sandbox_preflight,
    report_directory_status,
)
from analysis.D241.d241_operator_dry_run import verify_unseal_reseal
from src.goodix5125_d235_entrypoint import ProductionRuntimePaths


REPOSITORY = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY / "operator_kit/d241-live-tls-once.sh"
CLOSURE_REPORT = REPOSITORY / "analysis/D241/D241_executable_closure_report.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class D241OperatorPreflightTests(unittest.TestCase):
    def test_t9_result_directory_lifecycle_is_idempotent_and_strict(self):
        with tempfile.TemporaryDirectory(prefix="d241-report-dir-") as directory:
            reports = Path(directory) / "d241-results"
            reports.mkdir(mode=0o700)
            reports.chmod(0o700)
            self.assertTrue(
                report_directory_status(reports, owner_uid=os.getuid())["pass"]
            )
            reports.chmod(0o755)
            self.assertFalse(
                report_directory_status(reports, owner_uid=os.getuid())["pass"]
            )

    def test_t10_historical_markers_are_benign_but_d241_is_single_use(self):
        with tempfile.TemporaryDirectory(prefix="d241-markers-") as directory:
            store = Path(directory)
            for name in HISTORICAL_MARKER_NAMES:
                (store / name).write_text("historical\n", encoding="ascii")
            first = marker_namespace_status(store)
            self.assertTrue(first["d241_marker_absent"])
            self.assertFalse(first["historical_markers_blocking"])
            self.assertEqual(
                set(first["historical_markers_present_benign"]),
                set(HISTORICAL_MARKER_NAMES),
            )
            (store / D241_MARKER_NAME).write_text("consumed\n", encoding="ascii")
            second = marker_namespace_status(store)
            self.assertFalse(second["d241_marker_absent"])

    def test_offline_preflight_fixture_covers_both_marker_cases_and_report_dir(self):
        with tempfile.TemporaryDirectory(prefix="d241-preflight-") as directory:
            report = offline_sandbox_preflight(Path(directory))
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["historical_markers_case"]["d241_marker_absent"])
        self.assertFalse(report["consumed_d241_marker_case"]["d241_marker_absent"])
        self.assertTrue(report["report_directory"]["pass"])
        self.assertEqual(report["libusb_init_count"], 0)

    def test_production_namespace_is_d241_and_not_historical(self):
        paths = ProductionRuntimePaths.system_default()
        self.assertEqual(paths.single_use_marker.name, D241_MARKER_NAME)
        self.assertEqual(paths.report_directory.name, "d241-results")
        self.assertNotIn(paths.single_use_marker.name, HISTORICAL_MARKER_NAMES)

    def test_t11_seal_unseal_hashes_apply_and_reseal_byte_exactly(self):
        result = verify_unseal_reseal()
        self.assertEqual(result["patch_apply"], "PASS")
        self.assertEqual(result["reseal_rollback"], "PASS")
        self.assertEqual(result["sealed_sha256"], result["final_sealed_sha256"])
        self.assertFalse(result["d239_hash_used_as_gate"])
        launcher = LAUNCHER.read_text(encoding="utf-8")
        for label, relative in (
            ("EXPECTED_CORE_SHA256", "src/goodix5125_d232_offline.py"),
            ("EXPECTED_BACKEND_SHA256", "src/goodix5125_d233_backend.py"),
            ("EXPECTED_ENTRYPOINT_SHA256", "src/goodix5125_d235_entrypoint.py"),
            ("EXPECTED_PREFLIGHT_SHA256", "analysis/D241/d241_preflight.py"),
            ("EXPECTED_DRY_RUN_SHA256", "analysis/D241/d241_operator_dry_run.py"),
            ("EXPECTED_UNSEAL_SHA256", "analysis/D241/D241_live_unseal.patch"),
        ):
            self.assertIn(f'readonly {label}="{digest(REPOSITORY / relative)}"', launcher)

    def test_launcher_prepares_report_dir_and_prints_actionable_failure_fields(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('install -d -m 0700 -o root -g root "$D241_REPORT_DIR"', source)
        self.assertIn("D241_PHASE=", source)
        self.assertIn("D241_RESULT=", source)
        self.assertIn("D241_FAILURE_CLASS=", source)

    def test_executable_closure_runs_through_the_real_launcher(self):
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [str(LAUNCHER), "--offline-dry-run"],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D241_RESULT=PASS", result.stdout)
        report = json.loads(CLOSURE_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["classification"], "D241_EXECUTABLE_CLOSURE_GATE_PASS")
        self.assertEqual(report["direct_b0_success"]["first_tls_record_handoff_count"], 1)
        self.assertEqual(
            report["handshake_timeout"]["failure_class"],
            "TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT",
        )
        self.assertEqual(report["live_usb_execution"], "NOT_PERFORMED")


if __name__ == "__main__":
    unittest.main()
