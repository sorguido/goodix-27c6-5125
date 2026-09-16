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
HISTORICAL_REPOSITORY = Path("/home/guido/Repository/goodix-27c6-5125")
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

    def test_production_namespace_is_now_d243_and_d241_is_historical(self):
        paths = ProductionRuntimePaths.system_default()
        self.assertEqual(paths.single_use_marker.name, "d243-operator-invocation.marker")
        self.assertEqual(paths.report_directory.name, "d243-results")
        self.assertNotEqual(paths.single_use_marker.name, D241_MARKER_NAME)

    def test_t11_d241_seal_is_stale_after_reviewed_d242_source_change(self):
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertNotIn(
            f'readonly EXPECTED_BACKEND_SHA256="{digest(REPOSITORY / "src/goodix5125_d233_backend.py")}"',
            launcher,
        )

    def test_launcher_prepares_report_dir_and_prints_actionable_failure_fields(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('install -d -m 0700 -o root -g root "$D241_REPORT_DIR"', source)
        self.assertIn("D241_PHASE=", source)
        self.assertIn("D241_RESULT=", source)
        self.assertIn("D241_FAILURE_CLASS=", source)

    def test_historical_d241_launcher_rejects_d242_source_baseline(self):
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
        if REPOSITORY != HISTORICAL_REPOSITORY:
            self.assertEqual(result.returncode, 65, result.stderr)
            self.assertIn("WRONG_REPOSITORY_CWD", result.stderr)
            return
        self.assertEqual(result.returncode, 68, result.stderr)
        self.assertIn("D241_SEALED_BACKEND_HASH_MISMATCH", result.stderr)


if __name__ == "__main__":
    unittest.main()
