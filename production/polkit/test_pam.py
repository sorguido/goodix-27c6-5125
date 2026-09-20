#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Real libpam dispatch, pipes and child cancellation; only the leaf is synthetic."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
HEADERS = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None


class Conversation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert HEADERS and (HEADERS / "security/pam_appl.h").is_file()
        cls.build = tempfile.TemporaryDirectory(prefix="goodix-polkit-test.", dir="/tmp")
        cls.b = Path(cls.build.name)
        common = ["gcc", "-Wall", "-Wextra", "-Werror", "-O2", f"-I{HEADERS}"]
        if os.environ.get("GOODIX_POLKIT_SANITIZE") == "1":
            common += ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            if os.environ.get("GOODIX_POLKIT_SANITIZER_LIBDIR"):
                common += ["-L" + os.environ["GOODIX_POLKIT_SANITIZER_LIBDIR"]]
        lib = "/usr/lib64/libpam.so.0"
        for output, source, extra in (
            ("bridge.so", "pam_goodix_polkit.c", ["-fPIC", "-shared", "-DGOODIX_POLKIT_OFFLINE_TEST"]),
            ("production.so", "pam_goodix_polkit.c", ["-fPIC", "-shared"]),
            ("fake.so", "test_pam.c", ["-fPIC", "-shared", "-DTEST_MODULE"]),
            ("runner", "test_pam.c", ["-Wl,--export-dynamic"]),
        ):
            subprocess.run([*common, *extra, str(HERE / source), lib, "-o", str(cls.b / output)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="goodix-polkit-test.", dir="/tmp")
        self.root = Path(self.temp.name)
        self.guard = self.root / "guard"
        self.guard.mkdir(mode=0o700)
        self.counter = self.guard / str(os.getuid())
        self.marker = self.root / "children"
        self.env = os.environ | {
            "GOODIX_POLKIT_TEST_GUARD": str(self.guard),
            "GOODIX_POLKIT_TEST_CONFDIR": str(self.root),
            "GOODIX_POLKIT_TEST_MARKER": str(self.marker),
            "GOODIX_POLKIT_TEST_MODE": "match",
        }
        self.policy()
        (self.root / "goodix-polkit-fingerprint").write_text(f"auth required {self.b}/fake.so fingerprint\n")

    def tearDown(self):
        self.temp.cleanup()

    def policy(self, module="bridge.so", service="polkit-1"):
        (self.root / service).write_text(
            f"auth [success=done ignore=ignore open_err=ignore symbol_err=ignore module_unknown=ignore default=die] {self.b}/{module}\n"
            f"auth required {self.b}/fake.so password\n"
            f"account required {self.b}/fake.so\n")

    def run_pam(self, data, *, success=True, **env):
        with subprocess.Popen([str(self.b / "runner"), str(self.root), "polkit-1"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, env=self.env | env) as p:
            p.stdin.write(data); p.stdin.flush()
            # A real Polkit dialog keeps the channel open while authenticating.
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                raise
            out, err = p.communicate()
            r = subprocess.CompletedProcess(p.args, p.returncode, out, err)
        self.assertEqual(r.returncode, 0 if success else 1, r.stdout + r.stderr)
        self.assertNotIn("offline-password", r.stdout + r.stderr)
        return r

    def starts(self):
        return self.marker.read_text().splitlines() if self.marker.exists() else []

    def launch_blocked(self, mode="block"):
        p = subprocess.Popen([str(self.b / "runner"), str(self.root), "polkit-1"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=self.env | {"GOODIX_POLKIT_TEST_MODE": mode})
        def cleanup():
            if p.poll() is None: p.kill()
            p.communicate(timeout=2)
        self.addCleanup(cleanup)
        p.stdin.write(b"\n"); p.stdin.flush()
        deadline = time.monotonic() + 2
        while not self.starts():
            self.assertLess(time.monotonic(), deadline, "leaf did not start")
            time.sleep(0.005)
        return p

    def test_password_never_starts_fingerprint(self):
        self.run_pam("offline-password\n")
        self.assertEqual(self.starts(), [])
        self.assertEqual(self.counter.read_text(), "0")

    def test_socket_input_preserves_buffered_password(self):
        sender, receiver = socket.socketpair()
        with sender, receiver, subprocess.Popen(
            [str(self.b / "runner"), str(self.root), "polkit-1"], stdin=receiver,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=self.env | {"GOODIX_POLKIT_TEST_COOKIE": "1"}) as p:
            try:
                sender.sendall(b"offline-cookie\n\noffline-password\n")
                out, err = p.communicate(timeout=2)
                self.assertEqual(p.returncode, 0, out + err)
            finally:
                if p.poll() is None: p.kill()
                p.communicate(timeout=2)
        self.assertEqual(self.starts(), [])

    def test_match_ends_series(self):
        self.run_pam("\n")
        self.assertEqual(len(self.starts()), 1)
        self.assertEqual(self.counter.read_text(), "0")

    def test_three_conversations_then_password_only_until_success(self):
        for i in range(1, 4):
            self.run_pam("\n", success=False, GOODIX_POLKIT_TEST_MODE="no-match")
            self.assertEqual(self.counter.read_text(), str(i))
        self.run_pam("wrong\n", success=False)
        self.assertEqual(len(self.starts()), 3)
        self.assertEqual(self.counter.read_text(), "3")
        self.run_pam("offline-password\n")
        self.assertEqual(len(self.starts()), 3)
        self.assertEqual(self.counter.read_text(), "0")

    def test_buffered_cookie_blank_and_password_preserved(self):
        self.run_pam("offline-cookie\n\noffline-password\n", GOODIX_POLKIT_TEST_COOKIE="1")
        self.assertEqual(self.starts(), [])

    def test_password_cancels_blocked_child_without_timeout(self):
        p = self.launch_blocked()
        start = time.monotonic()
        out, err = p.communicate(b"offline-password\n", timeout=2)
        self.assertEqual(p.returncode, 0, out + err)
        self.assertLess(time.monotonic() - start, 2)
        self.assertFalse(Path(f"/proc/{self.starts()[0]}").exists())
        self.assertEqual(self.counter.read_text(), "0")

    def test_failed_password_does_not_reset_used_attempt(self):
        p = self.launch_blocked()
        out, err = p.communicate(b"wrong\n", timeout=2)
        self.assertEqual(p.returncode, 1, out + err)
        self.assertEqual(self.counter.read_text(), "1")
        self.assertEqual(len(self.starts()), 1)

    def test_eof_cancels_child(self):
        p = self.launch_blocked()
        p.communicate(timeout=2)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(Path(f"/proc/{self.starts()[0]}").exists())
        self.assertEqual(self.counter.read_text(), "1")

    def test_parent_death_kills_child(self):
        p = self.launch_blocked()
        child = self.starts()[0]
        p.kill(); p.communicate(timeout=2)
        deadline = time.monotonic() + 2
        while Path(f"/proc/{child}/stat").exists():
            # A terminated orphan may briefly remain a zombie until init reaps it.
            try:
                if Path(f"/proc/{child}/stat").read_text().split()[2] == "Z": break
            except (FileNotFoundError, ProcessLookupError):
                break  # init reaped it between stat and read
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.005)
        self.assertEqual(self.counter.read_text(), "1")

    def test_account_failure_does_not_reset_attempts(self):
        self.counter.write_text("2"); self.counter.chmod(0o600)
        self.run_pam("offline-password\n", success=False, GOODIX_POLKIT_TEST_ACCOUNT_FAIL="1")
        self.assertEqual(self.counter.read_text(), "2")

    def test_corrupt_counter_requires_password(self):
        self.counter.write_text("corrupt"); self.counter.chmod(0o600)
        self.run_pam("offline-password\n")
        self.assertEqual(self.starts(), [])
        self.assertEqual(self.counter.read_text(), "0")

    def test_symlink_collision_not_overwritten(self):
        target = self.root / "unrelated"
        target.write_text("preserve")
        self.counter.symlink_to(target)
        self.run_pam("offline-password\n")
        self.assertEqual(target.read_text(), "preserve")
        self.assertEqual(self.starts(), [])

    def test_concurrent_conversation_cannot_start_second_child(self):
        p = self.launch_blocked()
        self.run_pam("offline-password\n")
        self.assertEqual(len(self.starts()), 1)
        p.communicate(timeout=2)
        self.assertEqual(self.counter.read_text(), "1")

    def test_child_cannot_obtain_password(self):
        p = self.launch_blocked("prompt")
        out, err = p.communicate(b"offline-password\n", timeout=2)
        self.assertEqual(p.returncode, 0, out + err)
        self.assertEqual(len(self.starts()), 1)
        self.assertEqual(out.count(b"PROMPT\n"), 2)  # parent only: choice and fallback
        self.assertEqual(self.counter.read_text(), "0")

    def test_unavailable_leaf_falls_back_without_retry(self):
        p = self.launch_blocked("unavailable")
        out, err = p.communicate(b"offline-password\n", timeout=2)
        self.assertEqual(p.returncode, 0, out + err)
        self.assertEqual(len(self.starts()), 1)

    def test_partial_password_cancels_before_newline(self):
        p = self.launch_blocked()
        p.stdin.write(b"offline-"); p.stdin.flush()
        child = self.starts()[0]
        deadline = time.monotonic() + 2
        while Path(f"/proc/{child}").exists():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.005)
        out, err = p.communicate(b"password\n", timeout=2)
        self.assertEqual(p.returncode, 0, out + err)

    def test_production_module_rejects_test_process(self):
        self.policy(module="production.so")
        self.run_pam("offline-password\n")
        self.assertEqual(self.starts(), [])
        self.assertFalse(self.counter.exists())

    def test_missing_bridge_keeps_normal_password(self):
        self.policy(module="missing.so")
        self.run_pam("offline-password\n")
        self.run_pam("wrong\n", success=False)
        self.assertEqual(self.starts(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
