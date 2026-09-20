#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Real libpam, synthetic leaves, application-owned input; never executes sudo."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
HEADERS = Path(sys.argv.pop(1)).resolve()


class SudoPAM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="goodix-sudo-test.", dir="/tmp")
        cls.build = Path(cls.temp.name)
        args = ["gcc", "-Wall", "-Wextra", "-Werror", "-O2", f"-I{HEADERS}"]
        if os.environ.get("GOODIX_POLKIT_SANITIZE") == "1":
            args += ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            if os.environ.get("GOODIX_POLKIT_SANITIZER_LIBDIR"):
                args += ["-L" + os.environ["GOODIX_POLKIT_SANITIZER_LIBDIR"]]
        for name, source, flags in (
            ("bridge.so", "pam_goodix_sudo.c", ["-shared", "-fPIC", "-DGOODIX_SUDO_OFFLINE_TEST"]),
            ("production.so", "pam_goodix_sudo.c", ["-shared", "-fPIC"]),
            ("fake.so", "test_pam.c", ["-shared", "-fPIC", "-DTEST_MODULE"]),
            ("runner", "test_pam.c", ["-Wl,--export-dynamic"]),
        ):
            subprocess.run([*args, *flags, str(HERE / source), "/usr/lib64/libpam.so.0", "-o", str(cls.build / name)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="goodix-sudo-test.", dir="/tmp")
        self.root = Path(self.tmp.name)
        self.marker = self.root / "children"
        self.env = os.environ | {"GOODIX_SUDO_TEST_CONFDIR": str(self.root),
            "GOODIX_SUDO_TEST_MARKER": str(self.marker), "GOODIX_SUDO_TEST_MODE": "match"}
        for service in ("sudo", "sudo-i", "polkit-1"):
            self.policy(service)
        (self.root / "goodix-sudo-fingerprint").write_text(f"auth required {self.build}/fake.so fingerprint\n")
        # A foreign guard, deliberately exhausted: sudo must not read/reset it.
        self.guard = self.root / "polkit-guard"
        self.guard.write_text("3"); self.guard.chmod(0o600)
        self.env["GOODIX_POLKIT_TEST_GUARD"] = str(self.guard)

    def tearDown(self):
        self.assertEqual(self.guard.read_text(), "3")
        self.tmp.cleanup()

    def policy(self, service="sudo", module="bridge.so"):
        (self.root / service).write_text(
            f"auth [success=done ignore=ignore open_err=ignore symbol_err=ignore module_unknown=ignore default=die] {self.build}/{module}\n"
            f"auth required {self.build}/fake.so password\naccount required {self.build}/fake.so\n")

    def count(self):
        return len(self.marker.read_text().splitlines()) if self.marker.exists() else 0

    def run_pam(self, data, mode="match", service="sudo", success=True, timeout=3, **env):
        r = subprocess.run([str(self.build / "runner"), str(self.root), service], input=data,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            env=self.env | {"GOODIX_SUDO_TEST_MODE": mode} | env)
        self.assertEqual(r.returncode, 0 if success else 1, r.stdout + r.stderr)
        self.assertNotIn("offline-password", r.stdout + r.stderr)
        return r

    def blocked(self):
        p = subprocess.Popen([str(self.build / "runner"), str(self.root), "sudo"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=self.env | {"GOODIX_SUDO_TEST_MODE": "block"})
        def stop():
            if p.poll() is None: p.kill()
            p.communicate(timeout=2)
        self.addCleanup(stop)
        p.stdin.write(b"\n"); p.stdin.flush()
        end = time.monotonic() + 2
        while not self.count():
            self.assertLess(time.monotonic(), end)
            time.sleep(0.005)
        return p

    def test_password_immediate_no_fingerprint(self):
        self.run_pam("offline-password\n")
        self.assertEqual(self.count(), 0)

    def test_match_first_and_login_service(self):
        for service in ("sudo", "sudo-i"):
            self.run_pam("\n", service=service)
        self.assertEqual(self.count(), 2)

    def test_two_local_identities_are_not_bound_to_installer(self):
        users = [row.split(":")[0] for row in Path("/etc/passwd").read_text().splitlines()
                 if int(row.split(":")[2]) != 0][:2]
        self.assertEqual(len(users), 2)
        for user in users:
            self.run_pam("\n", GOODIX_SUDO_TEST_USER=user)
        self.assertEqual(self.count(), 2)

    def test_match_still_requires_account_approval(self):
        self.run_pam("\n", success=False, GOODIX_SUDO_TEST_ACCOUNT_FAIL="1")
        self.assertEqual(self.count(), 1)

    def test_no_match_then_explicit_second_choice(self):
        self.run_pam("\n\n", mode="match-second")
        self.assertEqual(self.count(), 2)

    def test_three_no_match_then_password_no_fourth(self):
        self.run_pam("\n\n\noffline-password\n", mode="no-match")
        self.assertEqual(self.count(), 3)

    def test_sudo_application_retries_cannot_multiply_budget(self):
        self.run_pam("\n\n\nwrong\n\n\n", mode="no-match", success=False, GOODIX_SUDO_TEST_REPEAT="1")
        self.assertEqual(self.count(), 3)

    def test_password_choice_disables_later_fingerprint(self):
        self.run_pam("wrong\n\noffline-password\n", GOODIX_SUDO_TEST_REPEAT="1")
        self.assertEqual(self.count(), 0)

    def test_busy_no_enrollment_error_prompt_fall_back(self):
        for mode in ("unavailable", "error", "prompt"):
            self.run_pam("\noffline-password\n", mode=mode)
        self.assertEqual(self.count(), 3)

    def test_timeout_is_eight_seconds_overall(self):
        start = time.monotonic()
        self.run_pam("\noffline-password\n", mode="block", timeout=10)
        self.assertGreater(time.monotonic() - start, 7.5)
        self.assertLess(time.monotonic() - start, 9.5)
        self.assertEqual(self.count(), 1)

    def test_pending_ctrl_c_cancels_child_without_password_or_retry(self):
        p = self.blocked()
        p.send_signal(signal.SIGINT)
        out, err = p.communicate(timeout=2)
        self.assertEqual(p.returncode, 1, out + err)
        self.assertEqual(self.count(), 1)
        self.assertFalse(Path("/proc/" + self.marker.read_text().strip()).exists())

    def test_parent_death_kills_leaf(self):
        p = self.blocked(); pid = self.marker.read_text().strip()
        p.kill(); p.communicate(timeout=2)
        end = time.monotonic() + 2
        while Path(f"/proc/{pid}/stat").exists():
            try:
                if Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z": break
            except (FileNotFoundError, ProcessLookupError): break
            self.assertLess(time.monotonic(), end)
            time.sleep(0.005)

    def test_cancel_at_prompt_never_starts_leaf(self):
        self.run_pam("", success=False)
        self.assertEqual(self.count(), 0)

    def test_wrong_service_and_production_runner_and_missing_module_fallback(self):
        self.run_pam("offline-password\n", service="polkit-1")
        for module in ("production.so", "absent.so"):
            self.policy(module=module)
            self.run_pam("offline-password\n")
        self.assertEqual(self.count(), 0)

    def test_root_and_nonlocal_users_password_only(self):
        for user in ("root", "goodix-nonexistent-offline-user"):
            self.run_pam("offline-password\n", GOODIX_SUDO_TEST_USER=user)
        self.assertEqual(self.count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
