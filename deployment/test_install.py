#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic install transactions; all privileged/service operations are replaced."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('goodix_installer_test', HERE / 'install.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
REAL_FSTAT = os.fstat


def root_owned_fstat(fd):
    """Simulate privileged ownership only; inode/type/mode remain real."""
    values = list(REAL_FSTAT(fd))
    values[4:6] = (0, 0)
    return os.stat_result(values)


class HostCompatibility(unittest.TestCase):
    def test_fedora_44_and_newer_accepted_without_disabling_selinux(self):
        for version in ('44', '45', '46', '100'):
            with self.subTest(version=version), \
                    patch.object(m.platform, 'freedesktop_os_release', return_value={'ID': 'fedora', 'VERSION_ID': version}), \
                    patch.object(m.platform, 'machine', return_value='x86_64'), \
                    patch.object(m, 'command', return_value='Enforcing'):
                m.supported_system()

    def test_unsupported_hosts_and_non_enforcing_selinux_rejected(self):
        for distro, version, arch, selinux in (
                ('fedora', '43', 'x86_64', 'Enforcing'),
                ('fedora', 'rawhide', 'x86_64', 'Enforcing'),
                ('fedora', '45', 'aarch64', 'Enforcing'),
                ('ubuntu', '45', 'x86_64', 'Enforcing'),
                ('fedora', '45', 'x86_64', 'Permissive')):
            with self.subTest(host=(distro, version, arch, selinux)), \
                    patch.object(m.platform, 'freedesktop_os_release', return_value={'ID': distro, 'VERSION_ID': version}), \
                    patch.object(m.platform, 'machine', return_value=arch), \
                    patch.object(m, 'command', return_value=selinux):
                with self.assertRaises(RuntimeError):
                    m.supported_system()


class DropinDirectory(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goodix-dropin-permissions-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.directory = self.base / 'fprintd.service.d'
        self.ctx = contextlib.ExitStack()
        self.addCleanup(self.ctx.close)
        self.ctx.enter_context(patch.object(m.r, 'DROPIN', self.directory / '90-goodix-5125-runtime.conf'))
        self.ctx.enter_context(patch.object(m, 'safe_parent', side_effect=m.r.parents))
        self.ctx.enter_context(patch.object(m.os, 'fstat', side_effect=root_owned_fstat))
        self.production_trusted = m.r.trusted
        # The real test process remains unprivileged. Only ownership's expected
        # identity is substituted; actual inode, type and permissions are checked.
        self.ctx.enter_context(patch.object(m.r, 'trusted', side_effect=self.trusted))

    def trusted(self, path, directory=False):
        m.r.parents(path)
        info = path.lstat()
        m.require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
                  and (info.st_uid, info.st_gid) == (os.getuid(), os.getgid())
                  and not info.st_mode & 0o022, 'fixture ownership/type/mode drift')

    def test_new_directory_is_readable_under_private_umask_and_state_stays_private(self):
        previous = os.umask(0o077)
        try:
            protected = self.base / 'protected-state'
            protected.mkdir(mode=0o700)
            m.prepare_dropin_directory()
            m.write_file(m.r.DROPIN, m.r.DROPIN_BYTES)
            self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(m.r.DROPIN.stat().st_mode), 0o644)
            self.assertEqual(m.r.DROPIN.read_bytes(), m.r.DROPIN_BYTES)
            self.assertEqual(os.umask(0o077), 0o077, 'The process umask must stay private')
            self.assertEqual(stat.S_IMODE(protected.stat().st_mode), 0o700)
        finally:
            os.umask(previous)

    def test_existing_directories_become_readable_without_changing_dropin_files(self):
        previous = os.umask(0o077)
        try:
            for mode in (0o755, 0o700):
                with self.subTest(mode=oct(mode)):
                    self.directory.mkdir(mode=mode)
                    self.directory.chmod(mode)
                    other = self.directory / '10-admin.conf'
                    other.write_bytes(b'Administrator override sentinel')
                    other.chmod(0o600)
                    m.r.DROPIN.write_bytes(m.r.DROPIN_BYTES)
                    m.r.DROPIN.chmod(0o644)
                    before = self.directory.stat()
                    files = {path: (path.read_bytes(), path.stat().st_mode, path.stat().st_ino)
                             for path in (other, m.r.DROPIN)}
                    with patch.object(m.os, 'fchmod', wraps=os.fchmod) as chmod:
                        m.prepare_dropin_directory()
                        chmod.assert_called_once_with(unittest.mock.ANY, 0o755)
                    after = self.directory.stat()
                    self.assertEqual(stat.S_IMODE(after.st_mode), 0o755)
                    self.assertEqual((after.st_dev, after.st_ino, after.st_uid, after.st_gid),
                                     (before.st_dev, before.st_ino, before.st_uid, before.st_gid))
                    for path, unchanged in files.items():
                        self.assertEqual((path.read_bytes(), path.stat().st_mode, path.stat().st_ino), unchanged)
                        path.unlink()
                    self.assertEqual(os.umask(0o077), 0o077)
                    self.directory.rmdir()
        finally:
            os.umask(previous)

    def test_untrusted_owner_symlink_wrong_type_and_redirected_parent_refused(self):
        self.directory.mkdir()
        with patch.object(m.r, 'trusted', side_effect=RuntimeError('unexpected owner')), \
                patch.object(m.os, 'fchmod', wraps=os.fchmod) as chmod:
            with self.assertRaisesRegex(RuntimeError, 'unexpected owner'):
                m.prepare_dropin_directory()
            chmod.assert_not_called()
        self.directory.rmdir()
        target = self.base / 'unrelated'
        target.mkdir(mode=0o700)
        self.directory.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            m.prepare_dropin_directory()
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
        self.directory.unlink()
        self.directory.write_bytes(b'unrelated file')
        with self.assertRaises(RuntimeError):
            m.prepare_dropin_directory()
        self.assertEqual(self.directory.read_bytes(), b'unrelated file')
        self.directory.unlink()
        redirected = self.base / 'redirected'
        redirected.symlink_to(target, target_is_directory=True)
        with patch.object(m.r, 'DROPIN', redirected / 'fprintd.service.d/90-goodix-5125-runtime.conf'):
            with self.assertRaisesRegex(RuntimeError, 'redirected parent'):
                m.prepare_dropin_directory()
        self.assertFalse((target / 'fprintd.service.d').exists())

    def test_actual_non_root_owner_fails_production_trust_before_any_chmod(self):
        self.assertNotEqual(os.getuid(), 0, 'This fixture must run without root')
        self.directory.mkdir(mode=0o700)
        with patch.object(m.r, 'trusted', side_effect=self.production_trusted), \
                patch.object(m.os, 'fchmod', wraps=os.fchmod) as chmod:
            with self.assertRaisesRegex(RuntimeError, 'ownership/type/mode drift'):
                m.prepare_dropin_directory()
            chmod.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)

    def test_opened_inode_unexpected_owner_or_replacement_is_never_chmodded(self):
        previous = os.umask(0o077)
        try:
            with patch.object(m.os, 'fstat', side_effect=REAL_FSTAT), \
                    patch.object(m.os, 'fchmod', wraps=os.fchmod) as chmod:
                with self.assertRaisesRegex(RuntimeError, 'ownership/type/mode drift'):
                    m.prepare_dropin_directory()
                chmod.assert_not_called()
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.directory.rmdir()
        real_open = os.open
        def replace_then_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            self.directory.rename(self.base / 'original')
            self.directory.mkdir(mode=0o700)
            return fd
        with patch.object(m.os, 'open', side_effect=replace_then_open), \
                patch.object(m.os, 'fchmod', wraps=os.fchmod) as chmod:
            with self.assertRaisesRegex(RuntimeError, 'directory changed'):
                m.prepare_dropin_directory()
            chmod.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)


