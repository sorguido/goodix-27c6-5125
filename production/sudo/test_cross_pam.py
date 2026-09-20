#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent PAM budgets with concurrent consumers; leaves are synthetic.

Actual daemon Claim contention is separately exercised in test_daemon.c.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
headers = sys.argv.pop(1)


def load(name, path):
    old = sys.argv
    sys.argv = [str(path), headers]
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.argv = old


Polkit = load("polkit_tests", HERE.parent / "polkit/test_pam.py").Conversation
Sudo = load("sudo_tests", HERE / "test_pam.py").SudoPAM


class IndependentBudgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Polkit.setUpClass(); Sudo.setUpClass()

    @classmethod
    def tearDownClass(cls):
        Polkit.tearDownClass(); Sudo.tearDownClass()

    def setUp(self):
        self.p = Polkit(); self.s = Sudo()
        self.p.setUp(); self.s.setUp()
        self.addCleanup(self.p.tearDown); self.addCleanup(self.s.tearDown)
        self.addCleanup(self.p.doCleanups); self.addCleanup(self.s.doCleanups)

    def test_polkit_active_sudo_busy_password_does_not_reset_guard(self):
        process = self.p.launch_blocked()
        self.assertEqual(self.p.counter.read_text(), "1")
        self.s.run_pam("\noffline-password\n", mode="unavailable")
        self.assertEqual(self.p.counter.read_text(), "1")
        self.assertIsNone(process.poll())
        out, err = process.communicate(b"offline-password\n", timeout=2)
        self.assertEqual(process.returncode, 0, out + err)

    def test_sudo_active_polkit_busy_password_does_not_stop_sudo(self):
        process = self.s.blocked()
        polkit = self.p.launch_blocked("unavailable")
        out, err = polkit.communicate(b"offline-password\n", timeout=2)
        self.assertEqual(polkit.returncode, 0, out + err)
        self.assertIsNone(process.poll())
        self.assertEqual(self.s.count(), 1)
        self.assertEqual(self.p.counter.read_text(), "0")

    def test_exhausted_polkit_allows_independent_three_sudo_choices(self):
        self.p.counter.write_text("3"); self.p.counter.chmod(0o600)
        self.s.run_pam("\n\n\noffline-password\n", mode="no-match")
        self.assertEqual(self.s.count(), 3)
        self.assertEqual(self.p.counter.read_text(), "3")


if __name__ == "__main__":
    unittest.main(defaultTest="IndependentBudgets", verbosity=2)
