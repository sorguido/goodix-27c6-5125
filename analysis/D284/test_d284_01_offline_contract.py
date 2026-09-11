#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d284-01-transient-sudo-pilot"
SCRIPT = KIT / "run-d284-01.sh"
D282 = ROOT / "operator_kit/d282-01-fprintd-target/run-d282-01.sh"


def function_slice(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


class D284OfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text()
        cls.pam = (KIT / "goodix-d284-01-sudo.pam").read_text()
        cls.readme = (KIT / "README_IT.md").read_text()
        cls.d282 = D282.read_text()

    def test_01_pam_service_has_one_try_and_password_fallback(self):
        self.assertIn("pam_fprintd.so max-tries=1 timeout=45", self.pam)
        self.assertEqual(self.pam.count("pam_fprintd.so"), 1)
        self.assertIn("auth        sufficient                                   pam_unix.so nullok", self.pam)
        self.assertLess(self.pam.index("pam_fprintd.so"), self.pam.index("pam_unix.so"))
        self.assertIn("auth        required                                     pam_deny.so", self.pam)

    def test_02_only_new_named_pam_and_sudoers_paths_are_used(self):
        self.assertIn("/etc/pam.d/goodix-d284-01-sudo", self.script)
        self.assertIn("/etc/sudoers.d/90-goodix-d284-01-pilot", self.script)
        self.assertNotIn('>"/etc/pam.d/sudo"', self.script)
        self.assertNotIn('>"/etc/authselect/', self.script)
        self.assertNotIn("authselect enable-feature", self.script)
        self.assertNotIn("authselect disable-feature", self.script)

    def test_03_sudo_override_is_scoped_to_one_user_and_service(self):
        writer = function_slice(self.script, "write_d284_sudoers ()", "install_d284_overrides ()")
        self.assertIn("Defaults:%s pam_service=goodix-d284-01-sudo", writer)
        self.assertIn("visudo -cf", self.script)

    def test_04_real_target_gate_is_exact_and_precedes_staging(self):
        live = function_slice(self.script, "run_d284_live ()", "export_d284_results ()")
        staging = live.index("live_staging_started=true")
        for marker in (
                "verify_d284_baseline", "SUDO_NEVRA_DRIFT", "PAM_NEVRA_DRIFT",
                "FPRINTD_NEVRA_DRIFT", "FPRINTD_PAM_NEVRA_DRIFT",
                "AUTHSELECT_PROFILE_DRIFT", "SYSTEM_AUTH_FPRINT_CONTRACT_DRIFT",
                "PILOT_PASSWORD_FALLBACK_MISSING", "OPERATOR_NOT_SUDOER",
                "TARGET_CARDINALITY_NOT_ONE"):
            self.assertLess(live.index(marker), staging, marker)

    def test_05_live_budget_is_one_enroll_one_sudo_verify(self):
        live = function_slice(self.script, "run_d284_live ()", "export_d284_results ()")
        self.assertEqual(live.count("fprintd-enroll -f"), 1)
        self.assertEqual(live.count("sudo -v"), 2)  # phase label plus invocation
        self.assertIn("BIOMETRIC_ACTION_MAX=2", live)
        self.assertIn("EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=9", live)
        self.assertNotIn("fprintd-verify", live)

    def test_06_sudo_timestamp_is_invalidated_before_and_after(self):
        live = function_slice(self.script, "run_d284_live ()", "export_d284_results ()")
        auth = live.index('env -u SUDO_ASKPASS sudo -v')
        first = live.index('runuser -u "$user" -- sudo -K')
        second = live.index('runuser -u "$user" -- sudo -K', auth)
        self.assertLess(first, auth)
        self.assertGreater(second, auth)
        self.assertIn("D284_01_SUDO_TIMESTAMP_INVALIDATED", self.script)

    def test_07_physical_confirmations_precede_actions(self):
        live = function_slice(self.script, "run_d284_live ()", "export_d284_results ()")
        self.assertLess(live.index("ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED"),
                        live.index("fprintd-enroll -f"))
        self.assertLess(live.index("SUDO_PHYSICAL_FINGER_NOT_CONFIRMED"),
                        live.index('env -u SUDO_ASKPASS sudo -v'))

    def test_08_overrides_are_removed_before_delete(self):
        live = function_slice(self.script, "run_d284_live ()", "export_d284_results ()")
        self.assertLess(live.index("remove_d284_overrides"),
                        live.index('fprintd-delete "$user"'))
        self.assertIn("D284_01_PAM_SUDOERS_REMOVED_BEFORE_DELETE=true", live)

    def test_09_cleanup_covers_overrides_timestamp_and_shared_runtime(self):
        cleanup = function_slice(self.script, "cleanup_d284 ()", "write_d284_sudoers ()")
        self.assertIn("sudo -K", cleanup)
        self.assertIn("remove_d284_overrides", cleanup)
        self.assertIn("hash_d284_host_config", cleanup)
        self.assertIn("cleanup_live", cleanup)
        self.assertIn("FAIL_ROLLBACK", cleanup)

    def test_10_cleanup_helper_removes_only_bounded_test_paths(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d284-cleanup-test.") as td:
            work = Path(td)
            pam = work / "pam"
            sudoers = work / "sudoers"
            pam.write_text("pam")
            sudoers.write_text("sudoers")
            command = (
                'D284_LIBRARY_ONLY=true; source "$0"; '
                'd284_cleanup_test_mode=true; d284_pam_path="$1"; '
                'd284_sudoers_path="$2"; d284_pam_installed=true; '
                'd284_sudoers_installed=true; remove_d284_overrides')
            subprocess.run(["bash", "-c", command, str(SCRIPT), str(pam), str(sudoers)],
                           check=True)
            self.assertFalse(pam.exists())
            self.assertFalse(sudoers.exists())

    def test_11_runtime_staging_preserves_real_file_and_symlink_shape(self):
        names = (
            "libfprint-2.so.2.0.0", "libgusb.so.2", "libopencv_core.so.413",
            "libopencv_features2d.so.413", "libopencv_flann.so.413",
            "libopencv_imgproc.so.413")
        with tempfile.TemporaryDirectory(prefix="goodix-d284-candidate-") as cd, \
             tempfile.TemporaryDirectory(prefix="goodix-d284-01-offline.") as td:
            candidate, work = Path(cd), Path(td)
            runtime = work / "runtime"
            runtime.mkdir()
            for name in names:
                (candidate / name).write_bytes(name.encode())
            command = ('D284_LIBRARY_ONLY=true; source "$0"; '
                       'stage_d284_runtime "$1" "$2"')
            subprocess.run(["bash", "-c", command, str(SCRIPT),
                            str(candidate), str(runtime)], check=True)
            self.assertFalse((runtime / "libfprint-2.so.2.0.0").is_symlink())
            self.assertEqual((runtime / "libfprint-2.so.2").readlink(),
                             Path("libfprint-2.so.2.0.0"))

    def test_12_shared_dropin_allowlists_d284_paths(self):
        self.assertIn("/run/goodix-d284-01/*", self.d282)
        self.assertIn("/var/lib/fprint/.goodix-d284-01-*", self.d282)

    def test_13_final_audit_requires_two_actions_and_no_retry(self):
        live = function_slice(self.script, "run_d284_live ()", "export_d284_results ()")
        for marker in (
                "$epoch_count -eq 3", "$enroll_count -eq 1", "$verify_count -eq 1",
                "$cleanup_epoch_count -eq 1", "$consumed_count -eq 2",
                "$retry_count -eq 0", "$reopen_count -eq 0",
                "$persistent_count -eq 0", "$matcher_match_count -eq 1",
                "$observed_max_score -ge 40", "verify_current_live_epoch_audit"):
            self.assertIn(marker, live)

    def test_14_no_login_lock_or_permanent_install(self):
        self.assertIn("D284_01_REAL_LOGIN_IN_SCOPE=false", self.script)
        self.assertIn("D284_01_KDE_LOCK_SCREEN_IN_SCOPE=false", self.script)
        self.assertNotIn("/etc/pam.d/plasmalogin", self.script)
        self.assertNotIn("/etc/pam.d/kcheckpass", self.script)
        self.assertNotIn("dnf install", self.script)
        self.assertNotIn("rpm -U", self.script)

    def test_15_operator_entrypoint_is_direct_and_exports(self):
        operator = function_slice(self.script, "operator_d284_run ()", "offline_cleanup_regression ()")
        self.assertIn("Digitare ESEGUI", operator)
        self.assertIn("--run-live", operator)
        self.assertIn("--export-results", operator)
        self.assertIn("TERMINAL_TRANSCRIPT", operator)
        self.assertNotIn("grant", operator.lower())

    def test_16_offline_preflight_cannot_call_live(self):
        offline = function_slice(self.script, "offline_preflight ()", "if [[ ${D284_LIBRARY_ONLY")
        self.assertIn("REAL_USB_ENUMERATION_ATTEMPTED=false", offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)
        self.assertIn("LIVE_EXECUTION_PERFORMED=false", offline)
        self.assertNotIn("run_d284_live", offline)

    def test_17_readme_has_human_gate_stop_conditions_and_outputs(self):
        for marker in (
                "HUMAN REQUIRED", "Ctrl-C", "non ripetere", "EXPORT_DIRECTORY",
                "TERMINAL_TRANSCRIPT", "non bloccare lo schermo",
                "fallback password"):
            self.assertIn(marker, self.readme)

    def test_18_real_target_topology_matches_current_host(self):
        raw = subprocess.run(["authselect", "current", "--raw"], check=True,
                             capture_output=True, text=True).stdout.strip()
        self.assertEqual(raw, "local with-silent-lastlog with-mdns4 with-fingerprint")
        system_auth = Path("/etc/authselect/system-auth").read_text()
        password_auth = Path("/etc/authselect/password-auth").read_text()
        self.assertIn("pam_fprintd.so", system_auth)
        self.assertNotIn("pam_fprintd.so", password_auth)

    def test_19_sensor_reaching_failures_are_captured_before_return(self):
        live = function_slice(self.script, "run_d284_live ()", "export_d284_results ()")
        for phase in (
                "ENROLL", "ENROLL_STORAGE_AUDIT", "ENROLL_FORMAT_AUDIT",
                "DAEMON_RESTART_AFTER_ENROLL", "SUDO_VALIDATE",
                "PRE_DELETE_AUDIT", "PRE_DELETE_MATCH_AUDIT",
                "SUDO_TIMESTAMP_CLEANUP", "PAM_SUDOERS_EARLY_REMOVE",
                "HOST_ONLY_DELETE", "FINAL_AUDIT"):
            self.assertIn(f"capture_d284_failure {phase}", live, phase)
        self.assertNotIn("|| return 1", live)

    def test_20_timestamp_cleanup_truth_depends_on_command_success(self):
        cleanup = function_slice(self.script, "cleanup_d284 ()", "write_d284_sudoers ()")
        success = cleanup.index("d284_timestamp_invalidated=true")
        failure = cleanup.index("d284_timestamp_invalidated=false", success)
        self.assertLess(success, failure)
        self.assertIn("d284_config_rollback=false", cleanup[failure:])

    def test_21_offline_exit_trap_uses_global_bounded_state(self):
        offline = function_slice(self.script, "cleanup_d284_offline_work ()",
                                 "if [[ ${D284_LIBRARY_ONLY")
        self.assertIn("d284_offline_work", offline)
        self.assertIn("/tmp/goodix-d284-01-offline.*", offline)
        self.assertNotIn("trap 'find \"$work\"", offline)
        work = Path(tempfile.mkdtemp(prefix="goodix-d284-01-offline.", dir="/tmp"))
        (work / "owned").write_text("owned")
        command = ('D284_LIBRARY_ONLY=true; source "$0"; '
                   'd284_offline_work="$1"; cleanup_d284_offline_work')
        subprocess.run(["bash", "-c", command, str(SCRIPT), str(work)], check=True)
        self.assertFalse(work.exists())

    def test_22_offline_cleanup_refuses_unowned_path(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d284-unowned.", dir="/tmp") as td:
            work = Path(td)
            owned = work / "preserve"
            owned.write_text("preserve")
            command = ('D284_LIBRARY_ONLY=true; source "$0"; '
                       'd284_offline_work="$1"; cleanup_d284_offline_work')
            result = subprocess.run(["bash", "-c", command, str(SCRIPT), str(work)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(owned.exists())
            self.assertIn("D284_01_OFFLINE_CLEANUP_REFUSED", result.stderr)

    def test_23_gate_refusals_after_result_creation_are_exportable(self):
        refusal = function_slice(self.script, "refuse ()", "verify_d284_baseline ()")
        self.assertIn("D284_01_RESULT=FAIL_GATE_REFUSED", refusal)
        self.assertIn("D284_01_FAILURE_PHASE=GATE_", refusal)
        self.assertIn('>>"$live_result/operator.log"', refusal)

    def test_24_rollback_failure_forces_nonzero_root_exit(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d284-cleanup-test.",
                                         dir="/tmp") as td:
            work = Path(td)
            result_dir = work / "result"
            result_dir.mkdir()
            (result_dir / "summary.env").write_text("D284_01_RESULT=PASS\n")
            (result_dir / "operator.log").write_text("")
            command = (
                'D284_LIBRARY_ONLY=true; source "$0"; '
                'cleanup_live(){ echo ROLLBACK_COMPLETE=false >>"$live_result/summary.env"; }; '
                'live_result="$1"; live_private="$1"; d284_user=; '
                'd284_cleanup_test_mode=true; d284_config_before_ready=false; '
                'd284_pam_path="$2/pam"; d284_sudoers_path="$2/sudoers"; '
                'true; cleanup_d284')
            result = subprocess.run(["bash", "-c", command, str(SCRIPT),
                                     str(result_dir), str(work)])
            self.assertNotEqual(result.returncode, 0)

    def test_25_baseline_status_pathspec_array_is_one_command(self):
        baseline = function_slice(self.script, "verify_d284_baseline ()",
                                  "stage_d284_runtime ()")
        self.assertIn("status --porcelain --untracked-files=all -- \\\n"
                      '    "${d284_critical[@]}"', baseline)


if __name__ == "__main__":
    unittest.main()
