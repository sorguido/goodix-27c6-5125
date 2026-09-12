#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "operator_kit/d291-01-multi-verify/run-d291-01.sh"
README = ROOT / "operator_kit/d291-01-multi-verify/README_IT.md"


def section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


class D291OperatorKitContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text()
        cls.readme = README.read_text()

    def test_01_shell_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_02_operator_requires_clean_pushed_development(self):
        operator = section(self.script, "operator_run ()", "case ${1:-}")
        for marker in (
                "branch --show-current", "development", "origin/development",
                "status --porcelain --untracked-files=all"):
            self.assertIn(marker, operator)

    def test_03_candidate_reuses_reviewed_d282_builder(self):
        operator = section(self.script, "operator_run ()", "case ${1:-}")
        self.assertIn('--prepare-candidate "$baseline" "$rpm_dir"', operator)
        self.assertIn("cleanup_candidate", operator)

    def test_04_root_preflight_pins_d285_and_three_tries(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        for marker in (
                "--root-audit D291_PRE", "D285_01_RUNTIME",
                "D285_01_MANIFEST_SHA256", "D285_01_PAM_SHA256",
                "max-tries=3 timeout=45", "TARGET_CARDINALITY_NOT_ONE"):
            self.assertIn(marker, root)

    def test_05_only_driver_and_manifest_are_replaced(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        self.assertIn('"$candidate/libfprint-2.so.2.0.0"', root)
        self.assertIn('"$candidate/d282-01-artifacts.sha256"', root)
        self.assertIn("NON_DRIVER_RUNTIME_DELTA", root)
        for forbidden in (
                'install -m 0644 "$candidate/libgusb',
                'install -m 0644 "$candidate/libopencv',
                'install -m 0644 "$pam', "authselect enable-feature",
                "authselect disable-feature", "fprintd-enroll", "fprintd-delete"):
            self.assertNotIn(forbidden, root)

    def test_06_rollback_is_armed_before_runtime_write(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        self.assertLess(root.index("deployment_started=true"),
                        root.index('systemctl stop fprintd.service'))
        rollback = section(self.script, "rollback ()", "root_run ()")
        for marker in (
                "backup/libfprint-2.so.2.0.0", "backup/artifacts.sha256",
                "backup/d285-01.state", "sha256sum -c artifacts.sha256",
                "FAILED_HUMAN_RECOVERY_REQUIRED"):
            self.assertIn(marker, rollback)

    def test_07_one_real_sudo_consumer_action(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        self.assertEqual(root.count('env -u SUDO_ASKPASS sudo ls'), 1)
        self.assertEqual(root.count('runuser -u "$operator" -- sudo -k'), 2)
        self.assertIn("Tentativo 1", root)
        self.assertIn("Tentativo 2", root)
        self.assertIn("premere Ctrl-C", root)

    def test_08_no_match_then_match_in_two_or_three_epochs(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        for marker in (
                "${#epochs[@]} -ge 2", "${#epochs[@]} -le 3",
                "${outcomes[-1]}", "THIRD_ATTEMPT_WITHOUT_SECOND_NO_MATCH",
                "result=no_match", "result=match",
                "LIVE_OUTCOME_NOT_NO_MATCH_THEN_MATCH"):
            self.assertIn(marker, root)

    def test_09_each_epoch_preserves_factory_guards(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        for field in (
                "attempts", "rejected", "consumed", "tls", "first_image",
                "secure_retry", "post_retry", "reset", "clear_halt",
                "persistent", "outstanding", "drained", "context_closed"):
            self.assertIn(f"{field}=", root)

    def test_10_explicit_reopen_is_not_hidden(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        self.assertIn("reopen=0 explicit_verify_reopen=0", root)
        self.assertIn("reopen=1 explicit_verify_reopen=1", root)
        self.assertIn("sigfm_baseline_pinned=1 sigfm_baseline_reused=0", root)
        self.assertIn("sigfm_baseline_pinned=0 sigfm_baseline_reused=1", root)

    def test_11_relative_launcher_becomes_absolute_before_pkexec(self):
        operator = section(self.script, "operator_run ()", "case ${1:-}")
        self.assertIn('script_path="$script_dir/run-d291-01.sh"', self.script)
        self.assertIn('"$script_path" --root-run', operator)
        self.assertNotIn('"$0" --root-run', operator)

    def test_12_no_authorization_credential_or_unbounded_loop(self):
        self.assertNotIn("grant", self.script.lower())
        self.assertNotIn("token", self.script.lower())
        self.assertNotIn("while true", self.script)
        self.assertNotIn("for attempt", self.script)

    def test_13_readme_declares_human_gate_and_output(self):
        for marker in (
                "Human Gate", "NO_MATCH", "MATCH", "Ctrl-C",
                "RESULT_DIRECTORY", "/tmp/goodix-d291-01-result.*",
                "non deve eseguirlo"):
            self.assertIn(marker, self.readme)


if __name__ == "__main__":
    unittest.main()
