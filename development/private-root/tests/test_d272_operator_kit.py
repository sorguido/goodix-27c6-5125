# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "operator_kit/d272-sigfm-validation.sh"


class D272OperatorKitTests(unittest.TestCase):
    def run_kit(self, cwd, flag):
        return subprocess.run(
            (str(LAUNCHER), flag), cwd=cwd, check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def test_dry_run_root_and_external_cwd(self):
        for cwd in (REPO, Path("/tmp")):
            completed = self.run_kit(cwd, "--dry-run")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            self.assertEqual(output["D272_OPERATOR_DRY_RUN"], "PASS")
            self.assertFalse(output["BASELINE_APPROVED"])
            self.assertFalse(output["LIVE_AUTHORIZED"])
            self.assertFalse(output["READY_FOR_LIVE"])
            self.assertEqual(output["LIVE_EXECUTION"], "NOT_PERFORMED")
            for key in (
                "REAL_USB_OPEN_COUNT",
                "REAL_SECRET_MATERIALIZATION_COUNT",
                "REAL_FPRINTD_MUTATION_COUNT",
                "REAL_BIOMETRIC_CAPTURE_COUNT",
                "PERSISTENT_DEVICE_WRITE_COUNT",
            ):
                self.assertEqual(output[key], 0)

    def test_future_live_is_hard_disabled(self):
        completed = self.run_kit(REPO, "--future-live")
        self.assertEqual(completed.returncode, 1)
        output = json.loads(completed.stdout)
        self.assertIn("BLOCCATO", output["MESSAGGIO_OPERATORE"])
        self.assertFalse(output["LIVE_AUTHORIZED"])

    def test_unknown_flag_and_import_are_inert(self):
        completed = self.run_kit(REPO, "--non-valido")
        self.assertEqual(completed.returncode, 2)
        subprocess.run(("sh", "-n", str(LAUNCHER)), check=True)
        imported = subprocess.run(
            ("python3", "-c", "import tools.d272_sigfm_validation; print('OK')"),
            cwd=REPO, check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(imported.stdout.strip(), "OK")
        self.assertEqual(imported.stderr, "")


if __name__ == "__main__":
    unittest.main()
