# SPDX-License-Identifier: GPL-2.0-or-later
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "operator_kit/live_probe"
EXP = HARNESS / "experiments/d289-real-locked-session"
IDENTITY = EXP / "kwin-identity.sh"


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
        subprocess.run(["bash", "-n", str(IDENTITY)], check=True)

    def test_02_small_payload_reuses_common_harness(self):
        self.assertIn("EXPERIMENT_ID=d289-real-locked-session", self.config)
        self.assertIn("LIVE_CAPABLE=false", self.config)
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
        self.assertLess(self.helper.index('d289_verify_kwin_identity "$kwin_pid"'), bind)
        self.assertIn(
            'D289_PROC_ROOT=/proc d289_verify_kwin_identity "$kwin_pid" "$operator_uid" >/dev/null',
            self.helper,
        )
        self.assertIn(
            'D289_PROC_ROOT=/proc d289_verify_kwin_identity "$kwin_pid" "$(id -u)"',
            self.payload,
        )
        self.assertIn(
            'D289_PROC_ROOT=/proc d289_verify_kwin_identity "$kwin_pid" "$uid"',
            self.audit,
        )
        self.assertIn('source "$here/kwin-identity.sh"', self.helper)
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

    def test_13_closed_instructions_preserve_risk_recovery_and_provenance(self):
        for text in (
            "Human Gate",
            "Ctrl+Alt+F3",
            "--recover",
            "Non rilanciare",
            "LIVE_CAPABLE=false",
            "comando storico",
        ):
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

    def test_15_read_only_preflight_mode_never_invokes_pkexec(self):
        self.assertIn("--read-only-preflight", self.audit)
        read_only = self.audit.index("if [[ $mode == read-only-preflight ]]")
        privileged = self.audit.index('audit_output=$(pkexec')
        self.assertLess(read_only, privileged)
        self.assertIn("D289_READ_ONLY_PREFLIGHT=PASS", self.audit)

    def test_16_coproc_descriptors_survive_fast_helper_exit(self):
        self.assertIn('exec {root_out_fd}<&"${D289_ROOT_HELPER[0]}"', self.payload)
        self.assertIn('exec {root_in_fd}>&"${D289_ROOT_HELPER[1]}"', self.payload)
        script = r'''
set -euo pipefail
coproc D289_TEST_HELPER {
  IFS= read -r command
  [[ $command == RELEASE ]]
  printf '%s\n' \
    D289_ROOT_OVERLAY_UNMOUNTED=true \
    D289_ROOT_HOST_PAM_RESTORED=true \
    D289_ROOT_RUNTIME_REMOVED=true
}
root_pid=$D289_TEST_HELPER_PID
exec {root_out_fd}<&"${D289_TEST_HELPER[0]}"
exec {root_in_fd}>&"${D289_TEST_HELPER[1]}"
printf 'RELEASE\n' >&"$root_in_fd"
exec {root_in_fd}>&-
sleep 0.05
while IFS= read -r line <&"$root_out_fd"; do printf '%s\n' "$line"; done
exec {root_out_fd}>&-
wait "$root_pid"
'''
        result = subprocess.run(
            ["bash", "-c", script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Descrittore di file errato", result.stdout)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "D289_ROOT_OVERLAY_UNMOUNTED=true",
                "D289_ROOT_HOST_PAM_RESTORED=true",
                "D289_ROOT_RUNTIME_REMOVED=true",
            ],
        )

    def test_17_closed_live_entrypoint_rejects_before_capture(self):
        with tempfile.TemporaryDirectory() as td:
            capture_root = Path(td) / "captures"
            result = subprocess.run(
                [
                    str(HARNESS / "run.sh"),
                    "d289-real-locked-session",
                    "--operator-run",
                    "--capture-root",
                    str(capture_root),
                ],
                cwd="/tmp",
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("LIVE_PROBE_ERROR=EXPERIMENT_NOT_LIVE_CAPABLE", result.stderr)
            self.assertFalse(capture_root.exists())


class D289KWinCompositeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="d289-kwin-identity-")
        self.proc = Path(self.tmp.name) / "proc"
        self.pid = "4242"
        self.entry = self.proc / self.pid
        self.entry.mkdir(parents=True)
        self.write_valid_fixture(with_exe=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_valid_fixture(self, with_exe):
        self.entry.joinpath("status").write_text(
            "Name:\tkwin_wayland\nUid:\t1000\t1000\t1000\t1000\n"
        )
        self.entry.joinpath("comm").write_text("kwin_wayland\n")
        self.entry.joinpath("cmdline").write_bytes(
            b"/usr/bin/kwin_wayland\0--wayland-fd\0" b"7\0"
        )
        self.entry.joinpath("cgroup").write_text(
            "0::/user.slice/user-1000.slice/user@1000.service/session.slice/plasma-kwin_wayland.service\n"
        )
        exe = self.entry / "exe"
        if exe.exists() or exe.is_symlink():
            exe.unlink()
        if with_exe:
            exe.symlink_to("/usr/bin/kwin_wayland")

    def run_identity(self, owner="u 4242"):
        script = (
            f"source '{IDENTITY}'; "
            f"D289_PROC_ROOT='{self.proc}'; "
            "pid=$(d289_parse_dbus_owner \"$D289_TEST_OWNER\") && "
            "d289_verify_kwin_identity \"$pid\" 1000"
        )
        return subprocess.run(
            ["bash", "-c", script],
            env={"PATH": "/usr/bin:/bin", "D289_TEST_OWNER": owner},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_valid_owner_uid_comm_cmdline_cgroup_and_readable_exe_pass(self):
        result = self.run_identity()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("D289_KWIN_IDENTITY_RESULT=PASS", result.stdout)
        self.assertIn("D289_KWIN_IDENTITY_EXE=COHERENT", result.stdout)

    def test_wrong_process_fails(self):
        self.entry.joinpath("comm").write_text("bash\n")
        result = self.run_identity()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("COMM_MISMATCH", result.stdout)

    def test_readable_but_empty_cmdline_fails(self):
        self.entry.joinpath("cmdline").write_bytes(b"")
        result = self.run_identity()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CMDLINE_EMPTY", result.stdout)

    def test_wrong_uid_fails(self):
        self.entry.joinpath("status").write_text("Uid:\t1001\t1001\t1001\t1001\n")
        result = self.run_identity()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UID_MISMATCH", result.stdout)

    def test_ambiguous_or_unparsable_owner_fails(self):
        for owner in ("u 4242\nu 4243", "s 4242", "u 0", ""):
            with self.subTest(owner=owner):
                result = self.run_identity(owner)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("D289_KWIN_OWNER_PARSE=FAIL", result.stdout)

    def test_root_or_system_cgroup_fails(self):
        for cgroup in (
            "0::/user.slice/user-0.slice/user@0.service/app.slice/kwin.scope\n",
            "0::/system.slice/kwin.service\n",
        ):
            with self.subTest(cgroup=cgroup):
                self.entry.joinpath("cgroup").write_text(cgroup)
                result = self.run_identity()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ROOT_OR_SYSTEM_CGROUP", result.stdout)

    def test_readable_but_inconsistent_exe_fails(self):
        exe = self.entry / "exe"
        exe.unlink()
        exe.symlink_to("/bin/sh")
        result = self.run_identity()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EXE_MISMATCH", result.stdout)

    def test_unreadable_exe_with_other_strong_signals_passes(self):
        self.write_valid_fixture(with_exe=False)
        result = self.run_identity()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "D289_KWIN_IDENTITY_EXE=UNREADABLE_ACCEPTED_WITH_COMPOSITE",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
