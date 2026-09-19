#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline transaction tests: temporary files, mocked service calls, no sudo/USB."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class TransactionTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('transaction', HERE / 'transaction.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.temp = tempfile.TemporaryDirectory(prefix='goodix-same-action-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.m.p = lambda x: self.root / x.lstrip('/')
        self.active = 'active'
        self.calls = []
        self.fail_restorecon = False
        self.fail_reload = False
        self.m.run = self.run_fake
        for name in self.m.BASELINE:
            path = self.m.p(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('baseline ' + name).encode())
        self.m.p(self.m.VENDOR_PAM).write_bytes(
            b'auth sufficient /usr/lib64/security/pam_fprintd.so max-tries=3 timeout=45 debug\n'
            b'auth substack password-auth\n')
        self.m.BASELINE = {name: self.m.digest(self.m.read(name)) for name in self.m.BASELINE}
        self.m.p(self.m.BASE_RUNTIME + '/libfprint-2.so.2').symlink_to('libfprint-2.so.2.0.0')
        self.m.p(self.m.BASE_RUNTIME + '/libfprint-2.so').symlink_to('libfprint-2.so.2')
        for name in (self.m.STATE, self.m.PAM):
            self.m.p(name).parent.mkdir(parents=True, exist_ok=True)
        self.candidate = self.root / 'candidate'
        self.candidate.mkdir()
        for name in self.m.FILES:
            (self.candidate / name).write_bytes(('candidate ' + name).encode())
        (self.candidate / 'SHA256SUMS').write_text(''.join(
            f'{self.m.digest((self.candidate / name).read_bytes())}  {name}\n' for name in self.m.FILES))

    def run_fake(self, *args):
        self.calls.append(args)
        if args[0] == 'restorecon':
            if self.fail_restorecon:
                self.fail_restorecon = False
                raise RuntimeError('injected label failure')
            return ''
        self.assertEqual(args[0], 'systemctl')
        command = args[1]
        if command in ('start', 'stop'):
            self.active = 'active' if command == 'start' else 'inactive'
        elif command == 'daemon-reload' and self.fail_reload:
            self.fail_reload = False
            raise RuntimeError('injected reload failure')
        elif command == 'show':
            if args[3] == 'ActiveState':
                return self.active
            wrapper = self.m.WRAPPER if self.m.p(self.m.DROPIN).exists() else self.m.PREVIOUS
            return f'{{ path={wrapper} ; argv[]={wrapper} ; ignore_errors=no ; }}'
        elif command == 'cat':
            return 'baseline-unit' + ('\noverlay' if self.m.p(self.m.DROPIN).exists() else '')
        return ''

    def assert_original(self):
        self.m.baseline()
        for name in (self.m.PAM, self.m.WRAPPER, self.m.DROPIN, self.m.RUNTIME, self.m.STATE):
            self.assertFalse(self.m.p(name).exists(), name)
        self.assertEqual(self.active, 'active')

    def test_install_rollback_idempotent(self):
        self.m.install(self.candidate)
        self.assertIn(b'max-tries=1 timeout=20', self.m.read(self.m.PAM))
        self.assertIn(b'auth substack password-auth', self.m.read(self.m.PAM))
        state = json.loads(self.m.read(self.m.STATE))
        self.assertEqual(state['status'], 'ACTIVE')
        self.assertEqual(self.m.p(self.m.STATE).stat().st_mode & 0o777, 0o600)
        subprocess.run(['bash', '-n', str(self.m.p(self.m.WRAPPER))], check=True)
        before = list(self.calls)
        self.m.install(self.candidate)
        self.assertNotIn(('systemctl', 'stop', 'fprintd.service'), self.calls[len(before):])
        self.m.rollback()
        self.m.rollback()
        self.assert_original()

    def test_install_label_failure_restores_original(self):
        self.fail_restorecon = True
        with self.assertRaisesRegex(RuntimeError, 'label failure'):
            self.m.install(self.candidate)
        self.assert_original()

    def test_partial_copy_failure_restores_original(self):
        original_write = self.m.write
        failed = False

        def write(name, data, mode=0o644):
            nonlocal failed
            if name.endswith('libgusb.so.2') and not failed:
                failed = True
                raise RuntimeError('injected copy failure')
            return original_write(name, data, mode)

        self.m.write = write
        with self.assertRaisesRegex(RuntimeError, 'copy failure'):
            self.m.install(self.candidate)
        self.assert_original()

    def test_rollback_can_resume_after_reload_failure(self):
        self.m.install(self.candidate)
        self.fail_reload = True
        with self.assertRaisesRegex(RuntimeError, 'reload failure'):
            self.m.rollback()
        self.assertEqual(json.loads(self.m.read(self.m.STATE))['status'], 'REMOVING')
        self.m.rollback()
        self.assert_original()

    def test_pam_drift_is_not_destroyed(self):
        self.m.install(self.candidate)
        self.m.p(self.m.PAM).write_bytes(b'user work')
        calls = len(self.calls)
        with self.assertRaisesRegex(RuntimeError, 'overlay changed'):
            self.m.rollback()
        self.assertEqual(self.m.read(self.m.PAM), b'user work')
        self.assertEqual(len(self.calls), calls)

    def test_candidate_drift_and_existing_pam_fail_before_mutation(self):
        (self.candidate / self.m.LIBS[0]).write_bytes(b'drift')
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            self.m.install(self.candidate)
        self.assert_original()
        self.m.p(self.m.PAM).write_bytes(b'preexisting override')
        with self.assertRaisesRegex(RuntimeError, 'expected absent'):
            self.m.install(self.candidate)
        self.assertEqual(self.m.read(self.m.PAM), b'preexisting override')


if __name__ == '__main__':
    unittest.main()
