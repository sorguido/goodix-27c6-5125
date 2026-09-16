#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d283-01-pam-dedicated"
D282 = ROOT / "operator_kit/d282-01-fprintd-target/run-d282-01.sh"
PAM_SOURCE = ROOT / "reference/fprintd-fedora44-1.94.5/source/pam/pam_fprintd.c"
CAPTURE = (ROOT / "captures/D283_01" /
           "D28301_ATTEMPT_01_20260911T042655Z_2cf82fd1fdb6/sanitized")


def function_slice(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


class D283OfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kit = (KIT / "run-d283-01.sh").read_text()
        cls.runner = (KIT / "pam-confdir-runner.c").read_text()
        cls.service = (KIT / "goodix-d283-01.pam").read_text().strip()
        cls.d282 = D282.read_text()
        cls.pam = PAM_SOURCE.read_text()

    def test_01_dedicated_service_is_exact_and_has_one_try(self):
        self.assertEqual(
            self.service,
            "auth required /usr/lib64/security/pam_fprintd.so "
            "max-tries=1 timeout=45")
        self.assertNotIn("/etc/pam.d", self.kit)
        self.assertNotIn("system-auth", self.service)

    def test_02_runner_uses_confdir_and_only_authenticate(self):
        self.assertIn("pam_start_confdir", self.runner)
        self.assertIn('"goodix-d283-01"', self.runner)
        self.assertIn("pam_authenticate", self.runner)
        self.assertIn("pam_end", self.runner)
        self.assertNotIn("pam_chauthtok", self.runner)

    def test_03_exact_pam_source_honors_max_tries_one(self):
        self.assertIn('#define MAX_TRIES_MATCH "max-tries="', self.pam)
        self.assertIn("data->max_tries = max_tries", self.pam)
        self.assertIn("data->max_tries--", self.pam)
        self.assertIn("return PAM_MAXTRIES", self.pam)

    def test_04_no_login_or_sudo_biometric_service(self):
        self.assertIn("D283_01_REAL_LOGIN_IN_SCOPE=false", self.kit)
        self.assertIn("D283_01_SUDO_BIOMETRIC_AUTHENTICATION_IN_SCOPE=false",
                      self.kit)
        self.assertNotIn("/etc/pam.d/login", self.kit)
        self.assertNotIn("/etc/pam.d/sudo", self.kit)
        self.assertIn("d283_live_closed=true", self.kit)
        self.assertEqual(
            self.kit.count("D283_01_LIVE_CLOSED_DO_NOT_RERUN"),
            2)

    def test_05_live_budget_is_two_actions_and_nine_contacts(self):
        self.assertIn("BIOMETRIC_ACTION_MAX=2", self.kit)
        self.assertIn("EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=9", self.kit)
        live = function_slice(self.kit, "run_d283_live ()", "export_d283_results ()")
        self.assertEqual(live.count("fprintd-enroll -f"), 1)
        self.assertIn(
            '"$live_runtime/d283-pam-confdir-runner" "$live_runtime/pam.d"',
            live)
        self.assertNotIn("fprintd-verify", live)

    def test_06_pam_finger_confirmation_precedes_authentication(self):
        live = function_slice(self.kit, "run_d283_live ()", "export_d283_results ()")
        confirm = live.index("INDICE DESTRO")
        auth = live.index('"$live_runtime/d283-pam-confdir-runner"', confirm)
        self.assertLess(confirm, auth)
        self.assertIn("PAM_PHYSICAL_FINGER_NOT_CONFIRMED", live)

    def test_07_all_host_gates_precede_staging(self):
        live = function_slice(self.kit, "run_d283_live ()", "export_d283_results ()")
        staging = live.index("live_staging_started=true")
        for marker in (
                "verify_d283_baseline", "PAM_MANIFEST_DRIFT",
                "PAM_SERVICE_DRIFT", "FPRINTD_PAM_NEVRA_DRIFT",
                "PAM_RUNNER_LINKAGE_INVALID", "TARGET_CARDINALITY_NOT_ONE"):
            self.assertLess(live.index(marker), staging, marker)

        baseline = function_slice(
            self.kit, "verify_d283_baseline ()", "build_pam_runner ()")
        self.assertIn("-- \\\n", baseline)
        self.assertIn('"${d283_critical[@]}"', baseline)

    def test_08_audit_requires_one_enroll_one_verify_and_delete_epoch(self):
        live = function_slice(self.kit, "run_d283_live ()", "export_d283_results ()")
        self.assertIn("$epoch_count -eq 3", live)
        self.assertIn("$enroll_count -eq 1", live)
        self.assertIn("$verify_count -eq 1", live)
        self.assertIn("$cleanup_epoch_count -eq 1", live)
        self.assertIn("$retry_count -eq 0", live)
        self.assertIn("verify_current_live_epoch_audit", live)

    def test_09_shared_cleanup_supports_d283_without_broad_delete(self):
        self.assertIn("/run/goodix-d283-01/*", self.d282)
        self.assertIn("/var/lib/fprint/.goodix-d283-01-*", self.d282)
        self.assertIn("${result_prefix}_RESULT", self.d282)
        self.assertNotIn("rm -rf /var/lib/fprint", self.d282)

    def test_10_operator_entrypoint_is_direct_and_exports(self):
        operator = function_slice(
            self.kit, "operator_d283_run ()", "offline_preflight ()")
        self.assertIn("Digitare ESEGUI", operator)
        self.assertIn("--run-live", operator)
        self.assertIn("--export-results", operator)
        self.assertIn("TERMINAL_TRANSCRIPT", operator)
        self.assertNotIn('rm -f -- "$transcript"', operator)
        self.assertNotIn("grant", operator.lower())

    def test_11_runner_build_and_real_confdir_permit(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d283-test-") as td:
            td = Path(td)
            binary = td / "runner"
            confdir = td / "pam.d"
            confdir.mkdir()
            (confdir / "goodix-d283-01").write_text(
                "auth required /usr/lib64/security/pam_permit.so\n")
            subprocess.run([
                "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                str(KIT / "pam-confdir-runner.c"), "-Wl,-l:libpam.so.0",
                "-o", str(binary)], check=True)
            result = subprocess.run(
                [str(binary), str(confdir), "nobody"],
                check=True, capture_output=True, text=True)
            self.assertIn("D283_01_PAM_AUTHENTICATE_RETURN_CODE=0",
                          result.stdout)

    def test_12_offline_preflight_cannot_reach_live(self):
        offline = function_slice(self.kit, "offline_preflight ()", "case ${1:-} in")
        self.assertIn("REAL_USB_ENUMERATION_ATTEMPTED=false", offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)
        self.assertIn("LIVE_EXECUTION_PERFORMED=false", offline)
        self.assertNotIn("run_d283_live", offline)

    def test_13_failure_diagnostics_are_exportable_without_template(self):
        self.assertIn("capture_d283_failure ENROLL", self.kit)
        self.assertIn("capture_d283_failure PAM_AUTHENTICATE", self.kit)
        self.assertIn("capture_d283_failure PHASE_B_AUDIT", self.kit)
        self.assertIn("capture_d283_failure FINAL_AUDIT", self.kit)
        self.assertIn("D283_01_FAILURE_PHASE", self.kit)
        self.assertIn('D283_01_RESULT=FAIL_${phase}', self.kit)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", self.kit)

    def test_14_runtime_staging_copies_real_files_before_symlinks(self):
        names = (
            "libfprint-2.so.2.0.0", "libgusb.so.2",
            "libopencv_core.so.413", "libopencv_features2d.so.413",
            "libopencv_flann.so.413", "libopencv_imgproc.so.413",
        )
        with tempfile.TemporaryDirectory(prefix="goodix-d283-candidate-") as cd, \
             tempfile.TemporaryDirectory(prefix="goodix-d283-01-offline.") as td:
            candidate, work = Path(cd), Path(td)
            runtime = work / "runtime"
            runtime.mkdir()
            (candidate / "pam.d").mkdir()
            for name in names:
                (candidate / name).write_bytes(f"fixture:{name}".encode())
            (candidate / "libfprint-2.so.2").symlink_to("libfprint-2.so.2.0.0")
            (candidate / "libfprint-2.so").symlink_to("libfprint-2.so.2")
            runner = candidate / "d283-pam-confdir-runner"
            runner.write_text("fixture")
            runner.chmod(0o700)
            (candidate / "pam.d/goodix-d283-01").write_text(self.service + "\n")
            subprocess.run(
                ["bash", "-c", 'D283_LIBRARY_ONLY=true; source "$0"; stage_d283_runtime "$1" "$2"',
                 str(KIT / "run-d283-01.sh"), str(candidate), str(runtime)],
                check=True)
            self.assertFalse((runtime / "libfprint-2.so.2.0.0").is_symlink())
            self.assertEqual((runtime / "libfprint-2.so.2").readlink(),
                             Path("libfprint-2.so.2.0.0"))

    def test_15_success_audit_requires_match_telemetry(self):
        live = function_slice(self.kit, "run_d283_live ()", "export_d283_results ()")
        self.assertIn("$extract_count -eq 9", live)
        self.assertIn("$matcher_start_count -eq 1", live)
        self.assertIn("$matcher_match_count -eq 1", live)
        self.assertIn("$observed_max_score -ge 40", live)
        self.assertIn("SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE=RESIDUAL_RISK", live)

    def test_16_enrollment_confirmation_and_preaction_export(self):
        live = function_slice(self.kit, "run_d283_live ()", "export_d283_results ()")
        self.assertLess(live.index("ENROLL_PHYSICAL_FINGER_NOT_CONFIRMED"),
                        live.index("fprintd-enroll -f"))
        self.assertIn('D283_01_FAILURE_PHASE=PRE_SENSOR_PREFLIGHT', live)
        self.assertIn(': >"$live_result/operator.log"', live)
        export = function_slice(self.kit, "export_d283_results ()", "operator_d283_run ()")
        self.assertIn("NOT_AVAILABLE_BEFORE_RESULT_INITIALIZATION", export)
        self.assertIn("copy_d283_result_set", export)

    def test_17_progress_marker_is_not_a_failure_marker(self):
        live = function_slice(self.kit, "run_d283_live ()", "export_d283_results ()")
        staging = live.index("live_staging_started=true")
        after_staging = live[staging:live.index("install -d -m 0700", staging)]
        self.assertIn("D283_01_PROGRESS_PHASE=PRE_SENSOR_STAGING", after_staging)
        self.assertNotIn("echo D283_01_FAILURE_PHASE", after_staging)

    def test_17b_closed_live_entrypoints_refuse_before_candidate_or_staging(self):
        live = function_slice(self.kit, "run_d283_live ()", "export_d283_results ()")
        operator = function_slice(
            self.kit, "operator_d283_run ()", "offline_preflight ()")
        self.assertLess(live.index("D283_01_LIVE_CLOSED_DO_NOT_RERUN"),
                        live.index("live_result="))
        self.assertLess(operator.index("D283_01_LIVE_CLOSED_DO_NOT_RERUN"),
                        operator.index("prepare_d283_candidate"))
        self.assertIn("D283_01_LIVE_READINESS=CLOSED_DO_NOT_RERUN", self.kit)

    def test_18_hash_pinned_attempt_01_evidence(self):
        from analysis.D283.d283_01_attempt_01_evidence_audit import audit_capture
        audit_capture(CAPTURE)

    def test_19_evidence_audit_rejects_semantic_tampering(self):
        from analysis.D283.d283_01_attempt_01_evidence_audit import audit_capture
        with tempfile.TemporaryDirectory(prefix="goodix-d283-evidence-") as td:
            copy = Path(td)
            for source in CAPTURE.iterdir():
                (copy / source.name).write_bytes(source.read_bytes())
            summary = copy / "summary.env"
            summary.write_text(summary.read_text().replace(
                "OBSERVED_RETRY_COUNT=0", "OBSERVED_RETRY_COUNT=1"))
            with self.assertRaisesRegex(ValueError, "OBSERVED_RETRY_COUNT"):
                audit_capture(copy, enforce_hashes=False)


if __name__ == "__main__":
    unittest.main()
