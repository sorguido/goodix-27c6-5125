#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
INSTALL = HERE / "install.sh"
HOOK = HERE / "50-goodix-fprint-account-delete"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class D293B5LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="d293-b5-test.", dir="/tmp"))
        self.env = os.environ.copy()
        self.env.update(D293_B5_TEST_MODE="true", D293_B5_TEST_ROOT=str(self.base))
        runtime = self.base / (
            "usr/local/lib64/goodix-27c6-5125/"
            "d293-native-e61fce313794922a2dab156a1b38a8ddc5837f19"
        )
        runtime.mkdir(parents=True)
        wrapper = self.base / "usr/local/sbin/goodix-d293-native-fprintd"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text(
            "#!/bin/sh\n"
            "runtime='/usr/local/lib64/goodix-27c6-5125/"
            "d293-native-e61fce313794922a2dab156a1b38a8ddc5837f19'\n"
        )
        wrapper.chmod(0o755)
        dropin = self.base / "etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf"
        dropin.parent.mkdir(parents=True)
        dropin.write_text(
            "[Service]\nExecStart=\n"
            "ExecStart=/usr/local/sbin/goodix-d293-native-fprintd\n"
        )
        (self.base / "etc/goodix-27c6-5125").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.base)

    def run_install(self, expect=0):
        cp = subprocess.run(
            [str(INSTALL), "--root-install", "tester", "a" * 40],
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(cp.returncode, expect, cp.stdout + cp.stderr)
        return cp

    def run_uninstall(self, expect=0):
        cp = subprocess.run(
            [str(INSTALL), "--root-uninstall", "tester"],
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(cp.returncode, expect, cp.stdout + cp.stderr)
        return cp

    def run_hook(self, subject="d293test", action="userdel", expect=0, extra_env=None):
        env = self.env.copy()
        env.update(ACTION=action, SUBJECT=subject)
        if extra_env:
            env.update(extra_env)
        cp = subprocess.run([str(HOOK)], env=env, text=True, capture_output=True)
        self.assertEqual(cp.returncode, expect, cp.stdout + cp.stderr)
        return cp

    def test_hook_passes_without_state_or_user_namespace(self):
        self.assertIn("PASS_NO_FPRINT_STATE", self.run_hook().stdout)
        (self.base / "var/lib/fprint").mkdir(parents=True)
        self.assertIn("PASS_NO_USER_NAMESPACE", self.run_hook().stdout)

    def test_hook_blocks_data_and_accepts_empty_namespace(self):
        user = self.base / "var/lib/fprint/d293test"
        user.mkdir(parents=True)
        self.assertIn("PASS_EMPTY_USER_NAMESPACE", self.run_hook().stdout)
        template = user / "goodix_27c6_5125/0/2"
        template.parent.mkdir(parents=True)
        template.write_text("content-free-fixture")
        cp = self.run_hook(expect=1)
        self.assertIn("BLOCKED_FINGERPRINTS_PRESENT", cp.stderr)

    def test_hook_fails_closed_when_namespace_cannot_be_read(self):
        user = self.base / "var/lib/fprint/d293test"
        user.mkdir(parents=True)
        test_bin = self.base / "test-bin"
        test_bin.mkdir()
        failing_find = test_bin / "find"
        failing_find.write_text("#!/bin/sh\nexit 1\n")
        failing_find.chmod(0o755)
        cp = self.run_hook(
            expect=1,
            extra_env={"PATH": f"{test_bin}:{self.env['PATH']}"},
        )
        self.assertIn("user_namespace_unreadable", cp.stderr)

    def test_hook_rejects_unsafe_input_and_symlinks(self):
        for subject in ("", ".", "..", "../escape", "a/b"):
            self.assertIn("invalid_subject", self.run_hook(subject=subject, expect=1).stderr)
        self.assertIn("unexpected_action", self.run_hook(action="usermod", expect=1).stderr)
        target = self.base / "target"
        target.mkdir()
        state = self.base / "var/lib/fprint"
        state.parent.mkdir(parents=True)
        state.symlink_to(target, target_is_directory=True)
        self.assertIn("fprint_state_root_unsafe", self.run_hook(expect=1).stderr)

    def test_install_and_exact_rollback(self):
        cp = self.run_install()
        self.assertIn("D293_B5_INSTALL=PASS", cp.stdout)
        hook = self.base / "etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete"
        state = self.base / "etc/goodix-27c6-5125/d293-phase-b-account-lifecycle.state"
        self.assertEqual(sha(hook), sha(HOOK))
        self.assertEqual(hook.stat().st_mode & 0o777, 0o755)
        self.assertEqual(state.stat().st_mode & 0o777, 0o600)
        cp = self.run_uninstall()
        self.assertIn("D293_B5_ROLLBACK=PASS", cp.stdout)
        self.assertFalse(hook.exists())
        self.assertFalse(state.exists())
        self.assertFalse((self.base / "etc/shadow-maint").exists())

    def test_partial_install_failure_is_rolled_back(self):
        state_parent = self.base / "etc/goodix-27c6-5125"
        state_parent.chmod(0o500)
        try:
            cp = self.run_install(expect=1)
            self.assertIn("partial_install_rolled_back", cp.stderr)
            self.assertFalse(
                (
                    self.base
                    / "etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete"
                ).exists()
            )
            self.assertFalse((self.base / "etc/shadow-maint").exists())
            self.assertFalse(
                (state_parent / "d293-phase-b-account-lifecycle.state").exists()
            )
        finally:
            state_parent.chmod(0o700)

    def test_existing_parent_is_preserved(self):
        parent = self.base / "etc/shadow-maint/userdel-pre.d"
        parent.mkdir(parents=True)
        parent.chmod(0o711)
        self.run_install()
        self.run_uninstall()
        self.assertTrue(parent.is_dir())
        self.assertEqual(parent.stat().st_mode & 0o777, 0o711)

    def test_collision_and_drift_fail_closed(self):
        hook = self.base / "etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete"
        hook.parent.mkdir(parents=True)
        hook.write_text("preexisting")
        self.assertIn("already_installed_or_collision", self.run_install(expect=1).stderr)
        hook.unlink()
        self.run_install()
        hook.write_text("drift")
        self.assertIn("hook_drift", self.run_uninstall(expect=1).stderr)
        self.assertTrue(hook.exists())

    def test_rollback_refuses_new_entries_in_created_parent(self):
        self.run_install()
        extra = self.base / "etc/shadow-maint/userdel-pre.d/90-external"
        extra.write_text("external")
        self.assertIn("hook_parent_gained_entries", self.run_uninstall(expect=1).stderr)
        self.assertTrue(extra.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
