#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d287-01-kscreenlocker-testing"
SCRIPT = KIT / "run-d287-01.sh"
README = KIT / "README_IT.md"
REPORT = ROOT / "analysis/D287/D287_01_kscreenlocker_testing_boundary.md"


def section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


class D287OfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text()
        cls.pam = (KIT / "goodix-d287-01-kde-fingerprint.pam").read_text()
        cls.readme = README.read_text()
        cls.report = REPORT.read_text()

    def test_01_shell_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_02_pam_is_exactly_one_explicit_fingerprint_try(self):
        active = [line for line in self.pam.splitlines()
                  if line and not line.startswith("#")]
        self.assertEqual(active,
                         ["auth required pam_fprintd.so max-tries=1 timeout=45"])

    def test_03_candidate_pam_hash_is_pinned(self):
        digest = hashlib.sha256((KIT / "goodix-d287-01-kde-fingerprint.pam").read_bytes()).hexdigest()
        self.assertIn(f"d287_expected_pam_sha={digest}", self.script)

    def test_04_target_versions_and_installed_hashes_are_pinned(self):
        host = section(self.script, "d287_validate_host_contract ()",
                       "d287_require_polkit_password_path ()")
        for marker in (
                "kscreenlocker-6.7.5-1.fc44.x86_64",
                "plasma-workspace-6.7.5-1.fc44.x86_64",
                "d287_expected_greeter_sha", "d287_expected_kde_pam_sha",
                "d287_expected_kde_fingerprint_sha", "d287_expected_lock_qml_sha"):
            self.assertIn(marker, host if marker.startswith("d287_") else self.script)

    def test_05_hard_coded_kde_fingerprint_service_is_checked(self):
        self.assertIn("strings -el /usr/libexec/kscreenlocker_greet", self.script)
        self.assertIn("grep -Fx kde-fingerprint", self.script)

    def test_06_repo_gate_requires_development_head_origin_and_clean_critical_set(self):
        gate = section(self.script, "d287_verify_repo ()", "d287_verify_hash ()")
        for marker in ("development", "rev-parse HEAD", "origin/development",
                       "status --porcelain --untracked-files=all", "d287_critical"):
            self.assertIn(marker, gate)

    def _init_repo_gate_fixture(self, base: Path) -> tuple[Path, str]:
        remote = base / "remote.git"
        repo = base / "repo"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "development", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "D287 test"],
                       check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email",
                        "d287-test@example.invalid"], check=True)
        (repo / "critical").mkdir()
        (repo / "critical/tracked.txt").write_text("baseline\n")
        command = repo / "critical_command"
        command.write_text("#!/usr/bin/env bash\ntouch \"$PWD/GATE_COMMAND_EXECUTED\"\n")
        command.chmod(0o755)
        subprocess.run(["git", "-C", str(repo), "add", "critical", "critical_command"],
                       check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"],
                       check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)],
                       check=True)
        subprocess.run(["git", "-C", str(repo), "push", "-q", "-u", "origin",
                        "development"], check=True)
        baseline = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout.strip()
        return repo, baseline

    def _run_repo_gate(self, repo: Path, baseline: str,
                       pathspec: str) -> subprocess.CompletedProcess:
        command = (
            'D287_LIBRARY_ONLY=true; source "$1"; d287_root=$2; '
            'cd "$d287_root"; d287_critical=("$3"); '
            'd287_verify_repo "$4"; echo GATE_PASS=true')
        return subprocess.run(["bash", "-c", command, "_", str(SCRIPT), str(repo),
                               pathspec, baseline], capture_output=True, text=True)

    def test_07_repo_gate_clean_pathspec_passes_without_command_execution(self):
        with tempfile.TemporaryDirectory(prefix="d287-gate-clean-") as tmp:
            repo, baseline = self._init_repo_gate_fixture(Path(tmp))
            result = self._run_repo_gate(repo, baseline, "./critical_command")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("GATE_PASS=true", result.stdout)
            self.assertFalse((repo / "GATE_COMMAND_EXECUTED").exists())

    def test_08_repo_gate_refuses_modified_tracked_critical_file(self):
        with tempfile.TemporaryDirectory(prefix="d287-gate-tracked-") as tmp:
            repo, baseline = self._init_repo_gate_fixture(Path(tmp))
            (repo / "critical/tracked.txt").write_text("modified\n")
            result = self._run_repo_gate(repo, baseline, "critical")
            self.assertEqual(result.returncode, 3)
            self.assertIn("D287_01_REFUSAL_REASON=LIVE_CRITICAL_DIRTY", result.stderr)

    def test_09_repo_gate_refuses_untracked_critical_file(self):
        with tempfile.TemporaryDirectory(prefix="d287-gate-untracked-") as tmp:
            repo, baseline = self._init_repo_gate_fixture(Path(tmp))
            (repo / "critical/untracked.txt").write_text("untracked\n")
            result = self._run_repo_gate(repo, baseline, "critical")
            self.assertEqual(result.returncode, 3)
            self.assertIn("D287_01_REFUSAL_REASON=LIVE_CRITICAL_DIRTY", result.stderr)

    def test_10_host_pam_is_overlaid_not_written(self):
        inner = section(self.script, "d287_root_namespace_attempt ()", "d287_root_series ()")
        self.assertIn('mount --bind "$staged_pam" /etc/pam.d/kde-fingerprint', inner)
        self.assertNotIn('> /etc/pam.d/kde-fingerprint', self.script)
        self.assertNotIn('>"/etc/pam.d/kde-fingerprint"', self.script)
        self.assertNotIn('install -o root -g root -m 0644 "$d287_pam" /etc/pam.d', self.script)

    def test_11_each_attempt_uses_a_private_mount_namespace(self):
        series = section(self.script, "d287_root_series ()", "d287_operator_run ()")
        self.assertIn("unshare --mount --propagation private --fork --kill-child=KILL", series)
        self.assertIn("--root-namespace-attempt", series)

    def test_12_namespace_overlay_is_read_only_and_lifecycle_bounded(self):
        inner = section(self.script, "d287_root_namespace_attempt ()", "d287_root_series ()")
        cleanup = section(self.script, "d287_inner_cleanup ()", "d287_collect_journal ()")
        self.assertIn("mount -o remount,bind,ro", inner)
        self.assertIn("PRIVATE_MOUNT_NAMESPACE_REQUIRED", inner)
        self.assertIn("PRIVATE_MOUNT_PROPAGATION_REQUIRED", inner)
        self.assertIn("PREEXISTING_PAM_MOUNTPOINT", inner)
        self.assertIn("mountpoint -q /etc/pam.d/kde-fingerprint", cleanup)
        self.assertIn("umount /etc/pam.d/kde-fingerprint", cleanup)
        self.assertIn("mount -t tmpfs", inner)
        self.assertIn("nodev,nosuid,noexec,size=4m,mode=1777", inner)
        self.assertIn("/tmp/goodix-d287-01", cleanup)
        self.assertIn("umount /tmp", cleanup)
        self.assertIn("d287_inner_abort", self.script)
        self.assertIn("trap d287_inner_abort HUP INT TERM", inner)
        self.assertIn("d287_inner_cleanup || return 4", inner)
        self.assertIn("trap - EXIT HUP INT TERM", inner)
        self.assertNotIn("rm -rf", cleanup)

    def test_13_only_testing_mode_invokes_the_real_greeter(self):
        invocations = [line.strip() for line in self.script.splitlines()
                       if "/usr/libexec/kscreenlocker_greet" in line]
        live = [line for line in invocations if line.startswith("/usr/libexec")]
        self.assertEqual(live, ["/usr/libexec/kscreenlocker_greet --testing >\"$d287_greeter_log\" 2>&1 &"])
        self.assertNotIn("--immediateLock", self.script)
        self.assertNotIn("loginctl lock-session", self.script)

    def test_14_wayland_and_session_bus_are_exactly_scoped(self):
        inner = section(self.script, "d287_root_namespace_attempt ()", "d287_root_series ()")
        for marker in ("/run/user/$uid", "^wayland-[0-9]+$",
                       'unix:path=$runtime/bus', "QT_QPA_PLATFORM=wayland"):
            self.assertIn(marker, inner)

    def test_15_existing_real_or_testing_greeter_is_a_gate(self):
        self.assertIn("EXISTING_KSCREENLOCKER_GREETER", self.script)
        series = section(self.script, "d287_root_series ()", "d287_operator_run ()")
        self.assertLess(series.index("d287_check_no_existing_greeter"),
                        series.index("for attempt in 1 2 3"))

    def test_16_d285_state_is_audited_before_and_after_every_attempt(self):
        series = section(self.script, "d287_root_series ()", "d287_operator_run ()")
        self.assertIn("d287_run_d285_audit D287_SERIES_PRE", series)
        self.assertIn('d287_run_d285_audit "D287_ATTEMPT_${attempt}_POST"', series)
        self.assertIn("UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES", self.script)

    def test_17_three_slots_require_separate_operator_confirmations(self):
        series = section(self.script, "d287_root_series ()", "d287_operator_run ()")
        self.assertIn("for attempt in 1 2 3", series)
        self.assertIn("INDICE DESTRO", series)
        self.assertIn('TENTATIVO $((attempt + 1))', series)
        self.assertIn("NEXT_ATTEMPT_NOT_CONFIRMED", series)

    def test_18_match_stops_the_series_immediately(self):
        series = section(self.script, "d287_root_series ()", "d287_operator_run ()")
        match = series[series.index("if [[ $outcome == MATCH ]]"):]
        self.assertLess(match.index("break"), match.index("NO_MATCH osservato"))
        self.assertIn("STOP_ON_FIRST_MATCH=true", series)

    def test_19_journal_boundary_is_cursor_based_and_locale_independent(self):
        cursor = section(self.script, "d287_current_cursor ()", "d287_check_no_existing_greeter ()")
        collect = section(self.script, "d287_collect_journal ()", "d287_classify_attempt ()")
        self.assertIn("--show-cursor", cursor)
        self.assertIn("LC_ALL=C", cursor)
        self.assertIn('--after-cursor "$cursor"', collect)
        self.assertNotIn("--since", self.script)

    def test_20_safety_telemetry_is_fail_closed(self):
        audit = section(self.script, "d287_classify_attempt ()",
                        "d287_root_namespace_attempt ()")
        for marker in ("$total_epoch_count -gt 1", "$retry_count -ne 0",
                       "$reopen_count -ne 0", "$reset_count -ne 0",
                       "$clear_halt_count -ne 0", "$persistent_count -ne 0",
                       "SAFETY_VIOLATION"):
            self.assertIn(marker, audit)

    def _classify(self, outcome_line: str, greeter_rc: int,
                  supervisor: str, extra_epoch: str = "",
                  unlocked: str | None = None) -> subprocess.CompletedProcess:
        if unlocked is None:
            unlocked = "true" if "result=match " in outcome_line else "false"
        fixture = (
            "GOODIX_SIGFM_EXTRACT_AUDIT keypoints=160\n"
            "GOODIX_SIGFM_MATCH_AUDIT event=start template_samples=8 threshold=40\n"
            "GOODIX_SIGFM_MATCH_AUDIT event=comparison sample=1 score=75 threshold=40\n"
            f"GOODIX_SIGFM_MATCH_AUDIT event=outcome {outcome_line}\n"
            "GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY attempts=1 "
            "rejected=0 consumed=1 tls=1 real_submit=76 secure_retry=0 post_retry=0 "
            "reopen=0 reset=0 clear_halt=0 persistent=0 outstanding=0 drained=1 "
            "context_closed=1\n" + extra_epoch
        )
        with tempfile.NamedTemporaryFile("w", prefix="d287-journal-", delete=False) as handle:
            path = Path(handle.name)
            handle.write(fixture)
        try:
            command = (
                'D287_LIBRARY_ONLY=true; source "$1"; set +e; '
                'd287_classify_attempt "$2" 1 "$3" "$4" "$5"; '
                'rc=$?; echo CLASSIFY_RC=$rc; exit 0')
            return subprocess.run(["bash", "-c", command, "_", str(SCRIPT), str(path),
                                   str(greeter_rc), supervisor, unlocked], check=True,
                                  capture_output=True, text=True)
        finally:
            path.unlink()

    def test_21_match_fixture_requires_clean_greeter_exit(self):
        result = self._classify("result=match matched_sample=1 comparisons=1 threshold=40",
                                0, "false")
        self.assertIn("D287_01_ATTEMPT_OUTCOME=MATCH", result.stdout)
        self.assertIn("CLASSIFY_RC=0", result.stdout)

    def test_22_no_match_fixture_requires_supervisor_termination(self):
        result = self._classify("result=no_match comparisons=8 threshold=40",
                                143, "true")
        self.assertIn("D287_01_ATTEMPT_OUTCOME=NO_MATCH", result.stdout)
        self.assertIn("CLASSIFY_RC=0", result.stdout)

    def test_23_hidden_second_epoch_is_a_safety_violation(self):
        extra = ("GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY attempts=1 "
                 "consumed=1 tls=1 secure_retry=0 post_retry=0 reopen=0 reset=0 "
                 "clear_halt=0 persistent=0 outstanding=0 drained=1 context_closed=1\n")
        result = self._classify("result=match matched_sample=1 comparisons=1 threshold=40",
                                0, "false", extra)
        self.assertIn("D287_01_ATTEMPT_OUTCOME=SAFETY_VIOLATION", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def test_24_match_with_nonzero_greeter_exit_is_rejected(self):
        result = self._classify("result=match matched_sample=1 comparisons=1 threshold=40",
                                1, "false")
        self.assertIn("D287_01_ATTEMPT_OUTCOME=PAM_ERROR", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def test_25_no_enroll_delete_restart_or_authselect_change(self):
        for forbidden in ("fprintd-enroll", "fprintd-delete", "fprintd-verify",
                          "systemctl restart", "authselect enable-feature",
                          "authselect disable-feature", "dnf install", "rpm -U"):
            self.assertNotIn(forbidden, self.script)

    def test_26_capture_is_sanitized_and_excludes_template_material(self):
        operator = section(self.script, "d287_operator_run ()", "d287_offline_preflight ()")
        self.assertIn("captures/D287_01", self.script)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", operator)
        for forbidden in ("D285_01_TEMPLATE_SHA256=", "/var/lib/fprint/"):
            self.assertNotIn(forbidden, operator)

    def test_27_offline_preflight_does_not_call_privileged_or_live_functions(self):
        offline = section(self.script, "d287_offline_preflight ()",
                          "if [[ ${D287_LIBRARY_ONLY")
        for forbidden in ("pkexec ", "unshare ", "mount ", "runuser ",
                          "d287_root_series", "d287_root_namespace_attempt",
                          "d287_count_goodix_targets"):
            self.assertNotIn(forbidden, offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)

    def test_28_operator_mode_is_unprivileged_and_delegates_once(self):
        operator = section(self.script, "d287_operator_run ()", "d287_offline_preflight ()")
        self.assertIn("OPERATOR_MUST_BE_UNPRIVILEGED", operator)
        self.assertEqual(operator.count("pkexec "), 1)
        self.assertIn("--root-series", operator)

    def test_29_readme_has_human_gate_risk_stop_and_direct_command(self):
        for marker in ("HUMAN REQUIRED", "Ctrl-C", "non blocca la sessione",
                       "non rilanciare", "INDICE DESTRO", "TENTATIVO 2",
                       "TENTATIVO 3", "senza un quarto", "--operator-run"):
            self.assertIn(marker, self.readme)

    def test_30_methodological_review_answers_all_three_questions(self):
        for marker in ("Cosa cambia realmente", "Quale nuova ipotesi",
                       "Se fallisce nello stesso punto"):
            self.assertIn(marker, self.report)

    def test_31_upstream_provenance_compatibility_and_no_code_reuse_are_explicit(self):
        self.assertIn("28544d4910d5ea9be6708eb343804fa0018cb8e4", self.report)
        self.assertIn("057b3774d9ad322cfccc2683ea057aed87e0f878", self.report)
        self.assertIn("RELEVANT_GREETER_SOURCE_DIFF=EMPTY", self.report)
        self.assertIn("invent.kde.org/plasma/kscreenlocker.git", self.report)
        self.assertIn("Non è stato copiato o adattato", self.report)

    def test_32_noninteractive_failure_semantics_drive_fresh_process_retries(self):
        for marker in ("non riporta lo stato aggregato a `Idle`",
                       "tre processi", "max-tries=1"):
            self.assertIn(marker, self.report)

    def test_33_result_preserves_no_live_claim_and_records_aborted_run(self):
        result = (ROOT / "analysis/D287/D287_01_OFFLINE_RESULT.env").read_text()
        for marker in ("OUTCOME=READY_FOR_HUMAN_GATE",
                       "REAL_SESSION_LOCKED=false", "HOST_PAM_FILE_WRITE_COUNT=0",
                       "LIVE_EXECUTION=HUMAN_REQUIRED", "REAL_SENSOR_ACCESSED=false",
                       "LIVE_EXECUTION_PERFORMED=false",
                       "PRELIVE_OPERATOR_RUN=ABORTED_BEFORE_PRIVILEGE_AND_SENSOR",
                       "SENSOR_CONTACTS_CONSUMED=0",
                       "NEW_DEVICE_SIDE_EVIDENCE=false"):
            self.assertIn(marker, result)

    def test_34_process_group_cleanup_kills_a_term_resistant_fixture(self):
        command = (
            'D287_LIBRARY_ONLY=true; source "$1"; '
            "setsid --wait bash -c 'trap \"\" TERM; sleep 30 & wait' & "
            'd287_greeter_pgid=$!; sleep 0.1; '
            'd287_greeter_running; echo RUNNING_BEFORE=true; '
            'd287_inner_cleanup; '
            '[[ -z $d287_greeter_pgid ]]; echo CLEANUP_COMPLETE=true')
        result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT)],
                                check=True, capture_output=True, text=True, timeout=5)
        self.assertIn("RUNNING_BEFORE=true", result.stdout)
        self.assertIn("CLEANUP_COMPLETE=true", result.stdout)

    def test_35_match_without_greeter_unlocked_marker_is_rejected(self):
        result = self._classify("result=match matched_sample=1 comparisons=1 threshold=40",
                                0, "false", unlocked="false")
        self.assertIn("D287_01_ATTEMPT_OUTCOME=PAM_ERROR", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
