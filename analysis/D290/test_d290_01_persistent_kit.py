#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d290-01-plasmalogin-persistent-test"
OLD_EXP = ROOT / "operator_kit/live_probe/experiments/d290-plasmalogin"
SCRIPT = KIT / "run-d290-01.sh"
ORIGINAL = Path("/usr/lib/pam.d/plasmalogin").read_bytes()
CANDIDATE = (OLD_EXP / "goodix-d290-plasmalogin.pam").read_bytes()
BASELINE = "1" * 40
ARM_BOOT = "11111111-1111-4111-8111-111111111111"
CLOSE_BOOT = "22222222-2222-4222-8222-222222222222"


class PersistentFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="goodix-d290-test.", dir="/tmp")
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.host = self.base / "host"
        self.fake_bin = self.base / "bin"
        self.fixtures = self.base / "fixtures"
        self.restore_log = self.base / "restorecon.log"
        self.target = self.host / "usr/lib/pam.d/plasmalogin"
        self.state_dir = self.host / "etc/goodix-27c6-5125/d290-01-plasmalogin-persistent-test"
        self.env = os.environ.copy()
        self._build()

    def close(self):
        self.temp.cleanup()

    def write_executable(self, name, body):
        path = self.fake_bin / name
        path.write_text("#!/usr/bin/env bash\nset -u\n" + body)
        path.chmod(0o755)

    def _build(self):
        script_path = self.repo / "operator_kit/d290-01-plasmalogin-persistent-test/run-d290-01.sh"
        script_path.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, script_path)
        candidate_path = self.repo / "operator_kit/live_probe/experiments/d290-plasmalogin/goodix-d290-plasmalogin.pam"
        candidate_path.parent.mkdir(parents=True)
        candidate_path.write_bytes(CANDIDATE)
        d286 = self.repo / "operator_kit/d286-01-reboot-survival/run-d286-01.sh"
        d286.parent.mkdir(parents=True)
        d286.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' D286_01_STATE_COHERENCE=PASS_ROOT_ONLY "
            "D286_01_RUNTIME_INTEGRITY=PASS D286_01_PASSWORD_FALLBACK=PASS "
            "D286_01_TEMPLATE_OWNERSHIP=PASS_PINNED_EXACTLY_ONE\n"
        )
        d286.chmod(0o755)
        (self.repo / "captures").mkdir()

        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(ORIGINAL)
        self.target.chmod(0o644)
        password_auth = self.host / "etc/authselect/password-auth"
        password_auth.parent.mkdir(parents=True)
        password_auth.write_text("auth sufficient pam_unix.so nullok\n")
        module = self.host / "usr/lib64/security/pam_fprintd.so"
        module.parent.mkdir(parents=True)
        module.write_bytes(b"fixture\n")
        state_parent = self.host / "etc/goodix-27c6-5125"
        state_parent.mkdir(parents=True)
        boot = self.host / "proc/sys/kernel/random/boot_id"
        boot.parent.mkdir(parents=True)
        boot.write_text(ARM_BOOT + "\n")
        usb = self.base / "sys/bus/usb/devices/1-1"
        usb.mkdir(parents=True)
        (usb / "idVendor").write_text("27c6\n")
        (usb / "idProduct").write_text("5125\n")
        self.fake_bin.mkdir()
        self.fixtures.mkdir()
        (self.fixtures / "fprintd.log").write_text("")
        (self.fixtures / "plasmalogin.log").write_text("plasmalogin: session for guido\n")

        self.write_executable(
            "git",
            f"""
case " $* " in
  *" branch --show-current "*) echo development ;;
  *" rev-parse HEAD "*) echo {BASELINE} ;;
  *" rev-parse origin/development "*) echo {BASELINE} ;;
  *" status --porcelain "*) [[ ${{D290_TEST_GIT_DIRTY:-false}} != true ]] || echo ' M operator_kit/live_probe' ;;
  *" rev-parse --show-toplevel "*) echo "$D290_TEST_ROOT/repo" ;;
  *) exit 2 ;;
esac
""",
        )
        self.write_executable(
            "rpm",
            """
case ${1:-} in
  -q|-qf) echo plasma-login-manager-6.7.5-1.fc44.x86_64 ;;
  -V)
    if [[ ${D290_TEST_RPM_VERIFY_ERROR:-false} == true ]]; then
      echo 'rpm database error' >&2
      exit 2
    elif [[ ${D290_TEST_RPM_TARGET_DRIFT:-false} == true ]]; then
      echo "S.5....T.  $D290_TEST_TARGET"
      exit 1
    fi
    ;;
  *) exit 2 ;;
esac
""",
        )
        self.write_executable(
            "restorecon",
            """
echo "$*" >>"$D290_TEST_RESTORE_LOG"
if [[ ${D290_TEST_RESTORECON_FAIL_ONCE:-false} == true && "$*" == "$D290_TEST_TARGET" && ! -e $D290_TEST_ROOT/restorecon.failed ]]; then
  : >$D290_TEST_ROOT/restorecon.failed
  exit 1
fi
""",
        )
        self.write_executable(
            "matchpathcon",
            'printf \'%s\\n\' "${D290_TEST_POLICY_CONTEXT:-$D290_TEST_CONTEXT}"\n',
        )
        self.write_executable("mountpoint", "exit 1\n")
        self.write_executable("pgrep", "exit 1\n")
        self.write_executable(
            "journalctl",
            """
[[ ${D290_TEST_JOURNAL_FAIL:-false} != true ]] || exit 1
case " $* " in
  *" fprintd.service "*) cat "$D290_TEST_FIXTURES/fprintd.log" ;;
  *" plasmalogin.service "*) cat "$D290_TEST_FIXTURES/plasmalogin.log" ;;
  *) exit 2 ;;
esac
""",
        )
        self.write_executable(
            "loginctl",
            """
if [[ ${1:-} == list-sessions ]]; then
  echo "7 $(id -u) fixture seat0 1 user tty2 no -"
elif [[ ${1:-} == show-session && ${3:-} == -p ]]; then
  case ${4:-} in
    Service) echo plasmalogin ;;
    Type) echo wayland ;;
    Class) echo user ;;
    State) echo active ;;
    TTY) echo tty2 ;;
    *) exit 2 ;;
  esac
else
  exit 2
fi
""",
        )
        self.env.update(
            {
                "PATH": f"{self.fake_bin}:/usr/bin:/bin",
                "D290_TEST_ROOT": str(self.base),
                "D290_TEST_CONTEXT": "system_u:object_r:lib_t:s0",
                "D290_TEST_FIXTURES": str(self.fixtures),
                "D290_TEST_RESTORE_LOG": str(self.restore_log),
                "D290_TEST_TARGET": str(self.target),
            }
        )
        self.script = script_path

    def run(self, mode, **env):
        merged = self.env.copy()
        merged.update({key: str(value) for key, value in env.items()})
        return subprocess.run(
            [str(self.script), mode],
            text=True,
            capture_output=True,
            env=merged,
            cwd=self.base,
        )

    def arm(self):
        result = self.run("--operator-arm")
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        return result

    def set_close_boot(self):
        (self.host / "proc/sys/kernel/random/boot_id").write_text(CLOSE_BOOT + "\n")

    def set_outcome(self, result):
        epoch = (
            "fprintd: GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY "
            "attempts=1 rejected=0 consumed=1 tls=1 first_image=1 secure_retry=0 "
            "post_retry=0 reopen=0 reset=0 clear_halt=0 persistent=0 outstanding=0 "
            "drained=1 context_closed=1\n"
        )
        outcome = f"fprintd: GOODIX_SIGFM_MATCH_AUDIT event=outcome result={result}\n"
        (self.fixtures / "fprintd.log").write_text(epoch + outcome)

    def capture(self):
        return next((self.repo / "captures/D290_01").glob("*/sanitized"))


