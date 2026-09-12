# SPDX-License-Identifier: GPL-2.0-or-later
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "operator_kit/live_probe"
EXP = HARNESS / "experiments/d290-plasmalogin"


class D290PlasmaLoginContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = (EXP / "experiment.conf").read_text()
        cls.payload = (EXP / "payload.sh").read_text()
        cls.helper = (EXP / "root-overlay.sh").read_text()
        cls.audit = (EXP / "audit.sh").read_text()
        cls.classifier = (EXP / "classify.sh").read_text()
        cls.readme = (EXP / "README_IT.md").read_text()
        cls.candidate = (EXP / "goodix-d290-plasmalogin.pam").read_text()

    def test_01_shell_syntax_and_executable(self):
        for name in ("payload.sh", "root-overlay.sh", "audit.sh", "cleanup.sh", "classify.sh", "sanitize.sh"):
            path = EXP / name
            self.assertTrue(path.stat().st_mode & 0o111, name)
            subprocess.run(["bash", "-n", str(path)], check=True)

    def test_02_reuses_common_harness_with_one_shot_budget(self):
        for marker in (
            "EXPERIMENT_ID=d290-plasmalogin",
            "ACTION=PLASMALOGIN_ONE_SHOT_VERIFY",
            "MAX_ACTIONS=1",
            "MAX_CONTACTS=1",
            "MAX_RETRIES=0",
            "REQUIRES_ACTIVE_USER_SESSION=false",
            "LIVE_CAPABLE=true",
        ):
            self.assertIn(marker, self.config)

    def test_03_candidate_is_exact_host_stack_plus_bounded_fingerprint(self):
        host = Path("/usr/lib/pam.d/plasmalogin").read_text()
        fingerprint = "auth        sufficient    /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=45 debug\n"
        first_auth = "auth     [success=done ignore=ignore default=bad] pam_selinux_permit.so\n"
        self.assertEqual(self.candidate, host.replace(first_auth, first_auth + fingerprint))
        self.assertEqual(self.candidate.count("pam_fprintd.so"), 1)
        self.assertEqual(self.candidate.count("password-auth"), host.count("password-auth"))

    def test_04_overlay_is_exact_read_only_and_recoverable(self):
        self.assertIn("target=/usr/lib/pam.d/plasmalogin", self.helper)
        self.assertIn('mount --bind "$runtime/plasmalogin" "$target"', self.helper)
        self.assertIn('mount -o remount,bind,ro "$target"', self.helper)
        self.assertIn("--recover", self.helper)
        self.assertIn("D290_ROOT_HOST_PAM_RESTORED=true", self.helper)
        self.assertIn("D290_ROOT_RUNTIME_REMOVED=true", self.helper)
        self.assertNotIn("authselect", self.helper)

    def test_05_root_helper_pins_real_daemon_and_namespace_before_mount(self):
        identity = self.helper.index("daemon_pid=$(systemctl show plasmalogin.service")
        namespace = self.helper.index('stat -Lc %i "/proc/$daemon_pid/ns/mnt"')
        bind = self.helper.index('mount --bind "$runtime/plasmalogin" "$target"')
        self.assertLess(identity, namespace)
        self.assertLess(namespace, bind)
        for marker in (
            "/usr/bin/plasmalogin",
            "/system.slice/plasmalogin.service",
            "D290_ROOT_DAEMON_IDENTITY=true",
        ):
            self.assertIn(marker, self.helper)

    def test_06_tty_lifecycle_is_explicit_and_logout_is_manual(self):
        self.assertIn("XDG_SESSION_TYPE:-} == tty", self.payload)
        self.assertIn("XDG_VTNR:-} == 3", self.payload)
        self.assertIn("Ctrl+Alt+F2", self.payload)
        self.assertIn("Ctrl+Alt+F3", self.payload)
        self.assertNotIn("terminate-session", self.payload)
        self.assertNotIn("logout-session", self.payload)
        self.assertNotIn("org.kde.Shutdown", self.payload)

    def test_07_real_greeter_and_new_session_are_required(self):
        for marker in (
            "/usr/libexec/plasma-login-greeter",
            "plasmalogin-greeter",
            "greeter",
            "plasma-login.service",
            "active_graphical_sessions",
            "PLASMALOGIN_MATCH_NEW_SESSION",
            "D290_NEW_GRAPHICAL_SESSION_CREATED=$session_created",
        ):
            self.assertIn(marker, self.payload)

    def test_08_exact_one_epoch_and_zero_retry_families(self):
        for field in (
            "attempts", "rejected", "consumed", "tls", "first_image",
            "secure_retry", "post_retry", "reopen", "reset", "clear_halt",
            "persistent", "outstanding", "drained", "context_closed",
        ):
            self.assertIn(f'field_sum {field} "$finger_log"', self.payload)
        self.assertNotIn("for attempt in", self.payload)
        self.assertIn("MAX_RETRIES=0", self.config)

    def test_09_overlay_is_released_before_operator_password_recovery(self):
        release = self.payload.index("\nrelease_overlay\n", self.payload.index("if [[ $result == match ]]"))
        recovery = self.payload.index("usare la password", release)
        close = self.payload.index("CHIUDI D290", release)
        self.assertLess(release, recovery)
        self.assertLess(release, close)
        self.assertIn("D290_OVERLAY_RELEASED_BEFORE_PASSWORD_RECOVERY=true", self.payload)
        self.assertIn("cleanup overlay non confermato", self.payload)

    def test_10_coproc_descriptors_are_duplicated(self):
        self.assertIn('exec {root_out_fd}<&"${D290_ROOT_HELPER[0]}"', self.payload)
        self.assertIn('exec {root_in_fd}>&"${D290_ROOT_HELPER[1]}"', self.payload)

    def test_11_pre_post_audit_pins_host_and_d286_state(self):
        for marker in (
            "plasma-login-manager-6.7.5-1.fc44.x86_64",
            "root:root:644",
            "OPERATOR_SESSION_TTY tty3",
            "INITIAL_GRAPHICAL_SESSION_NOT_TTY2",
            "GRAPHICAL_SESSION_TTY_INVALID",
            "D286_01_STATE_COHERENCE=PASS_ROOT_ONLY",
            "D286_01_PASSWORD_FALLBACK=PASS",
            "D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES",
        ):
            self.assertIn(marker, self.audit)

    def test_12_classifier_requires_session_causality_and_cleanup(self):
        for marker in (
            "D290_NEW_GRAPHICAL_SESSION_CREATED=true",
            "D290_NEW_GRAPHICAL_SESSION_CREATED=false",
            "D290_ROOT_OVERLAY_UNMOUNTED=true",
            "D290_ROOT_HOST_PAM_RESTORED=true",
            "D290_ROOT_RUNTIME_REMOVED=true",
        ):
            self.assertIn(marker, self.classifier)

    def test_13_operator_instructions_are_direct_and_fail_closed(self):
        for marker in (
            "Human Gate",
            "PREPARA LOGIN D290",
            "CHIUDI D290",
            "campo password, premere",
            "appoggiare una sola volta l'indice destro",
            "non rilanciare",
            "--recover",
        ):
            self.assertIn(marker, self.readme)

    def test_14_no_direct_usb_or_persistent_sensor_command(self):
        combined = "\n".join((self.payload, self.helper, self.audit))
        for forbidden in ("/dev/bus/usb", "usb.core", "ClearApp", "provision", "IAP", "flash"):
            self.assertNotIn(forbidden, combined)

    def test_15_real_offline_harness_path(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [str(HARNESS / "run.sh"), "d290-plasmalogin", "--offline-test", "--capture-root", td],
                cwd="/tmp",
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("LIVE_PROBE_RESULT=PASS", result.stdout)
            captures = list(Path(td).glob("*/sanitized"))
            self.assertEqual(len(captures), 1)
            self.assertIn(
                "D290_PAYLOAD_CLASSIFICATION=PASS_OFFLINE",
                (captures[0] / "payload-classification.env").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
