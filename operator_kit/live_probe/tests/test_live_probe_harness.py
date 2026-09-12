#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "operator_kit" / "live_probe"


class LiveProbeHarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="live-probe-test-")
        self.base = Path(self.tmp.name)
        self.capture_root = self.base / "captures"

    def tearDown(self):
        self.tmp.cleanup()

    def run_reference(self, experiment_dir=None, cwd=None):
        command = [
            str(HARNESS / "run.sh"),
            "offline-reference",
            "--offline-test",
            "--capture-root",
            str(self.capture_root),
        ]
        env = os.environ.copy()
        if experiment_dir is not None:
            env["LIVE_PROBE_TEST_EXPERIMENT_DIR"] = str(experiment_dir)
        return subprocess.run(
            command,
            cwd=cwd or self.base,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
            check=False,
            env=env,
        )

    def capture(self):
        captures = list(self.capture_root.glob("*/sanitized"))
        self.assertEqual(len(captures), 1)
        return captures[0]

    def copied_experiment(self):
        target = self.base / "offline-reference"
        shutil.copytree(HARNESS / "experiments" / "offline-reference", target)
        return target

    def test_offline_reference_end_to_end_from_foreign_cwd(self):
        result = self.run_reference(cwd=Path("/tmp"))
        self.assertEqual(result.returncode, 0, result.stdout)
        capture = self.capture()
        self.assertIn("LIVE_PROBE_RESULT=PASS", (capture / "summary.env").read_text())
        self.assertIn(
            "LIVE_PROBE_COMMON_CLASSIFICATION=PASS",
            (capture / "common-classification.env").read_text(),
        )
        self.assertIn(
            "LIVE_PROBE_OFFLINE_REFERENCE_CLASSIFICATION=PASS",
            (capture / "payload-classification.env").read_text(),
        )
        check = subprocess.run(
            ["sha256sum", "-c", "capture.sha256"],
            cwd=capture,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(check.returncode, 0, check.stdout)

    def test_offline_reference_cannot_be_operator_run(self):
        result = subprocess.run(
            [str(HARNESS / "run.sh"), "offline-reference", "--operator-run"],
            cwd=self.base,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EXPERIMENT_NOT_LIVE_CAPABLE", result.stdout)
        self.assertFalse(self.capture_root.exists())

    def test_payload_is_invoked_once_and_receives_exact_budgets(self):
        result = self.run_reference()
        self.assertEqual(result.returncode, 0, result.stdout)
        capture = self.capture()
        summary = (capture / "summary.env").read_text()
        telemetry = (capture / "telemetry.env").read_text()
        self.assertIn("LIVE_PROBE_INVOCATION_COUNT=1", summary)
        self.assertIn("MAX_ACTIONS_ENFORCED=1", telemetry)
        self.assertIn("MAX_CONTACTS_ENFORCED=1", telemetry)
        self.assertIn("MAX_RETRIES_ENFORCED=0", telemetry)

    def test_common_classifier_rejects_action_contact_and_retry_over_budget(self):
        for key, value in (
            ("ACTION_ATTEMPT_COUNT", "2"),
            ("CONTACT_COUNT", "2"),
            ("RETRY_COUNT", "1"),
        ):
            with self.subTest(key=key):
                telemetry = self.base / f"{key}.env"
                telemetry.write_text(
                    "PAYLOAD_OUTCOME=OFFLINE_REFERENCE_PASS\n"
                    f"ACTION_ATTEMPT_COUNT={'2' if key == 'ACTION_ATTEMPT_COUNT' else '0'}\n"
                    f"CONTACT_COUNT={'2' if key == 'CONTACT_COUNT' else '0'}\n"
                    f"RETRY_COUNT={'1' if key == 'RETRY_COUNT' else '0'}\n"
                    "MAX_ACTIONS_ENFORCED=1\nMAX_CONTACTS_ENFORCED=1\nMAX_RETRIES_ENFORCED=0\n"
                    "PERSISTENT_WRITE_FAMILY_COUNT=0\nOUTSTANDING_COUNT=0\n"
                    "DRAINED_COUNT=1\nCONTEXT_CLOSED_COUNT=1\n"
                )
                result = subprocess.run(
                    [
                        str(HARNESS / "classify_common.sh"),
                        str(telemetry),
                        "1",
                        "1",
                        "0",
                        "OFFLINE_REFERENCE_PASS",
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("PAYLOAD_BUDGET_EXCEEDED", result.stdout)

    def test_timeout_runs_cleanup_and_post_audit_without_retry(self):
        experiment = self.copied_experiment()
        payload = experiment / "payload.sh"
        payload.write_text(
            "#!/usr/bin/env bash\n"
            "trap 'exit 124' TERM\n"
            "sleep 20\n"
        )
        payload.chmod(0o755)
        conf = experiment / "experiment.conf"
        conf.write_text(conf.read_text().replace("TIMEOUT_SECONDS=5", "TIMEOUT_SECONDS=1"))
        result = self.run_reference(experiment_dir=experiment)
        self.assertNotEqual(result.returncode, 0)
        capture = self.capture()
        summary = (capture / "summary.env").read_text()
        self.assertIn("LIVE_PROBE_RESULT=FAIL_TIMEOUT", summary)
        self.assertIn("LIVE_PROBE_INVOCATION_COUNT=1", summary)
        self.assertIn("LIVE_PROBE_AUTOMATIC_RETRY_COUNT=0", summary)
        self.assertIn("LIVE_PROBE_OFFLINE_CLEANUP=PASS", (capture / "cleanup.log").read_text())
        self.assertIn("LIVE_PROBE_OFFLINE_POST_AUDIT=PASS", (capture / "post-audit.log").read_text())

    def test_sigint_preserves_cleanup_post_audit_summary_and_hashes(self):
        experiment = self.copied_experiment()
        payload = experiment / "payload.sh"
        payload.write_text(
            "#!/usr/bin/env bash\n"
            "trap 'exit 130' INT TERM\n"
            "echo LIVE_PROBE_TEST_WAITING=true\n"
            "sleep 20\n"
        )
        payload.chmod(0o755)
        command = [
            str(HARNESS / "run.sh"),
            "offline-reference",
            "--offline-test",
            "--capture-root",
            str(self.capture_root),
        ]
        env = os.environ.copy()
        env["LIVE_PROBE_TEST_EXPERIMENT_DIR"] = str(experiment)
        process = subprocess.Popen(
            command,
            cwd=self.base,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
            env=env,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            if list(self.capture_root.glob("*/sanitized/payload.log")):
                break
            time.sleep(0.05)
        os.killpg(process.pid, signal.SIGINT)
        output, _ = process.communicate(timeout=10)
        self.assertNotEqual(process.returncode, 0, output)
        capture = self.capture()
        self.assertIn("LIVE_PROBE_RESULT=INTERRUPTED", (capture / "summary.env").read_text())
        self.assertTrue((capture / "capture.sha256").is_file())
        self.assertIn("LIVE_PROBE_OFFLINE_CLEANUP=PASS", (capture / "cleanup.log").read_text())
        self.assertIn("LIVE_PROBE_OFFLINE_POST_AUDIT=PASS", (capture / "post-audit.log").read_text())

    def test_incomplete_cleanup_telemetry_fails_closed(self):
        experiment = self.copied_experiment()
        payload = experiment / "payload.sh"
        payload.write_text(payload.read_text().replace("DRAINED_COUNT=1", "DRAINED_COUNT=0"))
        result = self.run_reference(experiment_dir=experiment)
        self.assertNotEqual(result.returncode, 0)
        capture = self.capture()
        self.assertIn("FAIL_COMMON_CLASSIFICATION", (capture / "summary.env").read_text())
        self.assertIn("CLEANUP_TELEMETRY_INCOMPLETE", (capture / "common-classification.env").read_text())


if __name__ == "__main__":
    unittest.main()
