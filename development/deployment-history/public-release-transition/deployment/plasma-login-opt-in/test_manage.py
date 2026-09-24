#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Temporary-file lifecycle tests. Host environment and commands are mocked."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('login_manage', Path(__file__).with_name('manage.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
ENVIRONMENT = m.environment


class Lifecycle(unittest.TestCase):
    def setUp(self):
        # Synthetic actions must not print misleading real-install PASS markers.
        quiet = patch('builtins.print')
        quiet.start()
        self.addCleanup(quiet.stop)
        self.temp = tempfile.TemporaryDirectory(prefix='goodix-login-manage-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'etc/pam.d/plasmalogin'
        self.support = self.root / 'usr/local/lib64/goodix-plasma-login'
        self.vendor = self.root / 'usr/lib/pam.d/plasmalogin'
        for path in (self.config, self.support, self.vendor):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.vendor.write_bytes(b'current vendor\n')
        self.vendor.chmod(0o644)
        for name, value in {'CONFIG': self.config, 'SUPPORT': self.support, 'VENDOR': self.vendor,
                            'OWNER': (os.getuid(), os.getgid())}.items():
            replacement = patch.object(m, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        for name, value in {'environment': None, 'parents': None}.items():
            replacement = patch.object(m, name, return_value=value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.commands = patch.object(m, 'run', side_effect=self.command).start()
        self.addCleanup(patch.stopall)
        self.output = self.root / 'build'
        self.output.mkdir()
        for name, data in {m.MODULE: b'synthetic gate', 'plasmalogin.pam': b'project PAM\n',
                           'manage.py': Path(m.__file__).read_bytes(), 'SOURCE_COMMIT': b'a' * 40 + b'\n',
                           'VM_TESTS_PASS': b'PASS\n'}.items():
            (self.output / name).write_bytes(data)
        self.manifest()

    def command(self, *args):
        if args[0] == 'systemd-detect-virt':
            self.assertEqual(args, ('systemd-detect-virt', '--vm', '--quiet'))
            return ''
        if args[0] == 'getenforce':
            return 'Enforcing'
        if args[0] == 'rpm':
            return 'plasma-login-manager'
        if args[0] == 'matchpathcon':
            return 'system_u:object_r:etc_t:s0'
        self.assertEqual(args[0], 'restorecon')
        self.assertFalse(self.config.exists(), 'PAM published before labeling')
        return ''

    def manifest(self):
        (self.output / 'SHA256SUMS').write_text(''.join(
            f'{m.digest((self.output / name).read_bytes())}  {name}\n' for name in m.INPUTS))

    def test_install_remove_current_vendor_and_idempotent_absence(self):
        m.install(self.output)
        self.assertEqual(self.config.read_bytes(), b'project PAM\n')
        self.assertEqual(self.vendor.read_bytes(), b'current vendor\n')
        self.vendor.write_bytes(b'updated vendor policy\n')
        removed = []
        original_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            removed.append(path)
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', unlink):
            m.uninstall()
        self.assertEqual(removed[0], self.config)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())
        self.assertEqual(self.vendor.read_bytes(), b'updated vendor policy\n')
        m.uninstall()

    def test_candidate_tamper_and_missing_pass_are_nonmutating(self):
        (self.output / m.MODULE).write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'digest'):
            m.install(self.output)
        self.manifest()
        (self.output / 'VM_TESTS_PASS').unlink()
        with self.assertRaises(FileNotFoundError):
            m.install(self.output)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())

    def test_collisions_symlinks_and_drift_are_preserved(self):
        self.config.symlink_to(self.vendor)
        with self.assertRaisesRegex(RuntimeError, 'collision'):
            m.install(self.output)
        self.config.unlink()
        m.install(self.output)
        self.config.write_bytes(b'foreign changed config')
        with self.assertRaisesRegex(RuntimeError, 'drift'):
            m.uninstall()
        self.assertEqual(self.config.read_bytes(), b'foreign changed config')
        self.assertTrue(self.support.exists())

    def test_failure_before_publish_returns_to_stock(self):
        def fail_label(*args):
            if args[0] == 'rpm':
                return self.command(*args)
            raise RuntimeError('label failure')
        self.commands.side_effect = fail_label
        with self.assertRaisesRegex(RuntimeError, 'label failure'):
            m.install(self.output)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())
        self.assertEqual(list(self.config.parent.iterdir()), [])

    def test_publish_race_preserves_foreign_file(self):
        def collision(*args, **kwargs):
            self.config.write_bytes(b'foreign appeared')
            raise FileExistsError('collision at atomic publish')
        with patch.object(m.os, 'link', side_effect=collision):
            with self.assertRaises(FileExistsError):
                m.install(self.output)
        self.assertEqual(self.config.read_bytes(), b'foreign appeared')
        self.assertFalse(self.support.exists())

    def test_missing_vendor_does_not_block_project_override_removal(self):
        m.install(self.output)
        self.vendor.unlink()
        self.vendor.parent.rmdir()
        with patch.object(m, 'vendor_ready', side_effect=AssertionError('vendor must not be inspected')):
            m.uninstall()
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())
        self.assertFalse(self.vendor.parent.exists(), 'uninstall must not restore Fedora paths')
        m.environment.assert_called_with(removal=True)
        m.uninstall()

    def test_vendor_replaced_by_foreign_symlink_is_untouched_on_removal(self):
        m.install(self.output)
        self.vendor.unlink()
        target = self.root / 'relocated-vendor'
        target.write_bytes(b'new Fedora configuration\n')
        self.vendor.symlink_to(target)
        m.uninstall()
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())
        self.assertTrue(self.vendor.is_symlink())
        self.assertEqual(target.read_bytes(), b'new Fedora configuration\n')

    def test_missing_vendor_does_not_relax_project_receipt_and_drift_checks(self):
        m.install(self.output)
        self.vendor.unlink()
        original_config = self.config.read_bytes()
        self.config.write_bytes(b'foreign changed config')
        with self.assertRaisesRegex(RuntimeError, 'configuration drift'):
            m.uninstall()
        self.assertEqual(self.config.read_bytes(), b'foreign changed config')
        self.assertTrue((self.support / m.MODULE).exists())
        self.config.write_bytes(original_config)
        (self.support / 'receipt.json').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing receipt'):
            m.uninstall()
        self.assertEqual(self.config.read_bytes(), original_config)
        self.assertTrue((self.support / m.MODULE).exists())

    def test_support_mode_drift_and_cleanup_resume(self):
        m.install(self.output)
        (self.support / m.MODULE).chmod(0o666)
        with self.assertRaisesRegex(RuntimeError, 'untrusted'):
            m.uninstall()
        (self.support / m.MODULE).chmod(0o644)
        self.config.unlink()
        m.uninstall()
        self.assertFalse(self.support.exists())

    def test_environment_rejects_before_system_mutations(self):
        with patch.object(m.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(RuntimeError, 'root required'):
                ENVIRONMENT()
        self.commands.assert_not_called()
        with patch.object(m.os, 'geteuid', return_value=0), patch.object(m.platform, 'freedesktop_os_release',
                return_value={'ID': 'other', 'VERSION_ID': '44'}), patch.object(m, 'run', return_value=''):
            with self.assertRaisesRegex(RuntimeError, 'Fedora 44'):
                ENVIRONMENT()

    def test_removal_environment_is_independent_of_fedora_and_selinux_version(self):
        with patch.object(m.os, 'geteuid', return_value=0), \
                patch.object(m.platform, 'freedesktop_os_release',
                             side_effect=AssertionError('removal must not inspect Fedora release')), \
                patch.object(m.platform, 'machine',
                             side_effect=AssertionError('removal must not inspect architecture')), \
                patch.object(m, 'run', return_value='') as commands:
            ENVIRONMENT(removal=True)
            commands.assert_called_once_with('systemd-detect-virt', '--vm', '--quiet')

    def test_install_and_remove_with_reader_present_never_inspect_or_open_usb(self):
        device = self.root / 'sys/bus/usb/devices/1-1'
        device.mkdir(parents=True)
        (device / 'idVendor').write_text('27c6\n')
        (device / 'idProduct').write_text('5125\n')
        original_iterdir = Path.iterdir
        original_open = os.open

        def guarded_iterdir(path):
            self.assertNotEqual(str(path), '/sys/bus/usb/devices')
            self.assertFalse(path == device.parent or device.parent in path.parents,
                             'login lifecycle must not inspect synthetic USB presence')
            return original_iterdir(path)

        def guarded_open(path, *args, **kwargs):
            self.assertFalse(str(path).startswith(('/dev/bus/usb/', '/sys/bus/usb/')),
                             'login lifecycle attempted direct USB access')
            return original_open(path, *args, **kwargs)

        with patch.object(m, 'environment', side_effect=ENVIRONMENT), \
                patch.object(m.os, 'geteuid', return_value=0), \
                patch.object(m.platform, 'freedesktop_os_release',
                             return_value={'ID': 'fedora', 'VERSION_ID': '44'}), \
                patch.object(m.platform, 'machine', return_value='x86_64'), \
                patch.object(Path, 'iterdir', guarded_iterdir), patch.object(m.os, 'open', guarded_open):
            m.install(self.output)
            self.assertTrue(self.config.exists())
            m.uninstall()
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())
        self.assertEqual((device / 'idVendor').read_text(), '27c6\n')
        self.assertEqual((device / 'idProduct').read_text(), '5125\n')

    def qualified_output(self):
        # Exercise the exact compatibility gate with synthetic pinned inputs.
        # Public source exports deliberately omit private Git history; original
        # pin provenance is checked separately during internal release review.
        fixtures = {'manage.py': b'# synthetic previous manager; never executed\n',
                    'plasmalogin.pam': b'synthetic qualified PAM\n'}
        pins = patch.multiple(m,
                              QUALIFIED_MANAGER_SHA256=m.digest(fixtures['manage.py']),
                              QUALIFIED_PAM_SHA256=m.digest(fixtures['plasmalogin.pam']))
        pins.start()
        self.addCleanup(pins.stop)
        for name, data in fixtures.items():
            (self.output / name).write_bytes(data)
        (self.output / 'SOURCE_COMMIT').write_text(m.QUALIFIED_SOURCE + '\n')
        self.manifest()

    def test_qualified_preserved_output_saves_current_inverse_and_keeps_manifest(self):
        self.qualified_output()
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        m.install(self.output)
        self.assertEqual({path.name: path.read_bytes() for path in self.output.iterdir()}, before)
        self.assertEqual((self.support / m.MODULE).read_bytes(), before[m.MODULE])
        self.assertEqual(self.config.read_bytes(), before['plasmalogin.pam'])
        current_manager = Path(m.__file__).read_bytes()
        self.assertEqual((self.support / 'manage.py').read_bytes(), current_manager)
        receipt = json.loads((self.support / 'receipt.json').read_bytes())
        self.assertEqual(receipt['source_commit'], m.QUALIFIED_SOURCE)
        self.assertEqual(receipt['input_manager_sha256'], m.QUALIFIED_MANAGER_SHA256)
        self.assertEqual(receipt['files']['manage.py'], m.digest(current_manager))
        # Execute the saved inverse implementation against the synthetic tree.
        saved_spec = importlib.util.spec_from_file_location('saved_login_inverse', self.support / 'manage.py')
        saved = importlib.util.module_from_spec(saved_spec)
        with patch.object(sys, 'dont_write_bytecode', True):
            saved_spec.loader.exec_module(saved)
        with patch.multiple(saved, CONFIG=self.config, SUPPORT=self.support, VENDOR=self.vendor,
                            OWNER=(os.getuid(), os.getgid())), \
                patch.object(saved, 'environment'), patch.object(saved, 'parents'):
            saved.uninstall()
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())

    def test_unknown_manager_or_qualified_pam_drift_is_rejected_even_with_new_manifest(self):
        self.qualified_output()
        manager = self.output / 'manage.py'
        original = manager.read_bytes()
        manager.write_bytes(original + b'\n# altered manager\n')
        self.manifest()
        with self.assertRaisesRegex(RuntimeError, 'unsupported candidate manager'):
            m.install(self.output)
        manager.write_bytes(original)
        (self.output / 'plasmalogin.pam').write_bytes(b'unqualified PAM\n')
        self.manifest()
        with self.assertRaisesRegex(RuntimeError, 'unsupported candidate manager'):
            m.install(self.output)
        self.qualified_output()
        (self.output / 'SOURCE_COMMIT').write_text('b' * 40 + '\n')
        self.manifest()
        with self.assertRaisesRegex(RuntimeError, 'unsupported candidate manager'):
            m.install(self.output)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())

    def test_current_inverse_accepts_original_receipt_shape(self):
        m.install(self.output)
        receipt_path = self.support / 'receipt.json'
        receipt = json.loads(receipt_path.read_bytes())
        del receipt['input_manager_sha256']
        receipt_path.write_text(json.dumps(receipt) + '\n')
        m.uninstall()
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())

    def test_missing_module_with_active_config_can_be_uninstalled(self):
        m.install(self.output)
        (self.support / m.MODULE).unlink()
        m.uninstall()
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())

    def test_interrupted_payload_removal_can_resume_from_identical_inverse(self):
        m.install(self.output)
        original_unlink = Path.unlink
        def interrupt(path, *args, **kwargs):
            if path == self.support / 'receipt.json':
                raise OSError('interrupted after config and payload removal')
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', interrupt):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                m.uninstall()
        self.assertFalse(self.config.exists())
        self.assertEqual({p.name for p in self.support.iterdir()}, {'receipt.json'})
        m.uninstall()
        self.assertFalse(self.support.exists())
        self.support.mkdir(mode=0o755)
        m.uninstall()
        self.assertFalse(self.support.exists())

    def test_candidate_fifo_is_rejected_without_waiting_for_a_writer(self):
        module = self.output / m.MODULE
        module.unlink()
        os.mkfifo(module)
        with self.assertRaisesRegex(RuntimeError, 'not a regular file'):
            m.install(self.output)
        self.assertFalse(self.support.exists())

    def test_main_serializes_both_actions_and_closes_lock_after_failure(self):
        for action, args in (('install', ['install', str(self.output)]), ('uninstall', ['uninstall'])):
            with self.subTest(action=action), patch.object(sys, 'argv', ['manage.py', *args]), \
                    patch.object(m.os, 'geteuid', return_value=0), \
                    patch.object(m, 'lifecycle_lock', return_value=123) as lock, \
                    patch.object(m.os, 'close') as close, \
                    patch.object(m, action, side_effect=RuntimeError('synthetic action failure')) as operation:
                with self.assertRaisesRegex(RuntimeError, 'synthetic action failure'):
                    m.main()
                lock.assert_called_once_with()
                operation.assert_called_once_with(*([self.output] if action == 'install' else []))
                close.assert_called_once_with(123)

    def test_busy_shared_lock_fails_before_any_install_or_remove_operation(self):
        with patch.object(m.os, 'open', return_value=123) as opened, \
                patch.object(m.fcntl, 'flock', side_effect=BlockingIOError('synthetic busy')) as flock, \
                patch.object(m.os, 'close') as closed:
            with self.assertRaisesRegex(RuntimeError, 'another Goodix lifecycle operation is active'):
                m.lifecycle_lock()
            opened.assert_called_once_with(self.support.parent,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            flock.assert_called_once_with(123, m.fcntl.LOCK_EX | m.fcntl.LOCK_NB)
            closed.assert_called_once_with(123)
        with patch.object(sys, 'argv', ['manage.py', 'uninstall']), \
                patch.object(m.os, 'geteuid', return_value=0), \
                patch.object(m, 'lifecycle_lock', side_effect=RuntimeError('active lifecycle operation')), \
                patch.object(m, 'uninstall') as uninstall:
            with self.assertRaisesRegex(RuntimeError, 'active lifecycle operation'):
                m.main()
            uninstall.assert_not_called()
        self.assertFalse(self.config.exists())
        self.assertFalse(self.support.exists())


if __name__ == '__main__':
    unittest.main()
