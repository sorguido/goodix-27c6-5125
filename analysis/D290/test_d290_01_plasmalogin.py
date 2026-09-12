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
        cls.session_model = (EXP / "session-model.sh").read_text()
        cls.readme = (EXP / "README_IT.md").read_text()
        cls.candidate = (EXP / "goodix-d290-plasmalogin.pam").read_text()

    def session_records(self, sessions, function, *args):
        with tempfile.TemporaryDirectory() as td:
            fixture = Path(td)
            lines = []
            for session in sessions:
                sid = str(session["id"])
                lines.append(f'{sid} {session.get("uid", 1000)} user seat0 1 user tty2 no -')
                for prop in ("Service", "Type", "Class", "State", "TTY"):
                    (fixture / f"{sid}.{prop}").write_text(session[prop] + "\n")
            (fixture / "sessions").write_text("\n".join(lines) + ("\n" if lines else ""))
            fake = fixture / "loginctl"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "case $1 in\n"
                "  list-sessions) cat \"$D290_FIXTURE_DIR/sessions\" ;;\n"
                "  show-session) cat \"$D290_FIXTURE_DIR/$2.$4\" ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n"
            )
            fake.chmod(0o755)
            command = [
                "bash", "-c",
                'source "$1"; shift; "$@"',
                "bash", str(EXP / "session-model.sh"), function, *map(str, args),
            ]
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                env={
                    "PATH": "/usr/bin:/bin",
                    "D290_LOGINCTL": str(fake),
                    "D290_FIXTURE_DIR": str(fixture),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return [line.split("|") for line in result.stdout.splitlines() if line]

    def test_01_shell_syntax_and_executable(self):
        for name in ("payload.sh", "root-overlay.sh", "audit.sh", "cleanup.sh", "classify.sh", "sanitize.sh", "session-model.sh"):
            path = EXP / name
            if name != "session-model.sh":
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
            "d290_new_graphical_session_records",
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
            "D290_INITIAL_GRAPHICAL_SESSION_COUNT",
            "D290_INITIAL_GRAPHICAL_SESSION_STATE",
            "d290_initial_graphical_session_records",
            "D286_01_STATE_COHERENCE=PASS_ROOT_ONLY",
            "D286_01_PASSWORD_FALLBACK=PASS",
            "D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES",
        ):
            self.assertIn(marker, self.audit)

    def test_12_classifier_requires_session_causality_and_cleanup(self):
        for marker in (
            "D290_NEW_GRAPHICAL_SESSION_CREATED=true",
            "D290_NEW_GRAPHICAL_SESSION_CREATED=false",
            "D290_NEW_GRAPHICAL_SESSION_SERVICE=plasmalogin",
            'new_session != "$initial_session"',
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

    def test_15_observed_nonforeground_initial_graphical_session_is_unique(self):
        records = self.session_records(
            [
                {"id": 2, "Service": "plasmalogin", "Type": "wayland", "Class": "user", "State": "online", "TTY": "tty2"},
                {"id": 3, "Service": "systemd-user", "Type": "unspecified", "Class": "manager", "State": "active", "TTY": ""},
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
            ],
            "d290_initial_graphical_session_records", 1000, 4,
        )
        self.assertEqual(records, [["2", "tty2", "plasmalogin", "wayland", "user", "online"]])

    def test_16_missing_tty2_graphical_session_fails_cardinality(self):
        records = self.session_records(
            [
                {"id": 3, "Service": "systemd-user", "Type": "unspecified", "Class": "manager", "State": "active", "TTY": ""},
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
            ],
            "d290_initial_graphical_session_records", 1000, 4,
        )
        self.assertEqual(records, [])

    def test_17_two_initial_wayland_candidates_fail_cardinality(self):
        sessions = [
            {"id": sid, "Service": "plasmalogin", "Type": "wayland", "Class": "user", "State": state, "TTY": "tty2"}
            for sid, state in ((2, "online"), (5, "active"))
        ]
        records = self.session_records(sessions, "d290_initial_graphical_session_records", 1000, 4)
        self.assertEqual([record[0] for record in records], ["2", "5"])

    def test_18_manager_and_operator_tty_are_not_graphical_candidates(self):
        records = self.session_records(
            [
                {"id": 3, "Service": "systemd-user", "Type": "unspecified", "Class": "manager", "State": "active", "TTY": ""},
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
            ],
            "d290_initial_graphical_session_records", 1000, 4,
        )
        self.assertEqual(records, [])

    def test_19_wrong_initial_identity_property_is_rejected(self):
        valid = {"id": 2, "Service": "plasmalogin", "Type": "wayland", "Class": "user", "State": "online", "TTY": "tty2"}
        for prop, wrong in (("Service", "sddm"), ("Type", "x11"), ("Class", "greeter"), ("TTY", "tty1"), ("State", "closing")):
            with self.subTest(prop=prop):
                session = dict(valid)
                session[prop] = wrong
                self.assertEqual(
                    self.session_records([session], "d290_initial_graphical_session_records", 1000, 4),
                    [],
                )

    def test_20_match_detects_only_a_new_plasmalogin_wayland_id(self):
        records = self.session_records(
            [
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
                {"id": 5, "Service": "plasmalogin", "Type": "wayland", "Class": "user", "State": "online", "TTY": "tty2"},
            ],
            "d290_new_graphical_session_records", 1000, 4, 2,
        )
        self.assertEqual(records[0][0], "5")

    def test_21_no_match_has_no_new_graphical_session(self):
        records = self.session_records(
            [
                {"id": 3, "Service": "systemd-user", "Type": "unspecified", "Class": "manager", "State": "active", "TTY": ""},
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
            ],
            "d290_new_graphical_session_records", 1000, 4, 2,
        )
        self.assertEqual(records, [])

    def test_22_pre_audit_failure_skips_payload_artifacts_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            experiment = root / "experiment"
            captures = root / "captures"
            experiment.mkdir()
            (experiment / "experiment.conf").write_text(
                "EXPERIMENT_ID=d290-preaudit-test\n"
                "GOAL='Test D290 pre-audit failure'\nACTION=OFFLINE_TEST\n"
                "PAYLOAD=payload.sh\nMAX_ACTIONS=1\nMAX_CONTACTS=1\nMAX_RETRIES=0\nTIMEOUT_SECONDS=10\n"
                "REQUIRES_ROOT=false\nREQUIRES_ACTIVE_USER_SESSION=false\nLIVE_CAPABLE=false\n"
                "OFFLINE_TEST_CAPABLE=true\nOUTPUT_IS_SANITIZED=true\nEXPECTED_TELEMETRY=NEVER\n"
                "STOP_CONDITIONS='pre audit failure'\nCONFIRMATION_TEXT=NEVER\n"
                "PRE_AUDIT=audit.sh\nPOST_AUDIT=audit.sh\nCLEANUP=cleanup.sh\nCLASSIFIER=classify.sh\n"
                "PAYLOAD_ACCEPTED_RETURN_CODES=0\nCOLLECT_JOURNAL=false\n"
            )
            scripts = {
                "payload.sh": "#!/usr/bin/env bash\necho PAYLOAD_MUST_NOT_RUN\n",
                "audit.sh": (
                    "#!/usr/bin/env bash\n"
                    "if [[ $2 == pre ]]; then echo D290_PRE_AUDIT=FAIL; exit 1; fi\n"
                    "echo D290_POST_AUDIT=PASS\n"
                ),
                "cleanup.sh": "#!/usr/bin/env bash\necho D290_CLEANUP=PASS\n",
            }
            for name, content in scripts.items():
                path = experiment / name
                path.write_text(content)
                path.chmod(0o755)
            (experiment / "classify.sh").symlink_to(EXP / "classify.sh")
            result = subprocess.run(
                [str(HARNESS / "run.sh"), "d290-preaudit-test", "--offline-test", "--capture-root", str(captures)],
                cwd="/tmp",
                text=True,
                capture_output=True,
                env={"PATH": "/usr/bin:/bin", "LIVE_PROBE_TEST_EXPERIMENT_DIR": str(experiment)},
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("No such file", result.stdout + result.stderr)
            self.assertNotIn("PAYLOAD_MUST_NOT_RUN", result.stdout + result.stderr)
            sanitized = next(captures.glob("*/sanitized"))
            self.assertFalse((sanitized / "payload.log").exists())
            self.assertEqual(
                (sanitized / "payload-classification.env").read_text().strip(),
                "D290_PAYLOAD_CLASSIFICATION=NOT_APPLICABLE_PRE_AUDIT_FAILURE",
            )
            summary = (sanitized / "summary.env").read_text()
            self.assertIn("LIVE_PROBE_RESULT=FAIL_PRE_AUDIT", summary)
            self.assertIn("LIVE_PROBE_PRIMARY_FAILURE=PRE_AUDIT", summary)
            self.assertIn("LIVE_PROBE_PAYLOAD_STARTED=false", summary)
            self.assertIn("LIVE_PROBE_PAYLOAD_CLASSIFIER_RETURN_CODE=0", summary)

    def test_23_real_offline_harness_path(self):
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
