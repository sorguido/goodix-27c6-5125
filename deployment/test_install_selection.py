#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Real validators on synthetic bundles; no privileges, host mutation or USB."""
import importlib.util
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('selection_installer', HERE / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
fixtures = installer.load('selection_fixtures', HERE / 'test_materials.py')


class Selection(fixtures.MaterialFixture):
    def setUp(self):
        super().setUp()
        self.installed = self.root / 'installed'
        self.software = self.root / 'software'
        self.bad_owner = False
        self.bad_group = False
        self.validated = []
        real_validate = fixtures.materials.validate_bundle

        def validate(path, **kwargs):
            self.validated.append(Path(path))
            if Path(path) == self.installed:
                # Assert the production root:root contract, then map only the
                # fixture owner to the current unprivileged test user.
                self.assertEqual(kwargs, dict(source=False, owner_uid=0, owner_gid=0))
                kwargs.update(owner_uid=os.getuid() + int(self.bad_owner),
                              owner_gid=os.getgid() + int(self.bad_group))
            return real_validate(path, **kwargs)

        for seam in (patch.object(installer, 'materials', fixtures.materials),
                     patch.object(installer.r, 'MATERIAL', self.installed),
                     patch.object(installer, 'software_paths', return_value=(self.software,)),
                     patch.object(installer, 'safe_parent'),
                     patch.object(installer.os, 'geteuid', return_value=0),
                     patch.object(fixtures.materials, 'validate_bundle', side_effect=validate)):
            seam.start()
            self.addCleanup(seam.stop)

    def select(self, explicit=False):
        return installer.select_materials(self.source, os.getuid(), explicit=explicit)

    def populate_installed(self):
        fixtures.write_bundle(self.installed, self.files)

    def test_automatic_modes(self):
        mode, bundle, reuse = self.select()
        self.assertEqual((mode, reuse), ('FIRST_INSTALL', False))
        self.assertEqual(bundle.files, self.files)
        self.populate_installed()
        self.assertEqual(self.select()[::2], ('REINSTALL', True))
        self.software.touch()
        self.assertEqual(self.select()[::2], ('UPDATE', True))

    def test_no_material_requires_original_bundle(self):
        shutil.rmtree(self.source)
        for remaining_software in (False, True):
            if remaining_software:
                self.software.touch()
            with self.subTest(remaining_software=remaining_software), \
                    self.assertRaisesRegex(RuntimeError, 'REASON=no_device_material_available.*five-file'):
                self.select()
        self.assertFalse(self.validated)
        self.assertFalse(self.installed.exists())

    def test_material_loss_with_remaining_software_does_not_import_another_identity(self):
        self.software.touch()
        with self.assertRaisesRegex(RuntimeError, 'REASON=installed_material_missing'):
            self.select()
        self.assertFalse(self.validated)

    def test_ordinary_selection_ignores_identical_different_invalid_or_absent_home(self):
        self.populate_installed()
        self.software.touch()
        for home in ('identical', 'different', 'invalid', 'absent'):
            with self.subTest(home=home):
                if home == 'different':
                    shutil.rmtree(self.source)
                    fixtures.write_bundle(self.source, fixtures.synthetic_files(2))
                elif home == 'invalid':
                    (self.source / fixtures.materials.NAMES[0]).write_bytes(b'invalid')
                elif home == 'absent':
                    shutil.rmtree(self.source)
                self.validated.clear()
                mode, bundle, reuse = self.select()
                self.assertEqual((mode, reuse), ('UPDATE', True))
                self.assertEqual(bundle.files, self.files)
                self.assertEqual(self.validated, [self.installed])

    def test_explicit_first_install_and_identical_installed_bundle(self):
        self.assertEqual(self.select(explicit=True)[0], 'FIRST_INSTALL')
        self.populate_installed()
        self.assertEqual(self.select(explicit=True)[0], 'REINSTALL')
        self.assertEqual(installer.select_materials(self.installed, os.getuid(), explicit=True)[0], 'REINSTALL')

    def test_explicit_different_or_missing_bundle_stops_without_replacement(self):
        self.populate_installed()
        before = {p.name: p.stat().st_ino for p in self.installed.iterdir()}
        shutil.rmtree(self.source)
        fixtures.write_bundle(self.source, fixtures.synthetic_files(2))
        with self.assertRaisesRegex(RuntimeError, 'REASON=explicit_material_mismatch'):
            self.select(explicit=True)
        shutil.rmtree(self.source)
        with self.assertRaises(OSError):
            self.select(explicit=True)
        self.assertEqual(before, {p.name: p.stat().st_ino for p in self.installed.iterdir()})

    def test_invalid_installed_state_never_falls_back_to_valid_home(self):
        for drift in ('missing', 'extra', 'manifest', 'hash', 'binding', 'directory-mode',
                      'file-mode', 'owner', 'group', 'symlink', 'dangling-link',
                      'directory-fifo', 'file-fifo', 'file-link', 'hardlink', 'regular-path'):
            with self.subTest(drift=drift):
                self.populate_installed()
                path = self.installed / fixtures.materials.NAMES[1]
                if drift == 'missing': path.unlink()
                if drift == 'extra': (self.installed / 'extra').touch()
                if drift == 'manifest': (self.installed / fixtures.materials.NAMES[0]).write_bytes(b'{}')
                if drift == 'hash': path.write_bytes(path.read_bytes()[:-1] + b'x')
                if drift == 'binding':
                    files = fixtures.refresh_manifest(dict(self.files), otp_a6_response_sha256='0' * 64)
                    (self.installed / fixtures.materials.NAMES[0]).write_bytes(files[fixtures.materials.NAMES[0]])
                if drift == 'directory-mode': self.installed.chmod(0o755)
                if drift == 'file-mode': path.chmod(0o644)
                self.bad_owner, self.bad_group = drift == 'owner', drift == 'group'
                if drift in ('symlink', 'dangling-link', 'directory-fifo', 'regular-path'):
                    shutil.rmtree(self.installed)
                    if drift in ('symlink', 'dangling-link'):
                        self.installed.symlink_to(self.source if drift == 'symlink' else self.root / 'absent')
                    elif drift == 'regular-path': self.installed.touch()
                    else: os.mkfifo(self.installed, 0o600)
                if drift in ('file-link', 'file-fifo'):
                    path.unlink()
                    if drift == 'file-link': path.symlink_to(self.source / path.name)
                    else: os.mkfifo(path, 0o600)
                if drift == 'hardlink': os.link(path, self.root / 'outside-link')
                self.validated.clear()
                with self.assertRaisesRegex(RuntimeError, 'REASON=invalid_installed_material'):
                    self.select()
                self.assertEqual(self.validated, [self.installed])
                if self.installed.is_dir() and not self.installed.is_symlink():
                    shutil.rmtree(self.installed)
                else: self.installed.unlink()
                (self.root / 'outside-link').unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
