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
        for key in ('CONFIG', 'SUPPORT', 'RUNTIME', 'DROPIN', 'MASK', 'NORMAL', 'FORCE', 'RECOVERY', 'MATERIAL'):
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
        self.fail_login = False
        self.ctx.enter_context(patch.object(m, 'command', side_effect=self.command))
        self.ctx.enter_context(patch.object(m.r, 'command', side_effect=self.command))
        self.ctx.enter_context(patch.object(m, 'supported_system'))
        self.ctx.enter_context(patch.object(m, 'prerequisites'))
        self.ctx.enter_context(patch.object(m, 'safe_parent', side_effect=m.r.parents))
        self.ctx.enter_context(patch.object(m.r, 'trusted', side_effect=self.trusted))
        self.ctx.enter_context(patch.object(m, 'label_materials', side_effect=self.labels))
        self.ctx.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.ctx.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.source = self.base / 'goodix-5125-materials'
        self.source.mkdir(mode=0o700)
        # The full metadata/format/crypto contract is tested by test_materials;
        # this transaction fixture deliberately contains no real device data.
        for name in m.r.MATERIAL_NAMES:
            (self.source / name).write_bytes(b'SYNTHETIC ' + name.encode())
        self.bundle = object()
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
        self.assertEqual(Path(path), self.source)
        m.require({p.name for p in path.iterdir()} == set(m.r.MATERIAL_NAMES), 'five files required')
        m.require(all(p.is_file() and not p.is_symlink() for p in path.iterdir()), 'material source type')
        return self.bundle

    def import_material(self, bundle, destination, *, native_check):
        self.assertIs(bundle, self.bundle)
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
        self.assertTrue(self.rule)

    def command(self, *args):
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
        if args[0].endswith('/check-material'):
            self.assertEqual(Path(args[1]), m.r.MATERIAL)
            return 'GOODIX_MATERIAL_CHECK=PASS'
        raise AssertionError('unmocked host command: ' + repr(args))

    def make_payload(self, directory):
        directory.mkdir()
        names = {'runtime/libfprint-2.so.2.0.0', 'runtime/OpenCV-LICENSES.txt',
                 'runtime/LICENSING_AND_PROVENANCE.md', 'runtime/source-files.sha256',
                 'runtime/build-provenance.json', 'login/' + m.r.MODULE,
                 'login/plasmalogin.pam', 'check-material',
                 *(f'runtime/licenses/{n}.txt' for n in m.builder.LICENSES),
                 *(f'runtime/libopencv_{n}.so.413' for n in m.builder.OPENCV_PARTS)}
        manifest = {'schema': 1, 'source_id': 'a' * 64, 'files': {}, 'links': {}}
        for name in names:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            data = (self.clone / 'deployment/plasma-login-opt-in/plasmalogin.pam').read_bytes() \
                if name == 'login/plasmalogin.pam' else b'SYNTHETIC PUBLIC PAYLOAD ' + name.encode()
            target.write_bytes(data)
            target.chmod(0o755 if name == 'check-material' else 0o644)
            manifest['files'][name] = m.r.digest(data)
        for name, target in m.r.LINKS.items():
            (directory / 'runtime' / name).symlink_to(target)
            manifest['links']['runtime/' + name] = target
        (directory / 'payload.json').write_text(json.dumps(manifest))

    def apply(self):
        with patch.object(m.os, 'geteuid', return_value=0):
            m.apply(self.payload, self.source, os.getuid())

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
        self.assertEqual(m.r.DROPIN.read_bytes(),
            b'[Service]\nEnvironment=LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125\n'
            b'BindReadOnlyPaths=/dev/null:/proc/sys/vm/nr_hugepages\n')
        self.assert_preserved()
        self.assertEqual(m.r.remove(), 0)
        self.assert_preserved()
        self.assertFalse(m.r.RUNTIME.exists())
        self.assertFalse(m.r.DROPIN.exists())

    def legacy_environment(self, *args):
        if args == ('systemctl', 'show', 'fprintd.service', '-p', 'Environment', '--value'):
            return 'LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125'
        return self.command(*args)

    def test_upgrade_from_public_legacy_dropin(self):
        self.apply()
        m.r.DROPIN.write_bytes(m.r.LEGACY_DROPIN_BYTES)
        with patch.object(m, 'command', side_effect=self.legacy_environment):
            self.apply()
        self.assertEqual(m.r.DROPIN.read_bytes(), m.r.DROPIN_BYTES)
        self.apply()  # Reinstall must neither duplicate nor lose the mount.
        self.assertEqual(m.r.DROPIN.read_bytes(), m.r.DROPIN_BYTES)
        self.assert_preserved()

    def test_failed_upgrade_restores_exact_legacy_dropin(self):
        self.apply()
        m.r.DROPIN.write_bytes(m.r.LEGACY_DROPIN_BYTES)
        with patch.object(m, 'command', side_effect=self.legacy_environment), \
                patch.object(m, 'install_login', side_effect=RuntimeError('synthetic failed upgrade')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic failed upgrade'):
                self.apply()
        self.assertEqual(m.r.DROPIN.read_bytes(), m.r.LEGACY_DROPIN_BYTES)
        m.r.normal_preflight()
        self.assert_preserved()

    def test_modified_mount_is_rejected_before_service_mutation(self):
        self.apply()
        for extra in (b'BindReadOnlyPaths=/dev/null:/proc/sys/vm\n', b'ExecStart=/other\n'):
            m.r.DROPIN.write_bytes(m.r.LEGACY_DROPIN_BYTES + extra)
            self.events.clear()
            with self.assertRaisesRegex(RuntimeError, 'drop-in drift'):
                self.apply()
            self.assertNotIn(('systemctl', 'stop', 'fprintd.service'), self.events)

    def test_force_recovers_partial_install_with_only_dropin_and_tools(self):
        self.apply()
        for path in (m.r.CONFIG, m.r.SUPPORT, m.r.RUNTIME):
            m.r.remove_path(path)
        (m.r.RECOVERY / 'receipt.json').unlink()
        self.assertEqual(m.r.remove(force=True), 0)
        self.assertFalse(m.r.DROPIN.exists())
        self.assert_preserved()

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

    def test_partial_install_rolls_back_software_preserves_complete_materials(self):
        with patch.object(m, 'install_login', side_effect=RuntimeError('synthetic login failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic login failure'):
                self.apply()
        self.assertFalse(any(m.r.present(p) for p in m.software_paths()))
        self.assertFalse(self.rule)
        self.assertFalse(m.r.MASK.is_symlink())
        self.assert_preserved()

    def test_failed_update_restores_prior_project_installation(self):
        self.apply()
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        with patch.object(m, 'install_login', side_effect=RuntimeError('synthetic failed update')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic failed update'):
                self.apply()
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        m.r.normal_preflight()
        self.assertTrue(self.rule)
        self.assert_preserved()

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
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        def reject_native(*args):
            if str(args[0]).endswith('/check-material'):
                raise RuntimeError('synthetic native binding rejected')
            return self.command(*args)
        with patch.object(m, 'command', side_effect=reject_native):
            with self.assertRaisesRegex(RuntimeError, 'synthetic native binding rejected'):
                self.apply()
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        m.r.normal_preflight()
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
            for key in ('CONFIG', 'SUPPORT', 'RUNTIME', 'DROPIN', 'MASK', 'NORMAL', 'FORCE', 'RECOVERY', 'MATERIAL'):
                setattr(module, key, getattr(m.r, key))
            module.command = self.command
            module.trusted = self.trusted
            with patch.object(module.os, 'geteuid', return_value=0), \
                    patch.object(sys, 'argv', [str(installed)]):
                self.assertEqual(module.main(), 0)
            self.assert_preserved()
            self.assertFalse(module.DROPIN.exists())
            shutil.copytree(HERE.parent / 'deployment', self.clone / 'deployment', ignore=shutil.ignore_patterns('__pycache__'))

    def test_root_shell_entry_resolves_alternate_clone_and_foreign_cwd(self):
        result = subprocess.run([str(self.clone / 'install.sh'), '--help'], cwd='/tmp', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--materials', result.stdout)
        self.assertNotIn('--apply', result.stdout)

    def test_default_material_path_and_sudo_arguments_in_public_main(self):
        built = []
        def build(path):
            built.append(path)
            shutil.copytree(self.payload, path, symlinks=True)
        def execute(argv, **kwargs):
            self.assertEqual(argv[:6], ['/usr/bin/sudo', '--', '/usr/bin/python3', '-I', '-B', str(HERE / 'install.py')])
            self.assertEqual(argv[argv.index('--materials')+1], str(self.source))
            self.assertTrue(built)
            return SimpleNamespace(returncode=0)
        with patch.object(Path, 'home', return_value=self.base), \
                patch.object(m.os, 'geteuid', return_value=1000), \
                patch.object(sys, 'argv', [str(HERE / 'install.py')]), \
                patch.object(m.builder, 'build_payload', side_effect=build), \
                patch.object(m.subprocess, 'run', side_effect=execute):
            self.assertEqual(m.main(), 0)


class Confinement(unittest.TestCase):
    def test_installer_requires_enforcing(self):
        with patch.object(m.platform, 'freedesktop_os_release', return_value={'ID': 'fedora', 'VERSION_ID': '44'}), \
                patch.object(m.platform, 'machine', return_value='x86_64'):
            for state in ('Permissive', 'Disabled'):
                with patch.object(m, 'command', return_value=state), self.assertRaisesRegex(RuntimeError, 'Enforcing'):
                    m.supported_system()
            with patch.object(m, 'command', return_value='Enforcing'):
                m.supported_system()


if __name__ == '__main__':
    unittest.main()
