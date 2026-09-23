#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Recovery-tool lifecycle on temporary paths; no host installation or privileges."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('recovery_manage', SOURCE / 'manage.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
REAL_GATE = m.gate


class RecoveryTools(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goodix-recovery-tools-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.here = self.root / 'source/deployment/recovery'
        self.here.mkdir(parents=True)
        self.payload = (SOURCE / 'remove.py').read_bytes()
        (self.here / 'remove.py').write_bytes(self.payload)
        self.commands = tuple(self.root / 'usr/local/bin' / name for name in
                              ('goodix-uninstall', 'goodix-force-remove'))
        self.support = self.root / 'usr/local/share/goodix-recovery'
        for path in (*self.commands, self.support):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.foreign = self.root / 'foreign-cwd'
        self.foreign.mkdir()
        self.sentinels = []
        for name in ('etc/pam.d/plasmalogin',
                     'etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf',
                     'usr/local/lib64/goodix-27c6-5125/installation.json',
                     'usr/local/lib64/goodix-plasma-login/pam_goodix_login_gate.so',
                     'var/lib/goodix-5125-poc/transport-material.bin',
                     'var/lib/fprint/synthetic/template'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic preservation sentinel\n')
            self.sentinels.append(path)

        # Emulate root ownership only inside this synthetic filesystem. Real
        # type/mode checks remain enabled; no chown or privilege operation runs.
        original_lstat = Path.lstat

        def synthetic_lstat(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if path == self.root or self.root in path.parents:
                fields = list(info)
                fields[4:6] = [0, 0]
                return os.stat_result(fields)
            return info

        def synthetic_parents(path):
            self.assertIn(self.root, path.parents, 'attempted access outside fixture')
            for parent in path.parents:
                m.trusted(parent, directory=True)
                if parent == self.root:
                    break

        self.branch = 'development'
        self.dirty = ''
        self.commit = 'a' * 40
        self.system_calls = []
        for name, value in {'HERE': self.here, 'ROOT': self.here.parents[1],
                            'COMMANDS': self.commands, 'SUPPORT': self.support,
                            'LOCK_DIRECTORY': self.root / 'usr/local/lib64'}.items():
            self.start(patch.object(m, name, value))
        self.start(patch.object(Path, 'lstat', synthetic_lstat))
        self.start(patch.object(m, 'parents', side_effect=synthetic_parents))
        self.run = self.start(patch.object(m, 'run', side_effect=self.command))
        self.output = self.start(patch('builtins.print'))
        self.start(patch.object(m, 'gate', side_effect=AssertionError('host gate must be mocked explicitly')))

    def start(self, replacement):
        result = replacement.start()
        self.addCleanup(replacement.stop)
        return result

    def command(self, *args):
        self.system_calls.append(args)
        if args[:1] == ('git',):
            self.assertEqual(args[:5], ('git', '-c', f'safe.directory={m.ROOT}', '-C', str(m.ROOT)))
            if args[5:] == ('branch', '--show-current'):
                return self.branch
            if args[5:] == ('status', '--porcelain'):
                return self.dirty
            self.assertEqual(args[5:], ('rev-parse', 'HEAD'))
            return self.commit
        self.assertEqual(args[:2], ('restorecon', '-F'))
        self.assertEqual(set(args[2:]), {str(self.support), str(self.support / 'receipt.json'),
                                       *(str(path) for path in self.commands)})
        return ''

    def assert_preserved(self):
        for path in self.sentinels:
            self.assertEqual(path.read_bytes(), b'synthetic preservation sentinel\n')

    def assert_absent(self):
        self.assertFalse(m.present(self.support))
        for path in self.commands:
            self.assertFalse(m.present(path))
        self.assert_preserved()

    def test_install_exact_standalone_commands_modes_receipt_and_rollback(self):
        m.install()
        receipt = json.loads((self.support / 'receipt.json').read_bytes())
        self.assertEqual(receipt, {'schema': 1, 'source_commit': self.commit,
                                  'files': {p.name: m.digest(self.payload) for p in self.commands}})
        self.assertEqual(stat.S_IMODE(self.support.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.support / 'receipt.json').stat().st_mode), 0o644)
        for path in self.commands:
            self.assertEqual(path.read_bytes(), self.payload)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
            # --help exits before any privileged or host operation in remove.py.
            result = subprocess.run([str(path), '--help'], cwd=self.foreign,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(path.name + ': remove Goodix software', result.stdout)
        self.assert_preserved()
        self.system_calls.clear()
        m.uninstall()
        self.assert_absent()
        self.assertEqual(self.system_calls, [], 'tool rollback must not call host commands')
        m.uninstall()
        self.assert_absent()

    def test_same_candidate_is_idempotent_and_different_candidate_refused(self):
        m.install()
        before = {p: p.read_bytes() for p in (*self.commands, self.support / 'receipt.json')}
        self.system_calls.clear()
        m.install()
        self.assertFalse(any(call[0] == 'restorecon' for call in self.system_calls))
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        (self.here / 'remove.py').write_bytes(self.payload + b'\n# different candidate\n')
        with self.assertRaisesRegex(RuntimeError, 'different recovery version'):
            m.install()
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assert_preserved()

    def test_project_command_drift_and_mode_drift_fail_closed(self):
        m.install()
        self.commands[0].write_bytes(b'foreign modification\n')
        with self.assertRaisesRegex(RuntimeError, 'command drift'):
            m.uninstall()
        self.assertEqual(self.commands[0].read_bytes(), b'foreign modification\n')
        self.assertTrue(self.commands[1].exists())
        self.commands[0].write_bytes(self.payload)
        self.commands[0].chmod(0o777)
        with self.assertRaisesRegex(RuntimeError, 'unsafe recovery path'):
            m.uninstall()
        self.assertTrue((self.support / 'receipt.json').exists())
        self.assert_preserved()

    def test_restorecon_failure_rolls_back_only_new_recovery_files(self):
        def failed_label(*args):
            if args[0] == 'restorecon':
                raise subprocess.CalledProcessError(1, args, stderr='synthetic label failure')
            return self.command(*args)
        self.run.side_effect = failed_label
        with self.assertRaises(subprocess.CalledProcessError):
            m.install()
        self.assert_absent()

    def test_missing_execute_permission_cannot_be_reported_already_installed(self):
        m.install()
        self.commands[1].chmod(0o644)
        with self.assertRaises(RuntimeError):
            m.install()
        self.assertEqual(self.commands[1].read_bytes(), self.payload)
        self.assertEqual(stat.S_IMODE(self.commands[1].stat().st_mode), 0o644)
        self.assert_preserved()

    def test_clean_development_checkout_required_before_writes(self):
        self.branch = 'main'
        with self.assertRaisesRegex(RuntimeError, 'development required'):
            m.install()
        self.assert_absent()
        self.branch = 'development'
        self.dirty = ' M deployment/recovery/remove.py'
        with self.assertRaisesRegex(RuntimeError, 'clean committed checkout'):
            m.install()
        self.assert_absent()

    def test_foreign_collision_symlink_and_extra_support_file_are_preserved(self):
        target = self.root / 'foreign-tool'
        target.write_bytes(b'foreign tool\n')
        self.commands[0].symlink_to(target)
        with self.assertRaises((OSError, RuntimeError)):
            m.install()
        self.assertTrue(self.commands[0].is_symlink())
        self.assertEqual(target.read_bytes(), b'foreign tool\n')
        self.commands[0].unlink()
        m.install()
        extra = self.support / 'foreign-extra'
        extra.write_bytes(b'keep\n')
        with self.assertRaisesRegex(RuntimeError, 'support drift'):
            m.uninstall()
        self.assertEqual(extra.read_bytes(), b'keep\n')
        self.assertTrue(all(path.exists() for path in self.commands))
        self.assert_preserved()

    def test_invalid_receipt_fails_with_readable_error_without_removal(self):
        m.install()
        (self.support / 'receipt.json').write_text('[]\n')
        with self.assertRaisesRegex(RuntimeError, 'invalid recovery receipt'):
            m.uninstall()
        self.assertTrue(all(path.exists() for path in self.commands))
        self.assert_preserved()

    def test_tool_install_and_remove_allow_present_reader_without_usb_or_service_calls(self):
        sysfs = self.root / 'sys/bus/usb/devices/1-4'
        sysfs.mkdir(parents=True)
        (sysfs / 'idVendor').write_text('27c6')
        (sysfs / 'idProduct').write_text('5125')
        original_iterdir = Path.iterdir
        def no_usb(path):
            self.assertNotIn('/sys/bus/usb', str(path))
            return original_iterdir(path)
        with patch.object(m.os, 'geteuid', return_value=0), \
                patch.object(m, 'run', return_value='') as command, \
                patch.object(Path, 'iterdir', no_usb):
            REAL_GATE()
            command.assert_called_once_with('systemd-detect-virt', '--vm', '--quiet')
        m.install()
        m.uninstall()
        self.assert_absent()
        self.assertFalse(any(call[0] == 'systemctl' for call in self.system_calls))
        self.assertEqual((sysfs / 'idVendor').read_text(), '27c6')

    def test_main_self_elevation_uses_fixed_interpreter_action_and_environment(self):
        for action in ('install', 'uninstall'):
            with self.subTest(action=action), patch.object(sys, 'argv', ['manage.py', action]), \
                    patch.object(m.os, 'geteuid', return_value=1000), \
                    patch.object(m.os, 'execve', side_effect=RuntimeError('synthetic exec')) as execute:
                with self.assertRaisesRegex(RuntimeError, 'synthetic exec'):
                    m.main()
                execute.assert_called_once_with('/usr/bin/sudo',
                    ['sudo', '--', '/usr/bin/python3', '-I', '-B', str(self.here / 'manage.py'), action], m.ENV)
        m.gate.assert_not_called()
        self.assert_absent()

    def test_main_root_dispatch_still_requires_gate(self):
        with patch.object(sys, 'argv', ['manage.py', 'install']), \
                patch.object(m.os, 'geteuid', return_value=0), \
                patch.object(m, 'gate') as gate, patch.object(m, 'install') as install, \
                patch.object(m, 'lifecycle_lock', return_value=123) as lock, \
                patch.object(m.os, 'close') as closed:
            m.main()
            gate.assert_called_once_with()
            install.assert_called_once_with()
            lock.assert_called_once_with()
            closed.assert_called_once_with(123)
        self.assert_absent()

    def test_busy_shared_lock_prevents_tool_mutation(self):
        with patch.object(m.os, 'open', return_value=123) as opened, \
                patch.object(m.fcntl, 'flock', side_effect=BlockingIOError('synthetic busy')) as flock, \
                patch.object(m.os, 'close') as closed:
            with self.assertRaisesRegex(RuntimeError, 'another Goodix lifecycle operation is active'):
                m.lifecycle_lock()
            opened.assert_called_once_with(m.LOCK_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            flock.assert_called_once_with(123, m.fcntl.LOCK_EX | m.fcntl.LOCK_NB)
            closed.assert_called_once_with(123)
        with patch.object(sys, 'argv', ['manage.py', 'install']), \
                patch.object(m.os, 'geteuid', return_value=0), patch.object(m, 'gate'), \
                patch.object(m, 'lifecycle_lock', side_effect=RuntimeError('active lifecycle operation')), \
                patch.object(m, 'install') as install:
            with self.assertRaisesRegex(RuntimeError, 'active lifecycle operation'):
                m.main()
            install.assert_not_called()
        self.assert_absent()

    def test_shared_lock_is_released_after_either_tool_action_fails(self):
        for action in ('install', 'uninstall'):
            with self.subTest(action=action), patch.object(sys, 'argv', ['manage.py', action]), \
                    patch.object(m.os, 'geteuid', return_value=0), patch.object(m, 'gate'), \
                    patch.object(m, 'lifecycle_lock', return_value=123), \
                    patch.object(m.os, 'close') as closed, \
                    patch.object(m, action, side_effect=RuntimeError('synthetic action failure')):
                with self.assertRaisesRegex(RuntimeError, 'synthetic action failure'):
                    m.main()
                closed.assert_called_once_with(123)
        self.assert_absent()

    def test_absent_library_parent_needs_no_new_lock_artifact(self):
        absent = self.root / 'absent-lib64'
        with patch.object(m, 'LOCK_DIRECTORY', absent), patch.object(m.os, 'open') as opened:
            self.assertIsNone(m.lifecycle_lock())
            opened.assert_not_called()
            self.assertFalse(absent.exists())
        self.assert_absent()

    def test_wrappers_resolve_own_path_from_foreign_cwd_without_privileges(self):
        (self.here / 'manage.py').write_text(
            'import json, os, sys\nprint(json.dumps([sys.argv[1:], os.getcwd()]))\n')
        for action in ('install', 'uninstall'):
            wrapper = self.here / (action + '.sh')
            wrapper.write_bytes((SOURCE / wrapper.name).read_bytes())
            result = subprocess.run(['/usr/bin/bash', str(wrapper)], cwd=self.foreign,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), [[action], str(self.foreign)])
            result = subprocess.run(['/usr/bin/bash', str(wrapper), 'unexpected'], cwd=self.foreign,
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
        self.assert_absent()


if __name__ == '__main__':
    unittest.main()
