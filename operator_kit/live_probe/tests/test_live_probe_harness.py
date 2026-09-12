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

    def run_reference(self, experiment_dir=None, cwd=None, extra_env=None):
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
        if extra_env is not None:
            env.update(extra_env)
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

    def journal_enabled_experiment(self, pre_exit=0):
        experiment = self.copied_experiment()
        audit = experiment / "audit.sh"
        audit.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "[[ $# -eq 2 && $1 == --phase ]]\n"
            f"if [[ $2 == pre ]]; then echo SYNTHETIC_PRE_AUDIT=true; exit {pre_exit}; fi\n"
            "echo SYNTHETIC_POST_AUDIT=PASS\n"
        )
        audit.chmod(0o755)
        payload = experiment / "payload.sh"
        payload.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "touch \"$LIVE_PROBE_CAPTURE_DIR/payload-started\"\n"
            "exit 99\n"
        )
        payload.chmod(0o755)
        sanitizer = experiment / "sanitize.sh"
        sanitizer.write_text("#!/usr/bin/env bash\nset -euo pipefail\nsed 's/SECRET/<REDACTED>/g'\n")
        sanitizer.chmod(0o755)
        conf = experiment / "experiment.conf"
        conf.write_text(
            conf.read_text()
            + "\nCOLLECT_JOURNAL=true\nCOLLECT_JOURNAL_OFFLINE=true\nCLASSIFIER=\n"
            "OUTPUT_IS_SANITIZED=false\nSANITIZER=sanitize.sh\n"
        )
        return experiment

    def fake_journalctl(self, body):
        fake_bin = self.base / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        script = fake_bin / "journalctl"
        script.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body)
        script.chmod(0o755)
        return fake_bin

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

    def test_common_classifier_accepts_multiple_expected_outcomes_and_contexts(self):
        telemetry = self.base / "multi.env"
        telemetry.write_text(
            "PAYLOAD_OUTCOME=MATCH\nACTION_ATTEMPT_COUNT=2\nCONTACT_COUNT=2\nRETRY_COUNT=0\n"
            "MAX_ACTIONS_ENFORCED=3\nMAX_CONTACTS_ENFORCED=3\nMAX_RETRIES_ENFORCED=0\n"
            "PERSISTENT_WRITE_FAMILY_COUNT=0\nOUTSTANDING_COUNT=0\n"
            "DRAINED_COUNT=2\nCONTEXT_CLOSED_COUNT=2\n"
        )
        result = subprocess.run(
            [str(HARNESS / "classify_common.sh"), str(telemetry), "3", "3", "0", "MATCH NO_MATCH"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("LIVE_PROBE_COMMON_CLASSIFICATION=PASS", result.stdout)

    def test_git_gate_preserves_path_with_spaces_as_one_pathspec(self):
        repo = self.base / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "development"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Live Probe Test"], cwd=repo, check=True)
        (repo / "operator_kit/live_probe").mkdir(parents=True)
        (repo / "operator_kit/live_probe/tracked").write_text("ok\n")
        (repo / "path with spaces").mkdir()
        (repo / "path with spaces/tracked").write_text("ok\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "update-ref", "refs/remotes/origin/development", "HEAD"], cwd=repo, check=True)
        (repo / "path with spaces/untracked").write_text("dirty\n")
        script = (
            f"source {HARNESS / 'safety.sh'}; "
            f"LP_GIT_ROOT={repo}; LIVE_CRITICAL_PATHS=('path with spaces'); lp_git_gate"
        )
        result = subprocess.run(
            ["bash", "-c", script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GIT_LIVE_CRITICAL_SET_DIRTY", result.stdout)

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
        sanitizer = experiment / "sanitize.sh"
        sanitizer.write_text("#!/usr/bin/env bash\nsed 's/SECRET/<REDACTED>/g'\n")
        sanitizer.chmod(0o755)
        conf = experiment / "experiment.conf"
        conf.write_text(
            conf.read_text().replace("OUTPUT_IS_SANITIZED=true", "OUTPUT_IS_SANITIZED=false\nSANITIZER=sanitize.sh")
        )
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
        summary = (capture / "summary.env").read_text()
        self.assertIn("LIVE_PROBE_RESULT=INTERRUPTED", summary)
        self.assertIn("LIVE_PROBE_PRIMARY_FAILURE=SIGNAL", summary)
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

    def test_pre_audit_failure_preserves_primary_cause_and_skips_payload_and_journal(self):
        experiment = self.journal_enabled_experiment(pre_exit=23)
        calls = self.base / "journal-calls.log"
        fake_bin = self.fake_journalctl('echo called >>"$JOURNAL_CALL_LOG"\nexit 91\n')
        result = self.run_reference(
            experiment_dir=experiment,
            extra_env={
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "JOURNAL_CALL_LOG": str(calls),
            },
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        capture = self.capture()
        summary = (capture / "summary.env").read_text()
        self.assertIn("LIVE_PROBE_RESULT=FAIL_PRE_AUDIT", summary)
        self.assertIn("LIVE_PROBE_PRIMARY_FAILURE=PRE_AUDIT", summary)
        self.assertIn("LIVE_PROBE_PRE_AUDIT_RETURN_CODE=23", summary)
        self.assertIn("LIVE_PROBE_PAYLOAD_STARTED=false", summary)
        self.assertIn("LIVE_PROBE_JOURNAL_COLLECTION=NOT_APPLICABLE_NO_CURSOR", summary)
        self.assertIn("SYNTHETIC_PRE_AUDIT=true", (capture / "pre-audit.log").read_text())
        self.assertIn(
            "JOURNAL_COLLECTION=NOT_APPLICABLE_NO_CURSOR",
            (capture / "journal-status.env").read_text(),
        )
        self.assertFalse((capture / "payload-started").exists())
        self.assertFalse(calls.exists())
        self.assertNotIn("variabile non assegnata", result.stdout)
        hash_check = subprocess.run(
            ["sha256sum", "-c", "capture.sha256"],
            cwd=capture,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(hash_check.returncode, 0, hash_check.stdout)

    def test_cursor_failure_is_distinct_and_never_collects_with_invalid_cursor(self):
        experiment = self.journal_enabled_experiment(pre_exit=0)
        calls = self.base / "journal-calls.log"
        fake_bin = self.fake_journalctl(
            'echo "$*" >>"$JOURNAL_CALL_LOG"\n'
            'if [[ " $* " == *" --show-cursor "* ]]; then exit 77; fi\n'
            'exit 92\n'
        )
        result = self.run_reference(
            experiment_dir=experiment,
            extra_env={
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "JOURNAL_CALL_LOG": str(calls),
            },
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        capture = self.capture()
        summary = (capture / "summary.env").read_text()
        self.assertIn("LIVE_PROBE_RESULT=FAIL_JOURNAL_CURSOR", summary)
        self.assertIn("LIVE_PROBE_PRIMARY_FAILURE=JOURNAL_CURSOR_ACQUISITION", summary)
        self.assertIn("LIVE_PROBE_JOURNAL_CURSOR_RETURN_CODE=1", summary)
        self.assertIn("LIVE_PROBE_PAYLOAD_STARTED=false", summary)
        self.assertIn("LIVE_PROBE_JOURNAL_COLLECTION=NOT_APPLICABLE_NO_CURSOR", summary)
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assertIn("--show-cursor", calls.read_text())
        self.assertFalse((capture / "payload-started").exists())

    def test_unset_or_empty_cursor_under_set_u_is_a_classified_skip(self):
        capture = self.base / "direct-capture"
        capture.mkdir()
        script = (
            "set -u; "
            f"source '{HARNESS / 'capture.sh'}'; "
            f"LP_CAPTURE_DIR='{capture}'; "
            "LIVE_PROBE_MODE=offline-test; COLLECT_JOURNAL=true; "
            "COLLECT_JOURNAL_OFFLINE=true; lp_collect_journal; "
            "printf 'STATUS=%s\\n' \"$LP_JOURNAL_COLLECTION\""
        )
        result = subprocess.run(
            ["bash", "-c", script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("STATUS=NOT_APPLICABLE_NO_CURSOR", result.stdout)
        self.assertIn(
            "JOURNAL_COLLECTION=NOT_APPLICABLE_NO_CURSOR",
            (capture / "journal-status.env").read_text(),
        )

    def test_valid_cursor_happy_path_collects_once_and_remains_green(self):
        experiment = self.copied_experiment()
        conf = experiment / "experiment.conf"
        conf.write_text(
            conf.read_text() + "\nCOLLECT_JOURNAL=true\nCOLLECT_JOURNAL_OFFLINE=true\n"
        )
        calls = self.base / "journal-calls.log"
        fake_bin = self.fake_journalctl(
            'echo "$*" >>"$JOURNAL_CALL_LOG"\n'
            'if [[ " $* " == *" --show-cursor "* ]]; then echo "-- cursor: s=synthetic"; fi\n'
        )
        result = self.run_reference(
            experiment_dir=experiment,
            extra_env={
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "JOURNAL_CALL_LOG": str(calls),
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        capture = self.capture()
        summary = (capture / "summary.env").read_text()
        self.assertIn("LIVE_PROBE_RESULT=PASS", summary)
        self.assertIn("LIVE_PROBE_JOURNAL_COLLECTION=COLLECTED", summary)
        self.assertIn("JOURNAL_COLLECTION=COLLECTED", (capture / "journal-status.env").read_text())
        self.assertEqual(len(calls.read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
