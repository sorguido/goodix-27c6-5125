from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY / "operator_kit/d246-live-d4-once.sh"
OFFLINE_SAFETY = REPOSITORY / "analysis/D246/d246_live_enablement_offline.py"
AUTHORIZATION = "--i-authorize-one-d246-d4-live-attempt"


class D246LiveEnablementTests(unittest.TestCase):
    def test_launcher_syntax_and_exact_authorization(self):
        syntax = subprocess.run(["bash", "-n", str(LAUNCHER)], capture_output=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr.decode())
        for arguments in ((), ("--wrong",), (AUTHORIZATION, "extra")):
            denied = subprocess.run(
                [str(LAUNCHER), *arguments],
                cwd=REPOSITORY,
                text=True,
                capture_output=True,
            )
            self.assertEqual(denied.returncode, 64)
            self.assertIn("EXPLICIT_D246_SINGLE_RUN_AUTHORIZATION_REQUIRED", denied.stderr)

    @unittest.skipIf(os.geteuid() == 0, "non-root invocation requires a non-root test process")
    def test_correct_live_argument_is_blocked_for_non_root(self):
        denied = subprocess.run(
            [str(LAUNCHER), AUTHORIZATION],
            cwd=REPOSITORY,
            env={**os.environ, "D246_APPROVED_LIVE_BASELINE_SHA": "0" * 40},
            text=True,
            capture_output=True,
        )
        self.assertEqual(denied.returncode, 64)
        self.assertIn("ROOT_CONTEXT_REQUIRED", denied.stderr)

    def test_offline_dry_run_from_repository_and_external_cwd(self):
        for cwd in (REPOSITORY, Path(tempfile.gettempdir())):
            result = subprocess.run(
                [str(LAUNCHER), "--offline-dry-run"],
                cwd=cwd,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("D246_RESULT=PASS", result.stdout)
            self.assertIn("D246_GUARDRAIL_MATRIX=PASS", result.stdout)
            self.assertIn("D246_LIVE_USB_EXECUTION=NOT_PERFORMED", result.stdout)

    def test_disconnect_reenumeration_and_second_d4_are_terminal(self):
        result = subprocess.run(
            ["python3", str(OFFLINE_SAFETY)],
            cwd=REPOSITORY,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(REPOSITORY)},
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["unexpected_disconnect"], "TERMINAL_NO_RETRY_NO_REOPEN")
        self.assertEqual(
            report["unexpected_reenumeration"], "TERMINAL_NO_RETRY_NO_RECLAIM"
        )
        self.assertEqual(report["second_d4"], "UNREACHABLE")
        self.assertEqual(report["real_usb_open_count"], 0)


if __name__ == "__main__":
    unittest.main()
