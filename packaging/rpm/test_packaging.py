#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Source distribution, version and no-activation packaging contracts."""
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rpm_build', HERE / 'build.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class Packaging(unittest.TestCase):
    def test_source_archive_reproducible_and_private_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for folder in b.SOURCE_DIRS:
                (root / folder).mkdir(parents=True, exist_ok=True)
            for name in b.SOURCE_FILES:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text('3.0.0\n')
            (root / 'development').mkdir()
            (root / 'development/secret').write_text('must not ship')
            data = b.archive_bytes(root, '3.0.0')
            self.assertEqual(data, b.archive_bytes(root, '3.0.0'))
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                self.assertFalse(any('/development/' in n for n in archive.getnames()))
                self.assertEqual(len(archive.getnames()), len(b.SOURCE_FILES))
            (root / 'production/secret.key').write_text('must refuse')
            with self.assertRaisesRegex(RuntimeError, 'non-source'):
                b.archive_bytes(root, '3.0.0')

    def test_redirected_source_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for folder in b.SOURCE_DIRS:
                (root / folder).mkdir(parents=True, exist_ok=True)
            for name in b.SOURCE_FILES:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text('3.0.0\n')
            (root / 'production/redirect.py').symlink_to(root / 'VERSION')
            with self.assertRaisesRegex(RuntimeError, 'not a regular'):
                b.archive_bytes(root, '3.0.0')

    def test_redirected_source_directory_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, outside = base / 'source', base / 'private'
            root.mkdir()
            outside.mkdir()
            (outside / 'private-note.txt').write_text('must not ship')
            (root / 'production').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, 'redirected source directory'):
                b.archive_bytes(root, '3.0.0')

    def test_rpm_does_not_pin_fedora_system_release(self):
        spec = (HERE / 'goodix-manager.spec.in').read_text()
        self.assertNotRegex(spec, r'(?m)^Requires:\s+system-release(?:\(|\s)')
        self.assertIn('ExclusiveArch:  x86_64', spec)

    def test_rpm_does_not_own_runtime_or_execute_scriptlets(self):
        spec = (HERE / 'goodix-manager.spec.in').read_text()
        for scriptlet in ('%pre\n', '%post\n', '%preun\n', '%postun\n', '%trigger', '%posttrans'):
            self.assertNotIn(scriptlet, spec)
        files = spec.split('%files\n')[1]
        for path in ('/usr/local/', '/etc/pam.d/', '/var/lib/fprint', '/etc/systemd/'):
            self.assertNotIn(path, files)
        self.assertIn('__provides_exclude_from', spec)


if __name__ == '__main__':
    unittest.main()
