#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import hashlib
import os
import pwd
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d287-01-kscreenlocker-testing"
SCRIPT = KIT / "run-d287-01.sh"
README = KIT / "README_IT.md"
REPORT = ROOT / "analysis/D287/D287_01_kscreenlocker_testing_boundary.md"
HOST_AUDIT = ROOT / "analysis/D287/D287_01_HOST_PATH_AUDIT.md"
SECOND_CAPTURE = (ROOT / "captures/D287_01" /
                  "D28701_ATTEMPT_20260911T210420Z_dc09bad49913/sanitized")


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
        cls.host_audit = HOST_AUDIT.read_text()

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
        (repo / "critical dir").mkdir()
        (repo / "critical dir/tracked file.txt").write_text("baseline\n")
        command = repo / "critical_command"
        command.write_text("#!/usr/bin/env bash\ntouch \"$PWD/GATE_COMMAND_EXECUTED\"\n")
        command.chmod(0o755)
        subprocess.run(["git", "-C", str(repo), "add", "critical", "critical dir",
                        "critical_command"], check=True)
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
        overlay = section(self.script, "d287_prepare_namespace_overlay ()",
                          "d287_start_greeter ()")
        self.assertIn('mount --bind "$staged_pam" /etc/pam.d/kde-fingerprint', overlay)
        self.assertNotIn('> /etc/pam.d/kde-fingerprint', self.script)
        self.assertNotIn('>"/etc/pam.d/kde-fingerprint"', self.script)
        self.assertNotIn('install -o root -g root -m 0644 "$d287_pam" /etc/pam.d', self.script)

    def test_11_each_attempt_uses_a_private_mount_namespace(self):
        series = section(self.script, "d287_root_series ()", "d287_operator_run ()")
        self.assertIn("unshare --mount --propagation private --fork --kill-child=KILL", series)
        self.assertIn("--root-namespace-attempt", series)

    def test_12_namespace_overlay_is_read_only_and_lifecycle_bounded(self):
        inner = section(self.script, "d287_root_namespace_attempt ()", "d287_root_series ()")
        validation = section(self.script, "d287_validate_namespace_context ()",
                             "d287_prepare_namespace_overlay ()")
        overlay = section(self.script, "d287_prepare_namespace_overlay ()",
                          "d287_start_greeter ()")
        cleanup = section(self.script, "d287_inner_cleanup ()", "d287_collect_journal ()")
        self.assertIn("mount -o remount,bind,ro", overlay)
        self.assertIn("PRIVATE_MOUNT_NAMESPACE_REQUIRED", validation)
        self.assertIn("PRIVATE_MOUNT_PROPAGATION_REQUIRED", validation)
        self.assertIn("PREEXISTING_PAM_MOUNTPOINT", validation)
        self.assertIn("mountpoint -q /etc/pam.d/kde-fingerprint", cleanup)
        self.assertIn("umount /etc/pam.d/kde-fingerprint", cleanup)
        self.assertIn("mount -t tmpfs", overlay)
        self.assertIn("nodev,nosuid,noexec,size=4m,mode=1777", overlay)
        self.assertIn('d287_namespace_tmp=/tmp/goodix-d287-01', self.script)
        self.assertIn('d287_tmp == "$d287_namespace_tmp"', cleanup)
        self.assertIn("umount /tmp", cleanup)
        self.assertIn("d287_inner_abort", self.script)
        self.assertIn("trap d287_inner_abort HUP INT TERM", inner)
        self.assertIn("D287_01_ATTEMPT_FAILURE=CLEANUP_FAILED", inner)
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
        validation = section(self.script, "d287_validate_namespace_context ()",
                             "d287_prepare_namespace_overlay ()")
        greeter = section(self.script, "d287_start_greeter ()",
                          "d287_root_namespace_attempt ()")
        for marker in ("/run/user/$uid", "^wayland-[0-9]+$",
                       'unix:path=$runtime/bus', "QT_QPA_PLATFORM=wayland"):
            self.assertIn(marker, validation + greeter)

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

    def _run_cursor_fixture(self, output: str, rc: int = 0) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="d287-cursor-") as tmp:
            mock = Path(tmp) / "journalctl"
            mock.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s' \"${D287_MOCK_JOURNAL_STDOUT-}\"\n"
                "printf '%s' \"${D287_MOCK_JOURNAL_STDERR-}\" >&2\n"
                "exit \"${D287_MOCK_JOURNAL_RC-0}\"\n")
            mock.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "PATH": f"{tmp}:{env['PATH']}",
                "D287_MOCK_JOURNAL_STDOUT": output,
                "D287_MOCK_JOURNAL_RC": str(rc),
            })
            command = 'D287_LIBRARY_ONLY=true; source "$1"; d287_current_cursor'
            return subprocess.run(["bash", "-c", command, "_", str(SCRIPT)],
                                  capture_output=True, text=True, env=env)

    def test_20_valid_global_boot_cursor_passes(self):
        cursor = ("s=1baebe3761b14b41ae621d6ed2cd2338;i=237231;"
                  "b=af986ce05fea4aaebd5e4d483b0a5c4f;m=6194f49d")
        result = self._run_cursor_fixture(f"-- No entries --\n-- cursor: {cursor}\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), cursor)

    def test_21_missing_cursor_has_specific_refusal(self):
        result = self._run_cursor_fixture("-- No entries --\n")
        self.assertEqual(result.returncode, 3)
        self.assertIn("D287_01_REFUSAL_REASON=JOURNAL_CURSOR_MISSING", result.stderr)

    def test_22_multiple_cursors_have_specific_refusal(self):
        result = self._run_cursor_fixture(
            "-- cursor: s=12345678901234567890\n"
            "-- cursor: s=abcdefghijklmnopqrst\n")
        self.assertEqual(result.returncode, 3)
        self.assertIn("D287_01_REFUSAL_REASON=JOURNAL_CURSOR_MULTIPLE", result.stderr)

    def test_23_malformed_cursor_is_refused(self):
        result = self._run_cursor_fixture("-- cursor: contains forbidden spaces\n")
        self.assertEqual(result.returncode, 3)
        self.assertIn("D287_01_REFUSAL_REASON=JOURNAL_CURSOR_INVALID", result.stderr)

    def test_24_journal_read_failure_is_distinct(self):
        result = self._run_cursor_fixture("", rc=1)
        self.assertEqual(result.returncode, 3)
        self.assertIn("D287_01_REFUSAL_REASON=JOURNAL_CURSOR_READ_FAILED", result.stderr)

    def test_25_collection_filters_fprintd_after_cursor_without_time_fallback(self):
        cursor = "s=12345678901234567890;i=42;b=abcdef0123456789"
        with tempfile.TemporaryDirectory(prefix="d287-collect-") as tmp:
            base = Path(tmp)
            args_file = base / "args"
            mock_dir = base / "bin"
            mock_dir.mkdir()
            mock = mock_dir / "journalctl"
            mock.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >\"$D287_MOCK_ARGS\"\n"
                "printf 'fixture journal line\\n'\n")
            mock.chmod(0o755)
            env = os.environ.copy()
            env.update({"PATH": f"{mock_dir}:{env['PATH']}",
                        "D287_MOCK_ARGS": str(args_file)})
            command = (
                'D287_LIBRARY_ONLY=true; source "$1"; d287_tmp=$2; '
                'd287_collect_journal "$3" "$2/journal.log"; cat "$2/journal.log"')
            result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                     str(base), cursor], capture_output=True, text=True,
                                    env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "fixture journal line\n")
            self.assertEqual(args_file.read_text().strip(),
                             f"-b -u fprintd.service --after-cursor {cursor} --no-pager")
            self.assertNotIn("--since", args_file.read_text())

    def test_26_safety_telemetry_is_fail_closed(self):
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

    def test_27_match_fixture_requires_clean_greeter_exit(self):
        result = self._classify("result=match matched_sample=1 comparisons=1 threshold=40",
                                0, "false")
        self.assertIn("D287_01_ATTEMPT_OUTCOME=MATCH", result.stdout)
        self.assertIn("CLASSIFY_RC=0", result.stdout)

    def test_28_no_match_fixture_requires_supervisor_termination(self):
        result = self._classify("result=no_match comparisons=8 threshold=40",
                                143, "true")
        self.assertIn("D287_01_ATTEMPT_OUTCOME=NO_MATCH", result.stdout)
        self.assertIn("CLASSIFY_RC=0", result.stdout)

    def test_29_hidden_second_epoch_is_a_safety_violation(self):
        extra = ("GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY attempts=1 "
                 "consumed=1 tls=1 secure_retry=0 post_retry=0 reopen=0 reset=0 "
                 "clear_halt=0 persistent=0 outstanding=0 drained=1 context_closed=1\n")
        result = self._classify("result=match matched_sample=1 comparisons=1 threshold=40",
                                0, "false", extra)
        self.assertIn("D287_01_ATTEMPT_OUTCOME=SAFETY_VIOLATION", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def test_30_match_with_nonzero_greeter_exit_is_rejected(self):
        result = self._classify("result=match matched_sample=1 comparisons=1 threshold=40",
                                1, "false")
        self.assertIn("D287_01_ATTEMPT_OUTCOME=PAM_ERROR", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def test_31_no_enroll_delete_restart_or_authselect_change(self):
        for forbidden in ("fprintd-enroll", "fprintd-delete", "fprintd-verify",
                          "systemctl restart", "authselect enable-feature",
                          "authselect disable-feature", "dnf install", "rpm -U"):
            self.assertNotIn(forbidden, self.script)

    def test_32_capture_is_sanitized_and_excludes_template_material(self):
        operator = section(self.script, "d287_operator_run ()", "d287_offline_preflight ()")
        self.assertIn("captures/D287_01", self.script)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", operator)
        for forbidden in ("D285_01_TEMPLATE_SHA256=", "/var/lib/fprint/"):
            self.assertNotIn(forbidden, operator)

    def test_33_offline_preflight_does_not_call_privileged_or_live_functions(self):
        offline = section(self.script, "d287_offline_preflight ()",
                          "if [[ ${D287_LIBRARY_ONLY")
        for forbidden in ("pkexec ", "unshare ", "mount ", "runuser ",
                          "d287_root_series", "d287_root_namespace_attempt",
                          "d287_count_goodix_targets"):
            self.assertNotIn(forbidden, offline)
        self.assertIn("d287_current_cursor", offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)

    def test_34_operator_mode_is_unprivileged_and_delegates_once(self):
        operator = section(self.script, "d287_operator_run ()", "d287_offline_preflight ()")
        self.assertIn("OPERATOR_MUST_BE_UNPRIVILEGED", operator)
        self.assertEqual(operator.count("pkexec "), 1)
        self.assertIn("--root-series", operator)

    def test_35_readme_closes_old_live_path_and_corrects_wayland_ux(self):
        for marker in ("CHIUSO — NON RILANCIARE", "fullscreen layer-shell",
                       "input tastiera esclusivo", "può non essere facilmente",
                       "POST_LIVE_POLKIT_CONTEXT_DEFECT_CLOSED_DO_NOT_RERUN",
                       "--operator-run"):
            self.assertIn(marker, self.readme)

    def test_36_methodological_review_answers_all_three_questions(self):
        for marker in ("Cosa cambia realmente", "Quale nuova ipotesi",
                       "Se fallisce nello stesso punto"):
            self.assertIn(marker, self.report)

    def test_37_upstream_provenance_compatibility_and_no_code_reuse_are_explicit(self):
        self.assertIn("28544d4910d5ea9be6708eb343804fa0018cb8e4", self.report)
        self.assertIn("057b3774d9ad322cfccc2683ea057aed87e0f878", self.report)
        self.assertIn("RELEVANT_GREETER_SOURCE_DIFF=EMPTY", self.report)
        self.assertIn("invent.kde.org/plasma/kscreenlocker.git", self.report)
        self.assertIn("Non è stato copiato o adattato", self.report)

    def test_38_noninteractive_failure_semantics_drive_fresh_process_retries(self):
        for marker in ("non riporta lo stato aggregato a `Idle`",
                       "tre processi", "max-tries=1"):
            self.assertIn(marker, self.report)

    def test_39_result_preserves_no_live_claim_and_records_aborted_run(self):
        result = (ROOT / "analysis/D287/D287_01_OFFLINE_RESULT.env").read_text()
        for marker in ("OUTCOME=READY_FOR_HUMAN_GATE",
                       "REAL_SESSION_LOCKED=false", "HOST_PAM_FILE_WRITE_COUNT=0",
                       "LIVE_EXECUTION=HUMAN_REQUIRED", "REAL_SENSOR_ACCESSED=false",
                       "LIVE_EXECUTION_PERFORMED=false",
                       "PRELIVE_OPERATOR_RUN=ABORTED_BEFORE_PRIVILEGE_AND_SENSOR",
                       "SENSOR_CONTACTS_CONSUMED=0",
                       "NEW_DEVICE_SIDE_EVIDENCE=false"):
            self.assertIn(marker, result)

    def test_40_process_group_cleanup_kills_a_term_resistant_fixture(self):
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

    def test_41_match_without_greeter_unlocked_marker_is_rejected(self):
        result = self._classify("result=match matched_sample=1 comparisons=1 threshold=40",
                                0, "false", unlocked="false")
        self.assertIn("D287_01_ATTEMPT_OUTCOME=PAM_ERROR", result.stdout)
        self.assertIn("CLASSIFY_RC=1", result.stdout)

    def _run_operator_scenario(self, scenario: str,
                               confirmations: str = "INDICE DESTRO\n") -> tuple[subprocess.CompletedProcess, list[Path]]:
        temp = tempfile.TemporaryDirectory(prefix="d287-host-path-")
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        command = r'''
set -euo pipefail
D287_LIBRARY_ONLY=true
source "$1"
d287_capture_root="$2/captures"
d287_mock_scenario=$3
d287_root=$4
d287_script_dir=$(dirname -- "$1")
d287_mock_attempt=0
d287_require_operator_context () { return 0; }
d287_require_root_context () { return 0; }
d287_verify_repo () {
  echo HARNESS_STAGE=repo_gate
  [[ $d287_mock_scenario != repo_dirty ]] || d287_refuse LIVE_CRITICAL_DIRTY
}
d287_validate_host_contract () {
  echo HARNESS_STAGE=host_contract
  [[ $d287_mock_scenario != host_drift ]] || d287_refuse KSCREENLOCKER_NEVRA_DRIFT
}
d287_require_polkit_password_path () { echo HARNESS_STAGE=polkit_contract; }
d287_check_no_existing_greeter () { echo HARNESS_STAGE=greeter_absence_gate; }
d287_count_goodix_targets () { echo 1; }
d287_run_d285_audit () {
  echo "HARNESS_STAGE=d285_audit_$1"
  echo D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES
}
d287_current_cursor () {
  echo HARNESS_STAGE=journal_cursor >&2
  echo 's=12345678901234567890;i=42;b=abcdef0123456789'
}
unshare () {
  [[ $1 == --mount && $2 == --propagation && $3 == private &&
     $4 == --fork && $5 == --kill-child=KILL && $7 == --root-namespace-attempt ]] ||
    return 91
  echo HARNESS_UNSHARE_CONTRACT=PASS
  d287_mock_attempt=$((d287_mock_attempt + 1))
  case $d287_mock_scenario:$d287_mock_attempt in
    no_match_then_match:1)
      echo D287_01_ATTEMPT_OUTCOME=NO_MATCH
      ;;
    greeter_not_ready:*)
      echo D287_01_ATTEMPT_OUTCOME=PAM_ERROR
      echo D287_01_ATTEMPT_FAILURE=GREETER_NOT_READY
      return 4
      ;;
    greeter_exited:*)
      echo D287_01_ATTEMPT_OUTCOME=PAM_ERROR
      echo D287_01_ATTEMPT_FAILURE=GREETER_EXITED_BEFORE_OUTCOME
      return 4
      ;;
    no_outcome:*)
      echo D287_01_ATTEMPT_OUTCOME=PAM_ERROR
      echo D287_01_ATTEMPT_FAILURE=JOURNAL_OUTCOME_TIMEOUT
      return 4
      ;;
    cleanup_failure:*)
      echo D287_01_ATTEMPT_OUTCOME=PAM_ERROR
      echo D287_01_ATTEMPT_FAILURE=CLEANUP_FAILED
      return 4
      ;;
    safety_violation:*)
      echo D287_01_ATTEMPT_OUTCOME=SAFETY_VIOLATION
      return 4
      ;;
    *)
      echo D287_01_ATTEMPT_OUTCOME=MATCH
      ;;
  esac
}
pkexec () {
  echo HARNESS_STAGE=pkexec_handoff
  [[ $1 == "$d287_script_dir/run-d287-01.sh" && $2 == --root-series ]] || return 92
  shift 2
  d287_root_series "$@"
  local root_rc=$?
  if [[ $d287_mock_scenario == multiple_result ]]; then
    echo D287_01_SERIES_RESULT=INJECTED_SECOND_RESULT
  fi
  return "$root_rc"
}
if [[ $d287_mock_scenario == tee_failure ]]; then
  tee () { command tee "$@"; return 1; }
fi
export XDG_SESSION_TYPE=wayland XDG_RUNTIME_DIR="/run/user/$(id -u)"
export WAYLAND_DISPLAY=wayland-0 DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
d287_operator_run
'''
        result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                 str(base), scenario, str(ROOT)], input=confirmations,
                                capture_output=True, text=True, timeout=10)
        summaries = list((base / "captures").glob("*/sanitized/summary.env"))
        return result, summaries

    def _run_inner_scenario(self, scenario: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="d287-inner-") as tmp:
            command = r'''
set -euo pipefail
D287_LIBRARY_ONLY=true
source "$1"
d287_harness_dir=$2
d287_harness_scenario=$3
d287_require_root_context () { return 0; }
d287_validate_namespace_context () { return 0; }
d287_prepare_namespace_overlay () {
  d287_tmp=
  d287_greeter_log="$d287_harness_dir/greeter.log"
  d287_journal_log="$d287_harness_dir/journal.log"
  : >"$d287_greeter_log"
  : >"$d287_journal_log"
}
d287_start_greeter () {
  case $d287_harness_scenario in
    greeter_not_ready) bash -c 'exit 1' >"$d287_greeter_log" 2>&1 & ;;
    greeter_exited) bash -c 'echo "Locked at fixture"; exit 1' >"$d287_greeter_log" 2>&1 & ;;
    no_outcome|no_match) bash -c 'echo "Locked at fixture"; sleep 30' >"$d287_greeter_log" 2>&1 & ;;
    *) bash -c 'echo "Locked at fixture"; echo Unlocked' >"$d287_greeter_log" 2>&1 & ;;
  esac
  d287_greeter_pgid=$!
}
d287_collect_journal () {
  if [[ $d287_harness_scenario == match || $d287_harness_scenario == cleanup_failure ]]; then
    printf '%s\n' \
      'GOODIX_SIGFM_EXTRACT_AUDIT keypoints=160' \
      'GOODIX_SIGFM_MATCH_AUDIT event=start template_samples=8 threshold=40' \
      'GOODIX_SIGFM_MATCH_AUDIT event=comparison sample=1 score=75 threshold=40' \
      'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match matched_sample=1 comparisons=1 threshold=40' \
      'GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY attempts=1 rejected=0 consumed=1 tls=1 real_submit=76 secure_retry=0 post_retry=0 reopen=0 reset=0 clear_halt=0 persistent=0 outstanding=0 drained=1 context_closed=1' >"$2"
  elif [[ $d287_harness_scenario == no_match ]]; then
    printf '%s\n' \
      'GOODIX_SIGFM_EXTRACT_AUDIT keypoints=160' \
      'GOODIX_SIGFM_MATCH_AUDIT event=start template_samples=8 threshold=40' \
      'GOODIX_SIGFM_MATCH_AUDIT event=comparison sample=1 score=12 threshold=40' \
      'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=no_match comparisons=8 threshold=40' \
      'GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY attempts=1 rejected=0 consumed=1 tls=1 real_submit=76 secure_retry=0 post_retry=0 reopen=0 reset=0 clear_halt=0 persistent=0 outstanding=0 drained=1 context_closed=1' >"$2"
  else
    : >"$2"
  fi
}
if [[ $d287_harness_scenario == cleanup_failure ]]; then
  d287_inner_cleanup () { return 1; }
fi
d287_ready_timeout=1
d287_outcome_timeout=1
d287_match_exit_timeout=1
d287_termination_timeout=1
d287_epoch_poll_count=1
[[ $d287_harness_scenario != no_outcome ]] || d287_outcome_timeout=0
rc=0
if d287_root_namespace_attempt testuser 1000 /run/user/1000 wayland-0 \
  unix:path=/run/user/1000/bus 's=12345678901234567890;i=42;b=abcdef0123456789' 1; then
  rc=0
else
  rc=$?
fi
trap - EXIT HUP INT TERM
echo INNER_RC=$rc
exit 0
'''
            return subprocess.run(["bash", "-c", command, "_", str(SCRIPT), tmp,
                                   scenario], capture_output=True, text=True, timeout=5)

    def test_42_full_operator_happy_path_reaches_simulated_match_and_summary(self):
        result, summaries = self._run_operator_scenario("match")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HARNESS_UNSHARE_CONTRACT=PASS", result.stdout)
        self.assertIn("D287_01_SERIES_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW",
                      result.stdout)
        self.assertEqual(len(summaries), 1)
        summary = summaries[0].read_text()
        self.assertIn("D287_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW", summary)
        self.assertIn("D287_01_ROOT_SERIES_RETURN_CODE=0", summary)
        self.assertIn("D287_01_CAPTURE_TEE_RETURN_CODE=0", summary)

    def test_43_no_match_requires_explicit_second_confirmation(self):
        result, _ = self._run_operator_scenario(
            "no_match_then_match", "INDICE DESTRO\nTENTATIVO 2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D287_01_ATTEMPTS_PERFORMED=2", result.stdout)
        self.assertIn("D287_01_ATTEMPT_OUTCOMES=NO_MATCH,MATCH", result.stdout)
        self.assertIn("D287_01_MATCHED_ATTEMPT=2", result.stdout)

    def test_44_operator_repo_dirty_fails_before_host_or_pkexec(self):
        result, summaries = self._run_operator_scenario("repo_dirty")
        self.assertEqual(result.returncode, 3)
        self.assertIn("D287_01_REFUSAL_REASON=LIVE_CRITICAL_DIRTY", result.stderr)
        self.assertNotIn("HARNESS_STAGE=host_contract", result.stdout)
        self.assertNotIn("HARNESS_STAGE=pkexec_handoff", result.stdout)
        self.assertEqual(summaries, [])

    def test_45_operator_host_drift_fails_before_pkexec(self):
        result, summaries = self._run_operator_scenario("host_drift")
        self.assertEqual(result.returncode, 3)
        self.assertIn("D287_01_REFUSAL_REASON=KSCREENLOCKER_NEVRA_DRIFT", result.stderr)
        self.assertNotIn("HARNESS_STAGE=pkexec_handoff", result.stdout)
        self.assertEqual(summaries, [])

    def test_46_actual_inner_control_flow_reports_greeter_not_ready(self):
        result = self._run_inner_scenario("greeter_not_ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D287_01_ATTEMPT_FAILURE=GREETER_NOT_READY", result.stdout)
        self.assertIn("INNER_RC=4", result.stdout)

    def test_47_actual_inner_control_flow_reports_unexpected_greeter_exit(self):
        result = self._run_inner_scenario("greeter_exited")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D287_01_ATTEMPT_FAILURE=GREETER_EXITED_BEFORE_OUTCOME", result.stdout)
        self.assertIn("D287_01_ATTEMPT_OUTCOME=PAM_ERROR", result.stdout)
        self.assertIn("INNER_RC=4", result.stdout)

    def test_48_actual_inner_control_flow_reports_journal_outcome_timeout(self):
        result = self._run_inner_scenario("no_outcome")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D287_01_ATTEMPT_FAILURE=JOURNAL_OUTCOME_TIMEOUT", result.stdout)
        self.assertIn("INNER_RC=4", result.stdout)

    def test_49_actual_inner_control_flow_does_not_mask_cleanup_failure(self):
        result = self._run_inner_scenario("cleanup_failure")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D287_01_ATTEMPT_FAILURE=CLEANUP_FAILED", result.stderr)
        self.assertIn("INNER_RC=4", result.stdout)

    def test_50_root_failure_propagates_to_operator_summary_and_exit(self):
        result, summaries = self._run_operator_scenario("greeter_not_ready")
        self.assertEqual(result.returncode, 4)
        self.assertIn("D287_01_ATTEMPT_FAILURE=GREETER_NOT_READY", result.stdout)
        self.assertEqual(len(summaries), 1)
        summary = summaries[0].read_text()
        self.assertIn("D287_01_RESULT=ROOT_SERIES_RESULT_MISSING_OR_MULTIPLE", summary)
        self.assertIn("D287_01_ROOT_SERIES_RETURN_CODE=3", summary)

    def test_51_multiple_root_results_are_rejected(self):
        result, summaries = self._run_operator_scenario("multiple_result")
        self.assertEqual(result.returncode, 4)
        self.assertEqual(len(summaries), 1)
        self.assertIn("D287_01_RESULT=ROOT_SERIES_RESULT_MISSING_OR_MULTIPLE",
                      summaries[0].read_text())

    def test_52_tee_failure_is_not_masked_by_successful_root_series(self):
        result, summaries = self._run_operator_scenario("tee_failure")
        self.assertEqual(result.returncode, 4)
        self.assertEqual(len(summaries), 1)
        summary = summaries[0].read_text()
        self.assertIn("D287_01_RESULT=CAPTURE_TEE_FAILED", summary)
        self.assertIn("D287_01_CAPTURE_TEE_RETURN_CODE=1", summary)

    def test_53_repository_status_read_failure_is_fail_closed(self):
        baseline = "1" * 40
        with tempfile.TemporaryDirectory(prefix="d287-git-failure-") as tmp:
            mock = Path(tmp) / "git"
            mock.write_text(
                "#!/usr/bin/env bash\n"
                "case \"$*\" in\n"
                "  *'branch --show-current') echo development ;;\n"
                "  *'rev-parse HEAD') echo \"$D287_BASELINE\" ;;\n"
                "  *'rev-parse origin/development') echo \"$D287_BASELINE\" ;;\n"
                "  *'status --porcelain'*) exit 1 ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n")
            mock.chmod(0o755)
            env = os.environ.copy()
            env.update({"PATH": f"{tmp}:{env['PATH']}", "D287_BASELINE": baseline})
            command = (
                'D287_LIBRARY_ONLY=true; source "$1"; d287_root=/fixture; '
                'd287_critical=(critical); d287_verify_repo "$2"')
            result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT), baseline],
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 3)
            self.assertIn("D287_01_REFUSAL_REASON=REPOSITORY_STATUS_READ_FAILED",
                          result.stderr)

    def test_54_second_preverify_capture_is_hash_pinned_and_classified(self):
        expected = {
            "root-series.log": "c40543f6e62435224909ab7dc5ca1e709a043e63614728542395d64b129787e3",
            "summary.env": "ef4ed5d7d8970e37b53366181205885c40927bf2a7691e4afd63e651af3697ca",
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((SECOND_CAPTURE / name).read_bytes()).hexdigest(),
                             digest)
        root_log = (SECOND_CAPTURE / "root-series.log").read_text()
        summary = (SECOND_CAPTURE / "summary.env").read_text()
        self.assertIn("D286_01_D287_SERIES_PRE_ROOT_AUDIT_SENSOR_ACTION_COUNT=0",
                      root_log)
        self.assertIn("D287_01_REFUSAL_REASON=JOURNAL_CURSOR_AMBIGUOUS", root_log)
        self.assertNotIn("D287_01_GREETER_TESTING_MODE_READY=true", root_log)
        self.assertIn("D287_01_ROOT_SERIES_RETURN_CODE=3", summary)

    def test_55_horizontal_audit_classifies_every_operator_stage_and_residual(self):
        for marker in (
                "repo gate", "host contract", "polkit password path",
                "session environment validation", "capture creation",
                "pkexec handoff contract", "root-series revalidation",
                "target cardinality gate", "D285 root audit contract",
                "operator confirmation parsing", "journal cursor creation",
                "inner log creation", "unshare invocation construction",
                "namespace assumptions", "tmpfs staging assumptions",
                "PAM overlay path/hash assumptions", "greeter command construction",
                "greeter readiness detection", "journal collection",
                "MATCH / NO_MATCH detection", "greeter supervision/termination",
                "exit-code handling", "telemetry collection", "classification",
                "cleanup", "post-attempt host validation", "D285 post-audit contract",
                "next-attempt gating", "final result", "capture summary/hash"):
            self.assertIn(marker, self.host_audit)
        for marker in ("BEHAVIORALLY_TESTED_OFFLINE", "READ_ONLY_TARGET_VERIFIED",
                       "STATIC_ONLY_WITH_JUSTIFICATION", "REQUIRES_HUMAN_GATE",
                       "RESIDUAL_UNTESTABLE_BEFORE_HUMAN_RUN="):
            self.assertIn(marker, self.host_audit)

    def test_56_actual_inner_happy_match_control_flow_passes(self):
        result = self._run_inner_scenario("match")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D287_01_ATTEMPT_OUTCOME=MATCH", result.stdout)
        self.assertIn("INNER_RC=0", result.stdout)

    def test_57_actual_inner_no_match_is_supervisor_terminated_and_passes(self):
        result = self._run_inner_scenario("no_match")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D287_01_ATTEMPT_OUTCOME=NO_MATCH", result.stdout)
        self.assertIn("D287_01_ATTEMPT_SUPERVISOR_TERMINATED_GREETER=true",
                      result.stdout)
        self.assertIn("INNER_RC=0", result.stdout)

    def test_58_safety_violation_propagates_through_root_and_operator(self):
        result, summaries = self._run_operator_scenario("safety_violation")
        self.assertEqual(result.returncode, 4)
        self.assertIn("D287_01_ATTEMPT_OUTCOME=SAFETY_VIOLATION", result.stdout)
        self.assertEqual(len(summaries), 1)
        self.assertIn("D287_01_ROOT_SERIES_RETURN_CODE=3", summaries[0].read_text())

    def test_59_no_match_without_second_confirmation_cannot_retry(self):
        result, summaries = self._run_operator_scenario("no_match_then_match")
        self.assertEqual(result.returncode, 4)
        self.assertIn("D287_01_REFUSAL_REASON=OPERATOR_CONFIRMATION_READ_FAILED",
                      result.stdout)
        self.assertNotIn("D287_01_ATTEMPTS_PERFORMED=2", result.stdout)
        self.assertEqual(len(summaries), 1)

    def test_60_namespace_context_real_validator_passes_controlled_boundaries(self):
        command = r'''
D287_LIBRARY_ONLY=true
source "$1"
readlink () {
  [[ $1 == /proc/self/ns/mnt ]] && echo mnt:self || echo mnt:init
}
findmnt () { echo private; }
mountpoint () { return 1; }
d287_validate_namespace_context "$2" "$3" "/run/user/$3" "$4" \
  "unix:path=/run/user/$3/bus"
echo NAMESPACE_CONTEXT=PASS
'''
        result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                 os.environ.get("USER", "guido"), str(os.getuid()),
                                 os.environ.get("WAYLAND_DISPLAY", "wayland-0")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NAMESPACE_CONTEXT=PASS", result.stdout)

    def test_61_namespace_context_rejects_nonprivate_propagation(self):
        command = r'''
D287_LIBRARY_ONLY=true
source "$1"
readlink () {
  [[ $1 == /proc/self/ns/mnt ]] && echo mnt:self || echo mnt:init
}
findmnt () { echo shared; }
mountpoint () { return 1; }
d287_validate_namespace_context "$2" "$3" "/run/user/$3" "$4" \
  "unix:path=/run/user/$3/bus"
'''
        result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                 os.environ.get("USER", "guido"), str(os.getuid()),
                                 os.environ.get("WAYLAND_DISPLAY", "wayland-0")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)
        self.assertIn("D287_01_REFUSAL_REASON=PRIVATE_MOUNT_PROPAGATION_REQUIRED",
                      result.stderr)

    def test_62_overlay_staging_real_function_constructs_bounded_operations(self):
        with tempfile.TemporaryDirectory(prefix="d287-overlay-") as tmp:
            base = Path(tmp)
            calls = base / "calls"
            namespace_tmp = base / "namespace-tmp"
            command = r'''
D287_LIBRARY_ONLY=true
source "$1"
d287_namespace_tmp=$2
d287_pam=$3
export D287_CALLS=$4
mount () { printf 'mount %s\n' "$*" >>"$D287_CALLS"; }
install () {
  printf 'install %s\n' "$*" >>"$D287_CALLS"
  local args=("$@") count=$#
  cp "${args[$((count - 2))]}" "${args[$((count - 1))]}"
}
chcon () { printf 'chcon %s\n' "$*" >>"$D287_CALLS"; }
d287_verify_hash () { printf 'verify %s %s\n' "$1" "$2" >>"$D287_CALLS"; }
d287_prepare_namespace_overlay
printf 'TMP=%s ACTIVE=%s GREETER=%s JOURNAL=%s\n' "$d287_tmp" \
  "$d287_tmp_mount_active" "$d287_greeter_log" "$d287_journal_log"
'''
            result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                     str(namespace_tmp), str(KIT / "goodix-d287-01-kde-fingerprint.pam"),
                                     str(calls)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            operations = calls.read_text()
            expected_order = ("mount -t tmpfs", "install -o root -g root -m 0644",
                              "chcon --reference=/etc/pam.d/kde-fingerprint",
                              "mount --bind", "mount -o remount,bind,ro", "verify /etc/pam.d")
            positions = [operations.index(marker) for marker in expected_order]
            self.assertEqual(positions, sorted(positions))
            self.assertIn(f"TMP={namespace_tmp} ACTIVE=true", result.stdout)

    def test_63_real_greeter_builder_passes_exact_testing_environment_to_setsid(self):
        with tempfile.TemporaryDirectory(prefix="d287-greeter-build-") as tmp:
            args_file = Path(tmp) / "setsid.args"
            greeter_log = Path(tmp) / "greeter.log"
            command = r'''
D287_LIBRARY_ONLY=true
source "$1"
export D287_SETSID_ARGS=$2
d287_greeter_log=$3
setsid () { printf '%s\n' "$*" >"$D287_SETSID_ARGS"; }
d287_start_greeter "$4" /run/user/1000 wayland-0 unix:path=/run/user/1000/bus
wait "$d287_greeter_pgid"
'''
            user = pwd.getpwuid(os.getuid()).pw_name
            home = pwd.getpwuid(os.getuid()).pw_dir
            result = subprocess.run(["bash", "-c", command, "_", str(SCRIPT),
                                     str(args_file), str(greeter_log), user],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = args_file.read_text()
            for marker in (f"--wait runuser -u {user} -- env -i", f"HOME={home}",
                           "XDG_SESSION_TYPE=wayland",
                           "XDG_RUNTIME_DIR=/run/user/1000", "WAYLAND_DISPLAY=wayland-0",
                           "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
                           "QT_QPA_PLATFORM=wayland",
                           "/usr/libexec/kscreenlocker_greet --testing"):
                self.assertIn(marker, args)

    def test_64_repo_gate_handles_dirty_critical_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="d287-gate-spaces-") as tmp:
            repo, baseline = self._init_repo_gate_fixture(Path(tmp))
            (repo / "critical dir/tracked file.txt").write_text("modified\n")
            result = self._run_repo_gate(repo, baseline, "critical dir")
            self.assertEqual(result.returncode, 3)
            self.assertIn("D287_01_REFUSAL_REASON=LIVE_CRITICAL_DIRTY", result.stderr)

    def test_65_machine_result_satisfies_comprehensive_acceptance_contract(self):
        result = (ROOT / "analysis/D287/D287_01_OFFLINE_RESULT.env").read_text()
        for marker in (
                "D287_01_HOST_PATH_HORIZONTAL_AUDIT=PASS",
                "D287_01_JOURNAL_CURSOR_ROOT_CAUSE=KNOWN",
                "D287_01_JOURNAL_CURSOR_BEHAVIORAL_TESTS=PASS",
                "D287_01_FULL_OPERATOR_PATH_SIMULATION=PASS",
                "D287_01_SHELL_FAILURE_PROPAGATION_AUDIT=PASS",
                "D287_01_TARGET_READ_ONLY_ASSUMPTIONS=PASS",
                "D287_01_RESIDUAL_HOST_SIDE_UNKNOWN_FAILURES=NONE_KNOWN",
                "D287_01_SENSOR_CONTACTS_CONSUMED=0",
                "D287_01_NEW_DEVICE_SIDE_EVIDENCE=false",
                "D287_01_EXECUTABLE_CLOSURE=PASS_OFFLINE_HORIZONTAL",
                "D287_01_LIVE_EXECUTION=HUMAN_REQUIRED"):
            self.assertIn(marker, result)

    def test_66_post_live_operator_entrypoint_is_closed(self):
        result = subprocess.run(["bash", str(SCRIPT), "--operator-run"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)
        self.assertIn(
            "D287_01_REFUSAL_REASON=POST_LIVE_POLKIT_CONTEXT_DEFECT_CLOSED_DO_NOT_RERUN",
            result.stderr,
        )

    def test_67_post_live_capture_and_recovered_boundary_are_pinned(self):
        capture = ROOT / "captures/D287_01/D28701_ATTEMPT_20260911T213353Z_d0679cf9a725/sanitized"
        expected = {
            "root-series.log": "0147fc61bece845a8fcb39be0cab249186f4149f8a07b05fcb675da664563019",
            "summary.env": "46ef541179a979c38231cbb37224b08bf0d85b352b67a7d420f882c5bf33d938",
        }
        self.assertEqual({path.name for path in capture.iterdir()}, set(expected))
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((capture / name).read_bytes()).hexdigest(), digest)
        recovered = (ROOT / "analysis/D287/D287_01_POST_LIVE_RECOVERED_JOURNAL.log").read_text()
        for marker in (
            "New session 'c3' of user 'root' with class 'background-light'",
            "D287_01_GREETER_PROCESS_CGROUP=/user.slice/user-0.slice/session-c3.scope",
            "Authorization denied to :1.161 to call method 'ListEnrolledFingers'",
            "Not Authorized: net.reactivated.fprint.device.verify",
            "D287_01_FPRINTD_VERIFY_START_COUNT=0",
            "D287_01_GOODIX_VERIFY_EPOCH_COUNT=0",
        ):
            self.assertIn(marker, recovered)

    def test_68_post_live_normalization_records_replan_not_fingerprint_failure(self):
        normalized = (ROOT / "analysis/D287/D287_01_POST_LIVE_NORMALIZED.env").read_text()
        for marker in (
            "D287_01_POST_LIVE_OUTCOME=FAIL_HOST_POLKIT_CONTEXT_BEFORE_VERIFY",
            "D287_01_PAM_FPRINTD_INVOKED=true",
            "D287_01_FPRINTD_ACTIVATED=true",
            "D287_01_FPRINTD_LIST_ENROLLED_FINGERS=POLKIT_DENIED",
            "D287_01_FPRINTD_VERIFY_START_REACHED=false",
            "D287_01_SENSOR_ACTION_COUNT=0",
            "D287_01_FINGERPRINT_SUCCESS_NOT_PROVEN=true",
            "D287_01_EXECUTABLE_OBSERVABILITY_DEFECT=true",
            "D287_01_PM_DECISION=REPLAN",
        ):
            self.assertIn(marker, normalized)


if __name__ == "__main__":
    unittest.main()