class D290PersistentKitTests(unittest.TestCase):
    def setUp(self):
        self.fx = PersistentFixture()

    def tearDown(self):
        self.fx.close()

    def test_01_script_syntax_public_modes_and_old_method_disarmed(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        self.assertTrue(SCRIPT.stat().st_mode & stat.S_IXUSR)
        source = SCRIPT.read_text()
        for mode in ("--operator-arm", "--operator-close", "--operator-rollback"):
            self.assertIn(mode, source)
        for forbidden in ("coproc", "mkfifo", "mount --bind", "systemctl start"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("\nsudo reboot", source)
        self.assertIn('git -c "safe.directory=$d290_root"', source)
        self.assertNotIn("git config --global", source)
        self.assertIn("LIVE_CAPABLE=false", (OLD_EXP / "experiment.conf").read_text())

    def test_02_candidate_is_exact_single_line_delta_with_password_fallback(self):
        host = ORIGINAL.decode()
        line = "auth        sufficient    /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=45 debug\n"
        first = "auth     [success=done ignore=ignore default=bad] pam_selinux_permit.so\n"
        self.assertEqual(CANDIDATE.decode(), host.replace(first, first + line))
        self.assertLess(CANDIDATE.index(b"pam_fprintd.so"), CANDIDATE.index(b"password-auth"))

    def test_03_arm_success_and_root_only_state(self):
        result = self.fx.arm()
        self.assertIn("D290_PERSISTENT_TEST_ARMED=true", result.stdout)
        self.assertEqual(hashlib.sha256(self.fx.target.read_bytes()).hexdigest(), "89d389e6c2ee59dcee374029a5428a81dc9138c4f5e86068159b3d5a2c77ab2d")
        self.assertEqual(stat.S_IMODE(self.fx.state_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.fx.state_dir / "state.env").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.fx.state_dir / "plasmalogin.original").stat().st_mode), 0o600)
        self.assertEqual(self.fx.state_dir.stat().st_uid, os.getuid())
        self.assertEqual((self.fx.state_dir / "state.env").stat().st_uid, os.getuid())
        self.assertIn(str(self.fx.target), self.fx.restore_log.read_text())

    def test_04_arm_refuses_wrong_host_hash(self):
        self.fx.target.write_text("drift\n")
        result = self.fx.run("--operator-arm")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HOST_PAM_HASH_DRIFT", result.stderr)
        self.assertFalse(self.fx.state_dir.exists())

    def test_05_arm_refuses_preexisting_state(self):
        self.fx.state_dir.mkdir()
        result = self.fx.run("--operator-arm")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PREEXISTING_ARM_STATE", result.stderr)

    def test_05b_arm_refuses_selinux_policy_context_drift(self):
        result = self.fx.run(
            "--operator-arm",
            D290_TEST_POLICY_CONTEXT="system_u:object_r:wrong_t:s0",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HOST_PAM_SELINUX_POLICY_DRIFT", result.stderr)
        self.assertFalse(self.fx.state_dir.exists())

    def test_06_arm_failure_restores_original_and_removes_state(self):
        result = self.fx.run("--operator-arm", D290_TEST_RESTORECON_FAIL_ONCE="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)
        self.assertFalse(self.fx.state_dir.exists())
        self.assertIn("D290_ARM_FAILURE_ROLLBACK=PASS", result.stderr)

    def test_07_rollback_success_and_already_original_idempotence(self):
        for already_original in (False, True):
            with self.subTest(already_original=already_original):
                if self.fx.state_dir.exists():
                    self.fx.close()
                    self.fx = PersistentFixture()
                self.fx.arm()
                if already_original:
                    self.fx.target.write_bytes(ORIGINAL)
                result = self.fx.run("--operator-rollback")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)
                self.assertFalse(self.fx.state_dir.exists())
                self.assertIn("D290_ROLLBACK=PASS", result.stdout)

    def test_08_rollback_refuses_unknown_drift_and_retains_state(self):
        self.fx.arm()
        self.fx.target.write_text("unknown drift\n")
        result = self.fx.run("--operator-rollback")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UNKNOWN_HOST_PAM_DRIFT", result.stderr)
        self.assertTrue(self.fx.state_dir.exists())
        self.assertEqual(self.fx.target.read_text(), "unknown drift\n")

    def test_09_close_match_collects_session_and_rolls_back(self):
        self.fx.arm()
        self.fx.set_close_boot()
        self.fx.set_outcome("match")
        result = self.fx.run("--operator-close")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        capture = self.fx.capture()
        self.assertIn("D290_01_CLASSIFICATION=PASS_MATCH_NEW_SESSION", (capture / "classification.env").read_text())
        self.assertIn("D290_CURRENT_GRAPHICAL_SESSION_SERVICE=plasmalogin", (capture / "session.env").read_text())
        self.assertIn("D290_01_ROLLBACK_RETURN_CODE=0", (capture / "summary.env").read_text())
        self.assertNotIn("guido", (capture / "plasmalogin.log").read_text())
        self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)
        self.assertFalse(self.fx.state_dir.exists())

    def test_10_close_no_match_and_no_verify_are_classified_and_rolled_back(self):
        for outcome, expected in (("no_match", "NO_MATCH_PASSWORD_RECOVERY"), (None, "NO_VERIFY_REACHED")):
            with self.subTest(outcome=outcome):
                if self.fx.state_dir.exists() or list((self.fx.repo / "captures/D290_01").glob("*")):
                    self.fx.close()
                    self.fx = PersistentFixture()
                self.fx.arm()
                self.fx.set_close_boot()
                if outcome:
                    self.fx.set_outcome(outcome)
                result = self.fx.run("--operator-close")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"D290_01_CLASSIFICATION={expected}", result.stdout)
                self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)
                self.assertFalse(self.fx.state_dir.exists())

    def test_11_close_journal_failure_still_rolls_back(self):
        self.fx.arm()
        self.fx.set_close_boot()
        result = self.fx.run("--operator-close", D290_TEST_JOURNAL_FAIL="true")
        self.assertNotEqual(result.returncode, 0)
        capture = self.fx.capture()
        self.assertIn("D290_01_JOURNAL_COLLECTION_OK=false", (capture / "journal-status.env").read_text())
        self.assertIn("D290_01_ROLLBACK_RETURN_CODE=0", (capture / "summary.env").read_text())
        self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)
        self.assertFalse(self.fx.state_dir.exists())

    def test_12_close_same_boot_is_ambiguous_and_rolls_back(self):
        self.fx.arm()
        self.fx.set_outcome("match")
        result = self.fx.run("--operator-close")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("D290_01_CLASSIFICATION=AMBIGUOUS_REVIEW_REQUIRED", result.stdout)
        self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)

    def test_13_third_operator_capture_is_integral_pre_logout_and_pre_verify(self):
        capture = ROOT / "captures/live_probe/d290-plasmalogin_20260912T155916Z_4d6fb16350bb/sanitized"
        assessment = (ROOT / "analysis/D290/D290_01_post_reboot_read_only_assessment.env").read_text()
        check = subprocess.run(["sha256sum", "-c", "capture.sha256"], cwd=capture, text=True, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("D290_ROOT_OVERLAY_READY=true", (capture / "root-overlay.log").read_text())
        self.assertIn("D290_ROOT_HOST_PAM_RESTORED=true", (capture / "root-overlay.log").read_text())
        self.assertNotIn("GOODIX_", (capture / "diagnostic-journal.log").read_text())
        self.assertIn("D290_POST_AUDIT_SENSOR_ACTION_COUNT=0", (capture / "post-audit.log").read_text())
        self.assertIn("D290_01_PAM_MOUNTPOINT=false", assessment)
        self.assertIn("D290_01_OLD_RESIDUAL_PROCESS_COUNT=0", assessment)
        self.assertIn("D290_01_GOODIX_OR_VERIFY_MARKERS_AFTER_CAPTURE_CURSOR=0", assessment)

    def test_14_close_capture_setup_failure_uses_emergency_rollback(self):
        self.fx.arm()
        shutil.rmtree(self.fx.repo / "captures")
        (self.fx.repo / "captures").symlink_to(self.fx.fixtures, target_is_directory=True)
        result = self.fx.run("--operator-close")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CAPTURE_PARENT_UNSAFE", result.stderr)
        self.assertIn("D290_01_EMERGENCY_ROLLBACK=PASS", result.stderr)
        self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)
        self.assertFalse(self.fx.state_dir.exists())

    def test_15_rpm_verification_drift_retains_state_after_restoring_bytes(self):
        self.fx.arm()
        result = self.fx.run("--operator-rollback", D290_TEST_RPM_TARGET_DRIFT="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROLLBACK_VERIFICATION_FAILED", result.stderr)
        self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)
        self.assertTrue(self.fx.state_dir.exists())

    def test_16_rpm_verification_error_retains_state(self):
        self.fx.arm()
        result = self.fx.run("--operator-rollback", D290_TEST_RPM_VERIFY_ERROR="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROLLBACK_VERIFICATION_FAILED", result.stderr)
        self.assertEqual(self.fx.target.read_bytes(), ORIGINAL)
        self.assertTrue(self.fx.state_dir.exists())


if __name__ == "__main__":
    unittest.main()
