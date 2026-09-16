from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
HISTORICAL_REPOSITORY = Path("/home/guido/Repository/goodix-27c6-5125")
PREFLIGHT = REPOSITORY / "analysis/D236/d236_preflight.py"
DRY_RUN = REPOSITORY / "analysis/D239/d239_operator_dry_run.py"
DRY_RUN_REPORT = REPOSITORY / "analysis/D239/D239_operator_dry_run_report.json"
OPERATOR_KIT = REPOSITORY / "operator_kit/d239-live-pre-d1-tls-once.sh"
BACKEND = REPOSITORY / "src/goodix5125_d233_backend.py"
ENTRYPOINT = REPOSITORY / "src/goodix5125_d235_entrypoint.py"
LIVE_STDOUT = REPOSITORY / "analysis/D239/D239_operator_live_stdout.json"
D239_SEALED_SOURCE_HASHES = (
    "7727128ee27337b70ba48eac31b8640c888b76560387363e4eff0c167d993f5b",
    "38e857a14bd416808b9ae2df7c4101809879e4732b6e001ce29d11bd731dd555",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


class D239OperatorKitExecutabilityTests(unittest.TestCase):
    def test_direct_script_launch_reproduces_missing_repository_import_root(self):
        result = subprocess.run(
            [sys.executable, str(PREFLIGHT)],
            cwd=REPOSITORY,
            env=clean_environment(),
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ModuleNotFoundError: No module named 'src'", result.stderr)

    def test_same_explicit_import_context_used_by_operator_kit_passes(self):
        environment = clean_environment()
        environment["PYTHONPATH"] = str(REPOSITORY)
        result = subprocess.run(
            [sys.executable, str(PREFLIGHT), "--d239-offline-import-probe"],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["repository"], str(REPOSITORY))
        self.assertEqual(report["libusb_init_count"], 0)
        self.assertEqual(report["usb_open_count"], 0)
        self.assertEqual(report["goodix_command_count"], 0)

    def test_real_operator_kit_dry_run_reaches_fence_and_preserves_seals(self):
        source_hashes = (digest(BACKEND), digest(ENTRYPOINT))
        live_stdout_before = os.path.lexists(LIVE_STDOUT)
        result = subprocess.run(
            [str(OPERATOR_KIT), "--offline-dry-run-pre-usb"],
            cwd=REPOSITORY,
            env=clean_environment(),
            text=True,
            capture_output=True,
        )
        if REPOSITORY != HISTORICAL_REPOSITORY:
            self.assertEqual(result.returncode, 65)
            self.assertIn(f"launch from {HISTORICAL_REPOSITORY}", result.stderr)
            self.assertEqual((digest(BACKEND), digest(ENTRYPOINT)), source_hashes)
            self.assertEqual(os.path.lexists(LIVE_STDOUT), live_stdout_before)
            return
        if source_hashes != D239_SEALED_SOURCE_HASHES:
            # D241 intentionally supersedes the reviewed D239 source baseline.
            # The historical kit must now reject it rather than silently using
            # stale D239 hashes or an obsolete unseal patch.
            self.assertEqual(result.returncode, 68)
            self.assertIn("sealed backend source differs", result.stderr)
            self.assertEqual((digest(BACKEND), digest(ENTRYPOINT)), source_hashes)
            self.assertEqual(os.path.lexists(LIVE_STDOUT), live_stdout_before)
            return
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OPERATOR_KIT_DRY_RUN_PRE_USB=PASS", result.stdout)
        report = json.loads(DRY_RUN_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["classification"], "REAL_OFFLINE_OPERATOR_DRY_RUN")
        self.assertEqual(report["pre_usb_fence_count"], 1)
        self.assertEqual(report["libusb_init_count"], 0)
        self.assertEqual(report["usb_open_count"], 0)
        self.assertEqual(report["goodix_command_count"], 0)
        self.assertEqual(report["real_secret_read_count"], 0)
        self.assertEqual(report["live_marker_create_count"], 0)
        self.assertEqual(report["source_unseal_count"], 0)
        self.assertFalse(report["secret_present_in_report"])
        self.assertEqual(report["live_usb_execution"], "NOT_PERFORMED")
        self.assertEqual((digest(BACKEND), digest(ENTRYPOINT)), source_hashes)
        self.assertEqual(os.path.lexists(LIVE_STDOUT), live_stdout_before)

    def test_gate_validator_rejects_missing_and_stale_reports(self):
        environment = clean_environment()
        environment["PYTHONPATH"] = str(REPOSITORY)
        with tempfile.TemporaryDirectory(prefix="d239-gate-test-") as directory:
            missing = Path(directory) / "missing.json"
            result = subprocess.run(
                [sys.executable, str(DRY_RUN), "--verify-report", str(missing)],
                cwd=REPOSITORY,
                env=environment,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

            stale = Path(directory) / "stale.json"
            report = json.loads(DRY_RUN_REPORT.read_text(encoding="utf-8"))
            report["status"] = "FAIL"
            stale.write_text(json.dumps(report), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(DRY_RUN), "--verify-report", str(stale)],
                cwd=REPOSITORY,
                env=environment,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_live_branch_requires_current_dry_run_gate_before_root_gate(self):
        source = OPERATOR_KIT.read_text(encoding="utf-8")
        live_branch = source.index('[[ "${1-}" == "$AUTHORIZATION_ARGUMENT"')
        dry_gate = source.index("verify_dry_run_gate", live_branch)
        root_gate = source.index('[[ "$EUID" -eq 0 ]]', live_branch)
        live_entrypoint = source.index("python3 -m src.goodix5125_d235_entrypoint")
        self.assertLess(dry_gate, root_gate)
        self.assertLess(root_gate, live_entrypoint)
        self.assertIn(
            'PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}"',
            source,
        )

    def test_wrong_cwd_stops_before_python_or_live_path(self):
        with tempfile.TemporaryDirectory(prefix="d239-wrong-cwd-") as directory:
            result = subprocess.run(
                [str(OPERATOR_KIT), "--offline-dry-run-pre-usb"],
                cwd=directory,
                env=clean_environment(),
                text=True,
                capture_output=True,
            )
        self.assertEqual(result.returncode, 65)
        self.assertIn("launch from", result.stderr)


if __name__ == "__main__":
    unittest.main()
