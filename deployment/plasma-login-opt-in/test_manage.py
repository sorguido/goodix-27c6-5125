#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Temporary-file lifecycle tests. Host environment and commands are mocked."""
import importlib.util
import os
from pathlib import Path
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
        usb = self.root / 'synthetic-usb'
        usb.mkdir()
        with patch.object(m.os, 'geteuid', return_value=0), patch.object(m, 'USB', usb), \
                patch.object(m.platform, 'freedesktop_os_release',
                             side_effect=AssertionError('removal must not inspect Fedora release')), \
                patch.object(m.platform, 'machine',
                             side_effect=AssertionError('removal must not inspect architecture')), \
                patch.object(m, 'run', return_value='') as commands:
            ENVIRONMENT(removal=True)
            commands.assert_called_once_with('systemd-detect-virt', '--vm', '--quiet')
            device = usb / '1-1'
            device.mkdir()
            (device / 'idVendor').write_text('27c6\n')
            (device / 'idProduct').write_text('5125\n')
            with self.assertRaisesRegex(RuntimeError, 'detach Goodix'):
                ENVIRONMENT(removal=True)

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


if __name__ == '__main__':
    unittest.main()