class Installer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goodix-install-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.clone = self.base / 'alternate clone with spaces'
        shutil.copytree(HERE.parent / 'deployment', self.clone / 'deployment',
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(HERE.parent / 'production', self.clone / 'production',
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(HERE.parent / 'install.sh', self.clone / 'install.sh')
        self.host = self.base / 'host'
        self.host.mkdir()
        self.ctx = contextlib.ExitStack()
        self.addCleanup(self.ctx.close)
        self.ctx.enter_context(patch.object(m, 'ROOT', self.clone))
        for key in ('CONFIG', 'SUPPORT', 'RUNTIME', 'DROPIN', 'MASK', 'NORMAL', 'FORCE', 'RECOVERY', 'MATERIAL', 'STATE'):
            path = self.host / str(getattr(m.r, key)).lstrip('/')
            path.parent.mkdir(parents=True, exist_ok=True)
            self.ctx.enter_context(patch.object(m.r, key, path))
        self.vendor = self.host / 'usr/lib/pam.d/plasmalogin'
        self.vendor.parent.mkdir(parents=True)
        self.vendor.write_text('Fedora vendor sentinel\n')
        self.ctx.enter_context(patch.object(m, 'VENDOR', self.vendor))
        self.template = self.host / 'var/lib/fprint/user/template'
        self.template.parent.mkdir(parents=True)
        self.template.write_bytes(b'synthetic template sentinel')
        device = self.host / 'sys/bus/usb/devices/1-1'
        device.mkdir(parents=True)
        (device / 'idVendor').write_text('27c6')
        (device / 'idProduct').write_text('5125')
        self.events = []
        self.active = True
        self.rule = False
        self.selinux_modules = []
        self.selinux_policy = m.r.SELINUX_MODULE_RULE.encode() + b'\n'
        self.fail_login = False
        self.ctx.enter_context(patch.object(m, 'command', side_effect=self.command))
        self.ctx.enter_context(patch.object(m.r, 'command', side_effect=self.command))
        self.ctx.enter_context(patch.object(m, 'supported_system'))
        self.ctx.enter_context(patch.object(m, 'prerequisites'))
        self.ctx.enter_context(patch.object(m.builder, 'validate_chicago_sources', return_value={}))
        self.abi_check = self.ctx.enter_context(patch.object(m.builder, 'verify_runtime_abi'))
        self.ctx.enter_context(patch.object(m, 'safe_parent', side_effect=m.r.parents))
        self.ctx.enter_context(patch.object(m.os, 'fstat', side_effect=root_owned_fstat))
        self.ctx.enter_context(patch.object(m.r, 'trusted', side_effect=self.trusted))
        self.ctx.enter_context(patch.object(m, 'label_materials', side_effect=self.labels))
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        self.ctx.enter_context(contextlib.redirect_stdout(self.stdout))
        self.ctx.enter_context(contextlib.redirect_stderr(self.stderr))
        self.source = self.base / 'goodix-5125-materials'
        self.source.mkdir(mode=0o700)
        # The full metadata/format/crypto contract is tested by test_materials;
        # this transaction fixture deliberately contains no real device data.
        for name in m.r.MATERIAL_NAMES:
            (self.source / name).write_bytes(b'SYNTHETIC ' + name.encode())
        self.bundle = SimpleNamespace(files={p.name: p.read_bytes() for p in self.source.iterdir()})
        self.ctx.enter_context(patch.object(m.materials, 'validate_bundle', side_effect=self.validate_material))
        self.ctx.enter_context(patch.object(m.materials, 'install_materials', side_effect=self.import_material))
        self.payload = self.base / 'payload'
        self.make_payload(self.payload)

    def trusted(self, path, directory=False):
        m.r.parents(path)
        info = path.lstat()
        self.assertEqual(info.st_uid, os.getuid())
        m.require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode) and not info.st_mode & 0o022,
                  'synthetic project type/mode drift')

    def validate_material(self, path, **kwargs):
        self.assertIn(Path(path), (self.source, m.r.MATERIAL))
        self.assertEqual(kwargs['source'], path == self.source)
        self.assertEqual(kwargs['owner_uid'], os.getuid() if path == self.source else 0)
        if path == m.r.MATERIAL:
            self.assertEqual(kwargs['owner_gid'], 0)
        m.require({p.name for p in path.iterdir()} == set(m.r.MATERIAL_NAMES), 'five files required')
        m.require(all(p.is_file() and not p.is_symlink() for p in path.iterdir()), 'material source type')
        return SimpleNamespace(files={p.name: p.read_bytes() for p in path.iterdir()})

    def import_material(self, bundle, destination, *, native_check):
        self.assertEqual(bundle.files, self.bundle.files)
        self.assertFalse(self.active)
        self.assertTrue(m.r.MASK.is_symlink())
        if destination.exists():
            native_check(destination)
            return False
        destination.mkdir(mode=0o700)
        for name in m.r.MATERIAL_NAMES:
            shutil.copy2(self.source / name, destination / name)
            (destination / name).chmod(0o600)
        native_check(destination)
        return True

    def labels(self):
        self.assertFalse(self.active)
        self.assertTrue(m.r.STATE.is_dir())
        if m.r.MATERIAL.exists():
            self.assertTrue(self.rule)

    def command(self, *args, cwd=None):
        args = tuple(str(a) for a in args)
        self.events.append(args)
        self.assertFalse(any('/dev/bus/usb' in a or '/sys/bus/usb' in a for a in args))
        self.assertNotIn('start', args)
        if args[0] == 'restorecon':
            return ''
        if args[0] == 'rpm':
            return 'plasma-login-manager'
        if args[:2] == ('systemctl', 'daemon-reload'):
            return ''
        if args[:2] == ('systemctl', 'stop'):
            self.active = False
            return ''
        if args[:2] == ('systemctl', 'show'):
            if '--property=ActiveState' in args:
                return 'ActiveState=inactive\nMainPID=0\nLoadState=masked\n'
            prop = args[args.index('-p') + 1]
            return {'FragmentPath': '/usr/lib/systemd/system/fprintd.service',
                    'ExecStart': '{ path=/usr/libexec/fprintd ; }',
                    'Environment': '', 'DropInPaths': ''}[prop]
        if args[:3] == ('semanage', 'fcontext', '-l'):
            return m.r.RULE + ' all files system_u:object_r:fprintd_var_lib_t:s0\n' if self.rule else ''
        if args[:3] == ('semanage', 'fcontext', '-a'):
            self.rule = True
            return ''
        if args[:3] == ('semanage', 'fcontext', '-d'):
            self.rule = False
            return ''
        if args == ('semodule', '-X', m.r.SELINUX_MODULE_PRIORITY,
                    '--cil', '--extract', m.r.SELINUX_MODULE_NAME):
            self.assertIsNotNone(cwd)
            (Path(cwd) / (m.r.SELINUX_MODULE_NAME + '.cil')).write_bytes(self.selinux_policy)
            return ''
        if args == ('semodule', '-lfull'):
            return '\n'.join(self.selinux_modules)
        if args[:4] == ('semodule', '-X', m.r.SELINUX_MODULE_PRIORITY, '-i'):
            self.assertEqual(len(args), 5)
            self.assertTrue(m.r.NORMAL.exists() and m.r.FORCE.exists() and m.r.RECOVERY.exists())
            self.assertEqual(Path(args[4]).name, m.r.SELINUX_MODULE_NAME + '.cil')
            self.assertEqual(Path(args[4]).read_bytes(), self.selinux_policy)
            self.selinux_modules.append(
                f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil')
            return ''
        if args == ('semodule', '-X', m.r.SELINUX_MODULE_PRIORITY,
                    '-r', m.r.SELINUX_MODULE_NAME):
            self.selinux_modules.remove(
                f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil')
            return ''
        if args[0].endswith('/check-material'):
            self.assertEqual(Path(args[1]), m.r.MATERIAL)
            return 'GOODIX_MATERIAL_CHECK=PASS'
        raise AssertionError('unmocked host command: ' + repr(args))

    def make_payload(self, directory):
        directory.mkdir()
        names = {'runtime/libfprint-2.so.2.0.0', 'runtime/ChicagoHS-NOTICES.txt',
                 'runtime/LICENSING_AND_PROVENANCE.md', 'runtime/source-files.sha256',
                 'runtime/build-provenance.json', 'login/' + m.r.MODULE,
                 'login/plasmalogin.pam', 'check-material',
                 *(f'runtime/licenses/{n}.txt' for n in m.builder.LICENSES)}
        manifest = {'schema': 1, 'source_id': 'a' * 64, 'files': {}, 'links': {}}
        for name in names:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            data = (self.clone / 'deployment/plasma-login-opt-in/plasmalogin.pam').read_bytes() \
                if name == 'login/plasmalogin.pam' else b'SYNTHETIC PUBLIC PAYLOAD ' + name.encode()
            target.write_bytes(data)
            if name == 'runtime/build-provenance.json':
                target.write_text(json.dumps({'version': '3.0.0', 'source_id': manifest['source_id']}))
                data = target.read_bytes()
            target.chmod(0o755 if name == 'check-material' else 0o644)
            manifest['files'][name] = m.r.digest(data)
        for name, target in m.r.LINKS.items():
            (directory / 'runtime' / name).symlink_to(target)
            manifest['links']['runtime/' + name] = target
        (directory / 'payload.json').write_text(json.dumps(manifest))

    def apply(self):
        with patch.object(m.os, 'geteuid', return_value=0):
            m.apply(self.payload, self.source, os.getuid())

    def test_runtime_abi_uses_verified_staged_payload_before_mutation(self):
        def verify(runtime):
            self.assertNotEqual(runtime, self.payload / 'runtime')
            self.assertEqual(m.builder.validate_payload(runtime.parent),
                             m.builder.validate_payload(self.payload))
            self.assertTrue(self.active)
            self.assertFalse(m.r.MASK.exists())
            self.assertFalse(m.r.STATE.exists())
            self.assertFalse(any(m.r.present(p) for p in m.software_paths()))
        self.abi_check.side_effect = verify
        self.apply()
        self.abi_check.assert_called_once()

    def test_incompatible_runtime_stops_update_before_service_or_data_mutation(self):
        self.apply()
        software_before = {str(path): path.read_bytes() for root in m.software_paths()
                           for path in ([root] if root.is_file() else root.rglob('*'))
                           if path.is_file() and not path.is_symlink()}
        self.active = True
        self.events.clear()
        self.abi_check.side_effect = RuntimeError('stock fprintd ABI incompatible')
        with self.assertRaisesRegex(RuntimeError, 'stock fprintd ABI'):
            self.apply()
        self.assertTrue(self.active)
        self.assertFalse(m.r.MASK.exists())
        self.assertFalse(any(event[:2] == ('systemctl', 'stop') or event[0] == 'restorecon'
                             or event[0].endswith('/check-material')
                             or event[:3] in (('semanage', 'fcontext', '-a'),
                                             ('semanage', 'fcontext', '-d'))
                             for event in self.events))
        self.assertEqual(software_before, {name: Path(name).read_bytes() for name in software_before})
        self.assert_preserved()

    def test_manager_expected_absent_refuses_changed_runtime(self):
        self.apply()
        receipt = (m.r.RUNTIME / 'installation.json').read_bytes()
        with patch.object(m.os, 'geteuid', return_value=0), \
                self.assertRaisesRegex(RuntimeError, 'runtime changed since Manager'):
            m.apply(self.payload, self.source, os.getuid(), expected_source_id=None)
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), receipt)
        self.assertFalse(m.r.MASK.exists())

    def test_manager_expected_source_refuses_changed_runtime(self):
        self.apply()
        receipt = (m.r.RUNTIME / 'installation.json').read_bytes()
        with patch.object(m.os, 'geteuid', return_value=0), \
                self.assertRaisesRegex(RuntimeError, 'runtime changed since Manager'):
            m.apply(self.payload, self.source, os.getuid(), expected_source_id='f' * 64)
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), receipt)

    def test_runtime_receipt_records_payload_version(self):
        self.apply()
        self.assertEqual(json.loads((m.r.RUNTIME / 'installation.json').read_bytes())['version'], '3.0.0')

    def test_first_install_mode_and_no_protected_output(self):
        self.apply()
        self.assertIn('GOODIX_INSTALL_MODE=FIRST_INSTALL', self.stdout.getvalue())
        receipt = json.loads((m.r.RUNTIME / 'installation.json').read_bytes())
        self.assertEqual(self.selinux_modules, [])
        self.assertFalse(any(args[:4] == ('semodule', '-X', m.r.SELINUX_MODULE_PRIORITY, '-i')
                             for args in self.events))
        self.assertEqual(receipt['matcher'], 'chicago-type24')
        self.assertFalse(any('opencv' in name.lower() for name in receipt['files']))
        self.assertIn('new enrollment for every finger/user', self.stdout.getvalue())
        for value in self.bundle.files.values():
            self.assertNotIn(value.decode(), self.stdout.getvalue() + self.stderr.getvalue())

    def test_fresh_install_without_bundle_or_reader_creates_only_empty_state_root(self):
        shutil.rmtree(self.source)
        shutil.rmtree(self.host / 'sys')
        with patch.object(m.materials, 'validate_bundle',
                          side_effect=AssertionError('legacy bundle unexpectedly read')), \
                patch.object(m.materials, 'install_materials',
                             side_effect=AssertionError('legacy bundle unexpectedly imported')):
            self.apply()
        self.assertIn('GOODIX_PAIRING_STATE=READY', self.stdout.getvalue())
        self.assertFalse(m.r.MATERIAL.exists())
        self.assertTrue(m.r.STATE.is_dir())
        self.assertEqual(stat.S_IMODE(m.r.STATE.stat().st_mode), 0o700)
        receipt = json.loads((m.r.RUNTIME / 'installation.json').read_bytes())
        self.assertEqual(receipt['material_mode'], 'state-v2')
        self.assertIsNone(receipt['material_selinux'])
        self.assertFalse(any('/dev/bus/usb' in part or '/sys/bus/usb' in part
                             for event in self.events for part in event))

    def test_state_v2_only_update_reinstall_and_removal_preserve_state(self):
        shutil.rmtree(self.source)
        self.apply()
        sentinel = m.r.STATE / 'synthetic-reader-state'
        sentinel.write_bytes(b'SYNTHETIC STATE SENTINEL')
        sentinel.chmod(0o600)
        self.apply()
        self.assertEqual(sentinel.read_bytes(), b'SYNTHETIC STATE SENTINEL')
        self.assertEqual(m.r.remove(), 0)
        self.assertEqual(sentinel.read_bytes(), b'SYNTHETIC STATE SENTINEL')
        self.apply()
        self.assertEqual(sentinel.read_bytes(), b'SYNTHETIC STATE SENTINEL')

    def test_update_without_home_bundle_preserves_inodes(self):
        self.apply()
        before = {p.name: p.stat().st_ino for p in m.r.MATERIAL.iterdir()}
        shutil.rmtree(self.source)
        with patch.object(m.materials, 'install_materials', side_effect=AssertionError('unexpected import')):
            self.apply()
        self.assertIn('GOODIX_INSTALL_MODE=UPDATE', self.stdout.getvalue())
        self.assertEqual(before, {p.name: p.stat().st_ino for p in m.r.MATERIAL.iterdir()})
        self.assert_preserved()

    def test_reinstall_after_both_removal_paths_without_home_bundle(self):
        self.apply()
        before = {p.name: p.stat().st_ino for p in m.r.MATERIAL.iterdir()}
        shutil.rmtree(self.source)
        for force in (False, True):
            with self.subTest(force=force):
                self.assertEqual(m.r.remove(force=force), 0)
                self.assertFalse(any(m.r.present(p) for p in m.software_paths()))
                self.stdout.seek(0)
                self.stdout.truncate()
                with patch.object(m.materials, 'install_materials', side_effect=AssertionError('unexpected import')):
                    self.apply()
                self.assertIn('GOODIX_INSTALL_MODE=REINSTALL', self.stdout.getvalue())
                self.assertEqual(before, {p.name: p.stat().st_ino for p in m.r.MATERIAL.iterdir()})
                self.assert_preserved()

    def assert_preserved(self):
        self.assertEqual(self.vendor.read_text(), 'Fedora vendor sentinel\n')
        self.assertEqual(self.template.read_bytes(), b'synthetic template sentinel')
        for name in m.r.MATERIAL_NAMES:
            self.assertEqual((m.r.MATERIAL / name).read_bytes(), b'SYNTHETIC ' + name.encode())

    def test_complete_reader_present_install_and_normal_removal(self):
        self.apply()
        self.assertFalse(self.active)
        self.assertFalse(m.r.MASK.is_symlink())
        self.assertTrue(m.r.CONFIG.exists())
        self.assertEqual(self.selinux_modules, [])
        self.assert_preserved()
        self.assertEqual(m.r.remove(), 0)
        self.assert_preserved()
        self.assertFalse(m.r.RUNTIME.exists())
        self.assertEqual(self.selinux_modules, [])

    def test_update_rebuilds_without_private_history_and_preserves_materials(self):
        self.apply()
        before = {p.name: p.stat().st_ino for p in m.r.MATERIAL.iterdir()}
        library = self.payload / 'runtime/libfprint-2.so.2.0.0'
        library.write_bytes(b'SYNTHETIC UPDATED LIBRARY')
        manifest_path = self.payload / 'payload.json'
        manifest = json.loads(manifest_path.read_bytes())
        manifest['files']['runtime/libfprint-2.so.2.0.0'] = m.r.digest(library.read_bytes())
        manifest['source_id'] = 'b' * 64
        manifest_path.write_text(json.dumps(manifest))
        self.apply()
        self.assertEqual((m.r.RUNTIME / library.name).read_bytes(), library.read_bytes())
        self.assertEqual(before, {p.name: p.stat().st_ino for p in m.r.MATERIAL.iterdir()})
        m.r.normal_preflight()
        self.assert_preserved()

    def test_update_from_sigfm_receipt_uses_same_canonical_removal(self):
        self.apply()
        path = m.r.RUNTIME / 'installation.json'
        receipt = json.loads(path.read_bytes())
        self.selinux_modules = [f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil']
        receipt.pop('matcher')  # Existing main schema-2 receipts have no matcher.
        for part in ('core', 'features2d', 'flann', 'imgproc'):
            name = f'libopencv_{part}.so.413'
            data = b'SYNTHETIC SIGFM LIBRARY ' + part.encode()
            (m.r.RUNTIME / name).write_bytes(data)
            receipt['files'][name] = m.r.digest(data)
        path.write_text(json.dumps(receipt))
        m.r.normal_preflight()
        self.apply()
        receipt = json.loads(path.read_bytes())
        self.assertEqual(self.selinux_modules, [])
        self.assertFalse(any(args[:4] == ('semodule', '-X', m.r.SELINUX_MODULE_PRIORITY, '-i')
                             for args in self.events))
        self.assertEqual(receipt['matcher'], 'chicago-type24')
        self.assertFalse(any(name.startswith('libopencv_') for name in receipt['files']))
        m.r.normal_preflight()
        self.assert_preserved()

    def test_update_from_milan_removes_diagnostic_and_preserves_data(self):
        self.apply()
        path = m.r.RUNTIME / 'installation.json'
        receipt = json.loads(path.read_bytes())
        receipt['matcher'] = 'milan-type17'
        for name in ('Milan-NOTICES.txt', 'goodix-milan-diagnostic',
                     'prepare-milan-diagnostic.py'):
            data = b'SYNTHETIC LEGACY MILAN ' + name.encode()
            (m.r.RUNTIME / name).write_bytes(data)
            receipt['files'][name] = m.r.digest(data)
        path.write_text(json.dumps(receipt))
        m.r.normal_preflight()
        self.apply()
        receipt = json.loads(path.read_bytes())
        self.assertEqual(self.selinux_modules, [])
        self.assertFalse(any(args[:4] == ('semodule', '-X', m.r.SELINUX_MODULE_PRIORITY, '-i')
                             for args in self.events))
        self.assertEqual(receipt['matcher'], 'chicago-type24')
        self.assertFalse(any('milan' in name.lower() for name in receipt['files']))
        self.assertFalse(any('milan' in p.name.lower() for p in m.r.RUNTIME.iterdir()))
        m.r.normal_preflight()
        self.assert_preserved()

    def test_partial_install_rolls_back_software_preserves_complete_materials(self):
        with patch.object(m, 'install_login', side_effect=RuntimeError('synthetic login failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic login failure'):
                self.apply()
        self.assertFalse(any(m.r.present(p) for p in m.software_paths()))
        self.assertFalse(self.rule)
        self.assertEqual(self.selinux_modules, [])
        self.assertFalse(m.r.MASK.is_symlink())
        self.assert_preserved()

    def test_failed_update_restores_prior_project_installation(self):
        self.apply()
        self.selinux_modules = [f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil']
        self.selinux_policy = b'\n' + self.selinux_policy + b'\n'
        shutil.rmtree(self.source)
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        with patch.object(m, 'install_login', side_effect=RuntimeError('synthetic failed update')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic failed update'):
                self.apply()
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        m.r.normal_preflight()
        self.assertTrue(self.rule)
        self.assertEqual(self.selinux_modules,
                         [f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil'])
        self.assert_preserved()

    def test_recognized_legacy_residual_module_is_removed(self):
        expected = f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil'
        self.selinux_modules = [expected]
        self.apply()
        self.assertEqual(self.selinux_modules, [])
        self.assertFalse(any(args[:4] == ('semodule', '-X', m.r.SELINUX_MODULE_PRIORITY, '-i')
                             for args in self.events))

    def test_policy_collision_stops_update_before_mutation(self):
        self.apply()
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        self.selinux_modules = [f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil']
        self.selinux_policy = b'(allow fprintd_t sysctl_vm_t (file (read)))\n'
        self.events.clear()
        with self.assertRaisesRegex(RuntimeError, 'ownership ambiguous'):
            self.apply()
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        self.assertTrue(m.r.CONFIG.exists())
        self.assertFalse(any(args[:2] == ('systemctl', 'stop') or '-r' in args
                             for args in self.events))
        self.assert_preserved()

    def test_foreign_policy_appearing_during_rollback_is_not_overwritten(self):
        self.apply()
        self.selinux_modules = [f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil']
        def failed_login(*args):
            self.selinux_modules = [f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil']
            self.selinux_policy = b'(allow fprintd_t sysctl_vm_t (file (read)))\n'
            self.events.clear()
            raise RuntimeError('synthetic failure with concurrent policy change')
        with patch.object(m, 'install_login', side_effect=failed_login):
            with self.assertRaisesRegex(RuntimeError, 'rollback incomplete.*ownership ambiguous'):
                self.apply()
        self.assertTrue(self.selinux_modules)
        self.assertFalse(any('-i' in args or '-r' in args for args in self.events))
        self.assertTrue(m.r.NORMAL.exists() and m.r.FORCE.exists())
        self.assert_preserved()

    def test_failed_chicago_update_does_not_create_legacy_module(self):
        self.apply()
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        with patch.object(m, 'install_login', side_effect=RuntimeError('synthetic failed update')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic failed update'):
                self.apply()
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        self.assertEqual(self.selinux_modules, [])
        self.assertFalse(any(args[:4] == ('semodule', '-X', m.r.SELINUX_MODULE_PRIORITY, '-i')
                             for args in self.events))
        self.assert_preserved()

    def test_unexpected_selinux_module_priority_stops_before_mutation(self):
        unexpected = f'300 {m.r.SELINUX_MODULE_NAME} cil'
        self.selinux_modules = [unexpected]
        with self.assertRaisesRegex(RuntimeError, 'unexpected priority/state'):
            self.apply()
        self.assertEqual(self.selinux_modules, [unexpected])
        self.assertFalse(any(m.r.present(path) for path in m.software_paths()))

    def test_final_mask_release_reload_failure_reports_installed_state(self):
        def fail_final_reload(*args):
            if args == ('systemctl', 'daemon-reload') and not m.r.MASK.is_symlink():
                raise RuntimeError('synthetic final reload failure')
            return self.command(*args)
        with patch.object(m.r, 'command', side_effect=fail_final_reload):
            with self.assertRaisesRegex(RuntimeError, 'software installed; recovery commands retained'):
                self.apply()
        m.r.normal_preflight()
        self.assertTrue(m.r.NORMAL.exists())
        self.assertTrue(m.r.FORCE.exists())
        self.assert_preserved()

    def test_rollback_quiescence_failure_preserves_software_and_recovery(self):
        actual_stop = m.r.stop_and_verify
        stops = []
        def stop_once():
            if stops:
                raise RuntimeError('synthetic busy service')
            stops.append(True)
            return actual_stop()
        with patch.object(m.r, 'stop_and_verify', side_effect=stop_once), \
                patch.object(m, 'install_login', side_effect=RuntimeError('synthetic install failure')):
            with self.assertRaisesRegex(RuntimeError, 'rollback incomplete: service could not be quiesced'):
                self.apply()
        self.assertTrue(m.r.RUNTIME.exists())
        self.assertTrue(m.r.NORMAL.exists())
        self.assertTrue(m.r.FORCE.exists())
        self.assert_preserved()

    def test_mask_borrowed_after_host_preflight_is_preserved(self):
        original = m.host_preflight
        def preflight_then_mask():
            original()
            m.r.MASK.symlink_to('/dev/null')
        with patch.object(m, 'host_preflight', side_effect=preflight_then_mask):
            self.apply()
        self.assertTrue(m.r.MASK.is_symlink())
        self.assertEqual(os.readlink(m.r.MASK), '/dev/null')
        m.r.normal_preflight()

    def test_concurrent_lifecycle_fails_before_software_mutation(self):
        fd = os.open(m.r.RUNTIME.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            m.fcntl.flock(fd, m.fcntl.LOCK_EX | m.fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'another Goodix lifecycle operation'):
                self.apply()
        finally:
            os.close(fd)
        self.assertFalse(any(m.r.present(p) for p in m.software_paths()))
        self.assertFalse(m.r.MASK.is_symlink())

    def test_native_binding_rejection_restores_previous_install(self):
        self.apply()
        self.events.clear()
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        def reject_native(*args):
            if str(args[0]).endswith('/check-material'):
                raise RuntimeError('synthetic native binding rejected')
            return self.command(*args)
        with patch.object(m, 'command', side_effect=reject_native):
            with self.assertRaisesRegex(RuntimeError, 'synthetic native binding rejected'):
                self.apply()
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        self.assertFalse(any(args[:2] == ('systemctl', 'stop') for args in self.events))
        m.r.normal_preflight()
        self.assert_preserved()

    def test_explicit_mismatch_stops_before_transaction(self):
        self.apply()
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        (self.source / m.r.MATERIAL_NAMES[1]).write_bytes(b'SYNTHETIC DIFFERENT READER')
        self.events.clear()
        with patch.object(m.os, 'geteuid', return_value=0), \
                self.assertRaisesRegex(RuntimeError, 'REASON=explicit_material_mismatch'):
            m.apply(self.payload, self.source, os.getuid(), explicit=True)
        self.assertEqual(self.events, [])
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        self.assert_preserved()

    def test_installed_material_lost_after_native_check_is_not_recreated(self):
        self.apply()
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        original = m.r.inhibit_activation
        preserved = self.base / 'preserved-material-fixture'

        def lose_material():
            result = original()
            m.r.MATERIAL.rename(preserved)
            return result

        with patch.object(m.r, 'inhibit_activation', side_effect=lose_material), \
                patch.object(m.materials, 'install_materials') as publish, \
                self.assertRaisesRegex(RuntimeError, 'invalid_installed_material'):
            self.apply()
        publish.assert_not_called()
        self.assertFalse(m.r.MATERIAL.exists())
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        self.assertFalse(m.r.MASK.is_symlink())
        preserved.rename(m.r.MATERIAL)
        self.assert_preserved()

    def test_foreign_library_environment_is_rejected_before_mutation(self):
        def foreign(*args):
            if args == ('systemctl', 'show', 'fprintd.service', '-p', 'Environment', '--value'):
                return '"LD_LIBRARY_PATH=/unrelated"'
            return self.command(*args)
        with patch.object(m, 'command', side_effect=foreign):
            with self.assertRaisesRegex(RuntimeError, 'foreign library environment'):
                self.apply()
        self.assertFalse(any(m.r.present(p) for p in m.software_paths()))

    def test_missing_extra_and_symlink_material_fail_before_host_mutation(self):
        path = self.source / m.r.MATERIAL_NAMES[0]
        original = path.read_bytes()
        for mutation in ('missing', 'extra', 'symlink'):
            if mutation == 'missing': path.unlink()
            if mutation == 'extra': (self.source / 'extra').write_bytes(b'no')
            if mutation == 'symlink':
                path.unlink(); path.symlink_to(self.source / m.r.MATERIAL_NAMES[1])
            self.events.clear()
            with self.assertRaises(RuntimeError): self.apply()
            self.assertFalse(any(m.r.present(p) for p in m.software_paths()))
            self.assertFalse(any(x[0] in ('semanage', 'restorecon') or x[:2] == ('systemctl', 'stop') for x in self.events))
            (self.source / 'extra').unlink(missing_ok=True)
            path.unlink(missing_ok=True); path.write_bytes(original)

    def test_installed_commands_work_after_repository_fixture_is_deleted(self):
        for force in (False, True):
            self.apply()
            shutil.rmtree(self.clone)
            installed = m.r.FORCE if force else m.r.NORMAL
            installed_spec = importlib.util.spec_from_loader('standalone_installed',
                __import__('importlib').machinery.SourceFileLoader('standalone_installed', str(installed)))
            module = importlib.util.module_from_spec(installed_spec)
            installed_spec.loader.exec_module(module)
            for key in ('CONFIG', 'SUPPORT', 'RUNTIME', 'DROPIN', 'MASK', 'NORMAL', 'FORCE', 'RECOVERY', 'MATERIAL', 'STATE'):
                setattr(module, key, getattr(m.r, key))
            module.command = self.command
            module.trusted = self.trusted
            with patch.object(module.os, 'geteuid', return_value=0), \
                    patch.object(sys, 'argv', [str(installed)]):
                self.assertEqual(module.main(), 0)
            self.assert_preserved()
            shutil.copytree(HERE.parent / 'deployment', self.clone / 'deployment', ignore=shutil.ignore_patterns('__pycache__'))

    def test_root_shell_entry_resolves_alternate_clone_and_foreign_cwd(self):
        result = subprocess.run([str(self.clone / 'install.sh'), '--help'], cwd='/tmp', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('--materials', result.stdout)
        self.assertNotIn('five-file', result.stdout.lower())
        self.assertNotIn('state-v2', result.stdout.lower())
        self.assertNotIn('--apply', result.stdout)

    def test_default_material_path_and_sudo_arguments_in_public_main(self):
        built = []
        def build(path):
            self.assertNotEqual(m.os.geteuid(), 0)
            built.append(path)
            shutil.copytree(self.payload, path, symlinks=True)
        def execute(argv, **kwargs):
            self.assertEqual(argv[:6], ['/usr/bin/sudo', '--', '/usr/bin/python3', '-I', '-B', str(HERE / 'install.py')])
            self.assertNotIn('--materials', argv)
            self.assertEqual(argv[argv.index('--default-materials')+1], str(self.source))
            self.assertEqual(bool(built), '--apply' in argv)
            return SimpleNamespace(returncode=0)
        with patch.object(Path, 'home', return_value=self.base), \
                patch.object(m.os, 'geteuid', return_value=1000), \
                patch.object(sys, 'argv', [str(HERE / 'install.py')]), \
                patch.object(m.builder, 'build_payload', side_effect=build), \
                patch.object(m.subprocess, 'run', side_effect=execute):
            self.assertEqual(m.main(), 0)

    def test_missing_native_sources_stop_before_sudo_or_dependencies(self):
        with patch.object(m.os, 'geteuid', return_value=1000), \
                patch.object(sys, 'argv', ['install.py', '--install-dependencies']), \
                patch.object(m.builder, 'validate_chicago_sources',
                             side_effect=RuntimeError('incomplete ChicagoHS native source set')), \
                patch.object(m.subprocess, 'run') as run, \
                patch.object(m.builder, 'build_payload') as build, \
                self.assertRaisesRegex(RuntimeError, 'incomplete ChicagoHS native source set'):
            m.main()
        run.assert_not_called()
        build.assert_not_called()

    def test_failed_material_preflight_never_installs_packages_or_builds(self):
        for explicit in ([], ['--materials', str(self.source)]):
            with self.subTest(explicit=bool(explicit)), \
                    patch.object(Path, 'home', return_value=self.base), \
                    patch.object(m.os, 'geteuid', return_value=1000), \
                    patch.object(sys, 'argv', ['install.py', '--install-dependencies', *explicit]), \
                    patch.object(m.builder, 'build_payload') as build, \
                    patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as run:
                self.assertEqual(m.main(), 1)
                build.assert_not_called()
                run.assert_called_once()
                argv = run.call_args.args[0]
                self.assertIn('--material-preflight', argv)
                self.assertEqual('--materials' in argv, bool(explicit))

    def test_dependencies_follow_material_preflight_and_build_remains_unprivileged(self):
        order = []

        def execute(argv, **kwargs):
            self.assertEqual(m.os.geteuid(), 1000)
            if '--material-preflight' in argv:
                order.append('preflight')
            elif '/usr/bin/dnf' in argv:
                self.assertEqual(argv[:4], ['/usr/bin/sudo', '--', '/usr/bin/dnf', 'install'])
                self.assertTrue(set(m.builder.BUILD_PACKAGES + m.RUNTIME_PACKAGES) <= set(argv))
                order.append('packages')
            else:
                self.assertIn('--apply', argv)
                self.assertIn('--materials', argv)
                order.append('apply')
            return SimpleNamespace(returncode=0)

        def build(path):
            self.assertEqual(m.os.geteuid(), 1000)
            order.append('build')
            shutil.copytree(self.payload, path, symlinks=True)

        with patch.object(m.os, 'geteuid', return_value=1000), \
                patch.object(sys, 'argv', ['install.py', '--install-dependencies', '--materials', str(self.source)]), \
                patch.object(m.builder, 'build_payload', side_effect=build), \
                patch.object(m.subprocess, 'run', side_effect=execute):
            self.assertEqual(m.main(), 0)
        self.assertEqual(order, ['preflight', 'packages', 'build', 'apply'])

    def test_check_defers_installed_material_without_sudo_or_home(self):
        self.apply()
        shutil.rmtree(self.source)
        with patch.object(m.os, 'geteuid', return_value=1000), \
                patch.object(sys, 'argv', ['install.py', '--check']), \
                patch.object(m.subprocess, 'run') as run, \
                patch.object(m.materials, 'validate_bundle') as validate:
            self.assertEqual(m.main(), 0)
            run.assert_not_called()
            validate.assert_not_called()
        self.assertIn('INSTALLED_MATERIAL_VALIDATION=DEFERRED', self.stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
