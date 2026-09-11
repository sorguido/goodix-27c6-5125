#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "operator_kit/d286-01-reboot-survival/run-d286-01.sh"
README = ROOT / "operator_kit/d286-01-reboot-survival/README_IT.md"
RPM_MANIFEST = ROOT / "operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256"
CANONICAL_RPM_DIR = (
    "/home/guido/Repository/goodix-27c6-5125_private/"
    "GoodixArtifacts/opencv-4.13-rpms"
)


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

    def test_03_root_audit_checks_all_persistent_surfaces(self):
        audit = section(self.script, "d286_root_audit_installed ()", "d286_valid_cursor ()")
        for marker in (
                "STATE_MODE_OR_OWNER_DRIFT", "AUTHSELECT_ACTIVE_DRIFT",
                "DAEMON_PROVENANCE_DRIFT", "PAM_FILE_DRIFT", "SUDOERS_FILE_DRIFT",
                "WRAPPER_FILE_DRIFT", "DROPIN_FILE_DRIFT", "RUNTIME_ARTIFACT_DRIFT",
                "SYSTEM_LIBFPRINT_DRIFT", "TEMPLATE_OWNERSHIP_DRIFT",
                "UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES"):
            self.assertIn(marker, audit)

    def test_04_root_audit_exports_no_protected_values(self):
        audit = section(self.script, "d286_root_audit_installed ()", "d286_valid_cursor ()")
        output = audit[audit.index('echo "D286_01_ROOT_AUDIT_PHASE=') :]
        for forbidden in ("template_relative", "template_sha", "manifest_sha"):
            self.assertNotIn(forbidden, output)

    def test_05_first_reboot_cycle_is_closed_before_any_action(self):
        pre = section(self.script, "operator_pre_reboot ()", "operator_post_reboot ()")
        post = section(self.script, "operator_post_reboot ()", "operator_retry ()")
        self.assertIn("FIRST_REBOOT_CYCLE_CLOSED_USE_OPERATOR_RETRY", pre)
        self.assertIn("FIRST_REBOOT_CYCLE_CLOSED_USE_OPERATOR_RETRY", post)
        self.assertNotIn("systemctl reboot", self.script)
        self.assertNotIn("--since", self.script)

    def test_06_journal_boundary_is_cursor_based_and_locale_independent(self):
        cursor = section(self.script, "d286_current_cursor ()", "d286_root_attempt_audit ()")
        audit = section(self.script, "d286_root_attempt_audit ()", "d286_run_sudo_attempt ()")
        self.assertIn("--show-cursor", cursor)
        self.assertIn("LC_ALL=C", cursor)
        self.assertIn('--after-cursor "$cursor"', audit)
        self.assertIn("LC_ALL=C", audit)
        self.assertNotIn("date --iso-8601", self.script)

    def test_07_root_attempt_audit_waits_only_for_telemetry(self):
        audit = section(self.script, "d286_root_attempt_audit ()", "d286_run_sudo_attempt ()")
        self.assertIn("for poll in {1..50}", audit)
        self.assertIn("sleep 0.1", audit)
        for forbidden in ("sudo ", "fprintd-verify", "systemctl restart"):
            self.assertNotIn(forbidden, audit)

    def test_08_real_sudo_has_passwordless_input_channel(self):
        run = section(self.script, "d286_run_sudo_attempt ()", "operator_pre_reboot ()")
        self.assertIn("/usr/bin/sudo -S", run)
        self.assertIn("-p \"$marker\" -v", run)
        self.assertIn("mkfifo -m 0600", run)
        self.assertIn('exec {d286_attempt_fd}<>"$d286_attempt_fifo"', run)
        self.assertNotIn("read -r", run)
        self.assertNotIn("echo ", run)

    def test_09_fallback_marker_kills_exact_sudo_process(self):
        run = section(self.script, "d286_run_sudo_attempt ()", "operator_pre_reboot ()")
        self.assertIn("D286_PASSWORD_FALLBACK_BLOCKED", run)
        self.assertIn('kill -KILL "$d286_attempt_pid"', run)
        self.assertIn("d286_attempt_fallback_blocked=true", run)
        self.assertNotIn("timeout --signal", run)

    def test_10_three_attempts_are_separate_sudo_processes(self):
        operator = section(self.script, "operator_retry ()", "offline_preflight ()")
        self.assertIn("for attempt in 1 2 3", operator)
        self.assertEqual(self.script.count("/usr/bin/sudo -S"), 1)
        self.assertIn('d286_run_sudo_attempt "$attempt"', operator)
        self.assertIn("sudo -K", operator)

    def test_11_budget_and_stop_on_first_match_are_explicit(self):
        operator = section(self.script, "operator_retry ()", "offline_preflight ()")
        self.assertIn("d286_max_verify_attempts=3", self.script)
        self.assertIn("MAX_PHYSICAL_CONTACTS=3", operator)
        self.assertIn("PAM_MAX_TRIES_PER_ATTEMPT=1", operator)
        self.assertIn("STOP_ON_FIRST_MATCH=true", operator)
        match = operator[operator.index("MATCH)"):operator.index("NO_MATCH)")]
        self.assertIn("break", match)

    def test_12_every_additional_attempt_requires_confirmation(self):
        operator = section(self.script, "operator_retry ()", "offline_preflight ()")
        self.assertIn("INDICE DESTRO", operator)
        self.assertIn('TENTATIVO $((attempt + 1))', operator)
        self.assertIn("NEXT_ATTEMPT_NOT_CONFIRMED", operator)
        self.assertIn("RETRY_SERIES_FAILED_NO_FOURTH_ATTEMPT", operator)

    def test_13_attempt_outcomes_are_journal_classified(self):
        audit = section(self.script, "d286_root_attempt_audit ()", "d286_run_sudo_attempt ()")
        for outcome in ("MATCH", "NO_MATCH", "PAM_ERROR", "SAFETY_VIOLATION"):
            self.assertIn(outcome, audit)
        self.assertIn("event=outcome result=match", audit)
        self.assertIn("event=outcome result=no_match", audit)

    def test_14_attempt_telemetry_is_separate_and_complete(self):
        audit = section(self.script, "d286_root_attempt_audit ()", "d286_run_sudo_attempt ()")
        for marker in (
                "ATTEMPT_INDEX", "ATTEMPT_OUTCOME", "ATTEMPT_SUDO_RETURN_CODE",
                "ATTEMPT_VERIFY_EPOCH_COUNT", "ATTEMPT_PROBE_EXTRACT_COUNT",
                "ATTEMPT_COMPARISON_COUNT", "ATTEMPT_MATCH_COUNT",
                "ATTEMPT_NO_MATCH_COUNT", "ATTEMPT_RETRY_COUNT",
                "ATTEMPT_REOPEN_COUNT", "ATTEMPT_RESET_COUNT",
                "ATTEMPT_CLEAR_HALT_COUNT", "ATTEMPT_PERSISTENT_WRITE_FAMILY_COUNT"):
            self.assertIn(marker, audit)
        self.assertIn("GOODIX_SIGFM_", audit)
        self.assertIn("GOODIX_D282_EPOCH_AUDIT", audit)

    def test_15_hidden_retry_and_persistent_activity_are_safety_violations(self):
        audit = section(self.script, "d286_root_attempt_audit ()", "d286_run_sudo_attempt ()")
        for marker in (
                "$total_epoch_count -gt 1", "$retry_count -ne 0", "$reopen_count -ne 0",
                "$reset_count -ne 0", "$clear_halt_count -ne 0",
                "$persistent_count -ne 0"):
            self.assertIn(marker, audit)

    def test_16_no_enroll_delete_reinstall_or_matcher_change(self):
        for forbidden in (
                "fprintd-enroll", "fprintd-delete", "authselect enable-feature",
                "authselect disable-feature", "dnf install", "rpm -U",
                "SIGFM_THRESHOLD=", "threshold="):
            self.assertNotIn(forbidden, self.script)

    def test_17_capture_excludes_template_and_protected_values(self):
        self.assertIn("captures/D286_01", self.script)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", self.script)
        self.assertNotIn("D285_01_TEMPLATE_SHA256=", self.script)

    def test_18_offline_preflight_cannot_call_privileged_or_live_paths(self):
        offline = section(self.script, "offline_preflight ()", "case ${1:-}")
        for forbidden in ("pkexec ", "sudo ", "systemctl", "d286_root_audit_installed"):
            self.assertNotIn(forbidden, offline)
        self.assertIn("d286_current_cursor", offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)

    def test_19_closed_readme_preserves_historical_stop_conditions(self):
        for marker in (
                "CHIUSO", "D286_01_LIVE_CLOSED_DO_NOT_RERUN",
                "--operator-retry", "INDICE DESTRO",
                "TENTATIVO 2", "TENTATIVO 3", "senza un quarto tentativo",
                "PAM_ERROR", "SAFETY_VIOLATION", "STOP_ON_FIRST_MATCH=true"):
            self.assertIn(marker, self.readme)
        self.assertNotIn("Ctrl-C", self.readme)

    def test_20_d285_install_remains_closed_and_uninstall_retained(self):
        d285 = (ROOT / "operator_kit/d285-01-persistent-sudo/run-d285-01.sh").read_text()
        self.assertIn("d285_install_closed=true", d285)
        self.assertIn("--operator-uninstall)", d285)

    def test_21_repo_gate_covers_current_critical_paths(self):
        gate = section(self.script, "d286_verify_repo ()", "d286_cleanup_journal_tmp ()")
        self.assertIn("status --porcelain --untracked-files=all", gate)
        self.assertIn('"${d286_critical[@]}"', gate)
        self.assertIn("GoodixArtifacts .gitignore", self.script)

    def test_22_first_cycle_evidence_is_hash_pinned(self):
        result = subprocess.run(
            ["python3", str(ROOT / "analysis/D286/d286_01_first_cycle_evidence_audit.py")],
            check=True, capture_output=True, text=True)
        self.assertIn("PASS_HASH_PINNED_WITH_SAME_BOOT_RECOVERY", result.stdout)

    def test_23_first_cycle_required_classification_is_preserved(self):
        normalized = (ROOT / "analysis/D286/D286_01_FIRST_CYCLE_NORMALIZED.env").read_text()
        for marker in (
                "POST_REBOOT_PERSISTENT_STATE_AUDIT=PASS",
                "FIRST_POST_REBOOT_VERIFY=NO_MATCH", "PASSWORD_FALLBACK_ENTERED=true",
                "PASSWORD_USED_FOR_TEST=false", "FAILURE_AUDIT_TIMESTAMP_BUG=true",
                "AUTOMATIC_RETRY_PERFORMED=false"):
            self.assertIn(marker, normalized)

    def test_24_opencv_path_is_persistent_and_rpms_are_ignored(self):
        self.assertIn(CANONICAL_RPM_DIR, self.readme)
        self.assertIn("GoodixArtifacts/opencv-4.13-rpms/*.rpm",
                      (ROOT / ".gitignore").read_text())
        for path in (ROOT / "operator_kit").glob("*/README_IT.md"):
            self.assertNotIn("/tmp/goodix-opencv-4.13-rpms", path.read_text(), str(path))

    def test_25_canonical_opencv_manifest_is_unchanged(self):
        expected = {
            "6679ed1cf4a5cfd385837aa126c31d8f333b340465c295e41e5b2738f8a3d399  opencv-core-4.13.0-1.fc44.x86_64.rpm",
            "8b4fe567603f3ceece9bf9988e1cd87da98850d76049fb72a30c1c91e0f9e905  opencv-devel-4.13.0-1.fc44.x86_64.rpm",
            "a2acebbfdba20612ce6e34d091847e26f55c168288e7cb6d3e96ea00e2b948a9  opencv-features2d-4.13.0-1.fc44.x86_64.rpm",
            "6aeefd7e0d79383984f7139eb16bbda57ee342a04c908cecb9630c3420044c28  opencv-flann-4.13.0-1.fc44.x86_64.rpm",
            "1bbcc35f60dde99717edafccba9f4d94e38ecb21e13693c16ac7d6362fdcaceb  opencv-imgproc-4.13.0-1.fc44.x86_64.rpm",
        }
        self.assertEqual(set(RPM_MANIFEST.read_text().splitlines()), expected)

    def test_26_attempt_cleanup_is_bounded(self):
        cleanup = section(self.script, "d286_cleanup_attempt ()", "d286_abort_attempt ()")
        self.assertIn("/tmp/goodix-d286-input.*/password-input", cleanup)
        self.assertIn("! -L $d286_attempt_fifo", cleanup)
        self.assertIn("rmdir --", cleanup)
        self.assertNotIn("rm -rf", cleanup)

    def test_27_cursor_and_root_dispatch_arguments_are_validated(self):
        self.assertIn("d286_valid_cursor", self.script)
        dispatch = self.script[self.script.index("case ${1:-}"):]
        self.assertIn("[[ $# -eq 13", dispatch)
        self.assertIn("--watchdog-timeout", dispatch)

    def _run_supervisor_fixture(self, fake_body: str) -> str:
        cleanup = section(self.script, "d286_cleanup_attempt ()", "d286_abort_attempt ()")
        abort = section(self.script, "d286_abort_attempt ()", "d286_require_polkit_password_path ()")
        run = section(self.script, "d286_run_sudo_attempt ()", "operator_pre_reboot ()")
        with tempfile.TemporaryDirectory(prefix="goodix-d286-supervisor-") as tmp:
            tmp_path = Path(tmp)
            fake = tmp_path / "fake-sudo"
            fake.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + fake_body)
            fake.chmod(0o700)
            capture_root = tmp_path / "captures/D286_01"
            capture = capture_root / "D28601_RETRY_FIXTURE/sanitized"
            capture.mkdir(parents=True)
            harness = tmp_path / "harness.sh"
            harness.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                f"d286_capture_root={capture_root!s}\n"
                "d286_attempt_input_dir=\nd286_attempt_fifo=\nd286_attempt_fd=\n"
                "d286_attempt_pid=\nd286_attempt_rc=\n"
                "d286_attempt_fallback_blocked=false\n"
                "d286_attempt_watchdog_timeout=false\n"
                "d286_refuse () { echo REFUSED=$1 >&2; exit 3; }\n"
                + cleanup + abort
                + run.replace("/usr/bin/sudo", str(fake))
                + f'd286_run_sudo_attempt 1 "{capture}/attempt-1.sudo.log"\n'
                + "echo RC=$d286_attempt_rc\n"
                + "echo FALLBACK=$d286_attempt_fallback_blocked\n"
                + "echo WATCHDOG=$d286_attempt_watchdog_timeout\n")
            result = subprocess.run(["bash", str(harness)], check=True,
                                    capture_output=True, text=True, timeout=10)
            return result.stdout

    def test_28_supervisor_fixture_accepts_immediate_match_exit(self):
        output = self._run_supervisor_fixture("exit 0\n")
        self.assertIn("RC=0", output)
        self.assertIn("FALLBACK=false", output)
        self.assertIn("WATCHDOG=false", output)

    def test_29_supervisor_fixture_kills_blocked_password_fallback(self):
        output = self._run_supervisor_fixture(
            "printf %s \"$3\" >&2\nread -r ignored\n")
        self.assertIn("RC=137", output)
        self.assertIn("FALLBACK=true", output)
        self.assertIn("WATCHDOG=false", output)

    def test_30_live_target_gate_and_sensor_summary_are_evidence_based(self):
        operator = section(self.script, "operator_retry ()", "offline_preflight ()")
        self.assertIn("count_goodix_targets /sys/bus/usb/devices", operator)
        self.assertIn("REAL_TARGET_CARDINALITY_NOT_ONE", operator)
        self.assertLess(operator.index("REAL_TARGET_CARDINALITY_NOT_ONE"),
                        operator.index("d286_run_sudo_attempt"))
        self.assertIn("verify_epoch_total", operator)
        self.assertIn("REAL_SENSOR_ACCESSED=false", operator)

    def test_31_all_positional_parameters_above_nine_are_braced(self):
        dispatch = self.script[self.script.index("case ${1:-}"):]
        for index in range(10, 14):
            self.assertIn(f"${{{index}}}", dispatch)
        self.assertIsNone(re.search(r"(?<!\{)\$(?:10|11|12|13)\b", dispatch))

    def test_32_completed_live_entrypoint_is_closed_before_action(self):
        operator = section(self.script, "operator_retry ()", "offline_preflight ()")
        refusal = operator.index("D286_01_LIVE_CLOSED_DO_NOT_RERUN")
        self.assertLess(refusal, operator.index("git -C"))
        self.assertLess(refusal, operator.index("pkexec"))
        self.assertIn("CHIUSO", self.readme)

    def test_33_retry_evidence_is_hash_pinned_and_classified(self):
        result = subprocess.run(
            ["python3", str(ROOT / "analysis/D286/d286_01_retry_evidence_audit.py")],
            check=True, capture_output=True, text=True)
        self.assertIn("PASS_HASH_PINNED_HOST_FAILURES_AND_FINAL_MATCH", result.stdout)

    def test_34_permanent_explicit_retry_policy_is_canonical(self):
        manual = (ROOT / "Goodix 27c6 5125 manuale tecnico.md").read_text()
        for marker in (
                "INITIAL_FINGER_ATTEMPT=1",
                "MINIMUM_EXPLICIT_FINGER_RETRIES_AFTER_NO_MATCH=2",
                "MINIMUM_TOTAL_OPERATOR_FINGER_ATTEMPTS=3",
                "STOP_ON_FIRST_MATCH=true",
                "AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false"):
            self.assertIn(marker, manual)


if __name__ == "__main__":
    unittest.main()
