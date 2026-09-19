#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Use the existing overlay fixture; all host/service operations are mocked."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class DeltaTest(unittest.TestCase):
    def setUp(self):
        old = module('old_tests', HERE.parent / 'login-early/test_transaction.py')
        self.fixture = old.TransactionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.early = self.fixture.m
        self.early.install(self.fixture.candidate)
        self.delta = module('delta', HERE / 'transaction.py')
        self.delta.early = self.early
        self.before = {n: (self.early.read(n), self.early.p(n).stat().st_mode & 0o777)
                       for n in self.delta.TARGETS}
        self.candidate = self.fixture.root / 'delta'
        self.candidate.mkdir()
        for name in self.delta.FILES:
            (self.candidate / name).write_bytes(('updated ' + name).encode())
        (self.candidate / 'PROVENANCE').write_text('SOURCE_COMMIT=offline\nMODE=normal\nPURPOSE=PREPARED_LOGIN_THREE_ATTEMPTS\n')
        self.index()

    def index(self):
        (self.candidate / 'SHA256SUMS').write_text(''.join(
            f'{self.early.digest((self.candidate / n).read_bytes())}  {n}\n' for n in self.delta.FILES))

    def restored(self):
        self.assertEqual(self.fixture.active, 'active')
        for name, (data, mode) in self.before.items():
            self.assertEqual(self.early.read(name), data, name)
            self.assertEqual(self.early.p(name).stat().st_mode & 0o777, mode)
        self.assertFalse(self.early.p(self.delta.BACKUP).exists())

    def test_install_exact_rollback_and_idempotence(self):
        self.delta.install(self.candidate)
        self.assertIn(b'max-tries=3 timeout=8', self.early.read(self.early.PAM))
        self.assertIn(b'auth substack password-auth', self.early.read(self.early.PAM))
        before = len(self.fixture.calls)
        self.delta.install(self.candidate)
        self.assertEqual(len(self.fixture.calls), before)
        self.delta.restore(); self.delta.restore(); self.restored()

    def test_label_failure_restores_previous_overlay(self):
        self.fixture.fail_restorecon = True
        with self.assertRaisesRegex(RuntimeError, 'label failure'): self.delta.install(self.candidate)
        self.restored()

    def test_reload_failure_restores_previous_overlay(self):
        self.fixture.fail_reload = True
        with self.assertRaisesRegex(RuntimeError, 'reload failure'): self.delta.install(self.candidate)
        self.restored()

    def test_partial_update_failure_restores_previous_overlay(self):
        original = self.early.write
        failed = False
        def write(name, data, mode=0o644):
            nonlocal failed
            if name.endswith('/fprintd') and not failed:
                failed = True
                raise RuntimeError('partial update')
            original(name, data, mode)
        self.early.write = write
        with self.assertRaisesRegex(RuntimeError, 'partial update'): self.delta.install(self.candidate)
        self.restored()

    def test_rollback_reload_failure_is_resumable(self):
        self.delta.install(self.candidate)
        self.fixture.fail_reload = True
        with self.assertRaisesRegex(RuntimeError, 'reload failure'): self.delta.restore()
        self.assertTrue(self.early.p(self.delta.BACKUP).exists())
        self.delta.restore(); self.restored()

    def test_drift_is_preserved(self):
        self.delta.install(self.candidate)
        self.early.p(self.early.PAM).write_bytes(b'local edit')
        with self.assertRaisesRegex(RuntimeError, 'drift'): self.delta.restore()
        self.assertEqual(self.early.read(self.early.PAM), b'local edit')

    def test_candidate_tamper_fails_before_host_changes(self):
        (self.candidate / 'fprintd').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'digest'): self.delta.install(self.candidate)
        self.restored()

    def test_extra_candidate_file_fails_closed(self):
        (self.candidate / 'extra').write_bytes(b'no')
        with self.assertRaisesRegex(RuntimeError, 'file set'): self.delta.install(self.candidate)
        self.restored()

    def test_corrupt_backup_is_not_applied(self):
        self.delta.install(self.candidate)
        (self.early.p(self.delta.BACKUP) / '0').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'backup digest'): self.delta.restore()


if __name__ == '__main__':
    unittest.main(verbosity=2)
