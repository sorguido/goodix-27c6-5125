# SPDX-License-Identifier: GPL-2.0-or-later
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "operator_kit/live_probe"
EXP = HARNESS / "experiments/d289-real-locked-session"


class D289RealLockedSessionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = (EXP / "experiment.conf").read_text()
        cls.payload = (EXP / "payload.sh").read_text()
        cls.helper = (EXP / "root-overlay.sh").read_text()
        cls.audit = (EXP / "audit.sh").read_text()
        cls.classifier = (EXP / "classify.sh").read_text()
        cls.readme = (EXP / "README_IT.md").read_text()

    def test_01_shell_syntax_and_executable(self):
        scripts = ["payload.sh", "root-overlay.sh", "audit.sh", "cleanup.sh", "classify.sh", "sanitize.sh"]
        for name in scripts:
            path = EXP / name
            self.assertTrue(path.stat().st_mode & 0o111, name)
            subprocess.run(["bash", "-n", str(path)], check=True)

    def test_02_small_payload_reuses_common_harness(self):
        self.assertIn("EXPERIMENT_ID=d289-real-locked-session", self.config)
        self.assertIn("MAX_ACTIONS=3", self.config)
        self.assertIn("MAX_CONTACTS=3", self.config)
        self.assertIn("MAX_RETRIES=0", self.config)
        self.assertIn("TIMEOUT_SECONDS=900", self.config)
        self.assertNotIn("run-d289", "\n".join(p.name for p in EXP.iterdir()))

    def test_03_exact_single_try_fingerprint_pam(self):
        pam = (EXP / "goodix-d289-kde-fingerprint.pam").read_text()
        self.assertEqual(pam.count("pam_fprintd.so"), 1)
        self.assertIn("max-tries=1 timeout=45", pam)

    def test_04_overlay_is_exact_read_only_and_restored(self):
        self.assertIn("target=/etc/pam.d/kde-fingerprint", self.helper)
        self.assertIn('mount --bind "$runtime/kde-fingerprint" "$target"', self.helper)
        self.assertIn('mount -o remount,bind,ro "$target"', self.helper)
        self.assertIn('install -o root -g root -m 0644 "$candidate"', self.helper)
        self.assertIn('umount "$target"', self.helper)
        self.assertIn("D289_ROOT_HOST_PAM_RESTORED=true", self.helper)
        self.assertIn("D289_USER_OVERLAY_VISIBLE_AND_PASSWORD_SERVICE_UNCHANGED=true", self.payload)
        self.assertNotIn("/etc/pam.d/kde\"", self.helper)

    def test_05_namespace_and_kwin_identity_precede_mount(self):
        namespace = self.helper.index('stat -Lc %i "/proc/$kwin_pid/ns/mnt"')
        bind = self.helper.index('mount --bind "$runtime/kde-fingerprint" "$target"')
        self.assertLess(namespace, bind)
        self.assertLess(self.helper.index("/usr/bin/kwin_wayland"), bind)
        self.assertIn("PKEXEC_UID", self.helper)

    def test_06_helper_lifetime_is_pipe_bounded(self):
        self.assertIn("IFS= read -r command", self.helper)
        self.assertIn("[[ $command == RELEASE ]]", self.helper)
        self.assertIn("--recover", self.helper)
        self.assertIn("trap on_exit EXIT", self.helper)
        self.assertIn("trap 'exit 130' HUP INT TERM", self.helper)
        self.assertIn("release_overlay", self.payload)
        self.assertIn("start_overlay", self.payload)
        self.assertIn("recover_locked_session", self.payload)
        self.assertNotIn("unlock-session", self.payload)

    def test_07_real_lock_and_state_transition_are_required(self):
        self.assertIn("org.freedesktop.ScreenSaver Lock", self.payload)
        self.assertIn("wait_active true", self.payload)
        self.assertIn("wait_active false", self.payload)
        self.assertIn("D289_LOCK_ACTIVE_OBSERVED=true", self.payload)
        self.assertNotIn("--testing", self.payload)

    def test_08_real_greeter_must_be_kwin_child(self):
        self.assertIn("D289_ATTEMPT_${attempt}_GREETER_PARENT_KWIN=true", self.payload)
        self.assertIn('[[ $greeter_ppid == "$kwin_pid"', self.payload)
        self.assertIn('[[ $(get_kwin_owner) == "$kwin_pid" ]]', self.payload)
        self.assertIn("/usr/libexec/kscreenlocker_greet", self.payload)
        self.assertIn("wait_no_greeter", self.payload)

    def test_09_explicit_cycles_and_password_recovery_after_no_match(self):
        self.assertIn("for attempt in 1 2 3", self.payload)
        self.assertIn('[[ $confirmation == "TENTATIVO $attempt" ]]', self.payload)
        self.assertIn("result == no_match", self.payload)
        self.assertIn("password per recuperare la sessione", self.payload)
        self.assertIn("AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false", self.payload)

    def test_10_epoch_safety_is_fail_closed(self):
        for field in ("attempts", "rejected", "consumed", "tls", "first_image", "secure_retry", "post_retry", "reopen", "reset", "clear_halt", "persistent", "outstanding", "drained", "context_closed"):
            self.assertIn(f'field_sum {field} "$journal_log"', self.payload)

    def test_11_classifier_requires_lock_and_overlay_closure(self):
        for marker in ("D289_LOCK_ACTIVE_BEFORE=false", "D289_LOCK_ACTIVE_OBSERVED=true", "D289_LOCK_ACTIVE_AFTER=false", "D289_ROOT_OVERLAY_UNMOUNTED=true", "D289_ROOT_HOST_PAM_RESTORED=true"):
            self.assertIn(marker, self.classifier)

    def test_12_pre_post_audit_preserves_password_and_runtime(self):
        self.assertIn("D286_01_PASSWORD_FALLBACK=PASS", self.audit)
        self.assertIn("/etc/pam.d/kde ", self.audit)
        self.assertIn("D289_SCREEN_LOCK_ACTIVE=false", self.audit)
        self.assertIn("D289_EXISTING_GREETER_COUNT=0", self.audit)
        self.assertIn("findmnt mount umount chcon", self.audit)

    def test_13_operator_instructions_expose_lock_and_recovery(self):
        for text in ("Human Gate", "Ctrl+Alt+F3", "BLOCCA SESSIONE", "TENTATIVO 2", "--recover", "non rilanciare"):
            self.assertIn(text, self.readme)

    def test_14_offline_harness_path(self):
        with tempfile.TemporaryDirectory() as td:
            run = subprocess.run(
                [str(HARNESS / "run.sh"), "d289-real-locked-session", "--offline-test", "--capture-root", td],
                cwd="/tmp",
                text=True,
                capture_output=True,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("LIVE_PROBE_RESULT=PASS", run.stdout)
            captures = list(Path(td).glob("*/sanitized"))
            self.assertEqual(len(captures), 1)
            self.assertIn("D289_PAYLOAD_CLASSIFICATION=PASS_OFFLINE", (captures[0] / "payload-classification.env").read_text())


if __name__ == "__main__":
    unittest.main()
