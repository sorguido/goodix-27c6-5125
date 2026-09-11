#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "operator_kit/d286-01-reboot-survival/run-d286-01.sh"
README = ROOT / "operator_kit/d286-01-reboot-survival/README_IT.md"


def section(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


class D286OfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text()
        cls.readme = README.read_text()

    def test_01_shell_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_02_polkit_is_separate_from_d285_sudo_pam(self):
        gate = section(self.script, "d286_require_polkit_password_path ()",
                       "d286_verify_installed_file ()")
        self.assertIn("/usr/lib/pam.d/polkit-1", gate)
        self.assertIn("system-auth", gate)
        self.assertIn("POLKIT_SYSTEM_AUTH_FINGERPRINT_ENABLED", gate)
        pre = section(self.script, "operator_pre_reboot ()", "operator_post_reboot ()")
        self.assertIn("pkexec", pre)
        self.assertNotIn("sudo ", pre)

    def test_03_root_audit_checks_all_persistent_surfaces(self):
        audit = section(self.script, "d286_root_audit_installed ()",
                        "d286_root_final_audit ()")
        for marker in (
                "STATE_MODE_OR_OWNER_DRIFT", "AUTHSELECT_ACTIVE_DRIFT",
                "DAEMON_PROVENANCE_DRIFT", "PAM_FILE_DRIFT", "SUDOERS_FILE_DRIFT",
                "WRAPPER_FILE_DRIFT", "DROPIN_FILE_DRIFT", "RUNTIME_ARTIFACT_DRIFT",
                "SYSTEM_LIBFPRINT_DRIFT", "TEMPLATE_OWNERSHIP_DRIFT",
                "UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES"):
            self.assertIn(marker, audit)

    def test_04_root_audit_exports_no_protected_values(self):
        audit = section(self.script, "d286_root_audit_installed ()",
                        "d286_root_final_audit ()")
        output = audit[audit.index('echo "D286_01_ROOT_AUDIT_PHASE=') :]
        self.assertNotIn("template_relative", output)
        self.assertNotIn("template_sha", output)
        self.assertNotIn("manifest_sha", output)

    def test_05_pre_reboot_has_zero_sensor_path(self):
        pre = section(self.script, "operator_pre_reboot ()", "operator_post_reboot ()")
        for forbidden in ("sudo -v", "fprintd-", "count_goodix_targets"):
            self.assertNotIn(forbidden, pre)
        self.assertIn("REAL_SENSOR_ACCESSED=false", self.script)

    def test_06_reboot_is_explicitly_confirmed(self):
        pre = section(self.script, "operator_pre_reboot ()", "operator_post_reboot ()")
        self.assertLess(pre.index("RIAVVIA D286"), pre.index("systemctl reboot"))
        self.assertIn("REBOOT_CANCELLED", pre)

    def test_07_post_reboot_requires_changed_boot_id(self):
        post = section(self.script, "operator_post_reboot ()", "offline_preflight ()")
        self.assertIn('[[ $now != "$before" ]]', post)
        self.assertLess(post.index("REBOOT_NOT_OBSERVED"), post.index("sudo -v"))

    def test_08_post_reboot_has_exactly_one_sudo_verify(self):
        post = section(self.script, "operator_post_reboot ()", "offline_preflight ()")
        self.assertEqual(post.count("sudo -v"), 1)
        self.assertEqual(post.count("timeout --signal=INT"), 1)
        self.assertIn("SUDO_VALIDATE_FAILED_NO_RETRY", post)
        self.assertIn("sudo -K", post)

    def test_09_final_audit_requires_one_match_and_zero_retry(self):
        final = section(self.script, "d286_root_final_audit ()", "d286_capture_path ()")
        for marker in (
                "$total_epoch_count -eq 1", "$epoch_count -eq 1",
                "$retry_count -eq 0", "$reopen_count -eq 0",
                "$reset_count -eq 0", "$clear_halt_count -eq 0",
                "$persistent_count -eq 0", "$match_count -eq 1",
                "outstanding=0 drained=1 context_closed=1"):
            self.assertIn(marker, final)

    def test_10_no_enroll_delete_or_configuration_mutation(self):
        for forbidden in (
                "fprintd-enroll", "fprintd-delete", "authselect enable-feature",
                "authselect disable-feature", "dnf install", "rpm -U"):
            self.assertNotIn(forbidden, self.script)

    def test_11_capture_path_is_bounded_and_template_excluded(self):
        self.assertIn("captures/D286_01", self.script)
        self.assertIn("D28601_CYCLE_*", self.script)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", self.script)
        self.assertNotIn("D285_01_TEMPLATE_SHA256=", self.script)

    def test_12_offline_preflight_cannot_execute_privileged_or_live_paths(self):
        offline = section(self.script, "offline_preflight ()", "case ${1:-}")
        for forbidden in ("pkexec ", "sudo ", "systemctl reboot", "d286_root_audit_installed"):
            self.assertNotIn(forbidden, offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)

    def test_13_readme_has_human_gate_and_stop_conditions(self):
        for marker in (
                "HUMAN REQUIRED", "RIAVVIA D286", "INDICE DESTRO", "Ctrl-C",
                "Non ripetere", "SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE",
                "--operator-pre-reboot", "--operator-post-reboot"):
            self.assertIn(marker, self.readme)

    def test_14_d285_install_remains_closed_and_uninstall_retained(self):
        d285 = (ROOT / "operator_kit/d285-01-persistent-sudo/run-d285-01.sh").read_text()
        self.assertIn("d285_install_closed=true", d285)
        self.assertIn("--operator-uninstall)", d285)

    def test_15_baseline_status_pathspec_is_one_command(self):
        gate = section(self.script, "d286_verify_repo ()",
                       "d286_cleanup_journal_tmp ()")
        self.assertIn("status --porcelain --untracked-files=all -- \\\n"
                      '    "${d286_critical[@]}"', gate)

    def test_16_failure_reporting_and_journal_cleanup_are_bounded(self):
        self.assertIn("raw=$(mktemp /tmp/goodix-d286-journal.XXXXXX)", self.script)
        self.assertIn("d286_journal_tmp=$raw", self.script)
        cleanup = section(self.script, "d286_cleanup_journal_tmp ()",
                          "d286_require_polkit_password_path ()")
        self.assertIn("/tmp/goodix-d286-journal.*", cleanup)
        self.assertIn("! -L $d286_journal_tmp", cleanup)
        post = section(self.script, "operator_post_reboot ()", "offline_preflight ()")
        self.assertIn("POST_REBOOT_ROOT_AUDIT_FAILED", post)
        self.assertIn("POST_REBOOT_FINAL_AUDIT_FAILED", post)
        self.assertIn("rc=${PIPESTATUS[0]}", post)

    def test_17_failed_verify_collects_diagnostics_without_retry(self):
        failure = section(self.script, "d286_root_failure_audit ()",
                          "d286_capture_path ()")
        for marker in (
                "FAILURE_AUDIT=COLLECTED_NO_RETRY",
                "FAILURE_TOTAL_EPOCH_COUNT", "FAILURE_VERIFY_EPOCH_COUNT",
                "FAILURE_RETRY_COUNT", "FAILURE_REOPEN_COUNT",
                "FAILURE_RESET_COUNT", "FAILURE_CLEAR_HALT_COUNT",
                "FAILURE_PERSISTENT_WRITE_FAMILY_COUNT", "FAILURE_MATCH_COUNT"):
            self.assertIn(marker, failure)
        post = section(self.script, "operator_post_reboot ()", "offline_preflight ()")
        self.assertLess(post.index("--root-failure-audit"),
                        post.index("SUDO_VALIDATE_FAILED_NO_RETRY"))
        self.assertEqual(post.count("sudo -v"), 1)
        self.assertIn("FAIL_LIVE_NO_RETRY_PENDING_INDEPENDENT_REVIEW", post)


if __name__ == "__main__":
    unittest.main()
