#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""R5 filesystem tests: synthetic data only; every host operation is mocked."""
import contextlib
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).with_name('remove.py')


def load(source=SOURCE):
    spec = importlib.util.spec_from_loader('goodix_recovery_test_target',
                                          SourceFileLoader('goodix_recovery_test_target', str(source)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='goodix-r5-synthetic-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.m = load()
        self.bind(self.m)
        self.m.MASK.parent.mkdir(parents=True)
        self.sysfs = self.root / 'sys/bus/usb/devices/1-4'
        self.write(self.sysfs / 'idVendor', b'27c6')
        self.write(self.sysfs / 'idProduct', b'5125')
        self.events = []
        self.active = True
        self.rule = True
        self.fail = None
        self.output = io.StringIO()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(self.output))
        self.stack.enter_context(contextlib.redirect_stderr(self.output))
        self.real_command = self.m.command
        self.m.command = self.command
        self.m.trusted = self.trusted
        self.vendor = self.root / 'usr/lib/pam.d/plasmalogin'
        self.foreign_dropin = self.m.DROPIN.parent / '80-unrelated.conf'
        self.template = self.root / 'var/lib/fprint/test-user/driver/template'
        self.write(self.vendor, b'current Fedora vendor bytes\n')
        self.write(self.foreign_dropin, b'unrelated configuration\n')
        self.write(self.template, b'SYNTHETIC TEMPLATE SENTINEL')
        for name in self.m.MATERIAL_NAMES:
            self.write(self.m.MATERIAL / name, b'SYNTHETIC PRESERVED ' + name.encode(), 0o600)
        self.m.MATERIAL.chmod(0o700)
        self.protected_before = self.preserved_snapshot()
        self.install_fixture()

    def bind(self, module):
        for name in ('CONFIG', 'SUPPORT', 'RUNTIME', 'DROPIN', 'NORMAL', 'FORCE', 'RECOVERY', 'MATERIAL', 'MASK'):
            setattr(module, name, self.root / str(getattr(module, name)).lstrip('/'))

    def write(self, path, value, mode=0o644):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        path.chmod(mode)

    def trusted(self, path, directory=False):
        # The production ownership requirement remains tested in source separately;
        # fixtures are owned by the unprivileged test UID/GID, never chowned/root.
        self.m.parents(path)
        info = path.lstat()
        self.m.require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
                       and (info.st_uid, info.st_gid) == (os.geteuid(), os.getegid())
                       and not info.st_mode & 0o022, f'project ownership/type/mode drift: {path}')

    def install_fixture(self):
        m = self.m
        self.write(m.CONFIG, b'SYNTHETIC PROJECT PAM ENTRY\n')
        login_files = {m.MODULE: b'SYNTHETIC LOGIN MODULE', 'manage.py': b'SYNTHETIC OLD INVERSE'}
        for name, data in login_files.items():
            self.write(m.SUPPORT / name, data)
        login_receipt = {'schema': 1, 'source_commit': '6fc6e640710885954d9e6fd603b3bc47b45d2ac6',
                         'files': {name: m.digest(data) for name, data in login_files.items()},
                         'config_sha256': m.digest(m.CONFIG.read_bytes())}
        self.write(m.SUPPORT / 'receipt.json', json.dumps(login_receipt).encode())
        runtime_files = {name: b'SYNTHETIC PAYLOAD ' + name.encode() for name in m.RUNTIME_FILES}
        for name, data in runtime_files.items():
            self.write(m.RUNTIME / name, data)
        for name, target in m.LINKS.items():
            (m.RUNTIME / name).symlink_to(target)
        material = {'rule': m.RULE, 'context': 'system_u:object_r:fprintd_var_lib_t:s0',
                    'owned': True, 'preexisting': False, 'phase': 'ready',
                    'metadata': [[1, 2, 0, 0, 0o100600, 16, 1234]] * 6,
                    'before_contexts': ['unconfined_u:object_r:var_lib_t:s0'] +
                                       ['system_u:object_r:var_lib_t:s0'] * 5,
                    'manifest_sha256': '1b98bf54925cf9608ee8bf4e7d2f811f535c3c9395ea2eaf38fe18fb017aacc8'}
        runtime_receipt = {'schema': 1, 'build_commit': 'b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226',
                           'install_commit': '264cd7ff1ba77857e1985502f299e4375f9a0516',
                           'material_label_commit': '7f5a896' + '0' * 33,
                           'previous_service': 'active', 'created_dropin_directory': True,
                           'material_selinux': material, 'material_manifest_reconciled': True,
                           'files': {name: m.digest(data) for name, data in runtime_files.items()}}
        self.write(m.RUNTIME / 'installation.json', json.dumps(runtime_receipt).encode(), 0o600)
        self.write(m.DROPIN, m.DROPIN_BYTES)
        recovery_files = {}
        for path in (m.NORMAL, m.FORCE):
            self.write(path, SOURCE.read_bytes(), 0o755)
            recovery_files[path.name] = m.digest(path.read_bytes())
        self.write(m.RECOVERY / 'receipt.json', json.dumps({'schema': 1, 'files': recovery_files}).encode())

    def command(self, *args):
        # Capture whether authentication was detached before any host command.
        self.events.append((args, self.m.present(self.m.CONFIG), self.m.present(self.m.DROPIN)))
        if self.fail and args[:len(self.fail)] == self.fail:
            raise RuntimeError('synthetic command failure: ' + ' '.join(args))
        if args == ('systemctl', 'daemon-reload'):
            return ''
        if args == ('systemctl', 'stop', 'fprintd.service'):
            self.active = False
            return ''
        if args == ('systemctl', 'show', 'fprintd.service', '--property=ActiveState', '--property=MainPID', '--property=LoadState'):
            return 'ActiveState=active\nMainPID=42\nLoadState=masked\n' if self.active else 'ActiveState=inactive\nMainPID=0\nLoadState=masked\n'
        if args == ('semanage', 'fcontext', '-l', '-C', '-n'):
            return ('/unrelated(/.*)? all files system_u:object_r:var_lib_t:s0\n' +
                    (self.m.RULE + ' all files system_u:object_r:fprintd_var_lib_t:s0\n' if self.rule else ''))
        if args == ('semanage', 'fcontext', '-d', '-f', 'a', self.m.RULE):
            self.rule = False
            return ''
        if args[:3] == ('restorecon', '-F', '--'):
            expected = tuple(str(p) for p in (self.m.MATERIAL,
                             *(self.m.MATERIAL / name for name in self.m.MATERIAL_NAMES)))
            self.assertEqual(args[3:], expected)
            return ''
        raise AssertionError('unmocked host operation attempted: ' + repr(args))

    def preserved_snapshot(self):
        paths = [self.vendor, self.foreign_dropin, self.template,
                 *(self.m.MATERIAL / name for name in self.m.MATERIAL_NAMES)]
        return {path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode),
                       path.stat().st_uid, path.stat().st_gid, path.stat().st_mtime_ns)
                for path in paths if path.exists()}

    def assert_preserved(self):
        self.assertEqual(self.preserved_snapshot(), self.protected_before)

    def assert_removed(self):
        for path in (self.m.CONFIG, self.m.SUPPORT, self.m.RUNTIME, self.m.DROPIN,
                     self.m.NORMAL, self.m.FORCE, self.m.RECOVERY):
            self.assertFalse(self.m.present(path), str(path))
        self.assertFalse(self.active)
        self.assertFalse(self.m.MASK.exists() or self.m.MASK.is_symlink())
        self.assert_preserved()
        self.assertTrue(self.events)
        self.assertTrue(all(not login and not dropin for _args, login, dropin in self.events))
        self.assertFalse(any(args[:2] in (('systemctl', 'start'), ('systemctl', 'restart'))
                             for args, _login, _dropin in self.events))

    def remove_vendor(self):
        self.vendor.unlink()
        del self.protected_before[self.vendor]

    def change_runtime_receipt(self, mutate):
        path = self.m.RUNTIME / 'installation.json'
        receipt = json.loads(path.read_bytes())
        mutate(receipt)
        self.write(path, json.dumps(receipt).encode(), 0o600)

    def test_normal_complete_install(self):
        self.assertEqual(self.m.remove(), 0)
        self.assert_removed()
        self.assertFalse(self.rule)

    def test_normal_vendor_missing(self):
        self.remove_vendor()
        self.assertEqual(self.m.remove(), 0)
        self.assert_removed()

    def test_normal_drift_refuses_before_any_mutation(self):
        self.write(self.m.RUNTIME / self.m.LIBRARIES[0], b'DRIFTED PROJECT LIBRARY')
        with self.assertRaisesRegex(RuntimeError, 'project file drift'):
            self.m.remove()
        self.assertTrue(self.m.CONFIG.exists())
        self.assertTrue(self.m.DROPIN.exists())
        self.assertTrue(self.m.FORCE.exists())
        self.assertEqual(self.events, [])
        self.assert_preserved()

    def test_normal_login_drift_refuses_before_mutation(self):
        self.write(self.m.CONFIG, b'DRIFTED PAM')
        with self.assertRaisesRegex(RuntimeError, 'configuration drift'):
            self.m.remove()
        self.assertEqual(self.events, [])
        self.assertTrue(self.m.RUNTIME.exists())

    def test_normal_recovery_drift_refuses_before_mutation(self):
        self.write(self.m.FORCE, b'DRIFTED RECOVERY', 0o755)
        with self.assertRaisesRegex(RuntimeError, 'recovery command drift'):
            self.m.remove()
        self.assertEqual(self.events, [])
        self.assertTrue(self.m.CONFIG.exists())

    def test_normal_unowned_mapping_preserved(self):
        self.change_runtime_receipt(lambda value: value['material_selinux'].update(owned=False, preexisting=True))
        self.assertEqual(self.m.remove(), 0)
        self.assert_removed()
        self.assertTrue(self.rule)
        self.assertFalse(any(args[0] in ('semanage', 'restorecon') for args, *_rest in self.events))

    def test_normal_bad_receipt_refuses_before_mutation(self):
        self.change_runtime_receipt(lambda value: value.update(build_commit='0' * 40))
        with self.assertRaisesRegex(RuntimeError, 'unknown runtime receipt'):
            self.m.remove()
        self.assertEqual(self.events, [])
        self.assertTrue(self.m.CONFIG.exists())

    def test_normal_nonobject_receipts_refuse_before_mutation(self):
        for path in (self.m.SUPPORT / 'receipt.json', self.m.RUNTIME / 'installation.json',
                     self.m.RECOVERY / 'receipt.json'):
            original = path.read_bytes()
            for value in (None, [], 'unexpected'):
                with self.subTest(path=path, value=value):
                    self.write(path, json.dumps(value).encode())
                    with self.assertRaisesRegex(RuntimeError, 'invalid .* receipt'):
                        self.m.remove()
                    self.assertEqual(self.events, [])
                    self.assertTrue(self.m.CONFIG.exists())
            self.write(path, original)

    def test_normal_writable_project_payload_refuses_before_mutation(self):
        (self.m.SUPPORT / self.m.MODULE).chmod(0o666)
        with self.assertRaisesRegex(RuntimeError, 'ownership/type/mode drift'):
            self.m.remove()
        self.assertEqual(self.events, [])
        self.assertTrue(self.m.CONFIG.exists())

    def test_force_complete_install_active_service(self):
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()
        self.assertFalse(self.rule)

    def test_force_inactive_service(self):
        self.active = False
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_force_vendor_missing(self):
        self.remove_vendor()
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_force_all_receipts_missing(self):
        for path in (self.m.SUPPORT / 'receipt.json', self.m.RUNTIME / 'installation.json',
                     self.m.RECOVERY / 'receipt.json'):
            path.unlink()
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_force_partial_runtime(self):
        shutil.rmtree(self.m.RUNTIME)
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_force_partial_login(self):
        shutil.rmtree(self.m.SUPPORT)
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_force_missing_activation_entries(self):
        self.m.CONFIG.unlink()
        self.m.DROPIN.unlink()
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_force_idempotent_repeat(self):
        self.assertEqual(self.m.remove(force=True), 0)
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_force_selinux_failure_disarms_first_retains_tools(self):
        self.fail = ('semanage', 'fcontext', '-d')
        self.assertEqual(self.m.remove(force=True), 1)
        for path in (self.m.CONFIG, self.m.DROPIN, self.m.SUPPORT):
            self.assertFalse(self.m.present(path))
        for path in (self.m.NORMAL, self.m.FORCE, self.m.RECOVERY, self.m.RUNTIME):
            self.assertTrue(path.exists())
        self.assertTrue(self.rule)
        self.assertFalse(self.active)
        self.assertTrue(all(not login and not dropin for _args, login, dropin in self.events))
        self.assertIn('GOODIX_REMOVAL=INCOMPLETE', self.output.getvalue())
        self.assert_preserved()
        self.fail = None
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_force_stop_failure_retains_tools_reports_incomplete(self):
        self.fail = ('systemctl', 'stop')
        self.assertEqual(self.m.remove(force=True), 1)
        self.assertFalse(self.m.CONFIG.exists())
        self.assertFalse(self.m.DROPIN.exists())
        self.assertTrue(self.m.FORCE.exists())
        self.assertIn('GOODIX_REMOVAL=INCOMPLETE', self.output.getvalue())
        self.assertNotIn('GOODIX_REMOVAL=PASS', self.output.getvalue())
        self.assert_preserved()

    def test_force_runtime_symlink_does_not_follow(self):
        shutil.rmtree(self.m.RUNTIME)
        outside = self.root / 'unrelated-data'
        self.write(outside / 'keep', b'UNRELATED')
        self.m.RUNTIME.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.m.remove(force=True), 0)
        self.assertEqual((outside / 'keep').read_bytes(), b'UNRELATED')
        self.assert_removed()

    def test_force_internal_symlink_does_not_follow(self):
        outside = self.root / 'unrelated-data'
        self.write(outside / 'keep', b'UNRELATED')
        (self.m.RUNTIME / 'redirected').symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.m.remove(force=True), 0)
        self.assertEqual((outside / 'keep').read_bytes(), b'UNRELATED')
        self.assert_removed()

    def test_force_redirected_pam_parent_refuses_traversal(self):
        original = self.m.CONFIG.parent
        outside = self.root / 'unrelated-pam'
        original.rename(outside)
        original.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.m.remove(force=True), 1)
        self.assertEqual((outside / 'plasmalogin').read_bytes(), b'SYNTHETIC PROJECT PAM ENTRY\n')
        self.assertTrue(self.m.SUPPORT.exists())
        self.assertTrue(self.m.FORCE.exists())
        self.assertIn('redirected parent', self.output.getvalue())
        self.assert_preserved()

    def test_force_material_symlink_is_preserved(self):
        material_file = self.m.MATERIAL / self.m.MATERIAL_NAMES[0]
        before = self.protected_before.pop(material_file)
        material_file.unlink()
        outside = self.root / 'unrelated-material'
        self.write(outside, before[0], 0o600)
        material_file.symlink_to(outside)
        self.assertEqual(self.m.remove(force=True), 1)
        self.assertTrue(material_file.is_symlink())
        self.assertEqual(outside.read_bytes(), before[0])
        self.assertTrue(self.m.FORCE.exists())
        self.assertFalse(self.m.CONFIG.exists())
        self.assertFalse(any(args[0] == 'restorecon' for args, *_rest in self.events))

    def test_force_material_hardlink_is_preserved_without_relabel(self):
        material_file = self.m.MATERIAL / self.m.MATERIAL_NAMES[0]
        outside = self.root / 'unrelated-hardlink'
        os.link(material_file, outside)
        before = outside.read_bytes()
        self.assertEqual(self.m.remove(force=True), 1)
        self.assertEqual(outside.read_bytes(), before)
        self.assertEqual(material_file.stat().st_nlink, 2)
        self.assertTrue(self.m.FORCE.exists())
        self.assertTrue(self.m.RUNTIME.exists())
        self.assertFalse(self.m.CONFIG.exists())
        self.assertFalse(any(args[0] == 'restorecon' for args, *_rest in self.events))
        self.assert_preserved()

    def test_force_nonregular_material_preserved_without_relabel(self):
        material_file = self.m.MATERIAL / self.m.MATERIAL_NAMES[0]
        material_file.unlink()
        material_file.mkdir()
        self.assertEqual(self.m.remove(force=True), 1)
        self.assertTrue(material_file.is_dir())
        self.assertTrue(self.m.FORCE.exists())
        self.assertTrue(self.m.RUNTIME.exists())
        self.assertFalse(self.m.CONFIG.exists())
        self.assertFalse(any(args[0] == 'restorecon' for args, *_rest in self.events))

    def test_force_never_reads_protected_file_contents(self):
        original_read = self.m.read
        def guard(path):
            self.assertFalse(path == self.m.MATERIAL or self.m.MATERIAL in path.parents)
            self.assertFalse(path == self.template)
            return original_read(path)
        self.m.read = guard
        self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_normal_never_reads_protected_file_contents(self):
        original_read = self.m.read
        def guard(path):
            self.assertFalse(path == self.m.MATERIAL or self.m.MATERIAL in path.parents)
            self.assertFalse(path == self.template)
            return original_read(path)
        self.m.read = guard
        self.assertEqual(self.m.remove(), 0)
        self.assert_removed()

    def test_relocated_saved_command_without_repository_or_build(self):
        repository = self.root / 'home/test/source-checkout'
        build = self.root / 'home/test/build-output'
        self.write(repository / 'sentinel', b'REPOSITORY')
        self.write(build / 'sentinel', b'BUILD')
        shutil.rmtree(repository)
        shutil.rmtree(build)
        installed = load(self.m.FORCE)
        self.bind(installed)
        installed.command = self.command
        installed.trusted = self.trusted
        with mock.patch.object(installed.os, 'geteuid', return_value=0), \
                mock.patch.object(installed.sys, 'argv', [str(installed.FORCE)]):
            self.assertEqual(installed.main(), 0)
        self.assert_removed()

    def test_main_requests_fixed_sudo_invocation(self):
        class Executed(Exception):
            pass
        for path in (self.m.NORMAL, self.m.FORCE):
            with self.subTest(command=path.name), \
                    mock.patch.object(self.m.os, 'geteuid', return_value=1000), \
                    mock.patch.object(self.m.os, 'execve', side_effect=Executed) as execute, \
                    mock.patch.object(self.m.sys, 'argv', [path.name]):
                with self.assertRaises(Executed):
                    self.m.main()
                execute.assert_called_once_with('/usr/bin/sudo',
                    ['sudo', '--', '/usr/bin/python3', '-I', '-B', str(path)], self.m.ENV)
        self.assertEqual(self.events, [])

    def test_main_root_dispatches_correct_removal(self):
        for path, force in ((self.m.NORMAL, False), (self.m.FORCE, True)):
            with self.subTest(command=path.name), \
                    mock.patch.object(self.m.os, 'geteuid', return_value=0), \
                    mock.patch.object(self.m, 'remove', return_value=0) as remove, \
                    mock.patch.object(self.m.sys, 'argv', [str(path)]):
                self.assertEqual(self.m.main(), 0)
                remove.assert_called_once_with(force=force)

    def test_reader_presence_is_not_consulted_by_normal_or_force_removal(self):
        for force in (False, True):
            with self.subTest(force=force):
                if force:
                    self.install_fixture()
                original = Path.iterdir
                def no_usb_inspection(path):
                    self.assertNotIn('/sys/bus/usb', str(path), 'lifecycle must not inspect/open USB')
                    return original(path)
                with mock.patch.object(Path, 'iterdir', no_usb_inspection):
                    self.assertEqual(self.m.remove(force=force), 0)
                self.assertEqual((self.sysfs / 'idVendor').read_bytes(), b'27c6')
                self.assertEqual((self.sysfs / 'idProduct').read_bytes(), b'5125')
                self.assert_removed()

    def test_mask_blocks_activation_during_runtime_and_label_removal(self):
        original_remove = self.m.remove_path
        original_label = self.m.remove_label
        def remove_path(path):
            if path == self.m.RUNTIME:
                self.assertEqual(os.readlink(self.m.MASK), '/dev/null')
                self.assertFalse(self.active)
            return original_remove(path)
        def remove_label():
            self.assertEqual(os.readlink(self.m.MASK), '/dev/null')
            self.assertFalse(self.active)
            return original_label()
        with mock.patch.object(self.m, 'remove_path', side_effect=remove_path), \
                mock.patch.object(self.m, 'remove_label', side_effect=remove_label):
            self.assertEqual(self.m.remove(force=True), 0)
        self.assert_removed()

    def test_unquiesced_service_retains_runtime_and_material_labels(self):
        original = self.m.command
        def active_despite_stop(*args):
            if args[:2] == ('systemctl', 'show'):
                return 'ActiveState=deactivating\nMainPID=42\n'
            return original(*args)
        self.m.command = active_despite_stop
        self.assertEqual(self.m.remove(force=True), 1)
        self.assertTrue(self.m.RUNTIME.exists())
        self.assertTrue(self.rule)
        self.assertFalse(self.m.CONFIG.exists())
        self.assertFalse(self.m.DROPIN.exists())
        self.assertFalse(self.m.MASK.is_symlink())
        self.assertIn('has not quiesced', self.output.getvalue())
        self.assertTrue(self.m.FORCE.exists())
        self.assert_preserved()

    def test_shadowed_mask_cannot_allow_runtime_mutation(self):
        original = self.m.command
        def shadowed(*args):
            if args[:2] == ('systemctl', 'show'):
                return 'ActiveState=inactive\nMainPID=0\nLoadState=loaded\n'
            return original(*args)
        self.m.command = shadowed
        self.assertEqual(self.m.remove(force=True), 1)
        self.assertTrue(self.m.RUNTIME.exists())
        self.assertTrue(self.rule)
        self.assertFalse(self.m.CONFIG.exists())
        self.assertFalse(self.m.DROPIN.exists())
        self.assertFalse(self.m.MASK.is_symlink())
        self.assertTrue(self.m.FORCE.exists())
        self.assert_preserved()

    def test_concurrent_lifecycle_is_rejected_before_mutations(self):
        fd = os.open(self.m.RUNTIME.parent, os.O_RDONLY | os.O_DIRECTORY)
        self.m.fcntl.flock(fd, self.m.fcntl.LOCK_EX | self.m.fcntl.LOCK_NB)
        try:
            with mock.patch.object(self.m.os, 'geteuid', return_value=0), \
                    mock.patch.object(self.m.sys, 'argv', [str(self.m.FORCE)]):
                with self.assertRaisesRegex(RuntimeError, 'another Goodix lifecycle'):
                    self.m.main()
            self.assertTrue(self.m.CONFIG.exists())
            self.assertEqual(self.events, [])
        finally:
            os.close(fd)

    def test_existing_runtime_mask_is_preserved(self):
        self.m.MASK.symlink_to('/dev/null')
        before = self.m.MASK.lstat()
        self.assertEqual(self.m.remove(force=True), 0)
        self.assertEqual(self.m.MASK.lstat().st_ino, before.st_ino)
        self.assertEqual(os.readlink(self.m.MASK), '/dev/null')
        self.assertFalse(self.m.RUNTIME.exists())
        self.assert_preserved()

    def test_mask_collision_still_disarms_auth_and_retains_runtime(self):
        self.write(self.m.MASK, b'foreign override')
        self.assertEqual(self.m.remove(force=True), 1)
        self.assertFalse(self.m.CONFIG.exists())
        self.assertFalse(self.m.DROPIN.exists())
        self.assertTrue(self.m.RUNTIME.exists())
        self.assertEqual(self.m.MASK.read_bytes(), b'foreign override')
        self.assert_preserved()

    def test_interruption_releases_only_own_temporary_mask(self):
        with mock.patch.object(self.m, 'remove_label', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.m.remove(force=True)
        self.assertFalse(self.m.MASK.is_symlink())
        self.assertTrue(self.m.RUNTIME.exists())
        self.assertTrue(self.m.FORCE.exists())
        self.assert_preserved()

    def test_lstat_failure_after_mask_creation_reports_unconfirmed_ownership(self):
        original_lstat = Path.lstat
        failed = False
        def fail_acquisition(path, *args, **kwargs):
            nonlocal failed
            if path == self.m.MASK and not failed:
                failed = True
                raise OSError('synthetic post-create metadata failure')
            return original_lstat(path, *args, **kwargs)
        with mock.patch.object(Path, 'lstat', fail_acquisition):
            self.assertEqual(self.m.remove(force=True), 1)
        self.assertTrue(self.m.MASK.is_symlink())
        self.assertEqual(os.readlink(self.m.MASK), '/dev/null')
        self.assertIn('FPRINTD_MASK_ACQUISITION=INCOMPLETE', self.output.getvalue())
        self.assertIn('ownership could not be established', self.output.getvalue())
        self.assertTrue(self.m.RUNTIME.exists())
        self.assertTrue(self.m.FORCE.exists())
        self.assert_preserved()

    def test_interruption_during_mask_creation_reports_and_preserves_unknown_mask(self):
        original_symlink = Path.symlink_to
        def interrupt_after_create(path, *args, **kwargs):
            original_symlink(path, *args, **kwargs)
            if path == self.m.MASK:
                raise KeyboardInterrupt('synthetic interruption after symlink')
        with mock.patch.object(Path, 'symlink_to', interrupt_after_create):
            with self.assertRaises(KeyboardInterrupt):
                self.m.remove(force=True)
        self.assertTrue(self.m.MASK.is_symlink())
        self.assertIn('FPRINTD_MASK_ACQUISITION=INCOMPLETE', self.output.getvalue())
        self.assertTrue(self.m.RUNTIME.exists())
        self.assertTrue(self.m.FORCE.exists())
        self.assert_preserved()

    def test_replaced_mask_during_acquisition_is_never_deleted(self):
        original_lstat = Path.lstat
        replaced = False
        def replace_before_identity(path, *args, **kwargs):
            nonlocal replaced
            if path == self.m.MASK and not replaced:
                replaced = True
                path.unlink()
                path.write_bytes(b'foreign replacement unit')
                raise OSError('synthetic replacement during acquisition')
            return original_lstat(path, *args, **kwargs)
        with mock.patch.object(Path, 'lstat', replace_before_identity):
            self.assertEqual(self.m.remove(force=True), 1)
        self.assertEqual(self.m.MASK.read_bytes(), b'foreign replacement unit')
        self.assertIn('ownership could not be established', self.output.getvalue())
        self.assertTrue(self.m.RUNTIME.exists())
        self.assert_preserved()

    def test_command_absent_fprintd_stop_is_benign(self):
        for reason in ('not loaded', 'not found'):
            result = self.m.subprocess.CompletedProcess([], 5, '',
                f'Failed to stop fprintd.service: Unit fprintd.service {reason}.\n')
            with self.subTest(reason=reason), \
                    mock.patch.object(self.m.subprocess, 'run', return_value=result) as run:
                self.assertEqual(self.real_command('systemctl', 'stop', 'fprintd.service'), '')
                run.assert_called_once_with(('systemctl', 'stop', 'fprintd.service'),
                    env=self.m.ENV, text=True, capture_output=True, timeout=30)

    def test_command_other_systemctl_failure_not_misreported_as_absent(self):
        result = self.m.subprocess.CompletedProcess([], 1, '', 'Failed to connect to bus: Host is down\n')
        with mock.patch.object(self.m.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'Failed to connect to bus'):
                self.real_command('systemctl', 'stop', 'fprintd.service')

    def test_command_absent_unit_exception_not_applied_to_other_operations(self):
        result = self.m.subprocess.CompletedProcess([], 5, '',
            'Failed to stop fprintd.service: Unit fprintd.service not loaded.\n')
        with mock.patch.object(self.m.subprocess, 'run', return_value=result):
            with self.assertRaises(RuntimeError):
                self.real_command('systemctl', 'daemon-reload')

    def test_help_does_not_request_sudo_or_mutate(self):
        with mock.patch.object(self.m.sys, 'argv', [self.m.FORCE.name, '--help']), \
                mock.patch.object(self.m.os, 'execve') as execute:
            self.assertEqual(self.m.main(), 0)
            execute.assert_not_called()
        self.assertEqual(self.events, [])
        self.assertTrue(self.m.CONFIG.exists())

    def test_main_rejects_arguments_and_unknown_name(self):
        for argv in ([self.m.FORCE.name, '--root', '/'], ['remove.py']):
            with self.subTest(argv=argv), mock.patch.object(self.m.sys, 'argv', argv), \
                    mock.patch.object(self.m.os, 'execve') as execute:
                with self.assertRaises(RuntimeError):
                    self.m.main()
                execute.assert_not_called()
        self.assertEqual(self.events, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
