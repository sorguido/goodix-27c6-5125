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

    def test_01_shell_syntax_and_executable(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        self.assertTrue(SCRIPT.stat().st_mode & 0o100)

    def test_02_operator_requires_clean_pushed_development(self):
        operator = section(self.script, "operator_run ()", "case ${1:-}")
        for marker in ("branch --show-current", "development",
                       "origin/development",
                       "status --porcelain --untracked-files=all"):
            self.assertIn(marker, operator)

    def test_03_candidate_reuses_reviewed_d282_builder(self):
        operator = section(self.script, "operator_run ()", "case ${1:-}")
        self.assertIn('--prepare-candidate "$baseline" "$rpm_dir"', operator)
        self.assertIn("cleanup_candidate", operator)

    def test_04_root_preflight_pins_d285_and_three_tries(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        for marker in ("--root-audit D291_PRE", "D285_01_RUNTIME",
                       "D285_01_MANIFEST_SHA256", "D285_01_PAM_SHA256",
                       "max-tries=3 timeout=45", "TARGET_CARDINALITY_NOT_ONE",
                       "D285_01_TEMPLATE_RELATIVE_PATH",
                       "D285_01_TEMPLATE_SHA256"):
            self.assertIn(marker, root)

    def test_05_only_driver_runtime_delta_and_explicit_host_reenroll(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        self.assertIn('"$candidate/libfprint-2.so.2.0.0"', root)
        self.assertIn('"$candidate/d282-01-artifacts.sha256"', root)
        self.assertIn("NON_DRIVER_RUNTIME_DELTA", root)
        self.assertEqual(root.count('fprintd-delete "$operator"'), 1)
        self.assertEqual(root.count("fprintd-enroll -f right-index-finger"), 1)
        for forbidden in ('install -m 0644 "$candidate/libgusb',
                          'install -m 0644 "$candidate/libopencv',
                          'install -m 0644 "$pam', "authselect enable-feature",
                          "authselect disable-feature"):
            self.assertNotIn(forbidden, root)

    def test_06_rollback_restores_runtime_state_and_old_template(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        self.assertLess(root.index("deployment_started=true"),
                        root.index('systemctl stop fprintd.service'))
        rollback = section(self.script, "rollback ()", "write_updated_state ()")
        for marker in ("restore_old_template",
                       "backup/libfprint-2.so.2.0.0",
                       "backup/artifacts.sha256", "backup/d285-01.state",
                       "sha256sum -c artifacts.sha256",
                       "PASS_OLD_RUNTIME_AND_TEMPLATE_RESTORED",
                       "FAILED_HUMAN_RECOVERY_REQUIRED"):
            self.assertIn(marker, rollback)
        restore = section(self.script, "restore_old_template ()", "rollback ()")
        self.assertIn("old_template_sha", restore)
        self.assertIn("cp -a", restore)

    def test_07_enrollment_diversity_is_bounded_and_audited(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        for marker in ("REENROLL DESTRO", "enroll-stage-passed",
                       "enroll-retry-", "$accepted_count -ge 3",
                       "$accepted_count -le 8", "$physical_count -le 20",
                       "enroll_stages=[3-8]",
                       "enroll_contacts=", "enroll_retry_scans=",
                       "ENROLLMENT_CONTACT_TELEMETRY_MISMATCH",
                       "D291_01_ENROLL_PHYSICAL_CONTACT_MAX=20"):
            self.assertIn(marker, root)

    def test_08_four_independent_verify_series_each_max_three(self):
        root = section(self.script, "root_run ()", "operator_run ()")
        for series in range(1, 5):
            self.assertIn(f"run_verify_series {series} ", root)
        verify = section(self.script, "run_verify_series ()", "root_run ()")
        self.assertIn("${#epochs[@]} -ge 1", verify)
        self.assertIn("${#epochs[@]} -le 3", verify)
        self.assertIn("${outcomes[-1]} == *result=match*", verify)
        self.assertIn("sudo -K", verify)
        self.assertNotIn("while true", verify)

    def test_09_first_series_requires_wrong_finger_rejection(self):
        verify = section(self.script, "run_verify_series ()", "root_run ()")
        self.assertIn("dito NON registrato", verify)
        self.assertIn("${outcomes[0]} == *result=no_match*", verify)
        self.assertIn("SERIES_1_WRONG_FINGER_NOT_REJECTED", verify)

    def test_10_each_verify_epoch_preserves_factory_guards(self):
        verify = section(self.script, "run_verify_series ()", "root_run ()")
        for field in ("attempts", "rejected", "consumed", "tls",
                      "first_image", "secure_retry", "post_retry", "reset",
                      "clear_halt", "persistent", "outstanding", "drained",
                      "context_closed"):
            self.assertIn(f"{field}=", verify)

    def test_11_explicit_verify_reopen_is_visible(self):
        verify = section(self.script, "run_verify_series ()", "root_run ()")
        self.assertIn("reopen=0 explicit_verify_reopen=0", verify)
        self.assertIn("reopen=1 explicit_verify_reopen=1", verify)
        self.assertIn("sigfm_baseline_pinned=1 sigfm_baseline_reused=0", verify)
        self.assertIn("sigfm_baseline_pinned=0 sigfm_baseline_reused=1", verify)

    def test_12_no_credential_gate_or_unbounded_retry(self):
        self.assertNotIn("grant", self.script.lower())
        self.assertNotIn("token", self.script.lower())
        self.assertNotIn("while true", self.script)
        self.assertIn('script_path="$script_dir/run-d291-01.sh"', self.script)
        self.assertIn('"$script_path"', self.script)
        self.assertIn('--root-run "$candidate" "$baseline"', self.script)

    def test_13_readme_discloses_closed_gate_and_result(self):
        for marker in ("HISTORICAL_CLOSED_DO_NOT_RERUN", "re-enrollment", "3 a 8", "20",
                       "quattro serie VERIFY", "NO_MATCH", "MATCH", "Ctrl-C",
                       "rollback", "RESULT_DIRECTORY",
                       "template biometrico host", "FACTORY_PRESERVING"):
            self.assertIn(marker, self.readme)

    def test_14_closed_kit_stops_before_privileged_action(self):
        completed = subprocess.run(
            [str(SCRIPT), "--operator-run"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(completed.returncode, 4)
        self.assertIn("HISTORICAL_CLOSED_DO_NOT_RERUN", completed.stderr)
        self.assertIn("PASS_REENROLL_AND_4_MATCHED_SERIES", completed.stderr)


if __name__ == "__main__":
    unittest.main()
