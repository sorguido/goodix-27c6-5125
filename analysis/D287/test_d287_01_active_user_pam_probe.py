# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d287-01-active-user-pam-probe"
SCRIPT = KIT / "run-d287-01-active-user-pam-probe.sh"
SOURCE = KIT / "pam-confdir-runner.c"
PAM = KIT / "goodix-d287-01-active-user.pam"
README = KIT / "README_IT.md"
BOUNDARY = ROOT / "analysis/D287/D287_01_active_user_pam_probe_boundary.md"
RESULT = ROOT / "analysis/D287/D287_01_ACTIVE_USER_PAM_PROBE_OFFLINE_RESULT.env"
PM_REVIEW = ROOT / "analysis/D287/D287_01_active_user_pam_probe_pm_review.md"


def section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


class ActiveUserPamProbeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT.read_text()
        cls.source = SOURCE.read_text()
        cls.pam = PAM.read_text()
        cls.readme = README.read_text()
        cls.boundary = BOUNDARY.read_text()
        cls.result = RESULT.read_text()
        cls.pm_review = PM_REVIEW.read_text()

    def test_01_shell_syntax_and_executable(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(os.access(SCRIPT, os.X_OK))

    def test_02_pam_is_one_absolute_bounded_module(self):
        active = [line for line in self.pam.splitlines()
                  if line.strip() and not line.startswith("#")]
        self.assertEqual(active, [
            "auth required /usr/lib64/security/pam_fprintd.so "
            "max-tries=1 timeout=45 debug"
        ])

    def test_03_source_and_pam_hashes_are_pinned(self):
        for path, variable in ((SOURCE, "d287p_source_sha"), (PAM, "d287p_pam_sha")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIn(f"{variable}={digest}", self.script)

    def test_04_runner_compiles_warning_as_error(self):
        with tempfile.TemporaryDirectory(prefix="d287-compile-") as tmp:
            result = subprocess.run([
                "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-Wl,--build-id=none", str(SOURCE), "-Wl,-l:libpam.so.0",
                "-o", str(Path(tmp) / "runner")
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = hashlib.sha256((Path(tmp) / "runner").read_bytes()).hexdigest()
            self.assertIn(f"d287p_runner_sha={digest}", self.script)

    def test_05_pkcheck_uses_exact_same_process_subject(self):
        main = self.source.split("int\nmain", 1)[1]
        for token in ("getpid ()", "read_start_time (&start_time)", "getuid ()",
                      '"%ld,%llu,%ld"', '"--process", subject',
                      '"net.reactivated.fprint.device.verify"'):
            self.assertIn(token, self.source)
        self.assertLess(main.index("check_exact_polkit_subject ()"),
                        main.index("pam_start_confdir (service"))

    def test_06_pkcheck_cannot_prompt_or_install_agent(self):
        self.assertNotIn("--allow-user-interaction", self.source)
        self.assertNotIn("--enable-internal-agent", self.source)
        self.assertNotIn("pkexec", self.source)
        self.assertIn("D287_01_PROBE_PAM_NOT_STARTED=true", self.source)

    def test_07_runner_refuses_root_and_has_one_authenticate(self):
        main = self.source.split("int\nmain", 1)[1]
        self.assertIn("getuid () == 0 || geteuid () == 0", main)
        self.assertEqual(main.count("pam_authenticate (handle, 0)"), 1)

    def test_08_runner_never_logs_pam_responses(self):
        self.assertIn('result[i].resp = strdup ("")', self.source)
        self.assertNotIn('fprintf (stderr, "PAM_RESPONSE', self.source)
        self.assertNotIn('printf ("PAM_RESPONSE', self.source)
        self.assertNotIn("PAM_AUTHTOK", self.source)

    def test_09_operator_pam_process_is_not_root_wrapped(self):
        series = section(self.script, "d287p_series ()", "d287p_operator_run ()")
        self.assertIn('"$d287p_tmp/pam-confdir-runner" --active-user-probe', series)
        for forbidden in ("runuser", "systemd-run", "kscreenlocker_greet", "unshare"):
            self.assertNotIn(forbidden, series)
        self.assertNotIn('pkexec "$d287p_tmp/pam-confdir-runner"', series)

    def test_10_privileges_are_confined_to_d286_audits(self):
        self.assertEqual(self.script.count('pkexec "$d287p_d286" --root-audit'), 1)
        self.assertFalse(any(line.strip().startswith("sudo ")
                             for line in self.script.splitlines()))
        self.assertIn("D287_ACTIVE_USER_PAM_PRE", self.script)
        self.assertIn("D287_ACTIVE_USER_PAM_POST", self.script)

    def test_11_session_context_is_fail_closed(self):
        for token in ("XDG_SESSION_TYPE", "XDG_RUNTIME_DIR", "WAYLAND_DISPLAY",
                      "DBUS_SESSION_BUS_ADDRESS", "/proc/self/cgroup",
                      "ROOT_BACKGROUND_SESSION_CONTEXT_DETECTED", "session-c"):
            self.assertIn(token, self.script)

    def test_12_polkit_policy_and_password_path_are_pinned(self):
        for token in ("FPRINTD_POLKIT_ALLOW_ACTIVE_DRIFT",
                      "POLKIT_PAM_FINGERPRINT_RECURSION",
                      "FPRINTD_POLKIT_POLICY_DRIFT", "PKCHECK_BINARY_DRIFT"):
            self.assertIn(token, self.script)

    def test_13_exactly_one_explicit_contact_contract(self):
        self.assertIn("D287_01_PROBE_MAX_VERIFY_ACTIONS=1", self.script)
        self.assertIn("D287_01_PROBE_MAX_PHYSICAL_CONTACTS=1", self.script)
        self.assertIn("INDICE DESTRO", self.script)
        self.assertIn("AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false", self.script)

    def test_14_no_mutating_or_persistent_command_family(self):
        for forbidden in ("fprintd-enroll", "fprintd-delete", "systemctl restart",
                          "authselect enable-feature", "authselect disable-feature",
                          "ClearApp", "IAP", "usbreset"):
            self.assertNotIn(forbidden, self.script)

    def test_15_preexisting_fprintd_and_target_cardinality_are_gated(self):
        self.assertIn("FPRINTD_ALREADY_ACTIVE", self.script)
        self.assertIn("FPRINTD_BECAME_ACTIVE_BEFORE_PROBE", self.script)
        self.assertIn("REAL_TARGET_CARDINALITY_NOT_ONE", self.script)

    def test_16_complete_journal_observability_uses_one_cursor(self):
        collect = section(self.script, "d287p_collect_journals ()", "d287p_field_sum ()")
        self.assertEqual(collect.count('--after-cursor "$cursor"'), 2)
        self.assertIn("-u fprintd.service", collect)
        self.assertIn("pam_fprintd", collect)
        self.assertIn("Authorization (denied|granted)", collect)
        self.assertIn("systemd-logind", collect)
        self.assertEqual(collect.count("--output=short-iso-precise"), 2)
        self.assertIn('--grep "$pattern"', collect)
        self.assertNotIn("diagnostic.raw", collect)
        self.assertNotIn("--since", collect)

    def test_17_capture_has_logs_summary_and_hash_manifest(self):
        for name in ("operator.log", "context.env", "pam-runner.log",
                     "pre-root-audit.log", "post-root-audit.log",
                     "fprintd-journal.log", "diagnostic-journal.log",
                     "classification.env", "summary.env", "capture.sha256"):
            self.assertIn(name, self.script + self.readme)
        self.assertIn('sed "s/$user/<USER>/g"', self.script)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", self.script)

    def test_18_interruption_still_reaches_collection_and_post_audit(self):
        series = section(self.script, "d287p_series ()", "d287p_operator_run ()")
        self.assertIn("D287_01_PROBE_OPERATOR_INTERRUPT_RECEIVED=true", series)
        self.assertIn("HUP INT TERM", series)
        self.assertIn("d287p_signal_safe_tee", series)
        self.assertIn("timeout --foreground --signal=TERM", series)
        self.assertLess(series.index("trap 'd287p_interrupted=true"),
                        series.index("d287p_collect_terminal_observability"))
        self.assertLess(series.index("d287p_collect_terminal_observability"),
                        series.index("D287_ACTIVE_USER_PAM_POST"))
        self.assertIn("OPERATOR_INTERRUPTED_AFTER_ACTION_START", series)
        operator = section(self.script, "d287p_operator_run ()", "d287p_offline_preflight ()")
        self.assertIn("D287_01_PROBE_OUTER_INTERRUPT_DEFERRED_FOR_CAPTURE=true", operator)
        self.assertIn("d287p_signal_safe_tee", operator)

    def _classify(self, runner: str, journal: str, runner_rc: int,
                  timeout_rc: int = 0) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="d287-classify-") as tmp:
            base = Path(tmp)
            runner_path = base / "runner.log"
            journal_path = base / "journal.log"
            runner_path.write_text(runner)
            journal_path.write_text(journal)
            command = (
                'D287_PROBE_LIBRARY_ONLY=true; source "$1"; set +e; '
                'd287p_classify "$2" "$3" "$4" "$5"; '
                'rc=$?; echo CLASSIFY_RC=$rc; exit 0')
            return subprocess.run([
                "bash", "-c", command, "_", str(SCRIPT), str(runner_path),
                str(journal_path), str(runner_rc), str(timeout_rc)
            ], capture_output=True, text=True, check=True)

    @staticmethod
    def _runner(auth_rc: int) -> str:
        return ("D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=PASS\n"
                "D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=0\n"
                f"D287_01_PROBE_PAM_AUTHENTICATE_RETURN_CODE={auth_rc}\n"
                "D287_01_PROBE_PAM_END_RETURN_CODE=0\n")

    @staticmethod
    def _journal(result: str) -> str:
        outcome = ("result=match matched_sample=1 comparisons=1 threshold=40"
                   if result == "match" else
                   "result=no_match comparisons=8 threshold=40")
        comparisons = 1 if result == "match" else 8
        lines = ["GOODIX_SIGFM_EXTRACT_AUDIT keypoints=160",
                 "GOODIX_SIGFM_MATCH_AUDIT event=start template_samples=8 threshold=40"]
        lines += [f"GOODIX_SIGFM_MATCH_AUDIT event=comparison sample={index} "
                  f"score={75 if result == 'match' else 12} threshold=40"
                  for index in range(1, comparisons + 1)]
        lines += [f"GOODIX_SIGFM_MATCH_AUDIT event=outcome {outcome}",
                  "GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY "
                  "attempts=1 rejected=0 consumed=1 tls=1 first_image=1 "
                  "real_submit=76 "
                  "secure_retry=0 post_retry=0 reopen=0 reset=0 clear_halt=0 "
                  "persistent=0 outstanding=0 drained=1 context_closed=1"]
        return "\n".join(lines) + "\n"

    def test_19_match_fixture(self):
        result = self._classify(self._runner(0), self._journal("match"), 0)
        self.assertIn("D287_01_PROBE_OUTCOME=MATCH_REACHED_VERIFY", result.stdout)
        self.assertIn("CLASSIFY_RC=0", result.stdout)

    def test_20_no_match_fixture(self):
        result = self._classify(self._runner(9), self._journal("no_match"), 1)
        self.assertIn("D287_01_PROBE_OUTCOME=NO_MATCH_REACHED_VERIFY", result.stdout)
        self.assertIn("CLASSIFY_RC=0", result.stdout)

    def test_21_polkit_preflight_failure_proves_pam_not_started(self):
        runner = ("D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=FAIL\n"
                  "D287_01_PROBE_PAM_NOT_STARTED=true\n")
        result = self._classify(runner, "", 3)
        self.assertIn("D287_01_PROBE_OUTCOME=POLKIT_PREFLIGHT_FAILED_BEFORE_PAM",
                      result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def test_22_fprintd_polkit_denial_is_distinct(self):
        journal = "Authorization denied net.reactivated.Fprint.Device.ListEnrolledFingers\n"
        result = self._classify(self._runner(9), journal, 1)
        self.assertIn("D287_01_PROBE_OUTCOME=FPRINTD_POLKIT_DENIED_BEFORE_VERIFY",
                      result.stdout)

    def test_23_second_epoch_is_safety_violation(self):
        journal = self._journal("match") + self._journal("match").splitlines()[-1] + "\n"
        result = self._classify(self._runner(0), journal, 0)
        self.assertIn("D287_01_PROBE_OUTCOME=SAFETY_VIOLATION", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def test_24_forbidden_counter_is_safety_violation(self):
        journal = self._journal("match").replace("reopen=0", "reopen=1")
        result = self._classify(self._runner(0), journal, 0)
        self.assertIn("D287_01_PROBE_OUTCOME=SAFETY_VIOLATION", result.stdout)

    def test_25_offline_preflight_cannot_enter_live_functions(self):
        offline = section(self.script, "d287p_offline_preflight ()", "if [[ ${D287_PROBE_LIBRARY_ONLY")
        self.assertIn("d287p_validate_static_contract", offline)
        self.assertIn("d287p_prepare_runner", offline)
        for forbidden in ("d287p_validate_user_session", "d287p_count_goodix_targets",
                          "d287p_root_audit", "d287p_collect_journals", "pkcheck ",
                          "pkexec ", "--active-user-probe"):
            self.assertNotIn(forbidden, offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)
        self.assertIn("LIVE_EXECUTION_PERFORMED=false", offline)

    def test_26_historical_greeter_path_remains_closed(self):
        old = (ROOT / "operator_kit/d287-01-kscreenlocker-testing/run-d287-01.sh").read_text()
        self.assertIn("POST_LIVE_POLKIT_CONTEXT_DEFECT_CLOSED_DO_NOT_RERUN", old)
        self.assertIn("HISTORICAL_GREETER_PATH_NOT_CLOSED", self.script)

    def test_27_readme_has_one_command_and_stop_conditions(self):
        for token in ("Unica esecuzione manuale consentita", "non rilanciare",
                      "INDICE DESTRO", "Ctrl-C", "D287_01_PROBE_CAPTURE_DIRECTORY"):
            self.assertIn(token, self.readme)

    def test_28_methodological_questions_are_answered(self):
        for token in ("Cosa cambia realmente?", "Quale nuova ipotesi viene testata?",
                      "Se fallisce nello stesso punto?"):
            self.assertIn(token, self.boundary)

    def test_29_no_secret_or_biometric_payload_export(self):
        capture = section(self.script, "d287p_collect_journals ()", "d287p_field_sum ()")
        for forbidden in ("/var/lib/fprint", "PSK", "template_samples.bin",
                          "password=", "PAM_AUTHTOK"):
            self.assertNotIn(forbidden, capture)

    def test_30_empty_evidence_is_not_mislabeled_as_polkit_failure(self):
        result = self._classify("", "", 1)
        self.assertIn("D287_01_PROBE_OUTCOME=PAM_ERROR", result.stdout)
        self.assertNotIn("POLKIT_PREFLIGHT_FAILED_BEFORE_PAM", result.stdout)

    def test_31_incoherent_comparison_count_is_rejected(self):
        journal = self._journal("match").replace("comparisons=1", "comparisons=2")
        result = self._classify(self._runner(0), journal, 0)
        self.assertIn("D287_01_PROBE_OUTCOME=PAM_ERROR", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def test_32_non_verify_epoch_is_a_safety_violation(self):
        journal = self._journal("match").replace(
            "action=FPI_DEVICE_ACTION_VERIFY", "action=FPI_DEVICE_ACTION_ENROLL")
        result = self._classify(self._runner(0), journal, 0)
        self.assertIn("D287_01_PROBE_OUTCOME=SAFETY_VIOLATION", result.stdout)

    def test_33_timeout_cannot_be_accepted_as_match(self):
        result = self._classify(self._runner(0), self._journal("match"), 124, 124)
        self.assertIn("D287_01_PROBE_OUTCOME=PAM_ERROR", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def _series_fixture(self, runner: str, runner_rc: int,
                        journal: str) -> tuple[subprocess.CompletedProcess[str], Path, tempfile.TemporaryDirectory]:
        holder = tempfile.TemporaryDirectory(prefix="d287-series-")
        base = Path(holder.name)
        runtime = base / "runtime"
        capture = base / "capture"
        runtime.mkdir()
        capture.mkdir()
        binary = runtime / "pam-confdir-runner"
        binary.write_text("#!/usr/bin/env bash\n" + runner + f"exit {runner_rc}\n")
        binary.chmod(0o700)
        journal_path = base / "journal.fixture"
        journal_path.write_text(journal)
        command = r'''
D287_PROBE_LIBRARY_ONLY=true
source "$1"
d287_fixture_runtime=$2
d287_fixture_journal=$3
d287p_verify_repo () { :; }
d287p_validate_static_contract () { :; }
d287p_validate_user_session () { echo /user.slice/user-65534.slice/session-9.scope; }
d287p_count_goodix_targets () { echo 1; }
d287p_prepare_runner () { d287p_tmp=$d287_fixture_runtime; mkdir -p "$d287p_tmp/pam.d"; }
d287p_cleanup () { d287p_tmp=; return 0; }
d287p_root_audit () { echo D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES >"$3"; }
d287p_current_cursor () { echo 's=12345678901234567890;i=42;b=abcdef0123456789'; }
d287p_collect_terminal_observability () {
  cp "$d287_fixture_journal" "$2/diagnostic-journal.log"
  cp "$d287_fixture_journal" "$2/fprintd-journal.log"
}
pgrep () { return 1; }
rc=0
d287p_series 0123456789012345678901234567890123456789 nobody 65534 "$4" <<<"INDICE DESTRO" || rc=$?
echo SERIES_RC=$rc
exit 0
'''
        result = subprocess.run([
            "bash", "-c", command, "_", str(SCRIPT), str(runtime),
            str(journal_path), str(capture)
        ], capture_output=True, text=True, check=True)
        return result, capture, holder

    def test_34_full_series_fixture_reaches_one_match_and_post_audit(self):
        runner = ("echo D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=PASS\n"
                  "echo D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=0\n"
                  "echo D287_01_PROBE_PAM_AUTHENTICATE_RETURN_CODE=0\n"
                  "echo D287_01_PROBE_PAM_END_RETURN_CODE=0\n")
        result, capture, holder = self._series_fixture(
            runner, 0, self._journal("match"))
        try:
            self.assertIn("D287_01_PROBE_OUTCOME=MATCH_REACHED_VERIFY", result.stdout)
            self.assertIn("D287_01_PROBE_SERIES_RESULT=PROBE_REACHED_VERIFY_PENDING_INDEPENDENT_REVIEW",
                          result.stdout)
            self.assertIn("SERIES_RC=0", result.stdout)
            for name in ("pre-root-audit.log", "post-root-audit.log",
                         "pam-runner.log", "classification.env",
                         "diagnostic-journal.log", "fprintd-journal.log"):
                self.assertTrue((capture / name).is_file(), name)
        finally:
            holder.cleanup()

    def test_35_full_series_pkcheck_failure_stops_before_pam_and_still_audits(self):
        runner = ("echo D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=FAIL\n"
                  "echo D287_01_PROBE_PAM_NOT_STARTED=true\n")
        result, capture, holder = self._series_fixture(runner, 3, "")
        try:
            self.assertIn("D287_01_PROBE_OUTCOME=POLKIT_PREFLIGHT_FAILED_BEFORE_PAM",
                          result.stdout)
            self.assertIn("D287_01_PROBE_SERIES_RESULT=FAIL_LIVE_PENDING_INDEPENDENT_REVIEW",
                          result.stdout)
            self.assertIn("SERIES_RC=1", result.stdout)
            self.assertNotIn("PAM_START_CONFDIR_RETURN_CODE", (capture / "pam-runner.log").read_text())
            self.assertTrue((capture / "post-root-audit.log").is_file())
        finally:
            holder.cleanup()

    def test_36_operator_wrapper_persists_summary_and_manifest(self):
        with tempfile.TemporaryDirectory(prefix="d287-operator-") as tmp:
            command = r'''
D287_PROBE_LIBRARY_ONLY=true
source "$1"
d287p_capture_root=$2
d287p_root=$3
d287p_verify_repo () { :; }
d287p_series () {
  echo D287_01_PROBE_SERIES_RESULT=PROBE_REACHED_VERIFY_PENDING_INDEPENDENT_REVIEW
  return 0
}
d287p_operator_run
'''
            result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT), tmp,
                                     str(ROOT)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            captures = list(Path(tmp).glob("*/sanitized"))
            self.assertEqual(len(captures), 1)
            capture = captures[0]
            self.assertIn("D287_01_PROBE_RESULT=PROBE_REACHED_VERIFY_PENDING_INDEPENDENT_REVIEW",
                          (capture / "summary.env").read_text())
            manifest = (capture / "capture.sha256").read_text()
            self.assertIn("operator.log", manifest)
            self.assertIn("summary.env", manifest)

    def test_37_repository_gate_passes_clean_and_refuses_dirty_critical_file(self):
        with tempfile.TemporaryDirectory(prefix="d287-git-") as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "development", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "fixture"], check=True)
            (repo / "critical").write_text("clean\n")
            subprocess.run(["git", "-C", str(repo), "add", "critical"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
            head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/development", head], check=True)
            command = (
                'D287_PROBE_LIBRARY_ONLY=true; source "$1"; '
                'd287p_root=$2; d287p_critical=(critical); d287p_verify_repo "$3"')
            clean = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                    str(repo), head], capture_output=True, text=True)
            self.assertEqual(clean.returncode, 0, clean.stderr)
            (repo / "critical").write_text("dirty\n")
            result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                     str(repo), head], capture_output=True, text=True)
            self.assertEqual(result.returncode, 3)
            self.assertIn("D287_01_PROBE_REFUSAL_REASON=LIVE_CRITICAL_DIRTY",
                          result.stderr)

    def test_38_real_sigint_keeps_export_and_post_audit_path_alive(self):
        with tempfile.TemporaryDirectory(prefix="d287-signal-") as tmp:
            base = Path(tmp)
            runtime = base / "runtime"
            capture = base / "capture"
            runtime.mkdir()
            capture.mkdir()
            binary = runtime / "pam-confdir-runner"
            binary.write_text(
                "#!/usr/bin/env bash\n"
                "echo D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=PASS\n"
                "echo D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=0\n"
                "sleep 30\n")
            binary.chmod(0o700)
            command = r'''
D287_PROBE_LIBRARY_ONLY=true
source "$1"
d287_fixture_runtime=$2
d287p_verify_repo () { :; }
d287p_validate_static_contract () { :; }
d287p_validate_user_session () { echo /user.slice/user-65534.slice/session-9.scope; }
d287p_count_goodix_targets () { echo 1; }
d287p_prepare_runner () { d287p_tmp=$d287_fixture_runtime; mkdir -p "$d287p_tmp/pam.d"; }
d287p_cleanup () { d287p_tmp=; return 0; }
d287p_root_audit () { echo D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES >"$3"; }
d287p_current_cursor () { echo 's=12345678901234567890;i=42;b=abcdef0123456789'; }
d287p_collect_terminal_observability () {
  : >"$2/diagnostic-journal.log"
  : >"$2/fprintd-journal.log"
}
pgrep () { return 1; }
rc=0
d287p_series 0123456789012345678901234567890123456789 nobody 65534 "$3" || rc=$?
echo SERIES_RC=$rc
exit 0
'''
            process = subprocess.Popen(
                ["bash", "-c", command, "_", str(SCRIPT), str(runtime), str(capture)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True)
            assert process.stdin is not None
            process.stdin.write("INDICE DESTRO\n")
            process.stdin.flush()
            deadline = time.monotonic() + 5
            runner_log = capture / "pam-runner.log"
            while time.monotonic() < deadline:
                if runner_log.exists() and "PAM_START_CONFDIR" in runner_log.read_text():
                    break
                time.sleep(0.05)
            else:
                process.kill()
                self.fail("fixture runner did not reach the interruptible PAM phase")
            os.killpg(process.pid, signal.SIGINT)
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn("D287_01_PROBE_OPERATOR_INTERRUPT_RECEIVED=true", stdout)
            self.assertIn("D287_01_PROBE_SERIES_RESULT=OPERATOR_INTERRUPTED_AFTER_ACTION_START",
                          stdout)
            self.assertIn("SERIES_RC=1", stdout)
            self.assertTrue((capture / "diagnostic-journal.log").is_file())
            self.assertTrue((capture / "post-root-audit.log").is_file())

    def test_39_empty_filtered_journal_is_valid_but_read_error_is_not(self):
        with tempfile.TemporaryDirectory(prefix="d287-journal-") as tmp:
            base = Path(tmp)
            mock_dir = base / "bin"
            capture = base / "capture"
            runtime = base / "runtime"
            mock_dir.mkdir()
            capture.mkdir()
            runtime.mkdir()
            journalctl = mock_dir / "journalctl"
            journalctl.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ $* == *--grep* ]]; then\n"
                "  [[ -z ${D287_JOURNAL_ERROR:-} ]] || echo denied >&2\n"
                "  exit 1\n"
                "fi\n"
                "echo 'unit line for nobody'\n")
            journalctl.chmod(0o700)
            command = (
                'D287_PROBE_LIBRARY_ONLY=true; source "$1"; '
                'd287p_tmp=$2; d287p_collect_journals cursor "$3" nobody')
            env = os.environ.copy()
            env["PATH"] = f"{mock_dir}:{env['PATH']}"
            empty = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                    str(runtime), str(capture)], env=env,
                                   capture_output=True, text=True)
            self.assertEqual(empty.returncode, 0, empty.stderr)
            self.assertEqual((capture / "diagnostic-journal.log").read_text(), "")
            self.assertIn("<USER>", (capture / "fprintd-journal.log").read_text())
            env["D287_JOURNAL_ERROR"] = "true"
            failed = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                     str(runtime), str(capture)], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(failed.returncode, 1)
            self.assertIn("denied", failed.stderr)

    def test_40_operator_release_follows_positive_pm_review(self):
        self.assertIn("PM_DECISION=ACCEPT_AND_CONTINUE", self.pm_review)
        self.assertIn("Nessun finding resta aperto", self.pm_review)
        self.assertIn("OPERATOR_KIT_RELEASED=true", self.pm_review)
        self.assertIn("NEXT_STATE=HUMAN_REQUIRED", self.pm_review)
        self.assertIn("PM_DECISION=ACCEPT_AND_CONTINUE", self.boundary)
        self.assertIn("OPERATOR_KIT_RELEASED=true", self.result)
        self.assertIn("READY_FOR_HUMAN_OPERATOR", self.readme)

    def test_41_every_capture_pipeline_checks_producer_and_consumer(self):
        for token in ("runner_tee_rc=${pipeline_status[1]}",
                      "classification_tee_rc=${pipeline_status[1]}",
                      "unit_filter_rc=${pipeline_status[1]}",
                      "diagnostic_filter_rc=${pipeline_status[1]}",
                      "tee_rc=${pipeline_status[1]}"):
            self.assertIn(token, self.script)
        self.assertGreaterEqual(self.script.count('pipeline_status=("${PIPESTATUS[@]}")'), 5)
        self.assertIn("FAIL_RUNNER_CAPTURE", self.script)
        self.assertIn("FAIL_CLASSIFICATION_CAPTURE", self.script)

    def test_42_series_subprocess_owns_its_bounded_temp_cleanup(self):
        series = section(self.script, "d287p_series ()", "d287p_operator_run ()")
        self.assertIn("trap d287p_cleanup EXIT", series)
        self.assertIn("cleanup_rc=$?", series)
        self.assertIn("FAIL_TEMP_CLEANUP", series)
        self.assertLess(series.index("d287p_cleanup\n"),
                        series.index('echo "D287_01_PROBE_SERIES_RESULT=$final"'))


if __name__ == "__main__":
    unittest.main()
